"""
Parameter sweep for London Breakout Strategy (LBS).
Sweeps RR ratio only. SL is fixed at range midpoint. No EMA or body filters.
"""

import itertools
import io
import contextlib
import logging
import sys

from backtest_engine import BacktestEngine
from strategies.london_breakout import LondonBreakoutStrategy
from data.historical_loader import find_csv, load_and_merge

logging.basicConfig(level=logging.ERROR)
sys.stdout.reconfigure(line_buffering=True)

SYMBOLS = ['EURUSD', 'GBPUSD', 'AUDUSD', 'USDJPY', 'USDCAD', 'USDCHF']
INITIAL_BALANCE = 10_000.0

PARAM_GRID = {
    'rr_ratio': [1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0],
}

# ── Load M5 bars ─────────────────────────────────────────────────────────────
csv_paths = []
for symbol in SYMBOLS:
    csv_paths.extend(find_csv(symbol, 'M5'))

if not csv_paths:
    print("No CSV files found.")
    sys.exit(1)

print("Loading bar data...")
all_bars = load_and_merge(csv_paths)
print(f"Loaded {len(all_bars)} bars")

keys   = list(PARAM_GRID.keys())
combos = list(itertools.product(*PARAM_GRID.values()))
total  = len(combos)
print(f"Running {total} combinations...\n")

results = []

for i, combo in enumerate(combos):
    params = dict(zip(keys, combo))
    rr     = params['rr_ratio']

    strategy = LondonBreakoutStrategy(rr_ratio=rr)
    engine   = BacktestEngine(initial_balance=INITIAL_BALANCE, rr_ratio=rr)
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
    gp      = sum(t['r_multiple'] for t in trades if t['result'] == 'WIN')
    gl      = abs(sum(t['r_multiple'] for t in trades if t['result'] == 'LOSS'))
    pf      = gp / gl if gl > 0 else 0.0

    peak, max_dd, running = 0.0, 0.0, 0.0
    for t in trades:
        running += t['r_multiple']
        peak    = max(peak, running)
        max_dd  = max(max_dd, peak - running)

    results.append({
        'rr_ratio':  rr,
        'trades':    n,
        'win_rate':  wins / n * 100,
        'total_r':   total_r,
        'pf':        pf,
        'expectancy': total_r / n,
        'max_dd_r':  max_dd,
    })
    print(f"  RR {rr:.1f} → {n} trades  WR {wins/n*100:.1f}%  Expect {total_r/n:+.3f}R  TotalR {total_r:+.1f}")

W = 80
HEADER = f"{'RR':>5} | {'trades':>6} {'WR%':>6} {'TotalR':>8} {'PF':>6} {'Expect':>7} {'MaxDD':>6}"

def row(r):
    return (
        f"{r['rr_ratio']:>5.1f} | "
        f"{r['trades']:>6} {r['win_rate']:>5.1f}% {r['total_r']:>+8.1f} "
        f"{r['pf']:>6.2f} {r['expectancy']:>+7.3f} {r['max_dd_r']:>6.1f}"
    )

print(f"\n{'='*W}")
print("RESULTS BY RR RATIO  (EURUSD+GBPUSD+AUDUSD+USDJPY+USDCAD+USDCHF, range-midpoint SL)")
print(f"{'='*W}")
print(HEADER)
print('-' * W)
for r in sorted(results, key=lambda r: r['expectancy'], reverse=True):
    print(row(r))
print(f"{'='*W}")
