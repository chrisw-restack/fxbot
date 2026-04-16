"""
Walk-forward validation runner.

Splits historical data into rolling train/test windows, optimizes parameters
on each training window, then validates on unseen test data.

Usage:
    python walk_forward.py ema_fib_retracement
    python walk_forward.py ebp
    python walk_forward.py the_strat
    python walk_forward.py the_strat_m15
"""

import argparse
import itertools
import io
import contextlib
import logging
import multiprocessing
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime

import config
from backtest_engine import BacktestEngine
from data.historical_loader import find_csv, load_and_merge, filter_bars
from strategies.ema_fib_retracement import EmaFibRetracementStrategy
from strategies.the_strat import TheStratStrategy
from strategies.ebp import EbpStrategy
from strategies.ims import ImsStrategy
from strategies.ebp_limit import EbpLimitStrategy
from strategies.breakout import BreakoutStrategy
from strategies.ema_fib_retracement_intraday import EmaFibRetracementIntradayStrategy
from strategies.ema_fib_running import EmaFibRunningStrategy
from strategies.gaussian_channel import GaussianChannelStrategy
from strategies.smc_reversal import SmcReversalStrategy
from strategies.three_line_strike import ThreeLineStrikeStrategy
from strategies.hourly_mean_reversion import HourlyMeanReversionStrategy

logging.basicConfig(level=logging.ERROR)
sys.stdout.reconfigure(line_buffering=True)

# ── Settings ─────────────────────────────────────────────────────────────────
SYMBOLS         = ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDJPY', 'USDCAD', 'USDCHF', 'XAUUSD']
INITIAL_BALANCE = 10_000.0
RR_RATIO        = 2.0

# Walk-forward windows
TRAIN_YEARS = 4
TEST_YEARS  = 2
STEP_YEARS  = 2      # how far to advance between folds

# Optimization target
OPTIMIZATION_METRIC = 'expectancy'   # 'expectancy', 'total_r', or 'pf'
MIN_TRADES = 50                      # minimum trades for a param combo to qualify

RISK_PCT_OVERRIDES = {}
N_WORKERS = 1  # parallel workers (keep 1 to avoid hammering the PC)

# ── Strategy configs ─────────────────────────────────────────────────────────
STRATEGY_CONFIGS = {
    'ema_fib_retracement': {
        'class': EmaFibRetracementStrategy,
        'timeframes': ['D1', 'H1'],
        'symbols': ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDJPY', 'USDCAD', 'USDCHF'],
        'fixed_params': {
            'blocked_hours': (*range(20, 24), *range(0, 9)),  # allow 09:00-19:00 UTC
        },
        'param_grid': {
            'fib_entry':                [0.5, 0.618, 0.786],
            'fib_tp':                   [2.0, 2.5, 3.0],
            'min_swing_pips':           [10, 20],
            'ema_sep_pct':              [0.0, 0.001],
            'cooldown_bars':            [0, 10],
            'invalidate_swing_on_loss': [True, False],
        },
    },
    'ebp': {
        'class': EbpStrategy,
        'timeframes': ['H4', 'H1'],
        'symbols': ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDJPY', 'USDCAD', 'USDCHF', 'XAUUSD'],
        'fixed_params': {
            'tf_bias': 'H4', 'tf_entry': 'H1',
            'min_retrace_pct': 0.1,  # sweep showed minimal impact
        },
        'param_grid': {
            'fractal_n':       [1, 2, 3],
            'max_retrace_pct': [0.5, 0.618, 0.75],
            'require_fvg':     [True, False],
            'sl_mode':         ['mss_bar', 'structural'],
        },
    },
    'ebp_h1m15': {
        'class': EbpStrategy,
        'timeframes': ['H1', 'M15'],
        'symbols': ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDJPY', 'USDCAD', 'USDCHF', 'XAUUSD'],
        'fixed_params': {
            'tf_bias': 'H1', 'tf_entry': 'M15',
            'min_retrace_pct': 0.1,  # sweep showed minimal impact
        },
        'param_grid': {
            'fractal_n':       [1, 2, 3],
            'max_retrace_pct': [0.5, 0.618, 0.75],
            'require_fvg':     [True, False],
            'sl_mode':         ['mss_bar', 'structural'],
        },
    },
    'the_strat': {
        'class': TheStratStrategy,
        'timeframes': ['D1', 'H4', 'H1'],
        'param_grid': {
            'bias_types':    [
                frozenset({'2-1-2_rev', '3-1-2', '1-2-2'}),       # rev_only
                frozenset({'2-1-2_rev', '3-1-2', '1-2-2', '3'}),  # no_cont
                frozenset({'2-1-2_rev', '3-1-2'}),                  # strong
            ],
            'min_sl_pips':   [5, 8, 15],
            'cooldown_bars': [0, 3, 6],
            'fractal_n':     [2, 3],
        },
        'fixed_params': {
            'tf_bias': 'D1', 'tf_intermediate': 'H4', 'tf_entry': 'H1',
        },
    },
    'ims_d1_h4': {
        'class': ImsStrategy,
        'timeframes': ['D1', 'H4'],
        'fixed_params': {
            'tf_htf': 'D1', 'tf_ltf': 'H4',
            'ltf_fractal_n': 2,
            'tp_mode': 'htf_high',
            'ema_fast': 20, 'ema_slow': 50,
        },
        'param_grid': {
            'fractal_n':    [1, 2],
            'htf_lookback': [30, 50, 80],
            'cooldown_bars': [0, 3],
        },
    },
    'ims_h4_m15': {
        'class': ImsStrategy,
        'timeframes': ['H4', 'M15'],
        'symbols': ['USDJPY', 'XAUUSD', 'EURAUD', 'CADJPY', 'USDCAD', 'AUDUSD', 'EURUSD', 'GBPCAD', 'GBPUSD'],
        'fixed_params': {
            'tf_htf': 'H4', 'tf_ltf': 'M15',
            'entry_mode': 'pending',
            'tp_mode': 'rr',
            'blocked_hours': (*range(0, 12), *range(17, 24)),  # London/NY overlap 12-17 UTC
            'ema_fast': 20, 'ema_slow': 50,
            'ema_sep': 0.001,
            'cooldown_bars': 0,
            'fractal_n':     1,
            'ltf_fractal_n': 1,
            'htf_lookback':  30,
            'rr_ratio':      2.5,
        },
        'param_grid': {},
    },
    'ema_fib_running': {
        'class': EmaFibRunningStrategy,
        'timeframes': ['D1', 'H1'],
        'symbols': ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDJPY', 'USDCAD', 'USDCHF'],
        'fixed_params': {
            'min_swing_pips': 30,
            'cooldown_bars': 0,
            'invalidate_swing_on_loss': True,
            'blocked_hours': (*range(20, 24), *range(0, 9)),  # 09:00-19:00 UTC (session sweep winner)
        },
        'param_grid': {
            'fib_entry':   [0.618, 0.786],
            'fib_tp':      [2.0, 2.5, 3.0],
            'fractal_n':   [2, 3],
            'ema_sep_pct': [0.0, 0.001],
        },
    },
    'ema_fib_intraday': {
        'class': EmaFibRetracementIntradayStrategy,
        'timeframes': ['H4', 'M15'],
        'fixed_params': {
            'fib_entry': 0.786,
            'ema_sep_pct': 0.001,
        },
        'param_grid': {
            'min_swing_pips': [10, 20, 30],
            'cooldown_bars':  [0, 10],
        },
    },
    'breakout': {
        'class': BreakoutStrategy,
        'timeframes': ['H1'],
        'fixed_params': {},
        'param_grid': {
            'lookback': [50, 100, 150, 200],
        },
    },
    'ebp_limit_h4': {
        'class': EbpLimitStrategy,
        'timeframes': ['D1', 'H4'],
        'fixed_params': {
            'tf': 'H4', 'tf_trend': 'D1', 'entry_pct': 0.382,
            'max_sl_pips': 80,
        },
        'param_grid': {
            'min_range_pips': [40, 60, 80],
            'ema_fast':       [10, 20],
            'ema_slow':       [20, 50],
        },
    },
    'gaussian_channel': {
        'class': GaussianChannelStrategy,
        'timeframes': ['H4'],
        'fixed_params': {},
        'param_grid': {
            'period':        [72, 144, 288],
            'poles':         [2, 3, 4],
            'tr_mult':       [1.0, 1.414, 2.0],
            'cooldown_bars': [0, 3, 6],
        },
    },
    'the_strat_m15': {
        'class': TheStratStrategy,
        'timeframes': ['H4', 'H1', 'M15'],
        'param_grid': {
            'bias_types':    [
                frozenset({'2-1-2_rev', '3-1-2', '1-2-2'}),       # rev_only
                frozenset({'2-1-2_rev', '3-1-2', '1-2-2', '3'}),  # no_cont
                frozenset({'2-1-2_rev', '3-1-2'}),                  # strong
            ],
            'min_sl_pips':   [5, 10, 15, 20],
            'cooldown_bars': [0, 3, 6],
            'fractal_n':     [2, 3],
        },
        'fixed_params': {
            'tf_bias': 'H4', 'tf_intermediate': 'H1', 'tf_entry': 'M15',
        },
    },
    'engulfing': {
        'class': ThreeLineStrikeStrategy,
        'timeframes': ['M5'],
        'symbols': ['EURUSD', 'AUDUSD', 'USDCAD'],  # USDJPY/NZDUSD removed 2026-04-15 (session sweep: negative IS across all sessions)
        'min_trades': 15,   # ~3 pairs × ~3–5 trades/yr each in a 4yr IS window
        'fixed_params': {
            'allowed_hours': tuple(range(13, 18)),  # NY session only
            'sma_sep_pips': 5.0,
            'sl_mode': 'fractal',
            'fractal_n': 3,
        },
        'param_grid': {
            'min_prev_body_pips': [0.0, 3.0, 5.0],
            'engulf_ratio':       [1.0, 1.5, 2.0],
            'max_sl_pips':        [15, 20],
            'rr_ratio':           [2.0, 2.5],
        },
    },
    # ── Engulfing single-symbol / alternative-session configs ────────────────
    # Session sweep (2026-04-15) showed GBPUSD positive in London, negative in NY.
    # USDCAD has better expectancy in London than in NY core.
    # AUDUSD NY extended (13–20) outperformed NY core (13–17).
    # min_trades=5 — single-symbol configs fire ~1–5 trades/yr, 4yr IS window.
    'engulfing_gbpusd_london_open': {
        'class': ThreeLineStrikeStrategy,
        'timeframes': ['M5'],
        'symbols': ['GBPUSD'],
        'min_trades': 5,
        'fixed_params': {
            'allowed_hours': tuple(range(7, 11)),   # London open 07–10 UTC
            'sma_sep_pips': 5.0,
            'sl_mode': 'fractal',
            'fractal_n': 3,
        },
        'param_grid': {
            'min_prev_body_pips': [0.0, 3.0, 5.0],
            'engulf_ratio':       [1.0, 1.5, 2.0],
            'max_sl_pips':        [15, 20],
            'rr_ratio':           [2.0, 2.5],
        },
    },
    'engulfing_gbpusd_london_core': {
        'class': ThreeLineStrikeStrategy,
        'timeframes': ['M5'],
        'symbols': ['GBPUSD'],
        'min_trades': 5,
        'fixed_params': {
            'allowed_hours': tuple(range(8, 13)),   # London core 08–12 UTC
            'sma_sep_pips': 5.0,
            'sl_mode': 'fractal',
            'fractal_n': 3,
        },
        'param_grid': {
            'min_prev_body_pips': [0.0, 3.0, 5.0],
            'engulf_ratio':       [1.0, 1.5, 2.0],
            'max_sl_pips':        [15, 20],
            'rr_ratio':           [2.0, 2.5],
        },
    },
    'engulfing_audusd_ny_extended': {
        'class': ThreeLineStrikeStrategy,
        'timeframes': ['M5'],
        'symbols': ['AUDUSD'],
        'min_trades': 5,
        'fixed_params': {
            'allowed_hours': tuple(range(13, 21)),  # NY extended 13–20 UTC
            'sma_sep_pips': 5.0,
            'sl_mode': 'fractal',
            'fractal_n': 3,
        },
        'param_grid': {
            'min_prev_body_pips': [0.0, 3.0, 5.0],
            'engulf_ratio':       [1.0, 1.5, 2.0],
            'max_sl_pips':        [15, 20],
            'rr_ratio':           [2.0, 2.5],
        },
    },
    'engulfing_usdcad_london_core': {
        'class': ThreeLineStrikeStrategy,
        'timeframes': ['M5'],
        'symbols': ['USDCAD'],
        'min_trades': 5,
        'fixed_params': {
            'allowed_hours': tuple(range(8, 13)),   # London core 08–12 UTC
            'sma_sep_pips': 5.0,
            'sl_mode': 'fractal',
            'fractal_n': 3,
        },
        'param_grid': {
            'min_prev_body_pips': [0.0, 3.0, 5.0],
            'engulf_ratio':       [1.0, 1.5, 2.0],
            'max_sl_pips':        [15, 20],
            'rr_ratio':           [2.0, 2.5],
        },
    },
    'engulfing_usdcad_london_ny': {
        'class': ThreeLineStrikeStrategy,
        'timeframes': ['M5'],
        'symbols': ['USDCAD'],
        'min_trades': 5,
        'fixed_params': {
            'allowed_hours': tuple(range(8, 18)),   # London+NY 08–17 UTC
            'sma_sep_pips': 5.0,
            'sl_mode': 'fractal',
            'fractal_n': 3,
        },
        'param_grid': {
            'min_prev_body_pips': [0.0, 3.0, 5.0],
            'engulf_ratio':       [1.0, 1.5, 2.0],
            'max_sl_pips':        [15, 20],
            'rr_ratio':           [2.0, 2.5],
        },
    },
    'hmr': {
        'class': HourlyMeanReversionStrategy,
        'timeframes': ['M5'],
        'symbols': ['XAUUSD'],
        'min_trades': 8,
        'fixed_params': {
            'tf_lower': 'M5',
            'session_hours': tuple(range(8, 17)),  # London
        },
        'param_grid': {
            'min_move_pips':      [50, 75, 100, 150],
            'entry_window_start': [20, 25],
            'entry_window_end':   [40, 45, 50],
            'fractal_n':          [1, 2],
            'max_pullback_pips':  [0, 50],
        },
    },
    'hmr_fx': {
        # HMR on all 7 USD major FX pairs — pooled for trade count.
        # FX pip sizes are 0.0001 (or 0.01 for JPY), so min_move is in FX pips.
        # A 15-pip move on EURUSD in 20 min = ~$15 directional H1 candle.
        'class': HourlyMeanReversionStrategy,
        'timeframes': ['M5'],
        'symbols': ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDJPY', 'USDCAD', 'USDCHF'],
        'min_trades': 10,
        'fixed_params': {
            'tf_lower': 'M5',
            'session_hours': tuple(range(8, 17)),  # London session
            'pip_sizes': {
                'EURUSD': 0.0001, 'GBPUSD': 0.0001, 'AUDUSD': 0.0001,
                'NZDUSD': 0.0001, 'USDJPY': 0.01,   'USDCAD': 0.0001,
                'USDCHF': 0.0001,
            },
        },
        'param_grid': {
            'min_move_pips':      [10, 15, 20, 30],
            'entry_window_start': [20, 25],
            'entry_window_end':   [40, 45, 50],
            'fractal_n':          [1, 2],
            'max_pullback_pips':  [0, 50],
        },
    },
    'hmr_usa100': {
        # HMR on USA100 (Nasdaq) — primary active window is NY session.
        # 1 pip = 1 index point. move=100 → 100-point run in 20 min.
        'class': HourlyMeanReversionStrategy,
        'timeframes': ['M5'],
        'symbols': ['USA100'],
        'min_trades': 8,
        'fixed_params': {
            'tf_lower': 'M5',
            # London open (8-13) + NY session (13-21) — Nasdaq active when US open
            'session_hours': tuple(range(8, 21)),
            'pip_sizes': {'USA100': 1.0},
        },
        'param_grid': {
            'min_move_pips':      [75, 100, 150, 200],
            'entry_window_start': [20, 25],
            'entry_window_end':   [40, 45, 50],
            'fractal_n':          [1, 2],
            'max_pullback_pips':  [0, 50],
        },
    },
    'hmr_m1': {
        # HMR on XAUUSD M1 with ATR volatility gate (Option 3, 2026-04-09).
        # Asian WF FAIL, London WF WEAK, D1 bias WF WEAK — all regime-sensitive.
        # ATR gate: skip signals when prior-day ATR > threshold (trending = bad).
        # Low ATR = ranging/choppy day → mean-reversion conditions we want.
        # Standalone test (no D1 bias), focused grid (dropping move=50, fn=1, start=15).
        'class': HourlyMeanReversionStrategy,
        'timeframes': ['D1', 'M1'],
        'symbols': ['XAUUSD'],
        'min_trades': 20,
        'fixed_params': {
            'tf_lower': 'M1',
            'session_hours': tuple(range(8, 17)),  # London
            'use_d1_bias': False,
            'atr_period': 14,
        },
        'param_grid': {
            'min_move_pips':      [75, 100, 150],
            'entry_window_start': [20, 25],
            'entry_window_end':   [35, 40, 45, 50],
            'fractal_n':          [2, 3, 5],
            'max_pullback_pips':  [0, 25],
            'atr_max_pips':       [0, 200, 300, 400],
        },
    },
    # ICT-style SMC reversal across all 3 US equity indices.
    # Multi-symbol expands trade count from ~6/yr (USTEC only) to ~18/yr.
    'smc_reversal': {
        'class': SmcReversalStrategy,
        'timeframes': ['D1', 'H4', 'H1', 'M15', 'M5'],
        'symbols': ['USTEC', 'US30', 'US500'],
        'min_trades': 30,   # ~3 symbols × ~10 trades each per IS window
        'fixed_params': {
            'ob_max_per_tf': 3,
        },
        'param_grid': {
            'fractal_n':                [2, 3, 5],
            'fvg_window':               [2, 4, 6],
            'wiggle_room_pct':          [0.0, 0.002, 0.003, 0.006],
            'sl_buffer_pct':            [0.0003, 0.0006, 0.001],
            'multiple_trades_per_bias': [True, False],
        },
    },
}


# ── Parallel IS optimisation worker ──────────────────────────────────────────
# Module-level so ProcessPoolExecutor can pickle it.

_WF_BARS = None  # set once per worker process via initializer


def _init_wf_worker(bars):
    global _WF_BARS
    _WF_BARS = bars


def _run_wf_combo(args):
    """Run one param combo on the pre-loaded training bars. Returns merged params+metrics dict.

    If 'rr_ratio' appears in params or fixed_params it is extracted and passed to the
    BacktestEngine rather than the strategy constructor (RR is an engine param, not a
    strategy param).
    """
    params, strategy_class, fixed_params, symbols = args
    try:
        full_params = {**fixed_params, **params}
        rr = full_params.pop('rr_ratio', RR_RATIO)
        strategy = strategy_class(**full_params)
        m = run_backtest(
            _WF_BARS, strategy, symbols,
            INITIAL_BALANCE, rr, config.BACKTEST_SPREAD_PIPS, RISK_PCT_OVERRIDES,
        )
        return {**params, **m}
    except Exception:
        return {**params, 'trades': 0, 'win_rate': 0, 'total_r': 0,
                'expectancy': 0, 'pf': 0, 'max_dd_r': 0,
                'worst_loss_streak': 0, 'best_win_streak': 0}


# ── Core functions ───────────────────────────────────────────────────────────

def generate_folds(
    data_start: datetime, data_end: datetime,
    train_years: int, test_years: int, step_years: int,
) -> list[dict]:
    """Generate rolling train/test fold date ranges."""
    folds = []
    fold_num = 1
    year = data_start.year

    while True:
        train_start = datetime(year, 1, 1)
        train_end   = datetime(year + train_years, 1, 1)
        test_start  = train_end
        test_end    = datetime(year + train_years + test_years, 1, 1)

        if test_end > data_end + __import__('datetime').timedelta(days=90):
            # Allow up to 90 days past data end to not waste the last partial fold
            break

        folds.append({
            'fold': fold_num,
            'train_start': train_start,
            'train_end': train_end,
            'test_start': test_start,
            'test_end': min(test_end, data_end),
        })
        fold_num += 1
        year += step_years

    return folds


def run_backtest(bars: list, strategy, symbols: list[str],
                 initial_balance: float, rr_ratio: float,
                 spread_pips: dict[str, float] | float = config.BACKTEST_SPREAD_PIPS,
                 risk_pct_overrides: dict | None = None) -> dict:
    """Run a single backtest on pre-filtered bars. Returns metrics dict."""
    engine = BacktestEngine(
        initial_balance=initial_balance,
        rr_ratio=rr_ratio,
        spread_pips=spread_pips,
        risk_pct_overrides=risk_pct_overrides,
    )
    engine.add_strategy(strategy, symbols=symbols)

    with contextlib.redirect_stdout(io.StringIO()):
        for bar in bars:
            closed_trades = engine.execution.check_fills(bar)
            for trade in closed_trades:
                engine.portfolio.record_close(trade['symbol'], trade['pnl'], trade.get('strategy_name', ''))
                engine.trade_logger.log_close(trade['ticket'], trade)
                engine.event_engine.notify_trade_closed(trade)
            engine.event_engine.process_bar(bar)

    trades = engine.execution.get_closed_trades()
    return compute_metrics(trades)


def compute_metrics(trades: list[dict]) -> dict:
    """Compute performance metrics from a list of closed trade dicts."""
    total = len(trades)
    if total == 0:
        return {
            'trades': 0, 'win_rate': 0, 'total_r': 0, 'expectancy': 0,
            'pf': 0, 'max_dd_r': 0, 'worst_loss_streak': 0, 'best_win_streak': 0,
        }

    wins = sum(1 for t in trades if t['result'] == 'WIN')
    total_r = sum(t['r_multiple'] for t in trades)
    gp = sum(t['r_multiple'] for t in trades if t['result'] == 'WIN')
    gl = abs(sum(t['r_multiple'] for t in trades if t['result'] == 'LOSS'))

    peak = running = max_dd = 0.0
    for t in trades:
        running += t['r_multiple']
        peak = max(peak, running)
        max_dd = max(max_dd, peak - running)

    best_win = worst_loss = cur_win = cur_loss = 0
    for t in trades:
        if t['r_multiple'] > 0:
            cur_win += 1; cur_loss = 0
        else:
            cur_loss += 1; cur_win = 0
        best_win = max(best_win, cur_win)
        worst_loss = max(worst_loss, cur_loss)

    return {
        'trades': total,
        'win_rate': round(wins / total * 100, 1),
        'total_r': round(total_r, 1),
        'expectancy': round(total_r / total, 3),
        'pf': round(gp / gl, 2) if gl > 0 else 0.0,
        'max_dd_r': round(max_dd, 1),
        'worst_loss_streak': worst_loss,
        'best_win_streak': best_win,
    }


def optimize(all_bars, train_start, train_end, strategy_class,
             param_grid, fixed_params, symbols, metric, min_trades=MIN_TRADES, n_workers=1):
    """Optimize parameters on a training window. Returns best params and metrics."""
    train_bars = filter_bars(all_bars, start=train_start, end=train_end)

    keys = list(param_grid.keys())
    combos = [dict(zip(keys, c)) for c in itertools.product(*param_grid.values())]

    if n_workers > 1:
        task_args = [(params, strategy_class, fixed_params, symbols) for params in combos]
        with ProcessPoolExecutor(
            max_workers=n_workers,
            mp_context=multiprocessing.get_context('fork'),
            initializer=_init_wf_worker,
            initargs=(train_bars,),
        ) as executor:
            all_results = list(executor.map(_run_wf_combo, task_args))
    else:
        all_results = []
        for params in combos:
            full_params = {**fixed_params, **params}
            rr = full_params.pop('rr_ratio', RR_RATIO)
            strategy = strategy_class(**full_params)
            m = run_backtest(
                train_bars, strategy, symbols,
                INITIAL_BALANCE, rr, config.BACKTEST_SPREAD_PIPS, RISK_PCT_OVERRIDES,
            )
            all_results.append({**params, **m})

    best_score = -float('inf')
    best_params = None
    best_metrics = None

    for result in all_results:
        if result['trades'] < min_trades:
            continue
        score = result[metric]
        if score > best_score:
            best_score = score
            best_params = {k: result[k] for k in keys}
            best_metrics = {k: result[k] for k in result if k not in keys}

    return best_params, best_metrics, all_results


def test_oos(all_bars, test_start, test_end, strategy_class,
             best_params, fixed_params, symbols):
    """Test best parameters on out-of-sample window."""
    test_bars = filter_bars(all_bars, start=test_start, end=test_end)
    full_params = {**fixed_params, **best_params}
    rr = full_params.pop('rr_ratio', RR_RATIO)
    strategy = strategy_class(**full_params)

    return run_backtest(
        test_bars, strategy, symbols,
        INITIAL_BALANCE, rr, config.BACKTEST_SPREAD_PIPS, RISK_PCT_OVERRIDES,
    )


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Walk-forward validation.')
    parser.add_argument(
        'strategy', choices=STRATEGY_CONFIGS.keys(),
        help='Strategy to validate',
    )
    parser.add_argument(
        '--train-years', type=int, default=TRAIN_YEARS,
        help=f'Training window in years (default: {TRAIN_YEARS})',
    )
    parser.add_argument(
        '--test-years', type=int, default=TEST_YEARS,
        help=f'Test window in years (default: {TEST_YEARS})',
    )
    parser.add_argument(
        '--step-years', type=int, default=STEP_YEARS,
        help=f'Step between folds in years (default: {STEP_YEARS})',
    )
    parser.add_argument(
        '--metric', choices=['expectancy', 'total_r', 'pf'],
        default=OPTIMIZATION_METRIC,
        help=f'Metric to optimize (default: {OPTIMIZATION_METRIC})',
    )
    parser.add_argument(
        '--min-trades', type=int, default=MIN_TRADES,
        help=f'Minimum IS trades for a combo to qualify (default: {MIN_TRADES})',
    )
    parser.add_argument(
        '--workers', type=int, default=N_WORKERS,
        help=f'Parallel worker processes for IS optimisation (default: {N_WORKERS})',
    )
    args = parser.parse_args()

    cfg = STRATEGY_CONFIGS[args.strategy]
    strategy_class = cfg['class']
    param_grid = cfg['param_grid']
    fixed_params = cfg.get('fixed_params', {})
    timeframes = cfg['timeframes']
    symbols = cfg.get('symbols', SYMBOLS)
    min_trades = cfg.get('min_trades', args.min_trades)

    # ── Load all bar data once ───────────────────────────────────────────────
    print("Discovering CSV files...")
    csv_paths = []
    for sym in symbols:
        for tf in timeframes:
            paths = find_csv(sym, tf)
            if paths:
                csv_paths.extend(paths)
                for p in paths:
                    print(f"  Found: {p}")
            else:
                print(f"  WARNING: Missing {sym} {tf}")

    if not csv_paths:
        print("No CSV files found.")
        sys.exit(1)

    print("\nLoading bar data...")
    all_bars = load_and_merge(csv_paths)
    data_start = all_bars[0].timestamp
    data_end = all_bars[-1].timestamp
    print(f"Loaded {len(all_bars):,} bars ({data_start:%Y-%m-%d} to {data_end:%Y-%m-%d})")

    # ── Generate folds ───────────────────────────────────────────────────────
    folds = generate_folds(data_start, data_end, args.train_years, args.test_years, args.step_years)
    n_combos = 1
    for v in param_grid.values():
        n_combos *= len(v)
    print(f"\n{len(folds)} folds × {n_combos} param combos = {len(folds) * n_combos} total runs")

    # ── Walk forward ─────────────────────────────────────────────────────────
    fold_results = []

    for fold in folds:
        print(f"\n{'='*90}")
        print(f"FOLD {fold['fold']}:  Train {fold['train_start']:%Y-%m-%d} → {fold['train_end']:%Y-%m-%d}  |  "
              f"Test {fold['test_start']:%Y-%m-%d} → {fold['test_end']:%Y-%m-%d}")
        print(f"{'='*90}")

        # Optimize on training window
        print(f"  Optimizing ({n_combos} combos, metric={args.metric}, min_trades={min_trades}, workers={args.workers})...")
        best_params, is_metrics, _ = optimize(
            all_bars, fold['train_start'], fold['train_end'],
            strategy_class, param_grid, fixed_params, symbols, args.metric,
            min_trades=min_trades, n_workers=args.workers,
        )

        if best_params is None:
            print(f"  No valid params found (all had < {min_trades} trades). Skipping fold.")
            continue

        params_str = ', '.join(f'{k}={v}' for k, v in best_params.items())
        print(f"  Best params: {params_str}")
        print(f"  In-sample:  trades={is_metrics['trades']}  WR={is_metrics['win_rate']}%  "
              f"R={is_metrics['total_r']:+.1f}  PF={is_metrics['pf']:.2f}  "
              f"Expect={is_metrics['expectancy']:+.3f}  DD={is_metrics['max_dd_r']:.1f}R  "
              f"LStreak={is_metrics['worst_loss_streak']}")

        # Test on out-of-sample window
        oos_metrics = test_oos(
            all_bars, fold['test_start'], fold['test_end'],
            strategy_class, best_params, fixed_params, symbols,
        )

        print(f"  Out-of-sample: trades={oos_metrics['trades']}  WR={oos_metrics['win_rate']}%  "
              f"R={oos_metrics['total_r']:+.1f}  PF={oos_metrics['pf']:.2f}  "
              f"Expect={oos_metrics['expectancy']:+.3f}  DD={oos_metrics['max_dd_r']:.1f}R  "
              f"LStreak={oos_metrics['worst_loss_streak']}")

        # Degradation check
        if is_metrics['expectancy'] > 0:
            retention = oos_metrics['expectancy'] / is_metrics['expectancy'] * 100
            print(f"  OOS retention: {retention:.0f}% of IS expectancy")
        else:
            retention = None

        fold_results.append({
            'fold': fold['fold'],
            'train': f"{fold['train_start']:%Y-%m-%d} → {fold['train_end']:%Y-%m-%d}",
            'test':  f"{fold['test_start']:%Y-%m-%d} → {fold['test_end']:%Y-%m-%d}",
            'best_params': best_params,
            'is': is_metrics,
            'oos': oos_metrics,
            'retention': retention,
        })

    # ── Summary ──────────────────────────────────────────────────────────────
    if not fold_results:
        print("\nNo valid folds. Check data range and window sizes.")
        return

    print(f"\n\n{'='*130}")
    print(f"{'WALK-FORWARD SUMMARY':^130}")
    print(f"{'='*130}")
    print(f"{'Fold':<5} {'Test Period':<27} {'Params':<40} "
          f"{'IS R':>7} {'OOS R':>7} {'IS Exp':>7} {'OOS Exp':>8} {'OOS WR':>7} {'OOS PF':>7} {'Retain':>7}")
    print(f"{'-'*130}")

    total_oos_r = 0
    total_oos_trades = 0
    retentions = []

    for fr in fold_results:
        params_short = ', '.join(f'{k}={v}' for k, v in fr['best_params'].items())
        if len(params_short) > 38:
            params_short = params_short[:35] + '...'
        ret_str = f"{fr['retention']:.0f}%" if fr['retention'] is not None else 'N/A'
        print(f"{fr['fold']:<5} {fr['test']:<27} {params_short:<40} "
              f"{fr['is']['total_r']:>+7.1f} {fr['oos']['total_r']:>+7.1f} "
              f"{fr['is']['expectancy']:>+7.3f} {fr['oos']['expectancy']:>+8.3f} "
              f"{fr['oos']['win_rate']:>6.1f}% {fr['oos']['pf']:>7.2f} {ret_str:>7}")

        total_oos_r += fr['oos']['total_r']
        total_oos_trades += fr['oos']['trades']
        if fr['retention'] is not None:
            retentions.append(fr['retention'])

    print(f"{'-'*130}")

    avg_retention = sum(retentions) / len(retentions) if retentions else 0
    avg_oos_expect = total_oos_r / total_oos_trades if total_oos_trades else 0

    print(f"\n  Aggregate OOS:  {total_oos_trades} trades  |  {total_oos_r:+.1f}R total  |  "
          f"{avg_oos_expect:+.3f}R expectancy")
    print(f"  Avg OOS retention: {avg_retention:.0f}% of in-sample expectancy")

    if avg_retention >= 70:
        verdict = "STRONG — strategy is robust, parameters generalize well"
    elif avg_retention >= 40:
        verdict = "MODERATE — some overfitting, but strategy has edge out-of-sample"
    elif avg_retention > 0:
        verdict = "WEAK — significant overfitting, parameters don't generalize well"
    else:
        verdict = "FAIL — strategy loses money out-of-sample, likely curve-fit"

    print(f"\n  Verdict: {verdict}")
    print(f"{'='*130}")


if __name__ == '__main__':
    main()
