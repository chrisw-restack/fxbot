"""
Focused session sweep for Failed2 on forex majors.

This compares common trading-session windows using a small Failed2 FX grid.
Worker count is intentionally 1.
"""

import argparse
import contextlib
import csv
import io
import logging
from datetime import datetime

import config
from backtest_engine import BacktestEngine
from data.historical_loader import find_csv, filter_bars, load_and_merge
from strategies.failed2 import Failed2Strategy


INITIAL_BALANCE = 10_000.0
logging.disable(logging.CRITICAL)

SESSIONS = {
    # UTC buckets. These are fixed UTC approximations; they do not shift for DST.
    'asian': tuple(range(0, 7)),
    'london': tuple(range(7, 12)),
    'london_full': tuple(range(7, 16)),
    'ny_am': tuple(range(12, 17)),
    'ny_am_skip14': (12, 13, 15, 16),
    'ny_pm': tuple(range(17, 21)),
    'ny_full': tuple(range(12, 21)),
    'london_ny_overlap': tuple(range(12, 16)),
    'london_ny': tuple(range(7, 21)),
}


def blocked_from_allowed(allowed):
    return tuple(hour for hour in range(24) if hour not in allowed)


def parse_args():
    parser = argparse.ArgumentParser(description='Sweep Failed2 FX sessions.')
    parser.add_argument(
        '--symbols',
        nargs='+',
        default=['USDCAD', 'USDJPY', 'AUDUSD', 'GBPUSD', 'EURUSD'],
    )
    parser.add_argument('--start-date', default='2020-01-01')
    parser.add_argument('--end-date', default='2026-01-01')
    parser.add_argument('--data-source', choices=['dukascopy', 'histdata'], default='histdata')
    parser.add_argument('--output', default='output/failed2_fx_session_sweep.csv')
    parser.add_argument('--min-trades', type=int, default=30)
    parser.add_argument('--sessions', nargs='+', default=list(SESSIONS))
    parser.add_argument('--mss-values', nargs='+', type=int, default=[3, 4])
    parser.add_argument('--sl-values', nargs='+', type=int, default=[2, 3])
    parser.add_argument('--rr-values', nargs='+', type=float, default=[3.0, 3.5, 4.0])
    parser.add_argument(
        '--bias-options',
        nargs='+',
        choices=['2', '2_failed2', 'all'],
        default=['2', '2_failed2'],
    )
    parser.add_argument(
        '--range-options',
        nargs='+',
        choices=['off', 'on'],
        default=['off', 'on'],
    )
    parser.add_argument(
        '--fixed-usdjpy-candidate',
        action='store_true',
        help='Only sweep sessions using the current fixed USDJPY research parameters.',
    )
    return parser.parse_args()


def load_symbol_bars(symbol, start_date, end_date, data_source):
    paths = []
    for timeframe in ('D1', 'H4', 'H1', 'M5'):
        found = find_csv(symbol, timeframe, data_source=data_source)
        if not found:
            print(f"{symbol}: missing {timeframe}, skipping")
            return []
        paths.extend(found)

    bars = load_and_merge(paths)
    start = datetime.strptime(start_date, '%Y-%m-%d') if start_date else None
    end = datetime.strptime(end_date, '%Y-%m-%d') if end_date else None
    return filter_bars(bars, start=start, end=end)


def make_strategy(session_key, mss_n, sl_n, rr_ratio, bias_kinds, d1_range_filter):
    kwargs = {
        'tf_bias': 'H4',
        'tf_intermediate': 'H1',
        'tf_entry': 'M5',
        'entry_mode': 'market',
        'mss_fractal_n': mss_n,
        'sl_fractal_n': sl_n,
        'rr_ratio': rr_ratio,
        'sl_anchor': 'wick',
        'allowed_bias_kinds': bias_kinds,
        'blocked_hours': blocked_from_allowed(SESSIONS[session_key]),
        'trend_filter': 'd1_ema',
        'pip_sizes': dict(config.PIP_SIZE),
        'use_d1_diagnostics': True,
    }
    if d1_range_filter:
        kwargs.update({
            'd1_range_filter': 'block_top_pct',
            'd1_range_block_pct': 0.8,
        })
    return Failed2Strategy(**kwargs)


def run_one(symbol, bars, combo):
    session_key, mss_n, sl_n, rr_ratio, bias_kinds, d1_range_filter = combo
    strategy = make_strategy(session_key, mss_n, sl_n, rr_ratio, bias_kinds, d1_range_filter)
    engine = BacktestEngine(initial_balance=INITIAL_BALANCE, rr_ratio=rr_ratio)
    engine.add_strategy(strategy, symbols=[symbol])

    with contextlib.redirect_stdout(io.StringIO()):
        for bar in bars:
            closed = engine.execution.check_fills(bar)
            for trade in closed:
                engine.portfolio.record_close(
                    trade['symbol'],
                    trade['pnl'],
                    trade.get('strategy_name', ''),
                )
                engine.trade_logger.log_close(trade['ticket'], trade)
                engine.event_engine.notify_trade_closed(trade)
            engine.event_engine.process_bar(bar)

    trades = engine.execution.get_closed_trades()
    if not trades:
        return None

    wins = sum(1 for trade in trades if trade['result'] == 'WIN')
    total_r = sum(trade['r_multiple'] for trade in trades)
    gross_profit = sum(trade['r_multiple'] for trade in trades if trade['result'] == 'WIN')
    gross_loss = abs(sum(trade['r_multiple'] for trade in trades if trade['result'] == 'LOSS'))

    running = peak = max_dd = 0.0
    loss_streak = worst_loss_streak = 0
    for trade in trades:
        running += trade['r_multiple']
        peak = max(peak, running)
        max_dd = max(max_dd, peak - running)
        if trade['result'] == 'LOSS':
            loss_streak += 1
            worst_loss_streak = max(worst_loss_streak, loss_streak)
        else:
            loss_streak = 0

    return {
        'trades': len(trades),
        'wins': wins,
        'win_rate': wins / len(trades) * 100,
        'total_r': total_r,
        'expectancy': total_r / len(trades),
        'pf': gross_profit / gross_loss if gross_loss else 0.0,
        'max_dd_r': max_dd,
        'worst_loss_streak': worst_loss_streak,
    }


def aggregate(combo, per_symbol):
    valid = {symbol: metrics for symbol, metrics in per_symbol.items() if metrics}
    if not valid:
        return None

    trades = sum(m['trades'] for m in valid.values())
    wins = sum(m['wins'] for m in valid.values())
    total_r = sum(m['total_r'] for m in valid.values())

    session_key, mss_n, sl_n, rr_ratio, bias_kinds, d1_range_filter = combo
    return {
        'session': session_key,
        'allowed_hours': '/'.join(str(h) for h in SESSIONS[session_key]),
        'mss_n': mss_n,
        'sl_n': sl_n,
        'rr_ratio': rr_ratio,
        'bias_kinds': '+'.join(bias_kinds),
        'd1_range_filter': d1_range_filter,
        'symbols_traded': len(valid),
        'symbols_positive': sum(1 for m in valid.values() if m['total_r'] > 0),
        'trades': trades,
        'win_rate': wins / trades * 100 if trades else 0.0,
        'total_r': total_r,
        'expectancy': total_r / trades if trades else 0.0,
        'avg_pf': sum(m['pf'] for m in valid.values()) / len(valid),
        'max_dd_r': max(m['max_dd_r'] for m in valid.values()),
        'worst_loss_streak': max(m['worst_loss_streak'] for m in valid.values()),
        'per_symbol': valid,
    }


def print_rows(title, rows, limit=20):
    print(f"\n{'=' * 132}")
    print(title)
    print('=' * 132)
    print(
        f"{'session':<18} {'hours':<24} {'mss':>3} {'sl':>3} {'RR':>4} "
        f"{'bias':<10} {'rng':>3} | {'trades':>6} {'WR%':>6} {'TotalR':>8} "
        f"{'Exp':>7} {'PFavg':>6} {'MaxDD':>7} {'pos':>3} {'streak':>6}"
    )
    print('-' * 132)
    for row in rows[:limit]:
        print(
            f"{row['session']:<18} {row['allowed_hours']:<24} "
            f"{row['mss_n']:>3} {row['sl_n']:>3} {row['rr_ratio']:>4.1f} "
            f"{row['bias_kinds']:<10} {str(row['d1_range_filter'])[0]:>3} | "
            f"{row['trades']:>6} {row['win_rate']:>5.1f}% {row['total_r']:>+8.1f} "
            f"{row['expectancy']:>+7.3f} {row['avg_pf']:>6.2f} "
            f"{row['max_dd_r']:>7.1f} {row['symbols_positive']:>1}/{row['symbols_traded']:<1} "
            f"{row['worst_loss_streak']:>6}"
        )


def write_csv(path, rows, symbols):
    fieldnames = [
        'session', 'allowed_hours', 'mss_n', 'sl_n', 'rr_ratio', 'bias_kinds',
        'd1_range_filter', 'symbols_traded', 'symbols_positive', 'trades',
        'win_rate', 'total_r', 'expectancy', 'avg_pf', 'max_dd_r',
        'worst_loss_streak',
    ]
    for symbol in symbols:
        fieldnames.extend([
            f'{symbol}_trades', f'{symbol}_total_r', f'{symbol}_expectancy',
            f'{symbol}_pf', f'{symbol}_max_dd_r',
        ])

    with open(path, 'w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            csv_row = {key: row[key] for key in fieldnames if key in row}
            for symbol in symbols:
                metrics = row['per_symbol'].get(symbol)
                csv_row[f'{symbol}_trades'] = metrics['trades'] if metrics else 0
                csv_row[f'{symbol}_total_r'] = round(metrics['total_r'], 2) if metrics else 0.0
                csv_row[f'{symbol}_expectancy'] = round(metrics['expectancy'], 4) if metrics else 0.0
                csv_row[f'{symbol}_pf'] = round(metrics['pf'], 3) if metrics else 0.0
                csv_row[f'{symbol}_max_dd_r'] = round(metrics['max_dd_r'], 2) if metrics else 0.0
            writer.writerow(csv_row)


def main():
    args = parse_args()
    symbols = [symbol.upper() for symbol in args.symbols]
    sessions = [session for session in args.sessions if session in SESSIONS]
    if not sessions:
        raise SystemExit('No valid sessions selected.')

    print("Loading bar data...")
    bars_by_symbol = {}
    for symbol in symbols:
        bars = load_symbol_bars(symbol, args.start_date, args.end_date, args.data_source)
        if bars:
            bars_by_symbol[symbol] = bars
            print(f"{symbol}: {len(bars):,} bars")

    active_symbols = list(bars_by_symbol)
    if not active_symbols:
        raise SystemExit('No symbols loaded.')

    combos = []
    bias_map = {
        '2': ('2',),
        '2_failed2': ('2', 'failed2'),
        'all': ('2', '3', 'failed2'),
    }
    range_map = {
        'off': False,
        'on': True,
    }

    if args.fixed_usdjpy_candidate:
        for session_key in sessions:
            combos.append((session_key, 3, 3, 4.0, ('2', 'failed2'), True))
    else:
        for session_key in sessions:
            for mss_n in args.mss_values:
                for sl_n in args.sl_values:
                    for rr_ratio in args.rr_values:
                        for bias_option in args.bias_options:
                            for range_option in args.range_options:
                                bias_kinds = bias_map[bias_option]
                                d1_range_filter = range_map[range_option]
                                combos.append((session_key, mss_n, sl_n, rr_ratio, bias_kinds, d1_range_filter))

    print(
        f"Running {len(combos)} combos on {', '.join(active_symbols)} "
        f"from {args.start_date} to {args.end_date} using {args.data_source}..."
    )

    rows = []
    for index, combo in enumerate(combos, start=1):
        per_symbol = {
            symbol: run_one(symbol, bars_by_symbol[symbol], combo)
            for symbol in active_symbols
        }
        row = aggregate(combo, per_symbol)
        if row and row['trades'] >= args.min_trades:
            rows.append(row)
        if index % 25 == 0 or index == len(combos):
            print(f"Completed {index}/{len(combos)} combos")

    rows.sort(key=lambda row: (row['expectancy'], row['total_r']), reverse=True)
    write_csv(args.output, rows, active_symbols)

    print_rows("Top by expectancy", rows)
    print_rows("Top by total R", sorted(rows, key=lambda row: row['total_r'], reverse=True))
    print_rows(
        "Lowest drawdown with positive expectancy",
        sorted(
            [row for row in rows if row['expectancy'] > 0 and row['symbols_positive'] > 0],
            key=lambda row: (row['max_dd_r'], -row['expectancy']),
        ),
    )
    print(f"\nWrote {len(rows)} rows to {args.output}")


if __name__ == '__main__':
    main()
