from collections import deque
from datetime import time
from zoneinfo import ZoneInfo

from models import BarEvent, Signal

_UTC_TZ = ZoneInfo('UTC')


class NyIndexOpeningDriveStrategy:
    """
    NY index opening-drive continuation.

    The strategy measures the first NY cash-session drive, waits for a controlled
    pullback into the drive, then enters on a confirmed M5 structure break back
    in the drive direction.
    """

    ORDER_TYPE = 'MARKET'
    NAME = 'NYIndexOpeningDrive'

    def __init__(
        self,
        tf_entry: str = 'M5',
        opening_start_hour: int = 9,
        opening_start_minute: int = 30,
        opening_minutes: int = 30,
        entry_cutoff_hour: int = 12,
        entry_cutoff_minute: int = 0,
        session_timezone: str = 'America/New_York',
        min_drive_pips: float = 40.0,
        max_drive_pips: float | None = 250.0,
        min_drive_body_pct: float = 0.45,
        retrace_min_pct: float = 0.382,
        retrace_max_pct: float = 0.618,
        fractal_n: int = 1,
        rr_ratio: float = 3.0,
        sl_buffer_pips: float = 5.0,
        max_sl_pips: float | None = 180.0,
        trend_filter: str = 'd1_h1_ema',  # 'off' | 'd1_ema' | 'h1_ema' | 'd1_h1_ema'
        ema_fast: int = 20,
        ema_slow: int = 50,
        d1_range_filter: str = 'block_top_pct',  # 'off' | 'block_top_pct'
        d1_range_lookback: int = 60,
        d1_range_block_pct: float = 0.8,
        allowed_directions: tuple[str, ...] | None = None,
        pip_sizes: dict[str, float] | None = None,
        name: str | None = None,
    ):
        if opening_minutes <= 0:
            raise ValueError('opening_minutes must be positive')
        if fractal_n < 1:
            raise ValueError('fractal_n must be >= 1')
        if rr_ratio < 1.0:
            raise ValueError('rr_ratio must be >= 1.0')
        if not 0.0 < retrace_min_pct <= retrace_max_pct < 1.0:
            raise ValueError('retracement percentages must satisfy 0 < min <= max < 1')
        if trend_filter not in {'off', 'd1_ema', 'h1_ema', 'd1_h1_ema'}:
            raise ValueError("trend_filter must be 'off', 'd1_ema', 'h1_ema', or 'd1_h1_ema'")
        if d1_range_filter not in {'off', 'block_top_pct'}:
            raise ValueError("d1_range_filter must be 'off' or 'block_top_pct'")
        if ema_fast >= ema_slow:
            raise ValueError('ema_fast must be less than ema_slow')
        if allowed_directions is not None and not set(allowed_directions).issubset({'BUY', 'SELL'}):
            raise ValueError("allowed_directions must be a subset of {'BUY', 'SELL'}")

        self.tf_entry = tf_entry
        self.opening_start_hour = opening_start_hour
        self.opening_start_minute = opening_start_minute
        self.opening_minutes = opening_minutes
        self.entry_cutoff_hour = entry_cutoff_hour
        self.entry_cutoff_minute = entry_cutoff_minute
        self.session_timezone = session_timezone
        self._session_tz = ZoneInfo(session_timezone)
        self.min_drive_pips = min_drive_pips
        self.max_drive_pips = max_drive_pips
        self.min_drive_body_pct = min_drive_body_pct
        self.retrace_min_pct = retrace_min_pct
        self.retrace_max_pct = retrace_max_pct
        self.fractal_n = fractal_n
        self.rr_ratio = rr_ratio
        self.sl_buffer_pips = sl_buffer_pips
        self.max_sl_pips = max_sl_pips
        self.trend_filter = trend_filter
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.d1_range_filter = d1_range_filter
        self.d1_range_lookback = d1_range_lookback
        self.d1_range_block_pct = d1_range_block_pct
        self.allowed_directions = set(allowed_directions) if allowed_directions else None
        self.pip_sizes = pip_sizes or {'USA100': 1.0, 'USTEC': 1.0, 'US30': 1.0, 'USA30': 1.0}
        self.NAME = name or self.NAME

        self.TIMEFRAMES = ['D1', 'H1', tf_entry]
        self._fractal_window_size = 2 * fractal_n + 1

        self._day: dict[str, object] = {}
        self._opening_open: dict[str, float | None] = {}
        self._opening_high: dict[str, float | None] = {}
        self._opening_low: dict[str, float | None] = {}
        self._opening_close: dict[str, float | None] = {}
        self._opening_done: dict[str, bool] = {}
        self._drive: dict[str, dict | None] = {}
        self._pulled_back: dict[str, bool] = {}
        self._pullback_low: dict[str, float | None] = {}
        self._pullback_high: dict[str, float | None] = {}
        self._traded_day: dict[str, bool] = {}
        self._entry_bars: dict[str, deque] = {}
        self._last_swing_high: dict[str, float | None] = {}
        self._last_swing_low: dict[str, float | None] = {}
        self._d1_ema_fast: dict[str, float | None] = {}
        self._d1_ema_slow: dict[str, float | None] = {}
        self._d1_fast_sum: dict[str, float] = {}
        self._d1_slow_sum: dict[str, float] = {}
        self._d1_count: dict[str, int] = {}
        self._h1_ema_fast: dict[str, float | None] = {}
        self._h1_ema_slow: dict[str, float | None] = {}
        self._h1_fast_sum: dict[str, float] = {}
        self._h1_slow_sum: dict[str, float] = {}
        self._h1_count: dict[str, int] = {}
        self._d1_ranges: dict[str, deque] = {}
        self._d1_range_percentile: dict[str, float | None] = {}
        self._last_signal_context: dict[str, dict | None] = {}

    def reset(self):
        for state in (
            self._day, self._opening_open, self._opening_high, self._opening_low,
            self._opening_close, self._opening_done, self._drive, self._pulled_back,
            self._pullback_low, self._pullback_high, self._traded_day, self._entry_bars,
            self._last_swing_high, self._last_swing_low, self._d1_ema_fast,
            self._d1_ema_slow, self._d1_fast_sum, self._d1_slow_sum, self._d1_count,
            self._h1_ema_fast, self._h1_ema_slow, self._h1_fast_sum, self._h1_slow_sum,
            self._h1_count, self._d1_ranges, self._d1_range_percentile,
            self._last_signal_context,
        ):
            state.clear()

    def generate_signal(self, event: BarEvent) -> Signal | None:
        self._init_symbol(event.symbol)

        if event.timeframe == 'D1':
            self._on_d1_bar(event)
            return None
        if event.timeframe == 'H1':
            self._on_h1_bar(event)
            return None
        if event.timeframe != self.tf_entry:
            return None

        self._roll_day(event.symbol, event)
        return self._on_entry_bar(event)

    def notify_win(self, symbol: str):
        self._traded_day[symbol] = True

    def notify_loss(self, symbol: str):
        self._traded_day[symbol] = True

    def get_last_signal_context(self, symbol: str) -> dict | None:
        return self._last_signal_context.get(symbol)

    def _init_symbol(self, symbol: str):
        if symbol in self._day:
            return
        self._day[symbol] = None
        self._reset_session(symbol)
        self._entry_bars[symbol] = deque(maxlen=max(100, 20 * self._fractal_window_size))
        self._last_swing_high[symbol] = None
        self._last_swing_low[symbol] = None
        self._d1_ema_fast[symbol] = None
        self._d1_ema_slow[symbol] = None
        self._d1_fast_sum[symbol] = 0.0
        self._d1_slow_sum[symbol] = 0.0
        self._d1_count[symbol] = 0
        self._h1_ema_fast[symbol] = None
        self._h1_ema_slow[symbol] = None
        self._h1_fast_sum[symbol] = 0.0
        self._h1_slow_sum[symbol] = 0.0
        self._h1_count[symbol] = 0
        self._d1_ranges[symbol] = deque(maxlen=max(self.d1_range_lookback, 1))
        self._d1_range_percentile[symbol] = None
        self._last_signal_context[symbol] = None

    def _reset_session(self, symbol: str):
        self._opening_open[symbol] = None
        self._opening_high[symbol] = None
        self._opening_low[symbol] = None
        self._opening_close[symbol] = None
        self._opening_done[symbol] = False
        self._drive[symbol] = None
        self._pulled_back[symbol] = False
        self._pullback_low[symbol] = None
        self._pullback_high[symbol] = None
        self._traded_day[symbol] = False

    def _roll_day(self, symbol: str, event: BarEvent):
        current_day = self._session_datetime(event.timestamp).date()
        if self._day[symbol] != current_day:
            self._day[symbol] = current_day
            self._reset_session(symbol)
            self._entry_bars[symbol].clear()
            self._last_swing_high[symbol] = None
            self._last_swing_low[symbol] = None

    def _on_d1_bar(self, bar: BarEvent):
        symbol = bar.symbol
        self._d1_count[symbol] += 1
        count = self._d1_count[symbol]
        self._d1_ema_fast[symbol], self._d1_fast_sum[symbol] = self._update_ema(
            bar.close, self._d1_ema_fast[symbol], count, self._d1_fast_sum[symbol], self.ema_fast,
        )
        self._d1_ema_slow[symbol], self._d1_slow_sum[symbol] = self._update_ema(
            bar.close, self._d1_ema_slow[symbol], count, self._d1_slow_sum[symbol], self.ema_slow,
        )

        d1_range = bar.high - bar.low
        ranges = self._d1_ranges[symbol]
        if ranges:
            below_or_equal = sum(1 for value in ranges if value <= d1_range)
            self._d1_range_percentile[symbol] = below_or_equal / len(ranges)
        ranges.append(d1_range)

    def _on_h1_bar(self, bar: BarEvent):
        symbol = bar.symbol
        self._h1_count[symbol] += 1
        count = self._h1_count[symbol]
        self._h1_ema_fast[symbol], self._h1_fast_sum[symbol] = self._update_ema(
            bar.close, self._h1_ema_fast[symbol], count, self._h1_fast_sum[symbol], self.ema_fast,
        )
        self._h1_ema_slow[symbol], self._h1_slow_sum[symbol] = self._update_ema(
            bar.close, self._h1_ema_slow[symbol], count, self._h1_slow_sum[symbol], self.ema_slow,
        )

    def _on_entry_bar(self, bar: BarEvent) -> Signal | None:
        symbol = bar.symbol
        now = self._session_datetime(bar.timestamp).time()
        start = time(self.opening_start_hour, self.opening_start_minute)
        end = self._minutes_after(start, self.opening_minutes)
        cutoff = time(self.entry_cutoff_hour, self.entry_cutoff_minute)

        if now < start:
            return None
        if start <= now < end:
            self._update_opening_drive(symbol, bar)
            self._update_fractal(symbol, bar)
            return None

        if not self._opening_done[symbol]:
            self._finalize_opening_drive(symbol)
        self._update_fractal(symbol, bar)

        if self._traded_day[symbol] or self._drive[symbol] is None or now >= cutoff:
            return None

        drive = self._drive[symbol]
        if drive['direction'] == 'BUY':
            return self._check_buy(bar, drive)
        return self._check_sell(bar, drive)

    def _update_opening_drive(self, symbol: str, bar: BarEvent):
        if self._opening_open[symbol] is None:
            self._opening_open[symbol] = bar.open
            self._opening_high[symbol] = bar.high
            self._opening_low[symbol] = bar.low
        else:
            self._opening_high[symbol] = max(self._opening_high[symbol], bar.high)
            self._opening_low[symbol] = min(self._opening_low[symbol], bar.low)
        self._opening_close[symbol] = bar.close

    def _finalize_opening_drive(self, symbol: str):
        self._opening_done[symbol] = True
        open_price = self._opening_open[symbol]
        high = self._opening_high[symbol]
        low = self._opening_low[symbol]
        close = self._opening_close[symbol]
        if open_price is None or high is None or low is None or close is None:
            self._traded_day[symbol] = True
            return

        rng = high - low
        net = close - open_price
        if rng <= 0 or net == 0:
            self._traded_day[symbol] = True
            return

        direction = 'BUY' if net > 0 else 'SELL'
        if self.allowed_directions is not None and direction not in self.allowed_directions:
            self._traded_day[symbol] = True
            return
        pip = self._pip_size(symbol)
        range_pips = rng / pip
        body_pct = abs(net) / rng
        if range_pips < self.min_drive_pips:
            self._traded_day[symbol] = True
            return
        if self.max_drive_pips is not None and range_pips > self.max_drive_pips:
            self._traded_day[symbol] = True
            return
        if body_pct < self.min_drive_body_pct:
            self._traded_day[symbol] = True
            return
        if not self._trend_allows(symbol, direction) or not self._d1_regime_allows(symbol):
            self._traded_day[symbol] = True
            return

        self._drive[symbol] = {
            'direction': direction,
            'open': open_price,
            'high': high,
            'low': low,
            'close': close,
            'range': rng,
            'range_pips': range_pips,
            'body_pct': body_pct,
        }

    def _check_buy(self, bar: BarEvent, drive: dict) -> Signal | None:
        symbol = bar.symbol
        upper = drive['high'] - self.retrace_min_pct * drive['range']
        lower = drive['high'] - self.retrace_max_pct * drive['range']
        if bar.low <= drive['low'] or bar.low < lower:
            self._traded_day[symbol] = True
            return None
        if not self._pulled_back[symbol] and bar.low <= upper:
            self._pulled_back[symbol] = True
            self._pullback_low[symbol] = bar.low
            self._pullback_high[symbol] = bar.high
        if self._pulled_back[symbol]:
            self._pullback_low[symbol] = min(self._pullback_low[symbol], bar.low)
            self._pullback_high[symbol] = max(self._pullback_high[symbol], bar.high)
            swing = self._last_swing_high[symbol]
            if swing is not None and bar.close > swing:
                return self._build_signal(bar, 'BUY', drive)
        return None

    def _check_sell(self, bar: BarEvent, drive: dict) -> Signal | None:
        symbol = bar.symbol
        lower = drive['low'] + self.retrace_min_pct * drive['range']
        upper = drive['low'] + self.retrace_max_pct * drive['range']
        if bar.high >= drive['high'] or bar.high > upper:
            self._traded_day[symbol] = True
            return None
        if not self._pulled_back[symbol] and bar.high >= lower:
            self._pulled_back[symbol] = True
            self._pullback_low[symbol] = bar.low
            self._pullback_high[symbol] = bar.high
        if self._pulled_back[symbol]:
            self._pullback_low[symbol] = min(self._pullback_low[symbol], bar.low)
            self._pullback_high[symbol] = max(self._pullback_high[symbol], bar.high)
            swing = self._last_swing_low[symbol]
            if swing is not None and bar.close < swing:
                return self._build_signal(bar, 'SELL', drive)
        return None

    def _build_signal(self, bar: BarEvent, direction: str, drive: dict) -> Signal | None:
        symbol = bar.symbol
        entry = bar.close
        pip = self._pip_size(symbol)
        buffer_price = self.sl_buffer_pips * pip
        if direction == 'BUY':
            stop = self._pullback_low[symbol] - buffer_price
            if stop >= entry:
                return None
            risk = entry - stop
            tp = entry + self.rr_ratio * risk
        else:
            stop = self._pullback_high[symbol] + buffer_price
            if stop <= entry:
                return None
            risk = stop - entry
            tp = entry - self.rr_ratio * risk

        risk_pips = risk / pip
        if self.max_sl_pips is not None and risk_pips > self.max_sl_pips:
            self._traded_day[symbol] = True
            return None

        self._traded_day[symbol] = True
        self._last_signal_context[symbol] = {
            'opening_drive_direction': direction,
            'opening_drive_pips': round(drive['range_pips'], 1),
            'opening_drive_body_pct': round(drive['body_pct'], 3),
            'pullback_low': self._pullback_low[symbol],
            'pullback_high': self._pullback_high[symbol],
            'risk_pips': round(risk_pips, 1),
            'd1_range_percentile': self._d1_range_percentile[symbol],
        }
        return Signal(
            symbol=symbol,
            direction=direction,
            order_type=self.ORDER_TYPE,
            entry_price=entry,
            stop_loss=stop,
            take_profit=tp,
            strategy_name=self.NAME,
            timestamp=bar.timestamp,
        )

    def _update_fractal(self, symbol: str, bar: BarEvent):
        window = self._entry_bars[symbol]
        window.append(bar)
        if len(window) < self._fractal_window_size:
            return
        window = list(window)[-self._fractal_window_size:]
        mid = self.fractal_n
        center = window[mid]
        if all(center.high > b.high for i, b in enumerate(window) if i != mid):
            self._last_swing_high[symbol] = center.high
        if all(center.low < b.low for i, b in enumerate(window) if i != mid):
            self._last_swing_low[symbol] = center.low

    def _trend_allows(self, symbol: str, direction: str) -> bool:
        if self.trend_filter == 'off':
            return True
        checks = []
        if self.trend_filter in {'d1_ema', 'd1_h1_ema'}:
            checks.append((self._d1_ema_fast[symbol], self._d1_ema_slow[symbol]))
        if self.trend_filter in {'h1_ema', 'd1_h1_ema'}:
            checks.append((self._h1_ema_fast[symbol], self._h1_ema_slow[symbol]))
        for fast, slow in checks:
            if fast is None or slow is None:
                return False
            if direction == 'BUY' and fast <= slow:
                return False
            if direction == 'SELL' and fast >= slow:
                return False
        return True

    def _d1_regime_allows(self, symbol: str) -> bool:
        if self.d1_range_filter == 'off':
            return True
        percentile = self._d1_range_percentile[symbol]
        return percentile is not None and percentile < self.d1_range_block_pct

    @staticmethod
    def _update_ema(value: float, current: float | None, count: int, seed_sum: float, period: int):
        if count <= period:
            seed_sum += value
            if count == period:
                return seed_sum / period, seed_sum
            return None, seed_sum
        alpha = 2.0 / (period + 1)
        return value * alpha + current * (1.0 - alpha), seed_sum

    @staticmethod
    def _minutes_after(start: time, minutes: int) -> time:
        total = start.hour * 60 + start.minute + minutes
        return time((total // 60) % 24, total % 60)

    def _session_datetime(self, timestamp):
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=_UTC_TZ)
        return timestamp.astimezone(self._session_tz)

    def _pip_size(self, symbol: str) -> float:
        return self.pip_sizes.get(symbol, 0.0001)
