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


def find_csv(symbol: str, timeframe: str, path: str = 'data/historical') -> str | None:
    """
    Find the most recent CSV matching the given symbol and timeframe in the given directory.
    Returns the full filepath or None if not found.
    """
    if not os.path.isdir(path):
        return None

    prefix = f"{symbol}_{timeframe}_"
    matches = sorted(
        [f for f in os.listdir(path) if f.startswith(prefix) and f.endswith('.csv')],
        reverse=True,
    )
    return os.path.join(path, matches[0]) if matches else None


def load_and_merge(csv_paths: list[str]) -> list[BarEvent]:
    """
    Load multiple CSV files and return all BarEvents merged and sorted by timestamp.
    Used for multi-symbol / multi-timeframe backtests.
    """
    all_events: list[BarEvent] = []
    for path in csv_paths:
        all_events.extend(load_csv(path))
    tf_rank = {'D1': 0, 'H4': 1, 'H1': 2, 'M15': 3, 'M5': 4}
    all_events.sort(key=lambda e: (e.timestamp, tf_rank.get(e.timeframe, 99)))
    return all_events
