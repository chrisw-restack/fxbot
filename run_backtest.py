"""
Backtest runner.

Usage:
    python run_backtest.py breakout
    python run_backtest.py ema_fib_retracement
    python run_backtest.py the_strat
    python run_backtest.py live_suite          # current live/demo suite together
    python run_backtest.py ema_fib_retracement --start-date 2023-01-01 --end-date 2024-06-30
"""

import argparse
import logging
from datetime import datetime
import config

from backtest_engine import BacktestEngine
from live_config import create_live_strategy_specs
from strategies.breakout import BreakoutStrategy
from strategies.mean_reversion import MeanReversionStrategy
from strategies.ema_fib_retracement import EmaFibRetracementStrategy
from strategies.ema_fib_retracement_intraday import EmaFibRetracementIntradayStrategy
from strategies.ict_judas_swing import IctJudasSwingStrategy
from strategies.gaussian_channel import GaussianChannelStrategy
from strategies.the_strat import TheStratStrategy
from strategies.supply_demand import SupplyDemandStrategy
from strategies.keltner_reversion import KeltnerReversionStrategy
from strategies.range_fade import RangeFadeStrategy
from strategies.ema_fib_running import EmaFibRunningStrategy
from strategies.ebp import EbpStrategy
from strategies.ebp_limit import EbpLimitStrategy
from strategies.ims import ImsStrategy
from strategies.ims_reversal import ImsReversalStrategy
from strategies.smc_zone import SmcZoneStrategy
from strategies.bigbeluga_sd import BigBelugaSdStrategy
from strategies.smc_reversal import SmcReversalStrategy
from strategies.three_line_strike import ThreeLineStrikeStrategy
from strategies.hourly_mean_reversion import HourlyMeanReversionStrategy
from strategies.london_breakout import LondonBreakoutStrategy
from data.historical_loader import find_csv
from data.news_filter import NewsFilter

logging.basicConfig(
    level=logging.WARNING,   # Set to logging.INFO to see every bar/trade in the console
    format='%(asctime)s  %(levelname)-8s  %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

# ── Settings — edit these ─────────────────────────────────────────────────────
# ALL SYMBOLS         = ['AUDCAD','AUDJPY','AUDNZD','AUDUSD','CADJPY','EURAUD','EURCAD','EURCHF','EURGBP','EURJPY','EURUSD','GBPAUD','GBPCAD','GBPJPY','GBPNZD','GBPUSD','NZDJPY','NZDUSD','USA100','USA30','USA500','USDCAD','USDCHF','USDJPY','XAUUSD']

# LIVE SYMBOLS:
# EmaFibRetracementStrategy for ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDJPY', 'USDCAD', 'USDCHF']
# EmaFibRunningStrategy for ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDJPY', 'USDCAD', 'USDCHF']
# ThreeLineStrikeStrategy for ['EURUSD', 'AUDUSD', 'USDCAD']
# ImsStrategy for ['USDJPY', 'XAUUSD', 'EURAUD', 'CADJPY', 'USDCAD', 'AUDUSD', 'EURUSD', 'GBPCAD', 'GBPUSD']

# SYMBOLS         = ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDJPY', 'USDCAD', 'USDCHF', 'XAUUSD', 'USA100']
# SYMBOLS         = ['EURUSD', 'GBPUSD', 'AUDUSD' , 'USDJPY', 'USDCAD', 'GBPCAD' ]
# SYMBOLS         = ['AUDCAD','AUDJPY','AUDNZD','AUDUSD','CADJPY','EURAUD','EURCAD','EURCHF','EURGBP','EURJPY','EURUSD','GBPAUD','GBPCAD','GBPJPY','GBPNZD','GBPUSD','NZDJPY','NZDUSD','USA100','USA30','USA500','USDCAD','USDCHF','USDJPY','XAUUSD']
# SYMBOLS         = ['AUDUSD','CADJPY']
# SYMBOLS         = ['EURAUD','EURCAD','EURCHF','EURGBP','EURJPY']
SYMBOLS         = ['EURUSD', 'GBPUSD']  # LBS initial test

INITIAL_BALANCE = 10_000.0   # starting account balance in USD
RR_RATIO        = 2.5        # risk/reward ratio (overrides config default)
RISK_PCT_OVERRIDES = {}
# ─────────────────────────────────────────────────────────────────────────────

STRATEGIES = {
    'breakout':             BreakoutStrategy(lookback=20),
    'mean_reversion':       MeanReversionStrategy(lookback=20, std_multiplier=2.0, sl_lookback=5),
    'ema_fib_retracement':  EmaFibRetracementStrategy(fib_entry=0.786,fib_tp=3.0,fractal_n=3,min_swing_pips=10,ema_sep_pct=0.001,cooldown_bars=10,invalidate_swing_on_loss=True,blocked_hours=(*range(20,24),*range(0,9))),
    'ema_fib_retracement_intraday': EmaFibRetracementIntradayStrategy(cooldown_bars=10,invalidate_swing_on_loss=True,min_swing_pips=15,ema_sep_pct=0.0005),
    'ict_judas_swing':              IctJudasSwingStrategy(fractal_n=3, min_sl_pips=15, max_sl_pips=30, min_sweep_pips=2.0, require_sweep_pullback=True, require_fvg=False, require_d1_bias=False),
    'gaussian_channel':             GaussianChannelStrategy(period=144, poles=4, tr_mult=1.414),
    'the_strat':                    TheStratStrategy(min_sl_pips=8, cooldown_bars=3),
    'the_strat_m15':                TheStratStrategy(min_sl_pips=5, cooldown_bars=3, tf_bias='H4', tf_intermediate='H1', tf_entry='M15'),
    'supply_demand':                SupplyDemandStrategy(),
    'keltner_reversion':            KeltnerReversionStrategy(),
    'range_fade':                   RangeFadeStrategy(),
    'ema_fib_running':              EmaFibRunningStrategy(fib_entry=0.786, fib_tp=2.5, fractal_n=2, min_swing_pips=30, ema_sep_pct=0.0, cooldown_bars=0, invalidate_swing_on_loss=True, blocked_hours=(*range(20,24),*range(0,9))),
    'ebp':                          EbpStrategy(tf_bias='H4', tf_entry='H1', fractal_n=2, min_retrace_pct=0.382, max_retrace_pct=0.618, require_fvg=False),
    'ebp_mss_sl':                   EbpStrategy(tf_bias='H4', tf_entry='H1', fractal_n=2, min_retrace_pct=0.382, max_retrace_pct=0.618, require_fvg=False, sl_mode='mss_bar'),
    'ebp_symmetric_sl':             EbpStrategy(tf_bias='H4', tf_entry='H1', fractal_n=2, min_retrace_pct=0.382, max_retrace_pct=0.618, require_fvg=False, sl_mode='symmetric'),
    'ebp_limit_h4':                 EbpLimitStrategy(tf='H4'),
    'ebp_limit_h1':                 EbpLimitStrategy(tf='H1'),
    'ebp_limit_d1':                 EbpLimitStrategy(tf='D1'),
    'ebp_limit_h4_ema':             EbpLimitStrategy(tf='H4', min_range_pips=60, entry_pct=0.382, tf_trend='D1', ema_fast=10, ema_slow=20),
    'ims_d1_h4':                    ImsStrategy(tf_htf='D1', tf_ltf='H4', fractal_n=1, ltf_fractal_n=2, htf_lookback=50, tp_mode='htf_high', cooldown_bars=0, ema_fast=20, ema_slow=50),
    'ims_d1_h4_market':             ImsStrategy(tf_htf='D1', tf_ltf='H4', fractal_n=1, ltf_fractal_n=2, htf_lookback=50, entry_mode='market', tp_mode='htf_high', cooldown_bars=0, ema_fast=20, ema_slow=50),
    'ims_h4_h1':                    ImsStrategy(tf_htf='H4', tf_ltf='H1', fractal_n=1, ltf_fractal_n=2, htf_lookback=50, tp_mode='htf_high', cooldown_bars=0, ema_fast=20, ema_slow=50),
    'ims_h4_m15':                   ImsStrategy(tf_htf='H4', tf_ltf='M15', fractal_n=1, ltf_fractal_n=1, htf_lookback=30, entry_mode='pending', tp_mode='rr', rr_ratio=2.5, cooldown_bars=0, blocked_hours=(*range(0, 12), *range(17, 24)), ema_fast=20, ema_slow=50, ema_sep=0.001),
    'ims_reversal_h4_m15':          ImsReversalStrategy(tf_htf='H4', tf_ltf='M15', fractal_n=1, ltf_fractal_n=1, htf_lookback=30, tp_mode='htf_pct', htf_tp_pct=0.5, rr_ratio=2.5, cooldown_bars=0, blocked_hours=(*range(0, 12), *range(17, 24)), ema_fast=20, ema_slow=50, ema_sep=0.001),
    'ims_reversal_h4_m15_rr':       ImsReversalStrategy(tf_htf='H4', tf_ltf='M15', fractal_n=1, ltf_fractal_n=1, htf_lookback=30, tp_mode='rr',     htf_tp_pct=0.5, rr_ratio=2.5, cooldown_bars=0, blocked_hours=(*range(0, 12), *range(17, 24)), ema_fast=20, ema_slow=50, ema_sep=0.001),
    'ims_reversal_d1_h4':           ImsReversalStrategy(tf_htf='D1', tf_ltf='H4',  fractal_n=1, ltf_fractal_n=1, htf_lookback=30, tp_mode='htf_pct', htf_tp_pct=0.5, rr_ratio=2.5, cooldown_bars=0, blocked_hours=(*range(0, 12), *range(17, 24)), ema_fast=20, ema_slow=50, ema_sep=0.001),
    # Validated config: lf2, htf_pct 0.5, ln_us session, EMA 20/50, ml=1, 8 symbols (−CADJPY/USDJPY/EURUSD)
    'ims_reversal_best':            ImsReversalStrategy(tf_htf='H4', tf_ltf='M15', fractal_n=1, ltf_fractal_n=2, htf_lookback=30, tp_mode='htf_pct', htf_tp_pct=0.5, rr_ratio=2.5, cooldown_bars=0, blocked_hours=(*range(0, 12), *range(17, 24)), ema_fast=20, ema_slow=50, ema_sep=0.001, max_losses_per_bias=1, pip_sizes=dict(config.PIP_SIZE)),
    'smc_zone':                     SmcZoneStrategy(swing_length=3,  tf_entry='H1', zone_atr_mult=0.4, sl_buffer_atr=0.5, d1_ema_period=50, blocked_hours=(*range(20,24),*range(0,9))),
    'smc_zone_h1_sl10':             SmcZoneStrategy(swing_length=10, tf_entry='H1', zone_atr_mult=0.4, sl_buffer_atr=0.5, d1_ema_period=50, blocked_hours=(*range(20,24),*range(0,9))),
    'smc_zone_h4':                  SmcZoneStrategy(swing_length=3, tf_entry='H4', zone_atr_mult=2.0, sl_buffer_atr=0.5, zone_leg_atr=0.0, d1_ema_period=50, blocked_hours=(*range(20,24),*range(0,9))),
    'smc_zone_h4_leg15':            SmcZoneStrategy(swing_length=3, tf_entry='H4', zone_atr_mult=2.0, sl_buffer_atr=0.5, zone_leg_atr=1.5, d1_ema_period=50, blocked_hours=(*range(20,24),*range(0,9))),
    'smc_zone_h4_leg20':            SmcZoneStrategy(swing_length=3, tf_entry='H4', zone_atr_mult=2.0, sl_buffer_atr=0.5, zone_leg_atr=2.0, d1_ema_period=50, blocked_hours=(*range(20,24),*range(0,9))),
    'smc_zone_h4_leg25':            SmcZoneStrategy(swing_length=3, tf_entry='H4', zone_atr_mult=2.0, sl_buffer_atr=0.5, zone_leg_atr=2.5, d1_ema_period=50, blocked_hours=(*range(20,24),*range(0,9))),
    'bigbeluga_h4':                 BigBelugaSdStrategy(tf_entry='H4', atr_period=200, zone_atr_mult=2.0, sl_buffer_atr=0.5, require_volume=True,  d1_ema_period=50, cooldown_bars=15, blocked_hours=(*range(20,24),*range(0,9))),
    'bigbeluga_h4_novol':           BigBelugaSdStrategy(tf_entry='H4', atr_period=200, zone_atr_mult=2.0, sl_buffer_atr=0.5, require_volume=False, d1_ema_period=50, cooldown_bars=15, blocked_hours=(*range(20,24),*range(0,9))),
    'smc_reversal':                 SmcReversalStrategy(fractal_n=3, fvg_window=4, ob_max_per_tf=3, wiggle_room_pct=0.003, sl_buffer_pct=0.0006, multiple_trades_per_bias=True),
    'smc_reversal_single':          SmcReversalStrategy(fractal_n=3, fvg_window=4, ob_max_per_tf=3, wiggle_room_pct=0.003, sl_buffer_pct=0.0006, multiple_trades_per_bias=False),
    'three_line_strike':            ThreeLineStrikeStrategy(sl_mode='fractal', fractal_n=3, min_prev_body_pips=3.0, engulf_ratio=1.5, max_sl_pips=15, allowed_hours=tuple(range(13,18)), sma_sep_pips=5.0, pip_sizes={'USDJPY': 0.01}),
    # WF-validated params (XAUUSD M5, London session, STRONG): all 3 folds +, +0.265R OOS expect
    'hmr':    HourlyMeanReversionStrategy(tf_lower='M5',  min_move_pips=100, entry_window_start=20, entry_window_end=45, fractal_n=1, max_pullback_pips=0,  session_hours=tuple(range(8,17))),
    'hmr_m1': HourlyMeanReversionStrategy(tf_lower='M1',  min_move_pips=100, entry_window_start=20, entry_window_end=45, fractal_n=2, max_pullback_pips=30, session_hours=tuple(range(8,17))),
    'lbs':         LondonBreakoutStrategy(rr_ratio=2.5),
}

ALL_CHOICES = list(STRATEGIES.keys()) + ['live_suite']

parser = argparse.ArgumentParser(description='Run a backtest for a given strategy.')
parser.add_argument(
    'strategy',
    choices=ALL_CHOICES,
    help='Strategy to backtest: ' + ', '.join(ALL_CHOICES),
)
parser.add_argument(
    '--news-filter', choices=['off', 'high', 'high-medium', 'major'],
    default='off',
    help=(
        'News event filter mode: '
        'off = disabled (default), '
        'high = block all high-impact news, '
        'high-medium = block high and medium impact, '
        'major = block only NFP/CPI/FOMC/rate decisions'
    ),
)
parser.add_argument(
    '--news-hours-before', type=float, default=4.0,
    help='Hours before a news event to block signals (default: 4)',
)
parser.add_argument(
    '--news-hours-after', type=float, default=1.0,
    help='Hours after a news event to block signals (default: 1)',
)
parser.add_argument(
    '--start-date', type=str, default=None,
    help='Start date for backtest (YYYY-MM-DD). Default: use all available data.',
)
parser.add_argument(
    '--end-date', type=str, default=None,
    help='End date for backtest (YYYY-MM-DD). Default: use all available data.',
)
parser.add_argument(
    '--breakeven-at-r', type=float, default=None,
    help='Move SL to break-even once price reaches N×R in profit (e.g. 2.0, 3.0, 5.0). Default: off.',
)
parser.add_argument(
    '--data-source', choices=['dukascopy', 'histdata'],
    default='dukascopy',
    help='Historical data source. dukascopy uses data/historical; histdata uses data/historical/histdata.',
)
parser.add_argument(
    '--symbols', nargs='+', default=None,
    help='Optional symbol override, e.g. --symbols EURUSD. For live_suite this filters each strategy to matching symbols.',
)
args = parser.parse_args()

if args.symbols:
    requested_symbols = {symbol.upper() for symbol in args.symbols}

if args.strategy == 'live_suite':
    strategy_specs = create_live_strategy_specs()
    if args.symbols:
        strategy_specs = [
            (strategy, [symbol for symbol in symbols if symbol.upper() in requested_symbols])
            for strategy, symbols in strategy_specs
        ]
        strategy_specs = [(strategy, symbols) for strategy, symbols in strategy_specs if symbols]
else:
    symbols = [symbol.upper() for symbol in args.symbols] if args.symbols else SYMBOLS
    strategy_specs = [(STRATEGIES[args.strategy], symbols)]

# Collect all timeframes needed across all strategies
csv_paths = []
seen_paths = set()
for strategy, symbols in strategy_specs:
    for symbol in symbols:
        for tf in strategy.TIMEFRAMES:
            paths = find_csv(symbol, tf, data_source=args.data_source)
            if paths:
                for p in paths:
                    if p not in seen_paths:
                        csv_paths.append(p)
                        seen_paths.add(p)
                        print(f"Found: {p}")
            else:
                print(f"WARNING: No CSV found for {symbol} {tf} in data/historical/ — skipping")

if not csv_paths:
    print("\nNo CSV files found. Run fetch_data.py on your Windows VPS first.")
    raise SystemExit(1)

# ── News filter setup ────────────────────────────────────────────────────────
news_filter = None
if args.news_filter != 'off':
    MAJOR_KEYWORDS = [
        'Non-Farm', 'NFP', 'CPI', 'FOMC', 'Interest Rate Decision',
        'Federal Funds Rate', 'Monetary Policy', 'ECB Press Conference',
        'BOE Interest', 'RBA Rate', 'RBNZ Rate', 'BOC Rate', 'BOJ Policy',
    ]

    filter_config = {
        'high':        {'impact_levels': {'HIGH'}, 'event_keywords': None},
        'high-medium': {'impact_levels': {'HIGH', 'MEDIUM'}, 'event_keywords': None},
        'major':       {'impact_levels': {'HIGH'}, 'event_keywords': MAJOR_KEYWORDS},
    }
    cfg = filter_config[args.news_filter]
    news_filter = NewsFilter(
        block_hours_before=args.news_hours_before,
        block_hours_after=args.news_hours_after,
        impact_levels=cfg['impact_levels'],
        event_keywords=cfg['event_keywords'],
    )
    if news_filter.is_loaded:
        print(f"\nNews filter: {args.news_filter} "
              f"(block {args.news_hours_before}h before, {args.news_hours_after}h after)")
    else:
        print("\nWARNING: News filter requested but calendar data not found. "
              "Run: python fetch_news_data.py")
        news_filter = None

engine = BacktestEngine(
    initial_balance=INITIAL_BALANCE, rr_ratio=RR_RATIO,
    news_filter=news_filter, risk_pct_overrides=RISK_PCT_OVERRIDES,
    breakeven_at_r=args.breakeven_at_r,
    max_open_trades=config.MAX_OPEN_TRADES if args.strategy == 'live_suite' else 99,
    max_daily_loss_pct=config.MAX_DAILY_LOSS_PCT if args.strategy == 'live_suite' else None,
)
for strategy, symbols in strategy_specs:
    engine.add_strategy(strategy, symbols=symbols)
start_date = datetime.strptime(args.start_date, '%Y-%m-%d') if args.start_date else None
end_date = datetime.strptime(args.end_date, '%Y-%m-%d') if args.end_date else None

if start_date or end_date:
    date_range = f"{args.start_date or 'start'} to {args.end_date or 'end'}"
    print(f"\nDate range: {date_range}")
print(f"\nData source: {args.data_source}")

engine.run(csv_paths, start_date=start_date, end_date=end_date)
