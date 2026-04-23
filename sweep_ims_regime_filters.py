"""
Regime filter comparison sweep for IMS Reversal.

Tests D1 ADX and D1 Efficiency Ratio thresholds head-to-head.
All other params held at the validated H4/M15 config.

Also sweeps ER period (10, 14, 20) since ER is more period-sensitive than ADX.
"""

import io
import contextlib
import logging

import config
from backtest_engine import BacktestEngine
from strategies.ims_reversal import ImsReversalStrategy
from data.historical_loader import find_csv, load_and_merge

logging.basicConfig(level=logging.ERROR)

SYMBOLS         = ['GBPNZD', 'AUDUSD', 'USA30', 'USDCHF', 'XAUUSD', 'AUDJPY', 'AUDCAD', 'USDCAD']
INITIAL_BALANCE = 10_000.0

FIXED = dict(
    tf_htf='H4', tf_ltf='M15',
    fractal_n=1, ltf_fractal_n=2, htf_lookback=30,
    entry_mode='pending', tp_mode='htf_pct', htf_tp_pct=0.5,
    rr_ratio=2.5, zone_pct=0.5, cooldown_bars=0,
    blocked_hours=(*range(0, 12), *range(17, 24)),
    ema_fast=20, ema_slow=50, ema_sep=0.001,
    sl_anchor='swing', sl_buffer_pips=0.0,
    max_losses_per_bias=1,
    pip_sizes={sym: config.PIP_SIZE[sym] for sym in SYMBOLS if sym in config.PIP_SIZE},
)

# ── Filter configs to test ─────────────────────────────────────────────────────
# Each entry: (label, extra_kwargs)
FILTER_CONFIGS = [
    ('baseline',    {}),

    # ADX thresholds (period=14, D1)
    ('adx>20',      dict(adx_period=14, adx_threshold=20,  adx_tf='D1')),
    ('adx>25',      dict(adx_period=14, adx_threshold=25,  adx_tf='D1')),
    ('adx>30',      dict(adx_period=14, adx_threshold=30,  adx_tf='D1')),

    # ER thresholds — period 10
    ('er10>0.2',    dict(er_period=10, er_threshold=0.2,  er_tf='D1')),
    ('er10>0.3',    dict(er_period=10, er_threshold=0.3,  er_tf='D1')),
    ('er10>0.4',    dict(er_period=10, er_threshold=0.4,  er_tf='D1')),
    ('er10>0.5',    dict(er_period=10, er_threshold=0.5,  er_tf='D1')),
    ('er10>0.6',    dict(er_period=10, er_threshold=0.6,  er_tf='D1')),

    # ER thresholds — period 14
    ('er14>0.2',    dict(er_period=14, er_threshold=0.2,  er_tf='D1')),
    ('er14>0.3',    dict(er_period=14, er_threshold=0.3,  er_tf='D1')),
    ('er14>0.4',    dict(er_period=14, er_threshold=0.4,  er_tf='D1')),
    ('er14>0.5',    dict(er_period=14, er_threshold=0.5,  er_tf='D1')),
    ('er14>0.6',    dict(er_period=14, er_threshold=0.6,  er_tf='D1')),

    # ER thresholds — period 20
    ('er20>0.2',    dict(er_period=20, er_threshold=0.2,  er_tf='D1')),
    ('er20>0.3',    dict(er_period=20, er_threshold=0.3,  er_tf='D1')),
    ('er20>0.4',    dict(er_period=20, er_threshold=0.4,  er_tf='D1')),
    ('er20>0.5',    dict(er_period=20, er_threshold=0.5,  er_tf='D1')),
    ('er20>0.6',    dict(er_period=20, er_threshold=0.6,  er_tf='D1')),
]

# ── Load data ──────────────────────────────────────────────────────────────────
print("Loading bar data...")
bars_by_symbol: dict[str, list] = {}
for symbol in SYMBOLS:
    htf = find_csv(symbol, 'H4')
    ltf = find_csv(symbol, 'M15')
    d1  = find_csv(symbol, 'D1')
    if not htf or not ltf:
        print(f"  {symbol}: SKIPPED (no H4/M15)")
        continue
    bars_by_symbol[symbol] = load_and_merge(htf + ltf + (d1 if d1 else []))
    print(f"  {symbol}: {len(bars_by_symbol[symbol]):,} bars"
          + (" + D1" if d1 else " (no D1 — filter will be inactive)"))


def _run_config(extra_kwargs: dict) -> dict | None:
    all_trades: list[dict] = []
    for symbol, bars in bars_by_symbol.items():
        strategy = ImsReversalStrategy(**FIXED, **extra_kwargs)
        engine   = BacktestEngine(initial_balance=INITIAL_BALANCE, rr_ratio=FIXED['rr_ratio'])
        engine.add_strategy(strategy, symbols=[symbol])
        with contextlib.redirect_stdout(io.StringIO()):
            for bar in bars:
                closed = engine.execution.check_fills(bar)
                for trade in closed:
                    engine.portfolio.record_close(
                        trade['symbol'], trade['pnl'], trade.get('strategy_name', ''))
                    engine.trade_logger.log_close(trade['ticket'], trade)
                    engine.event_engine.notify_trade_closed(trade)
                engine.event_engine.process_bar(bar)
        all_trades.extend(engine.execution.get_closed_trades())

    if not all_trades:
        return None

    all_trades.sort(key=lambda t: t['close_time'])
    n       = len(all_trades)
    wins    = sum(1 for t in all_trades if t['result'] == 'WIN')
    total_r = sum(t['r_multiple'] for t in all_trades)

    equity = peak = max_dd = streak = max_streak = 0.0
    for t in all_trades:
        equity += t['r_multiple']
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd
        if t['result'] == 'LOSS':
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0

    return dict(n=n, wr=wins/n*100, total_r=total_r, exp=total_r/n,
                max_dd=max_dd, max_streak=int(max_streak))


# ── Run ────────────────────────────────────────────────────────────────────────
print(f"\nRunning {len(FILTER_CONFIGS)} configs...\n")
results = []
for label, kwargs in FILTER_CONFIGS:
    print(f"  {label:<14}...", end=' ', flush=True)
    r = _run_config(kwargs)
    if r:
        results.append((label, r))
        print(f"{r['n']:>5} trades  exp={r['exp']:+.3f}R  "
              f"max_dd={r['max_dd']:.1f}R  streak={r['max_streak']}")
    else:
        print("no trades")

# ── Table ──────────────────────────────────────────────────────────────────────
if not results:
    print("No results.")
    raise SystemExit

base_n, base_r, base_exp, base_dd, base_streak = (
    results[0][1]['n'], results[0][1]['total_r'],
    results[0][1]['exp'], results[0][1]['max_dd'], results[0][1]['max_streak'],
)

W = 95
print(f"\n{'='*W}")
print("REGIME FILTER COMPARISON — IMS Reversal (H4/M15, 8 symbols, validated params)")
print(f"{'='*W}")
print(f"  {'filter':<14}  {'trades':>6}  {'trade%':>7}  "
      f"{'win%':>6}  {'exp':>7}  {'total_R':>8}  "
      f"{'max_dd':>8}  {'Δdd':>7}  {'streak':>7}  {'Δstreak':>8}")
print('-' * W)

for label, r in results:
    trade_pct  = r['n'] / base_n * 100
    dd_delta   = r['max_dd']     - base_dd
    str_delta  = r['max_streak'] - base_streak
    print(f"  {label:<14}  {r['n']:>6}  {trade_pct:>6.1f}%  "
          f"{r['wr']:>6.1f}%  {r['exp']:>+7.3f}  {r['total_r']:>+8.1f}  "
          f"{r['max_dd']:>7.1f}R  {dd_delta:>+7.1f}  "
          f"{r['max_streak']:>7}  {str_delta:>+8}")

print()
print("  Δdd and Δstreak are vs baseline (positive = worse, negative = better)")

# ── Best trade-off ─────────────────────────────────────────────────────────────
# Score: maximise (exp_improvement * trade_retention) / dd_reduction_needed
# Simple ranking: sort by max_dd improvement weighted by expectancy retention
print(f"\n{'='*W}")
print("BEST TRADE-OFF  (ranked by: max_dd reduction, filtered to exp ≥ baseline − 0.020R)")
print(f"{'='*W}")
candidates = [
    (label, r) for label, r in results[1:]
    if r['exp'] >= base_exp - 0.020
]
candidates.sort(key=lambda x: x[1]['max_dd'])
print(f"  {'filter':<14}  {'trades':>6}  {'exp':>7}  {'Δexp':>7}  "
      f"{'max_dd':>8}  {'Δdd':>7}  {'streak':>7}  {'Δstreak':>8}")
print('-' * 75)
for label, r in candidates:
    print(f"  {label:<14}  {r['n']:>6}  {r['exp']:>+7.3f}  "
          f"{r['exp']-base_exp:>+7.3f}  {r['max_dd']:>7.1f}R  "
          f"{r['max_dd']-base_dd:>+7.1f}  {r['max_streak']:>7}  "
          f"{r['max_streak']-base_streak:>+8}")
