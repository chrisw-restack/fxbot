"""
Backtest runner.

Usage:
    python run_backtest.py breakout
    python run_backtest.py ema_fib_retracement
    python run_backtest.py the_strat
    python run_backtest.py live_suite          # all 3 live strategies together
    python run_backtest.py ema_fib_retracement --start-date 2023-01-01 --end-date 2024-06-30
"""

import argparse
import logging
from datetime import datetime

from backtest_engine import BacktestEngine
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
from data.historical_loader import find_csv
from data.news_filter import NewsFilter

logging.basicConfig(
    level=logging.WARNING,   # Set to logging.INFO to see every bar/trade in the console
    format='%(asctime)s  %(levelname)-8s  %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

# ── Settings — edit these ─────────────────────────────────────────────────────
# SYMBOLS         = ['XAUUSD']
# SYMBOLS         = ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDJPY', 'USDCAD', 'USDCHF', 'XAUUSD']
SYMBOLS         = ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDJPY', 'USDCAD', 'USDCHF']
# SYMBOLS         = [  'XAUUSD']
# SYMBOLS         = [  'USA100']
INITIAL_BALANCE = 10_000.0   # starting account balance in USD
RR_RATIO        = 2.0        # risk/reward ratio (overrides config default)
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
    'ema_fib_running':              EmaFibRunningStrategy(fib_entry=0.618, min_swing_pips=30, ema_sep_pct=0.001, cooldown_bars=0, invalidate_swing_on_loss=True),
    'ebp':                          EbpStrategy(tf_bias='H4', tf_entry='H1', fractal_n=2, min_retrace_pct=0.382, max_retrace_pct=0.618, require_fvg=False),
    'ebp_mss_sl':                   EbpStrategy(tf_bias='H4', tf_entry='H1', fractal_n=2, min_retrace_pct=0.382, max_retrace_pct=0.618, require_fvg=False, sl_mode='mss_bar'),
    'ebp_symmetric_sl':             EbpStrategy(tf_bias='H4', tf_entry='H1', fractal_n=2, min_retrace_pct=0.382, max_retrace_pct=0.618, require_fvg=False, sl_mode='symmetric'),
    'ebp_limit_h4':                 EbpLimitStrategy(tf='H4'),
    'ebp_limit_h1':                 EbpLimitStrategy(tf='H1'),
    'ebp_limit_d1':                 EbpLimitStrategy(tf='D1'),
    'ebp_limit_h4_ema':             EbpLimitStrategy(tf='H4', min_range_pips=60, entry_pct=0.382, tf_trend='D1', ema_fast=10, ema_slow=20),
    'ims_d1_h4':                    ImsStrategy(tf_htf='D1', tf_ltf='H4', fractal_n=1, ltf_fractal_n=2, htf_lookback=50, tp_mode='htf_high', cooldown_bars=0, ema_fast=20, ema_slow=50),
    'ims_h4_h1':                    ImsStrategy(tf_htf='H4', tf_ltf='H1', fractal_n=1, ltf_fractal_n=2, htf_lookback=50, tp_mode='htf_high', cooldown_bars=0, ema_fast=20, ema_slow=50),
    'ims_h4_m15':                   ImsStrategy(tf_htf='H4', tf_ltf='M15', fractal_n=1, ltf_fractal_n=2, htf_lookback=50, tp_mode='htf_high', cooldown_bars=0, ema_fast=20, ema_slow=50),
}

# ── Live suite: all 3 strategies run together ────────────────────────────────
# TheStrat suspended pending re-validation with corrected simulator
LIVE_SUITE = [
    EmaFibRetracementStrategy(fib_entry=0.786, fib_tp=3.0, fractal_n=3, min_swing_pips=10, ema_sep_pct=0.001, cooldown_bars=10, invalidate_swing_on_loss=True, blocked_hours=(*range(20,24),*range(0,9))),
]

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
args = parser.parse_args()

if args.strategy == 'live_suite':
    strategies_to_run = LIVE_SUITE
else:
    strategies_to_run = [STRATEGIES[args.strategy]]

# Collect all timeframes needed across all strategies
timeframes_needed = set()
for s in strategies_to_run:
    timeframes_needed.update(s.TIMEFRAMES)

csv_paths = []
for symbol in SYMBOLS:
    for tf in timeframes_needed:
        paths = find_csv(symbol, tf)
        if paths:
            csv_paths.extend(paths)
            for p in paths:
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
)
for s in strategies_to_run:
    engine.add_strategy(s, symbols=SYMBOLS)
start_date = datetime.strptime(args.start_date, '%Y-%m-%d') if args.start_date else None
end_date = datetime.strptime(args.end_date, '%Y-%m-%d') if args.end_date else None

if start_date or end_date:
    date_range = f"{args.start_date or 'start'} to {args.end_date or 'end'}"
    print(f"\nDate range: {date_range}")

engine.run(csv_paths, start_date=start_date, end_date=end_date)
