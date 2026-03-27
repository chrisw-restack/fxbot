from collections import deque
from datetime import datetime

from models import BarEvent, Signal


def _is_us_dst(dt: datetime) -> bool:
    """Check if a UTC date falls within US DST (second Sunday in March to first Sunday in November)."""
    year = dt.year
    mar1 = datetime(year, 3, 1)
    first_sun_mar = 1 + (6 - mar1.weekday()) % 7
    dst_start_day = first_sun_mar + 7
    dst_start = datetime(year, 3, dst_start_day, 7)

    nov1 = datetime(year, 11, 1)
    first_sun_nov = 1 + (6 - nov1.weekday()) % 7
    dst_end = datetime(year, 11, first_sun_nov, 6)

    return dst_start <= dt < dst_end


class IctJudasSwingStrategy:
    """
    ICT Judas Swing — session-based reversal strategy on M5 with D1 bias filter.

    1. D1 EMA crossover determines daily bias (BUY or SELL only in trend direction)
    2. Track Asian session range, wait for liquidity sweep during London/NY AM
    3. After sweep, detect MSS via fractal swing break
    4. Require a Fair Value Gap (FVG) in the post-sweep bars before entry
    5. Enter MARKET at MSS confirmation candle close

    All session times in UTC with automatic US DST adjustment.
    """

    TIMEFRAMES = ['D1', 'M5']
    ORDER_TYPE = 'MARKET'
    NAME = 'IctJudasSwing'

    def __init__(
        self,
        fractal_n: int = 1,
        min_sl_pips: float = 10.0,
        max_sl_pips: float = 0.0,
        min_sweep_pips: float = 1.0,
        require_sweep_pullback: bool = True,
        require_fvg: bool = False,
        require_d1_bias: bool = False,
        ema_fast: int = 10,
        ema_slow: int = 20,
        pip_sizes: dict[str, float] | None = None,
    ):
        self.fractal_n = fractal_n
        self.min_sl_pips = min_sl_pips
        self.max_sl_pips = max_sl_pips
        self.min_sweep_pips = min_sweep_pips
        self.require_sweep_pullback = require_sweep_pullback
        self.require_fvg = require_fvg
        self.require_d1_bias = require_d1_bias
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.pip_sizes = pip_sizes or {
            'EURUSD': 0.0001, 'GBPUSD': 0.0001, 'AUDUSD': 0.0001,
            'NZDUSD': 0.0001, 'USDJPY': 0.01,   'USDCAD': 0.0001,
            'USDCHF': 0.0001, 'XAUUSD': 0.10,
        }
        self._window_size = 2 * fractal_n + 1

        # ── D1 EMA state ─────────────────────────────────────────────────
        self._d1_ema_fast: dict[str, float | None] = {}
        self._d1_ema_slow: dict[str, float | None] = {}
        self._d1_bar_count: dict[str, int] = {}
        self._d1_sma_sum_fast: dict[str, float] = {}
        self._d1_sma_sum_slow: dict[str, float] = {}

        # ── M5 session state (per-symbol) ────────────────────────────────
        self._current_date: dict[str, object] = {}
        self._asian_high: dict[str, float | None] = {}
        self._asian_low: dict[str, float | None] = {}
        self._london_high: dict[str, float | None] = {}
        self._london_low: dict[str, float | None] = {}
        self._session_high: dict[str, float | None] = {}
        self._session_low: dict[str, float | None] = {}
        self._sweep_direction: dict[str, str | None] = {}
        self._active_session: dict[str, str | None] = {}
        self._mss_bars: dict[str, deque] = {}
        self._mss_swing_low: dict[str, float | None] = {}
        self._mss_swing_high: dict[str, float | None] = {}
        self._traded_london: dict[str, bool] = {}
        self._traded_ny: dict[str, bool] = {}
        self._sweep_bar_idx: dict[str, int] = {}
        self._session_bar_counter: dict[str, int] = {}
        # FVG tracking: all post-sweep M5 bars for FVG detection
        self._post_sweep_bars: dict[str, list] = {}
        self._has_fvg: dict[str, bool] = {}

    def reset(self):
        """Clear all internal state."""
        self._d1_ema_fast.clear()
        self._d1_ema_slow.clear()
        self._d1_bar_count.clear()
        self._d1_sma_sum_fast.clear()
        self._d1_sma_sum_slow.clear()

        self._current_date.clear()
        self._asian_high.clear()
        self._asian_low.clear()
        self._london_high.clear()
        self._london_low.clear()
        self._session_high.clear()
        self._session_low.clear()
        self._sweep_direction.clear()
        self._active_session.clear()
        self._mss_bars.clear()
        self._mss_swing_low.clear()
        self._mss_swing_high.clear()
        self._traded_london.clear()
        self._traded_ny.clear()
        self._sweep_bar_idx.clear()
        self._session_bar_counter.clear()
        self._post_sweep_bars.clear()
        self._has_fvg.clear()

    # ── EMA helper ────────────────────────────────────────────────────────

    def _update_ema(self, close: float, prev_ema: float | None, bar_count: int,
                    sma_sum: float, period: int) -> tuple[float | None, float]:
        sma_sum += close
        if bar_count < period:
            return None, sma_sum
        if bar_count == period:
            return sma_sum / period, sma_sum
        k = 2.0 / (period + 1)
        return close * k + prev_ema * (1 - k), sma_sum

    # ── D1 processing ─────────────────────────────────────────────────────

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

    def _get_d1_bias(self, symbol: str) -> str | None:
        fast = self._d1_ema_fast.get(symbol)
        slow = self._d1_ema_slow.get(symbol)
        if fast is None or slow is None:
            return None
        return 'BUY' if fast > slow else 'SELL'

    # ── Session helpers ───────────────────────────────────────────────────

    def _get_sessions(self, dt: datetime) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
        if _is_us_dst(dt):
            return (0, 4), (6, 9), (12, 15)
        else:
            return (1, 5), (7, 10), (13, 16)

    # ── FVG detection ─────────────────────────────────────────────────────

    def _check_fvg(self, symbol: str, bar: BarEvent):
        """Check for FVG in post-sweep bars. Updates _has_fvg flag."""
        bars = self._post_sweep_bars[symbol]
        bars.append(bar)
        if len(bars) < 3:
            return

        # Check the last 3 bars for an FVG
        c1, c2, c3 = bars[-3], bars[-2], bars[-1]

        sweep_dir = self._sweep_direction[symbol]
        if sweep_dir == 'BEARISH':
            # Bearish FVG: candle 3 high < candle 1 low (gap below candle 2)
            if c3.high < c1.low:
                self._has_fvg[symbol] = True
        else:  # BULLISH
            # Bullish FVG: candle 3 low > candle 1 high (gap above candle 2)
            if c3.low > c1.high:
                self._has_fvg[symbol] = True

    # ── Main entry point ──────────────────────────────────────────────────

    def generate_signal(self, event: BarEvent) -> Signal | None:
        symbol = event.symbol
        self._init_symbol(symbol)

        if event.timeframe == 'D1':
            self._update_d1(symbol, event)
            return None

        if event.timeframe != 'M5':
            return None

        hour = event.timestamp.hour
        bar_date = event.timestamp.date()

        # Daily reset on date change
        if bar_date != self._current_date[symbol]:
            self._reset_daily_state(symbol)
            self._current_date[symbol] = bar_date

        asian, london, ny_am = self._get_sessions(event.timestamp)

        # ── Asian session: build the range ────────────────────────────────
        if asian[0] <= hour < asian[1]:
            if self._asian_high[symbol] is None or event.high > self._asian_high[symbol]:
                self._asian_high[symbol] = event.high
            if self._asian_low[symbol] is None or event.low < self._asian_low[symbol]:
                self._asian_low[symbol] = event.low
            return None

        # ── London session ────────────────────────────────────────────────
        if london[0] <= hour < london[1]:
            if self._london_high[symbol] is None or event.high > self._london_high[symbol]:
                self._london_high[symbol] = event.high
            if self._london_low[symbol] is None or event.low < self._london_low[symbol]:
                self._london_low[symbol] = event.low

            if self._traded_london[symbol]:
                return None
            if self._asian_high[symbol] is None:
                return None

            if self._active_session[symbol] != 'LONDON':
                self._active_session[symbol] = 'LONDON'
                self._reset_session_state(symbol)

            return self._process_session_bar(
                symbol, event,
                range_high=self._asian_high[symbol],
                range_low=self._asian_low[symbol],
                session='LONDON',
            )

        # ── NY AM session ─────────────────────────────────────────────────
        if ny_am[0] <= hour < ny_am[1]:
            if self._traded_ny[symbol]:
                return None
            if self._london_high[symbol] is None:
                return None

            if self._active_session[symbol] != 'NY':
                self._active_session[symbol] = 'NY'
                self._reset_session_state(symbol)

            return self._process_session_bar(
                symbol, event,
                range_high=self._london_high[symbol],
                range_low=self._london_low[symbol],
                session='NY',
            )

        return None

    # ── Session bar processing ────────────────────────────────────────────

    def _process_session_bar(
        self, symbol: str, event: BarEvent,
        range_high: float, range_low: float, session: str,
    ) -> Signal | None:
        self._session_bar_counter[symbol] += 1

        if self._session_high[symbol] is None or event.high > self._session_high[symbol]:
            self._session_high[symbol] = event.high
        if self._session_low[symbol] is None or event.low < self._session_low[symbol]:
            self._session_low[symbol] = event.low

        pip_size = self.pip_sizes.get(symbol, 0.0001)

        # ── Sweep detection (first sweep locks direction) ─────────────
        if self._sweep_direction[symbol] is None:
            if event.high >= range_high:
                sweep_dist = (event.high - range_high) / pip_size
                if sweep_dist >= self.min_sweep_pips:
                    self._sweep_direction[symbol] = 'BEARISH'
                    self._sweep_bar_idx[symbol] = self._session_bar_counter[symbol]
            elif event.low <= range_low:
                sweep_dist = (range_low - event.low) / pip_size
                if sweep_dist >= self.min_sweep_pips:
                    self._sweep_direction[symbol] = 'BULLISH'
                    self._sweep_bar_idx[symbol] = self._session_bar_counter[symbol]

        if self._sweep_direction[symbol] is None:
            return None

        # ── D1 bias filter ────────────────────────────────────────────
        if self.require_d1_bias:
            d1_bias = self._get_d1_bias(symbol)
            if d1_bias is None:
                return None
            # Bearish sweep → SELL signal; only allow if D1 bias is SELL
            # Bullish sweep → BUY signal; only allow if D1 bias is BUY
            expected = 'SELL' if self._sweep_direction[symbol] == 'BEARISH' else 'BUY'
            if d1_bias != expected:
                return None

        # ── Require pullback ──────────────────────────────────────────
        if self.require_sweep_pullback:
            if self._session_bar_counter[symbol] <= self._sweep_bar_idx[symbol]:
                return None

        # ── FVG tracking ──────────────────────────────────────────────
        if self.require_fvg:
            self._check_fvg(symbol, event)

        # ── MSS detection ─────────────────────────────────────────────
        return self._check_mss(symbol, event, session)

    # ── Market Structure Shift detection ──────────────────────────────────

    def _check_mss(self, symbol: str, event: BarEvent, session: str) -> Signal | None:
        window = self._mss_bars[symbol]
        window.append(event)

        if len(window) < self._window_size:
            return None

        mid = self.fractal_n
        mid_bar = window[mid]

        if self._sweep_direction[symbol] == 'BEARISH':
            is_swing_low = all(
                mid_bar.low < window[i].low
                for i in range(len(window))
                if i != mid
            )
            if is_swing_low:
                self._mss_swing_low[symbol] = mid_bar.low

            trigger = self._mss_swing_low[symbol]
            if trigger is not None and event.close < trigger:
                # FVG filter
                if self.require_fvg and not self._has_fvg[symbol]:
                    return None

                sl = self._session_high[symbol]
                pip_size = self.pip_sizes.get(symbol, 0.0001)
                sl_pips = abs(sl - event.close) / pip_size
                if sl_pips < self.min_sl_pips:
                    return None
                if self.max_sl_pips > 0 and sl_pips > self.max_sl_pips:
                    return None
                if session == 'LONDON':
                    self._traded_london[symbol] = True
                else:
                    self._traded_ny[symbol] = True
                return Signal(
                    symbol=symbol,
                    direction='SELL',
                    order_type=self.ORDER_TYPE,
                    entry_price=event.close,
                    stop_loss=sl,
                    strategy_name=self.NAME,
                    timestamp=event.timestamp,
                )

        else:  # BULLISH
            is_swing_high = all(
                mid_bar.high > window[i].high
                for i in range(len(window))
                if i != mid
            )
            if is_swing_high:
                self._mss_swing_high[symbol] = mid_bar.high

            trigger = self._mss_swing_high[symbol]
            if trigger is not None and event.close > trigger:
                # FVG filter
                if self.require_fvg and not self._has_fvg[symbol]:
                    return None

                sl = self._session_low[symbol]
                pip_size = self.pip_sizes.get(symbol, 0.0001)
                sl_pips = abs(event.close - sl) / pip_size
                if sl_pips < self.min_sl_pips:
                    return None
                if self.max_sl_pips > 0 and sl_pips > self.max_sl_pips:
                    return None
                if session == 'LONDON':
                    self._traded_london[symbol] = True
                else:
                    self._traded_ny[symbol] = True
                return Signal(
                    symbol=symbol,
                    direction='BUY',
                    order_type=self.ORDER_TYPE,
                    entry_price=event.close,
                    stop_loss=sl,
                    strategy_name=self.NAME,
                    timestamp=event.timestamp,
                )

        return None

    # ── State management ──────────────────────────────────────────────────

    def _init_symbol(self, symbol: str):
        if symbol in self._current_date:
            return
        # D1 state
        self._d1_ema_fast[symbol] = None
        self._d1_ema_slow[symbol] = None
        self._d1_bar_count[symbol] = 0
        self._d1_sma_sum_fast[symbol] = 0.0
        self._d1_sma_sum_slow[symbol] = 0.0
        # M5 session state
        self._current_date[symbol] = None
        self._asian_high[symbol] = None
        self._asian_low[symbol] = None
        self._london_high[symbol] = None
        self._london_low[symbol] = None
        self._session_high[symbol] = None
        self._session_low[symbol] = None
        self._sweep_direction[symbol] = None
        self._active_session[symbol] = None
        self._mss_bars[symbol] = deque(maxlen=self._window_size)
        self._mss_swing_low[symbol] = None
        self._mss_swing_high[symbol] = None
        self._traded_london[symbol] = False
        self._traded_ny[symbol] = False
        self._sweep_bar_idx[symbol] = 0
        self._session_bar_counter[symbol] = 0
        self._post_sweep_bars[symbol] = []
        self._has_fvg[symbol] = False

    def _reset_session_state(self, symbol: str):
        """Reset state when entering a new session (London or NY)."""
        self._session_high[symbol] = None
        self._session_low[symbol] = None
        self._sweep_direction[symbol] = None
        self._mss_bars[symbol].clear()
        self._mss_swing_low[symbol] = None
        self._mss_swing_high[symbol] = None
        self._session_bar_counter[symbol] = 0
        self._post_sweep_bars[symbol] = []
        self._has_fvg[symbol] = False

    def _reset_daily_state(self, symbol: str):
        """Reset all session state for a new trading day."""
        self._asian_high[symbol] = None
        self._asian_low[symbol] = None
        self._london_high[symbol] = None
        self._london_low[symbol] = None
        self._traded_london[symbol] = False
        self._traded_ny[symbol] = False
        self._reset_session_state(symbol)
