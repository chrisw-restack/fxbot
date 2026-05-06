import os
import logging
from datetime import datetime, timedelta

import pandas as pd

from models import BarEvent

logger = logging.getLogger(__name__)


def _is_us_dst(dt: datetime) -> bool:
    """Check if a date falls within US DST (second Sunday March to first Sunday November)."""
    year = dt.year
    mar1 = datetime(year, 3, 1)
    dst_start_day = 1 + (6 - mar1.weekday()) % 7 + 7  # second Sunday
    dst_start = datetime(year, 3, dst_start_day)

    nov1 = datetime(year, 11, 1)
    dst_end_day = 1 + (6 - nov1.weekday()) % 7  # first Sunday
    dst_end = datetime(year, 11, dst_end_day)

    return dst_start <= dt.replace(hour=0, minute=0, second=0) < dst_end


def _server_to_utc(dt: datetime) -> datetime:
    """Convert ICMarkets server time to UTC. Server is UTC+3 during DST, UTC+2 outside."""
    offset = 3 if _is_us_dst(dt) else 2
    return dt - timedelta(hours=offset)


def load_csv(filepath: str) -> list[BarEvent]:
    """
    Load a historical CSV and return a list of BarEvents sorted by timestamp.

    The symbol and timeframe are inferred from the filename convention:
        <SYMBOL>_<TF>_<START>-<END>.csv  e.g. EURUSD_H1_20230101-20240101.csv
    """
    filename = os.path.basename(filepath)
    parts = filename.replace('.csv', '').split('_')
    if len(parts) < 2:
        raise ValueError(f"Cannot infer symbol/timeframe from filename: {filename}")

    symbol = parts[0]
    timeframe = parts[1]

    df = pd.read_csv(filepath, parse_dates=['time'])

    # ── Validate CSV structure ────────────────────────────────────────────────
    required_cols = {'time', 'open', 'high', 'low', 'close'}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"CSV {filename} is missing required columns: {', '.join(sorted(missing))}")

    if df.empty:
        raise ValueError(f"CSV {filename} contains no data rows")

    if df[list(required_cols)].isnull().any().any():
        nan_counts = df[list(required_cols)].isnull().sum()
        bad = {col: int(n) for col, n in nan_counts.items() if n > 0}
        logger.warning(f"CSV {filename} has NaN values in: {bad} — dropping affected rows")
        df = df.dropna(subset=list(required_cols))

    invalid_bars = df[df['high'] < df['low']]
    if len(invalid_bars) > 0:
        logger.warning(f"CSV {filename} has {len(invalid_bars)} bars where high < low — dropping them")
        df = df[df['high'] >= df['low']]

    dupes = df.duplicated(subset=['time'], keep='first')
    if dupes.any():
        logger.warning(f"CSV {filename} has {dupes.sum()} duplicate timestamps — keeping first occurrence")
        df = df[~dupes]

    df = df.sort_values('time').reset_index(drop=True)

    # Support both 'volume' and 'tick_volume' column names
    vol_col = 'volume' if 'volume' in df.columns else 'tick_volume'
    if vol_col not in df.columns:
        logger.warning(f"CSV {filename} has no volume column — defaulting to 0")
        df[vol_col] = 0

    # Detect whether data is already UTC (Dukascopy) or server time (MT5/ICMarkets).
    # UTC data has Sunday bars (market opens ~22:00 UTC Sunday); server-time data never does.
    has_sunday = (df['time'].dt.dayofweek == 6).any()
    if has_sunday:
        logger.info(f"CSV {filename} appears to be UTC (has Sunday bars) — no conversion needed")
    else:
        logger.info(f"CSV {filename} appears to be server time — converting to UTC")
        df['time'] = df['time'].apply(lambda t: _server_to_utc(t.to_pydatetime()))

    # Filter out weekend D1 bars from Dukascopy data.
    # Dukascopy generates D1 bars for Saturdays/Sundays with minimal volume.
    # These don't exist on MT5/ICMarkets and distort EMA calculations.
    if timeframe == 'D1':
        weekend_mask = df['time'].dt.dayofweek >= 5  # Saturday=5, Sunday=6
        n_weekend = weekend_mask.sum()
        if n_weekend > 0:
            logger.info(f"CSV {filename}: dropping {n_weekend} weekend D1 bars")
            df = df[~weekend_mask].reset_index(drop=True)

    events = [
        BarEvent(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=row['time'],
            open=float(row['open']),
            high=float(row['high']),
            low=float(row['low']),
            close=float(row['close']),
            volume=float(row[vol_col]),
        )
        for _, row in df.iterrows()
    ]

    logger.info(f"Loaded {len(events)} bars from {filepath} ({symbol} {timeframe})")
    return events


DATA_SOURCE_DIRS = {
    'dukascopy': 'data/historical',
    'histdata': 'data/historical/histdata',
}


def find_csv(
    symbol: str,
    timeframe: str,
    path: str = 'data/historical',
    data_source: str | None = None,
) -> list[str]:
    """
    Find all CSVs matching the given symbol and timeframe in the given directory.
    Returns a list of full filepaths (sorted alphabetically), or an empty list.

    Multiple files for the same symbol/timeframe are supported — load_and_merge
    handles deduplication of any overlapping bars automatically.
    """
    if data_source is not None:
        path = DATA_SOURCE_DIRS.get(data_source, os.path.join('data', 'historical', data_source))

    if not os.path.isdir(path):
        return []

    prefix = f"{symbol}_{timeframe}_"
    matches = sorted(
        [f for f in os.listdir(path) if f.startswith(prefix) and f.endswith('.csv')],
    )
    return [os.path.join(path, m) for m in matches]


def filter_bars(
    bars: list[BarEvent],
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[BarEvent]:
    """Filter a pre-loaded bar list to a date range [start, end). Inclusive start, exclusive end."""
    result = bars
    if start is not None:
        result = [b for b in result if b.timestamp >= start]
    if end is not None:
        result = [b for b in result if b.timestamp < end]
    return result


_TF_DURATION = {
    'M1': timedelta(minutes=1),
    'M5': timedelta(minutes=5),
    'M15': timedelta(minutes=15),
    'M30': timedelta(minutes=30),
    'H1': timedelta(hours=1),
    'H4': timedelta(hours=4),
    'D1': timedelta(days=1),
}


def bar_close_time(bar: BarEvent) -> datetime:
    """Return the close time of a bar (open time + timeframe duration)."""
    return bar.timestamp + _TF_DURATION.get(bar.timeframe, timedelta(hours=1))


def load_and_merge(csv_paths: list[str]) -> list[BarEvent]:
    """
    Load multiple CSV files and return all BarEvents merged and sorted by
    close time. This prevents look-ahead bias: a higher-timeframe bar
    (e.g. H4) is only processed after all lower-timeframe bars (e.g. M15)
    that fall within it have been processed first.

    Within the same close time, lower timeframes sort first.

    Duplicate bars (same symbol + timeframe + timestamp) from overlapping
    CSV files are removed — only the first occurrence is kept.
    """
    all_events: list[BarEvent] = []
    for path in csv_paths:
        all_events.extend(load_csv(path))

    # Deduplicate: same symbol + timeframe + timestamp = duplicate bar
    seen: set[tuple[str, str, datetime]] = set()
    deduped: list[BarEvent] = []
    for e in all_events:
        key = (e.symbol, e.timeframe, e.timestamp)
        if key not in seen:
            seen.add(key)
            deduped.append(e)
        else:
            logger.debug(f"Dropping duplicate bar: {e.symbol} {e.timeframe} {e.timestamp}")

    n_dupes = len(all_events) - len(deduped)
    if n_dupes > 0:
        logger.info(f"Removed {n_dupes} duplicate bars from overlapping CSV files")

    tf_rank = {'M1': 0, 'M5': 1, 'M15': 2, 'M30': 3, 'H1': 4, 'H4': 5, 'D1': 6}
    deduped.sort(key=lambda e: (bar_close_time(e), tf_rank.get(e.timeframe, 99)))
    return deduped
