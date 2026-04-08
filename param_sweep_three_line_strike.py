"""
Parameter sweep for Engulfing strategy on GBPUSD M5.

Focused on four questions:
  1. Session window  — is London, NY, or both more profitable?
  2. Candle sizing   — min_prev_body_pips + engulf_ratio filter quality vs quantity
  3. SL placement    — fractal (n=3/5) vs bar_multiple (1.5×/2×)
  4. SL size limit   — does capping max_sl_pips help?

Fixed: sma_sep_pips=5, sma periods (21/50/200), rsi_period=14, RR=2.0

Grid:
  allowed_hours      — 3 session windows
  min_prev_body_pips — 3 values
  engulf_ratio       — 3 values
  sl_mode + params   — 4 meaningful SL configs (avoids redundant cross-product)
  max_sl_pips        — 3 values

Total: 3×3×3×4×3 = 324 combinations
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

SYMBOLS = ['GBPUSD']
INITIAL_BALANCE = 10_000.0
RR_RATIO = 2.0
N_WORKERS = 1  # parallel workers

# ── Session window options ───────────────────────────────────────────────────
LONDON = tuple(range(7, 13))    # 07-12 UTC
NY     = tuple(range(13, 18))   # 13-17 UTC
BOTH   = tuple(range(7, 18))    # 07-17 UTC

SESSION_LABELS = {
    LONDON: 'London',
    NY:     'NY    ',
    BOTH:   'Both  ',
}

# ── SL configs — defined explicitly to avoid redundant cross-product ─────────
SL_CONFIGS = [
    ('bar_multiple', 1.5, 3),
    ('bar_multiple', 2.0, 3),
    ('fractal',      2.0, 3),
    ('fractal',      2.0, 5),
]

SESSIONS         = [LONDON, NY, BOTH]
MIN_PREV_BODIES  = [0.0, 3.0, 5.0]
ENGULF_RATIOS    = [1.0, 1.5, 2.0]
MAX_SL_PIPS_LIST = [10, 15, 20]

combos = list(itertools.product(
    SESSIONS, MIN_PREV_BODIES, ENGULF_RATIOS, SL_CONFIGS, MAX_SL_PIPS_LIST
))
total = len(combos)


# ── Worker (module-level so it's picklable) ───────────────────────────────────
_BARS = None  # set once per worker via initializer


def _init_worker(bars):
    global _BARS
    _BARS = bars


def _run_combo(combo):
    session, min_body, eng_ratio, sl_cfg, max_sl = combo
    sl_mode, sl_mult, frac_n = sl_cfg

    try:
        strategy = ThreeLineStrikeStrategy(
            sma_sep_pips=5.0,
            allowed_hours=session,
            min_prev_body_pips=min_body,
            engulf_ratio=eng_ratio,
            sl_mode=sl_mode,
            sl_bar_multiplier=sl_mult,
            fractal_n=frac_n,
            max_sl_pips=max_sl,
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

        wins = sum(1 for t in trades if t['result'] == 'WIN')
        total_r = sum(t['r_multiple'] for t in trades)
        win_rate = wins / n * 100
        expectancy = total_r / n
        gp = sum(t['r_multiple'] for t in trades if t['result'] == 'WIN')
        gl = abs(sum(t['r_multiple'] for t in trades if t['result'] == 'LOSS'))
        pf = gp / gl if gl > 0 else 0.0

        peak, max_dd, running = 0.0, 0.0, 0.0
        for t in trades:
            running += t['r_multiple']
            peak = max(peak, running)
            max_dd = max(max_dd, peak - running)

        worst_streak, cur_streak = 0, 0
        for t in trades:
            if t['result'] == 'LOSS':
                cur_streak += 1
                worst_streak = max(worst_streak, cur_streak)
            else:
                cur_streak = 0

        return {
            'session':      SESSION_LABELS[session],
            'min_body':     min_body,
            'eng_ratio':    eng_ratio,
            'sl_mode':      sl_mode,
            'sl_mult':      sl_mult,
            'fractal_n':    frac_n,
            'max_sl':       max_sl,
            'trades':       n,
            'win_rate':     win_rate,
            'total_r':      total_r,
            'pf':           pf,
            'expectancy':   expectancy,
            'max_dd_r':     max_dd,
            'worst_streak': worst_streak,
        }
    except Exception:
        return None


# ── Load bar data ────────────────────────────────────────────────────────────
csv_paths = []
for symbol in SYMBOLS:
    csv_paths.extend(find_csv(symbol, 'M5'))

if not csv_paths:
    print("No M5 CSV files found.")
    sys.exit(1)

print("Loading bar data...")
all_bars = load_and_merge(csv_paths)
print(f"Loaded {len(all_bars)} bars")
print(f"Running {total} combinations across {N_WORKERS} workers...\n")

# ── Run in parallel ──────────────────────────────────────────────────────────
if N_WORKERS > 1:
    with ProcessPoolExecutor(
        max_workers=N_WORKERS,
        mp_context=multiprocessing.get_context('fork'),
        initializer=_init_worker,
        initargs=(all_bars,),
    ) as executor:
        raw = list(executor.map(_run_combo, combos))
else:
    _init_worker(all_bars)
    raw = [_run_combo(c) for c in combos]

results = [r for r in raw if r is not None]
print(f"Done — {len(results)} valid combinations\n")


# ── Display ──────────────────────────────────────────────────────────────────
W = 175
HEADER = (
    f"{'session':>7} {'min_b':>5} {'eng_r':>5} {'sl_mode':>12} {'sl_m':>4} {'fn':>2} {'max_sl':>6} | "
    f"{'trades':>6} {'WR%':>6} {'TotalR':>8} {'PF':>6} {'Expect':>7} {'MaxDD':>6} {'Streak':>6}"
)


def row(r):
    return (
        f"{r['session']:>7} {r['min_body']:>5.1f} {r['eng_ratio']:>5.1f} "
        f"{r['sl_mode']:>12} {r['sl_mult']:>4.1f} {r['fractal_n']:>2} {r['max_sl']:>6.0f} | "
        f"{r['trades']:>6} {r['win_rate']:>5.1f}% {r['total_r']:>+8.1f} "
        f"{r['pf']:>6.2f} {r['expectancy']:>+7.3f} {r['max_dd_r']:>6.1f} {r['worst_streak']:>6}"
    )


def print_table(title, rows, n=30):
    print(f"\n{'='*W}")
    print(title)
    print(f"{'='*W}")
    print(HEADER)
    print('-' * W)
    for r in rows[:n]:
        print(row(r))


# ── 1. Top by Expectancy (min 30 trades) ─────────────────────────────────────
filtered = [r for r in results if r['trades'] >= 30]
filtered.sort(key=lambda r: r['expectancy'], reverse=True)
print_table(f"TOP 30 BY EXPECTANCY  (min 30 trades, out of {len(results)} valid combinations)", filtered)

# ── 2. Top by Total R ────────────────────────────────────────────────────────
results.sort(key=lambda r: r['total_r'], reverse=True)
print_table(f"TOP 30 BY TOTAL R", results)

# ── 3. Top by Profit Factor (min 30 trades) ──────────────────────────────────
filtered.sort(key=lambda r: r['pf'], reverse=True)
print_table("TOP 20 BY PROFIT FACTOR  (min 30 trades)", filtered, n=20)

# ── 4. Risk-adjusted (min 30 trades, DD > 0) ─────────────────────────────────
for r in filtered:
    r['risk_adj'] = r['expectancy'] / r['max_dd_r'] if r['max_dd_r'] > 0 else 0.0
filtered.sort(key=lambda r: r['risk_adj'], reverse=True)
print_table("TOP 20 BY RISK-ADJUSTED  (expectancy / max_DD, min 30 trades)", filtered, n=20)

# ── 5. Session breakdown: best per session (min 30 trades) ───────────────────
print(f"\n{'='*W}")
print("BEST BY SESSION  (top 5 per window, sorted by expectancy, min 30 trades)")
print(f"{'='*W}")
print(HEADER)
print('-' * W)
for label in ['London', 'NY    ', 'Both  ']:
    sess_rows = [r for r in results if r['session'] == label and r['trades'] >= 30]
    sess_rows.sort(key=lambda r: r['expectancy'], reverse=True)
    for r in sess_rows[:5]:
        print(row(r))
    if sess_rows:
        print()
