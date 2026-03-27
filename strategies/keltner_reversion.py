from collections import deque
from math import fabs

from models import BarEvent, Signal


class KeltnerReversionStrategy:
    """
    Mean reversion strategy using Keltner Channels + RSI divergence + ADX filter.

    Logic:
      1. ADX must be below threshold (ranging market — no trending)
      2. Price touches or exceeds outer Keltner Channel band
      3. RSI shows divergence against price (momentum weakening at extreme)
      4. Enter MARKET order on the bar that confirms all three conditions

    Keltner Channel: EMA(kc_period) ± ATR(atr_period) × kc_mult
    RSI divergence: price makes new extreme but RSI doesn't confirm it
    ADX filter: ADX(adx_period) < adx_threshold confirms ranging regime

    SL: Beyond the recent swing extreme (highest high or lowest low of N bars)
    TP: Handled by risk manager (R:R ratio)
    """

    TIMEFRAMES = ['H1']
    ORDER_TYPE = 'MARKET'
    NAME = 'KeltnerReversion'

    def __init__(
        self,
        kc_period: int = 20,
        kc_mult: float = 2.0,
        atr_period: int = 14,
        rsi_period: int = 14,
        adx_period: int = 14,
        adx_threshold: float = 25.0,
        swing_lookback: int = 5,
        sl_lookback: int = 10,
        divergence_lookback: int = 30,
        min_sl_pips: float = 10.0,
        max_sl_pips: float = 60.0,
        cooldown_bars: int = 5,
        lookback: int = 80,
        pip_sizes: dict[str, float] | None = None,
    ):
        self.kc_period = kc_period
        self.kc_mult = kc_mult
        self.atr_period = atr_period
        self.rsi_period = rsi_period
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold
        self.swing_lookback = swing_lookback
        self.sl_lookback = sl_lookback
        self.divergence_lookback = divergence_lookback
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
        self._closes: dict[str, deque] = {}
        self._highs: dict[str, deque] = {}
        self._lows: dict[str, deque] = {}

        # EMA for Keltner centre
        self._kc_ema: dict[str, float | None] = {}

        # ATR state
        self._atr: dict[str, float | None] = {}
        self._prev_close: dict[str, float | None] = {}

        # RSI state
        self._rsi_avg_gain: dict[str, float | None] = {}
        self._rsi_avg_loss: dict[str, float | None] = {}
        self._rsi_values: dict[str, deque] = {}
        self._rsi_bar_count: dict[str, int] = {}
        self._rsi_prev_close: dict[str, float | None] = {}

        # ADX state
        self._adx_plus_dm_ema: dict[str, float | None] = {}
        self._adx_minus_dm_ema: dict[str, float | None] = {}
        self._adx_tr_ema: dict[str, float | None] = {}
        self._adx_value: dict[str, float | None] = {}
        self._adx_dx_ema: dict[str, float | None] = {}
        self._adx_prev_high: dict[str, float | None] = {}
        self._adx_prev_low: dict[str, float | None] = {}
        self._adx_bar_count: dict[str, int] = {}

        # Cooldown
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

        # Update indicators
        self._update_kc_ema(s, event.close)
        self._update_atr(s, event)
        self._update_rsi(s, event.close)
        self._update_adx(s, event)

        # Store price data
        self._highs[s].append(event.high)
        self._lows[s].append(event.low)
        self._closes[s].append(event.close)
        self._bars[s].append(event)

        # Cooldown management
        if self._cooldown_remaining[s] > 0:
            self._cooldown_remaining[s] -= 1
            return None

        # Need enough data for all indicators
        min_bars = max(self.kc_period, self.atr_period, self.rsi_period,
                       self.adx_period, self.divergence_lookback) + 10
        if self._bar_count[s] < min_bars:
            return None

        # Check conditions
        kc_ema = self._kc_ema[s]
        atr = self._atr[s]
        adx = self._adx_value[s]
        rsi = self._current_rsi(s)

        if kc_ema is None or atr is None or adx is None or rsi is None:
            return None

        upper_band = kc_ema + self.kc_mult * atr
        lower_band = kc_ema - self.kc_mult * atr
        pip = self._pip_size(s)

        # 1. ADX filter — must be ranging
        if adx >= self.adx_threshold:
            return None

        signal = None

        # 2. Price at lower band + bullish RSI divergence → BUY
        if event.low <= lower_band:
            if self._has_bullish_divergence(s):
                if self._last_direction[s] != 'BUY':
                    # SL below recent lowest low
                    lows = list(self._lows[s])
                    sl_low = min(lows[-self.sl_lookback:])
                    sl = sl_low - 2 * pip  # small buffer

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

        # 3. Price at upper band + bearish RSI divergence → SELL
        elif event.high >= upper_band:
            if self._has_bearish_divergence(s):
                if self._last_direction[s] != 'SELL':
                    highs = list(self._highs[s])
                    sl_high = max(highs[-self.sl_lookback:])
                    sl = sl_high + 2 * pip

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
        self._closes[s] = deque(maxlen=self.lookback)
        self._highs[s] = deque(maxlen=self.lookback)
        self._lows[s] = deque(maxlen=self.lookback)
        self._kc_ema[s] = None
        self._atr[s] = None
        self._prev_close[s] = None
        self._rsi_avg_gain[s] = None
        self._rsi_avg_loss[s] = None
        self._rsi_values[s] = deque(maxlen=self.lookback)
        self._rsi_bar_count[s] = 0
        self._rsi_prev_close[s] = None
        self._adx_plus_dm_ema[s] = None
        self._adx_minus_dm_ema[s] = None
        self._adx_tr_ema[s] = None
        self._adx_value[s] = None
        self._adx_dx_ema[s] = None
        self._adx_prev_high[s] = None
        self._adx_prev_low[s] = None
        self._adx_bar_count[s] = 0
        self._cooldown_remaining[s] = 0
        self._last_direction[s] = None
        self._bar_count[s] = 0

    def _pip_size(self, s: str) -> float:
        return self.pip_sizes.get(s, 0.0001)

    # ══════════════════════════════════════════════════════════════════════════
    # Indicator updates
    # ══════════════════════════════════════════════════════════════════════════

    def _update_kc_ema(self, s: str, close: float):
        """EMA for Keltner Channel centre line."""
        if self._kc_ema[s] is None:
            self._kc_ema[s] = close
        else:
            k = 2.0 / (self.kc_period + 1)
            self._kc_ema[s] = close * k + self._kc_ema[s] * (1 - k)

    def _update_atr(self, s: str, event: BarEvent):
        """ATR using Wilder's smoothing."""
        if self._prev_close[s] is None:
            self._prev_close[s] = event.close
            return

        tr = max(
            event.high - event.low,
            fabs(event.high - self._prev_close[s]),
            fabs(event.low - self._prev_close[s]),
        )
        self._prev_close[s] = event.close

        if self._atr[s] is None:
            self._atr[s] = tr
        else:
            self._atr[s] = (self._atr[s] * (self.atr_period - 1) + tr) / self.atr_period

    def _update_rsi(self, s: str, close: float):
        """RSI using Wilder's smoothing."""
        self._rsi_bar_count[s] += 1

        if self._rsi_prev_close[s] is None:
            self._rsi_prev_close[s] = close
            self._rsi_values[s].append(50.0)  # neutral until seeded
            return

        change = close - self._rsi_prev_close[s]
        self._rsi_prev_close[s] = close
        gain = max(change, 0.0)
        loss = max(-change, 0.0)

        if self._rsi_avg_gain[s] is None:
            # Seed with first value
            self._rsi_avg_gain[s] = gain
            self._rsi_avg_loss[s] = loss
        else:
            n = self.rsi_period
            self._rsi_avg_gain[s] = (self._rsi_avg_gain[s] * (n - 1) + gain) / n
            self._rsi_avg_loss[s] = (self._rsi_avg_loss[s] * (n - 1) + loss) / n

        rsi = self._current_rsi(s)
        if rsi is not None:
            self._rsi_values[s].append(rsi)

    def _current_rsi(self, s: str) -> float | None:
        avg_gain = self._rsi_avg_gain[s]
        avg_loss = self._rsi_avg_loss[s]
        if avg_gain is None:
            return None
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def _update_adx(self, s: str, event: BarEvent):
        """ADX using Wilder's smoothing of +DI, -DI, and DX."""
        self._adx_bar_count[s] += 1

        if self._adx_prev_high[s] is None:
            self._adx_prev_high[s] = event.high
            self._adx_prev_low[s] = event.low
            return

        prev_h = self._adx_prev_high[s]
        prev_l = self._adx_prev_low[s]
        prev_c = self._prev_close[s] or event.close

        # Directional movement
        plus_dm = event.high - prev_h
        minus_dm = prev_l - event.low

        if plus_dm > minus_dm and plus_dm > 0:
            minus_dm = 0.0
        elif minus_dm > plus_dm and minus_dm > 0:
            plus_dm = 0.0
        else:
            plus_dm = minus_dm = 0.0

        # True range
        tr = max(
            event.high - event.low,
            fabs(event.high - prev_c),
            fabs(event.low - prev_c),
        )

        self._adx_prev_high[s] = event.high
        self._adx_prev_low[s] = event.low

        n = self.adx_period

        # Smooth +DM, -DM, TR with Wilder's method
        if self._adx_tr_ema[s] is None:
            self._adx_plus_dm_ema[s] = plus_dm
            self._adx_minus_dm_ema[s] = minus_dm
            self._adx_tr_ema[s] = tr
        else:
            self._adx_plus_dm_ema[s] = (self._adx_plus_dm_ema[s] * (n - 1) + plus_dm) / n
            self._adx_minus_dm_ema[s] = (self._adx_minus_dm_ema[s] * (n - 1) + minus_dm) / n
            self._adx_tr_ema[s] = (self._adx_tr_ema[s] * (n - 1) + tr) / n

        # +DI and -DI
        if self._adx_tr_ema[s] == 0:
            return
        plus_di = 100.0 * self._adx_plus_dm_ema[s] / self._adx_tr_ema[s]
        minus_di = 100.0 * self._adx_minus_dm_ema[s] / self._adx_tr_ema[s]

        # DX
        di_sum = plus_di + minus_di
        if di_sum == 0:
            return
        dx = 100.0 * fabs(plus_di - minus_di) / di_sum

        # Smooth DX to get ADX
        if self._adx_dx_ema[s] is None:
            self._adx_dx_ema[s] = dx
        else:
            self._adx_dx_ema[s] = (self._adx_dx_ema[s] * (n - 1) + dx) / n

        self._adx_value[s] = self._adx_dx_ema[s]

    # ══════════════════════════════════════════════════════════════════════════
    # Divergence detection
    # ══════════════════════════════════════════════════════════════════════════

    def _find_swing_lows(self, values: list, n: int = 5) -> list[tuple[int, float]]:
        """Find swing low indices and values. A swing low is lower than n bars on each side."""
        swings = []
        for i in range(n, len(values) - 1):  # exclude the very last bar
            val = values[i]
            is_low = all(val <= values[i - j] for j in range(1, n + 1))
            is_low = is_low and all(val <= values[i + j] for j in range(1, min(n + 1, len(values) - i)))
            if is_low:
                swings.append((i, val))
        return swings

    def _find_swing_highs(self, values: list, n: int = 5) -> list[tuple[int, float]]:
        """Find swing high indices and values."""
        swings = []
        for i in range(n, len(values) - 1):
            val = values[i]
            is_high = all(val >= values[i - j] for j in range(1, n + 1))
            is_high = is_high and all(val >= values[i + j] for j in range(1, min(n + 1, len(values) - i)))
            if is_high:
                swings.append((i, val))
        return swings

    def _has_bullish_divergence(self, s: str) -> bool:
        """
        Bullish divergence: price makes lower low but RSI makes higher low.
        """
        lows = list(self._lows[s])
        rsi_vals = list(self._rsi_values[s])

        n = min(len(lows), len(rsi_vals), self.divergence_lookback)
        if n < self.swing_lookback * 3:
            return False

        price_lows = lows[-n:]
        rsi_lows = rsi_vals[-n:]

        price_swings = self._find_swing_lows(price_lows, self.swing_lookback)
        rsi_swings = self._find_swing_lows(rsi_lows, self.swing_lookback)

        if len(price_swings) < 2 or len(rsi_swings) < 2:
            return False

        # Compare last two price swing lows
        prev_price_idx, prev_price_val = price_swings[-2]
        curr_price_idx, curr_price_val = price_swings[-1]

        # Price made a lower low
        if curr_price_val >= prev_price_val:
            return False

        # Find RSI values at those price swing indices
        if curr_price_idx >= len(rsi_lows) or prev_price_idx >= len(rsi_lows):
            return False

        curr_rsi_at_low = rsi_lows[curr_price_idx]
        prev_rsi_at_low = rsi_lows[prev_price_idx]

        # RSI made a higher low (divergence)
        return curr_rsi_at_low > prev_rsi_at_low

    def _has_bearish_divergence(self, s: str) -> bool:
        """
        Bearish divergence: price makes higher high but RSI makes lower high.
        """
        highs = list(self._highs[s])
        rsi_vals = list(self._rsi_values[s])

        n = min(len(highs), len(rsi_vals), self.divergence_lookback)
        if n < self.swing_lookback * 3:
            return False

        price_highs = highs[-n:]
        rsi_highs = rsi_vals[-n:]

        price_swings = self._find_swing_highs(price_highs, self.swing_lookback)
        rsi_swings = self._find_swing_highs(rsi_highs, self.swing_lookback)

        if len(price_swings) < 2 or len(rsi_swings) < 2:
            return False

        prev_price_idx, prev_price_val = price_swings[-2]
        curr_price_idx, curr_price_val = price_swings[-1]

        # Price made a higher high
        if curr_price_val <= prev_price_val:
            return False

        if curr_price_idx >= len(rsi_highs) or prev_price_idx >= len(rsi_highs):
            return False

        curr_rsi_at_high = rsi_highs[curr_price_idx]
        prev_rsi_at_high = rsi_highs[prev_price_idx]

        # RSI made a lower high (divergence)
        return curr_rsi_at_high < prev_rsi_at_high

    def notify_loss(self, symbol: str):
        self._last_direction[symbol] = None  # allow re-entry after loss

    def get_status(self, symbol: str) -> dict:
        """Diagnostic: return current indicator values."""
        return {
            'kc_ema': self._kc_ema.get(symbol),
            'atr': self._atr.get(symbol),
            'rsi': self._current_rsi(symbol),
            'adx': self._adx_value.get(symbol),
            'cooldown': self._cooldown_remaining.get(symbol, 0),
        }
