"""Validated IC Markets demo strategy suite configuration.

The module and function names retain "live" for compatibility. Nothing in
this file authorizes real-money trading.
"""

import config
from strategies.three_line_strike import ThreeLineStrikeStrategy
from strategies.ims import ImsStrategy
from strategies.ims_reversal import ImsReversalStrategy
from strategies.failed2 import Failed2Strategy
from strategies.candle_confirmation import CandleConfirmationStrategy
from strategies.ny_index_opening_drive import NyIndexOpeningDriveStrategy


IMS_SYMBOLS = ['USDJPY', 'EURAUD', 'CADJPY', 'USDCAD', 'AUDUSD', 'EURUSD', 'GBPCAD', 'GBPUSD']
# Forward-demo research candidate. Treat data after 2026-07-14 as unseen.
IMS_REV_SYMBOLS = ['EURUSD']
ENGULFING_SYMBOLS = ['EURUSD', 'AUDUSD']
FAILED2_SYMBOLS = ['USTEC']
FAILED2_NAME = 'Failed2_H4_H1_M5_market'
NY_INDEX_OPENING_DRIVE_SYMBOLS = ['USTEC']
CANDLE_CONFIRMATION_GBPUSD_SYMBOLS = ['GBPUSD']


def create_live_strategy_specs():
    """Return strategy and symbol pairs for the current demo suite."""
    # EmaFibRetracement retired from DEMO on 2026-09-25 after corrected broker validation.
    # EmaFibRunning retired from DEMO on 2026-09-28 after corrected rolling validation.
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
        blocked_hours=(*range(0, 13), *range(16, 24)),
        trend_filter='d1_ema',
        d1_range_filter='block_top_pct',
        d1_range_block_pct=0.7,
        pip_sizes={s: config.PIP_SIZE[s] for s in FAILED2_SYMBOLS if s in config.PIP_SIZE},
    )
    ny_index_opening_drive = NyIndexOpeningDriveStrategy(
        tf_entry='M5',
        opening_start_hour=9,
        opening_start_minute=30,
        opening_minutes=30,
        entry_cutoff_hour=12,
        entry_cutoff_minute=0,
        min_drive_pips=40,
        max_drive_pips=250,
        min_drive_body_pct=0.30,
        retrace_min_pct=0.382,
        retrace_max_pct=0.618,
        fractal_n=1,
        rr_ratio=3.0,
        sl_buffer_pips=5.0,
        max_sl_pips=180,
        trend_filter='d1_h1_ema',
        d1_range_filter='block_top_pct',
        d1_range_block_pct=0.8,
        pip_sizes={s: config.PIP_SIZE[s] for s in NY_INDEX_OPENING_DRIVE_SYMBOLS if s in config.PIP_SIZE},
    )
    # Candle Confirmation USDJPY retired from new DEMO runs on 2026-09-30.
    # Keep the GBPUSD candidate unchanged while recovery-only remains research.
    candle_confirmation_gbpusd = CandleConfirmationStrategy(
        name='CandleConfirmation_GBPUSD_H1_M5',
        tf_bias='H1',
        tf_entry='M5',
        fractal_n=3,
        retrace_pct=0.5,
        tp_range_pct=1.5,
        sl_rr_ratio=2.0,
        sl_mode='symmetric',
        require_fvg=True,
        min_sl_pips=8.0,
        tf_trend='D1',
        ema_fast=20,
        ema_slow=50,
        ema_sep_pct=0.001,
        min_engulf_range_pips=8.0,
        min_engulf_body_pct=0.6,
        close_extreme_pct=1.0,
        require_engulf_color=False,
        pip_sizes={s: config.PIP_SIZE[s] for s in CANDLE_CONFIRMATION_GBPUSD_SYMBOLS if s in config.PIP_SIZE},
    )
    return [
        (engulfing, ENGULFING_SYMBOLS),
        (ims, IMS_SYMBOLS),
        (ims_reversal, IMS_REV_SYMBOLS),
        (failed2, FAILED2_SYMBOLS),
        (ny_index_opening_drive, NY_INDEX_OPENING_DRIVE_SYMBOLS),
        (candle_confirmation_gbpusd, CANDLE_CONFIRMATION_GBPUSD_SYMBOLS),
    ]


def live_risk_pct_overrides() -> dict[str, float]:
    """Per-strategy risk settings; empty means all strategies use config.RISK_PCT."""
    return {
        'NYIndexOpeningDrive': 0.0025,
    }


def live_strategy_names() -> list[str]:
    return [strategy.NAME for strategy, _ in create_live_strategy_specs()]


def live_symbols() -> list[str]:
    symbols = []
    for _, spec_symbols in create_live_strategy_specs():
        for symbol in spec_symbols:
            if symbol not in symbols:
                symbols.append(symbol)
    return symbols
