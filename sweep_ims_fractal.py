"""
Fractal size sweep for IMS Reversal.

Sweeps fractal_n (HTF H4 swing points) and ltf_fractal_n (LTF M15 swing points)
independently and in combination. All other params fixed at validated config.

fractal_n=N means each confirmed swing needs N bars each side that are lower/higher.
  N=1 → 3-bar fractal (minimal confirmation)
  N=2 → 5-bar fractal
  N=3 → 7-bar fractal (strong structural confirmation)

Validated baseline: fractal_n=1, ltf_fractal_n=2

Reports: trades, win%, expectancy, total_R, max_dd, worst_streak per combo.
Also per-symbol breakdown for the most promising combos.
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
    htf_lookback=30,
    entry_mode='pending', tp_mode='htf_pct', htf_tp_pct=0.5,
    rr_ratio=2.5, zone_pct=0.5, cooldown_bars=0,
    blocked_hours=(*range(0, 12), *range(17, 24)),
    ema_fast=20, ema_slow=50, ema_sep=0.001,
    sl_anchor='swing', sl_buffer_pips=0.0,
    max_losses_per_bias=1,
    pip_sizes={sym: config.PIP_SIZE[sym] for sym in SYMBOLS if sym in config.PIP_SIZE},
)

HTF_FRACTALS = [1, 2, 3]   # fractal_n — H4 swing confirmation
LTF_FRACTALS = [1, 2, 3]   # ltf_fractal_n — M15 swing confirmation
BASELINE = (1, 2)           # currently validated

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


def _run_combo(fn: int, lfn: int) -> tuple[dict, dict]:
    """Returns (aggregate_stats, per_symbol_stats)."""
    all_trades: list[dict] = []
    per_sym: dict[str, dict] = {}

    for symbol, bars in bars_by_symbol.items():
        strategy = ImsReversalStrategy(**FIXED, fractal_n=fn, ltf_fractal_n=lfn)
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

        trades = engine.execution.get_closed_trades()
        all_trades.extend(trades)

        if trades:
            sym_r = sum(t['r_multiple'] for t in trades)
            sym_w = sum(1 for t in trades if t['result'] == 'WIN')
            per_sym[symbol] = dict(
                n=len(trades), wr=sym_w/len(trades)*100,
                exp=sym_r/len(trades), total_r=sym_r,
            )

    if not all_trades:
        return {}, per_sym

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
                max_dd=max_dd, max_streak=int(max_streak)), per_sym


# ── Run all combos ─────────────────────────────────────────────────────────────
combos = list(itertools.product(HTF_FRACTALS, LTF_FRACTALS))
print(f"\nRunning {len(combos)} combos × {len(bars_by_symbol)} symbols...\n")

results = []
per_sym_all = {}
for fn, lfn in combos:
    label = f"htf{fn}/ltf{lfn}"
    marker = " ← baseline" if (fn, lfn) == BASELINE else ""
    print(f"  {label}...", end=' ', flush=True)
    agg, per_sym = _run_combo(fn, lfn)
    if agg:
        results.append(dict(fn=fn, lfn=lfn, label=label, **agg))
        per_sym_all[(fn, lfn)] = per_sym
        print(f"{agg['n']:>5} trades  exp={agg['exp']:+.3f}R  "
              f"max_dd={agg['max_dd']:.1f}R  streak={agg['max_streak']}{marker}")
    else:
        print("no trades")

if not results:
    raise SystemExit("No results.")

base = next((r for r in results if r['fn'] == BASELINE[0] and r['lfn'] == BASELINE[1]), results[0])

# ── Main table ─────────────────────────────────────────────────────────────────
W = 100
print(f"\n{'='*W}")
print("FRACTAL SIZE SWEEP — IMS Reversal (H4/M15, 8 symbols, validated params)")
print(f"  fractal_n = bars each side of H4 swing point  |  ltf_fractal_n = bars each side of M15 swing")
print(f"{'='*W}")
print(f"  {'combo':<12}  {'trades':>6}  {'trade%':>7}  {'win%':>6}  "
      f"{'exp':>7}  {'Δexp':>7}  {'total_R':>8}  "
      f"{'max_dd':>8}  {'Δdd':>7}  {'streak':>7}  {'Δstreak':>8}")
print('-' * W)

results_sorted = sorted(results, key=lambda r: (r['fn'], r['lfn']))
for r in results_sorted:
    is_base = (r['fn'], r['lfn']) == BASELINE
    trade_pct = r['n'] / base['n'] * 100
    dd_delta  = r['max_dd']     - base['max_dd']
    st_delta  = r['max_streak'] - base['max_streak']
    exp_delta = r['exp']        - base['exp']
    marker = " *" if is_base else ""
    print(f"  {r['label']+marker:<12}  {r['n']:>6}  {trade_pct:>6.1f}%  {r['wr']:>6.1f}%  "
          f"{r['exp']:>+7.3f}  {exp_delta:>+7.3f}  {r['total_r']:>+8.1f}  "
          f"{r['max_dd']:>7.1f}R  {dd_delta:>+7.1f}  "
          f"{r['max_streak']:>7}  {st_delta:>+8}")

print(f"\n  * = validated baseline")

# ── HTF fractal breakdown (best ltf per htf level) ────────────────────────────
print(f"\n{'='*W}")
print("HTF FRACTAL BREAKDOWN  (effect of increasing H4 swing confirmation)")
print(f"  Each row shows the best ltf_fractal_n for that htf fractal level")
print(f"{'='*W}")
print(f"  {'htf_fn':>6}  {'best ltf':>8}  {'trades':>6}  {'exp':>7}  "
      f"{'Δexp':>7}  {'max_dd':>8}  {'Δdd':>7}  {'streak':>7}  {'Δstreak':>8}")
print('-' * 75)
for fn in HTF_FRACTALS:
    group = [r for r in results if r['fn'] == fn]
    best  = min(group, key=lambda r: r['max_dd'])   # best = lowest max_dd
    print(f"  {fn:>6}  {best['lfn']:>8}  {best['n']:>6}  {best['exp']:>+7.3f}  "
          f"{best['exp']-base['exp']:>+7.3f}  {best['max_dd']:>7.1f}R  "
          f"{best['max_dd']-base['max_dd']:>+7.1f}  {best['max_streak']:>7}  "
          f"{best['max_streak']-base['max_streak']:>+8}")

# ── LTF fractal breakdown (best htf per ltf level) ────────────────────────────
print(f"\n{'='*W}")
print("LTF FRACTAL BREAKDOWN  (effect of increasing M15 swing confirmation)")
print(f"  Each row shows the best htf_fractal_n for that ltf fractal level")
print(f"{'='*W}")
print(f"  {'ltf_fn':>6}  {'best htf':>8}  {'trades':>6}  {'exp':>7}  "
      f"{'Δexp':>7}  {'max_dd':>8}  {'Δdd':>7}  {'streak':>7}  {'Δstreak':>8}")
print('-' * 75)
for lfn in LTF_FRACTALS:
    group = [r for r in results if r['lfn'] == lfn]
    best  = min(group, key=lambda r: r['max_dd'])
    print(f"  {lfn:>6}  {best['fn']:>8}  {best['n']:>6}  {best['exp']:>+7.3f}  "
          f"{best['exp']-base['exp']:>+7.3f}  {best['max_dd']:>7.1f}R  "
          f"{best['max_dd']-base['max_dd']:>+7.1f}  {best['max_streak']:>7}  "
          f"{best['max_streak']-base['max_streak']:>+8}")

# ── Per-symbol table for best non-baseline combo and baseline ──────────────────
best_non_base = min(
    (r for r in results if (r['fn'], r['lfn']) != BASELINE),
    key=lambda r: r['max_dd'],
)
print(f"\n{'='*W}")
print(f"PER-SYMBOL COMPARISON: baseline {base['label']} vs best alternative {best_non_base['label']}")
print(f"{'='*W}")
print(f"  {'symbol':<10}  "
      f"{'base trades':>12}  {'base exp':>9}  {'base dd':>8}  "
      f"{'alt trades':>11}  {'alt exp':>8}  {'Δexp':>7}")
print('-' * 80)
base_sym  = per_sym_all.get(BASELINE, {})
alt_sym   = per_sym_all.get((best_non_base['fn'], best_non_base['lfn']), {})
for sym in SYMBOLS:
    bd = base_sym.get(sym)
    ad = alt_sym.get(sym)
    bt = f"{bd['n']}t / {bd['exp']:+.3f}R" if bd else "—"
    at = f"{ad['n']}t / {ad['exp']:+.3f}R" if ad else "—"
    de = f"{ad['exp']-bd['exp']:+.3f}" if (bd and ad) else "—"
    print(f"  {sym:<10}  {bt:>20}  {'':>9}  {'':>8}  {at:>19}  {de:>7}")

# ── Best trade-off ranked by max_dd (exp ≥ baseline − 0.020R) ─────────────────
print(f"\n{'='*W}")
print(f"BEST TRADE-OFF  (exp ≥ baseline − 0.020R, ranked by max_dd)")
print(f"{'='*W}")
print(f"  {'combo':<12}  {'trades':>6}  {'exp':>7}  {'Δexp':>7}  "
      f"{'max_dd':>8}  {'Δdd':>7}  {'streak':>7}  {'Δstreak':>8}")
print('-' * 75)
candidates = [r for r in results if r['exp'] >= base['exp'] - 0.020]
candidates.sort(key=lambda r: r['max_dd'])
for r in candidates:
    marker = " *" if (r['fn'], r['lfn']) == BASELINE else ""
    print(f"  {r['label']+marker:<12}  {r['n']:>6}  {r['exp']:>+7.3f}  "
          f"{r['exp']-base['exp']:>+7.3f}  {r['max_dd']:>7.1f}R  "
          f"{r['max_dd']-base['max_dd']:>+7.1f}  {r['max_streak']:>7}  "
          f"{r['max_streak']-base['max_streak']:>+8}")
