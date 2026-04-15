"""
Stop-loss placement sweep for IMS H4/M15.

Fixes the best params from the main sweep and varies only SL placement:
  sl_anchor      — 'swing' (wick) | 'body' (candle body) | 'fvg' (bottom of LTF FVG)
  sl_buffer_pips — fixed pip buffer below/above anchor
  sl_atr_mult    — dynamic buffer: mult × ATR(14) on M15 bars

Fixed params (best from main sweep):
  pending / rr2.5 / EMA 20/50 / ln_us (12-17 UTC) / fn1/lf1 / lb30 / ema_sep=0.001 / cd0

Symbols: USDJPY, XAUUSD, EURAUD, CADJPY, USDCAD, AUDUSD, EURUSD, GBPCAD, GBPUSD
"""

import io
import contextlib
import logging
import multiprocessing
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

import config
from backtest_engine import BacktestEngine
from strategies.ims import ImsStrategy
from data.historical_loader import find_csv, load_and_merge

logging.basicConfig(level=logging.ERROR)
sys.stdout.reconfigure(line_buffering=True)

SYMBOLS         = ['USDJPY', 'XAUUSD', 'EURAUD', 'CADJPY', 'USDCAD', 'AUDUSD', 'EURUSD', 'GBPCAD', 'GBPUSD']
INITIAL_BALANCE = 10_000.0
N_WORKERS       = 2
PROGRESS_EVERY  = 50

PIP_SIZES = {sym: config.PIP_SIZE[sym] for sym in SYMBOLS if sym in config.PIP_SIZE}

# ── Fixed best params ─────────────────────────────────────────────────────────
FIXED = dict(
    tf_htf='H4', tf_ltf='M15',
    entry_mode='pending',
    tp_mode='rr', rr_ratio=2.5,
    fractal_n=1, ltf_fractal_n=1,
    htf_lookback=30,
    cooldown_bars=0,
    blocked_hours=(*range(0, 12), *range(17, 24)),  # ln_us: 12-17 UTC
    ema_fast=20, ema_slow=50, ema_sep=0.001,
    pip_sizes=PIP_SIZES,
)

# ── SL combos: (anchor, buffer_pips, atr_mult) ───────────────────────────────
SL_COMBOS = [
    # Swing wick anchor (baseline + buffers)
    ('swing', 0.0, 0.0),
    ('swing', 1.0, 0.0),
    ('swing', 2.0, 0.0),
    ('swing', 3.0, 0.0),
    ('swing', 0.0, 0.25),
    ('swing', 0.0, 0.5),
    ('swing', 0.0, 1.0),
    # Body anchor (ignores spike wicks)
    ('body',  0.0, 0.0),
    ('body',  1.0, 0.0),
    ('body',  2.0, 0.0),
    ('body',  0.0, 0.25),
    ('body',  0.0, 0.5),
    # FVG bottom anchor (structurally tighter)
    ('fvg',   0.0, 0.0),
    ('fvg',   1.0, 0.0),
    ('fvg',   2.0, 0.0),
    ('fvg',   0.0, 0.25),
    ('fvg',   0.0, 0.5),
]

n_combos = len(SL_COMBOS)
n_tasks  = n_combos * len(SYMBOLS)


# ── Worker ────────────────────────────────────────────────────────────────────
_ALL_BARS = None


def _init_worker(bars_by_symbol):
    global _ALL_BARS
    _ALL_BARS = bars_by_symbol


def _run_task(args):
    sl_combo, symbol = args
    anchor, buf_pips, atr_mult = sl_combo
    all_bars = _ALL_BARS[symbol]

    try:
        strategy = ImsStrategy(
            **FIXED,
            sl_anchor=anchor,
            sl_buffer_pips=buf_pips,
            sl_atr_mult=atr_mult,
        )
        engine = BacktestEngine(initial_balance=INITIAL_BALANCE, rr_ratio=FIXED['rr_ratio'])
        engine.add_strategy(strategy, symbols=[symbol])

        with contextlib.redirect_stdout(io.StringIO()):
            for bar in all_bars:
                closed = engine.execution.check_fills(bar)
                for trade in closed:
                    engine.portfolio.record_close(
                        trade['symbol'], trade['pnl'], trade.get('strategy_name', ''))
                    engine.trade_logger.log_close(trade['ticket'], trade)
                    engine.event_engine.notify_trade_closed(trade)
                engine.event_engine.process_bar(bar)

        trades = engine.execution.get_closed_trades()
        n = len(trades)
        if n == 0:
            return (sl_combo, symbol, None)

        wins    = sum(1 for t in trades if t['result'] == 'WIN')
        total_r = sum(t['r_multiple'] for t in trades)
        return (sl_combo, symbol, {
            'trades':     n,
            'win_rate':   wins / n * 100,
            'total_r':    total_r,
            'expectancy': total_r / n,
        })
    except Exception:
        return (sl_combo, symbol, None)


# ── Load bar data ─────────────────────────────────────────────────────────────
print("Loading bar data...")
bars_by_symbol = {}
for symbol in SYMBOLS:
    h4  = find_csv(symbol, 'H4')
    m15 = find_csv(symbol, 'M15')
    if not h4 or not m15:
        print(f"  {symbol}: SKIPPED (missing H4 or M15 data)")
        continue
    merged = load_and_merge(h4 + m15)
    bars_by_symbol[symbol] = merged
    print(f"  {symbol}: {len(merged):,} bars")

active_symbols = list(bars_by_symbol.keys())
n_tasks = n_combos * len(active_symbols)
print(f"\n{n_combos} SL combos × {len(active_symbols)} symbols = {n_tasks} tasks "
      f"across {N_WORKERS} workers\n")

tasks = [(sl_combo, sym) for sl_combo in SL_COMBOS for sym in active_symbols]

# ── Run ───────────────────────────────────────────────────────────────────────
if N_WORKERS > 1:
    raw = []
    with ProcessPoolExecutor(
        max_workers=N_WORKERS,
        mp_context=multiprocessing.get_context('fork'),
        initializer=_init_worker,
        initargs=(bars_by_symbol,),
    ) as executor:
        futures = {executor.submit(_run_task, task): task for task in tasks}
        for i, future in enumerate(as_completed(futures), 1):
            raw.append(future.result())
            if i % PROGRESS_EVERY == 0 or i == n_tasks:
                print(f"  {i}/{n_tasks} tasks done ({i/n_tasks*100:.1f}%)...")
else:
    _init_worker(bars_by_symbol)
    raw = []
    for i, task in enumerate(tasks, 1):
        raw.append(_run_task(task))
        if i % PROGRESS_EVERY == 0 or i == n_tasks:
            print(f"  {i}/{n_tasks} tasks done ({i/n_tasks*100:.1f}%)...")

# ── Aggregate results ─────────────────────────────────────────────────────────
lookup = {(combo, sym): data for combo, sym, data in raw}

results = []
for sl_combo in SL_COMBOS:
    anchor, buf_pips, atr_mult = sl_combo
    per_sym = {sym: lookup.get((sl_combo, sym)) for sym in active_symbols}
    all_exp    = [d['expectancy'] for d in per_sym.values() if d]
    all_r      = [d['total_r']    for d in per_sym.values() if d]
    all_trades = [d['trades']     for d in per_sym.values() if d]
    if not all_exp:
        continue
    results.append({
        'sl_combo':     sl_combo,
        'anchor':       anchor,
        'buf_pips':     buf_pips,
        'atr_mult':     atr_mult,
        'per_sym':      per_sym,
        'syms_pos':     sum(1 for d in per_sym.values() if d and d['expectancy'] > 0),
        'avg_exp':      sum(all_exp) / len(all_exp),
        'total_r':      sum(all_r),
        'total_trades': sum(all_trades),
    })

print(f"\nDone. {len(results)} combos had at least one trade.\n")

# ── Display ───────────────────────────────────────────────────────────────────
SYM_W   = 11
LABEL_W = 28
W = LABEL_W + SYM_W * len(active_symbols) + 36


def sl_label(r):
    buf = f"+{r['buf_pips']:.0f}pip" if r['buf_pips'] else (
          f"+{r['atr_mult']:.2f}ATR" if r['atr_mult'] else "  bare  ")
    return f"{r['anchor']:<5} {buf:<9}"


def sym_col(d):
    if d is None:
        return f"{'—':>{SYM_W}}"
    return f"{d['expectancy']:>+5.3f}/{d['trades']:>3}t"


def header_sym():
    return ''.join(f"{s[:SYM_W-1]:>{SYM_W}}" for s in active_symbols)


def result_row(r):
    sym_cols = ''.join(sym_col(r['per_sym'].get(s)) for s in active_symbols)
    return (
        f"{sl_label(r):<{LABEL_W}} {sym_cols}  "
        f"{r['syms_pos']:>5}/{len(active_symbols):<2} "
        f"{r['avg_exp']:>+7.3f} {r['total_r']:>+8.1f} {r['total_trades']:>7}"
    )


hdr = (f"{'SL config':<{LABEL_W}} {header_sym()}  "
       f"{'pos':>8} {'avg_exp':>7} {'total_R':>8} {'trades':>7}")
div = '=' * W

print(div)
print(f"SL PLACEMENT SWEEP  —  all combos ranked by avg expectancy")
print(f"Fixed: pending / rr2.5 / EMA 20/50 / ln_us / fn1/lf1 / lb30 / ema_sep=0.001")
print(div)
print(hdr)
print('-' * W)
results.sort(key=lambda r: r['avg_exp'], reverse=True)
for r in results:
    print(result_row(r))
print()
print(f"  Symbol columns: expectancy/trades  |  pos = symbols with positive expectancy")

# ── Anchor breakdown ──────────────────────────────────────────────────────────
print(f"\n{div}")
print("BEST PER ANCHOR TYPE")
print(div)
print(hdr)
print('-' * W)
for anchor in ('swing', 'body', 'fvg'):
    rows = [r for r in results if r['anchor'] == anchor]
    rows.sort(key=lambda r: r['avg_exp'], reverse=True)
    if rows:
        print(f"── {anchor:<5}  {result_row(rows[0])}")
