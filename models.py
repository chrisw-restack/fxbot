from dataclasses import dataclass
from datetime import datetime


@dataclass
class BarEvent:
    symbol: str        # e.g. 'EURUSD'
    timeframe: str     # e.g. 'H1'
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Signal:
    symbol: str
    direction: str      # 'BUY' | 'SELL'
    order_type: str     # 'MARKET' | 'PENDING'
    entry_price: float  # current price (MARKET) or specific level (PENDING)
    stop_loss: float    # price level — always set by the strategy
    strategy_name: str
    timestamp: datetime
    take_profit: float | None = None  # optional — if set, overrides risk manager TP


@dataclass
class EnrichedSignal:
    """Signal after the risk manager has added lot size and take-profit."""
    symbol: str
    direction: str
    order_type: str
    entry_price: float
    stop_loss: float
    take_profit: float
    lot_size: float
    strategy_name: str
    timestamp: datetime
