"""
Tests a set of candidate shared configs across all 6 major pairs (NY session).
Goal: find one config that performs consistently across all pairs for walk-forward.
"""

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

SYMBOLS = ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDJPY', 'USDCAD']
NY = tuple(range(13, 18))
INITIAL_BALANCE = 10_000.0
RR_RATIO = 2.0
N_WORKERS = 1  # parallel workers

# Candidate shared configs
# (label, sl_mode, sl_mult, fractal_n, min_body, engulf_ratio, max_sl)
CANDIDATES = [
    ('A: frac3  body3 eng1.0 sl20', 'fractal',      2.0, 3, 3.0, 1.0, 20),
    ('B: frac5  body3 eng1.0 sl15', 'fractal',      2.0, 5, 3.0, 1.0, 15),
    ('C: frac3  body3 eng1.5 sl20', 'fractal',      2.0, 3, 3.0, 1.5, 20),
    ('D: frac5  body3 eng1.5 sl15', 'fractal',      2.0, 5, 3.0, 1.5, 15),
    ('E: bar1.5 body3 eng1.0 sl20', 'bar_multiple', 1.5, 3, 3.0, 1.0, 20),
    ('F: bar2.0 body3 eng1.0 sl15', 'bar_multiple', 2.0, 3, 3.0, 1.0, 15),
    ('G: bar2.0 body0 eng2.0 sl10', 'bar_multiple', 2.0, 3, 0.0, 2.0, 10),
    ('H: frac3  body3 eng1.0 sl15', 'fractal',      2.0, 3, 3.0, 1.0, 15),
]


# ── Worker (module-level so it's picklable) ───────────────────────────────────
_ALL_BARS = None  # dict: symbol -> (bars, pip_sizes)


def _init_compare_worker(bars_by_symbol):
    global _ALL_BARS
    _ALL_BARS = bars_by_symbol


def _run_task(args):
    """Run one (candidate, symbol) backtest. Returns (label, symbol, result_or_None)."""
    label, sl_mode, sl_mult, frac_n, min_body, eng_ratio, max_sl, symbol = args
    all_bars, pip_sizes = _ALL_BARS[symbol]

    try:
        strategy = ThreeLineStrikeStrategy(
            allowed_hours=NY,
            sma_sep_pips=5.0,
            sl_mode=sl_mode,
            sl_bar_multiplier=sl_mult,
            fractal_n=frac_n,
            min_prev_body_pips=min_body,
            engulf_ratio=eng_ratio,
            max_sl_pips=max_sl,
            pip_sizes=pip_sizes,
        )

        engine = BacktestEngine(initial_balance=INITIAL_BALANCE, rr_ratio=RR_RATIO)
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
            return (label, symbol, None)

        wins = sum(1 for t in trades if t['result'] == 'WIN')
        total_r = sum(t['r_multiple'] for t in trades)

        return (label, symbol, {
            'trades':     n,
            'win_rate':   wins / n * 100,
            'total_r':    total_r,
            'expectancy': total_r / n,
        })
    except Exception:
        return (label, symbol, None)


# ── Pre-load all bar data ─────────────────────────────────────────────────────
print("Loading bar data...")
bars_by_symbol = {}
for symbol in SYMBOLS:
    pip_sizes = {'USDJPY': 0.01} if symbol == 'USDJPY' else {}
    csv_paths = find_csv(symbol, 'M5')
    bars_by_symbol[symbol] = (load_and_merge(csv_paths), pip_sizes)
    print(f"  {symbol}: {len(bars_by_symbol[symbol][0])} bars")

n_tasks = len(CANDIDATES) * len(SYMBOLS)
print(f"\nRunning {n_tasks} tasks ({len(CANDIDATES)} configs × {len(SYMBOLS)} pairs) "
      f"across {N_WORKERS} workers...")

# ── Flat task list: all (candidate, symbol) pairs ────────────────────────────
tasks = [
    (label, sl_mode, sl_mult, frac_n, min_body, eng_ratio, max_sl, symbol)
    for (label, sl_mode, sl_mult, frac_n, min_body, eng_ratio, max_sl) in CANDIDATES
    for symbol in SYMBOLS
]

if N_WORKERS > 1:
    with ProcessPoolExecutor(
        max_workers=N_WORKERS,
        mp_context=multiprocessing.get_context('fork'),
        initializer=_init_compare_worker,
        initargs=(bars_by_symbol,),
    ) as executor:
        task_results = list(executor.map(_run_task, tasks))
else:
    _init_compare_worker(bars_by_symbol)
    task_results = [_run_task(t) for t in tasks]

# ── Reconstruct per-candidate results ────────────────────────────────────────
# Build lookup: (label, symbol) -> result
lookup = {(label, sym): data for label, sym, data in task_results}

results = []
for label, sl_mode, sl_mult, frac_n, min_body, eng_ratio, max_sl in CANDIDATES:
    per_symbol = {sym: lookup.get((label, sym)) for sym in SYMBOLS}
    results.append({'label': label, 'per_symbol': per_symbol})


# ── Display ───────────────────────────────────────────────────────────────────
W = 145
SYM_W = 14


def sym_col(d):
    if d is None:
        return f"{'—':>{SYM_W}}"
    return f"{d['expectancy']:>+6.3f}R/{d['trades']:>3}t"


print(f"\n{'='*W}")
print("SHARED CONFIG COMPARISON  —  NY session, all 6 pairs  (expectancy / trade count per pair)")
print(f"{'='*W}")
sym_header = ''.join(f"{s:>{SYM_W}}" for s in SYMBOLS)
print(f"{'config':<32} {sym_header}   {'pairs+':>6} {'avg_exp':>8} {'total_R':>8}")
print('-' * W)

for r in results:
    ps = r['per_symbol']
    sym_cols = ''.join(sym_col(ps.get(s)) for s in SYMBOLS)

    positive_pairs = sum(1 for s in SYMBOLS if ps.get(s) and ps[s]['expectancy'] > 0)
    all_exp = [ps[s]['expectancy'] for s in SYMBOLS if ps.get(s)]
    avg_exp = sum(all_exp) / len(all_exp) if all_exp else 0
    total_r = sum(ps[s]['total_r'] for s in SYMBOLS if ps.get(s))

    print(f"{r['label']:<32} {sym_cols}   {positive_pairs:>6} {avg_exp:>+8.3f} {total_r:>+8.1f}")

print()
print("Columns: expectancy / trade count per pair over 10 years")
print("pairs+:  number of pairs with positive expectancy")
print("avg_exp: average expectancy across all pairs")
print("total_R: combined R across all pairs")
