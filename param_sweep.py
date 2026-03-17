"""
Parameter sweep for EmaFibRetracement strategy.
Tests combinations and outputs a ranked results table.
"""

import itertools
import logging
import sys

from backtest_engine import BacktestEngine
from strategies.ema_fib_retracement import EmaFibRetracementStrategy
from data.historical_loader import find_csv

logging.basicConfig(level=logging.ERROR)
sys.stdout.reconfigure(line_buffering=True)

SYMBOLS = ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDJPY', 'USDCAD']
INITIAL_BALANCE = 10_000.0
RR_RATIO = 2.0
SPREAD_PIPS = 2.0

# ── Parameter grid ──────────────────────────────────────────────────────────
PARAM_GRID = {
    'swing_max_age':          [50, 100, 150],
    'cooldown_bars':          [0, 10, 20],
    'invalidate_swing_on_loss': [True, False],
    'min_swing_pips':         [10, 15, 20],
    'ema_sep_pct':            [0.0, 0.0005],
    'min_d1_atr_pips':        [0, 50],
    'fractal_n':              [2, 3, 5],
}

# ── Discover CSV files ──────────────────────────────────────────────────────
csv_paths = []
for symbol in SYMBOLS:
    for tf in ['D1', 'H1']:
        path = find_csv(symbol, tf)
        if path:
            csv_paths.append(path)

if not csv_paths:
    print("No CSV files found.")
    sys.exit(1)

# ── Pre-load bar data once ──────────────────────────────────────────────────
from data.historical_loader import load_and_merge
print("Loading bar data...")
all_bars = load_and_merge(csv_paths)
print(f"Loaded {len(all_bars)} bars")

# ── Generate all combinations ───────────────────────────────────────────────
keys = list(PARAM_GRID.keys())
values = list(PARAM_GRID.values())
combos = list(itertools.product(*values))
total = len(combos)
print(f"Running {total} parameter combinations...\n")

results = []

for i, combo in enumerate(combos):
    params = dict(zip(keys, combo))

    strategy = EmaFibRetracementStrategy(
        swing_max_age=params['swing_max_age'],
        cooldown_bars=params['cooldown_bars'],
        invalidate_swing_on_loss=params['invalidate_swing_on_loss'],
        min_swing_pips=params['min_swing_pips'],
        ema_sep_pct=params['ema_sep_pct'],
        min_d1_atr_pips=params['min_d1_atr_pips'],
        fractal_n=params['fractal_n'],
    )

    engine = BacktestEngine(
        initial_balance=INITIAL_BALANCE,
        rr_ratio=RR_RATIO,
        spread_pips=SPREAD_PIPS,
    )
    engine.add_strategy(strategy, symbols=SYMBOLS)

    # Suppress all print output from the engine — feed pre-loaded bars directly
    import io, contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        for bar in all_bars:
            closed_trades = engine.execution.check_fills(bar)
            for trade in closed_trades:
                engine.portfolio.record_close(trade['symbol'], trade['pnl'])
                engine.trade_logger.log_close(trade['ticket'], trade)
                engine.event_engine.notify_trade_closed(trade)
            engine.event_engine.process_bar(bar)

    trades = engine.execution.get_closed_trades()
    total_trades = len(trades)

    if total_trades == 0:
        continue

    wins = sum(1 for t in trades if t['result'] == 'WIN')
    total_r = sum(t['r_multiple'] for t in trades)
    win_rate = wins / total_trades * 100
    expectancy = total_r / total_trades
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
    worst_streak = 0
    current_streak = 0
    for t in trades:
        if t['result'] == 'LOSS':
            current_streak += 1
            worst_streak = max(worst_streak, current_streak)
        else:
            current_streak = 0

    results.append({
        **params,
        'trades': total_trades,
        'win_rate': win_rate,
        'total_r': total_r,
        'pf': pf,
        'expectancy': expectancy,
        'max_dd_r': max_dd,
        'worst_streak': worst_streak,
    })

    if (i + 1) % 50 == 0 or i + 1 == total:
        print(f"  Progress: {i+1}/{total}")

# ── Sort and display results ────────────────────────────────────────────────
# Primary sort: total_r descending
results.sort(key=lambda r: r['total_r'], reverse=True)

print(f"\n{'='*160}")
print(f"TOP 30 BY TOTAL R (out of {len(results)} valid combinations)")
print(f"{'='*160}")
header = (
    f"{'swing_age':>9} {'cool':>4} {'inval':>5} {'min_sw':>6} {'ema_sep':>7} "
    f"{'atr_pip':>7} {'frac_n':>6} | "
    f"{'trades':>6} {'WR%':>6} {'TotalR':>8} {'PF':>6} {'Expect':>7} {'MaxDD':>6} {'Streak':>6}"
)
print(header)
print('-' * 160)

for r in results[:30]:
    print(
        f"{r['swing_max_age']:>9} {r['cooldown_bars']:>4} "
        f"{'Y' if r['invalidate_swing_on_loss'] else 'N':>5} "
        f"{r['min_swing_pips']:>6.0f} {r['ema_sep_pct']:>7.4f} "
        f"{r['min_d1_atr_pips']:>7.0f} {r['fractal_n']:>6} | "
        f"{r['trades']:>6} {r['win_rate']:>5.1f}% {r['total_r']:>+8.1f} "
        f"{r['pf']:>6.2f} {r['expectancy']:>+7.2f} {r['max_dd_r']:>6.1f} {r['worst_streak']:>6}"
    )

print(f"\n{'='*160}")
print(f"TOP 20 BY EXPECTANCY (minimum 200 trades)")
print(f"{'='*160}")
print(header)
print('-' * 160)

filtered = [r for r in results if r['trades'] >= 200]
filtered.sort(key=lambda r: r['expectancy'], reverse=True)
for r in filtered[:20]:
    print(
        f"{r['swing_max_age']:>9} {r['cooldown_bars']:>4} "
        f"{'Y' if r['invalidate_swing_on_loss'] else 'N':>5} "
        f"{r['min_swing_pips']:>6.0f} {r['ema_sep_pct']:>7.4f} "
        f"{r['min_d1_atr_pips']:>7.0f} {r['fractal_n']:>6} | "
        f"{r['trades']:>6} {r['win_rate']:>5.1f}% {r['total_r']:>+8.1f} "
        f"{r['pf']:>6.2f} {r['expectancy']:>+7.2f} {r['max_dd_r']:>6.1f} {r['worst_streak']:>6}"
    )

print(f"\n{'='*160}")
print(f"TOP 20 BY PROFIT FACTOR (minimum 200 trades)")
print(f"{'='*160}")
print(header)
print('-' * 160)

filtered.sort(key=lambda r: r['pf'], reverse=True)
for r in filtered[:20]:
    print(
        f"{r['swing_max_age']:>9} {r['cooldown_bars']:>4} "
        f"{'Y' if r['invalidate_swing_on_loss'] else 'N':>5} "
        f"{r['min_swing_pips']:>6.0f} {r['ema_sep_pct']:>7.4f} "
        f"{r['min_d1_atr_pips']:>7.0f} {r['fractal_n']:>6} | "
        f"{r['trades']:>6} {r['win_rate']:>5.1f}% {r['total_r']:>+8.1f} "
        f"{r['pf']:>6.2f} {r['expectancy']:>+7.2f} {r['max_dd_r']:>6.1f} {r['worst_streak']:>6}"
    )

# Current config for comparison
print(f"\n{'='*160}")
print("CURRENT CONFIG: swing_age=100, cool=10, inval=Y, min_sw=15, ema_sep=0.0005, atr_pip=50, frac_n=3")
current = [r for r in results
           if r['swing_max_age'] == 100 and r['cooldown_bars'] == 10
           and r['invalidate_swing_on_loss'] is True and r['min_swing_pips'] == 15
           and r['ema_sep_pct'] == 0.0005 and r['min_d1_atr_pips'] == 50
           and r['fractal_n'] == 3]
if current:
    r = current[0]
    print(
        f"  trades={r['trades']}  WR={r['win_rate']:.1f}%  TotalR={r['total_r']:+.1f}  "
        f"PF={r['pf']:.2f}  Expect={r['expectancy']:+.2f}  MaxDD={r['max_dd_r']:.1f}R  "
        f"WorstStreak={r['worst_streak']}"
    )
print(f"{'='*160}")
