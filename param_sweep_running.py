"""
Parameter sweep for EmaFibRunningStrategy — TP mode comparison.

Grid covers:
  use_fib_tp    — True: TP = fib extension of body range; False: TP = risk manager R:R
  fib_tp        — fib extension multiplier (1×, 2×, 3×)  [use_fib_tp=True only]
  rr_ratio      — risk manager R:R (2.0, 2.5, 3.0)       [use_fib_tp=False only]
  fib_entry     — retracement entry level (61.8%, 78.6%)
  fractal_n     — bars each side for fractal confirmation (2, 3)
  ema_sep_pct   — minimum H1 EMA separation (off, 0.1%)

Fixed (WF-validated winners):
  min_swing_pips=30, cooldown_bars=0, invalidate_swing_on_loss=True
  blocked_hours=(20–23, 00–08)  [session sweep: 09:00–19:00 UTC]

Total: 2×3×3×2×2×2 = 144 combinations
"""

import itertools
import io
import contextlib
import logging
import sys

from backtest_engine import BacktestEngine
from strategies.ema_fib_running import EmaFibRunningStrategy
from data.historical_loader import find_csv, load_and_merge

logging.basicConfig(level=logging.ERROR)
sys.stdout.reconfigure(line_buffering=True)

SYMBOLS = ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDJPY', 'USDCAD', 'USDCHF']
INITIAL_BALANCE = 10_000.0

FIXED_PARAMS = {
    'min_swing_pips':           30,
    'cooldown_bars':            0,
    'invalidate_swing_on_loss': True,
    'blocked_hours':            (*range(20, 24), *range(0, 9)),
}

PARAM_GRID = {
    'use_fib_tp':  [True, False],    # True=fib ext; False=risk mgr R:R
    'fib_tp':      [1.0, 2.0, 3.0],  # fib extension multiplier
    'rr_ratio':    [2.0, 2.5, 3.0],  # R:R for risk manager
    'fib_entry':   [0.618, 0.786],
    'fractal_n':   [2, 3],
    'ema_sep_pct': [0.0, 0.001],
}

# ── Pre-load bar data once ────────────────────────────────────────────────────
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

keys   = list(PARAM_GRID.keys())
combos = list(itertools.product(*PARAM_GRID.values()))
total  = len(combos)
print(f"Running {total} parameter combinations (~{total * 2 // 60} min)...\n")

results = []

for i, combo in enumerate(combos):
    params = dict(zip(keys, combo))
    rr = params.pop('rr_ratio')

    strategy = EmaFibRunningStrategy(
        **FIXED_PARAMS,
        use_fib_tp=params['use_fib_tp'],
        fib_tp=params['fib_tp'],
        fib_entry=params['fib_entry'],
        fractal_n=params['fractal_n'],
        ema_sep_pct=params['ema_sep_pct'],
    )

    engine = BacktestEngine(initial_balance=INITIAL_BALANCE, rr_ratio=rr)
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

    wins    = sum(1 for t in trades if t['result'] == 'WIN')
    total_r = sum(t['r_multiple'] for t in trades)
    win_rate = wins / n * 100
    expectancy = total_r / n
    gp = sum(t['r_multiple'] for t in trades if t['result'] == 'WIN')
    gl = abs(sum(t['r_multiple'] for t in trades if t['result'] == 'LOSS'))
    pf = gp / gl if gl > 0 else 0.0

    peak, max_dd, running = 0.0, 0.0, 0.0
    for t in trades:
        running += t['r_multiple']
        peak    = max(peak, running)
        max_dd  = max(max_dd, peak - running)

    worst_streak, cur_streak = 0, 0
    for t in trades:
        if t['result'] == 'LOSS':
            cur_streak += 1
            worst_streak = max(worst_streak, cur_streak)
        else:
            cur_streak = 0

    results.append({
        **params,
        'rr_ratio':  rr,
        'trades':    n,
        'win_rate':  win_rate,
        'total_r':   total_r,
        'pf':        pf,
        'expectancy': expectancy,
        'max_dd_r':  max_dd,
        'worst_streak': worst_streak,
    })

    if (i + 1) % 50 == 0 or i + 1 == total:
        best_so_far = max((r['expectancy'] for r in results), default=0)
        print(f"  {i+1}/{total}  best expectancy so far: {best_so_far:+.3f}R")


# ── Display helpers ───────────────────────────────────────────────────────────
W = 175
HEADER = (
    f"{'tp_mode':>7} {'fib_tp':>6} {'rr':>5} {'fib_e':>6} {'frac':>4} {'ema_s':>6} | "
    f"{'trades':>6} {'WR%':>6} {'TotalR':>8} {'PF':>6} {'Expect':>7} {'MaxDD':>6} {'Streak':>6}"
)


def row(r):
    tp_mode    = 'fib' if r['use_fib_tp'] else 'R:R'
    fib_tp_str = f"{r['fib_tp']:>6.1f}" if r['use_fib_tp'] else '    --'
    rr_str     = f"{r['rr_ratio']:>5.1f}" if not r['use_fib_tp'] else '   --'
    return (
        f"{tp_mode:>7} {fib_tp_str} {rr_str} {r['fib_entry']:>6.3f} {r['fractal_n']:>4} "
        f"{r['ema_sep_pct']:>6.4f} | "
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

# ── 2. Top by Expectancy (min 100 trades) ────────────────────────────────────
filtered = [r for r in results if r['trades'] >= 100]
filtered.sort(key=lambda r: r['expectancy'], reverse=True)
print_table("TOP 30 BY EXPECTANCY  (min 100 trades)", filtered)

# ── 3. Top by Profit Factor (min 100 trades) ─────────────────────────────────
filtered.sort(key=lambda r: r['pf'], reverse=True)
print_table("TOP 20 BY PROFIT FACTOR  (min 100 trades)", filtered, n=20)

# ── 4. Risk-adjusted (min 100 trades) ────────────────────────────────────────
for r in filtered:
    r['risk_adj'] = r['expectancy'] / r['max_dd_r'] if r['max_dd_r'] > 0 else 0.0
filtered.sort(key=lambda r: r['risk_adj'], reverse=True)
print_table("TOP 20 BY RISK-ADJUSTED  (expectancy / max_DD, min 100 trades)", filtered, n=20)

# ── Current live config for comparison ───────────────────────────────────────
print(f"\n{'='*W}")
print("CURRENT LIVE CONFIG:  tp_mode=fib  fib_tp=2.5  fib_e=0.786  frac=2  ema_s=0.0")
live = [r for r in results
        if r['use_fib_tp'] is True and r['fib_tp'] == 2.0  # closest available to 2.5
        and r['fib_entry'] == 0.786 and r['fractal_n'] == 2
        and r['ema_sep_pct'] == 0.0]
if live:
    print("  Live config (fib_tp=2.0 — closest in grid to live 2.5):")
    print(f"  {row(live[0])}")

# Show all 6 TP modes at WF-validated entry params
print("\n  All 6 TP modes at WF-validated params (fib_e=0.786, frac=2, ema_s=0.0):")
tp_variants = [r for r in results
               if r['fib_entry'] == 0.786 and r['fractal_n'] == 2 and r['ema_sep_pct'] == 0.0
               and (
                   (r['use_fib_tp'] is True and r['rr_ratio'] == 2.0)
                   or r['use_fib_tp'] is False
               )]
tp_variants.sort(key=lambda r: (not r['use_fib_tp'], r['fib_tp'] if r['use_fib_tp'] else r['rr_ratio']))
for r in tp_variants:
    print(f"  {row(r)}")
print(f"{'='*W}")
