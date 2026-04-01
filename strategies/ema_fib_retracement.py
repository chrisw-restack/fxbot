from collections import deque

from models import BarEvent, Signal


class EmaFibRetracementStrategy:
    """
    Multi-timeframe EMA + Fibonacci retracement strategy.

    D1 + H1 EMA bias must agree (10 EMA vs 20 EMA). When aligned, places
    PENDING orders at the 61.8% Fibonacci retracement of the most recent
    H1 swing. TP at 200% extension. Cancels pending orders when bias flips.
    """

    TIMEFRAMES = ['D1', 'H1']
    ORDER_TYPE = 'PENDING'
    NAME = 'EmaFibRetracement'

    def __init__(
        self,
        ema_fast: int = 10,
        ema_slow: int = 20,
        fractal_n: int = 3,
        fib_entry: float = 0.618,
        fib_tp: float = 2.0,
        swing_max_age: int = 100,
        cooldown_bars: int = 10,
        min_swing_pips: float = 15.0,
        ema_sep_pct: float = 0.0005,
        invalidate_swing_on_loss: bool = True,
        blocked_hours: tuple[int, ...] = (16, 17, 18, 19, 20, 21, 22, 23),
        min_d1_atr_pips: float = 50.0,
        d1_atr_period: int = 14,
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
        self.min_d1_atr_pips = min_d1_atr_pips
        self.d1_atr_period = d1_atr_period
        self.pip_sizes = pip_sizes or {
            'EURUSD': 0.0001, 'GBPUSD': 0.0001, 'AUDUSD': 0.0001,
            'NZDUSD': 0.0001, 'USDJPY': 0.01,   'USDCAD': 0.0001,
            'USDCHF': 0.0001,
            # JPY crosses — must be explicit; fallback default is 0.0001 (wrong for JPY)
            'AUDJPY': 0.01, 'CADJPY': 0.01, 'EURJPY': 0.01,
            'GBPJPY': 0.01, 'NZDJPY': 0.01,
        }

        self._window_size = 2 * fractal_n + 1

        # Per-symbol state
        self._d1_ema_fast: dict[str, float | None] = {}
        self._d1_ema_slow: dict[str, float | None] = {}
        self._d1_bar_count: dict[str, int] = {}
        self._d1_sma_sum_fast: dict[str, float] = {}
        self._d1_sma_sum_slow: dict[str, float] = {}

        self._d1_prev_close: dict[str, float | None] = {}
        self._d1_tr_window: dict[str, deque] = {}
        self._d1_atr: dict[str, float | None] = {}

        self._h1_ema_fast: dict[str, float | None] = {}
        self._h1_ema_slow: dict[str, float | None] = {}
        self._h1_bar_count: dict[str, int] = {}
        self._h1_sma_sum_fast: dict[str, float] = {}
        self._h1_sma_sum_slow: dict[str, float] = {}

        self._h1_window: dict[str, deque] = {}
        self._h1_counter: dict[str, int] = {}

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
        self._d1_ema_fast.clear()
        self._d1_ema_slow.clear()
        self._d1_bar_count.clear()
        self._d1_sma_sum_fast.clear()
        self._d1_sma_sum_slow.clear()

        self._d1_prev_close.clear()
        self._d1_tr_window.clear()
        self._d1_atr.clear()

        self._h1_ema_fast.clear()
        self._h1_ema_slow.clear()
        self._h1_bar_count.clear()
        self._h1_sma_sum_fast.clear()
        self._h1_sma_sum_slow.clear()

        self._h1_window.clear()
        self._h1_counter.clear()

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

        if event.timeframe == 'D1':
            self._update_d1(symbol, event)
            return None

        if event.timeframe == 'H1':
            return self._process_h1(symbol, event)

        return None

    # ── Initialisation ───────────────────────────────────────────────────────

    def _init_symbol(self, symbol: str):
        if symbol in self._d1_bar_count:
            return
        self._d1_ema_fast[symbol] = None
        self._d1_ema_slow[symbol] = None
        self._d1_bar_count[symbol] = 0
        self._d1_sma_sum_fast[symbol] = 0.0
        self._d1_sma_sum_slow[symbol] = 0.0

        self._d1_prev_close[symbol] = None
        self._d1_tr_window[symbol] = deque(maxlen=self.d1_atr_period)
        self._d1_atr[symbol] = None

        self._h1_ema_fast[symbol] = None
        self._h1_ema_slow[symbol] = None
        self._h1_bar_count[symbol] = 0
        self._h1_sma_sum_fast[symbol] = 0.0
        self._h1_sma_sum_slow[symbol] = 0.0

        self._h1_window[symbol] = deque(maxlen=self._window_size)
        self._h1_counter[symbol] = 0

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

    # ── D1 processing ────────────────────────────────────────────────────────

    def _update_d1(self, symbol: str, event: BarEvent):
        self._d1_bar_count[symbol] += 1
        count = self._d1_bar_count[symbol]

        fast, self._d1_sma_sum_fast[symbol] = self._update_ema(
            event.close, self._d1_ema_fast[symbol], count,
            self._d1_sma_sum_fast[symbol], self.ema_fast,
        )
        slow, self._d1_sma_sum_slow[symbol] = self._update_ema(
            event.close, self._d1_ema_slow[symbol], count,
            self._d1_sma_sum_slow[symbol], self.ema_slow,
        )
        self._d1_ema_fast[symbol] = fast
        self._d1_ema_slow[symbol] = slow

        # D1 ATR
        prev = self._d1_prev_close[symbol]
        if prev is not None:
            tr = max(event.high - event.low,
                     abs(event.high - prev),
                     abs(event.low - prev))
        else:
            tr = event.high - event.low
        self._d1_prev_close[symbol] = event.close

        window = self._d1_tr_window[symbol]
        window.append(tr)
        if len(window) == self.d1_atr_period:
            self._d1_atr[symbol] = sum(window) / self.d1_atr_period

    # ── H1 processing ────────────────────────────────────────────────────────

    def _process_h1(self, symbol: str, event: BarEvent) -> Signal | None:
        # Update H1 EMAs
        self._h1_bar_count[symbol] += 1
        count = self._h1_bar_count[symbol]

        fast, self._h1_sma_sum_fast[symbol] = self._update_ema(
            event.close, self._h1_ema_fast[symbol], count,
            self._h1_sma_sum_fast[symbol], self.ema_fast,
        )
        slow, self._h1_sma_sum_slow[symbol] = self._update_ema(
            event.close, self._h1_ema_slow[symbol], count,
            self._h1_sma_sum_slow[symbol], self.ema_slow,
        )
        self._h1_ema_fast[symbol] = fast
        self._h1_ema_slow[symbol] = slow

        # Increment H1 bar counter
        self._h1_counter[symbol] += 1
        bar_idx = self._h1_counter[symbol]

        # Append to fractal window and check for new swings
        self._h1_window[symbol].append(event)
        self._detect_swings(symbol)

        # Check if pending order was filled (bar range includes entry price)
        pending = self._pending_entry[symbol]
        if pending is not None:
            if event.low <= pending <= event.high:
                # Pending filled — clear tracking so new setups can form
                self._pending_entry[symbol] = None
                self._pending_direction[symbol] = None
                return None  # Position now open, wait for SL/TP

            # Pending still unfilled — check if H1 bias flipped → cancel
            h1_bias = self._get_bias(self._h1_ema_fast[symbol], self._h1_ema_slow[symbol])
            if h1_bias is not None and h1_bias != self._pending_direction[symbol]:
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
            return None  # Pending still valid, wait

        # ── Filter 1: Cooldown after stop-out ────────────────────────────────
        if bar_idx < self._cooldown_until[symbol]:
            return None

        # ── Filter 5: Session filter ────────────────────────────────────────
        if self.blocked_hours and event.timestamp.hour in self.blocked_hours:
            return None

        # ── Filter 6: D1 ATR minimum ────────────────────────────────────────
        if self.min_d1_atr_pips > 0:
            d1_atr = self._d1_atr.get(symbol)
            if d1_atr is None:
                return None
            atr_pips = d1_atr / self._pip_size(symbol)
            if atr_pips < self.min_d1_atr_pips:
                return None

        # Need both D1 and H1 EMAs to be seeded
        d1_bias = self._get_bias(self._d1_ema_fast[symbol], self._d1_ema_slow[symbol])
        h1_bias = self._get_bias(self._h1_ema_fast[symbol], self._h1_ema_slow[symbol])

        if d1_bias is None or h1_bias is None:
            return None

        # Biases must agree
        if d1_bias != h1_bias:
            return None

        # ── Filter 4: EMA separation / trend strength ────────────────────────
        if self.ema_sep_pct > 0:
            h1_fast_val = self._h1_ema_fast[symbol]
            h1_slow_val = self._h1_ema_slow[symbol]
            separation = abs(h1_fast_val - h1_slow_val) / h1_slow_val
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

        # ── Filter 2: Invalidate swing after loss ────────────────────────────
        if self.invalidate_swing_on_loss:
            if (swing_high == self._used_swing_high[symbol]
                    and swing_low == self._used_swing_low[symbol]):
                return None

        # Swing must make sense (high > low)
        if swing_high <= swing_low:
            return None

        swing_range = swing_high - swing_low

        # ── Filter 3: Minimum swing range ────────────────────────────────────
        if self.min_swing_pips > 0:
            swing_pips = swing_range / self._pip_size(symbol)
            if swing_pips < self.min_swing_pips:
                return None

        direction = d1_bias

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
        bar_idx = self._h1_counter.get(symbol, 0)
        self._cooldown_until[symbol] = bar_idx + self.cooldown_bars

        if self.invalidate_swing_on_loss:
            self._used_swing_high[symbol] = self._swing_high.get(symbol)
            self._used_swing_low[symbol] = self._swing_low.get(symbol)

    # ── Diagnostics ─────────────────────────────────────────────────────────

    def get_status(self, symbol: str) -> dict:
        """Return current strategy state for a symbol (for diagnostic logging)."""
        d1_bias = self._get_bias(self._d1_ema_fast.get(symbol), self._d1_ema_slow.get(symbol))
        h1_bias = self._get_bias(self._h1_ema_fast.get(symbol), self._h1_ema_slow.get(symbol))

        h1_fast = self._h1_ema_fast.get(symbol)
        h1_slow = self._h1_ema_slow.get(symbol)
        ema_sep = abs(h1_fast - h1_slow) / h1_slow if (h1_fast and h1_slow) else 0.0

        d1_atr = self._d1_atr.get(symbol)
        atr_pips = d1_atr / self._pip_size(symbol) if d1_atr else 0.0

        swing_h = self._swing_high.get(symbol)
        swing_l = self._swing_low.get(symbol)
        swing_pips = (swing_h - swing_l) / self._pip_size(symbol) if (swing_h and swing_l and swing_h > swing_l) else 0.0

        bar_idx = self._h1_counter.get(symbol, 0)
        h_age = bar_idx - self._swing_high_bar.get(symbol, 0) if swing_h else None
        l_age = bar_idx - self._swing_low_bar.get(symbol, 0) if swing_l else None

        pending = self._pending_direction.get(symbol)

        # Determine the blocking reason
        blocker = None
        if pending:
            blocker = f'PENDING {pending} @ {self._pending_entry[symbol]:.5f}'
        elif bar_idx < self._cooldown_until.get(symbol, 0):
            blocker = 'COOLDOWN'
        elif d1_atr is None or atr_pips < self.min_d1_atr_pips:
            blocker = f'ATR {atr_pips:.0f} < {self.min_d1_atr_pips}'
        elif d1_bias is None or h1_bias is None:
            blocker = 'EMA NOT SEEDED'
        elif d1_bias != h1_bias:
            blocker = f'BIAS DISAGREE D1={d1_bias} H1={h1_bias}'
        elif ema_sep < self.ema_sep_pct:
            blocker = f'EMA SEP {ema_sep:.5f} < {self.ema_sep_pct}'
        elif swing_h is None or swing_l is None:
            blocker = 'NO SWING'
        elif swing_pips < self.min_swing_pips:
            blocker = f'SWING {swing_pips:.0f} < {self.min_swing_pips} pips'
        elif (self.invalidate_swing_on_loss
              and swing_h == self._used_swing_high.get(symbol)
              and swing_l == self._used_swing_low.get(symbol)):
            blocker = 'SWING USED (loss)'
        else:
            blocker = 'READY (blocked_hours?)'

        return {
            'd1_bias': d1_bias,
            'h1_bias': h1_bias,
            'ema_sep': f'{ema_sep:.5f}',
            'atr_pips': f'{atr_pips:.0f}',
            'swing': f'{swing_l}-{swing_h}' if (swing_h and swing_l) else 'None',
            'swing_pips': f'{swing_pips:.0f}',
            'swing_age': f'H={h_age} L={l_age}',
            'blocker': blocker,
        }

    # ── Swing detection (fractal method) ─────────────────────────────────────

    def _detect_swings(self, symbol: str):
        window = self._h1_window[symbol]
        if len(window) < self._window_size:
            return

        mid = self.fractal_n  # index of the middle bar in the window
        mid_bar = window[mid]

        # Check fractal high: middle bar's high exceeds all N bars on each side
        is_swing_high = all(
            mid_bar.high > window[i].high
            for i in range(self._window_size)
            if i != mid
        )
        if is_swing_high:
            self._swing_high[symbol] = mid_bar.high
            self._swing_high_bar[symbol] = self._h1_counter[symbol] - self.fractal_n

        # Check fractal low: middle bar's low is below all N bars on each side
        is_swing_low = all(
            mid_bar.low < window[i].low
            for i in range(self._window_size)
            if i != mid
        )
        if is_swing_low:
            self._swing_low[symbol] = mid_bar.low
            self._swing_low_bar[symbol] = self._h1_counter[symbol] - self.fractal_n

    # ── Pip size helper ───────────────────────────────────────────────────────

    def _pip_size(self, symbol: str) -> float:
        return self.pip_sizes.get(symbol, 0.0001)

    # ── Bias helper ──────────────────────────────────────────────────────────

    @staticmethod
    def _get_bias(ema_fast: float | None, ema_slow: float | None) -> str | None:
        if ema_fast is None or ema_slow is None:
            return None
        return 'BUY' if ema_fast > ema_slow else 'SELL'
