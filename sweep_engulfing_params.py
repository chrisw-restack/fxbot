"""
Secondary sweep for the Engulfing strategy — tests parameters that were held
static during the original sweep.

Fixed (validated config):
  fractal_n=3, min_prev_body_pips=3.0, engulf_ratio=1.5, max_sl_pips=15
  sl_mode='fractal', allowed_hours=NY (13-17 UTC)
  sma_mid=50 (kept fixed — mid MA for alignment filter)

Swept:
  sma_sep_pips — minimum pip gap between SMA_fast and SMA_mid for alignment
  rr_ratio     — risk/reward target
  sma_fast     — fast MA period (alignment signal)
  sma_slow     — slow MA period (trend filter: price above/below)

Total: 4 × 4 × 2 × 2 = 64 combinations, across 5 pairs = 320 tasks

Goal: find if relaxing/changing these can increase trade count without
      significantly hurting expectancy.
"""

import itertools
import io
import contextlib
import logging
import multiprocessing
import os
import sys
from concurrent.futures import ProcessPoolExecutor

from backtest_engine import BacktestEngine
from strategies.three_line_strike import ThreeLineStrikeStrategy
from data.historical_loader import find_csv, load_and_merge

logging.basicConfig(level=logging.ERROR)
sys.stdout.reconfigure(line_buffering=True)

SYMBOLS = ['EURUSD', 'AUDUSD', 'NZDUSD', 'USDJPY', 'USDCAD']
INITIAL_BALANCE = 10_000.0
N_WORKERS = 2  # parallel workers

NY = tuple(range(13, 18))

# ── Fixed (validated) params ─────────────────────────────────────────────────
FIXED = dict(
    sl_mode='fractal',
    fractal_n=3,
    min_prev_body_pips=3.0,
    engulf_ratio=1.5,
    max_sl_pips=15,
    allowed_hours=NY,
    sma_mid=50,
    pip_sizes={'USDJPY': 0.01},
)

# ── Params to sweep ──────────────────────────────────────────────────────────
SMA_SEP_PIPS = [0.0, 2.5, 5.0, 10.0]
RR_RATIOS    = [1.5, 2.0, 2.5, 3.0]
SMA_FAST     = [10, 21]
SMA_SLOW     = [100, 200]

combos = list(itertools.product(SMA_SEP_PIPS, RR_RATIOS, SMA_FAST, SMA_SLOW))
total  = len(combos)


# ── Worker ───────────────────────────────────────────────────────────────────
_ALL_BARS = None  # dict: symbol -> (bars, pip_sizes)


def _init_worker(bars_by_symbol):
    global _ALL_BARS
    _ALL_BARS = bars_by_symbol


def _run_task(args):
    """Run one (combo, symbol) pair. Returns (combo, symbol, result_or_None)."""
    sep, rr, fast, slow, symbol = args
    all_bars, pip_sizes = _ALL_BARS[symbol]

    try:
        strategy = ThreeLineStrikeStrategy(
            sma_fast=fast,
            sma_slow=slow,
            sma_sep_pips=sep,
            pip_sizes=pip_sizes,
            **{k: v for k, v in FIXED.items() if k != 'pip_sizes'},
        )

        engine = BacktestEngine(initial_balance=INITIAL_BALANCE, rr_ratio=rr)
        engine.add_strategy(strategy, symbols=[symbol])

        with contextlib.redirect_stdout(io.StringIO()):
            for bar in all_bars:
                closed = engine.execution.check_fills(bar)
                for trade in closed:
                    engine.portfolio.record_close(trade['symbol'], trade['pnl'], trade.get('strategy_name', ''))
                    engine.trade_logger.log_close(trade['ticket'], trade)
                    engine.event_engine.notify_trade_closed(trade)
                engine.event_engine.process_bar(bar)

        trades = engine.execution.get_closed_trades()
        n = len(trades)
        if n == 0:
            return ((sep, rr, fast, slow), symbol, None)

        wins = sum(1 for t in trades if t['result'] == 'WIN')
        total_r = sum(t['r_multiple'] for t in trades)

        return ((sep, rr, fast, slow), symbol, {
            'trades':     n,
            'win_rate':   wins / n * 100,
            'total_r':    total_r,
            'expectancy': total_r / n,
        })
    except Exception:
        return ((sep, rr, fast, slow), symbol, None)


# ── Pre-load bar data ─────────────────────────────────────────────────────────
print("Loading bar data...")
bars_by_symbol = {}
for symbol in SYMBOLS:
    pip_sizes = {'USDJPY': 0.01} if symbol == 'USDJPY' else {}
    csv_paths = find_csv(symbol, 'M5')
    bars_by_symbol[symbol] = (load_and_merge(csv_paths), pip_sizes)
    print(f"  {symbol}: {len(bars_by_symbol[symbol][0])} bars")

n_tasks = total * len(SYMBOLS)
print(f"\nRunning {n_tasks} tasks ({total} combos × {len(SYMBOLS)} pairs) "
      f"across {N_WORKERS} workers...")
print(f"Fixed: fractal_n=3, min_body=3.0, engulf_ratio=1.5, max_sl=15, NY session, sma_mid=50\n")

# ── Flat task list ────────────────────────────────────────────────────────────
tasks = [
    (sep, rr, fast, slow, symbol)
    for (sep, rr, fast, slow) in combos
    for symbol in SYMBOLS
]

if N_WORKERS > 1:
    with ProcessPoolExecutor(
        max_workers=N_WORKERS,
        mp_context=multiprocessing.get_context('fork'),
        initializer=_init_worker,
        initargs=(bars_by_symbol,),
    ) as executor:
        raw = list(executor.map(_run_task, tasks))
else:
    _init_worker(bars_by_symbol)
    raw = [_run_task(t) for t in tasks]

# ── Reconstruct per-combo results ─────────────────────────────────────────────
lookup = {(combo, sym): data for combo, sym, data in raw}

results = []
for combo in combos:
    sep, rr, fast, slow = combo
    per_symbol = {sym: lookup.get((combo, sym)) for sym in SYMBOLS}

    all_exp    = [d['expectancy'] for d in per_symbol.values() if d]
    all_r      = [d['total_r']    for d in per_symbol.values() if d]
    all_trades = [d['trades']     for d in per_symbol.values() if d]

    results.append({
        'sep':          sep,
        'rr':           rr,
        'fast':         fast,
        'slow':         slow,
        'per_symbol':   per_symbol,
        'pairs_pos':    sum(1 for d in per_symbol.values() if d and d['expectancy'] > 0),
        'avg_exp':      sum(all_exp) / len(all_exp) if all_exp else 0,
        'total_r':      sum(all_r),
        'total_trades': sum(all_trades),
    })

print(f"Done.\n")


# ── Display helpers ───────────────────────────────────────────────────────────
SYM_W  = 13
LABEL_W = 30
W = LABEL_W + SYM_W * len(SYMBOLS) + 38


def sym_col(d):
    if d is None:
        return f"{'—':>{SYM_W}}"
    return f"{d['expectancy']:>+5.3f}R/{d['trades']:>3}t"


def header_line():
    sym_h = ''.join(f"{s:>{SYM_W}}" for s in SYMBOLS)
    return f"{'sep  rr fast slow':<{LABEL_W}} {sym_h}  {'pairs+':>6} {'avg_exp':>8} {'total_R':>8} {'trades':>7}"


def result_row(r):
    sym_cols = ''.join(sym_col(r['per_symbol'].get(s)) for s in SYMBOLS)
    label = f"sep={r['sep']:.1f} rr={r['rr']:.1f} f={r['fast']:>2} s={r['slow']}"
    return (
        f"{label:<{LABEL_W}} {sym_cols}  "
        f"{r['pairs_pos']:>6} {r['avg_exp']:>+8.3f} {r['total_r']:>+8.1f} {r['total_trades']:>7}"
    )


def print_table(title, rows, n=20):
    print(f"\n{'='*W}")
    print(title)
    print(f"{'='*W}")
    print(header_line())
    print('-' * W)
    for r in rows[:n]:
        print(result_row(r))
    print()
    print("Columns: expectancy / trade count per pair over 10 years")
    print("trades: total trades across all 5 pairs")


# ── 1. Top by avg expectancy (all 5 pairs present) ────────────────────────────
full = [r for r in results if all(r['per_symbol'].get(s) for s in SYMBOLS)]
full.sort(key=lambda r: r['avg_exp'], reverse=True)
print_table(
    f"TOP 20 BY AVG EXPECTANCY  (all 5 pairs have trades, {len(full)}/{total} combos)",
    full,
)

# ── 2. Top by total trades (to find high-frequency configs) ──────────────────
by_trades = sorted(results, key=lambda r: r['total_trades'], reverse=True)
print_table("TOP 20 BY TOTAL TRADE COUNT", by_trades)

# ── 3. Top by total R ─────────────────────────────────────────────────────────
by_r = sorted(results, key=lambda r: r['total_r'], reverse=True)
print_table("TOP 20 BY TOTAL R", by_r)

# ── 4. Breakdown by sma_sep_pips — best per value ─────────────────────────────
print(f"\n{'='*W}")
print("SMA_SEP_PIPS BREAKDOWN  (best avg_exp per sep value, all 5 pairs present)")
print(f"{'='*W}")
print(header_line())
print('-' * W)
for sep_val in SMA_SEP_PIPS:
    rows = [r for r in full if r['sep'] == sep_val]
    rows.sort(key=lambda r: r['avg_exp'], reverse=True)
    if rows:
        print(f"sep={sep_val:.1f}  →  {result_row(rows[0])}")

# ── 5. Breakdown by rr_ratio — best per value ────────────────────────────────
print(f"\n{'='*W}")
print("RR_RATIO BREAKDOWN  (best avg_exp per RR value, all 5 pairs present)")
print(f"{'='*W}")
print(header_line())
print('-' * W)
for rr_val in RR_RATIOS:
    rows = [r for r in full if r['rr'] == rr_val]
    rows.sort(key=lambda r: r['avg_exp'], reverse=True)
    if rows:
        print(f"rr={rr_val:.1f}   →  {result_row(rows[0])}")

# ── 6. Reference row — current live config ───────────────────────────────────
print(f"\n{'='*W}")
print("REFERENCE: current live config  (sep=5.0, rr=2.0, fast=21, slow=200)")
print(f"{'='*W}")
print(header_line())
print('-' * W)
ref = next((r for r in results if r['sep'] == 5.0 and r['rr'] == 2.0
            and r['fast'] == 21 and r['slow'] == 200), None)
if ref:
    print(result_row(ref))
else:
    print("  (not found in results)")
