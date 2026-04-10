"""
Parameter sweep for IMS (ICT Market Structure) — H4/M15 stack.
Runs each param combo per symbol separately so you can see which symbols
contribute to performance and which drag it down.

Swept parameters:
  entry_mode    — 'pending' (limit at 50% of LTF leg) | 'market' (MSS bar close)
  tp_mode/rr    — HTF target, 2:1, or 2.5:1
  ema_pair      — H4 EMA fast/slow (off, 20/50, 60/120 ≈ daily 10/20)
  session       — which hours to allow LTF signals
  fractal_n     — H4 fractal bars each side (1=3-candle, 2=5-candle)
  ltf_fractal_n — M15 fractal bars each side (1=3-candle, 2=5-candle)
  htf_lookback  — H4 bars scanned for bias
  cooldown_bars — M15 bars to skip after a loss
  ema_sep       — minimum EMA separation as fraction of price

Total: 2×3×3×3×2×2×2×2×2 = 1,728 combos × 9 symbols = 15,552 tasks
"""

import itertools
import io
import contextlib
import logging
import multiprocessing
import sys
from concurrent.futures import ProcessPoolExecutor

from backtest_engine import BacktestEngine
from strategies.ims import ImsStrategy
from data.historical_loader import find_csv, load_and_merge

logging.basicConfig(level=logging.ERROR)
sys.stdout.reconfigure(line_buffering=True)

SYMBOLS         = ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDJPY', 'USDCAD', 'USDCHF', 'XAUUSD', 'USA100']
INITIAL_BALANCE = 10_000.0
N_WORKERS       = 2   # increase if you have spare CPU cores

# ── Session options (hours to BLOCK) ─────────────────────────────────────────
# Signals fired during blocked hours are suppressed in _on_ltf_bar.
SESSIONS = {
    'all':   (),                                             # no filter
    'eu_us': (*range(0, 7), *range(18, 24)),                 # allow 07–18 UTC
    'eu':    (*range(0, 7), *range(16, 24)),                 # allow 07–16 UTC
    'us':    (*range(0, 13), *range(18, 24)),                # allow 13–18 UTC
}

# ── EMA pair options (fast, slow on H4) ──────────────────────────────────────
EMA_PAIRS = [
    (0,   0),    # disabled
    (20,  50),   # medium-term H4 trend
    (60, 120),   # ≈ daily 10/20 (6 H4 bars per day × 10/20)
]

# ── TP combos: (tp_mode, rr_ratio) ───────────────────────────────────────────
TP_COMBOS = [
    ('htf_high', 2.0),   # TP at HTF swing high/low
    ('rr',       2.0),   # 2:1 from entry
    ('rr',       2.5),   # 2.5:1 from entry
]

# ── Remaining param grid ──────────────────────────────────────────────────────
ENTRY_MODES   = ['pending', 'market']
FRACTAL_N     = [1, 2]
LTF_FRACTAL_N = [1, 2]
HTF_LOOKBACK  = [30, 50]
COOLDOWN      = [0, 3]
EMA_SEP       = [0.0, 0.001]

combos = list(itertools.product(
    ENTRY_MODES,
    TP_COMBOS,
    EMA_PAIRS,
    list(SESSIONS.keys()),
    FRACTAL_N,
    LTF_FRACTAL_N,
    HTF_LOOKBACK,
    COOLDOWN,
    EMA_SEP,
))
total = len(combos)


# ── Worker ────────────────────────────────────────────────────────────────────
_ALL_BARS = None  # dict: symbol -> merged [H4 + M15] bar list


def _init_worker(bars_by_symbol):
    global _ALL_BARS
    _ALL_BARS = bars_by_symbol


def _run_task(args):
    """Run one (combo, symbol) pair. Returns (combo, symbol, result_or_None)."""
    combo, symbol = args
    (entry_mode, tp_combo, ema_pair,
     session_key, fractal_n, ltf_fractal_n,
     htf_lookback, cooldown, ema_sep) = combo
    tp_mode, rr_ratio = tp_combo
    ema_fast, ema_slow = ema_pair
    all_bars = _ALL_BARS[symbol]

    try:
        strategy = ImsStrategy(
            tf_htf='H4',
            tf_ltf='M15',
            entry_mode=entry_mode,
            fractal_n=fractal_n,
            ltf_fractal_n=ltf_fractal_n,
            htf_lookback=htf_lookback,
            tp_mode=tp_mode,
            rr_ratio=rr_ratio,
            cooldown_bars=cooldown,
            blocked_hours=SESSIONS[session_key],
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            ema_sep=ema_sep,
        )

        engine = BacktestEngine(initial_balance=INITIAL_BALANCE, rr_ratio=rr_ratio)
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
            return (combo, symbol, None)

        wins    = sum(1 for t in trades if t['result'] == 'WIN')
        total_r = sum(t['r_multiple'] for t in trades)

        return (combo, symbol, {
            'trades':     n,
            'win_rate':   wins / n * 100,
            'total_r':    total_r,
            'expectancy': total_r / n,
        })
    except Exception:
        return (combo, symbol, None)


# ── Pre-load bar data (H4 + M15 merged per symbol) ───────────────────────────
print("Loading bar data...")
bars_by_symbol = {}
for symbol in SYMBOLS:
    h4_paths  = find_csv(symbol, 'H4')
    m15_paths = find_csv(symbol, 'M15')
    if not h4_paths or not m15_paths:
        print(f"  {symbol}: SKIPPED (no H4 or M15 data)")
        continue
    merged = load_and_merge(h4_paths + m15_paths)
    bars_by_symbol[symbol] = merged
    print(f"  {symbol}: {len(merged):,} bars (H4+M15)")

active_symbols = list(bars_by_symbol.keys())
n_tasks = total * len(active_symbols)
print(f"\n{total} combos × {len(active_symbols)} symbols = {n_tasks:,} tasks "
      f"across {N_WORKERS} workers\n")

# ── Build flat task list ──────────────────────────────────────────────────────
tasks = [(combo, symbol) for combo in combos for symbol in active_symbols]

# ── Run ───────────────────────────────────────────────────────────────────────
if N_WORKERS > 1:
    with ProcessPoolExecutor(
        max_workers=N_WORKERS,
        mp_context=multiprocessing.get_context('fork'),
        initializer=_init_worker,
        initargs=(bars_by_symbol,),
    ) as executor:
        raw = list(executor.map(_run_task, tasks, chunksize=8))
else:
    _init_worker(bars_by_symbol)
    raw = []
    for i, task in enumerate(tasks):
        raw.append(_run_task(task))
        if (i + 1) % 500 == 0:
            print(f"  {i+1}/{n_tasks} tasks done...")

# ── Reconstruct per-combo results ─────────────────────────────────────────────
lookup = {(combo, sym): data for combo, sym, data in raw}

results = []
for combo in combos:
    per_sym = {sym: lookup.get((combo, sym)) for sym in active_symbols}

    all_exp    = [d['expectancy'] for d in per_sym.values() if d]
    all_r      = [d['total_r']    for d in per_sym.values() if d]
    all_trades = [d['trades']     for d in per_sym.values() if d]

    if not all_exp:
        continue

    (entry_mode, tp_combo, ema_pair,
     session_key, fractal_n, ltf_fractal_n,
     htf_lookback, cooldown, ema_sep) = combo
    tp_mode, rr_ratio = tp_combo
    ema_fast, ema_slow = ema_pair

    results.append({
        'combo':        combo,
        'entry_mode':   entry_mode,
        'tp_mode':      tp_mode,
        'rr_ratio':     rr_ratio,
        'ema_fast':     ema_fast,
        'ema_slow':     ema_slow,
        'session':      session_key,
        'fractal_n':    fractal_n,
        'ltf_frac_n':   ltf_fractal_n,
        'htf_lb':       htf_lookback,
        'cooldown':     cooldown,
        'ema_sep':      ema_sep,
        'per_sym':      per_sym,
        'syms_pos':     sum(1 for d in per_sym.values() if d and d['expectancy'] > 0),
        'avg_exp':      sum(all_exp) / len(all_exp),
        'total_r':      sum(all_r),
        'total_trades': sum(all_trades),
    })

print(f"Done. {len(results)} combos had at least one trade.\n")


# ── Display helpers ───────────────────────────────────────────────────────────
SYM_W   = 11   # chars per symbol column:  "+0.123/12t"
LABEL_W = 48

W = LABEL_W + SYM_W * len(active_symbols) + 36


def sym_col(d):
    if d is None:
        return f"{'—':>{SYM_W}}"
    return f"{d['expectancy']:>+5.3f}/{d['trades']:>3}t"


def header_sym():
    return ''.join(f"{s[:SYM_W-1]:>{SYM_W}}" for s in active_symbols)


def result_label(r):
    em   = r['entry_mode'][:4]
    tp   = r['tp_mode'][:5] if r['tp_mode'] == 'htf_high' else f"rr{r['rr_ratio']:.1f}"
    ema  = f"{r['ema_fast']}/{r['ema_slow']}" if r['ema_fast'] else 'ema_off'
    ses  = r['session']
    frac = f"fn{r['fractal_n']}/lf{r['ltf_frac_n']}"
    rest = f"lb{r['htf_lb']} cd{r['cooldown']} sep{r['ema_sep']:.3f}"
    return f"{em:<4} {tp:<7} {ema:<7} {ses:<5} {frac} {rest}"


def result_row(r):
    sym_cols = ''.join(sym_col(r['per_sym'].get(s)) for s in active_symbols)
    return (
        f"{result_label(r):<{LABEL_W}} {sym_cols}  "
        f"{r['syms_pos']:>5}/{len(active_symbols):<2} "
        f"{r['avg_exp']:>+7.3f} {r['total_r']:>+8.1f} {r['total_trades']:>7}"
    )


def print_table(title, rows, n=25):
    print(f"\n{'='*W}")
    print(title)
    print(f"{'='*W}")
    hdr = (f"{'label':<{LABEL_W}} {header_sym()}  "
           f"{'pos':>8} {'avg_exp':>7} {'total_R':>8} {'trades':>7}")
    print(hdr)
    print('-' * W)
    for r in rows[:n]:
        print(result_row(r))
    print()
    print(f"  Symbol columns: expectancy/trades  |  pos = symbols with positive expectancy")


# ── 1. Top by avg expectancy — all symbols with trades ───────────────────────
results.sort(key=lambda r: r['avg_exp'], reverse=True)
print_table(
    f"TOP 25 BY AVG EXPECTANCY  ({len(results)} combos with trades)",
    results,
)

# ── 2. Top — requiring all symbols to have trades ─────────────────────────────
full = [r for r in results if all(r['per_sym'].get(s) for s in active_symbols)]
full.sort(key=lambda r: r['avg_exp'], reverse=True)
print_table(
    f"TOP 25 BY AVG EXPECTANCY  (all {len(active_symbols)} symbols have trades, {len(full)} combos)",
    full,
)

# ── 3. Top by total R ─────────────────────────────────────────────────────────
by_r = sorted(results, key=lambda r: r['total_r'], reverse=True)
print_table("TOP 25 BY TOTAL R", by_r)

# ── 4. Entry mode breakdown ───────────────────────────────────────────────────
print(f"\n{'='*W}")
print("ENTRY MODE BREAKDOWN  (best avg_exp per mode)")
print(f"{'='*W}")
print(f"{'label':<{LABEL_W}} {header_sym()}  {'pos':>8} {'avg_exp':>7} {'total_R':>8} {'trades':>7}")
print('-' * W)
for mode in ENTRY_MODES:
    rows = [r for r in results if r['entry_mode'] == mode]
    rows.sort(key=lambda r: r['avg_exp'], reverse=True)
    if rows:
        print(f"── {mode} ──  {result_row(rows[0])}")

# ── 5. TP mode breakdown ──────────────────────────────────────────────────────
print(f"\n{'='*W}")
print("TP MODE BREAKDOWN  (best avg_exp per TP option)")
print(f"{'='*W}")
print(f"{'label':<{LABEL_W}} {header_sym()}  {'pos':>8} {'avg_exp':>7} {'total_R':>8} {'trades':>7}")
print('-' * W)
for tp_mode, rr in TP_COMBOS:
    key = f"{tp_mode} rr={rr}"
    rows = [r for r in results if r['tp_mode'] == tp_mode and r['rr_ratio'] == rr]
    rows.sort(key=lambda r: r['avg_exp'], reverse=True)
    if rows:
        print(f"── {key:<15}  {result_row(rows[0])}")

# ── 6. EMA pair breakdown ─────────────────────────────────────────────────────
print(f"\n{'='*W}")
print("EMA PAIR BREAKDOWN  (best avg_exp per EMA setting)")
print(f"{'='*W}")
print(f"{'label':<{LABEL_W}} {header_sym()}  {'pos':>8} {'avg_exp':>7} {'total_R':>8} {'trades':>7}")
print('-' * W)
for ema_f, ema_s in EMA_PAIRS:
    key = f"{ema_f}/{ema_s}" if ema_f else "off"
    rows = [r for r in results if r['ema_fast'] == ema_f and r['ema_slow'] == ema_s]
    rows.sort(key=lambda r: r['avg_exp'], reverse=True)
    if rows:
        print(f"── ema={key:<10}  {result_row(rows[0])}")

# ── 7. Session breakdown ──────────────────────────────────────────────────────
print(f"\n{'='*W}")
print("SESSION BREAKDOWN  (best avg_exp per session filter)")
print(f"{'='*W}")
print(f"{'label':<{LABEL_W}} {header_sym()}  {'pos':>8} {'avg_exp':>7} {'total_R':>8} {'trades':>7}")
print('-' * W)
for ses in SESSIONS:
    rows = [r for r in results if r['session'] == ses]
    rows.sort(key=lambda r: r['avg_exp'], reverse=True)
    if rows:
        print(f"── session={ses:<6}  {result_row(rows[0])}")

# ── 8. Per-symbol summary — best config for each symbol ──────────────────────
print(f"\n{'='*W}")
print("PER-SYMBOL SUMMARY  (best avg_exp combo where that symbol has trades)")
print(f"{'='*W}")
print(f"  {'Symbol':<10} {'Best expectancy':>16} {'Trades':>7}  Best combo label")
print('-' * 80)
for sym in active_symbols:
    sym_results = [(r, r['per_sym'][sym]) for r in results if r['per_sym'].get(sym)]
    if not sym_results:
        print(f"  {sym:<10}  no trades")
        continue
    sym_results.sort(key=lambda x: x[1]['expectancy'], reverse=True)
    best_r, best_d = sym_results[0]
    print(f"  {sym:<10}  {best_d['expectancy']:>+8.3f}R / {best_d['trades']:>4}t     {result_label(best_r)}")
