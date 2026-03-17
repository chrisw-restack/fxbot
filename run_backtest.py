"""
Backtest runner.

Usage:
    python run_backtest.py breakout
    python run_backtest.py mean_reversion
    python run_backtest.py ema_fib_retracement
    python run_backtest.py ema_fib_retracement_intraday
    python run_backtest.py ict_judas_swing
"""

import argparse
import logging

from backtest_engine import BacktestEngine
from strategies.breakout import BreakoutStrategy
from strategies.mean_reversion import MeanReversionStrategy
from strategies.ema_fib_retracement import EmaFibRetracementStrategy
from strategies.ema_fib_retracement_intraday import EmaFibRetracementIntradayStrategy
from strategies.ict_judas_swing import IctJudasSwingStrategy
from data.historical_loader import find_csv
from data.news_filter import NewsFilter

logging.basicConfig(
    level=logging.WARNING,   # Set to logging.INFO to see every bar/trade in the console
    format='%(asctime)s  %(levelname)-8s  %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

# ── Settings — edit these ─────────────────────────────────────────────────────
SYMBOLS         = ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDJPY', 'USDCAD']
# SYMBOLS         = ['EURUSD', 'GBPUSD']
# SYMBOLS         = ['EURUSD']
INITIAL_BALANCE = 10_000.0   # starting account balance in USD
RR_RATIO        = 2.0        # risk/reward ratio (overrides config default)
SPREAD_PIPS     = 2.0        # simulated spread in pips (applied at entry)
# ─────────────────────────────────────────────────────────────────────────────

STRATEGIES = {
    'breakout':             BreakoutStrategy(lookback=20),
    'mean_reversion':       MeanReversionStrategy(lookback=20, std_multiplier=2.0, sl_lookback=5),
    'ema_fib_retracement':  EmaFibRetracementStrategy(cooldown_bars=10,invalidate_swing_on_loss=True,min_swing_pips=15,ema_sep_pct=0.0005),
    'ema_fib_retracement_intraday': EmaFibRetracementIntradayStrategy(cooldown_bars=10,invalidate_swing_on_loss=True,min_swing_pips=15,ema_sep_pct=0.0005),
    'ict_judas_swing':              IctJudasSwingStrategy(fractal_n=3, min_sl_pips=15, max_sl_pips=30, min_sweep_pips=2.0, require_sweep_pullback=True, require_fvg=False, require_d1_bias=False),
}

parser = argparse.ArgumentParser(description='Run a backtest for a given strategy.')
parser.add_argument(
    'strategy',
    choices=STRATEGIES.keys(),
    help='Strategy to backtest: ' + ', '.join(STRATEGIES.keys()),
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
args = parser.parse_args()

strategy = STRATEGIES[args.strategy]
timeframes_needed = strategy.TIMEFRAMES

csv_paths = []
for symbol in SYMBOLS:
    for tf in timeframes_needed:
        path = find_csv(symbol, tf)
        if path:
            csv_paths.append(path)
            print(f"Found: {path}")
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
    initial_balance=INITIAL_BALANCE, rr_ratio=RR_RATIO, spread_pips=SPREAD_PIPS,
    news_filter=news_filter,
)
engine.add_strategy(strategy, symbols=SYMBOLS)
engine.run(csv_paths)
