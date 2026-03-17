from collections import deque

from models import BarEvent, Signal


class EmaFibRetracementIntradayStrategy:
    """
    Intraday version of the EMA + Fibonacci retracement strategy.

    H4 + M15 EMA bias must agree (10 EMA vs 20 EMA). When aligned, places
    PENDING orders at the 61.8% Fibonacci retracement of the most recent
    M15 swing. TP at 200% extension. Cancels pending orders when bias flips.
    """

    TIMEFRAMES = ['H4', 'M15']
    ORDER_TYPE = 'PENDING'
    NAME = 'EmaFibRetracementIntraday'

    def __init__(
        self,
        ema_fast: int = 10,
        ema_slow: int = 20,
        fractal_n: int = 3,
        fib_entry: float = 0.618,
        fib_tp: float = 2.0,
        swing_max_age: int = 100,
        cooldown_bars: int = 0,
        min_swing_pips: float = 0.0,
        ema_sep_pct: float = 0.0,
        invalidate_swing_on_loss: bool = False,
        blocked_hours: tuple[int, ...] = (),
        min_htf_atr_pips: float = 0.0,
        htf_atr_period: int = 14,
        pip_sizes: dict[str, float] | None = None,
    ):
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.fractal_n = fractal_n
        self.fib_entry = fib_entry
        self.fib_tp = fib_tp
        self.swing_max_age = swing_max_age
        self.cooldown_bars = cooldown_bars
        self.min_swing_pips = min_swing_pips
        self.ema_sep_pct = ema_sep_pct
        self.invalidate_swing_on_loss = invalidate_swing_on_loss
        self.blocked_hours = set(blocked_hours)
        self.min_htf_atr_pips = min_htf_atr_pips
        self.htf_atr_period = htf_atr_period
        self.pip_sizes = pip_sizes or {
            'EURUSD': 0.0001, 'GBPUSD': 0.0001, 'AUDUSD': 0.0001,
            'NZDUSD': 0.0001, 'USDJPY': 0.01,   'USDCAD': 0.0001,
        }

        self._window_size = 2 * fractal_n + 1

        # Per-symbol state — higher timeframe (H4)
        self._htf_ema_fast: dict[str, float | None] = {}
        self._htf_ema_slow: dict[str, float | None] = {}
        self._htf_bar_count: dict[str, int] = {}
        self._htf_sma_sum_fast: dict[str, float] = {}
        self._htf_sma_sum_slow: dict[str, float] = {}

        self._htf_prev_close: dict[str, float | None] = {}
        self._htf_tr_window: dict[str, deque] = {}
        self._htf_atr: dict[str, float | None] = {}

        # Per-symbol state — lower timeframe (M15)
        self._ltf_ema_fast: dict[str, float | None] = {}
        self._ltf_ema_slow: dict[str, float | None] = {}
        self._ltf_bar_count: dict[str, int] = {}
        self._ltf_sma_sum_fast: dict[str, float] = {}
        self._ltf_sma_sum_slow: dict[str, float] = {}

        self._ltf_window: dict[str, deque] = {}
        self._ltf_counter: dict[str, int] = {}

        self._swing_high: dict[str, float | None] = {}
        self._swing_low: dict[str, float | None] = {}
        self._swing_high_bar: dict[str, int] = {}
        self._swing_low_bar: dict[str, int] = {}

        self._pending_entry: dict[str, float | None] = {}
        self._pending_direction: dict[str, str | None] = {}

        # Filter state
        self._cooldown_until: dict[str, int] = {}
        self._used_swing_high: dict[str, float | None] = {}
        self._used_swing_low: dict[str, float | None] = {}

    def reset(self):
        """Clear all internal state."""
        self._htf_ema_fast.clear()
        self._htf_ema_slow.clear()
        self._htf_bar_count.clear()
        self._htf_sma_sum_fast.clear()
        self._htf_sma_sum_slow.clear()

        self._htf_prev_close.clear()
        self._htf_tr_window.clear()
        self._htf_atr.clear()

        self._ltf_ema_fast.clear()
        self._ltf_ema_slow.clear()
        self._ltf_bar_count.clear()
        self._ltf_sma_sum_fast.clear()
        self._ltf_sma_sum_slow.clear()

        self._ltf_window.clear()
        self._ltf_counter.clear()

        self._swing_high.clear()
        self._swing_low.clear()
        self._swing_high_bar.clear()
        self._swing_low_bar.clear()

        self._pending_entry.clear()
        self._pending_direction.clear()

        self._cooldown_until.clear()
        self._used_swing_high.clear()
        self._used_swing_low.clear()

    def generate_signal(self, event: BarEvent) -> Signal | None:
        symbol = event.symbol
        self._init_symbol(symbol)

        if event.timeframe == 'H4':
            self._update_htf(symbol, event)
            return None

        if event.timeframe == 'M15':
            return self._process_ltf(symbol, event)

        return None

    # ── Initialisation ───────────────────────────────────────────────────────

    def _init_symbol(self, symbol: str):
        if symbol in self._htf_bar_count:
            return
        self._htf_ema_fast[symbol] = None
        self._htf_ema_slow[symbol] = None
        self._htf_bar_count[symbol] = 0
        self._htf_sma_sum_fast[symbol] = 0.0
        self._htf_sma_sum_slow[symbol] = 0.0

        self._htf_prev_close[symbol] = None
        self._htf_tr_window[symbol] = deque(maxlen=self.htf_atr_period)
        self._htf_atr[symbol] = None

        self._ltf_ema_fast[symbol] = None
        self._ltf_ema_slow[symbol] = None
        self._ltf_bar_count[symbol] = 0
        self._ltf_sma_sum_fast[symbol] = 0.0
        self._ltf_sma_sum_slow[symbol] = 0.0

        self._ltf_window[symbol] = deque(maxlen=self._window_size)
        self._ltf_counter[symbol] = 0

        self._swing_high[symbol] = None
        self._swing_low[symbol] = None
        self._swing_high_bar[symbol] = 0
        self._swing_low_bar[symbol] = 0

        self._pending_entry[symbol] = None
        self._pending_direction[symbol] = None

        self._cooldown_until[symbol] = 0
        self._used_swing_high[symbol] = None
        self._used_swing_low[symbol] = None

    # ── EMA helpers ──────────────────────────────────────────────────────────

    def _update_ema(self, close: float, prev_ema: float | None, bar_count: int,
                    sma_sum: float, period: int) -> tuple[float | None, float]:
        """
        Returns (ema_value_or_None, updated_sma_sum).
        SMA-seeds for the first `period` bars, then switches to recursive EMA.
        """
        sma_sum += close
        if bar_count < period:
            return None, sma_sum
        if bar_count == period:
            return sma_sum / period, sma_sum
        k = 2.0 / (period + 1)
        return close * k + prev_ema * (1 - k), sma_sum

    # ── Higher timeframe (H4) processing ─────────────────────────────────────

    def _update_htf(self, symbol: str, event: BarEvent):
        self._htf_bar_count[symbol] += 1
        count = self._htf_bar_count[symbol]

        fast, self._htf_sma_sum_fast[symbol] = self._update_ema(
            event.close, self._htf_ema_fast[symbol], count,
            self._htf_sma_sum_fast[symbol], self.ema_fast,
        )
        slow, self._htf_sma_sum_slow[symbol] = self._update_ema(
            event.close, self._htf_ema_slow[symbol], count,
            self._htf_sma_sum_slow[symbol], self.ema_slow,
        )
        self._htf_ema_fast[symbol] = fast
        self._htf_ema_slow[symbol] = slow

        # H4 ATR
        prev = self._htf_prev_close[symbol]
        if prev is not None:
            tr = max(event.high - event.low,
                     abs(event.high - prev),
                     abs(event.low - prev))
        else:
            tr = event.high - event.low
        self._htf_prev_close[symbol] = event.close

        window = self._htf_tr_window[symbol]
        window.append(tr)
        if len(window) == self.htf_atr_period:
            self._htf_atr[symbol] = sum(window) / self.htf_atr_period

    # ── Lower timeframe (M15) processing ─────────────────────────────────────

    def _process_ltf(self, symbol: str, event: BarEvent) -> Signal | None:
        # Update M15 EMAs
        self._ltf_bar_count[symbol] += 1
        count = self._ltf_bar_count[symbol]

        fast, self._ltf_sma_sum_fast[symbol] = self._update_ema(
            event.close, self._ltf_ema_fast[symbol], count,
            self._ltf_sma_sum_fast[symbol], self.ema_fast,
        )
        slow, self._ltf_sma_sum_slow[symbol] = self._update_ema(
            event.close, self._ltf_ema_slow[symbol], count,
            self._ltf_sma_sum_slow[symbol], self.ema_slow,
        )
        self._ltf_ema_fast[symbol] = fast
        self._ltf_ema_slow[symbol] = slow

        # Increment bar counter
        self._ltf_counter[symbol] += 1
        bar_idx = self._ltf_counter[symbol]

        # Append to fractal window and check for new swings
        self._ltf_window[symbol].append(event)
        self._detect_swings(symbol)

        # Check if pending order was filled (bar range includes entry price)
        pending = self._pending_entry[symbol]
        if pending is not None:
            if event.low <= pending <= event.high:
                self._pending_entry[symbol] = None
                self._pending_direction[symbol] = None
                return None

            # Pending still unfilled — check if LTF bias flipped → cancel
            ltf_bias = self._get_bias(self._ltf_ema_fast[symbol], self._ltf_ema_slow[symbol])
            if ltf_bias is not None and ltf_bias != self._pending_direction[symbol]:
                self._pending_entry[symbol] = None
                self._pending_direction[symbol] = None
                return Signal(
                    symbol=symbol,
                    direction='CANCEL',
                    order_type=self.ORDER_TYPE,
                    entry_price=0.0,
                    stop_loss=0.0,
                    strategy_name=self.NAME,
                    timestamp=event.timestamp,
                )
            return None

        # ── Filter: Cooldown after stop-out ────────────────────────────────
        if self.cooldown_bars > 0 and bar_idx < self._cooldown_until[symbol]:
            return None

        # ── Filter: Session filter ─────────────────────────────────────────
        if self.blocked_hours and event.timestamp.hour in self.blocked_hours:
            return None

        # ── Filter: HTF ATR minimum ────────────────────────────────────────
        if self.min_htf_atr_pips > 0:
            htf_atr = self._htf_atr.get(symbol)
            if htf_atr is None:
                return None
            atr_pips = htf_atr / self._pip_size(symbol)
            if atr_pips < self.min_htf_atr_pips:
                return None

        # Need both HTF and LTF EMAs to be seeded
        htf_bias = self._get_bias(self._htf_ema_fast[symbol], self._htf_ema_slow[symbol])
        ltf_bias = self._get_bias(self._ltf_ema_fast[symbol], self._ltf_ema_slow[symbol])

        if htf_bias is None or ltf_bias is None:
            return None

        # Biases must agree
        if htf_bias != ltf_bias:
            return None

        # ── Filter: EMA separation / trend strength ────────────────────────
        if self.ema_sep_pct > 0:
            ltf_fast_val = self._ltf_ema_fast[symbol]
            ltf_slow_val = self._ltf_ema_slow[symbol]
            separation = abs(ltf_fast_val - ltf_slow_val) / ltf_slow_val
            if separation < self.ema_sep_pct:
                return None

        # Need valid swings
        swing_high = self._swing_high[symbol]
        swing_low = self._swing_low[symbol]
        if swing_high is None or swing_low is None:
            return None

        # Check swing age
        high_age = bar_idx - self._swing_high_bar[symbol]
        low_age = bar_idx - self._swing_low_bar[symbol]
        if high_age > self.swing_max_age or low_age > self.swing_max_age:
            return None

        # ── Filter: Invalidate swing after loss ────────────────────────────
        if self.invalidate_swing_on_loss:
            if (swing_high == self._used_swing_high[symbol]
                    and swing_low == self._used_swing_low[symbol]):
                return None

        # Swing must make sense (high > low)
        if swing_high <= swing_low:
            return None

        swing_range = swing_high - swing_low

        # ── Filter: Minimum swing range ────────────────────────────────────
        if self.min_swing_pips > 0:
            swing_pips = swing_range / self._pip_size(symbol)
            if swing_pips < self.min_swing_pips:
                return None

        direction = htf_bias

        if direction == 'BUY':
            entry_price = swing_high - self.fib_entry * swing_range
            stop_loss = swing_low
            take_profit = swing_low + self.fib_tp * swing_range
        else:
            entry_price = swing_low + self.fib_entry * swing_range
            stop_loss = swing_high
            take_profit = swing_high - self.fib_tp * swing_range

        # Track the pending order
        self._pending_entry[symbol] = entry_price
        self._pending_direction[symbol] = direction

        return Signal(
            symbol=symbol,
            direction=direction,
            order_type=self.ORDER_TYPE,
            entry_price=entry_price,
            stop_loss=stop_loss,
            strategy_name=self.NAME,
            timestamp=event.timestamp,
            take_profit=take_profit,
        )

    # ── Post-trade feedback ──────────────────────────────────────────────────

    def notify_loss(self, symbol: str):
        """
        Called externally (by the engine/backtest) when a trade from this
        strategy closes at a loss. Activates cooldown and marks the swing
        that produced the trade as used.
        """
        bar_idx = self._ltf_counter.get(symbol, 0)
        if self.cooldown_bars > 0:
            self._cooldown_until[symbol] = bar_idx + self.cooldown_bars

        if self.invalidate_swing_on_loss:
            self._used_swing_high[symbol] = self._swing_high.get(symbol)
            self._used_swing_low[symbol] = self._swing_low.get(symbol)

    # ── Swing detection (fractal method) ─────────────────────────────────────

    def _detect_swings(self, symbol: str):
        window = self._ltf_window[symbol]
        if len(window) < self._window_size:
            return

        mid = self.fractal_n
        mid_bar = window[mid]

        is_swing_high = all(
            mid_bar.high > window[i].high
            for i in range(self._window_size)
            if i != mid
        )
        if is_swing_high:
            self._swing_high[symbol] = mid_bar.high
            self._swing_high_bar[symbol] = self._ltf_counter[symbol] - self.fractal_n

        is_swing_low = all(
            mid_bar.low < window[i].low
            for i in range(self._window_size)
            if i != mid
        )
        if is_swing_low:
            self._swing_low[symbol] = mid_bar.low
            self._swing_low_bar[symbol] = self._ltf_counter[symbol] - self.fractal_n

    # ── Pip size helper ───────────────────────────────────────────────────────

    def _pip_size(self, symbol: str) -> float:
        return self.pip_sizes.get(symbol, 0.0001)

    # ── Bias helper ──────────────────────────────────────────────────────────

    @staticmethod
    def _get_bias(ema_fast: float | None, ema_slow: float | None) -> str | None:
        if ema_fast is None or ema_slow is None:
            return None
        return 'BUY' if ema_fast > ema_slow else 'SELL'
