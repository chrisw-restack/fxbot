"""Fixed-parameter EmaFib audit. Read-only observers, sequential CSV replays.

Run with .venv/Scripts/python research_ema_fib_review.py. Never connects to MT5.
No strategy settings or production state are changed by this research script.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import inspect
import json
import logging
from pathlib import Path
import subprocess
import time

import pandas as pd
import config
from backtest_engine import BacktestEngine
from data.historical_loader import find_csv, load_and_merge, bar_close_time
from data.histdata_provenance import file_hash, metadata_path, write_json
from research_ema_fib_baseline import EmaFibRetracementStrategy, REVISION

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'output/ema_fib_review_20260923'
PERIODS = [('2020_2025', datetime(2020, 1, 1), datetime(2026, 1, 1)),
           ('2026_to_july14', datetime(2026, 1, 1), datetime(2026, 7, 15))]


def current_settings():
    """Return the reviewed settings, retained after retirement from the DEMO suite."""
    strategy = EmaFibRetracementStrategy(
        fib_entry=0.786, fib_tp=3.0, fractal_n=3, min_swing_pips=10,
        ema_sep_pct=0.001, cooldown_bars=10, invalidate_swing_on_loss=True,
        blocked_hours=(*range(20,24), *range(0,9)),
    )
    symbols = ['EURUSD','GBPUSD','AUDUSD','NZDUSD','USDJPY','USDCAD','USDCHF']
    params = {k: getattr(strategy, k) for k in inspect.signature(EmaFibRetracementStrategy).parameters}
    params['blocked_hours'] = sorted(params['blocked_hours'])
    return params, symbols


def metrics(trades):
    trades = sorted(trades, key=lambda t: (t['close_time'], t['symbol'], t['ticket']))
    rs = [t['net_r'] for t in trades]
    profit, loss = sum(r for r in rs if r > 0), -sum(r for r in rs if r < 0)
    total = peak = dd = 0.0
    wins = losses = max_wins = max_losses = 0
    for r in rs:
        total += r
        peak = max(peak, total)
        dd = max(dd, peak-total)
        wins = wins+1 if r > 0 else 0
        losses = losses+1 if r < 0 else 0
        max_wins, max_losses = max(max_wins, wins), max(max_losses, losses)
    return dict(trades=len(rs), win_rate=100*sum(r > 0 for r in rs)/len(rs) if rs else None,
                total_r=total, profit_factor=profit/loss if loss else None,
                expectancy=total/len(rs) if rs else None, max_dd_r=dd,
                max_win_streak=max_wins, max_loss_streak=max_losses)


class ObservedEmaFib(EmaFibRetracementStrategy):
    """Records state differences without altering the strategy's decisions."""
    def __init__(self, **params):
        super().__init__(**params)
        self.audit = Counter()
        self.examples = {}
        self.accepted = {}
        self.execution = None

    def note(self, key, **details):
        self.audit[key] += 1
        examples = self.examples.setdefault(key, [])
        if len(examples) < 3:
            examples.append(deepcopy(details))

    def snapshot(self, symbol):
        return self._pending_swing_high.get(symbol), self._pending_swing_low.get(symbol)

    def generate_signal(self, event):
        symbol = event.symbol
        local_entry = self._pending_entry.get(symbol)
        pending = list(self.execution._pending.values()) if self.execution else []
        occupied = self.execution.get_open_positions() if self.execution else []
        signal = super().generate_signal(event)
        if event.timeframe == 'H1' and local_entry is not None and event.low <= local_entry <= event.high:
            actual_pending = [p for p in pending if p['symbol'] == symbol]
            if actual_pending:
                self.note('heuristic_consumed_while_execution_pending', time=event.timestamp,
                          local_entry=local_entry, actual=actual_pending)
        if signal and signal.direction != 'CANCEL' and occupied:
            self.note('proposal_while_slot_occupied', time=event.timestamp, snapshot=self.snapshot(symbol))
        return signal

    def notify_order_accepted(self, signal, ticket, details=None):
        self.accepted[ticket] = self.snapshot(signal.symbol)
        self.audit['accepted_orders'] += 1

    def notify_order_cancelled(self, order):
        self.accepted.pop(order['ticket'], None)
        self.audit['confirmed_cancellations'] += 1

    def notify_trade_closed(self, trade):
        symbol = trade['symbol']
        origin = self.accepted.pop(trade['ticket'], None)
        before = self.snapshot(symbol)
        if trade['result'] == 'LOSS':
            super().notify_loss(symbol)
            used = self._used_swing_high[symbol], self._used_swing_low[symbol]
            if origin is not None and used != origin:
                self.note('loss_invalidated_wrong_swing', ticket=trade['ticket'], time=trade['close_time'],
                          accepted_swing=origin, snapshot_at_close=before, marked_used=used)
        elif trade['result'] == 'WIN':
            super().notify_win(symbol)
        if self._pending_entry.get(symbol) is not None:
            self.note('close_left_local_pending', ticket=trade['ticket'], time=trade['close_time'],
                      local_entry=self._pending_entry[symbol])


def paths_for(source, symbol):
    files = []
    for tf in ('M5', 'H1', 'D1'):
        found = find_csv(symbol, tf, data_source=source)
        if not found:
            raise ValueError(f'Missing {source} {symbol} {tf}')
        files.extend(found)
    return files


def replay(bars, symbol, params, start, end, observed=True):
    strategy = ObservedEmaFib(**params) if observed else EmaFibRetracementStrategy(**params)
    engine = BacktestEngine(initial_balance=10000)
    if observed:
        strategy.execution = engine.execution
    engine.add_strategy(strategy, [symbol])
    trades = engine.replay(bars, start_date=start, end_date=end)
    return trades, engine, strategy


def price_comparison(paths):
    result = []
    for symbol, sources in paths.items():
        for tf in ('M5', 'H1', 'D1'):
            frames = {}
            for source, files in sources.items():
                selected = [p for p in files if f'_{tf}_' in Path(p).name]
                frame = pd.concat([pd.read_csv(p) for p in selected])
                time_col = 'time' if 'time' in frame.columns else 'timestamp'
                frame[time_col] = pd.to_datetime(frame[time_col])
                frame = frame.set_index(time_col)
                frames[source] = frame.loc[(frame.index >= PERIODS[0][1]) & (frame.index < PERIODS[-1][2])]
                assert frames[source].index.is_unique
            d, h = frames['dukascopy'], frames['histdata']
            common = d.index.intersection(h.index)
            equal = (d.loc[common, ['open','high','low','close']].round(8) ==
                     h.loc[common, ['open','high','low','close']].round(8)).all(axis=1)
            result.append(dict(symbol=symbol, timeframe=tf, dukascopy_bars=len(d), histdata_bars=len(h),
                               common_bars=len(common), identical_ohlc_pct=100*equal.mean(),
                               absent_from_histdata=len(d.index.difference(h.index)),
                               absent_from_dukascopy=len(h.index.difference(d.index))))
    return result


def main():
    logging.disable(logging.CRITICAL)
    OUT.mkdir(parents=True, exist_ok=True)
    params, symbols = current_settings()
    paths = {sym: {src: paths_for(src, sym) for src in ('dukascopy', 'histdata')} for sym in symbols}
    code = ['research_ema_fib_review.py', 'research_ema_fib_baseline.py', 'engine.py',
            'backtest_engine.py', 'execution/simulated_execution.py', 'risk/risk_manager.py',
            'portfolio/portfolio_manager.py', 'data/historical_loader.py', 'data/histdata_provenance.py',
            'config.py', 'live_config.py']
    write_json(OUT/'manifest.json', dict(created_at_utc=datetime.now(timezone.utc),
        revision=subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip(),
        frozen_strategy_revision=REVISION,
        parameters=params, symbols=symbols, periods=PERIODS, workers=1,
        code_hashes={p:file_hash(ROOT/p) for p in code},
        input_hashes={str(p):file_hash(p) for sources in paths.values() for files in sources.values() for p in files},
        sidecar_hashes={str(metadata_path(p)):file_hash(metadata_path(p))
                        for sources in paths.values() for p in sources['histdata']},
        assumptions=dict(initial_balance_per_symbol=10000, risk_pct=config.RISK_PCT,
            spread_pips={s:config.BACKTEST_SPREAD_PIPS[s] for s in symbols}, commission_per_lot=config.COMMISSION_PER_LOT,
            swaps=False, news_filter=False, daily_loss_gate=False, warmup_days=180,
            execution_timeframe='M5', aggregate='Independent symbol runs, equal R weighting; not pooled account returns',
            optimization=False, end_exposure='Left open, excluded from closed-trade metrics')))
    results = []
    all_trades = {}
    control_done = False
    for symbol in symbols:
        for source, files in paths[symbol].items():
            for label, start, end in PERIODS:
                name = f'{source}_{symbol}_{label}'
                print(f'Start {name}', flush=True)
                began = time.monotonic()
                bars = load_and_merge(files, start=start-timedelta(days=180), end=end)
                bars = [b for b in bars if bar_close_time(b) <= end]
                trades, engine, strategy = replay(bars, symbol, params, start, end)
                if not control_done:
                    plain, plain_engine, _ = replay(bars, symbol, params, start, end, observed=False)
                    assert plain == trades, 'Observer altered trade history'
                    assert plain_engine.execution.get_open_positions() == engine.execution.get_open_positions()
                    write_json(OUT/'observer_control.json', dict(source=source, symbol=symbol, period=label,
                        trades=len(trades), all_trade_fields_identical=True, end_exposure_identical=True))
                    control_done = True
                result = dict(source=source, symbol=symbol, period=label, start=start, end=end,
                    metrics=metrics(trades), audit=dict(strategy.audit), examples=strategy.examples,
                    ending_balance=engine.execution.get_account_balance(),
                    max_equity_dd_pct=engine.execution.max_equity_drawdown_pct,
                    open_exposure=engine.execution.get_open_positions(),
                    bars=dict(Counter(b.timeframe for b in bars)), seconds=time.monotonic()-began)
                write_json(OUT/(name+'.json'), result)
                write_json(OUT/(name+'_trades.json'), trades)
                results.append(result)
                all_trades.setdefault((source, label), []).extend(trades)
                write_json(OUT/'results.json', results)
                print(json.dumps(dict(name=name, metrics=result['metrics'], audit=result['audit'],
                                      seconds=result['seconds'])), flush=True)
                del bars, engine, strategy
    aggregate = []
    for (source, period), trades in all_trades.items():
        yearly = {str(y): metrics([t for t in trades if t['close_time'].year == y])
                  for y in sorted({t['close_time'].year for t in trades})}
        aggregate.append(dict(source=source, period=period, metrics=metrics(trades), years=yearly))
    write_json(OUT/'aggregate.json', aggregate)
    write_json(OUT/'price_comparison.json', price_comparison(paths))
    print('Completed 28 fixed-parameter replays plus observer control.', flush=True)


if __name__ == '__main__':
    main()
