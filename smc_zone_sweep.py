"""
Parameter sweep for SmcZoneStrategy.

Grid:
  swing_length   — bars each side for pivot confirmation (3, 5, 7, 10)
  zone_atr_mult  — zone width in ATRs (1.0, 1.5, 2.0, 2.5, 3.0)
  zone_leg_atr   — min impulse move away from pivot (0.0, 1.0, 1.5, 2.0, 2.5)

Total: 4 × 5 × 5 = 100 combinations
"""

import itertools
import io
import contextlib
import logging
import sys

from backtest_engine import BacktestEngine
from strategies.smc_zone import SmcZoneStrategy
from data.historical_loader import find_csv, load_and_merge

logging.basicConfig(level=logging.ERROR)
sys.stdout.reconfigure(line_buffering=True)

SYMBOLS = ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDJPY', 'USDCAD', 'USDCHF']
INITIAL_BALANCE = 10_000.0
RR_RATIO = 2.0

PARAM_GRID = {
    'swing_length':  [3, 5, 7, 10],
    'zone_atr_mult': [1.0, 1.5, 2.0, 2.5, 3.0],
    'zone_leg_atr':  [0.0, 1.0, 1.5, 2.0, 2.5],
}

# Fixed params
BLOCKED_HOURS = (*range(20, 24), *range(0, 9))
SL_BUFFER_ATR = 0.5
D1_EMA_PERIOD = 50
TF_ENTRY = 'H4'

# ── Pre-load bar data once ──────────────────────────────────────────────────
csv_paths = []
for symbol in SYMBOLS:
    for tf in ['D1', TF_ENTRY]:
        csv_paths.extend(find_csv(symbol, tf))

if not csv_paths:
    print("No CSV files found.")
    sys.exit(1)

print("Loading bar data...")
all_bars = load_and_merge(csv_paths)
print(f"Loaded {len(all_bars):,} bars")

keys = list(PARAM_GRID.keys())
combos = list(itertools.product(*PARAM_GRID.values()))
total = len(combos)
print(f"Running {total} combinations...\n")

results = []

for i, combo in enumerate(combos):
    params = dict(zip(keys, combo))

    strategy = SmcZoneStrategy(
        swing_length=params['swing_length'],
        tf_entry=TF_ENTRY,
        zone_atr_mult=params['zone_atr_mult'],
        sl_buffer_atr=SL_BUFFER_ATR,
        zone_leg_atr=params['zone_leg_atr'],
        d1_ema_period=D1_EMA_PERIOD,
        blocked_hours=BLOCKED_HOURS,
    )

    engine = BacktestEngine(initial_balance=INITIAL_BALANCE, rr_ratio=RR_RATIO)
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
    if n < 30:
        continue

    wins = [t for t in trades if t['result'] == 'WIN']
    losses = [t for t in trades if t['result'] == 'LOSS']
    total_r = sum(t['r_multiple'] for t in trades)
    win_rate = len(wins) / n * 100
    expectancy = total_r / n
    gp = sum(t['r_multiple'] for t in wins)
    gl = abs(sum(t['r_multiple'] for t in losses))
    pf = gp / gl if gl > 0 else 0.0

    peak, max_dd, running = 0.0, 0.0, 0.0
    for t in trades:
        running += t['r_multiple']
        peak = max(peak, running)
        max_dd = max(max_dd, peak - running)

    worst_streak, cur_streak = 0, 0
    for t in trades:
        if t['result'] == 'LOSS':
            cur_streak += 1
            worst_streak = max(worst_streak, cur_streak)
        else:
            cur_streak = 0

    results.append({
        **params,
        'trades': n,
        'win_rate': win_rate,
        'total_r': total_r,
        'pf': pf,
        'expectancy': expectancy,
        'max_dd_r': max_dd,
        'worst_streak': worst_streak,
    })

    if (i + 1) % 20 == 0 or i + 1 == total:
        best = max((r['expectancy'] for r in results), default=0)
        print(f"  {i+1}/{total}  best expectancy so far: {best:+.3f}R")


# ── Display ──────────────────────────────────────────────────────────────────
W = 130
HEADER = (
    f"{'sl':>4} {'z_atr':>5} {'leg':>5} | "
    f"{'trades':>6} {'WR%':>6} {'TotalR':>8} {'PF':>6} {'Expect':>7} {'MaxDD':>6} {'Streak':>6}"
)

def row(r):
    return (
        f"{r['swing_length']:>4} {r['zone_atr_mult']:>5.1f} {r['zone_leg_atr']:>5.1f} | "
        f"{r['trades']:>6} {r['win_rate']:>5.1f}% {r['total_r']:>+8.1f} "
        f"{r['pf']:>6.2f} {r['expectancy']:>+7.3f} {r['max_dd_r']:>6.1f} {r['worst_streak']:>6}"
    )

def print_table(title, rows, n=25):
    print(f"\n{'='*W}")
    print(title)
    print(f"{'='*W}")
    print(HEADER)
    print('-' * W)
    for r in rows[:n]:
        print(row(r))

print_table("TOP 25 BY EXPECTANCY", sorted(results, key=lambda r: r['expectancy'], reverse=True))
print_table("TOP 25 BY TOTAL R",    sorted(results, key=lambda r: r['total_r'],    reverse=True))
print_table("TOP 25 BY PROFIT FACTOR (min 50 trades)",
            sorted([r for r in results if r['trades'] >= 50], key=lambda r: r['pf'], reverse=True))
