"""
Diagnostic breakdown for Failed2 trades.

Runs a single Failed2 configuration and attaches setup context to each closed
trade: HTF bias type, direction, hour, symbol, H4/D1 EMA alignment, and D1
range percentile.
"""

import argparse
import contextlib
import io
from collections import defaultdict
from datetime import datetime

import config
from data.historical_loader import find_csv, filter_bars, load_and_merge
from execution.simulated_execution import SimulatedExecution
from portfolio.portfolio_manager import PortfolioManager
from risk.risk_manager import RiskManager
from strategies.failed2 import Failed2Strategy


INITIAL_BALANCE = 10_000.0


def parse_args():
    parser = argparse.ArgumentParser(description='Analyze Failed2 diagnostics.')
    parser.add_argument('--symbols', nargs='+', default=['USA100', 'EURUSD', 'GBPUSD'])
    parser.add_argument('--start-date', default='2022-01-01')
    parser.add_argument('--end-date', default=None)
    parser.add_argument('--data-source', choices=['dukascopy', 'histdata'], default='dukascopy')
    parser.add_argument(
        '--candidate',
        choices=['best', 'filtered', 'nasdaq_candidate'],
        default='best',
        help='Failed2 parameter set to diagnose.',
    )
    return parser.parse_args()


def load_bars(symbols, timeframes, start_date, end_date, data_source):
    paths = []
    for symbol in symbols:
        for tf in timeframes:
            found = find_csv(symbol, tf, data_source=data_source)
            if not found:
                print(f"WARNING: missing {symbol} {tf}")
            paths.extend(found)
    bars = load_and_merge(paths)
    start = datetime.strptime(start_date, '%Y-%m-%d') if start_date else None
    end = datetime.strptime(end_date, '%Y-%m-%d') if end_date else None
    return filter_bars(bars, start=start, end=end)


def make_strategy(candidate):
    params = {
        'tf_bias': 'H4',
        'tf_intermediate': 'H1',
        'tf_entry': 'M5',
        'entry_mode': 'market',
        'mss_fractal_n': 3,
        'sl_fractal_n': 2,
        'rr_ratio': 3.5,
        'blocked_hours': (*range(0, 12), *range(17, 24)),
        'pip_sizes': dict(config.PIP_SIZE),
        'use_d1_diagnostics': True,
    }
    if candidate == 'filtered':
        params.update({
            'trend_filter': 'd1_ema',
            'd1_range_filter': 'block_top_pct',
            'd1_range_block_pct': 0.8,
        })
    elif candidate == 'nasdaq_candidate':
        params.update({
            'mss_fractal_n': 4,
            'rr_ratio': 4.0,
            'blocked_hours': (*range(0, 13), *range(18, 24)),
            'trend_filter': 'd1_ema',
            'd1_range_filter': 'block_top_pct',
            'd1_range_block_pct': 0.7,
        })
    return Failed2Strategy(**params)


def run_diagnostic_backtest(bars, symbols, candidate):
    strategy = make_strategy(candidate)
    execution = SimulatedExecution(
        INITIAL_BALANCE,
        spread_pips=config.BACKTEST_SPREAD_PIPS,
        rr_ratio=strategy.rr_ratio,
    )
    portfolio = PortfolioManager(max_open_trades=99, max_daily_loss_pct=None)
    risk = RiskManager(
        account_balance_fn=execution.get_account_balance,
        rr_ratio=strategy.rr_ratio,
    )

    ticket_context = {}
    closed_with_context = []

    for bar in bars:
        closed = execution.check_fills(bar)
        for trade in closed:
            portfolio.record_close(trade['symbol'], trade['pnl'], trade.get('strategy_name', ''))
            ctx = ticket_context.pop(trade['ticket'], {})
            trade = {**trade, **ctx}
            closed_with_context.append(trade)
            if trade.get('result') == 'LOSS':
                strategy.notify_loss(trade['symbol'])
            elif trade.get('result') == 'WIN':
                strategy.notify_win(trade['symbol'])

        portfolio.set_current_date(bar.timestamp.date())
        if bar.symbol not in symbols or bar.timeframe not in strategy.TIMEFRAMES:
            continue

        signal = strategy.generate_signal(bar)
        if signal is None:
            continue

        if signal.direction == 'CANCEL':
            for pos in execution.get_open_positions():
                if (
                    pos['symbol'] == signal.symbol
                    and pos['strategy_name'] == signal.strategy_name
                    and pos.get('open_time') is None
                ):
                    execution.close_order(pos['ticket'])
                    portfolio.record_close(signal.symbol, 0.0, signal.strategy_name)
                    ticket_context.pop(pos['ticket'], None)
            continue

        signal.entry_timeframe = bar.timeframe
        enriched = risk.process(signal)
        if enriched is None or not portfolio.approve(enriched):
            continue

        ticket = execution.place_order(
            symbol=enriched.symbol,
            direction=enriched.direction,
            order_type=enriched.order_type,
            entry_price=enriched.entry_price,
            lot_size=enriched.lot_size,
            sl=enriched.stop_loss,
            tp=enriched.take_profit,
            strategy_name=enriched.strategy_name,
            entry_timeframe=enriched.entry_timeframe,
            tp_locked=enriched.tp_locked,
            signal_time=enriched.timestamp,
        )
        if ticket:
            portfolio.record_open(enriched, ticket)
            ctx = strategy.get_last_signal_context(enriched.symbol) or {}
            ticket_context[ticket] = ctx

    return closed_with_context


def metrics(trades):
    n = len(trades)
    if n == 0:
        return None
    wins = sum(1 for t in trades if t['result'] == 'WIN')
    total_r = sum(t['r_multiple'] for t in trades)
    gp = sum(t['r_multiple'] for t in trades if t['result'] == 'WIN')
    gl = abs(sum(t['r_multiple'] for t in trades if t['result'] == 'LOSS'))
    peak = running = max_dd = 0.0
    for t in trades:
        running += t['r_multiple']
        peak = max(peak, running)
        max_dd = max(max_dd, peak - running)
    return {
        'trades': n,
        'win_rate': wins / n * 100,
        'total_r': total_r,
        'expectancy': total_r / n,
        'pf': gp / gl if gl > 0 else 0.0,
        'max_dd_r': max_dd,
    }


def print_group(title, trades, key_fn, min_trades=20):
    groups = defaultdict(list)
    for trade in trades:
        groups[key_fn(trade)].append(trade)
    rows = []
    for key, group in groups.items():
        m = metrics(group)
        if m and m['trades'] >= min_trades:
            rows.append((key, m))
    rows.sort(key=lambda item: item[1]['total_r'], reverse=True)

    print(f"\n{'=' * 100}")
    print(title)
    print('=' * 100)
    print(f"{'bucket':<24} {'trades':>7} {'WR%':>7} {'TotalR':>9} {'Exp':>8} {'PF':>6} {'MaxDD':>8}")
    print('-' * 100)
    for key, m in rows:
        print(
            f"{str(key):<24} {m['trades']:>7} {m['win_rate']:>6.1f}% "
            f"{m['total_r']:>+9.1f} {m['expectancy']:>+8.3f} "
            f"{m['pf']:>6.2f} {m['max_dd_r']:>8.1f}"
        )


def range_bucket(trade):
    pct = trade.get('d1_range_percentile')
    if pct is None:
        return 'unknown'
    if pct >= 0.8:
        return 'top_20pct'
    if pct >= 0.6:
        return '60_80pct'
    if pct >= 0.4:
        return '40_60pct'
    return 'bottom_40pct'


def main():
    args = parse_args()
    symbols = [s.upper() for s in args.symbols]
    print("Loading bars...")
    bars = load_bars(symbols, ['D1', 'H4', 'H1', 'M5'], args.start_date, args.end_date, args.data_source)
    print(f"Loaded {len(bars):,} bars")
    print(f"Candidate: {args.candidate} | Data source: {args.data_source}")

    print("Running diagnostic backtest...")
    with contextlib.redirect_stdout(io.StringIO()):
        trades = run_diagnostic_backtest(bars, symbols, args.candidate)
    print(f"Closed trades: {len(trades):,}")

    overall = metrics(trades)
    print(
        f"Overall: {overall['trades']} trades | {overall['win_rate']:.1f}% WR | "
        f"{overall['total_r']:+.1f}R | {overall['expectancy']:+.3f}R exp | "
        f"PF {overall['pf']:.2f} | DD {overall['max_dd_r']:.1f}R"
    )

    print_group("By Symbol", trades, lambda t: t.get('symbol'))
    print_group("By Direction", trades, lambda t: t.get('direction'))
    print_group("By HTF Bias Type", trades, lambda t: t.get('htf_bias_type') or 'unknown')
    print_group("By Entry Hour UTC", trades, lambda t: t.get('session_hour'), min_trades=10)
    print_group("By H4 EMA Alignment", trades, lambda t: t.get('h4_trend_alignment') or 'unknown')
    print_group("By D1 EMA Alignment", trades, lambda t: t.get('d1_trend_alignment') or 'unknown')
    print_group("By D1 Range Percentile", trades, range_bucket)

    print_group(
        "By Symbol + HTF Bias Type",
        trades,
        lambda t: f"{t.get('symbol')}|{t.get('htf_bias_type') or 'unknown'}",
    )
    print_group(
        "By Symbol + H4 Trend",
        trades,
        lambda t: f"{t.get('symbol')}|{t.get('h4_trend_alignment') or 'unknown'}",
    )


if __name__ == '__main__':
    main()
