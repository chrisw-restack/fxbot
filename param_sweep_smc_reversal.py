"""
Parameter sweep for SmcReversalStrategy (USA100 + USA30 + USA500).

All price-level params are expressed as fractions of price so they scale
automatically across the three indices.

Grid:
  fractal_n                — D1 swing detection bars each side     (2, 3, 5)
  fvg_window               — candles after series to find FVG      (2, 4, 6)
  wiggle_room_pct          — OB overlap tolerance as % of price    (0, 0.002, 0.003, 0.006)
  sl_buffer_pct            — extra buffer below/above SL swing     (0.0003, 0.0006, 0.001)
  multiple_trades_per_bias — allow re-entry while bias is active    (True, False)

Total: 3 × 3 × 4 × 3 × 2 = 216 combinations
"""

import itertools
import io
import contextlib
import logging
import sys

from backtest_engine import BacktestEngine
from strategies.smc_reversal import SmcReversalStrategy
from data.historical_loader import find_csv, load_and_merge

logging.basicConfig(level=logging.ERROR)
sys.stdout.reconfigure(line_buffering=True)

SYMBOLS = ['USTEC', 'US30', 'US500']
TIMEFRAMES = ['D1', 'H4', 'H1', 'M15', 'M5']
INITIAL_BALANCE = 10_000.0
RR_RATIO = 2.0
MIN_TRADES = 60   # ~3 symbols × ~20 trades each over 10yr

# ── Parameter grid ───────────────────────────────────────────────────────────
PARAM_GRID = {
    'fractal_n':                [2, 3, 5],
    'fvg_window':               [2, 4, 6],
    'wiggle_room_pct':          [0.0, 0.002, 0.003, 0.006],
    'sl_buffer_pct':            [0.0003, 0.0006, 0.001],
    'multiple_trades_per_bias': [True, False],
}

# ── Pre-load bar data once ───────────────────────────────────────────────────
csv_paths = []
for symbol in SYMBOLS:
    for tf in TIMEFRAMES:
        paths = find_csv(symbol, tf)
        if not paths:
            print(f"ERROR: No CSV found for {symbol} {tf} — run fetch_data first.")
            sys.exit(1)
        csv_paths.extend(paths)

print("Loading bar data...")
all_bars = load_and_merge(csv_paths)
print(f"Loaded {len(all_bars):,} bars across {len(SYMBOLS)} symbols × {len(TIMEFRAMES)} timeframes\n")

# ── Generate all combinations ────────────────────────────────────────────────
keys = list(PARAM_GRID.keys())
combos = list(itertools.product(*PARAM_GRID.values()))
total = len(combos)
print(f"Running {total} parameter combinations...\n")

results = []

for i, combo in enumerate(combos):
    params = dict(zip(keys, combo))

    strategy = SmcReversalStrategy(
        fractal_n=params['fractal_n'],
        fvg_window=params['fvg_window'],
        wiggle_room_pct=params['wiggle_room_pct'],
        sl_buffer_pct=params['sl_buffer_pct'],
        multiple_trades_per_bias=params['multiple_trades_per_bias'],
    )

    engine = BacktestEngine(initial_balance=INITIAL_BALANCE, rr_ratio=RR_RATIO)
    engine.add_strategy(strategy, symbols=SYMBOLS)

    with contextlib.redirect_stdout(io.StringIO()):
        for bar in all_bars:
            closed_trades = engine.execution.check_fills(bar)
            for trade in closed_trades:
                engine.portfolio.record_close(
                    trade['symbol'], trade['pnl'], trade.get('strategy_name', '')
                )
                engine.trade_logger.log_close(trade['ticket'], trade)
                engine.event_engine.notify_trade_closed(trade)
            engine.event_engine.process_bar(bar)

    trades = engine.execution.get_closed_trades()
    n = len(trades)
    if n < MIN_TRADES:
        continue

    wins = sum(1 for t in trades if t['result'] == 'WIN')
    total_r = sum(t['r_multiple'] for t in trades)
    win_rate = wins / n * 100
    expectancy = total_r / n
    gp = sum(t['r_multiple'] for t in trades if t['result'] == 'WIN')
    gl = abs(sum(t['r_multiple'] for t in trades if t['result'] == 'LOSS'))
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
        'trades':       n,
        'win_rate':     win_rate,
        'total_r':      total_r,
        'pf':           pf,
        'expectancy':   expectancy,
        'max_dd_r':     max_dd,
        'worst_streak': worst_streak,
    })

    if (i + 1) % 50 == 0 or i + 1 == total:
        best = max((r['expectancy'] for r in results), default=0.0)
        print(f"  {i+1}/{total}  combos with >={MIN_TRADES} trades: {len(results)}  "
              f"best expectancy so far: {best:+.3f}R")

# ── Display helpers ──────────────────────────────────────────────────────────
W = 140
HEADER = (
    f"{'frac':>4} {'fvg_w':>5} {'wiggle%':>8} {'slbuf%':>7} {'multi':>5} | "
    f"{'trades':>6} {'WR%':>6} {'TotalR':>8} {'PF':>6} {'Expect':>7} "
    f"{'MaxDD':>6} {'Streak':>6}"
)

def row(r):
    return (
        f"{r['fractal_n']:>4} {r['fvg_window']:>5} "
        f"{r['wiggle_room_pct']*100:>7.3f}% {r['sl_buffer_pct']*100:>6.4f}% "
        f"{'Y' if r['multiple_trades_per_bias'] else 'N':>5} | "
        f"{r['trades']:>6} {r['win_rate']:>5.1f}% {r['total_r']:>+8.1f} "
        f"{r['pf']:>6.2f} {r['expectancy']:>+7.3f} "
        f"{r['max_dd_r']:>6.1f} {r['worst_streak']:>6}"
    )

def print_table(title, rows, n=30):
    print(f"\n{'='*W}")
    print(title)
    print(f"{'='*W}")
    print(HEADER)
    print('-' * W)
    for r in rows[:n]:
        print(row(r))

if not results:
    print(f"\nNo combinations produced >= {MIN_TRADES} trades.")
    sys.exit(0)

# ── 1. Top by Total R ────────────────────────────────────────────────────────
results.sort(key=lambda r: r['total_r'], reverse=True)
print_table(f"TOP 30 BY TOTAL R  (out of {len(results)} combos with >= {MIN_TRADES} trades)", results)

# ── 2. Top by Expectancy ─────────────────────────────────────────────────────
results.sort(key=lambda r: r['expectancy'], reverse=True)
print_table("TOP 30 BY EXPECTANCY", results)

# ── 3. Top by Profit Factor ──────────────────────────────────────────────────
results.sort(key=lambda r: r['pf'], reverse=True)
print_table("TOP 20 BY PROFIT FACTOR", results, n=20)

# ── 4. Risk-adjusted (expectancy / max_DD) ──────────────────────────────────
for r in results:
    r['risk_adj'] = r['expectancy'] / r['max_dd_r'] if r['max_dd_r'] > 0 else 0.0
results.sort(key=lambda r: r['risk_adj'], reverse=True)
print_table("TOP 20 BY RISK-ADJUSTED  (expectancy / max_DD)", results, n=20)

# ── 5. multiple_trades_per_bias comparison (top 10 each) ────────────────────
results.sort(key=lambda r: r['expectancy'], reverse=True)
multi  = [r for r in results if     r['multiple_trades_per_bias']]
single = [r for r in results if not r['multiple_trades_per_bias']]
print_table("TOP 10 EXPECTANCY — multiple_trades_per_bias=True",  multi,  n=10)
print_table("TOP 10 EXPECTANCY — multiple_trades_per_bias=False", single, n=10)
print(f"\n{'='*W}")
