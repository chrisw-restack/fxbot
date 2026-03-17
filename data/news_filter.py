"""
News event filter for backtesting and live trading.

Loads the Forex Factory calendar CSV and provides methods to check whether
a signal should be blocked due to upcoming/recent high-impact news.

Usage:
    from data.news_filter import NewsFilter

    nf = NewsFilter(
        csv_path='data/news/forex_factory_calendar.csv',
        block_hours_before=4,
        block_hours_after=1,
        impact_levels={'HIGH'},
    )

    # Check a single signal
    blocked = nf.is_blocked(symbol='EURUSD', timestamp=some_datetime)

    # Or check with specific event names only
    nf_targeted = NewsFilter(
        csv_path='data/news/forex_factory_calendar.csv',
        block_hours_before=4,
        block_hours_after=1,
        impact_levels={'HIGH'},
        event_keywords=['Non-Farm', 'NFP', 'CPI', 'FOMC', 'Interest Rate'],
    )
"""

import logging
import os
from bisect import bisect_left, bisect_right
from datetime import datetime, timedelta

import pandas as pd

logger = logging.getLogger(__name__)

# Map symbol to the currencies affected by news for that pair
SYMBOL_CURRENCIES = {
    'EURUSD': ['EUR', 'USD'],
    'GBPUSD': ['GBP', 'USD'],
    'AUDUSD': ['AUD', 'USD'],
    'NZDUSD': ['NZD', 'USD'],
    'USDJPY': ['USD', 'JPY'],
    'USDCAD': ['USD', 'CAD'],
}

DEFAULT_CSV = os.path.join('data', 'news', 'forex_factory_calendar.csv')


class NewsFilter:
    """
    Blocks signals that fall within a configurable window around news events.

    Parameters
    ----------
    csv_path : str
        Path to the normalized Forex Factory calendar CSV.
    block_hours_before : float
        Hours before a news event to start blocking signals.
    block_hours_after : float
        Hours after a news event to keep blocking signals.
    impact_levels : set[str]
        Which impact levels to filter on. Default: {'HIGH'}.
    event_keywords : list[str] | None
        If provided, only block on events whose name contains one of these
        keywords (case-insensitive). If None, block on all events matching
        the impact level.
    """

    def __init__(
        self,
        csv_path: str = DEFAULT_CSV,
        block_hours_before: float = 4.0,
        block_hours_after: float = 1.0,
        impact_levels: set[str] | None = None,
        event_keywords: list[str] | None = None,
    ):
        self.block_before = timedelta(hours=block_hours_before)
        self.block_after = timedelta(hours=block_hours_after)
        self.impact_levels = impact_levels or {'HIGH'}
        self.event_keywords = (
            [kw.lower() for kw in event_keywords] if event_keywords else None
        )

        # Load and index events by currency for fast lookup
        # _events[currency] = sorted list of (datetime, event_name)
        self._events: dict[str, list[tuple[datetime, str]]] = {}
        # _timestamps[currency] = sorted list of datetimes (for bisect)
        self._timestamps: dict[str, list[datetime]] = {}

        self._load(csv_path)

    def _load(self, csv_path: str):
        """Load the calendar CSV and build lookup indexes."""
        if not os.path.exists(csv_path):
            logger.warning(
                f"News calendar not found at {csv_path} — "
                f"news filter will be disabled. Run fetch_news_data.py first."
            )
            return

        df = pd.read_csv(csv_path, parse_dates=['datetime_utc'])

        # Filter by impact level
        df = df[df['impact'].isin(self.impact_levels)]

        # Filter by event keywords if specified
        if self.event_keywords:
            mask = df['event'].str.lower().apply(
                lambda name: any(kw in name for kw in self.event_keywords)
            )
            df = df[mask]

        # Build per-currency indexes
        for currency, group in df.groupby('currency'):
            events = sorted(
                zip(group['datetime_utc'].tolist(), group['event'].tolist())
            )
            self._events[currency] = events
            self._timestamps[currency] = [e[0] for e in events]

        total = sum(len(v) for v in self._events.values())
        logger.info(f"NewsFilter loaded {total} events across {len(self._events)} currencies")

    @property
    def is_loaded(self) -> bool:
        """True if calendar data was successfully loaded."""
        return len(self._events) > 0

    def is_blocked(self, symbol: str, timestamp: datetime) -> bool:
        """
        Check if a signal for `symbol` at `timestamp` should be blocked
        due to a nearby news event.

        Returns True if blocked, False if clear.
        """
        if not self._events:
            return False

        currencies = SYMBOL_CURRENCIES.get(symbol, [])
        window_start = timestamp - self.block_before
        window_end = timestamp + self.block_after

        for ccy in currencies:
            ts_list = self._timestamps.get(ccy)
            if not ts_list:
                continue

            # Find events in [window_start, window_end] using binary search
            left = bisect_left(ts_list, window_start)
            right = bisect_right(ts_list, window_end)

            if left < right:
                # At least one event in the window
                event_time, event_name = self._events[ccy][left]
                logger.debug(
                    f"NewsFilter blocked {symbol} at {timestamp}: "
                    f"{ccy} {event_name} at {event_time}"
                )
                return True

        return False

    def get_nearby_events(
        self, symbol: str, timestamp: datetime
    ) -> list[tuple[datetime, str, str]]:
        """
        Return all events within the block window for a symbol at a given time.
        Returns list of (datetime, currency, event_name).
        """
        if not self._events:
            return []

        currencies = SYMBOL_CURRENCIES.get(symbol, [])
        window_start = timestamp - self.block_before
        window_end = timestamp + self.block_after
        results = []

        for ccy in currencies:
            ts_list = self._timestamps.get(ccy)
            if not ts_list:
                continue

            left = bisect_left(ts_list, window_start)
            right = bisect_right(ts_list, window_end)

            for i in range(left, right):
                event_time, event_name = self._events[ccy][i]
                results.append((event_time, ccy, event_name))

        return sorted(results)
