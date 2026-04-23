"""
Focused sweep of the D1 ADX threshold for IMS Reversal.

Holds all other params fixed at the validated H4/M15 config and sweeps only
adx_threshold to find the value that best reduces max drawdown / loss streaks
without meaningfully hurting expectancy.

adx_threshold=0 is the baseline (no filter), included for direct comparison.
"""

import io
import contextlib
import logging

import config
from backtest_engine import BacktestEngine
from strategies.ims_reversal import ImsReversalStrategy
from data.historical_loader import find_csv, load_and_merge

logging.basicConfig(level=logging.ERROR)

SYMBOLS = ['GBPNZD', 'AUDUSD', 'USA30', 'USDCHF', 'XAUUSD', 'AUDJPY', 'AUDCAD', 'USDCAD']
INITIAL_BALANCE = 10_000.0
ADX_THRESHOLDS  = [0, 20, 25, 30, 35, 40]   # 0 = disabled (baseline)
ADX_PERIOD      = 14
ADX_TF          = 'D1'

# Validated fixed params
FIXED = dict(
    tf_htf='H4', tf_ltf='M15',
    fractal_n=1, ltf_fractal_n=2, htf_lookback=30,
    entry_mode='pending', tp_mode='htf_pct', htf_tp_pct=0.5,
    rr_ratio=2.5, zone_pct=0.5,
    cooldown_bars=0,
    blocked_hours=(*range(0, 12), *range(17, 24)),
    ema_fast=20, ema_slow=50, ema_sep=0.001,
    sl_anchor='swing', sl_buffer_pips=0.0,
    max_losses_per_bias=1,
    adx_period=ADX_PERIOD,
    adx_tf=ADX_TF,
    pip_sizes={sym: config.PIP_SIZE[sym] for sym in SYMBOLS if sym in config.PIP_SIZE},
)

# ── Load data ─────────────────────────────────────────────────────────────────
print("Loading bar data...")
bars_by_symbol: dict[str, list] = {}
for symbol in SYMBOLS:
    htf_paths = find_csv(symbol, 'H4')
    ltf_paths = find_csv(symbol, 'M15')
    d1_paths  = find_csv(symbol, 'D1')
    if not htf_paths or not ltf_paths:
        print(f"  {symbol}: SKIPPED (no H4/M15 data)")
        continue
    all_paths = htf_paths + ltf_paths + (d1_paths if d1_paths else [])
    bars_by_symbol[symbol] = load_and_merge(all_paths)
    d1_note = f" + D1({len(d1_paths)} file{'s' if len(d1_paths)>1 else ''})" if d1_paths else " (no D1)"
    print(f"  {symbol}: {len(bars_by_symbol[symbol]):,} bars{d1_note}")


def _run_threshold(threshold: float) -> dict:
    """Run backtest for all 8 symbols at a given ADX threshold. Returns aggregate stats."""
    all_trades: list[dict] = []

    for symbol, bars in bars_by_symbol.items():
        strategy = ImsReversalStrategy(**FIXED, adx_threshold=threshold)
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
        return {}

    all_trades.sort(key=lambda t: t['close_time'])

    n        = len(all_trades)
    wins     = sum(1 for t in all_trades if t['result'] == 'WIN')
    total_r  = sum(t['r_multiple'] for t in all_trades)
    exp      = total_r / n

    # Rolling equity (in R) for max drawdown and loss streak
    equity = 0.0
    peak   = 0.0
    max_dd = 0.0
    streak = 0
    max_streak = 0

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

    return {
        'threshold': threshold,
        'trades':    n,
        'win_rate':  wins / n * 100,
        'total_r':   total_r,
        'exp':       exp,
        'max_dd':    max_dd,
        'max_streak': max_streak,
        'trades_pct': None,   # filled in after baseline is known
    }


# ── Run all thresholds ────────────────────────────────────────────────────────
print(f"\nRunning {len(ADX_THRESHOLDS)} thresholds × {len(bars_by_symbol)} symbols...\n")

results = []
for thresh in ADX_THRESHOLDS:
    label = f"adx>{thresh}" if thresh > 0 else "no filter"
    print(f"  threshold={thresh:>2}  ({label})...", end=' ', flush=True)
    r = _run_threshold(thresh)
    if r:
        results.append(r)
        print(f"{r['trades']} trades  exp={r['exp']:+.3f}R  "
              f"max_dd={r['max_dd']:.1f}R  streak={r['max_streak']}")
    else:
        print("no trades")

# Fill trades_pct vs baseline
if results:
    baseline_trades = results[0]['trades']
    baseline_r      = results[0]['total_r']
    for r in results:
        r['trades_pct'] = r['trades'] / baseline_trades * 100
        r['r_pct']      = r['total_r'] / baseline_r * 100 if baseline_r else 0

# ── Summary table ─────────────────────────────────────────────────────────────
W = 90
print(f"\n{'='*W}")
print("D1 ADX THRESHOLD SWEEP — IMS Reversal (H4/M15, 8 symbols, validated params)")
print(f"{'='*W}")
print(f"  {'threshold':>10}  {'trades':>7}  {'trade%':>7}  "
      f"{'win%':>6}  {'exp':>7}  {'total_R':>8}  {'R%':>6}  "
      f"{'max_dd':>8}  {'max_streak':>10}")
print('-' * W)
for r in results:
    thresh_label = f"adx>{r['threshold']}" if r['threshold'] > 0 else "none (base)"
    print(f"  {thresh_label:>10}  {r['trades']:>7}  {r['trades_pct']:>6.1f}%  "
          f"{r['win_rate']:>6.1f}%  {r['exp']:>+7.3f}  {r['total_r']:>+8.1f}  {r['r_pct']:>5.1f}%  "
          f"{r['max_dd']:>8.1f}R  {r['max_streak']:>10}")

print()
if len(results) > 1:
    base = results[0]
    print("  Change vs baseline (no filter):")
    for r in results[1:]:
        dd_delta     = r['max_dd']     - base['max_dd']
        streak_delta = r['max_streak'] - base['max_streak']
        exp_delta    = r['exp']        - base['exp']
        trade_delta  = r['trades']     - base['trades']
        print(f"    adx>{r['threshold']:>2}: "
              f"trades {trade_delta:+d} ({r['trades_pct']-100:+.1f}%)  "
              f"exp {exp_delta:+.3f}R  "
              f"max_dd {dd_delta:+.1f}R  "
              f"streak {streak_delta:+d}")
