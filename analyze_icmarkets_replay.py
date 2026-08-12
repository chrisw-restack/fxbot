"""Replay the frozen live suite against a UTC-normalized IC Markets export.

This is an audit utility, not a parameter optimizer. It writes machine-readable
trade, event, and summary files so broker-native results can be reconciled with
the MT5 account report.
"""

from __future__ import annotations

import argparse
import csv
import gc
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import config
from backtest_engine import BacktestEngine
from data.historical_loader import bar_close_time, load_and_merge
from live_config import create_live_strategy_specs, live_risk_pct_overrides


WARMUP_BARS = {'D1': 50, 'H4': 100, 'H1': 100, 'M15': 200, 'M5': 250}
TF_RANK = {'M5': 0, 'M15': 1, 'H1': 2, 'H4': 3, 'D1': 4}


class MemoryJournal:
    def __init__(self):
        self.rows: list[dict] = []

    def _add(self, event: str, signal=None, reason: str = '', ticket=None, pos=None):
        source = signal or pos or {}
        get = source.get if isinstance(source, dict) else lambda key, default='': getattr(source, key, default)
        timestamp = get('timestamp', '')
        self.rows.append({
            'event': event,
            'ticket': ticket if ticket is not None else get('ticket', ''),
            'symbol': get('symbol', ''),
            'strategy_name': get('strategy_name', ''),
            'direction': get('direction', ''),
            'order_type': get('order_type', ''),
            'signal_time': timestamp.isoformat() if hasattr(timestamp, 'isoformat') else timestamp,
            'entry_price': get('entry_price', get('open_price', '')),
            'stop_loss': get('stop_loss', get('sl', '')),
            'take_profit': get('take_profit', get('tp', '')),
            'lot_size': get('lot_size', get('volume', '')),
            'reason': reason,
        })

    def log_signal(self, signal, context=None):
        self._add('SIGNAL', signal=signal)

    def log_cancel_requested(self, signal, context=None):
        self._add('CANCEL_REQUESTED', signal=signal)

    def log_rejected(self, signal, reason, context=None):
        self._add('REJECTED', signal=signal, reason=reason)

    def log_order_placed(self, signal, ticket, context=None, execution_details=None):
        self._add('ORDER_PLACED', signal=signal, ticket=ticket)

    def log_order_cancelled(self, pos, reason=''):
        self._add('ORDER_CANCELLED', pos=pos, reason=reason)

    def log_cancel_failed(self, pos, reason='', details=None):
        self._add('CANCEL_FAILED', pos=pos, reason=reason)


def _paths_for_specs(data_dir: Path, specs) -> list[str]:
    paths: list[str] = []
    seen: set[Path] = set()
    for strategy, symbols in specs:
        for symbol in symbols:
            for timeframe in strategy.TIMEFRAMES:
                matches = sorted(data_dir.glob(f'{symbol}_{timeframe}_*.csv'))
                if not matches:
                    raise FileNotFoundError(f'Missing export for {symbol} {timeframe}')
                for match in matches:
                    if match not in seen:
                        paths.append(str(match))
                        seen.add(match)
    return paths


def _warmup(engine: BacktestEngine, bars, start: datetime) -> list:
    before: dict[tuple[str, str], list] = defaultdict(list)
    active = []
    for bar in bars:
        if bar.timestamp < start:
            before[(bar.symbol, bar.timeframe)].append(bar)
        else:
            active.append(bar)

    warmup = []
    for (_, timeframe), pair_bars in before.items():
        warmup.extend(pair_bars[-WARMUP_BARS.get(timeframe, 50):])
    warmup.sort(key=lambda bar: (bar_close_time(bar), TF_RANK.get(bar.timeframe, 99), bar.symbol))
    for bar in warmup:
        engine.event_engine.warmup_bar(bar)
    return active


def _run(engine: BacktestEngine, paths: list[str], start: datetime | None, end: datetime | None):
    load_start = None
    if start is not None:
        # D1 needs 50 completed sessions; 90 calendar days gives ample room.
        load_start = start - pd_timedelta_days(90)
    bars = load_and_merge(paths, start=load_start, end=end)
    if start is not None:
        bars = _warmup(engine, bars, start)

    for bar in bars:
        closed_trades = engine.execution.check_fills(bar)
        for trade in closed_trades:
            engine.portfolio.record_close(
                trade['symbol'], trade['pnl'], trade.get('strategy_name', '')
            )
            engine.trade_logger.log_close(trade['ticket'], trade)
            engine.event_engine.notify_trade_closed(trade)
        engine.event_engine.process_bar(bar)


def pd_timedelta_days(days: int):
    # Avoid making pandas part of this audit script's public interface.
    from datetime import timedelta
    return timedelta(days=days)


def _net_r(trade: dict) -> float:
    pip_value = config.PIP_VALUE_USD[trade['symbol']]
    initial_risk = trade['sl_pips'] * pip_value * trade['lot_size']
    return trade['pnl'] / initial_risk if initial_risk else 0.0


def _summary(name: str, trades: list[dict], journal: MemoryJournal, engine: BacktestEngine) -> dict:
    ordered = sorted(trades, key=lambda trade: trade['close_time'])
    net_rs = [_net_r(trade) for trade in ordered]
    gross_win = sum(value for value in net_rs if value > 0)
    gross_loss = -sum(value for value in net_rs if value < 0)
    running = peak = max_dd = 0.0
    loss_streak = worst_streak = 0
    for value in net_rs:
        running += value
        peak = max(peak, running)
        max_dd = max(max_dd, peak - running)
        if value <= 0:
            loss_streak += 1
            worst_streak = max(worst_streak, loss_streak)
        else:
            loss_streak = 0

    events = Counter(row['event'] for row in journal.rows)
    rejection_reasons = Counter(
        row['reason'] for row in journal.rows if row['event'] == 'REJECTED'
    )
    return {
        'scenario': name,
        'trades': len(ordered),
        'wins': sum(value > 0 for value in net_rs),
        'win_rate_pct': round(sum(value > 0 for value in net_rs) / len(net_rs) * 100, 3) if net_rs else 0.0,
        'price_r': round(sum(trade['r_multiple'] for trade in ordered), 4),
        'net_r': round(sum(net_rs), 4),
        'net_expectancy_r': round(sum(net_rs) / len(net_rs), 4) if net_rs else 0.0,
        'net_profit_factor': round(gross_win / gross_loss, 4) if gross_loss else None,
        'net_pnl': round(sum(trade['pnl'] for trade in ordered), 2),
        'commission': round(sum(trade.get('commission', 0.0) for trade in ordered), 2),
        'max_drawdown_net_r': round(max_dd, 4),
        'worst_loss_streak': worst_streak,
        'events': dict(events),
        'rejection_reasons': dict(rejection_reasons),
        'open_positions_or_orders': len(engine.execution.get_open_positions()),
    }


def _write_scenario(output_dir: Path, name: str, summary: dict, trades, journal):
    output_dir.mkdir(parents=True, exist_ok=True)
    safe = name.lower().replace(' ', '_').replace('/', '_')
    (output_dir / f'{safe}_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')

    trade_rows = []
    for trade in trades:
        row = dict(trade)
        row['net_r'] = round(_net_r(trade), 6)
        for field in ('signal_time', 'open_time', 'close_time'):
            value = row.get(field)
            if hasattr(value, 'isoformat'):
                row[field] = value.isoformat()
        trade_rows.append(row)
    if trade_rows:
        fields = sorted({key for row in trade_rows for key in row})
        with (output_dir / f'{safe}_trades.csv').open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(trade_rows)

    if journal.rows:
        fields = list(journal.rows[0])
        with (output_dir / f'{safe}_events.csv').open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(journal.rows)


def run_scenario(data_dir: Path, output_dir: Path, name: str, specs, start, end, suite: bool):
    engine = BacktestEngine(
        initial_balance=30_000.0,
        rr_ratio=2.5,
        risk_pct_overrides=live_risk_pct_overrides(),
        max_open_trades=config.MAX_OPEN_TRADES if suite else 99,
        max_daily_loss_pct=config.MAX_DAILY_LOSS_PCT if suite else None,
    )
    journal = MemoryJournal()
    engine.event_engine.trade_journal = journal
    for strategy, symbols in specs:
        engine.add_strategy(strategy, symbols)
    paths = _paths_for_specs(data_dir, specs)
    _run(engine, paths, start=start, end=end)
    trades = list(engine.execution._closed_trades)
    summary = _summary(name, trades, journal, engine)
    _write_scenario(output_dir, name, summary, trades, journal)
    print(json.dumps(summary, sort_keys=True))
    del engine, trades, journal
    gc.collect()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--mode', choices=['individual', 'suite'], required=True)
    parser.add_argument(
        '--strategy',
        action='append',
        help='In individual mode, run only this strategy NAME (repeatable).',
    )
    parser.add_argument('--start', default=None)
    parser.add_argument('--end', default='2026-08-12')
    args = parser.parse_args()
    start = datetime.strptime(args.start, '%Y-%m-%d') if args.start else None
    end = datetime.strptime(args.end, '%Y-%m-%d') if args.end else None

    if args.mode == 'individual':
        specs = create_live_strategy_specs()
        if args.strategy:
            wanted = set(args.strategy)
            available = {strategy.NAME for strategy, _ in specs}
            unknown = wanted - available
            if unknown:
                parser.error(
                    f"Unknown strategy name(s): {', '.join(sorted(unknown))}. "
                    f"Available: {', '.join(sorted(available))}"
                )
            specs = [spec for spec in specs if spec[0].NAME in wanted]

        for strategy, symbols in specs:
            run_scenario(
                args.data_dir,
                args.output_dir,
                strategy.NAME,
                [(strategy, symbols)],
                start,
                end,
                suite=False,
            )
    else:
        run_scenario(
            args.data_dir,
            args.output_dir,
            'current_live_suite',
            create_live_strategy_specs(),
            start,
            end,
            suite=True,
        )


if __name__ == '__main__':
    main()
