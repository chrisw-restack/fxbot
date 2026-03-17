from collections import deque

from models import BarEvent, Signal


class BreakoutStrategy:
    """
    N-bar channel breakout strategy (placeholder for more sophisticated strategies).

    Logic:
    - Maintains a rolling window of the previous N completed bars per symbol.
    - BUY signal: current bar closes above the highest high of the N-bar window.
    - SELL signal: current bar closes below the lowest low of the N-bar window.
    - Stop-loss: set at the opposite extreme of the N-bar window
        (lowest low for BUY, highest high for SELL).
    - Re-entry in the same direction is suppressed until the opposite signal fires.

    One instance can handle multiple symbols; state is tracked per symbol.
    """

    TIMEFRAMES = ['H1']
    ORDER_TYPE = 'MARKET'
    NAME = 'Breakout'

    def __init__(self, lookback: int = 20):
        self.lookback = lookback
        # Per-symbol state
        self._bars: dict[str, deque] = {}
        self._last_direction: dict[str, str | None] = {}

    def reset(self):
        """Clear all internal state. Call before reusing the instance in a new backtest."""
        self._bars.clear()
        self._last_direction.clear()

    def generate_signal(self, event: BarEvent) -> Signal | None:
        symbol = event.symbol

        # Initialise per-symbol state on first bar
        if symbol not in self._bars:
            self._bars[symbol] = deque(maxlen=self.lookback)
            self._last_direction[symbol] = None

        window = self._bars[symbol]

        # Need a full window of previous bars before signalling
        if len(window) < self.lookback:
            window.append(event)
            return None

        highest_high = max(b.high for b in window)
        lowest_low   = min(b.low  for b in window)

        signal = None

        if event.close > highest_high and self._last_direction[symbol] != 'BUY':
            self._last_direction[symbol] = 'BUY'
            signal = Signal(
                symbol=symbol,
                direction='BUY',
                order_type=self.ORDER_TYPE,
                entry_price=event.close,
                stop_loss=lowest_low,
                strategy_name=self.NAME,
                timestamp=event.timestamp,
            )

        elif event.close < lowest_low and self._last_direction[symbol] != 'SELL':
            self._last_direction[symbol] = 'SELL'
            signal = Signal(
                symbol=symbol,
                direction='SELL',
                order_type=self.ORDER_TYPE,
                entry_price=event.close,
                stop_loss=highest_high,
                strategy_name=self.NAME,
                timestamp=event.timestamp,
            )

        # Append current bar to window after checking (so window always holds previous bars)
        window.append(event)
        return signal
