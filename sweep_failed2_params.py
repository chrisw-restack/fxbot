"""
Focused parameter sweep for Failed2.

Default symbols: USA100, EURUSD, GBPUSD.
Worker count intentionally stays at 1; higher parallelism has hung this machine.
"""

import argparse
import contextlib
import csv
import io
import itertools
import logging
import sys
from datetime import datetime

import config
from backtest_engine import BacktestEngine
from data.historical_loader import find_csv, filter_bars, load_and_merge
from strategies.failed2 import Failed2Strategy

logging.basicConfig(level=logging.ERROR)
sys.stdout.reconfigure(line_buffering=True)

INITIAL_BALANCE = 10_000.0

SESSIONS = {
    'all': (),
    'london': (*range(0, 7), *range(13, 24)),     # allow 07-13 UTC
    'ny': (*range(0, 13), *range(18, 24)),        # allow 13-18 UTC
    'ln_us': (*range(0, 12), *range(17, 24)),     # allow 12-17 UTC
    'eu_us': (*range(0, 7), *range(18, 24)),      # allow 07-18 UTC
}

FRACTAL_PAIRS = [
    (1, 1),
    (1, 2),
    (2, 1),
    (2, 2),
    (2, 3),
    (3, 2),
]


def parse_args():
    parser = argparse.ArgumentParser(description='Sweep Failed2 parameters.')
    parser.add_argument('--symbols', nargs='+', default=['USA100', 'EURUSD', 'GBPUSD'])
    parser.add_argument('--start-date', default='2022-01-01')
    parser.add_argument('--end-date', default=None)
    parser.add_argument('--output', default='output/failed2_param_sweep.csv')
    parser.add_argument('--min-trades', type=int, default=50)
    parser.add_argument('--entry-modes', nargs='+', default=['market', 'fvg'])
    parser.add_argument('--rr', nargs='+', type=float, default=[1.5, 2.0, 2.5])
    parser.add_argument('--sessions', nargs='+', default=['all', 'ln_us', 'ny'])
    parser.add_argument('--sl-anchors', nargs='+', default=['wick', 'body'])
    parser.add_argument('--include-extreme-invalidation', action='store_true')
    return parser.parse_args()


def load_bars(symbols, start_date, end_date):
    bars_by_symbol = {}
    start = datetime.strptime(start_date, '%Y-%m-%d') if start_date else None
    end = datetime.strptime(end_date, '%Y-%m-%d') if end_date else None

    for symbol in symbols:
        paths = []
        for tf in ('H4', 'H1', 'M5'):
            tf_paths = find_csv(symbol, tf)
            if not tf_paths:
                print(f"{symbol}: missing {tf}, skipping")
                paths = []
                break
            paths.extend(tf_paths)

        if not paths:
            continue

        bars = load_and_merge(paths)
        bars = filter_bars(bars, start=start, end=end)
        bars_by_symbol[symbol] = bars
        print(f"{symbol}: {len(bars):,} bars")

    return bars_by_symbol


def run_symbol(combo, symbol, bars):
    entry_mode, mss_n, sl_n, sl_anchor, rr_ratio, session_key, invalidate = combo

    strategy = Failed2Strategy(
        tf_bias='H4',
        tf_intermediate='H1',
        tf_entry='M5',
        entry_mode=entry_mode,
        mss_fractal_n=mss_n,
        sl_fractal_n=sl_n,
        rr_ratio=rr_ratio,
        fvg_entry_pct=0.5,
        blocked_hours=SESSIONS[session_key],
        sl_anchor=sl_anchor,
        invalidate_on_bias_extreme=invalidate,
        pip_sizes=dict(config.PIP_SIZE),
    )
    engine = BacktestEngine(initial_balance=INITIAL_BALANCE, rr_ratio=rr_ratio)
    engine.add_strategy(strategy, symbols=[symbol])

    with contextlib.redirect_stdout(io.StringIO()):
        for bar in bars:
            closed = engine.execution.check_fills(bar)
            for trade in closed:
                engine.portfolio.record_close(
                    trade['symbol'], trade['pnl'], trade.get('strategy_name', ''))
                engine.trade_logger.log_close(trade['ticket'], trade)
                engine.event_engine.notify_trade_closed(trade)
            engine.event_engine.process_bar(bar)

    trades = engine.execution.get_closed_trades()
    n = len(trades)
    if n == 0:
        return None

    wins = sum(1 for t in trades if t['result'] == 'WIN')
    total_r = sum(t['r_multiple'] for t in trades)
    gp = sum(t['r_multiple'] for t in trades if t['result'] == 'WIN')
    gl = abs(sum(t['r_multiple'] for t in trades if t['result'] == 'LOSS'))
    pf = gp / gl if gl > 0 else 0.0

    peak = max_dd = running = 0.0
    worst_streak = cur_streak = 0
    for t in trades:
        running += t['r_multiple']
        peak = max(peak, running)
        max_dd = max(max_dd, peak - running)
        if t['result'] == 'LOSS':
            cur_streak += 1
            worst_streak = max(worst_streak, cur_streak)
        else:
            cur_streak = 0

    return {
        'trades': n,
        'wins': wins,
        'win_rate': wins / n * 100,
        'total_r': total_r,
        'pf': pf,
        'expectancy': total_r / n,
        'max_dd_r': max_dd,
        'worst_streak': worst_streak,
    }


def aggregate(combo, per_symbol):
    valid = [d for d in per_symbol.values() if d]
    if not valid:
        return None

    total_trades = sum(d['trades'] for d in valid)
    total_wins = sum(d['wins'] for d in valid)
    total_r = sum(d['total_r'] for d in valid)
    gp_proxy = sum(d['pf'] for d in valid) / len(valid)

    return {
        'combo': combo,
        'entry_mode': combo[0],
        'mss_n': combo[1],
        'sl_n': combo[2],
        'sl_anchor': combo[3],
        'rr_ratio': combo[4],
        'session': combo[5],
        'invalidate': combo[6],
        'per_symbol': per_symbol,
        'symbols_positive': sum(1 for d in per_symbol.values() if d and d['total_r'] > 0),
        'symbols_traded': len(valid),
        'trades': total_trades,
        'win_rate': total_wins / total_trades * 100 if total_trades else 0.0,
        'total_r': total_r,
        'expectancy': total_r / total_trades if total_trades else 0.0,
        'avg_pf': gp_proxy,
        'max_dd_r': max(d['max_dd_r'] for d in valid),
        'worst_streak': max(d['worst_streak'] for d in valid),
    }


def print_table(title, rows, symbols, n=25):
    header = (
        f"{'entry':>6} {'mss':>3} {'sl':>3} {'anchor':>6} {'RR':>4} {'session':>7} {'inv':>3} | "
        f"{'trades':>6} {'WR%':>6} {'TotalR':>8} {'Exp':>7} {'PFavg':>6} {'MaxDD':>7} {'pos':>3}"
    )
    print(f"\n{'=' * 140}")
    print(title)
    print('=' * 140)
    print(header)
    print('-' * 140)
    for r in rows[:n]:
        print(
            f"{r['entry_mode']:>6} {r['mss_n']:>3} {r['sl_n']:>3} {r['sl_anchor']:>6} "
            f"{r['rr_ratio']:>4.1f} {r['session']:>7} {str(r['invalidate'])[0]:>3} | "
            f"{r['trades']:>6} {r['win_rate']:>5.1f}% {r['total_r']:>+8.1f} "
            f"{r['expectancy']:>+7.3f} {r['avg_pf']:>6.2f} {r['max_dd_r']:>7.1f} "
            f"{r['symbols_positive']:>1}/{len(symbols):<1}"
        )


def write_csv(path, rows, symbols):
    fieldnames = [
        'entry_mode', 'mss_n', 'sl_n', 'sl_anchor', 'rr_ratio', 'session',
        'invalidate', 'symbols_positive', 'symbols_traded', 'trades',
        'win_rate', 'total_r', 'expectancy', 'avg_pf', 'max_dd_r',
        'worst_streak',
    ]
    for symbol in symbols:
        fieldnames.extend([
            f'{symbol}_trades', f'{symbol}_total_r', f'{symbol}_expectancy',
            f'{symbol}_pf', f'{symbol}_max_dd_r',
        ])

    with open(path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            row = {k: r[k] for k in fieldnames if k in r}
            for symbol in symbols:
                d = r['per_symbol'].get(symbol)
                row[f'{symbol}_trades'] = d['trades'] if d else 0
                row[f'{symbol}_total_r'] = round(d['total_r'], 2) if d else 0.0
                row[f'{symbol}_expectancy'] = round(d['expectancy'], 4) if d else 0.0
                row[f'{symbol}_pf'] = round(d['pf'], 3) if d else 0.0
                row[f'{symbol}_max_dd_r'] = round(d['max_dd_r'], 2) if d else 0.0
            writer.writerow(row)


def main():
    args = parse_args()
    symbols = [s.upper() for s in args.symbols]
    sessions = [s for s in args.sessions if s in SESSIONS]
    invalidation_options = [False, True] if args.include_extreme_invalidation else [False]

    print("Loading bar data...")
    bars_by_symbol = load_bars(symbols, args.start_date, args.end_date)
    active_symbols = [s for s in symbols if s in bars_by_symbol]
    if not active_symbols:
        print("No usable symbol data found.")
        return 1

    combos = [
        (entry_mode, mss_n, sl_n, sl_anchor, rr_ratio, session_key, invalidate)
        for entry_mode, (mss_n, sl_n), sl_anchor, rr_ratio, session_key, invalidate
        in itertools.product(
            args.entry_modes,
            FRACTAL_PAIRS,
            args.sl_anchors,
            args.rr,
            sessions,
            invalidation_options,
        )
    ]

    total_tasks = len(combos) * len(active_symbols)
    print(
        f"\nRunning {len(combos)} combos × {len(active_symbols)} symbols "
        f"= {total_tasks} single-symbol runs"
    )
    print(f"Date range: {args.start_date or 'start'} to {args.end_date or 'end'}")
    print("Workers: 1\n")

    results = []
    for i, combo in enumerate(combos, 1):
        per_symbol = {}
        for symbol in active_symbols:
            per_symbol[symbol] = run_symbol(combo, symbol, bars_by_symbol[symbol])

        agg = aggregate(combo, per_symbol)
        if agg is not None and agg['trades'] >= args.min_trades:
            results.append(agg)

        if i % 10 == 0 or i == len(combos):
            print(f"  {i}/{len(combos)} combos done ({i / len(combos) * 100:.1f}%)")

    results.sort(key=lambda r: (r['symbols_positive'], r['total_r']), reverse=True)
    write_csv(args.output, results, active_symbols)

    print(f"\nDone. {len(results)} combos met min_trades={args.min_trades}.")
    print(f"CSV saved to {args.output}")

    ranked = sorted(results, key=lambda r: r['total_r'], reverse=True)
    print_table("TOP BY TOTAL R", ranked, active_symbols)

    consistent = sorted(
        results,
        key=lambda r: (r['symbols_positive'], r['expectancy'], r['total_r']),
        reverse=True,
    )
    print_table("TOP BY CROSS-SYMBOL CONSISTENCY THEN EXPECTANCY", consistent, active_symbols)

    low_dd = sorted(
        results,
        key=lambda r: (r['total_r'] / r['max_dd_r'] if r['max_dd_r'] > 0 else 0, r['total_r']),
        reverse=True,
    )
    print_table("TOP BY TOTALR / MAXDD", low_dd, active_symbols)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
