import logging
import os
import time
from datetime import datetime

import pandas as pd
import MetaTrader5 as mt5

from models import BarEvent

logger = logging.getLogger(__name__)

_TIMEFRAME_MAP = {
    'M5':  mt5.TIMEFRAME_M5,
    'M15': mt5.TIMEFRAME_M15,
    'H1':  mt5.TIMEFRAME_H1,
    'H4':  mt5.TIMEFRAME_H4,
    'D1':  mt5.TIMEFRAME_D1,
}

# Stored credentials for reconnection
_credentials: dict | None = None

MAX_RECONNECT_ATTEMPTS = 5
RECONNECT_BASE_DELAY = 2  # seconds — doubles each attempt (exponential backoff)


def connect(login: int, password: str, server: str) -> bool:
    global _credentials
    _credentials = {'login': login, 'password': password, 'server': server}

    if not mt5.initialize(login=login, password=password, server=server):
        logger.error(f"MT5 initialize failed: {mt5.last_error()}")
        return False
    info = mt5.account_info()
    logger.info(f"Connected to MT5: server={info.server} account={info.login}")
    return True


def reconnect() -> bool:
    """Attempt to re-establish a dropped MT5 connection with exponential backoff."""
    if _credentials is None:
        logger.error("Cannot reconnect — no stored credentials (call connect() first)")
        return False

    for attempt in range(1, MAX_RECONNECT_ATTEMPTS + 1):
        delay = RECONNECT_BASE_DELAY * (2 ** (attempt - 1))
        logger.warning(f"MT5 reconnect attempt {attempt}/{MAX_RECONNECT_ATTEMPTS} in {delay}s...")
        time.sleep(delay)

        mt5.shutdown()
        if mt5.initialize(**_credentials):
            info = mt5.account_info()
            logger.info(f"MT5 reconnected: server={info.server} account={info.login}")
            return True

        logger.warning(f"Reconnect attempt {attempt} failed: {mt5.last_error()}")

    logger.error(f"MT5 reconnect failed after {MAX_RECONNECT_ATTEMPTS} attempts")
    return False


def disconnect():
    mt5.shutdown()
    logger.info("MT5 connection closed")


def get_latest_completed_bar(symbol: str, timeframe: str) -> BarEvent | None:
    """Return the most recently completed (closed) bar for a symbol/timeframe."""
    tf = _TIMEFRAME_MAP.get(timeframe)
    if tf is None:
        logger.error(f"Unknown timeframe: {timeframe}")
        return None

    # Position 1 = last completed bar (position 0 is the currently forming bar)
    bars = mt5.copy_rates_from_pos(symbol, tf, 1, 1)
    if bars is None or len(bars) == 0:
        logger.warning(f"No bar data for {symbol} {timeframe}")
        return None

    b = bars[0]
    return BarEvent(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=datetime.utcfromtimestamp(b['time']),
        open=float(b['open']),
        high=float(b['high']),
        low=float(b['low']),
        close=float(b['close']),
        volume=float(b['tick_volume']),
    )


def get_recent_bars(symbol: str, timeframe: str, count: int) -> list[BarEvent]:
    """Return the last `count` completed bars (excluding the current forming bar)."""
    tf = _TIMEFRAME_MAP.get(timeframe)
    if tf is None:
        logger.error(f"Unknown timeframe: {timeframe}")
        return []

    # Position 1 = skip the currently forming bar; fetch `count` completed bars
    bars = mt5.copy_rates_from_pos(symbol, tf, 1, count)
    if bars is None or len(bars) == 0:
        logger.warning(f"No bar data for {symbol} {timeframe} (requested {count})")
        return []

    return [
        BarEvent(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=datetime.utcfromtimestamp(b['time']),
            open=float(b['open']),
            high=float(b['high']),
            low=float(b['low']),
            close=float(b['close']),
            volume=float(b['tick_volume']),
        )
        for b in bars
    ]


def fetch_historical(symbol: str, timeframe: str, start: datetime, end: datetime) -> pd.DataFrame:
    """Fetch historical OHLCV bars from MT5 and return as a DataFrame."""
    tf = _TIMEFRAME_MAP.get(timeframe)
    if tf is None:
        raise ValueError(f"Unknown timeframe: {timeframe}")

    bars = mt5.copy_rates_range(symbol, tf, start, end)
    if bars is None or len(bars) == 0:
        raise RuntimeError(f"No historical data returned for {symbol} {timeframe}")

    df = pd.DataFrame(bars)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df = df[['time', 'open', 'high', 'low', 'close', 'tick_volume']].rename(
        columns={'tick_volume': 'volume'}
    )
    return df


def save_historical(
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    path: str = 'data/historical',
) -> str:
    """Fetch historical data from MT5 and save to CSV. Returns the saved filepath."""
    df = fetch_historical(symbol, timeframe, start, end)
    os.makedirs(path, exist_ok=True)
    filename = f"{symbol}_{timeframe}_{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}.csv"
    filepath = os.path.join(path, filename)
    df.to_csv(filepath, index=False)
    logger.info(f"Saved {len(df)} bars → {filepath}")
    return filepath
