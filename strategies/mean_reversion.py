from collections import deque

from models import BarEvent, Signal


class MeanReversionStrategy:
    """
    Bollinger Band mean reversion strategy.

    Logic:
    - Calculates a simple moving average (SMA) and standard deviation over
      the previous `lookback` bars.
    - Upper band = SMA + (std_multiplier × std)
    - Lower band = SMA - (std_multiplier × std)
    - BUY signal:  close drops below the lower band — price stretched to downside,
                   expect reversion back toward the mean.
    - SELL signal: close rises above the upper band — price stretched to upside,
                   expect reversion back toward the mean.
    - Stop-loss:   set at the lowest low (BUY) or highest high (SELL) of the last
                   `sl_lookback` bars including the current bar, so the SL sits
                   just beyond the recent extreme that triggered the signal.
    - Re-entry in the same direction is suppressed until the opposite signal fires.

    One instance handles multiple symbols; state is tracked per symbol.
    """

    TIMEFRAMES = ['H1']
    ORDER_TYPE = 'MARKET'
    NAME = 'MeanReversion'

    def __init__(
        self,
        lookback: int = 20,
        std_multiplier: float = 2.0,
        sl_lookback: int = 5,
    ):
        self.lookback = lookback
        self.std_multiplier = std_multiplier
        self.sl_lookback = sl_lookback
        # Per-symbol state
        self._bars: dict[str, deque] = {}
        self._last_direction: dict[str, str | None] = {}

    def reset(self):
        """Clear all internal state. Call before reusing the instance in a new backtest."""
        self._bars.clear()
        self._last_direction.clear()

    def generate_signal(self, event: BarEvent) -> Signal | None:
        symbol = event.symbol

        if symbol not in self._bars:
            self._bars[symbol] = deque(maxlen=self.lookback)
            self._last_direction[symbol] = None

        window = self._bars[symbol]

        if len(window) < self.lookback:
            window.append(event)
            return None

        # ── Bollinger Bands from previous `lookback` bars ─────────────────────
        closes = [b.close for b in window]
        sma = sum(closes) / len(closes)
        std = (sum((c - sma) ** 2 for c in closes) / len(closes)) ** 0.5

        if std == 0:
            window.append(event)
            return None

        upper_band = sma + self.std_multiplier * std
        lower_band = sma - self.std_multiplier * std

        # ── Stop-loss from recent extremes ────────────────────────────────────
        # Include the current bar so the SL sits just beyond the bar that
        # triggered the signal, not the bar before it.
        sl_bars = list(window)[-self.sl_lookback:]
        recent_low  = min(min(b.low  for b in sl_bars), event.low)
        recent_high = max(max(b.high for b in sl_bars), event.high)

        signal = None

        if event.close < lower_band and self._last_direction[symbol] != 'BUY':
            self._last_direction[symbol] = 'BUY'
            signal = Signal(
                symbol=symbol,
                direction='BUY',
                order_type=self.ORDER_TYPE,
                entry_price=event.close,
                stop_loss=recent_low,
                strategy_name=self.NAME,
                timestamp=event.timestamp,
            )

        elif event.close > upper_band and self._last_direction[symbol] != 'SELL':
            self._last_direction[symbol] = 'SELL'
            signal = Signal(
                symbol=symbol,
                direction='SELL',
                order_type=self.ORDER_TYPE,
                entry_price=event.close,
                stop_loss=recent_high,
                strategy_name=self.NAME,
                timestamp=event.timestamp,
            )

        # Append after checking so the window always holds the previous bars
        window.append(event)
        return signal
