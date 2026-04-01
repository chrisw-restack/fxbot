"""
EBP Parameter Sweep — exhaustive search across TF stacks, zone params, SL modes, session filter.

Grid:
  tf_stack        — (bias_tf, entry_tf): D1/H4, H4/H1, H1/M15
  fractal_n       — swing confirmation bars each side: 1, 2, 3
  min_retrace_pct — zone entry level (% into engulf range): 0.1, 0.25, 0.382
  max_retrace_pct — zone exit level (% into engulf range): 0.5, 0.618, 0.75
  require_fvg     — require fair value gap in leg: True, False
  sl_mode         — stop-loss reference: structural, mss_bar, symmetric
  session         — blocked hours: none, 09:00-19:00 UTC only

Symbols: 7 FX pairs + XAUUSD (EBP uses % retracement, no pip-based filters — XAUUSD is safe)
Total valid combos: 3 stacks × 3 × 9 (zone) × 2 × 3 × 2 = 972
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

SYMBOLS = ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDJPY', 'USDCAD', 'USDCHF', 'XAUUSD']
INITIAL_BALANCE = 10_000.0
RR_RATIO = 2.0

SESSION_FILTER = (*range(20, 24), *range(0, 9))  # block 20:00-08:59 UTC → allow 09:00-19:59

# ── TF stacks — (bias, entry) ────────────────────────────────────────────────
TF_STACKS = [
    ('D1', 'H4'),
    ('H4', 'H1'),
    ('H1', 'M15'),
]

# ── Per-stack parameter grid (same for all stacks) ───────────────────────────
PARAM_GRID = {
    'fractal_n':       [1, 2, 3],
    'min_retrace_pct': [0.1, 0.25, 0.382],
    'max_retrace_pct': [0.5, 0.618, 0.75],
    'require_fvg':     [True, False],
    'sl_mode':         ['structural', 'mss_bar', 'symmetric'],
    'session':         ['none', 'filtered'],  # session label (not passed to strategy directly)
}

# ── Pre-load bars for each TF stack ─────────────────────────────────────────
print("Loading bar data for all stacks...")
stack_bars: dict[tuple, list] = {}
for tf_bias, tf_entry in TF_STACKS:
    csv_paths = []
    for symbol in SYMBOLS:
        for tf in [tf_bias, tf_entry]:
            csv_paths.extend(find_csv(symbol, tf))
    if not csv_paths:
        print(f"  WARNING: no CSVs found for {tf_bias}/{tf_entry} stack — skipping")
        continue
    bars = load_and_merge(csv_paths)
    stack_bars[(tf_bias, tf_entry)] = bars
    print(f"  {tf_bias}/{tf_entry}: {len(bars):,} bars")

if not stack_bars:
    print("No data loaded. Exiting.")
    sys.exit(1)

# ── Build combo list ─────────────────────────────────────────────────────────
keys = list(PARAM_GRID.keys())
base_combos = list(itertools.product(*PARAM_GRID.values()))
# Filter invalid zone combos (min >= max is technically valid — they just widen/narrow the zone)
# All our values have min < max so no filtering needed.

all_combos = [
    (stack, dict(zip(keys, combo)))
    for stack in TF_STACKS
    if stack in stack_bars
    for combo in base_combos
]
total = len(all_combos)
print(f"\nRunning {total} combinations across {len(stack_bars)} stacks...\n")

results = []

for i, (stack, params) in enumerate(all_combos):
    tf_bias, tf_entry = stack
    blocked = SESSION_FILTER if params['session'] == 'filtered' else ()

    strategy = EbpStrategy(
        tf_bias=tf_bias,
        tf_entry=tf_entry,
        fractal_n=params['fractal_n'],
        min_retrace_pct=params['min_retrace_pct'],
        max_retrace_pct=params['max_retrace_pct'],
        require_fvg=params['require_fvg'],
        sl_mode=params['sl_mode'],
        blocked_hours=blocked,
    )

    engine = BacktestEngine(initial_balance=INITIAL_BALANCE, rr_ratio=RR_RATIO)
    engine.add_strategy(strategy, symbols=SYMBOLS)

    bars = stack_bars[stack]
    with contextlib.redirect_stdout(io.StringIO()):
        for bar in bars:
            closed_trades = engine.execution.check_fills(bar)
            for trade in closed_trades:
                engine.portfolio.record_close(trade['symbol'], trade['pnl'], trade.get('strategy_name', ''))
                engine.trade_logger.log_close(trade['ticket'], trade)
                engine.event_engine.notify_trade_closed(trade)
            engine.event_engine.process_bar(bar)

    trades = engine.execution.get_closed_trades()
    n = len(trades)
    if n == 0:
        continue

    wins = sum(1 for t in trades if t['result'] == 'WIN')
    total_r = sum(t['r_multiple'] for t in trades)
    win_rate = wins / n * 100
    expectancy = total_r / n
    gp = sum(t['r_multiple'] for t in trades if t['result'] == 'WIN')
    gl = abs(sum(t['r_multiple'] for t in trades if t['result'] == 'LOSS'))
    pf = gp / gl if gl > 0 else 0.0

    peak = running = max_dd = 0.0
    for t in trades:
        running += t['r_multiple']
        peak = max(peak, running)
        max_dd = max(max_dd, peak - running)

    worst_streak = cur_streak = 0
    for t in trades:
        if t['result'] == 'LOSS':
            cur_streak += 1
            worst_streak = max(worst_streak, cur_streak)
        else:
            cur_streak = 0

    results.append({
        'stack':    f"{tf_bias}/{tf_entry}",
        'fractal_n':       params['fractal_n'],
        'min_retrace_pct': params['min_retrace_pct'],
        'max_retrace_pct': params['max_retrace_pct'],
        'require_fvg':     params['require_fvg'],
        'sl_mode':         params['sl_mode'],
        'session':         params['session'],
        'trades':      n,
        'win_rate':    win_rate,
        'total_r':     total_r,
        'pf':          pf,
        'expectancy':  expectancy,
        'max_dd_r':    max_dd,
        'worst_streak': worst_streak,
    })

    if (i + 1) % 50 == 0 or i + 1 == total:
        best_so_far = max((r['expectancy'] for r in results), default=0)
        print(f"  {i+1}/{total}  best expectancy so far: {best_so_far:+.3f}R")


# ── Display helpers ──────────────────────────────────────────────────────────
W = 185
HEADER = (
    f"{'stack':>8} {'frac':>4} {'min_r':>5} {'max_r':>5} {'fvg':>3} {'sl':>10} {'sess':>8} | "
    f"{'trades':>6} {'WR%':>6} {'TotalR':>8} {'PF':>6} {'Expect':>7} {'MaxDD':>6} {'Streak':>6}"
)

def row(r):
    return (
        f"{r['stack']:>8} {r['fractal_n']:>4} {r['min_retrace_pct']:>5.3f} {r['max_retrace_pct']:>5.3f} "
        f"{'Y' if r['require_fvg'] else 'N':>3} {r['sl_mode']:>10} {r['session']:>8} | "
        f"{r['trades']:>6} {r['win_rate']:>5.1f}% {r['total_r']:>+8.1f} "
        f"{r['pf']:>6.2f} {r['expectancy']:>+7.3f} {r['max_dd_r']:>6.1f} {r['worst_streak']:>6}"
    )

def print_table(title, rows, n=30):
    print(f"\n{'='*W}")
    print(title)
    print(f"{'='*W}")
    print(HEADER)
    print('-' * W)
    for r in rows[:n]:
        print(row(r))

# ── Overall top tables ───────────────────────────────────────────────────────
results.sort(key=lambda r: r['total_r'], reverse=True)
print_table(f"TOP 30 BY TOTAL R  (all combos, {len(results)} valid)", results)

filtered = [r for r in results if r['trades'] >= 30]
filtered.sort(key=lambda r: r['expectancy'], reverse=True)
print_table("TOP 30 BY EXPECTANCY  (min 30 trades)", filtered)

filtered.sort(key=lambda r: r['pf'], reverse=True)
print_table("TOP 20 BY PROFIT FACTOR  (min 30 trades)", filtered, n=20)

# ── Per-stack top tables ─────────────────────────────────────────────────────
for stack_label in ['D1/H4', 'H4/H1', 'H1/M15']:
    stack_results = [r for r in results if r['stack'] == stack_label and r['trades'] >= 20]
    if not stack_results:
        continue
    stack_results.sort(key=lambda r: r['expectancy'], reverse=True)
    print_table(f"TOP 20 — {stack_label}  (min 20 trades, by expectancy)", stack_results, n=20)

# ── Session filter impact ────────────────────────────────────────────────────
print(f"\n{'='*W}")
print("SESSION FILTER IMPACT (avg expectancy: filtered vs no filter, min 20 trades)")
print(f"{'='*W}")
for stack_label in ['D1/H4', 'H4/H1', 'H1/M15']:
    no_filt = [r for r in results if r['stack'] == stack_label and r['session'] == 'none' and r['trades'] >= 20]
    filt    = [r for r in results if r['stack'] == stack_label and r['session'] == 'filtered' and r['trades'] >= 20]
    if no_filt and filt:
        avg_no = sum(r['expectancy'] for r in no_filt) / len(no_filt)
        avg_fi = sum(r['expectancy'] for r in filt) / len(filt)
        print(f"  {stack_label}:  no filter → {avg_no:+.3f}R avg   |   filtered → {avg_fi:+.3f}R avg   (delta {avg_fi-avg_no:+.3f}R)")

# ── SL mode impact ───────────────────────────────────────────────────────────
print(f"\n{'='*W}")
print("SL MODE IMPACT (avg expectancy across all stacks, min 20 trades)")
print(f"{'='*W}")
for mode in ['structural', 'mss_bar', 'symmetric']:
    mode_results = [r for r in results if r['sl_mode'] == mode and r['trades'] >= 20]
    if mode_results:
        avg = sum(r['expectancy'] for r in mode_results) / len(mode_results)
        best = max(r['expectancy'] for r in mode_results)
        print(f"  {mode:>12}: avg {avg:+.3f}R   best {best:+.3f}R   ({len(mode_results)} combos)")

# ── Trade frequency summary ──────────────────────────────────────────────────
print(f"\n{'='*W}")
print("TRADE FREQUENCY BY STACK (all combos, avg trades)")
print(f"{'='*W}")
for stack_label in ['D1/H4', 'H4/H1', 'H1/M15']:
    stack_r = [r for r in results if r['stack'] == stack_label]
    if stack_r:
        avg_trades = sum(r['trades'] for r in stack_r) / len(stack_r)
        max_trades = max(r['trades'] for r in stack_r)
        above_30 = sum(1 for r in stack_r if r['trades'] >= 30)
        print(f"  {stack_label}: avg {avg_trades:.0f} trades  |  max {max_trades}  |  {above_30}/{len(stack_r)} combos with ≥30 trades")
