from collections import deque
from math import fabs

from models import BarEvent, Signal


class RangeFadeStrategy:
    """
    Range-bound fade strategy on H1.

    Detects when a pair is in a defined range (ATR compression + price
    oscillating between clear highs and lows), then fades moves to the
    range edges with a confirmation candle.

    Logic:
      1. Range detection: current ATR < long-term ATR × squeeze_ratio
         (market is in low-volatility, range-bound conditions)
      2. Define range: highest high and lowest low over range_period bars
      3. Entry zone: price enters the outer edge_pct of the range
      4. Confirmation: rejection candle at the edge (bullish at bottom,
         bearish at top)
      5. SL: Beyond the range edge
      6. TP: Handled by risk manager (R:R ratio) — target is the mean/opposite edge

    This strategy is the inverse of a breakout strategy — it profits when
    ranges hold and loses when they break.
    """

    TIMEFRAMES = ['H1']
    ORDER_TYPE = 'MARKET'
    NAME = 'RangeFade'

    def __init__(
        self,
        atr_period: int = 14,
        atr_long_period: int = 100,
        squeeze_ratio: float = 0.7,
        range_period: int = 48,
        edge_pct: float = 0.15,
        min_range_pips: float = 30.0,
        max_range_pips: float = 150.0,
        sl_buffer_pips: float = 3.0,
        min_sl_pips: float = 10.0,
        max_sl_pips: float = 50.0,
        cooldown_bars: int = 5,
        lookback: int = 120,
        pip_sizes: dict[str, float] | None = None,
    ):
        self.atr_period = atr_period
        self.atr_long_period = atr_long_period
        self.squeeze_ratio = squeeze_ratio
        self.range_period = range_period
        self.edge_pct = edge_pct
        self.min_range_pips = min_range_pips
        self.max_range_pips = max_range_pips
        self.sl_buffer_pips = sl_buffer_pips
        self.min_sl_pips = min_sl_pips
        self.max_sl_pips = max_sl_pips
        self.cooldown_bars = cooldown_bars
        self.lookback = lookback
        self.pip_sizes = pip_sizes or {
            'EURUSD': 0.0001, 'GBPUSD': 0.0001, 'AUDUSD': 0.0001,
            'NZDUSD': 0.0001, 'USDJPY': 0.01,   'USDCAD': 0.0001,
            'USDCHF': 0.0001, 'XAUUSD': 0.10,
        }

        # ── Per-symbol state ─────────────────────────────────────────────────
        self._bars: dict[str, deque] = {}
        self._highs: dict[str, deque] = {}
        self._lows: dict[str, deque] = {}

        # ATR state (short and long)
        self._atr_short: dict[str, float | None] = {}
        self._atr_long: dict[str, float | None] = {}
        self._prev_close: dict[str, float | None] = {}

        # Trade management
        self._cooldown_remaining: dict[str, int] = {}
        self._last_direction: dict[str, str | None] = {}
        self._bar_count: dict[str, int] = {}

    def reset(self):
        """Clear all internal state."""
        for attr in vars(self):
            val = getattr(self, attr)
            if isinstance(val, dict) and attr.startswith('_'):
                val.clear()

    def generate_signal(self, event: BarEvent) -> Signal | None:
        s = event.symbol
        self._init_symbol(s)
        self._bar_count[s] += 1

        # Update ATR
        self._update_atr(s, event)

        # Store price data
        self._highs[s].append(event.high)
        self._lows[s].append(event.low)
        self._bars[s].append(event)

        # Cooldown
        if self._cooldown_remaining[s] > 0:
            self._cooldown_remaining[s] -= 1
            return None

        # Need enough data
        if self._bar_count[s] < max(self.range_period, self.atr_long_period) + 10:
            return None

        atr_short = self._atr_short[s]
        atr_long = self._atr_long[s]
        if atr_short is None or atr_long is None or atr_long == 0:
            return None

        pip = self._pip_size(s)

        # 1. Check for ATR squeeze (ranging conditions)
        if atr_short / atr_long > self.squeeze_ratio:
            return None  # volatility too high — market may be trending

        # 2. Define the range
        highs = list(self._highs[s])
        lows = list(self._lows[s])

        range_high = max(highs[-self.range_period:])
        range_low = min(lows[-self.range_period:])
        range_width = range_high - range_low
        range_pips = range_width / pip

        if range_pips < self.min_range_pips or range_pips > self.max_range_pips:
            return None

        # 3. Check if price is at range edge
        edge_size = range_width * self.edge_pct
        lower_edge = range_low + edge_size
        upper_edge = range_high - edge_size

        signal = None

        # 4. Bottom edge — look for bullish rejection
        if event.low <= lower_edge and event.close > lower_edge:
            # Must be bullish candle
            if event.close > event.open:
                # Lower wick should show rejection
                body_bot = min(event.open, event.close)
                lower_wick = body_bot - event.low
                body = fabs(event.close - event.open)

                if body > 0 and lower_wick >= body * 0.5:
                    if self._last_direction[s] != 'BUY':
                        sl = range_low - self.sl_buffer_pips * pip
                        sl_pips = (event.close - sl) / pip

                        if self.min_sl_pips <= sl_pips <= self.max_sl_pips:
                            self._last_direction[s] = 'BUY'
                            self._cooldown_remaining[s] = self.cooldown_bars
                            signal = Signal(
                                symbol=s, direction='BUY',
                                order_type=self.ORDER_TYPE,
                                entry_price=event.close,
                                stop_loss=sl,
                                strategy_name=self.NAME,
                                timestamp=event.timestamp,
                            )

        # 5. Top edge — look for bearish rejection
        elif event.high >= upper_edge and event.close < upper_edge:
            # Must be bearish candle
            if event.close < event.open:
                body_top = max(event.open, event.close)
                upper_wick = event.high - body_top
                body = fabs(event.close - event.open)

                if body > 0 and upper_wick >= body * 0.5:
                    if self._last_direction[s] != 'SELL':
                        sl = range_high + self.sl_buffer_pips * pip
                        sl_pips = (sl - event.close) / pip

                        if self.min_sl_pips <= sl_pips <= self.max_sl_pips:
                            self._last_direction[s] = 'SELL'
                            self._cooldown_remaining[s] = self.cooldown_bars
                            signal = Signal(
                                symbol=s, direction='SELL',
                                order_type=self.ORDER_TYPE,
                                entry_price=event.close,
                                stop_loss=sl,
                                strategy_name=self.NAME,
                                timestamp=event.timestamp,
                            )

        return signal

    # ── Initialisation ────────────────────────────────────────────────────────

    def _init_symbol(self, s: str):
        if s in self._bars:
            return
        self._bars[s] = deque(maxlen=self.lookback)
        self._highs[s] = deque(maxlen=self.lookback)
        self._lows[s] = deque(maxlen=self.lookback)
        self._atr_short[s] = None
        self._atr_long[s] = None
        self._prev_close[s] = None
        self._cooldown_remaining[s] = 0
        self._last_direction[s] = None
        self._bar_count[s] = 0

    def _pip_size(self, s: str) -> float:
        return self.pip_sizes.get(s, 0.0001)

    def _update_atr(self, s: str, event: BarEvent):
        """Update both short and long ATR."""
        if self._prev_close[s] is None:
            self._prev_close[s] = event.close
            return

        tr = max(
            event.high - event.low,
            fabs(event.high - self._prev_close[s]),
            fabs(event.low - self._prev_close[s]),
        )
        self._prev_close[s] = event.close

        # Short ATR
        if self._atr_short[s] is None:
            self._atr_short[s] = tr
        else:
            n = self.atr_period
            self._atr_short[s] = (self._atr_short[s] * (n - 1) + tr) / n

        # Long ATR
        if self._atr_long[s] is None:
            self._atr_long[s] = tr
        else:
            n = self.atr_long_period
            self._atr_long[s] = (self._atr_long[s] * (n - 1) + tr) / n

    def notify_loss(self, symbol: str):
        self._last_direction[symbol] = None

    def get_status(self, symbol: str) -> dict:
        """Diagnostic: return current indicator and range values."""
        highs = list(self._highs.get(symbol, []))
        lows = list(self._lows.get(symbol, []))
        pip = self._pip_size(symbol)

        range_high = max(highs[-self.range_period:]) if len(highs) >= self.range_period else None
        range_low = min(lows[-self.range_period:]) if len(lows) >= self.range_period else None

        atr_s = self._atr_short.get(symbol)
        atr_l = self._atr_long.get(symbol)

        return {
            'atr_short': round(atr_s / pip, 1) if atr_s else None,
            'atr_long': round(atr_l / pip, 1) if atr_l else None,
            'squeeze': round(atr_s / atr_l, 2) if atr_s and atr_l else None,
            'range_high': range_high,
            'range_low': range_low,
            'range_pips': round((range_high - range_low) / pip, 1) if range_high and range_low else None,
            'cooldown': self._cooldown_remaining.get(symbol, 0),
        }
