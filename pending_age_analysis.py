"""
Pending order age analysis for EmaFibRetracement.

Bins filled trades by how long the pending order sat before being filled,
then shows win rate, expectancy, and total R per bucket.

Goal: identify whether old pending orders are lower probability and
whether an order expiry parameter would improve performance.
"""

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
RR_RATIO = 2.0

# Current live config
strategy = EmaFibRetracementStrategy(
    fib_entry=0.786, fib_tp=3.0, fractal_n=3, min_swing_pips=10,
    ema_sep_pct=0.001, cooldown_bars=10, invalidate_swing_on_loss=True,
    blocked_hours=(*range(20, 24), *range(0, 9)),
)

print("Loading bar data...")
csv_paths = []
for symbol in SYMBOLS:
    for tf in ['D1', 'H1']:
        csv_paths.extend(find_csv(symbol, tf))
all_bars = load_and_merge(csv_paths)
print(f"Loaded {len(all_bars):,} bars\n")

engine = BacktestEngine(initial_balance=INITIAL_BALANCE, rr_ratio=RR_RATIO)
engine.add_strategy(strategy, symbols=SYMBOLS)

with contextlib.redirect_stdout(io.StringIO()):
    for bar in all_bars:
        closed = engine.execution.check_fills(bar)
        for trade in closed:
            engine.portfolio.record_close(trade['symbol'], trade['pnl'], trade.get('strategy_name', ''))
            engine.trade_logger.log_close(trade['ticket'], trade)
            engine.event_engine.notify_trade_closed(trade)
        engine.event_engine.process_bar(bar)

trades = engine.execution.get_closed_trades()
print(f"Total trades: {len(trades)}")

# ── Separate trades with pending_hours from market orders ───────────────────
pending_trades = [t for t in trades if t.get('pending_hours') is not None]
market_trades  = [t for t in trades if t.get('pending_hours') is None]
print(f"Pending fills: {len(pending_trades)}   Market fills: {len(market_trades)}\n")

# ── Age buckets (hours) ──────────────────────────────────────────────────────
BUCKETS = [
    (0,    24,   '0–1 day'),
    (24,   48,   '1–2 days'),
    (48,   72,   '2–3 days'),
    (72,   120,  '3–5 days'),
    (120,  240,  '5–10 days'),
    (240,  480,  '10–20 days'),
    (480,  float('inf'), '20+ days'),
]

def bucket_stats(bucket_trades):
    n = len(bucket_trades)
    if n == 0:
        return None
    wins   = [t for t in bucket_trades if t['result'] == 'WIN']
    losses = [t for t in bucket_trades if t['result'] == 'LOSS']
    bes    = [t for t in bucket_trades if t['result'] == 'BE']
    total_r = sum(t['r_multiple'] for t in bucket_trades)
    gp = sum(t['r_multiple'] for t in wins)
    gl = abs(sum(t['r_multiple'] for t in losses))
    pf = gp / gl if gl > 0 else 0.0
    avg_win = gp / len(wins) if wins else 0.0
    return {
        'n': n, 'wins': len(wins), 'losses': len(losses), 'bes': len(bes),
        'wr': len(wins) / n * 100,
        'total_r': total_r,
        'expect': total_r / n,
        'pf': pf,
        'avg_win': avg_win,
    }

# ── Main table ───────────────────────────────────────────────────────────────
W = 110
print('=' * W)
print(f"{'PENDING AGE vs OUTCOME  (EmaFibRetracement, 7 pairs, 2016–2026)':^{W}}")
print('=' * W)
print(f"{'Age bucket':<14} {'Trades':>6} {'Wins':>5} {'Loss':>5} {'BE':>4} "
      f"{'WR%':>6} {'Total R':>8} {'Expect':>7} {'PF':>6} {'Avg Win':>8}")
print('-' * W)

cumulative = []
for lo, hi, label in BUCKETS:
    bucket = [t for t in pending_trades if lo <= t['pending_hours'] < hi]
    s = bucket_stats(bucket)
    if s is None:
        print(f"  {label:<12} {'—':>6}")
        continue
    print(f"  {label:<12} {s['n']:>6} {s['wins']:>5} {s['losses']:>5} {s['bes']:>4} "
          f"{s['wr']:>5.1f}% {s['total_r']:>+8.1f} {s['expect']:>+7.3f} "
          f"{s['pf']:>6.2f} {s['avg_win']:>+8.2f}")
    cumulative.append((label, s))

# All pending combined
s_all = bucket_stats(pending_trades)
print('-' * W)
print(f"  {'ALL PENDING':<12} {s_all['n']:>6} {s_all['wins']:>5} {s_all['losses']:>5} {s_all['bes']:>4} "
      f"{s_all['wr']:>5.1f}% {s_all['total_r']:>+8.1f} {s_all['expect']:>+7.3f} "
      f"{s_all['pf']:>6.2f} {s_all['avg_win']:>+8.2f}")

# ── Cumulative "keep orders younger than N" simulation ───────────────────────
print(f"\n{'=' * W}")
print(f"{'CUMULATIVE: KEEP ORDERS UP TO AGE X  (what if we cancelled after N days?)':^{W}}")
print('=' * W)
print(f"{'Max age kept':<16} {'Trades':>6} {'Wins':>5} {'Loss':>5} "
      f"{'WR%':>6} {'Total R':>8} {'Expect':>7} {'PF':>6} {'Cancelled':>10}")
print('-' * W)

thresholds_hours = [24, 48, 72, 120, 240, 480]
for thresh in thresholds_hours:
    kept      = [t for t in pending_trades if t['pending_hours'] < thresh]
    cancelled = len(pending_trades) - len(kept)
    s = bucket_stats(kept)
    if s is None:
        continue
    days = thresh // 24
    label = f'< {days}d'
    print(f"  {label:<14} {s['n']:>6} {s['wins']:>5} {s['losses']:>5} "
          f"{s['wr']:>5.1f}% {s['total_r']:>+8.1f} {s['expect']:>+7.3f} "
          f"{s['pf']:>6.2f} {cancelled:>10}")

# Baseline (no expiry)
print(f"  {'No expiry':<14} {s_all['n']:>6} {s_all['wins']:>5} {s_all['losses']:>5} "
      f"{s_all['wr']:>5.1f}% {s_all['total_r']:>+8.1f} {s_all['expect']:>+7.3f} "
      f"{s_all['pf']:>6.2f} {'0':>10}")

# ── Per-symbol breakdown by age ──────────────────────────────────────────────
print(f"\n{'=' * W}")
print("PER-SYMBOL PENDING AGE DISTRIBUTION")
print('=' * W)
print(f"{'Symbol':<10} {'<1d':>5} {'1–2d':>5} {'2–3d':>5} {'3–5d':>5} "
      f"{'5–10d':>6} {'10–20d':>7} {'20+d':>6} {'Total':>6}")
print('-' * W)
for sym in SYMBOLS:
    sym_trades = [t for t in pending_trades if t['symbol'] == sym]
    counts = []
    for lo, hi, _ in BUCKETS:
        counts.append(len([t for t in sym_trades if lo <= t['pending_hours'] < hi]))
    print(f"  {sym:<8} " + "  ".join(f"{c:>4}" for c in counts) + f"  {len(sym_trades):>5}")

# ── Distribution of pending hours ───────────────────────────────────────────
print(f"\n{'=' * W}")
print("PENDING HOURS DISTRIBUTION (histogram)")
print('=' * W)
all_hours = sorted(t['pending_hours'] for t in pending_trades)
if all_hours:
    print(f"  Min: {all_hours[0]:.0f}h   "
          f"Median: {all_hours[len(all_hours)//2]:.0f}h   "
          f"p75: {all_hours[int(len(all_hours)*0.75)]:.0f}h   "
          f"p90: {all_hours[int(len(all_hours)*0.90)]:.0f}h   "
          f"Max: {all_hours[-1]:.0f}h  "
          f"({all_hours[-1]/24:.0f} days)")
