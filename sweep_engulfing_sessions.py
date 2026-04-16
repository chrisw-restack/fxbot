"""
Session × Symbol sweep for the Engulfing (ThreeLineStrike) strategy.

All structural params are fixed at walk-forward validated values.
Only the session window and symbol are varied.

Sessions tested (6):
  NY core     — 13–17 UTC  (current live config)
  NY open     — 13–15 UTC
  NY extended — 13–20 UTC
  London core — 08–12 UTC
  London open — 07–10 UTC
  London+NY   — 08–17 UTC

Symbols (7): AUDUSD, EURUSD, GBPUSD, NZDUSD, USDCAD, USDCHF, USDJPY

Output: a 7×6 grid — symbol × session — showing expectancy (trades).
"""

import io
import contextlib
import logging
import sys

from backtest_engine import BacktestEngine
from strategies.three_line_strike import ThreeLineStrikeStrategy
from data.historical_loader import find_csv, load_and_merge

logging.basicConfig(level=logging.ERROR)
sys.stdout.reconfigure(line_buffering=True)

SYMBOLS = ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDCAD', 'USDCHF', 'USDJPY']
INITIAL_BALANCE = 10_000.0
RR_RATIO = 2.5

# Fixed validated params
FIXED = dict(
    sl_mode='fractal',
    fractal_n=3,
    min_prev_body_pips=3.0,
    engulf_ratio=1.5,
    max_sl_pips=15,
    sma_sep_pips=5.0,
    pip_sizes={'USDJPY': 0.01},
)

# Session windows: label → allowed_hours tuple
SESSIONS = {
    'NY core':     tuple(range(13, 18)),   # 13,14,15,16,17
    'NY open':     tuple(range(13, 16)),   # 13,14,15
    'NY extended': tuple(range(13, 21)),   # 13–20
    'London core': tuple(range(8,  13)),   # 8,9,10,11,12
    'London open': tuple(range(7,  11)),   # 7,8,9,10
    'London+NY':   tuple(range(8,  18)),   # 8–17
}

SESSION_LABELS = list(SESSIONS.keys())

# ── Pre-load all M5 bar data ─────────────────────────────────────────────────
print("Loading M5 bar data...")
csv_paths = []
for symbol in SYMBOLS:
    csv_paths.extend(find_csv(symbol, 'M5'))

if not csv_paths:
    print("No M5 CSV files found.")
    sys.exit(1)

all_bars = load_and_merge(csv_paths)
print(f"Loaded {len(all_bars):,} bars across {len(SYMBOLS)} symbols\n")

# Pre-bucket bars by symbol for fast single-symbol runs
bars_by_symbol: dict[str, list] = {s: [] for s in SYMBOLS}
for bar in all_bars:
    if bar.symbol in bars_by_symbol:
        bars_by_symbol[bar.symbol].append(bar)


def run_one(symbol: str, session_label: str, allowed_hours: tuple) -> dict:
    """Run a single (symbol, session) backtest and return result dict."""
    strategy = ThreeLineStrikeStrategy(
        allowed_hours=allowed_hours,
        **FIXED,
    )
    engine = BacktestEngine(initial_balance=INITIAL_BALANCE, rr_ratio=RR_RATIO)
    engine.add_strategy(strategy, symbols=[symbol])

    bars = bars_by_symbol[symbol]
    with contextlib.redirect_stdout(io.StringIO()):
        for bar in bars:
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
    if n == 0:
        return {'symbol': symbol, 'session': session_label, 'trades': 0,
                'expectancy': None, 'win_rate': None, 'total_r': None, 'pf': None}

    wins   = sum(1 for t in trades if t['result'] == 'WIN')
    total_r = sum(t['r_multiple'] for t in trades)
    gp = sum(t['r_multiple'] for t in trades if t['result'] == 'WIN')
    gl = abs(sum(t['r_multiple'] for t in trades if t['result'] == 'LOSS'))
    pf = gp / gl if gl > 0 else 0.0

    return {
        'symbol':     symbol,
        'session':    session_label,
        'trades':     n,
        'win_rate':   wins / n * 100,
        'total_r':    total_r,
        'pf':         pf,
        'expectancy': total_r / n,
    }


# ── Run all 42 combinations ───────────────────────────────────────────────────
total = len(SYMBOLS) * len(SESSIONS)
print(f"Running {total} combinations (7 symbols × {len(SESSIONS)} sessions)...\n")

results = {}   # (symbol, session) → result dict
done = 0

for symbol in SYMBOLS:
    for label, hours in SESSIONS.items():
        r = run_one(symbol, label, hours)
        results[(symbol, label)] = r
        done += 1
        tag = f"+{r['expectancy']:+.3f}R/{r['trades']}t" if r['trades'] else "—"
        print(f"  [{done:2d}/{total}]  {symbol:<8}  {label:<14}  {tag}")


# ── Summary grid: symbol × session ───────────────────────────────────────────
COL_W = 18   # width per session column

def cell(r) -> str:
    if r['trades'] == 0:
        return '  —'.ljust(COL_W)
    sign = '+' if r['expectancy'] >= 0 else ''
    return f"  {sign}{r['expectancy']:.3f}R ({r['trades']})".ljust(COL_W)

def cell_r(r) -> str:
    if r['trades'] == 0:
        return '  —'.ljust(COL_W)
    sign = '+' if r['total_r'] >= 0 else ''
    return f"  {sign}{r['total_r']:.1f}R ({r['trades']})".ljust(COL_W)

LINE_W = 12 + COL_W * len(SESSION_LABELS)
DIVIDER = '─' * LINE_W

print(f"\n\n{'═' * LINE_W}")
print("EXPECTANCY GRID  (expectancy per trade / trade count)")
print(f"Fixed: sl=fractal, fn=3, body=3, ratio=1.5, sl_max=15, sma_sep=5, rr=2.5")
print(f"{'═' * LINE_W}")
header = f"{'Symbol':<12}" + ''.join(f"{lbl:<{COL_W}}" for lbl in SESSION_LABELS)
print(header)
print(DIVIDER)

for symbol in SYMBOLS:
    row = f"{symbol:<12}"
    for label in SESSION_LABELS:
        row += cell(results[(symbol, label)])
    print(row)

print(DIVIDER)

# Per-session totals (all-symbol combined)
print(f"{'ALL SYM':<12}", end='')
for label in SESSION_LABELS:
    combined = [results[(s, label)] for s in SYMBOLS if results[(s, label)]['trades'] > 0]
    if not combined:
        print('  —'.ljust(COL_W), end='')
        continue
    total_trades = sum(r['trades'] for r in combined)
    total_r_sum  = sum(r['total_r'] for r in combined)
    exp = total_r_sum / total_trades
    sign = '+' if exp >= 0 else ''
    print(f"  {sign}{exp:.3f}R ({total_trades})".ljust(COL_W), end='')
print()

print(f"\n\n{'═' * LINE_W}")
print("TOTAL R GRID  (total R / trade count)")
print(f"{'═' * LINE_W}")
print(header)
print(DIVIDER)

for symbol in SYMBOLS:
    row = f"{symbol:<12}"
    for label in SESSION_LABELS:
        row += cell_r(results[(symbol, label)])
    print(row)

print(DIVIDER)

print(f"{'ALL SYM':<12}", end='')
for label in SESSION_LABELS:
    combined = [results[(s, label)] for s in SYMBOLS if results[(s, label)]['trades'] > 0]
    if not combined:
        print('  —'.ljust(COL_W), end='')
        continue
    total_r_sum = sum(r['total_r'] for r in combined)
    total_trades = sum(r['trades'] for r in combined)
    sign = '+' if total_r_sum >= 0 else ''
    print(f"  {sign}{total_r_sum:.1f}R ({total_trades})".ljust(COL_W), end='')
print()


# ── Per-symbol summary across all sessions ────────────────────────────────────
print(f"\n\n{'═' * 70}")
print("PER-SYMBOL SUMMARY  (best session highlighted)")
print(f"{'═' * 70}")
print(f"{'Symbol':<10} {'Best Session':<16} {'Best Exp':>9} {'Best TotR':>10} "
      f"{'NY core Exp':>12} {'NY core T':>9}")
print('─' * 70)

for symbol in SYMBOLS:
    sym_results = [(label, results[(symbol, label)]) for label in SESSION_LABELS
                   if results[(symbol, label)]['trades'] > 0]
    if not sym_results:
        print(f"{symbol:<10} —")
        continue

    best_label, best = max(sym_results, key=lambda x: x[1]['expectancy'])
    ny_r = results[(symbol, 'NY core')]
    ny_exp_str = f"{ny_r['expectancy']:+.3f}R" if ny_r['trades'] else '—'
    ny_t_str   = str(ny_r['trades']) if ny_r['trades'] else '—'

    marker = ' ◄ current' if best_label == 'NY core' else ''
    print(f"{symbol:<10} {best_label:<16} {best['expectancy']:>+9.3f}R "
          f"{best['total_r']:>+10.1f}R  {ny_exp_str:>11}  {ny_t_str:>9}{marker}")

print(f"{'═' * 70}")


# ── USDJPY deep dive ─────────────────────────────────────────────────────────
print(f"\n\n{'═' * 60}")
print("USDJPY SESSION BREAKDOWN")
print(f"{'═' * 60}")
print(f"{'Session':<16} {'Trades':>7} {'WR%':>6} {'TotalR':>8} {'Expect':>8} {'PF':>6}")
print('─' * 60)

for label in SESSION_LABELS:
    r = results[('USDJPY', label)]
    if r['trades'] == 0:
        print(f"{label:<16} {'0':>7} {'—':>6} {'—':>8} {'—':>8} {'—':>6}")
    else:
        print(f"{label:<16} {r['trades']:>7} {r['win_rate']:>5.1f}% "
              f"{r['total_r']:>+8.1f}R {r['expectancy']:>+8.3f}R {r['pf']:>6.2f}")

print(f"{'═' * 60}")
