"""
Circuit breaker sweep for IMS Reversal.

After N consecutive losses (global, cross-symbol), pause all new signals
for X calendar days. Streak resets to 0 on a win, or when the pause expires.

Sweeps:
  streak_pause_after : [3, 4, 5, 6, 7, 8, 10]
  streak_pause_days  : [3, 5, 7, 10, 14]

Baseline (0, 0) = no circuit breaker, included for comparison.
"""

import io
import contextlib
import logging
import itertools

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

STREAK_THRESHOLDS = [3, 4, 5, 6, 7, 8, 10]
PAUSE_DAYS        = [3, 5, 7, 10, 14]

# ── Load data ──────────────────────────────────────────────────────────────────
print("Loading bar data...")
bars_by_symbol: dict[str, list] = {}
for symbol in SYMBOLS:
    htf = find_csv(symbol, 'H4')
    ltf = find_csv(symbol, 'M15')
    if not htf or not ltf:
        print(f"  {symbol}: SKIPPED")
        continue
    bars_by_symbol[symbol] = load_and_merge(htf + ltf)
    print(f"  {symbol}: {len(bars_by_symbol[symbol]):,} bars")


def _run(pause_after: int, pause_days: int) -> dict | None:
    all_trades: list[dict] = []
    for symbol, bars in bars_by_symbol.items():
        strategy = ImsReversalStrategy(
            **FIXED,
            streak_pause_after=pause_after,
            streak_pause_days=pause_days,
        )
        engine = BacktestEngine(initial_balance=INITIAL_BALANCE, rr_ratio=FIXED['rr_ratio'])
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
# Baseline first
print(f"\nRunning baseline + {len(STREAK_THRESHOLDS) * len(PAUSE_DAYS)} combos...\n")

print("  baseline...", end=' ', flush=True)
base = _run(0, 0)
print(f"{base['n']} trades  exp={base['exp']:+.3f}R  max_dd={base['max_dd']:.1f}R  streak={base['max_streak']}")

results = []
for pause_after, pause_days in itertools.product(STREAK_THRESHOLDS, PAUSE_DAYS):
    label = f"streak≥{pause_after} pause {pause_days}d"
    print(f"  {label}...", end=' ', flush=True)
    r = _run(pause_after, pause_days)
    if r:
        r['pause_after'] = pause_after
        r['pause_days']  = pause_days
        results.append(r)
        print(f"{r['n']} trades  exp={r['exp']:+.3f}R  "
              f"max_dd={r['max_dd']:.1f}R  streak={r['max_streak']}")
    else:
        print("no trades")

# ── Full table ─────────────────────────────────────────────────────────────────
W = 100
print(f"\n{'='*W}")
print("CIRCUIT BREAKER SWEEP — IMS Reversal (H4/M15, 8 symbols, validated params)")
print(f"{'='*W}")
print(f"  {'config':<22}  {'trades':>6}  {'trade%':>7}  {'win%':>6}  "
      f"{'exp':>7}  {'Δexp':>7}  {'total_R':>8}  {'max_dd':>8}  {'Δdd':>7}  "
      f"{'streak':>7}  {'Δstreak':>8}")
print('-' * W)

# Baseline row
print(f"  {'baseline':<22}  {base['n']:>6}  {'100.0%':>7}  {base['wr']:>6.1f}%  "
      f"{base['exp']:>+7.3f}  {'—':>7}  {base['total_r']:>+8.1f}  "
      f"{base['max_dd']:>7.1f}R  {'—':>7}  {base['max_streak']:>7}  {'—':>8}")

for r in results:
    label = f"≥{r['pause_after']} → pause {r['pause_days']}d"
    trade_pct  = r['n'] / base['n'] * 100
    dd_delta   = r['max_dd'] - base['max_dd']
    str_delta  = r['max_streak'] - base['max_streak']
    exp_delta  = r['exp'] - base['exp']
    print(f"  {label:<22}  {r['n']:>6}  {trade_pct:>6.1f}%  {r['wr']:>6.1f}%  "
          f"{r['exp']:>+7.3f}  {exp_delta:>+7.3f}  {r['total_r']:>+8.1f}  "
          f"{r['max_dd']:>7.1f}R  {dd_delta:>+7.1f}  "
          f"{r['max_streak']:>7}  {str_delta:>+8}")

# ── Best trade-off table ───────────────────────────────────────────────────────
print(f"\n{'='*W}")
print("BEST TRADE-OFF  (exp ≥ baseline − 0.015R, ranked by max_dd)")
print(f"{'='*W}")
print(f"  {'config':<22}  {'trades':>6}  {'exp':>7}  {'Δexp':>7}  "
      f"{'max_dd':>8}  {'Δdd':>7}  {'streak':>7}  {'Δstreak':>8}")
print('-' * 75)
candidates = [r for r in results if r['exp'] >= base['exp'] - 0.015]
candidates.sort(key=lambda x: x['max_dd'])
for r in candidates[:15]:
    label = f"≥{r['pause_after']} → pause {r['pause_days']}d"
    print(f"  {label:<22}  {r['n']:>6}  {r['exp']:>+7.3f}  "
          f"{r['exp']-base['exp']:>+7.3f}  {r['max_dd']:>7.1f}R  "
          f"{r['max_dd']-base['max_dd']:>+7.1f}  {r['max_streak']:>7}  "
          f"{r['max_streak']-base['max_streak']:>+8}")

# ── Breakdown by pause_after ───────────────────────────────────────────────────
print(f"\n{'='*W}")
print("STREAK THRESHOLD BREAKDOWN  (best max_dd per pause_after value, any pause_days)")
print(f"{'='*W}")
print(f"  {'pause_after':>11}  {'best pause_days':>15}  {'trades':>6}  "
      f"{'exp':>7}  {'max_dd':>8}  {'Δdd':>7}  {'streak':>7}")
print('-' * 75)
for pa in STREAK_THRESHOLDS:
    group = [r for r in results if r['pause_after'] == pa]
    if not group:
        continue
    best = min(group, key=lambda r: r['max_dd'])
    print(f"  {pa:>11}  {best['pause_days']:>15}d  {best['n']:>6}  "
          f"{best['exp']:>+7.3f}  {best['max_dd']:>7.1f}R  "
          f"{best['max_dd']-base['max_dd']:>+7.1f}  {best['max_streak']:>7}")

# ── Breakdown by pause_days ────────────────────────────────────────────────────
print(f"\n{'='*W}")
print("PAUSE DURATION BREAKDOWN  (best max_dd per pause_days value, any pause_after)")
print(f"{'='*W}")
print(f"  {'pause_days':>10}  {'best pause_after':>16}  {'trades':>6}  "
      f"{'exp':>7}  {'max_dd':>8}  {'Δdd':>7}  {'streak':>7}")
print('-' * 75)
for pd in PAUSE_DAYS:
    group = [r for r in results if r['pause_days'] == pd]
    if not group:
        continue
    best = min(group, key=lambda r: r['max_dd'])
    print(f"  {pd:>10}d  {best['pause_after']:>16}  {best['n']:>6}  "
          f"{best['exp']:>+7.3f}  {best['max_dd']:>7.1f}R  "
          f"{best['max_dd']-base['max_dd']:>+7.1f}  {best['max_streak']:>7}")
