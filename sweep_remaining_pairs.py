"""
Runs the focused engulfing sweep across the 5 remaining major FX pairs.
Outputs the top 5 by expectancy and the session breakdown for each pair.

Pairs: EURUSD, NZDUSD, USDJPY, USDCAD, USDCHF
Fixed: sma_sep_pips=5, RR=2.0
Grid: sessions × candle sizing × SL mode × max_sl = 324 combos per pair
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

PAIRS = ['EURUSD', 'NZDUSD', 'USDJPY', 'USDCAD', 'USDCHF']
INITIAL_BALANCE = 10_000.0
RR_RATIO = 2.0
N_WORKERS = 2  # parallel workers

LONDON = tuple(range(7, 13))
NY     = tuple(range(13, 18))
BOTH   = tuple(range(7, 18))

SESSION_LABELS = {LONDON: 'London', NY: 'NY    ', BOTH: 'Both  '}

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

W = 175
HEADER = (
    f"{'session':>7} {'min_b':>5} {'eng_r':>5} {'sl_mode':>12} {'sl_m':>4} {'fn':>2} {'max_sl':>6} | "
    f"{'trades':>6} {'WR%':>6} {'TotalR':>8} {'PF':>6} {'Expect':>7} {'MaxDD':>6} {'Streak':>6}"
)


def fmt_row(r):
    return (
        f"{r['session']:>7} {r['min_body']:>5.1f} {r['eng_ratio']:>5.1f} "
        f"{r['sl_mode']:>12} {r['sl_mult']:>4.1f} {r['fractal_n']:>2} {r['max_sl']:>6.0f} | "
        f"{r['trades']:>6} {r['win_rate']:>5.1f}% {r['total_r']:>+8.1f} "
        f"{r['pf']:>6.2f} {r['expectancy']:>+7.3f} {r['max_dd_r']:>6.1f} {r['worst_streak']:>6}"
    )


# ── Worker (module-level so it's picklable) ───────────────────────────────────
_SWEEP_BARS   = None
_SWEEP_SYMBOL = None
_SWEEP_PIPS   = None


def _init_sweep_worker(bars, symbol, pip_sizes):
    global _SWEEP_BARS, _SWEEP_SYMBOL, _SWEEP_PIPS
    _SWEEP_BARS   = bars
    _SWEEP_SYMBOL = symbol
    _SWEEP_PIPS   = pip_sizes


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
            pip_sizes=_SWEEP_PIPS,
        )

        engine = BacktestEngine(initial_balance=INITIAL_BALANCE, rr_ratio=RR_RATIO)
        engine.add_strategy(strategy, symbols=[_SWEEP_SYMBOL])

        with contextlib.redirect_stdout(io.StringIO()):
            for bar in _SWEEP_BARS:
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


# ── Summary collector ────────────────────────────────────────────────────────
summary = []

for symbol in PAIRS:
    print(f"\n{'#'*W}")
    print(f"  {symbol}  —  {total} combinations across {N_WORKERS} workers")
    print(f"{'#'*W}")

    csv_paths = find_csv(symbol, 'M5')
    if not csv_paths:
        print(f"  No M5 data found for {symbol}, skipping.")
        continue

    pip_sizes = {'USDJPY': 0.01} if symbol == 'USDJPY' else {}
    all_bars = load_and_merge(csv_paths)
    print(f"  Loaded {len(all_bars)} bars — running...")

    if N_WORKERS > 1:
        with ProcessPoolExecutor(
            max_workers=N_WORKERS,
            mp_context=multiprocessing.get_context('fork'),
            initializer=_init_sweep_worker,
            initargs=(all_bars, symbol, pip_sizes),
        ) as executor:
            raw = list(executor.map(_run_combo, combos))
    else:
        _init_sweep_worker(all_bars, symbol, pip_sizes)
        raw = [_run_combo(c) for c in combos]

    results = [r for r in raw if r is not None]
    print(f"  Done — {len(results)} valid combinations")

    if not results:
        print("  No valid results.")
        continue

    # ── Top 5 by expectancy (min 30 trades) ──────────────────────────────────
    filtered = [r for r in results if r['trades'] >= 30]
    filtered.sort(key=lambda r: r['expectancy'], reverse=True)

    print(f"\n  TOP 5 BY EXPECTANCY  (min 30 trades, {len(results)} valid combos)")
    print(f"  {HEADER}")
    print(f"  {'-'*W}")
    for r in filtered[:5]:
        print(f"  {fmt_row(r)}")

    # ── Session breakdown ─────────────────────────────────────────────────────
    print(f"\n  SESSION BREAKDOWN  (best per window, min 30 trades)")
    print(f"  {HEADER}")
    print(f"  {'-'*W}")
    for label in ['London', 'NY    ', 'Both  ']:
        sess_rows = [r for r in results if r['session'] == label and r['trades'] >= 30]
        sess_rows.sort(key=lambda r: r['expectancy'], reverse=True)
        if sess_rows:
            print(f"  {fmt_row(sess_rows[0])}")

    if filtered:
        best = filtered[0]
        summary.append({'symbol': symbol, **best})


# ── Cross-pair summary ────────────────────────────────────────────────────────
print(f"\n\n{'='*W}")
print("CROSS-PAIR SUMMARY  —  best config per pair (min 30 trades, by expectancy)")
print(f"{'='*W}")
print(f"{'symbol':>7} {HEADER}")
print('-'*W)
summary.sort(key=lambda r: r['expectancy'], reverse=True)
for r in summary:
    print(f"{r['symbol']:>7} {fmt_row(r)}")
