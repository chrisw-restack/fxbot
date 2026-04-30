"""
Parameter sweep for EmaFibRetracement strategy.
Tests combinations and outputs a ranked results table.

Grid covers:
  use_fib_tp       — True: TP = fib extension of swing; False: TP = risk manager R:R
  fib_tp           — fib extension multiplier (1×, 2×, 3×)   [use_fib_tp=True only]
  rr_ratio         — risk manager R:R (2.0, 2.5, 3.0)        [use_fib_tp=False only]
  fib_entry        — retracement entry level (50%, 61.8%, 78.6%)
  fractal_n        — bars each side for fractal confirmation (2, 3)
  min_swing_pips   — minimum swing range filter (10, 20)
  ema_sep_pct      — minimum H1 EMA separation (off, 0.1%)
  cooldown_bars    — H1 bars to skip after a loss (0, 10)
  invalidate_swing — discard swing that produced a loss (Y/N)
  swing_max_age    — max H1 bar age for a swing to remain valid (100, fixed)

  require_recent_swing_alignment: fixed False  (all prior WF folds: hurt/no benefit)
  pending_max_age_bars: fixed 0               (all prior WF folds: hurt/no benefit)

Total: 2×3×3×3×2×2×2×2×2×1 = 864 combinations
"""

import itertools
import io
import contextlib
import logging
import sys

from backtest_engine import BacktestEngine
from strategies.ema_fib_retracement import EmaFibRetracementStrategy
from data.historical_loader import find_csv, load_and_merge

logging.basicConfig(level=logging.ERROR)
sys.stdout.reconfigure(line_buffering=True)

SYMBOLS = ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDJPY', 'USDCAD', 'USDCHF']
INITIAL_BALANCE = 10_000.0

# ── Parameter grid ──────────────────────────────────────────────────────────
# Updated 2026-04-29: added use_fib_tp / rr_ratio to compare fib-extension TP
# against fixed R:R TP. fib_tp expanded to include 1.0. Dropped
# require_recent_swing_alignment and pending_max_age_bars (confirmed losers in
# all prior WF folds — fixed at defaults). min_swing_pips reduced to [10, 20]
# (30 was consistently weak). rr_ratio extracted and forwarded to BacktestEngine
# (not passed to strategy constructor).
PARAM_GRID = {
    'use_fib_tp':               [True, False],    # True=fib ext; False=risk mgr R:R
    'fib_tp':                   [1.0, 2.0, 3.0],  # fib extension multiplier
    'rr_ratio':                 [2.0, 2.5, 3.0],  # R:R for risk manager
    'fib_entry':                [0.5, 0.618, 0.786],
    'fractal_n':                [2, 3],
    'min_swing_pips':           [10, 20],
    'ema_sep_pct':              [0.0, 0.001],
    'cooldown_bars':            [0, 10],
    'invalidate_swing_on_loss': [True, False],
    'swing_max_age':            [100],
}

# ── Discover and pre-load bar data once ────────────────────────────────────
csv_paths = []
for symbol in SYMBOLS:
    for tf in ['D1', 'H1']:
        csv_paths.extend(find_csv(symbol, tf))

if not csv_paths:
    print("No CSV files found.")
    sys.exit(1)

print("Loading bar data...")
all_bars = load_and_merge(csv_paths)
print(f"Loaded {len(all_bars)} bars")

# ── Generate all combinations ───────────────────────────────────────────────
keys = list(PARAM_GRID.keys())
combos = list(itertools.product(*PARAM_GRID.values()))
total = len(combos)
print(f"Running {total} parameter combinations (~{total * 2 // 60} min)...\n")

results = []

for i, combo in enumerate(combos):
    params = dict(zip(keys, combo))
    rr = params.pop('rr_ratio')  # engine param, not strategy param

    strategy = EmaFibRetracementStrategy(
        use_fib_tp=params['use_fib_tp'],
        fib_entry=params['fib_entry'],
        fib_tp=params['fib_tp'],
        fractal_n=params['fractal_n'],
        min_swing_pips=params['min_swing_pips'],
        ema_sep_pct=params['ema_sep_pct'],
        cooldown_bars=params['cooldown_bars'],
        invalidate_swing_on_loss=params['invalidate_swing_on_loss'],
        swing_max_age=params['swing_max_age'],
        blocked_hours=(*range(20, 24), *range(0, 9)),  # allow 09:00-19:00 UTC
    )

    engine = BacktestEngine(
        initial_balance=INITIAL_BALANCE,
        rr_ratio=rr,
    )
    engine.add_strategy(strategy, symbols=SYMBOLS)

    with contextlib.redirect_stdout(io.StringIO()):
        for bar in all_bars:
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

    # Max drawdown in R
    peak, max_dd, running = 0.0, 0.0, 0.0
    for t in trades:
        running += t['r_multiple']
        peak = max(peak, running)
        max_dd = max(max_dd, peak - running)

    # Worst loss streak
    worst_streak, cur_streak = 0, 0
    for t in trades:
        if t['result'] == 'LOSS':
            cur_streak += 1
            worst_streak = max(worst_streak, cur_streak)
        else:
            cur_streak = 0

    results.append({
        **params,
        'rr_ratio': rr,   # re-add after pop so it's available in output
        'trades': n,
        'win_rate': win_rate,
        'total_r': total_r,
        'pf': pf,
        'expectancy': expectancy,
        'max_dd_r': max_dd,
        'worst_streak': worst_streak,
    })

    if (i + 1) % 100 == 0 or i + 1 == total:
        best_so_far = max((r['expectancy'] for r in results), default=0)
        print(f"  {i+1}/{total}  best expectancy so far: {best_so_far:+.3f}R")


# ── Display helpers ──────────────────────────────────────────────────────────
W = 185
HEADER = (
    f"{'tp_mode':>7} {'fib_tp':>6} {'rr':>5} {'fib_e':>6} {'frac':>4} "
    f"{'sw_pip':>6} {'ema_s':>6} {'cool':>4} {'inv':>3} {'sw_age':>6} | "
    f"{'trades':>6} {'WR%':>6} {'TotalR':>8} {'PF':>6} {'Expect':>7} {'MaxDD':>6} {'Streak':>6}"
)

def row(r):
    tp_mode = 'fib' if r['use_fib_tp'] else 'R:R'
    fib_tp_str = f"{r['fib_tp']:>6.1f}" if r['use_fib_tp'] else '    --'
    rr_str     = f"{r['rr_ratio']:>5.1f}" if not r['use_fib_tp'] else '   --'
    return (
        f"{tp_mode:>7} {fib_tp_str} {rr_str} {r['fib_entry']:>6.3f} {r['fractal_n']:>4} "
        f"{r['min_swing_pips']:>6.0f} {r['ema_sep_pct']:>6.4f} "
        f"{r['cooldown_bars']:>4} {'Y' if r['invalidate_swing_on_loss'] else 'N':>3} "
        f"{r['swing_max_age']:>6} | "
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


# ── 1. Top by Total R ────────────────────────────────────────────────────────
results.sort(key=lambda r: r['total_r'], reverse=True)
print_table(f"TOP 30 BY TOTAL R  (out of {len(results)} valid combinations)", results)

# ── 2. Top by Expectancy (min 200 trades) ───────────────────────────────────
filtered = [r for r in results if r['trades'] >= 200]
filtered.sort(key=lambda r: r['expectancy'], reverse=True)
print_table("TOP 30 BY EXPECTANCY  (min 200 trades)", filtered)

# ── 3. Top by Profit Factor (min 200 trades) ────────────────────────────────
filtered.sort(key=lambda r: r['pf'], reverse=True)
print_table("TOP 20 BY PROFIT FACTOR  (min 200 trades)", filtered, n=20)

# ── 4. Risk-adjusted: expectancy / max_drawdown (min 200 trades, DD > 0) ───
for r in filtered:
    r['risk_adj'] = r['expectancy'] / r['max_dd_r'] if r['max_dd_r'] > 0 else 0.0
filtered.sort(key=lambda r: r['risk_adj'], reverse=True)
print_table("TOP 20 BY RISK-ADJUSTED  (expectancy / max_DD, min 200 trades)", filtered, n=20)

# ── Current live config for comparison ──────────────────────────────────────
print(f"\n{'='*W}")
print("CURRENT LIVE CONFIG:  tp_mode=fib  fib_tp=3.0  fib_e=0.786  frac=3  sw_pip=10  ema_s=0.001  cool=10  inv=Y  sw_age=100")
live = [r for r in results
        if r['use_fib_tp'] is True and r['fib_tp'] == 3.0
        and r['fib_entry'] == 0.786 and r['fractal_n'] == 3
        and r['min_swing_pips'] == 10 and r['ema_sep_pct'] == 0.001
        and r['cooldown_bars'] == 10 and r['invalidate_swing_on_loss'] is True
        and r['swing_max_age'] == 100]
if live:
    print("  Live config baseline (fib mode — rr_ratio column is irrelevant):")
    print(f"  {row(live[0])}")

# Show all 6 TP configs at otherwise-live params for direct comparison
print("\n  All 6 TP configs at live params (fib_e=0.786, frac=3, sw_pip=10, ema_s=0.001, cool=10, inv=Y):")
tp_variants = [r for r in results
               if r['fib_entry'] == 0.786 and r['fractal_n'] == 3
               and r['min_swing_pips'] == 10 and r['ema_sep_pct'] == 0.001
               and r['cooldown_bars'] == 10 and r['invalidate_swing_on_loss'] is True
               and r['swing_max_age'] == 100
               and (
                   # fib configs: one rr_ratio value (they're all identical; take 2.0)
                   (r['use_fib_tp'] is True and r['rr_ratio'] == 2.0)
                   # R:R configs: show all three
                   or r['use_fib_tp'] is False
               )]
tp_variants.sort(key=lambda r: (not r['use_fib_tp'], r['fib_tp'] if r['use_fib_tp'] else r['rr_ratio']))
for r in tp_variants:
    print(f"  {row(r)}")
print(f"{'='*W}")
