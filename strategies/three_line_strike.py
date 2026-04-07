from collections import deque

from models import BarEvent, Signal

_DEFAULT_PIP_SIZES = {'USDJPY': 0.01, 'XAUUSD': 0.01}


class ThreeLineStrikeStrategy:
    """
    Bullish/bearish engulfing pattern on M5 with trend, MA alignment, and RSI filters.

    Trend filter:  price above 200 SMA (bullish) / below 200 SMA (bearish)
    MA alignment:  21 SMA > 50 SMA + sma_sep_pips (no weaving)
    Momentum:      RSI > 50 for longs, < 50 for shorts (Wilder's smoothing)
    Session:       event.timestamp.hour in allowed_hours (default: London 08-12 + NY 13-17 UTC)

    Bullish pattern:
      - Previous bar bearish (close < open)
      - Engulf bar: bullish, opens below prev body bottom, closes above prev body top

    SL modes:
      'bar_multiple' — entry ± sl_bar_multiplier × engulf bar range
      'sma50'        — 50 SMA level (skipped if SMA50 is on wrong side of entry)
      'fractal'      — most recent fractal swing low/high (n bars each side)

    Trade skipped if SL distance > max_sl_pips.
    """

    TIMEFRAMES = ['M5']
    ORDER_TYPE = 'MARKET'
    NAME = 'Engulfing'

    def __init__(
        self,
        sma_fast: int = 21,
        sma_mid: int = 50,
        sma_slow: int = 200,
        rsi_period: int = 14,
        sma_sep_pips: float = 5.0,
        sl_mode: str = 'bar_multiple',
        sl_bar_multiplier: float = 2.0,
        fractal_n: int = 3,
        max_sl_pips: float = 15.0,
        min_prev_body_pips: float = 3.0,
        engulf_ratio: float = 1.5,
        allowed_hours: tuple = (8, 9, 10, 11, 12, 13, 14, 15, 16, 17),
        pip_sizes: dict | None = None,
    ):
        self.sma_fast = sma_fast
        self.sma_mid = sma_mid
        self.sma_slow = sma_slow
        self.rsi_period = rsi_period
        self.sma_sep_pips = sma_sep_pips
        self.sl_mode = sl_mode
        self.sl_bar_multiplier = sl_bar_multiplier
        self.fractal_n = fractal_n
        self.max_sl_pips = max_sl_pips
        self.min_prev_body_pips = min_prev_body_pips
        self.engulf_ratio = engulf_ratio
        self.allowed_hours = set(allowed_hours)
        self.pip_sizes = pip_sizes or {}
        self._fractal_win_size = 2 * fractal_n + 1

        # Per-symbol state
        self._bars: dict[str, deque] = {}
        self._rsi_prev_close: dict[str, float | None] = {}
        self._rsi_avg_gain: dict[str, float | None] = {}
        self._rsi_avg_loss: dict[str, float | None] = {}
        self._fractal_window: dict[str, deque] = {}
        self._fractal_low: dict[str, float | None] = {}
        self._fractal_high: dict[str, float | None] = {}
        self._last_direction: dict[str, str | None] = {}

    def reset(self):
        self._bars.clear()
        self._rsi_prev_close.clear()
        self._rsi_avg_gain.clear()
        self._rsi_avg_loss.clear()
        self._fractal_window.clear()
        self._fractal_low.clear()
        self._fractal_high.clear()
        self._last_direction.clear()

    def _init_symbol(self, symbol: str):
        self._bars[symbol] = deque(maxlen=self.sma_slow)
        self._rsi_prev_close[symbol] = None
        self._rsi_avg_gain[symbol] = None
        self._rsi_avg_loss[symbol] = None
        self._fractal_window[symbol] = deque(maxlen=self._fractal_win_size)
        self._fractal_low[symbol] = None
        self._fractal_high[symbol] = None
        self._last_direction[symbol] = None

    def _pip_size(self, symbol: str) -> float:
        return self.pip_sizes.get(symbol, _DEFAULT_PIP_SIZES.get(symbol, 0.0001))

    # ── RSI (Wilder's smoothing) ──────────────────────────────────────────────

    def _update_rsi(self, symbol: str, close: float):
        if self._rsi_prev_close[symbol] is None:
            self._rsi_prev_close[symbol] = close
            return

        change = close - self._rsi_prev_close[symbol]
        self._rsi_prev_close[symbol] = close
        gain = max(change, 0.0)
        loss = max(-change, 0.0)

        if self._rsi_avg_gain[symbol] is None:
            self._rsi_avg_gain[symbol] = gain
            self._rsi_avg_loss[symbol] = loss
        else:
            n = self.rsi_period
            self._rsi_avg_gain[symbol] = (self._rsi_avg_gain[symbol] * (n - 1) + gain) / n
            self._rsi_avg_loss[symbol] = (self._rsi_avg_loss[symbol] * (n - 1) + loss) / n

    def _current_rsi(self, symbol: str) -> float | None:
        avg_gain = self._rsi_avg_gain[symbol]
        avg_loss = self._rsi_avg_loss[symbol]
        if avg_gain is None:
            return None
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    # ── Fractal swing detection ───────────────────────────────────────────────

    def _update_fractal(self, symbol: str, bar: BarEvent):
        window = self._fractal_window[symbol]
        window.append(bar)
        if len(window) < self._fractal_win_size:
            return

        mid = self.fractal_n
        mid_bar = window[mid]

        if all(mid_bar.low < window[i].low for i in range(self._fractal_win_size) if i != mid):
            self._fractal_low[symbol] = mid_bar.low

        if all(mid_bar.high > window[i].high for i in range(self._fractal_win_size) if i != mid):
            self._fractal_high[symbol] = mid_bar.high

    # ── SL calculation ────────────────────────────────────────────────────────

    def _calc_sl(self, symbol: str, event: BarEvent, direction: str,
                 sma50: float, pip_size: float) -> float | None:
        entry = event.close

        if self.sl_mode == 'bar_multiple':
            bar_range = event.high - event.low
            sl = entry - self.sl_bar_multiplier * bar_range if direction == 'BUY' \
                else entry + self.sl_bar_multiplier * bar_range

        elif self.sl_mode == 'sma50':
            sl = sma50
            if direction == 'BUY' and sl >= entry:
                return None
            if direction == 'SELL' and sl <= entry:
                return None

        elif self.sl_mode == 'fractal':
            sl = self._fractal_low[symbol] if direction == 'BUY' else self._fractal_high[symbol]
            if sl is None:
                return None
            if direction == 'BUY' and sl >= entry:
                return None
            if direction == 'SELL' and sl <= entry:
                return None

        else:
            return None

        sl_pips = abs(entry - sl) / pip_size
        if sl_pips > self.max_sl_pips:
            return None

        return sl

    # ── Main signal generation ────────────────────────────────────────────────

    def generate_signal(self, event: BarEvent) -> Signal | None:
        symbol = event.symbol

        if symbol not in self._bars:
            self._init_symbol(symbol)

        # Update RSI and fractal each bar (before warm-up completes too)
        self._update_rsi(symbol, event.close)
        self._update_fractal(symbol, event)

        bars = self._bars[symbol]

        # Warm-up: accumulate until we have sma_slow bars
        if len(bars) < self.sma_slow:
            bars.append(event)
            return None

        # ── SMAs (inline from window) ─────────────────────────────────────────
        closes = [b.close for b in bars]
        sma200 = sum(closes) / self.sma_slow
        sma50  = sum(closes[-self.sma_mid:]) / self.sma_mid
        sma21  = sum(closes[-self.sma_fast:]) / self.sma_fast

        pip_size = self._pip_size(symbol)
        sep_price = self.sma_sep_pips * pip_size

        # ── Session filter ────────────────────────────────────────────────────
        if self.allowed_hours and event.timestamp.hour not in self.allowed_hours:
            bars.append(event)
            return None

        # ── RSI ───────────────────────────────────────────────────────────────
        rsi = self._current_rsi(symbol)
        if rsi is None:
            bars.append(event)
            return None

        # prev is the bar immediately before the engulfing candle
        prev = bars[-1]
        prev_body = abs(prev.close - prev.open)
        engulf_body = abs(event.close - event.open)
        signal = None

        # ── Bullish engulf ────────────────────────────────────────────────────
        if (event.close > sma200
                and sma21 > sma50 + sep_price
                and rsi > 50
                and self._last_direction[symbol] != 'BUY'
                and prev.close < prev.open                              # previous bar bearish
                and prev_body >= self.min_prev_body_pips * pip_size     # prev body not tiny
                and event.close > event.open                            # engulf bar bullish
                and event.open < prev.close                             # opens below prev body bottom
                and event.close > prev.open                             # closes above prev body top
                and engulf_body >= prev_body * self.engulf_ratio):      # engulf decisively larger

            sl = self._calc_sl(symbol, event, 'BUY', sma50, pip_size)
            if sl is not None:
                self._last_direction[symbol] = 'BUY'
                signal = Signal(
                    symbol=symbol,
                    direction='BUY',
                    order_type=self.ORDER_TYPE,
                    entry_price=event.close,
                    stop_loss=sl,
                    strategy_name=self.NAME,
                    timestamp=event.timestamp,
                )

        # ── Bearish engulf ────────────────────────────────────────────────────
        elif (event.close < sma200
                and sma21 < sma50 - sep_price
                and rsi < 50
                and self._last_direction[symbol] != 'SELL'
                and prev.close > prev.open                              # previous bar bullish
                and prev_body >= self.min_prev_body_pips * pip_size     # prev body not tiny
                and event.close < event.open                            # engulf bar bearish
                and event.open > prev.close                             # opens above prev body top
                and event.close < prev.open                             # closes below prev body bottom
                and engulf_body >= prev_body * self.engulf_ratio):      # engulf decisively larger

            sl = self._calc_sl(symbol, event, 'SELL', sma50, pip_size)
            if sl is not None:
                self._last_direction[symbol] = 'SELL'
                signal = Signal(
                    symbol=symbol,
                    direction='SELL',
                    order_type=self.ORDER_TYPE,
                    entry_price=event.close,
                    stop_loss=sl,
                    strategy_name=self.NAME,
                    timestamp=event.timestamp,
                )

        bars.append(event)
        return signal
