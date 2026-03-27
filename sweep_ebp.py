"""
Parameter sweep for EBP (Engulfing Bar Play).

Grid:
  fractal_n        — bars each side for swing high/low detection
  min_retrace_pct  — minimum retracement into engulfing bar range
  max_retrace_pct  — maximum retracement before bias expires
  require_fvg      — whether MSS must have an FVG in the bullish leg

Runs both:
  H4 / H1   (4H bias, 1H entry)
  H4 / M15  (4H bias, 15M entry)

Total: 3 × 3 × 3 × 2 × 2 stacks = 108 combinations
"""

import itertools
import io
import contextlib
import logging
import sys

from backtest_engine import BacktestEngine
from strategies.ebp import EbpStrategy
from data.historical_loader import find_csv, load_and_merge

logging.basicConfig(level=logging.ERROR)
sys.stdout.reconfigure(line_buffering=True)

SYMBOLS         = ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDJPY', 'USDCAD', 'USDCHF']
INITIAL_BALANCE = 10_000.0
RR_RATIO        = 2.0
SPREAD_PIPS     = 2.0

PARAM_GRID = {
    'fractal_n':       [1, 2, 3],
    'min_retrace_pct': [0.1, 0.25, 0.382],
    'max_retrace_pct': [0.5, 0.618, 0.75],
    'require_fvg':     [True, False],
}

TF_STACKS = [
    {'tf_bias': 'H4', 'tf_entry': 'H1',  'label': 'H4/H1'},
    {'tf_bias': 'H4', 'tf_entry': 'M15', 'label': 'H4/M15'},
]

# Pre-load bar data once
needed_tfs = {'H4', 'H1', 'M15'}
csv_paths = []
for symbol in SYMBOLS:
    for tf in needed_tfs:
        paths = find_csv(symbol, tf)
        if paths:
            csv_paths.extend(paths)

if not csv_paths:
    print("No CSV files found.")
    sys.exit(1)

print("Loading bar data...")
all_bars = load_and_merge(csv_paths)
print(f"Loaded {len(all_bars)} bars\n")

keys   = list(PARAM_GRID.keys())
combos = list(itertools.product(*PARAM_GRID.values()))
total  = len(combos) * len(TF_STACKS)
print(f"Running {len(combos)} param combos × {len(TF_STACKS)} stacks = {total} total runs\n")

all_results = {stack['label']: [] for stack in TF_STACKS}
run_count = 0

for stack in TF_STACKS:
    print(f"Stack: {stack['label']}")
    for combo in combos:
        params = dict(zip(keys, combo))

        # Skip invalid combos where min >= max retrace
        if params['min_retrace_pct'] >= params['max_retrace_pct']:
            run_count += 1
            continue

        strategy = EbpStrategy(
            tf_bias=stack['tf_bias'],
            tf_entry=stack['tf_entry'],
            fractal_n=params['fractal_n'],
            min_retrace_pct=params['min_retrace_pct'],
            max_retrace_pct=params['max_retrace_pct'],
            require_fvg=params['require_fvg'],
        )

        engine = BacktestEngine(
            initial_balance=INITIAL_BALANCE,
            rr_ratio=RR_RATIO,
            spread_pips=SPREAD_PIPS,
        )
        engine.add_strategy(strategy, symbols=SYMBOLS)

        with contextlib.redirect_stdout(io.StringIO()):
            for bar in all_bars:
                closed_trades = engine.execution.check_fills(bar)
                for trade in closed_trades:
                    engine.portfolio.record_close(trade['symbol'], trade['pnl'])
                    engine.trade_logger.log_close(trade['ticket'], trade)
                    engine.event_engine.notify_trade_closed(trade)
                engine.event_engine.process_bar(bar)

        trades = engine.execution.get_closed_trades()
        n = len(trades)
        run_count += 1

        if n == 0:
            continue

        wins     = sum(1 for t in trades if t['result'] == 'WIN')
        total_r  = sum(t['r_multiple'] for t in trades)
        win_rate = wins / n * 100
        exp      = total_r / n
        gp       = sum(t['r_multiple'] for t in trades if t['result'] == 'WIN')
        gl       = abs(sum(t['r_multiple'] for t in trades if t['result'] == 'LOSS'))
        pf       = gp / gl if gl > 0 else 0.0

        peak = running = max_dd = 0.0
        for t in trades:
            running += t['r_multiple']
            peak     = max(peak, running)
            max_dd   = max(max_dd, peak - running)

        worst_streak = cur = 0
        for t in trades:
            if t['result'] == 'LOSS':
                cur += 1
                worst_streak = max(worst_streak, cur)
            else:
                cur = 0

        all_results[stack['label']].append({
            **params,
            'trades': n, 'win_rate': win_rate, 'total_r': total_r,
            'pf': pf, 'expectancy': exp, 'max_dd_r': max_dd,
            'worst_streak': worst_streak,
        })

        if run_count % 20 == 0 or run_count == total:
            print(f"  {run_count}/{total}")


# ── Display ────────────────────────────────────────────────────────────────────
W = 140
HDR = (
    f"{'frac':>4} {'minR%':>5} {'maxR%':>5} {'rfvg':>5} | "
    f"{'trades':>6} {'WR%':>6} {'TotalR':>8} {'PF':>6} {'Expect':>7} {'MaxDD':>6} {'Streak':>6}"
)

def row(r):
    fvg = 'Y' if r['require_fvg'] else 'N'
    return (
        f"{r['fractal_n']:>4} {r['min_retrace_pct']:>5.3f} {r['max_retrace_pct']:>5.3f} {fvg:>5} | "
        f"{r['trades']:>6} {r['win_rate']:>5.1f}% {r['total_r']:>+8.1f} "
        f"{r['pf']:>6.2f} {r['expectancy']:>+7.3f} {r['max_dd_r']:>6.1f} {r['worst_streak']:>6}"
    )

def print_table(title, rows, n=20):
    print(f"\n{'='*W}")
    print(title)
    print(f"{'='*W}")
    print(HDR)
    print('-' * W)
    for r in rows[:n]:
        print(row(r))

for stack in TF_STACKS:
    label   = stack['label']
    results = all_results[label]
    if not results:
        print(f"\nNo results for {label}")
        continue

    results.sort(key=lambda r: r['total_r'], reverse=True)
    print_table(f"{label}  —  TOP 20 BY TOTAL R  ({len(results)} valid combos)", results)

    filtered = [r for r in results if r['trades'] >= 50]
    filtered.sort(key=lambda r: r['expectancy'], reverse=True)
    print_table(f"{label}  —  TOP 20 BY EXPECTANCY  (min 50 trades)", filtered)

    filtered.sort(key=lambda r: r['pf'], reverse=True)
    print_table(f"{label}  —  TOP 10 BY PROFIT FACTOR  (min 50 trades)", filtered, n=10)

    filtered2 = [r for r in filtered if r['max_dd_r'] > 0]
    filtered2.sort(key=lambda r: r['expectancy'] / r['max_dd_r'], reverse=True)
    print_table(f"{label}  —  TOP 10 RISK-ADJUSTED (expectancy/maxDD, min 50 trades)", filtered2, n=10)
