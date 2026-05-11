"""Validated live/demo strategy suite configuration."""

import config
from strategies.ema_fib_retracement import EmaFibRetracementStrategy
from strategies.ema_fib_running import EmaFibRunningStrategy
from strategies.three_line_strike import ThreeLineStrikeStrategy
from strategies.ims import ImsStrategy
from strategies.ims_reversal import ImsReversalStrategy
from strategies.failed2 import Failed2Strategy


IMS_SYMBOLS = ['USDJPY', 'XAUUSD', 'EURAUD', 'CADJPY', 'USDCAD', 'AUDUSD', 'EURUSD', 'GBPCAD', 'GBPUSD']
IMS_REV_SYMBOLS = ['GBPNZD', 'AUDUSD', 'US30', 'USDCHF', 'XAUUSD', 'AUDJPY', 'AUDCAD', 'USDCAD']
ENGULFING_SYMBOLS = ['EURUSD', 'AUDUSD']
FAILED2_SYMBOLS = ['USTEC']
FAILED2_NAME = 'Failed2_H4_H1_M5_market'


def create_live_strategy_specs():
    """Return [(strategy_instance, symbols), ...] for the current live/demo suite."""
    ema_fib = EmaFibRetracementStrategy(
        fib_entry=0.786,
        fib_tp=3.0,
        fractal_n=3,
        min_swing_pips=10,
        ema_sep_pct=0.001,
        cooldown_bars=10,
        invalidate_swing_on_loss=True,
        blocked_hours=(*range(20, 24), *range(0, 9)),
    )
    ema_fib_running = EmaFibRunningStrategy(
        fib_entry=0.786,
        fib_tp=2.5,
        fractal_n=2,
        min_swing_pips=30,
        ema_sep_pct=0.0,
        cooldown_bars=0,
        invalidate_swing_on_loss=True,
        blocked_hours=(*range(20, 24), *range(0, 9)),
    )
    engulfing = ThreeLineStrikeStrategy(
        sl_mode='fractal',
        fractal_n=3,
        min_prev_body_pips=3.0,
        engulf_ratio=1.5,
        max_sl_pips=15,
        allowed_hours=tuple(range(13, 18)),
        sma_sep_pips=5.0,
    )
    ims = ImsStrategy(
        tf_htf='H4',
        tf_ltf='M15',
        fractal_n=1,
        ltf_fractal_n=1,
        htf_lookback=30,
        entry_mode='pending',
        tp_mode='rr',
        rr_ratio=2.5,
        cooldown_bars=0,
        blocked_hours=(*range(0, 12), *range(17, 24)),
        ema_fast=20,
        ema_slow=50,
        ema_sep=0.001,
        sl_anchor='swing',
        pip_sizes={s: config.PIP_SIZE[s] for s in IMS_SYMBOLS if s in config.PIP_SIZE},
    )
    ims_reversal = ImsReversalStrategy(
        tf_htf='H4',
        tf_ltf='M15',
        fractal_n=1,
        ltf_fractal_n=2,
        htf_lookback=30,
        entry_mode='pending',
        tp_mode='htf_pct',
        htf_tp_pct=0.5,
        zone_pct=0.5,
        cooldown_bars=0,
        blocked_hours=(*range(0, 12), *range(17, 24)),
        ema_fast=20,
        ema_slow=50,
        ema_sep=0.001,
        sl_anchor='swing',
        sl_buffer_pips=0.0,
        max_losses_per_bias=1,
        pip_sizes={s: config.PIP_SIZE[s] for s in IMS_REV_SYMBOLS if s in config.PIP_SIZE},
    )
    failed2 = Failed2Strategy(
        tf_bias='H4',
        tf_intermediate='H1',
        tf_entry='M5',
        entry_mode='market',
        mss_fractal_n=4,
        sl_fractal_n=2,
        rr_ratio=4.0,
        blocked_hours=(*range(0, 13), *range(18, 24)),
        trend_filter='d1_ema',
        d1_range_filter='block_top_pct',
        d1_range_block_pct=0.7,
        pip_sizes={s: config.PIP_SIZE[s] for s in FAILED2_SYMBOLS if s in config.PIP_SIZE},
    )
    return [
        (ema_fib, config.SYMBOLS),
        (ema_fib_running, config.SYMBOLS),
        (engulfing, ENGULFING_SYMBOLS),
        (ims, IMS_SYMBOLS),
        (ims_reversal, IMS_REV_SYMBOLS),
        (failed2, FAILED2_SYMBOLS),
    ]


def live_risk_pct_overrides() -> dict[str, float]:
    """Per-strategy risk settings; empty means all strategies use config.RISK_PCT."""
    return {}


def live_strategy_names() -> list[str]:
    return [strategy.NAME for strategy, _ in create_live_strategy_specs()]


def live_symbols() -> list[str]:
    symbols = []
    for _, spec_symbols in create_live_strategy_specs():
        for symbol in spec_symbols:
            if symbol not in symbols:
                symbols.append(symbol)
    return symbols
