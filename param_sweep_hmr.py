"""
Parameter sweep for HourlyMeanReversionStrategy (XAUUSD M5).

Grid:
  min_move_pips      — minimum H1 run before checking for MSS
  entry_window       — (start, end) minutes into H1 (tested as named pairs)
  fractal_n          — bars each side for swing confirmation
  max_pullback_pips  — max intra-run pullback; 0 = off
  session            — asian / london / both

Run: python3 param_sweep_hmr.py
"""

import itertools
import io
import contextlib
import logging
import multiprocessing
import sys

from concurrent.futures import ProcessPoolExecutor
from backtest_engine import BacktestEngine
from strategies.hourly_mean_reversion import HourlyMeanReversionStrategy
from data.historical_loader import find_csv, load_and_merge

logging.basicConfig(level=logging.ERROR)
sys.stdout.reconfigure(line_buffering=True)

SYMBOLS         = ['XAUUSD']
INITIAL_BALANCE = 10_000.0
RR_RATIO        = 2.0
TF_LOWER        = 'M5'
N_WORKERS       = 1

SESSION_CONFIGS = {
    'asian':  tuple(range(0, 8)),
    'london': tuple(range(8, 17)),
    'both':   tuple(range(0, 17)),
}

# Named window pairs — avoids start>=end and keeps combos meaningful
WINDOWS = [
    (15, 35), (15, 40),
    (20, 40), (20, 45),
    (25, 45), (25, 50),
]

MIN_MOVE      = [50, 75, 100, 150, 200]
FRACTAL_N     = [1, 2, 3]
MAX_PULLBACK  = [0, 25, 50]
SESSIONS      = ['asian', 'london', 'both']

combos = list(itertools.product(MIN_MOVE, WINDOWS, FRACTAL_N, MAX_PULLBACK, SESSIONS))
total  = len(combos)


# ── Worker (module-level for pickling) ────────────────────────────────────────
_BARS = None


def _init_worker(bars):
    global _BARS
    _BARS = bars


def _run_combo(combo):
    min_move, (w_start, w_end), fn, max_pb, session = combo
    try:
        strategy = HourlyMeanReversionStrategy(
            tf_lower=TF_LOWER,
            min_move_pips=min_move,
            entry_window_start=w_start,
            entry_window_end=w_end,
            fractal_n=fn,
            max_pullback_pips=max_pb,
            session_hours=SESSION_CONFIGS[session],
        )
        engine = BacktestEngine(initial_balance=INITIAL_BALANCE, rr_ratio=RR_RATIO)
        engine.add_strategy(strategy, symbols=SYMBOLS)

        with contextlib.redirect_stdout(io.StringIO()):
            for bar in _BARS:
                closed = engine.execution.check_fills(bar)
                for trade in closed:
                    engine.portfolio.record_close(trade['symbol'], trade['pnl'], trade.get('strategy_name', ''))
                    engine.trade_logger.log_close(trade['ticket'], trade)
                    engine.event_engine.notify_trade_closed(trade)
                engine.event_engine.process_bar(bar)

        trades = engine.execution.get_closed_trades()
        n = len(trades)
        if n == 0:
            return None

        wins    = [t for t in trades if t['result'] == 'WIN']
        losses  = [t for t in trades if t['result'] == 'LOSS']
        total_r = sum(t['r_multiple'] for t in trades)
        wr      = len(wins) / n * 100
        exp     = total_r / n
        gross_p = sum(t['r_multiple'] for t in wins)
        gross_l = abs(sum(t['r_multiple'] for t in losses))
        pf      = gross_p / gross_l if gross_l > 0 else 0.0

        # Max drawdown in R
        peak, max_dd, running = 0.0, 0.0, 0.0
        for t in trades:
            running += t['r_multiple']
            peak = max(peak, running)
            max_dd = max(max_dd, peak - running)

        return {
            'min_move': min_move,
            'w_start':  w_start,
            'w_end':    w_end,
            'fn':       fn,
            'max_pb':   max_pb,
            'session':  session,
            'trades':   n,
            'wr':       wr,
            'total_r':  total_r,
            'expect':   exp,
            'pf':       pf,
            'max_dd':   max_dd,
        }
    except Exception:
        return None


# ── Load bars once ────────────────────────────────────────────────────────────
csv_paths = []
for sym in SYMBOLS:
    csv_paths.extend(find_csv(sym, TF_LOWER))

if not csv_paths:
    print(f"No {TF_LOWER} CSV for {SYMBOLS}. Run fetch_data_dukascopy.py first.")
    sys.exit(1)

print("Loading bar data...")
all_bars = load_and_merge(csv_paths)
print(f"Loaded {len(all_bars)} bars")
print(f"Running {total} combinations across {N_WORKERS} workers...\n")

# ── Run in parallel ───────────────────────────────────────────────────────────
with ProcessPoolExecutor(
    max_workers=N_WORKERS,
    mp_context=multiprocessing.get_context('fork'),
    initializer=_init_worker,
    initargs=(all_bars,),
) as executor:
    raw = list(executor.map(_run_combo, combos, chunksize=10))

results = [r for r in raw if r is not None]
print(f"Done — {len(results)}/{total} combinations with trades.\n")

if not results:
    print("No trades fired in any combination.")
    sys.exit(0)


# ── Display tables ────────────────────────────────────────────────────────────
def show_table(rows, title, sort_key, min_trades=15):
    pool = [r for r in rows if r['trades'] >= min_trades] or rows
    print(f"\n{'='*105}")
    print(f" Top 25 by {title}  (≥{min_trades} trades)")
    print(f"{'='*105}")
    print(f"{'move':>5} {'w_st':>4} {'w_end':>5} {'fn':>3} {'pb':>4} {'session':>7} | "
          f"{'trades':>6} {'wr%':>6} {'totalR':>7} {'expect':>7} {'pf':>5} {'maxDD':>6}")
    print('-' * 105)
    for r in sorted(pool, key=lambda x: x[sort_key], reverse=True)[:25]:
        print(
            f"{r['min_move']:>5d} {r['w_start']:>4d} {r['w_end']:>5d} "
            f"{r['fn']:>3d} {r['max_pb']:>4.0f} {r['session']:>7s} | "
            f"{r['trades']:>6d} {r['wr']:>6.1f} {r['total_r']:>7.1f} "
            f"{r['expect']:>7.3f} {r['pf']:>5.2f} {r['max_dd']:>6.1f}"
        )

show_table(results, 'Expectancy',    'expect')
show_table(results, 'Total R',       'total_r')
show_table(results, 'Profit Factor', 'pf')
