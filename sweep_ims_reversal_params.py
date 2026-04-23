"""
Parameter sweep for IMS Reversal — H4/M15 and D1/H4 stacks.

Sweeps the following against all 9 IMS symbols, tracking each symbol separately:

  tp_mode / htf_tp_pct / rr_ratio
      'htf_pct' 0.5 → TP at HTF midpoint (50%)
      'htf_pct' 0.6 → TP 60% into range from entry direction
                       (SELL: 40% from bottom; BUY: 60% from bottom)
      'rr'      1.5 → 1.5:1 risk/reward
      'rr'      2.0 → 2:1
      'rr'      3.0 → 3:1

  sl_buffer_pips
      0.0 → exact swing wick (no buffer)
      1.0 → swing wick + 1 pip

  entry_mode
      'pending' → limit at 50% of LTF leg
      'market'  → MSS bar close

  ltf_fractal_n
      1 → 3-candle LTF fractal (1 bar each side)
      2 → 5-candle LTF fractal (2 bars each side)

  ema_pair  (ema_fast, ema_slow, ema_sep)
      (20, 50, 0.001) → H4 EMA 20/50 filter, 0.1% min separation
      (0,  0,  0.0)   → EMA filter disabled

  session  (blocked_hours)
      'all'   → no filter
      'eu_us' → allow 07–18 UTC
      'ln_us' → allow 12–17 UTC (London/NY overlap — IMS live config)
      'us'    → allow 13–18 UTC

  zone_pct  (fraction of range price must push into before LTF monitoring begins)
      0.5 → price above 50% for SELL setup (relaxed — any premium entry)
      0.6 → price above 60% — more extended, higher-conviction setups only

  tf_combo  (tf_htf, tf_ltf)
      ('H4', 'M15') — proven IMS stack
      ('D1', 'H4')  — higher TF version

  max_losses_per_bias
      1 → expire bias after first loss (one trade per structural range)
      2 → allow one retry after a losing trade
      3 → allow two retries

Total: 5 × 2 × 2 × 2 × 2 × 4 × 2 × 2 × 3 = 1,920 combos × 9 symbols = 17,280 tasks
"""

import itertools
import io
import contextlib
import logging
import multiprocessing
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

import config
from backtest_engine import BacktestEngine
from strategies.ims_reversal import ImsReversalStrategy
from data.historical_loader import find_csv, load_and_merge

logging.basicConfig(level=logging.ERROR)
sys.stdout.reconfigure(line_buffering=True)

SYMBOLS         = ['USDJPY', 'XAUUSD', 'EURAUD', 'CADJPY', 'USDCAD', 'AUDUSD', 'EURUSD', 'GBPCAD', 'GBPUSD']
INITIAL_BALANCE = 10_000.0
N_WORKERS       = 2

PIP_SIZES = {sym: config.PIP_SIZE[sym] for sym in SYMBOLS if sym in config.PIP_SIZE}

# ── Session options (hours to BLOCK) ─────────────────────────────────────────
SESSIONS = {
    'all':    (),
    'eu_us':  (*range(0, 7), *range(18, 24)),
    'ln_us':  (*range(0, 12), *range(17, 24)),
    'us':     (*range(0, 13), *range(18, 24)),
}

# ── TP combos: (tp_mode, htf_tp_pct, rr_ratio) ───────────────────────────────
TP_COMBOS = [
    ('htf_pct', 0.5, 2.0),   # TP at 50% of HTF range (midpoint / equilibrium)
    ('htf_pct', 0.6, 2.0),   # TP 60% into range from entry direction (deeper)
    ('rr',      0.5, 1.5),   # 1.5:1 R:R
    ('rr',      0.5, 2.0),   # 2:1 R:R
    ('rr',      0.5, 3.0),   # 3:1 R:R
]

# ── SL buffer options ─────────────────────────────────────────────────────────
SL_BUFFERS = [0.0, 1.0]   # 0 = exact swing wick; 1.0 = +1 pip (per-symbol pip size)

# ── Entry mode ────────────────────────────────────────────────────────────────
ENTRY_MODES = ['pending', 'market']

# ── LTF fractal size ──────────────────────────────────────────────────────────
LTF_FRACTAL_N = [1, 2]

# ── EMA pairs ────────────────────────────────────────────────────────────────
EMA_PAIRS = [
    (20, 50, 0.001),   # H4 EMA 20/50 with 0.1% min separation
    (0,  0,  0.0),     # disabled
]

# ── Zone gate threshold ───────────────────────────────────────────────────────
ZONE_PCTS = [0.5, 0.6]

# ── Timeframe combos ─────────────────────────────────────────────────────────
TF_COMBOS = [
    ('H4', 'M15'),
    ('D1', 'H4'),
]

# ── Max losses per bias ───────────────────────────────────────────────────────
MAX_LOSSES_OPTIONS = [1, 2, 3]

combos = list(itertools.product(
    TP_COMBOS,
    SL_BUFFERS,
    ENTRY_MODES,
    LTF_FRACTAL_N,
    EMA_PAIRS,
    list(SESSIONS.keys()),
    ZONE_PCTS,
    TF_COMBOS,
    MAX_LOSSES_OPTIONS,
))
total = len(combos)

# ── Worker ────────────────────────────────────────────────────────────────────
_ALL_BARS = None  # dict: (tf_htf, tf_ltf, symbol) -> merged bar list


def _init_worker(bars_by_key):
    global _ALL_BARS
    _ALL_BARS = bars_by_key


def _run_task(args):
    combo, symbol = args
    (tp_combo, sl_buf, entry_mode, ltf_frac_n,
     ema_pair, session_key, zone_pct, tf_combo, max_losses) = combo
    tp_mode, htf_tp_pct, rr_ratio = tp_combo
    ema_fast, ema_slow, ema_sep = ema_pair
    tf_htf, tf_ltf = tf_combo

    key = (tf_htf, tf_ltf, symbol)
    all_bars = _ALL_BARS.get(key)
    if all_bars is None:
        return (combo, symbol, None)

    try:
        strategy = ImsReversalStrategy(
            tf_htf=tf_htf,
            tf_ltf=tf_ltf,
            fractal_n=1,
            ltf_fractal_n=ltf_frac_n,
            htf_lookback=30,
            entry_mode=entry_mode,
            tp_mode=tp_mode,
            htf_tp_pct=htf_tp_pct,
            rr_ratio=rr_ratio,
            zone_pct=zone_pct,
            cooldown_bars=0,
            blocked_hours=SESSIONS[session_key],
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            ema_sep=ema_sep,
            sl_anchor='swing',
            sl_buffer_pips=sl_buf,
            pip_sizes=PIP_SIZES,
            max_losses_per_bias=max_losses,
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


# ── Pre-load bar data per (tf_htf, tf_ltf, symbol) ───────────────────────────
print("Loading bar data...")
bars_by_key = {}
for tf_htf, tf_ltf in TF_COMBOS:
    for symbol in SYMBOLS:
        htf_paths = find_csv(symbol, tf_htf)
        ltf_paths = find_csv(symbol, tf_ltf)
        if not htf_paths or not ltf_paths:
            print(f"  {symbol} {tf_htf}/{tf_ltf}: SKIPPED (no data)")
            continue
        merged = load_and_merge(htf_paths + ltf_paths)
        bars_by_key[(tf_htf, tf_ltf, symbol)] = merged
        print(f"  {symbol} {tf_htf}/{tf_ltf}: {len(merged):,} bars")

active_symbols = SYMBOLS  # retain full list; skip happens in _run_task
n_tasks = total * len(active_symbols)
print(f"\n{total} combos × {len(active_symbols)} symbols = {n_tasks:,} tasks "
      f"across {N_WORKERS} workers\n")

tasks = [(combo, symbol) for combo in combos for symbol in active_symbols]

# ── Run ───────────────────────────────────────────────────────────────────────
PROGRESS_EVERY = 500

if N_WORKERS > 1:
    raw = []
    with ProcessPoolExecutor(
        max_workers=N_WORKERS,
        mp_context=multiprocessing.get_context('fork'),
        initializer=_init_worker,
        initargs=(bars_by_key,),
    ) as executor:
        futures = {executor.submit(_run_task, task): task for task in tasks}
        for i, future in enumerate(as_completed(futures), 1):
            raw.append(future.result())
            if i % PROGRESS_EVERY == 0 or i == n_tasks:
                print(f"  {i}/{n_tasks} tasks done ({i/n_tasks*100:.1f}%)...")
else:
    _init_worker(bars_by_key)
    raw = []
    for i, task in enumerate(tasks, 1):
        raw.append(_run_task(task))
        if i % PROGRESS_EVERY == 0 or i == n_tasks:
            print(f"  {i}/{n_tasks} tasks done ({i/n_tasks*100:.1f}%)...")

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

    (tp_combo, sl_buf, entry_mode, ltf_frac_n,
     ema_pair, session_key, zone_pct, tf_combo, max_losses) = combo
    tp_mode, htf_tp_pct, rr_ratio = tp_combo
    ema_fast, ema_slow, ema_sep = ema_pair
    tf_htf, tf_ltf = tf_combo

    results.append({
        'combo':        combo,
        'tp_mode':      tp_mode,
        'htf_tp_pct':   htf_tp_pct,
        'rr_ratio':     rr_ratio,
        'sl_buf':       sl_buf,
        'entry_mode':   entry_mode,
        'ltf_frac_n':   ltf_frac_n,
        'ema_fast':     ema_fast,
        'ema_slow':     ema_slow,
        'session':      session_key,
        'zone_pct':     zone_pct,
        'tf_htf':       tf_htf,
        'tf_ltf':       tf_ltf,
        'max_losses':   max_losses,
        'per_sym':      per_sym,
        'syms_pos':     sum(1 for d in per_sym.values() if d and d['expectancy'] > 0),
        'avg_exp':      sum(all_exp) / len(all_exp),
        'total_r':      sum(all_r),
        'total_trades': sum(all_trades),
    })

print(f"Done. {len(results)} combos had at least one trade.\n")


# ── Display helpers ───────────────────────────────────────────────────────────
SYM_W   = 11
LABEL_W = 56

W = LABEL_W + SYM_W * len(active_symbols) + 36


def sym_col(d):
    if d is None:
        return f"{'—':>{SYM_W}}"
    return f"{d['expectancy']:>+5.3f}/{d['trades']:>3}t"


def header_sym():
    return ''.join(f"{s[:SYM_W-1]:>{SYM_W}}" for s in active_symbols)


def result_label(r):
    tf   = f"{r['tf_htf']}/{r['tf_ltf']}"
    em   = r['entry_mode'][:4]
    if r['tp_mode'] == 'htf_pct':
        tp = f"htf{r['htf_tp_pct']:.0%}"
    else:
        tp = f"rr{r['rr_ratio']:.1f}"
    sl   = f"sl+{r['sl_buf']:.0f}"
    ema  = f"{r['ema_fast']}/{r['ema_slow']}" if r['ema_fast'] else 'ema_off'
    ses  = r['session']
    zone = f"z{r['zone_pct']:.0%}"
    lf   = f"lf{r['ltf_frac_n']}"
    ml   = f"ml{r['max_losses']}"
    return f"{tf:<8} {em:<4} {tp:<7} {sl:<5} {ema:<7} {ses:<5} {zone} {lf} {ml}"


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


# ── 1. Top 25 by avg expectancy (all combos) ─────────────────────────────────
results.sort(key=lambda r: r['avg_exp'], reverse=True)
print_table(
    f"TOP 25 BY AVG EXPECTANCY  ({len(results)} combos with trades)",
    results,
)

# ── 2. Top 25 — requiring min 10 trades per symbol with trades ────────────────
filtered = [r for r in results if all(
    d['trades'] >= 10 for d in r['per_sym'].values() if d
)]
filtered.sort(key=lambda r: r['avg_exp'], reverse=True)
print_table(
    f"TOP 25 BY AVG EXPECTANCY  (≥10 trades per active symbol, {len(filtered)} combos)",
    filtered,
)

# ── 3. Top by total R ─────────────────────────────────────────────────────────
by_r = sorted(results, key=lambda r: r['total_r'], reverse=True)
print_table("TOP 25 BY TOTAL R", by_r)

# ── 4. TP mode breakdown ──────────────────────────────────────────────────────
print(f"\n{'='*W}")
print("TP MODE BREAKDOWN  (best avg_exp per TP option)")
print(f"{'='*W}")
print(f"{'label':<{LABEL_W}} {header_sym()}  {'pos':>8} {'avg_exp':>7} {'total_R':>8} {'trades':>7}")
print('-' * W)
for tp_mode, htf_tp_pct, rr_ratio in TP_COMBOS:
    if tp_mode == 'htf_pct':
        key = f"htf_pct {htf_tp_pct:.0%}"
    else:
        key = f"rr {rr_ratio}"
    rows = [r for r in results
            if r['tp_mode'] == tp_mode and r['rr_ratio'] == rr_ratio and r['htf_tp_pct'] == htf_tp_pct]
    rows.sort(key=lambda r: r['avg_exp'], reverse=True)
    if rows:
        print(f"── {key:<15}  {result_row(rows[0])}")

# ── 5. SL buffer breakdown ────────────────────────────────────────────────────
print(f"\n{'='*W}")
print("SL BUFFER BREAKDOWN  (best avg_exp per SL option)")
print(f"{'='*W}")
print(f"{'label':<{LABEL_W}} {header_sym()}  {'pos':>8} {'avg_exp':>7} {'total_R':>8} {'trades':>7}")
print('-' * W)
for sl_buf in SL_BUFFERS:
    rows = [r for r in results if r['sl_buf'] == sl_buf]
    rows.sort(key=lambda r: r['avg_exp'], reverse=True)
    if rows:
        print(f"── sl_buf={sl_buf:.0f}pip  {result_row(rows[0])}")

# ── 6. Entry mode breakdown ───────────────────────────────────────────────────
print(f"\n{'='*W}")
print("ENTRY MODE BREAKDOWN  (best avg_exp per mode)")
print(f"{'='*W}")
print(f"{'label':<{LABEL_W}} {header_sym()}  {'pos':>8} {'avg_exp':>7} {'total_R':>8} {'trades':>7}")
print('-' * W)
for mode in ENTRY_MODES:
    rows = [r for r in results if r['entry_mode'] == mode]
    rows.sort(key=lambda r: r['avg_exp'], reverse=True)
    if rows:
        print(f"── {mode:<8}  {result_row(rows[0])}")

# ── 7. Zone gate breakdown ────────────────────────────────────────────────────
print(f"\n{'='*W}")
print("ZONE GATE BREAKDOWN  (best avg_exp per zone_pct)")
print(f"{'='*W}")
print(f"{'label':<{LABEL_W}} {header_sym()}  {'pos':>8} {'avg_exp':>7} {'total_R':>8} {'trades':>7}")
print('-' * W)
for zp in ZONE_PCTS:
    rows = [r for r in results if r['zone_pct'] == zp]
    rows.sort(key=lambda r: r['avg_exp'], reverse=True)
    if rows:
        print(f"── zone={zp:.0%}    {result_row(rows[0])}")

# ── 8. Session breakdown ──────────────────────────────────────────────────────
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

# ── 9. Timeframe breakdown ────────────────────────────────────────────────────
print(f"\n{'='*W}")
print("TIMEFRAME BREAKDOWN  (best avg_exp per TF stack)")
print(f"{'='*W}")
print(f"{'label':<{LABEL_W}} {header_sym()}  {'pos':>8} {'avg_exp':>7} {'total_R':>8} {'trades':>7}")
print('-' * W)
for tf_htf, tf_ltf in TF_COMBOS:
    rows = [r for r in results if r['tf_htf'] == tf_htf and r['tf_ltf'] == tf_ltf]
    rows.sort(key=lambda r: r['avg_exp'], reverse=True)
    if rows:
        print(f"── {tf_htf}/{tf_ltf:<5}      {result_row(rows[0])}")

# ── 10. EMA filter breakdown ──────────────────────────────────────────────────
print(f"\n{'='*W}")
print("EMA FILTER BREAKDOWN  (best avg_exp per EMA setting)")
print(f"{'='*W}")
print(f"{'label':<{LABEL_W}} {header_sym()}  {'pos':>8} {'avg_exp':>7} {'total_R':>8} {'trades':>7}")
print('-' * W)
for ema_f, ema_s, ema_sep in EMA_PAIRS:
    key = f"{ema_f}/{ema_s}" if ema_f else "off"
    rows = [r for r in results if r['ema_fast'] == ema_f and r['ema_slow'] == ema_s]
    rows.sort(key=lambda r: r['avg_exp'], reverse=True)
    if rows:
        print(f"── ema={key:<10}  {result_row(rows[0])}")

# ── 11. LTF fractal breakdown ─────────────────────────────────────────────────
print(f"\n{'='*W}")
print("LTF FRACTAL BREAKDOWN  (best avg_exp per ltf_fractal_n)")
print(f"{'='*W}")
print(f"{'label':<{LABEL_W}} {header_sym()}  {'pos':>8} {'avg_exp':>7} {'total_R':>8} {'trades':>7}")
print('-' * W)
for lf in LTF_FRACTAL_N:
    rows = [r for r in results if r['ltf_frac_n'] == lf]
    rows.sort(key=lambda r: r['avg_exp'], reverse=True)
    if rows:
        print(f"── ltf_frac={lf}     {result_row(rows[0])}")

# ── 12. Max losses per bias breakdown ────────────────────────────────────────
print(f"\n{'='*W}")
print("MAX LOSSES PER BIAS BREAKDOWN  (best avg_exp per value)")
print(f"{'='*W}")
print(f"{'label':<{LABEL_W}} {header_sym()}  {'pos':>8} {'avg_exp':>7} {'total_R':>8} {'trades':>7}")
print('-' * W)
for ml in MAX_LOSSES_OPTIONS:
    rows = [r for r in results if r['max_losses'] == ml]
    rows.sort(key=lambda r: r['avg_exp'], reverse=True)
    if rows:
        print(f"── max_losses={ml}   {result_row(rows[0])}")

# ── 13. Per-symbol summary (best overall combo per symbol) ───────────────────
print(f"\n{'='*W}")
print("PER-SYMBOL SUMMARY  (best avg_exp combo for each symbol)")
print(f"{'='*W}")
print(f"  {'Symbol':<10} {'Best expectancy':>16} {'Win%':>6} {'Trades':>7}  Best combo label")
print('-' * 90)
for sym in active_symbols:
    sym_results = [(r, r['per_sym'][sym]) for r in results if r['per_sym'].get(sym)]
    if not sym_results:
        print(f"  {sym:<10}  no trades")
        continue
    sym_results.sort(key=lambda x: x[1]['expectancy'], reverse=True)
    best_r, best_d = sym_results[0]
    print(f"  {sym:<10}  {best_d['expectancy']:>+8.3f}R / {best_d['win_rate']:>5.1f}% / {best_d['trades']:>4}t     {result_label(best_r)}")
