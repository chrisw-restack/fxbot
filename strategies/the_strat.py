from collections import deque

from models import BarEvent, Signal


class TheStratStrategy:
    """
    TheStrat (Rob Smith) multi-timeframe strategy.

    Bias TF: Label candles as 1/2U/2D/3. Detect patterns (2-1-2 rev, 3-1-2,
        1-2-2, 2-1-2 cont, just-3) to set directional bias. Invalidate if
        price moves against the bias (above bias bar high for SELL, below
        bias bar low for BUY).
    Intermediate TF: Swing liquidity filter — if the intermediate-TF fractal
        high (BUY) or low (SELL) is taken, bias is invalidated.
    Entry TF: Entry via market structure shift (MSS) + fair value gap (FVG)
        + 50% fibonacci retracement of the entry-TF swing range.
        TP is set by the risk manager (R:R ratio), not by the strategy.
    """

    ORDER_TYPE = 'PENDING'
    NAME = 'TheStrat'

    def __init__(
        self,
        fractal_n: int = 1,
        bias_types: set[str] | None = None,
        min_sl_pips: float = 10.0,
        cooldown_bars: int = 6,
        pip_sizes: dict[str, float] | None = None,
        tf_bias: str = 'D1',
        tf_intermediate: str = 'H4',
        tf_entry: str = 'H1',
        name: str | None = None,
    ):
        self.NAME = name or f"TheStrat_{tf_bias}_{tf_intermediate}_{tf_entry}"
        self.fractal_n = fractal_n
        self.bias_types = bias_types or {
            '2-1-2_rev', '3-1-2', '1-2-2', '2-1-2_cont', '3',
        }
        self.min_sl_pips = min_sl_pips
        self.cooldown_bars = cooldown_bars
        self.pip_sizes = pip_sizes or {
            'EURUSD': 0.0001, 'GBPUSD': 0.0001, 'AUDUSD': 0.0001,
            'NZDUSD': 0.0001, 'USDJPY': 0.01,   'USDCAD': 0.0001,
            'USDCHF': 0.0001,
        }
        self._tf_bias = tf_bias
        self._tf_intermediate = tf_intermediate
        self._tf_entry = tf_entry
        self.TIMEFRAMES = [tf_bias, tf_intermediate, tf_entry]
        self._fw = 2 * fractal_n + 1       # fractal window size

        # ── D1 state ──────────────────────────────────────────────────────────
        self._d1_prev_bar: dict[str, BarEvent | None] = {}
        self._d1_labels: dict[str, deque] = {}
        self._d1_bias: dict[str, str | None] = {}
        self._d1_bias_type: dict[str, str | None] = {}
        self._d1_prev_high: dict[str, float | None] = {}
        self._d1_prev_low: dict[str, float | None] = {}
        self._d1_invalidated: dict[str, bool] = {}

        # ── H4 state ──────────────────────────────────────────────────────────
        self._h4_window: dict[str, deque] = {}
        self._h4_swing_high: dict[str, float | None] = {}
        self._h4_swing_low: dict[str, float | None] = {}
        self._h4_liq_taken: dict[str, bool] = {}

        # ── H1 state ──────────────────────────────────────────────────────────
        self._h1_window: dict[str, deque] = {}
        self._h1_bar_count: dict[str, int] = {}
        self._h1_swing_high: dict[str, float | None] = {}
        self._h1_swing_low: dict[str, float | None] = {}
        self._h1_mss: dict[str, bool] = {}
        self._h1_fvg: dict[str, bool] = {}
        self._h1_move_bars: dict[str, list] = {}
        self._h1_range_low: dict[str, float | None] = {}
        self._h1_range_high: dict[str, float | None] = {}

        # ── Pending order tracking ────────────────────────────────────────────
        self._pend_entry: dict[str, float | None] = {}
        self._pend_dir: dict[str, str | None] = {}
        self._needs_reentry: dict[str, bool] = {}

        # ── Cooldown ──────────────────────────────────────────────────────────
        self._cooldown_until: dict[str, int] = {}

    def reset(self):
        """Clear all internal state."""
        for d in [
            self._d1_prev_bar, self._d1_labels, self._d1_bias, self._d1_bias_type,
            self._d1_prev_high, self._d1_prev_low, self._d1_invalidated,
            self._h4_window, self._h4_swing_high, self._h4_swing_low, self._h4_liq_taken,
            self._h1_window, self._h1_bar_count, self._h1_swing_high, self._h1_swing_low,
            self._h1_mss, self._h1_fvg, self._h1_move_bars,
            self._h1_range_low, self._h1_range_high,
            self._pend_entry, self._pend_dir, self._needs_reentry,
            self._cooldown_until,
        ]:
            d.clear()

    def generate_signal(self, event: BarEvent) -> Signal | None:
        symbol = event.symbol
        self._init_symbol(symbol)

        if event.timeframe == self._tf_bias:
            return self._process_d1(symbol, event)
        if event.timeframe == self._tf_intermediate:
            return self._process_h4(symbol, event)
        if event.timeframe == self._tf_entry:
            return self._process_h1(symbol, event)
        return None

    # ── Initialisation ────────────────────────────────────────────────────────

    def _init_symbol(self, s: str):
        if s in self._d1_labels:
            return
        self._d1_prev_bar[s] = None
        self._d1_labels[s] = deque(maxlen=3)
        self._d1_bias[s] = None
        self._d1_bias_type[s] = None
        self._d1_prev_high[s] = None
        self._d1_prev_low[s] = None
        self._d1_invalidated[s] = False

        self._h4_window[s] = deque(maxlen=self._fw)
        self._h4_swing_high[s] = None
        self._h4_swing_low[s] = None
        self._h4_liq_taken[s] = False

        self._h1_window[s] = deque(maxlen=self._fw)
        self._h1_bar_count[s] = 0
        self._h1_swing_high[s] = None
        self._h1_swing_low[s] = None
        self._h1_mss[s] = False
        self._h1_fvg[s] = False
        self._h1_move_bars[s] = []
        self._h1_range_low[s] = None
        self._h1_range_high[s] = None

        self._pend_entry[s] = None
        self._pend_dir[s] = None
        self._needs_reentry[s] = False
        self._cooldown_until[s] = 0

    # ══════════════════════════════════════════════════════════════════════════
    # D1 — candle labeling, bias detection, invalidation levels
    # ══════════════════════════════════════════════════════════════════════════

    def _process_d1(self, s: str, event: BarEvent) -> Signal | None:
        prev = self._d1_prev_bar[s]
        self._d1_prev_bar[s] = event

        # Cancel any active pending from the previous day
        cancel = None
        if self._pend_entry[s] is not None:
            self._pend_entry[s] = None
            self._pend_dir[s] = None
            self._needs_reentry[s] = False
            cancel = self._cancel_signal(s, event)

        if prev is None:
            return cancel

        # Label the just-completed candle and detect bias
        label = self._label_candle(event, prev)
        self._d1_labels[s].append(label)
        self._d1_bias[s], self._d1_bias_type[s] = self._detect_bias(s, event)

        # Invalidation levels from the just-completed candle
        self._d1_prev_high[s] = event.high
        self._d1_prev_low[s] = event.low

        # Reset daily state (H1 swing levels persist across days for faster warmup)
        self._d1_invalidated[s] = False
        self._h4_liq_taken[s] = False
        self._h1_mss[s] = False
        self._h1_fvg[s] = False
        self._h1_move_bars[s] = []
        self._h1_range_low[s] = None
        self._h1_range_high[s] = None
        self._needs_reentry[s] = False

        return cancel

    @staticmethod
    def _label_candle(cur: BarEvent, prev: BarEvent) -> str:
        """Label a D1 candle relative to the previous candle."""
        above = cur.high > prev.high
        below = cur.low < prev.low
        if above and below:
            return '3'
        if not above and not below:
            return '1'
        return '2U' if above else '2D'

    def _detect_bias(self, s: str, last_bar: BarEvent) -> tuple[str | None, str | None]:
        """Pattern-match the D1 label sequence to determine directional bias."""
        labels = list(self._d1_labels[s])

        # ── 3-candle patterns (higher priority) ──────────────────────────────
        if len(labels) >= 3:
            a, b, c = labels[-3], labels[-2], labels[-1]

            # 2-1-2 reversal: [2U, 1, 2D] → SELL  |  [2D, 1, 2U] → BUY
            # 2-1-2 continuation: [2U, 1, 2U] → BUY  |  [2D, 1, 2D] → SELL
            if b == '1' and a in ('2U', '2D') and c in ('2U', '2D'):
                bias = 'BUY' if c == '2U' else 'SELL'
                if a != c and '2-1-2_rev' in self.bias_types:
                    return bias, '2-1-2_rev'
                if a == c and '2-1-2_cont' in self.bias_types:
                    return bias, '2-1-2_cont'

            # 3-1-2: [3, 1, 2U/2D] → bias from the 2 direction
            if a == '3' and b == '1' and c in ('2U', '2D'):
                bias = 'BUY' if c == '2U' else 'SELL'
                if '3-1-2' in self.bias_types:
                    return bias, '3-1-2'

            # 1-2-2: [1, 2U, 2U] → BUY  |  [1, 2D, 2D] → SELL
            if a == '1' and b == c and b in ('2U', '2D'):
                bias = 'BUY' if b == '2U' else 'SELL'
                if '1-2-2' in self.bias_types:
                    return bias, '1-2-2'

        # ── 1-candle pattern: just a 3 (close direction) ─────────────────────
        if labels and labels[-1] == '3' and '3' in self.bias_types:
            bias = 'BUY' if last_bar.close > last_bar.open else 'SELL'
            return bias, '3'

        return None, None

    # ══════════════════════════════════════════════════════════════════════════
    # H4 — swing detection + liquidity filter
    # ══════════════════════════════════════════════════════════════════════════

    def _process_h4(self, s: str, event: BarEvent) -> Signal | None:
        self._check_d1_invalidation(s, event)

        # Fractal detection
        self._h4_window[s].append(event)
        w = self._h4_window[s]
        if len(w) == self._fw:
            mid = self.fractal_n
            mb = w[mid]
            if all(mb.high > w[i].high for i in range(self._fw) if i != mid):
                self._h4_swing_high[s] = mb.high
            if all(mb.low < w[i].low for i in range(self._fw) if i != mid):
                self._h4_swing_low[s] = mb.low

        # Check if H4 swing liquidity was taken (on this bar)
        self._check_h4_liquidity(s, event)

        # Cancel pending if invalidated
        if (self._d1_invalidated[s] or self._h4_liq_taken[s]) and self._pend_entry[s] is not None:
            self._pend_entry[s] = None
            self._pend_dir[s] = None
            self._needs_reentry[s] = False
            return self._cancel_signal(s, event)

        return None

    # ══════════════════════════════════════════════════════════════════════════
    # H1 — entry logic (MSS + FVG + 50% fib retracement)
    # ══════════════════════════════════════════════════════════════════════════

    def _process_h1(self, s: str, event: BarEvent) -> Signal | None:
        self._check_d1_invalidation(s, event)
        self._check_h4_liquidity(s, event)
        self._h1_bar_count[s] += 1
        bar_idx = self._h1_bar_count[s]
        bias = self._d1_bias[s]

        # Always update H1 fractal window (persists across days)
        self._h1_window[s].append(event)
        if len(self._h1_window[s]) == self._fw:
            mid = self.fractal_n
            mb = self._h1_window[s][mid]
            if all(mb.high > self._h1_window[s][i].high
                   for i in range(self._fw) if i != mid):
                self._h1_swing_high[s] = mb.high
            if all(mb.low < self._h1_window[s][i].low
                   for i in range(self._fw) if i != mid):
                self._h1_swing_low[s] = mb.low

        # ── No bias → cancel and return ──────────────────────────────────────
        if bias is None:
            if self._pend_entry[s] is not None:
                self._pend_entry[s] = None
                self._pend_dir[s] = None
                self._needs_reentry[s] = False
                return self._cancel_signal(s, event)
            return None

        # ── Update move tracking (range, MSS, FVG) ───────────────────────────
        self._h1_move_bars[s].append(event)
        if self._h1_range_low[s] is None or event.low < self._h1_range_low[s]:
            self._h1_range_low[s] = event.low
        if self._h1_range_high[s] is None or event.high > self._h1_range_high[s]:
            self._h1_range_high[s] = event.high

        if not self._h1_mss[s]:
            if bias == 'BUY' and self._h1_swing_high[s] is not None:
                if event.close > self._h1_swing_high[s]:
                    self._h1_mss[s] = True
            elif bias == 'SELL' and self._h1_swing_low[s] is not None:
                if event.close < self._h1_swing_low[s]:
                    self._h1_mss[s] = True

        if not self._h1_fvg[s]:
            self._h1_fvg[s] = self._check_fvg(self._h1_move_bars[s], bias)

        # ── Pending fill check (before invalidation — fill takes priority) ───
        if self._pend_entry[s] is not None:
            if event.low <= self._pend_entry[s] <= event.high:
                self._pend_entry[s] = None
                self._pend_dir[s] = None
                return None

        # ── Invalidation → cancel pending ─────────────────────────────────────
        if self._d1_invalidated[s] or self._h4_liq_taken[s]:
            if self._pend_entry[s] is not None:
                self._pend_entry[s] = None
                self._pend_dir[s] = None
                self._needs_reentry[s] = False
                return self._cancel_signal(s, event)
            self._needs_reentry[s] = False
            return None

        # ── Cooldown ──────────────────────────────────────────────────────────
        if bar_idx < self._cooldown_until[s]:
            return None

        # ── Pending range-change check → cancel and re-place next bar ─────────
        if self._pend_entry[s] is not None:
            new_entry = self._calc_entry(s)
            if new_entry is not None and abs(new_entry - self._pend_entry[s]) > self._pip_size(s):
                self._pend_entry[s] = None
                self._pend_dir[s] = None
                self._needs_reentry[s] = True
                return self._cancel_signal(s, event)
            return None  # pending unchanged, wait for fill

        # ── Re-entry after cancel ─────────────────────────────────────────────
        if self._needs_reentry[s]:
            self._needs_reentry[s] = False
            return self._place_pending(s, event)

        # ── New entry if all conditions met ───────────────────────────────────
        if self._h1_mss[s] and self._h1_fvg[s]:
            return self._place_pending(s, event)

        return None

    # ══════════════════════════════════════════════════════════════════════════
    # Shared helpers
    # ══════════════════════════════════════════════════════════════════════════

    def _check_d1_invalidation(self, s: str, event: BarEvent):
        """Invalidate bias if price moves against it (above high for SELL, below low for BUY)."""
        if self._d1_invalidated[s]:
            return
        bias = self._d1_bias[s]
        if bias == 'BUY' and self._d1_prev_low[s] is not None:
            if event.low <= self._d1_prev_low[s]:
                self._d1_invalidated[s] = True
        elif bias == 'SELL' and self._d1_prev_high[s] is not None:
            if event.high >= self._d1_prev_high[s]:
                self._d1_invalidated[s] = True

    def _check_h4_liquidity(self, s: str, event: BarEvent):
        """Check if H4 swing liquidity was taken on this bar."""
        if self._h4_liq_taken[s]:
            return
        bias = self._d1_bias[s]
        if bias == 'BUY' and self._h4_swing_high[s] is not None:
            if event.high >= self._h4_swing_high[s]:
                self._h4_liq_taken[s] = True
        elif bias == 'SELL' and self._h4_swing_low[s] is not None:
            if event.low <= self._h4_swing_low[s]:
                self._h4_liq_taken[s] = True

    @staticmethod
    def _check_fvg(bars: list[BarEvent], direction: str) -> bool:
        """Check for a fair value gap in the bar list."""
        for i in range(len(bars) - 2):
            if direction == 'BUY':
                # Bullish FVG: candle 3 low > candle 1 high (gap up)
                if bars[i + 2].low > bars[i].high:
                    return True
            else:
                # Bearish FVG: candle 3 high < candle 1 low (gap down)
                if bars[i + 2].high < bars[i].low:
                    return True
        return False

    def _calc_entry(self, s: str) -> float | None:
        """Calculate 50% fibonacci retracement of the H1 range."""
        lo, hi = self._h1_range_low[s], self._h1_range_high[s]
        if lo is None or hi is None or hi <= lo:
            return None
        return (lo + hi) / 2

    def _place_pending(self, s: str, event: BarEvent) -> Signal | None:
        """Place a pending order at 50% of the entry-TF range."""
        bias = self._d1_bias[s]
        entry = self._calc_entry(s)
        if entry is None or bias is None:
            return None

        lo, hi = self._h1_range_low[s], self._h1_range_high[s]

        # SL at the opposite extreme of the entry range
        sl = lo if bias == 'BUY' else hi

        if sl is None:
            return None

        # Validate minimum SL
        sl_pips = abs(entry - sl) / self._pip_size(s)
        if sl_pips < self.min_sl_pips:
            return None

        self._pend_entry[s] = entry
        self._pend_dir[s] = bias

        # TP left to risk manager (R:R ratio)
        return Signal(
            symbol=s,
            direction=bias,
            order_type=self.ORDER_TYPE,
            entry_price=entry,
            stop_loss=sl,
            strategy_name=self.NAME,
            timestamp=event.timestamp,
        )

    def _cancel_signal(self, s: str, event: BarEvent) -> Signal:
        return Signal(
            symbol=s, direction='CANCEL', order_type=self.ORDER_TYPE,
            entry_price=0.0, stop_loss=0.0,
            strategy_name=self.NAME, timestamp=event.timestamp,
        )

    def _pip_size(self, s: str) -> float:
        return self.pip_sizes.get(s, 0.0001)

    # ── Post-trade feedback ───────────────────────────────────────────────────

    def notify_loss(self, symbol: str):
        bar_idx = self._h1_bar_count.get(symbol, 0)
        self._cooldown_until[symbol] = bar_idx + self.cooldown_bars

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def get_status(self, symbol: str) -> dict:
        s = symbol
        return {
            'd1_bias': self._d1_bias.get(s),
            'bias_type': self._d1_bias_type.get(s),
            'd1_invalidated': self._d1_invalidated.get(s, False),
            'd1_prev_high': self._d1_prev_high.get(s),
            'd1_prev_low': self._d1_prev_low.get(s),
            'h4_swing_high': self._h4_swing_high.get(s),
            'h4_swing_low': self._h4_swing_low.get(s),
            'h4_liq_taken': self._h4_liq_taken.get(s, False),
            'h1_swing_high': self._h1_swing_high.get(s),
            'h1_swing_low': self._h1_swing_low.get(s),
            'h1_mss': self._h1_mss.get(s, False),
            'h1_fvg': self._h1_fvg.get(s, False),
            'h1_range': f"{self._h1_range_low.get(s)}-{self._h1_range_high.get(s)}",
            'pending': self._pend_dir.get(s),
        }
