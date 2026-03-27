"""Parameter sweep for EmaFibRunning strategy."""

import itertools
import logging
import sys
import io
import contextlib

from backtest_engine import BacktestEngine
from strategies.ema_fib_running import EmaFibRunningStrategy
from data.historical_loader import find_csv, load_and_merge

logging.basicConfig(level=logging.ERROR)
sys.stdout.reconfigure(line_buffering=True)

SYMBOLS = ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDJPY', 'USDCAD', 'USDCHF']
INITIAL_BALANCE = 10_000.0
RR_RATIO = 2.0
SPREAD_PIPS = 2.0

PARAM_GRID = {
    'fib_entry':        [0.382, 0.5, 0.618],
    'fib_tp':           [1.618, 2.0, 2.618],
    'min_swing_pips':   [10, 15, 20, 30],
    'max_sl_pips':      [0, 40, 60, 80],      # 0 = no max limit
    'cooldown_bars':    [0, 5, 10],
    'ema_sep_pct':      [0.0005, 0.001],
}

# Fixed params (same as original best)
FIXED = {
    'invalidate_swing_on_loss': True,
}

# Load data
csv_paths = []
for sym in SYMBOLS:
    for tf in ['D1', 'H1']:
        csv_paths.extend(find_csv(sym, tf))

print("Loading bar data...")
all_bars = load_and_merge(csv_paths)
print(f"Loaded {len(all_bars):,} bars")

keys = list(PARAM_GRID.keys())
combos = list(itertools.product(*PARAM_GRID.values()))
total = len(combos)
print(f"Running {total} parameter combinations...\n")

results = []

for i, combo in enumerate(combos):
    params = dict(zip(keys, combo))

    # Build strategy kwargs
    strat_kwargs = {**FIXED, **params}
    max_sl = strat_kwargs.pop('max_sl_pips')  # handle separately

    strategy = EmaFibRunningStrategy(**strat_kwargs)

    engine = BacktestEngine(
        initial_balance=INITIAL_BALANCE, rr_ratio=RR_RATIO, spread_pips=SPREAD_PIPS,
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

    # Apply max SL filter post-hoc (easier than adding to strategy)
    if max_sl > 0:
        trades = [t for t in trades if t.get('sl_pips', 999) <= max_sl]

    total_trades = len(trades)
    if total_trades == 0:
        if (i + 1) % 50 == 0:
            print(f"  Progress: {i+1}/{total}")
        continue

    wins = sum(1 for t in trades if t['result'] == 'WIN')
    total_r = sum(t['r_multiple'] for t in trades)
    win_rate = wins / total_trades * 100
    gp = sum(t['r_multiple'] for t in trades if t['result'] == 'WIN')
    gl = abs(sum(t['r_multiple'] for t in trades if t['result'] == 'LOSS'))
    pf = gp / gl if gl > 0 else 0.0

    peak = running = max_dd = 0.0
    for t in trades:
        running += t['r_multiple']
        peak = max(peak, running)
        max_dd = max(max_dd, peak - running)

    worst_streak = cur = 0
    for t in trades:
        if t['result'] == 'LOSS':
            cur += 1
            worst_streak = max(worst_streak, cur)
        else:
            cur = 0

    results.append({
        **params,
        'max_sl_pips': max_sl,
        'trades': total_trades,
        'win_rate': win_rate,
        'total_r': total_r,
        'pf': pf,
        'expectancy': total_r / total_trades,
        'max_dd_r': max_dd,
        'worst_streak': worst_streak,
    })

    if (i + 1) % 50 == 0 or i + 1 == total:
        print(f"  Progress: {i+1}/{total}")

# ── Results ──────────────────────────────────────────────────────────────────
results.sort(key=lambda r: r['total_r'], reverse=True)

header = (
    f"{'fib_e':>5} {'fib_tp':>6} {'min_sl':>6} {'max_sl':>6} {'cool':>4} {'ema_s':>6} | "
    f"{'trades':>6} {'WR%':>6} {'TotalR':>8} {'PF':>6} {'Expect':>7} {'MaxDD':>6} {'LStrk':>5}"
)

print(f"\n{'='*100}")
print(f"TOP 30 BY TOTAL R (out of {len(results)} valid)")
print(f"{'='*100}")
print(header)
print('-' * 100)
for r in results[:30]:
    ms = f"{r['max_sl_pips']}" if r['max_sl_pips'] > 0 else 'none'
    print(
        f"{r['fib_entry']:>5.3f} {r['fib_tp']:>6.3f} {r['min_swing_pips']:>6.0f} {ms:>6} "
        f"{r['cooldown_bars']:>4} {r['ema_sep_pct']:>6.4f} | "
        f"{r['trades']:>6} {r['win_rate']:>5.1f}% {r['total_r']:>+8.1f} "
        f"{r['pf']:>6.2f} {r['expectancy']:>+7.3f} {r['max_dd_r']:>6.1f} {r['worst_streak']:>5}"
    )

print(f"\n{'='*100}")
print(f"TOP 20 BY EXPECTANCY (min 100 trades)")
print(f"{'='*100}")
print(header)
print('-' * 100)
filtered = [r for r in results if r['trades'] >= 100]
filtered.sort(key=lambda r: r['expectancy'], reverse=True)
for r in filtered[:20]:
    ms = f"{r['max_sl_pips']}" if r['max_sl_pips'] > 0 else 'none'
    print(
        f"{r['fib_entry']:>5.3f} {r['fib_tp']:>6.3f} {r['min_swing_pips']:>6.0f} {ms:>6} "
        f"{r['cooldown_bars']:>4} {r['ema_sep_pct']:>6.4f} | "
        f"{r['trades']:>6} {r['win_rate']:>5.1f}% {r['total_r']:>+8.1f} "
        f"{r['pf']:>6.2f} {r['expectancy']:>+7.3f} {r['max_dd_r']:>6.1f} {r['worst_streak']:>5}"
    )

# Positive combos count
positive = [r for r in results if r['total_r'] > 0]
print(f"\n  Positive combos: {len(positive)}/{len(results)}")

# Breakdown by fib_entry
for fib in sorted(set(r['fib_entry'] for r in results)):
    subset = [r for r in results if r['fib_entry'] == fib]
    pos = sum(1 for r in subset if r['total_r'] > 0)
    print(f"    fib_entry={fib:.3f}: {pos}/{len(subset)} positive")

# Breakdown by max_sl
for ms in sorted(set(r['max_sl_pips'] for r in results)):
    subset = [r for r in results if r['max_sl_pips'] == ms]
    pos = sum(1 for r in subset if r['total_r'] > 0)
    label = f"{ms}" if ms > 0 else "none"
    print(f"    max_sl={label}: {pos}/{len(subset)} positive")
