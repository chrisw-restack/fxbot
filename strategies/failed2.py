from collections import deque
from datetime import timedelta

from models import BarEvent, Signal


_TF_DURATION = {
    'M1': timedelta(minutes=1),
    'M5': timedelta(minutes=5),
    'M15': timedelta(minutes=15),
    'M30': timedelta(minutes=30),
    'H1': timedelta(hours=1),
    'H4': timedelta(hours=4),
    'D1': timedelta(days=1),
}


class Failed2Strategy:
    """
    Failed2: three-timeframe TheStrat-inspired setup.

    HTF sets directional bias from a body-close 2, 3, or failed2 candle.
    ITF confirms with a failed2 in the HTF direction after the HTF candle closes.
    LTF enters on market structure shift, either at market or at an FVG retrace.
    """

    ORDER_TYPE = 'MARKET'

    def __init__(
        self,
        tf_bias: str = 'H4',
        tf_intermediate: str = 'H1',
        tf_entry: str = 'M5',
        entry_mode: str = 'market',  # 'market' | 'fvg'
        mss_fractal_n: int = 2,
        sl_fractal_n: int = 2,
        rr_ratio: float = 2.0,
        fvg_entry_pct: float = 0.5,
        invalidate_on_bias_extreme: bool = False,
        blocked_hours: tuple[int, ...] = (),
        sl_anchor: str = 'wick',  # 'wick' | 'body'
        sl_buffer_pips: float = 0.0,
        max_sl_pips: float | None = None,
        tp_rr_ratio: float | None = None,
        allowed_bias_kinds: set[str] | tuple[str, ...] | None = None,
        trend_filter: str = 'off',  # 'off' | 'h4_ema' | 'd1_ema'
        ema_fast: int = 20,
        ema_slow: int = 50,
        d1_range_filter: str = 'off',  # 'off' | 'block_top_pct'
        d1_range_lookback: int = 60,
        d1_range_block_pct: float = 0.8,
        use_d1_diagnostics: bool = False,
        pip_sizes: dict[str, float] | None = None,
        name: str | None = None,
    ):
        if entry_mode not in {'market', 'fvg'}:
            raise ValueError("entry_mode must be 'market' or 'fvg'")
        if mss_fractal_n < 1 or sl_fractal_n < 1:
            raise ValueError('fractal parameters must be >= 1')
        rr = tp_rr_ratio if tp_rr_ratio is not None else rr_ratio
        if rr < 1.0:
            raise ValueError('rr_ratio must be >= 1.0')
        if not 0.0 <= fvg_entry_pct <= 1.0:
            raise ValueError('fvg_entry_pct must be between 0.0 and 1.0')
        if sl_anchor not in {'wick', 'body'}:
            raise ValueError("sl_anchor must be 'wick' or 'body'")
        if trend_filter not in {'off', 'h4_ema', 'd1_ema'}:
            raise ValueError("trend_filter must be 'off', 'h4_ema', or 'd1_ema'")
        if d1_range_filter not in {'off', 'block_top_pct'}:
            raise ValueError("d1_range_filter must be 'off' or 'block_top_pct'")

        self.tf_bias = tf_bias
        self.tf_intermediate = tf_intermediate
        self.tf_entry = tf_entry
        self.entry_mode = entry_mode
        self.mss_fractal_n = mss_fractal_n
        self.sl_fractal_n = sl_fractal_n
        self.rr_ratio = rr
        self.fvg_entry_pct = fvg_entry_pct
        self.invalidate_on_bias_extreme = invalidate_on_bias_extreme
        self.blocked_hours = set(blocked_hours)
        self.sl_anchor = sl_anchor
        self.sl_buffer_pips = sl_buffer_pips
        self.max_sl_pips = max_sl_pips
        self.allowed_bias_kinds = set(allowed_bias_kinds) if allowed_bias_kinds else None
        self.trend_filter = trend_filter
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.d1_range_filter = d1_range_filter
        self.d1_range_lookback = d1_range_lookback
        self.d1_range_block_pct = d1_range_block_pct
        self.use_d1_diagnostics = use_d1_diagnostics
        self.pip_sizes = pip_sizes or {}

        self.TIMEFRAMES = [tf_bias, tf_intermediate, tf_entry]
        if (
            trend_filter == 'd1_ema'
            or d1_range_filter != 'off'
            or use_d1_diagnostics
        ) and 'D1' not in self.TIMEFRAMES:
            self.TIMEFRAMES = ['D1'] + self.TIMEFRAMES
        self.ORDER_TYPE = 'PENDING' if entry_mode == 'fvg' else 'MARKET'
        self.NAME = name or f'Failed2_{tf_bias}_{tf_intermediate}_{tf_entry}_{entry_mode}'

        max_fractal = max(mss_fractal_n, sl_fractal_n)
        self._entry_bars_len = max(300, 20 * (2 * max_fractal + 1))

        self._prev_bias_bar: dict[str, BarEvent | None] = {}
        self._prev_itf_bar: dict[str, BarEvent | None] = {}
        self._bias: dict[str, dict | None] = {}
        self._itf_setup: dict[str, dict | None] = {}
        self._entry_bars: dict[str, deque] = {}
        self._pending_entry: dict[str, float | None] = {}
        self._pending_setup_id: dict[str, tuple | None] = {}
        self._traded_setup_id: dict[str, tuple | None] = {}
        self._h4_ema_fast: dict[str, float | None] = {}
        self._h4_ema_slow: dict[str, float | None] = {}
        self._h4_ema_fast_sum: dict[str, float] = {}
        self._h4_ema_slow_sum: dict[str, float] = {}
        self._h4_ema_count: dict[str, int] = {}
        self._d1_ema_fast: dict[str, float | None] = {}
        self._d1_ema_slow: dict[str, float | None] = {}
        self._d1_ema_fast_sum: dict[str, float] = {}
        self._d1_ema_slow_sum: dict[str, float] = {}
        self._d1_ema_count: dict[str, int] = {}
        self._d1_ranges: dict[str, deque] = {}
        self._d1_range_percentile: dict[str, float | None] = {}
        self._d1_range_blocked: dict[str, bool] = {}
        self._last_signal_context: dict[str, dict | None] = {}

    def reset(self):
        for d in (
            self._prev_bias_bar, self._prev_itf_bar, self._bias, self._itf_setup,
            self._entry_bars, self._pending_entry, self._pending_setup_id,
            self._traded_setup_id,
            self._h4_ema_fast, self._h4_ema_slow, self._h4_ema_fast_sum,
            self._h4_ema_slow_sum, self._h4_ema_count,
            self._d1_ema_fast, self._d1_ema_slow, self._d1_ema_fast_sum,
            self._d1_ema_slow_sum, self._d1_ema_count, self._d1_ranges,
            self._d1_range_percentile, self._d1_range_blocked,
            self._last_signal_context,
        ):
            d.clear()

    def generate_signal(self, event: BarEvent) -> Signal | None:
        self._init_symbol(event.symbol)

        if event.timeframe == 'D1':
            self._on_d1_bar(event)
            return None
        if event.timeframe == self.tf_bias:
            return self._on_bias_bar(event)
        if event.timeframe == self.tf_intermediate:
            return self._on_itf_bar(event)
        if event.timeframe == self.tf_entry:
            return self._on_entry_bar(event)
        return None

    def notify_win(self, symbol: str):
        self._pending_entry[symbol] = None
        self._pending_setup_id[symbol] = None

    def notify_loss(self, symbol: str):
        self._pending_entry[symbol] = None
        self._pending_setup_id[symbol] = None

    def get_last_signal_context(self, symbol: str) -> dict | None:
        return self._last_signal_context.get(symbol)

    def _init_symbol(self, symbol: str):
        if symbol in self._bias:
            return
        self._prev_bias_bar[symbol] = None
        self._prev_itf_bar[symbol] = None
        self._bias[symbol] = None
        self._itf_setup[symbol] = None
        self._entry_bars[symbol] = deque(maxlen=self._entry_bars_len)
        self._pending_entry[symbol] = None
        self._pending_setup_id[symbol] = None
        self._traded_setup_id[symbol] = None
        self._h4_ema_fast[symbol] = None
        self._h4_ema_slow[symbol] = None
        self._h4_ema_fast_sum[symbol] = 0.0
        self._h4_ema_slow_sum[symbol] = 0.0
        self._h4_ema_count[symbol] = 0
        self._d1_ema_fast[symbol] = None
        self._d1_ema_slow[symbol] = None
        self._d1_ema_fast_sum[symbol] = 0.0
        self._d1_ema_slow_sum[symbol] = 0.0
        self._d1_ema_count[symbol] = 0
        self._d1_ranges[symbol] = deque(maxlen=max(self.d1_range_lookback, 1))
        self._d1_range_percentile[symbol] = None
        self._d1_range_blocked[symbol] = False
        self._last_signal_context[symbol] = None

    def _on_d1_bar(self, bar: BarEvent):
        symbol = bar.symbol
        self._d1_ema_count[symbol] += 1
        count = self._d1_ema_count[symbol]
        self._d1_ema_fast[symbol], self._d1_ema_fast_sum[symbol] = self._update_ema(
            bar.close, self._d1_ema_fast[symbol], count, self._d1_ema_fast_sum[symbol], self.ema_fast,
        )
        self._d1_ema_slow[symbol], self._d1_ema_slow_sum[symbol] = self._update_ema(
            bar.close, self._d1_ema_slow[symbol], count, self._d1_ema_slow_sum[symbol], self.ema_slow,
        )

        d1_range = bar.high - bar.low
        ranges = self._d1_ranges[symbol]
        if ranges:
            pct = sum(1 for value in ranges if value <= d1_range) / len(ranges)
            self._d1_range_percentile[symbol] = pct
            self._d1_range_blocked[symbol] = (
                self.d1_range_filter == 'block_top_pct' and pct >= self.d1_range_block_pct
            )
        ranges.append(d1_range)

    def _on_bias_bar(self, bar: BarEvent) -> Signal | None:
        symbol = bar.symbol
        self._update_h4_ema(symbol, bar)
        prev = self._prev_bias_bar[symbol]
        self._prev_bias_bar[symbol] = bar

        cancel = self._check_pending_fill_or_cancel(symbol, bar)

        if prev is None:
            return cancel

        new_bias = self._classify_bias(bar, prev)
        if new_bias is None:
            if self._bias_invalidated_by_extreme(symbol, bar):
                self._clear_bias(symbol)
                return cancel or self._cancel_signal(symbol, bar)
            return cancel

        if self.allowed_bias_kinds is not None and new_bias['kind'] not in self.allowed_bias_kinds:
            return cancel

        existing = self._bias[symbol]
        if existing is not None and existing['direction'] != new_bias['direction']:
            cancel = cancel or self._cancel_signal(symbol, bar)

        self._bias[symbol] = {
            'direction': new_bias['direction'],
            'kind': new_bias['kind'],
            'high': bar.high,
            'low': bar.low,
            'timestamp': bar.timestamp,
            'close_time': self._close_time(bar),
        }
        self._itf_setup[symbol] = None
        self._entry_bars[symbol].clear()
        self._pending_entry[symbol] = None
        self._pending_setup_id[symbol] = None
        self._traded_setup_id[symbol] = None
        return cancel

    def _on_itf_bar(self, bar: BarEvent) -> Signal | None:
        symbol = bar.symbol
        prev = self._prev_itf_bar[symbol]
        self._prev_itf_bar[symbol] = bar

        cancel = self._check_pending_fill_or_cancel(symbol, bar)
        bias = self._bias[symbol]
        if bias is None or prev is None:
            return cancel

        if self._close_time(bar) <= bias['close_time']:
            return cancel

        direction = bias['direction']
        if direction == 'BUY':
            confirmed = bar.low < prev.low and bar.close > prev.low
        else:
            confirmed = bar.high > prev.high and bar.close < prev.high

        if not confirmed:
            return cancel

        setup_id = (bar.timestamp, direction)
        if self._pending_entry[symbol] is not None:
            cancel = cancel or self._cancel_signal(symbol, bar)

        self._itf_setup[symbol] = {
            'id': setup_id,
            'direction': direction,
            'timestamp': bar.timestamp,
            'close_time': self._close_time(bar),
        }
        self._pending_entry[symbol] = None
        self._pending_setup_id[symbol] = None
        return cancel

    def _on_entry_bar(self, bar: BarEvent) -> Signal | None:
        symbol = bar.symbol
        self._entry_bars[symbol].append(bar)

        cancel = self._check_pending_fill_or_cancel(symbol, bar)
        if cancel is not None:
            return cancel

        bias = self._bias[symbol]
        setup = self._itf_setup[symbol]
        if bias is None or setup is None:
            return None

        if self._close_time(bar) <= setup['close_time']:
            return None
        if self._traded_setup_id[symbol] == setup['id']:
            return None
        if self._pending_entry[symbol] is not None:
            return None
        if bar.timestamp.hour in self.blocked_hours:
            return None
        if not self._passes_entry_filters(symbol, setup['direction']):
            return None

        bars = list(self._entry_bars[symbol])
        if setup['direction'] == 'BUY':
            signal = self._detect_buy(symbol, bar, setup, bars)
        else:
            signal = self._detect_sell(symbol, bar, setup, bars)

        if signal is not None:
            self._last_signal_context[symbol] = self._build_signal_context(symbol, signal, bar)
            self._traded_setup_id[symbol] = setup['id']
            if signal.order_type == 'PENDING':
                self._pending_entry[symbol] = signal.entry_price
                self._pending_setup_id[symbol] = setup['id']
        return signal

    def _detect_buy(
        self, symbol: str, bar: BarEvent, setup: dict, bars: list[BarEvent]
    ) -> Signal | None:
        n = len(bars)
        fn = self.mss_fractal_n
        current = bars[-1]
        swing_high_idxs = self._swing_high_idxs(bars, fn, n - 1)
        broken = [idx for idx in swing_high_idxs if current.close > bars[idx].high]
        if not broken:
            return None
        broken_idx = max(broken)

        sl_idxs = self._swing_low_idxs(bars, self.sl_fractal_n, broken_idx)
        if not sl_idxs:
            return None
        sl_idx = max(sl_idxs)
        stop_loss = self._buy_sl(symbol, bars[sl_idx])

        if self.entry_mode == 'market':
            entry = bar.close
        else:
            entry = self._fvg_entry_buy(bars[sl_idx: n])
            if entry is None:
                return None

        if stop_loss >= entry:
            return None
        if not self._sl_size_ok(symbol, entry, stop_loss):
            return None

        return self._signal(symbol, 'BUY', entry, stop_loss, bar, setup)

    def _detect_sell(
        self, symbol: str, bar: BarEvent, setup: dict, bars: list[BarEvent]
    ) -> Signal | None:
        n = len(bars)
        fn = self.mss_fractal_n
        current = bars[-1]
        swing_low_idxs = self._swing_low_idxs(bars, fn, n - 1)
        broken = [idx for idx in swing_low_idxs if current.close < bars[idx].low]
        if not broken:
            return None
        broken_idx = max(broken)

        sl_idxs = self._swing_high_idxs(bars, self.sl_fractal_n, broken_idx)
        if not sl_idxs:
            return None
        sl_idx = max(sl_idxs)
        stop_loss = self._sell_sl(symbol, bars[sl_idx])

        if self.entry_mode == 'market':
            entry = bar.close
        else:
            entry = self._fvg_entry_sell(bars[sl_idx: n])
            if entry is None:
                return None

        if stop_loss <= entry:
            return None
        if not self._sl_size_ok(symbol, entry, stop_loss):
            return None

        return self._signal(symbol, 'SELL', entry, stop_loss, bar, setup)

    def _signal(
        self,
        symbol: str,
        direction: str,
        entry: float,
        stop_loss: float,
        bar: BarEvent,
        setup: dict,
    ) -> Signal:
        risk = abs(entry - stop_loss)
        take_profit = entry + self.rr_ratio * risk if direction == 'BUY' else entry - self.rr_ratio * risk
        return Signal(
            symbol=symbol,
            direction=direction,
            order_type=self.ORDER_TYPE,
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            strategy_name=self.NAME,
            timestamp=bar.timestamp,
        )

    def _check_pending_fill_or_cancel(self, symbol: str, bar: BarEvent) -> Signal | None:
        entry = self._pending_entry[symbol]
        if entry is not None and bar.timeframe == self.tf_entry and bar.low <= entry <= bar.high:
            self._pending_entry[symbol] = None
            self._pending_setup_id[symbol] = None
        return None

    def _bias_invalidated_by_extreme(self, symbol: str, bar: BarEvent) -> bool:
        if not self.invalidate_on_bias_extreme:
            return False
        bias = self._bias[symbol]
        if bias is None:
            return False
        if bias['direction'] == 'BUY':
            return bar.high >= bias['high']
        return bar.low <= bias['low']

    def _clear_bias(self, symbol: str):
        self._bias[symbol] = None
        self._itf_setup[symbol] = None
        self._entry_bars[symbol].clear()
        self._pending_entry[symbol] = None
        self._pending_setup_id[symbol] = None
        self._traded_setup_id[symbol] = None

    def _passes_entry_filters(self, symbol: str, direction: str) -> bool:
        if self.d1_range_filter == 'block_top_pct' and self._d1_range_blocked[symbol]:
            return False
        if self.trend_filter == 'off':
            return True
        trend = self._trend_direction(symbol, self.trend_filter)
        return trend == direction

    def _trend_direction(self, symbol: str, trend_filter: str) -> str | None:
        if trend_filter == 'h4_ema':
            fast = self._h4_ema_fast[symbol]
            slow = self._h4_ema_slow[symbol]
        elif trend_filter == 'd1_ema':
            fast = self._d1_ema_fast[symbol]
            slow = self._d1_ema_slow[symbol]
        else:
            return None
        if fast is None or slow is None:
            return None
        if fast > slow:
            return 'BUY'
        if fast < slow:
            return 'SELL'
        return None

    def _trend_alignment(self, symbol: str, direction: str, trend_filter: str) -> str:
        trend = self._trend_direction(symbol, trend_filter)
        if trend is None:
            return 'unknown'
        return 'aligned' if trend == direction else 'counter'

    def _build_signal_context(self, symbol: str, signal: Signal, bar: BarEvent) -> dict:
        bias = self._bias[symbol] or {}
        return {
            'symbol': symbol,
            'direction': signal.direction,
            'session_hour': bar.timestamp.hour,
            'htf_bias_type': bias.get('kind'),
            'h4_trend_alignment': self._trend_alignment(symbol, signal.direction, 'h4_ema'),
            'd1_trend_alignment': self._trend_alignment(symbol, signal.direction, 'd1_ema'),
            'd1_range_percentile': self._d1_range_percentile[symbol],
            'd1_range_blocked': self._d1_range_blocked[symbol],
        }

    def _update_h4_ema(self, symbol: str, bar: BarEvent):
        self._h4_ema_count[symbol] += 1
        count = self._h4_ema_count[symbol]
        self._h4_ema_fast[symbol], self._h4_ema_fast_sum[symbol] = self._update_ema(
            bar.close, self._h4_ema_fast[symbol], count, self._h4_ema_fast_sum[symbol], self.ema_fast,
        )
        self._h4_ema_slow[symbol], self._h4_ema_slow_sum[symbol] = self._update_ema(
            bar.close, self._h4_ema_slow[symbol], count, self._h4_ema_slow_sum[symbol], self.ema_slow,
        )

    @staticmethod
    def _update_ema(
        close: float,
        prev: float | None,
        count: int,
        sma_sum: float,
        period: int,
    ) -> tuple[float | None, float]:
        sma_sum += close
        if period <= 0:
            return None, sma_sum
        if count < period:
            return None, sma_sum
        if count == period:
            return sma_sum / period, sma_sum
        k = 2.0 / (period + 1)
        return close * k + prev * (1 - k), sma_sum

    def _buy_sl(self, symbol: str, bar: BarEvent) -> float:
        anchor = min(bar.open, bar.close) if self.sl_anchor == 'body' else bar.low
        return anchor - self.sl_buffer_pips * self._pip_size(symbol)

    def _sell_sl(self, symbol: str, bar: BarEvent) -> float:
        anchor = max(bar.open, bar.close) if self.sl_anchor == 'body' else bar.high
        return anchor + self.sl_buffer_pips * self._pip_size(symbol)

    def _sl_size_ok(self, symbol: str, entry: float, stop_loss: float) -> bool:
        if self.max_sl_pips is None:
            return True
        sl_pips = abs(entry - stop_loss) / self._pip_size(symbol)
        return sl_pips <= self.max_sl_pips

    @staticmethod
    def _classify_bias(cur: BarEvent, prev: BarEvent) -> dict | None:
        prev_body_high = max(prev.open, prev.close)
        prev_body_low = min(prev.open, prev.close)

        took_high = cur.high > prev.high
        took_low = cur.low < prev.low

        if took_low and cur.close > prev_body_high:
            return {'direction': 'BUY', 'kind': '3'}
        if took_high and cur.close < prev_body_low:
            return {'direction': 'SELL', 'kind': '3'}

        if took_high and cur.close < prev_body_high:
            return {'direction': 'SELL', 'kind': 'failed2'}
        if took_low and cur.close > prev_body_low:
            return {'direction': 'BUY', 'kind': 'failed2'}

        if not took_low and cur.close > prev_body_high:
            return {'direction': 'BUY', 'kind': '2'}
        if not took_high and cur.close < prev_body_low:
            return {'direction': 'SELL', 'kind': '2'}

        return None

    def _fvg_entry_buy(self, leg: list[BarEvent]) -> float | None:
        fvgs = []
        for i in range(len(leg) - 2):
            if leg[i + 2].low > leg[i].high:
                low = leg[i].high
                high = leg[i + 2].low
                fvgs.append((low, high))
        if not fvgs:
            return None
        low, high = fvgs[-1]
        return high - self.fvg_entry_pct * (high - low)

    def _fvg_entry_sell(self, leg: list[BarEvent]) -> float | None:
        fvgs = []
        for i in range(len(leg) - 2):
            if leg[i + 2].high < leg[i].low:
                low = leg[i + 2].high
                high = leg[i].low
                fvgs.append((low, high))
        if not fvgs:
            return None
        low, high = fvgs[-1]
        return low + self.fvg_entry_pct * (high - low)

    @staticmethod
    def _swing_high_idxs(bars: list[BarEvent], fractal_n: int, before_idx: int) -> list[int]:
        limit = min(before_idx, len(bars) - fractal_n)
        return [
            i for i in range(fractal_n, limit)
            if all(bars[i].high > bars[i - k].high for k in range(1, fractal_n + 1))
            and all(bars[i].high > bars[i + k].high for k in range(1, fractal_n + 1))
        ]

    @staticmethod
    def _swing_low_idxs(bars: list[BarEvent], fractal_n: int, before_idx: int) -> list[int]:
        limit = min(before_idx, len(bars) - fractal_n)
        return [
            i for i in range(fractal_n, limit)
            if all(bars[i].low < bars[i - k].low for k in range(1, fractal_n + 1))
            and all(bars[i].low < bars[i + k].low for k in range(1, fractal_n + 1))
        ]

    @staticmethod
    def _close_time(bar: BarEvent):
        return bar.timestamp + _TF_DURATION.get(bar.timeframe, timedelta(hours=1))

    def _cancel_signal(self, symbol: str, bar: BarEvent) -> Signal:
        return Signal(
            symbol=symbol,
            direction='CANCEL',
            order_type='PENDING',
            entry_price=0.0,
            stop_loss=0.0,
            strategy_name=self.NAME,
            timestamp=bar.timestamp,
        )

    def _pip_size(self, symbol: str) -> float:
        return self.pip_sizes.get(symbol, 0.0001)
