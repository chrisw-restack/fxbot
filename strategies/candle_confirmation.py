"""
Candle Confirmation

Bias timeframe:
  - Bullish engulf: current close above the previous candle body high.
  - Bearish engulf: current close below the previous candle body low.
  - Wicks are ignored for engulf detection.

Entry timeframe:
  - Bias is invalid before entry if price reaches the engulfing candle extreme.
  - Wait for retracement into the engulfing candle range.
  - Enter on a candle close through a confirmed fractal swing in the bias direction.
  - The breaking leg must contain a fair value gap.

Defaults are H1 bias and M5 entry.
"""

from collections import deque

from models import BarEvent, Signal


class CandleConfirmationStrategy:
    ORDER_TYPE = 'MARKET'

    def __init__(
        self,
        tf_bias: str = 'H1',
        tf_entry: str = 'M5',
        fractal_n: int = 2,
        retrace_pct: float = 0.5,
        tp_range_pct: float = 1.0,
        sl_rr_ratio: float = 1.0,
        sl_mode: str = 'symmetric',  # 'symmetric' | 'mss_bar' | 'structural'
        require_fvg: bool = True,
        blocked_hours: tuple = (),
        min_sl_pips: float = 5.0,
        pip_sizes: dict | None = None,
        tf_trend: str | None = None,
        ema_fast: int = 20,
        ema_slow: int = 50,
        ema_sep_pct: float = 0.0,
        min_engulf_range_pips: float = 0.0,
        min_engulf_body_pct: float = 0.0,
        close_extreme_pct: float = 1.0,
        require_engulf_color: bool = False,
        name: str | None = None,
    ):
        if fractal_n < 1:
            raise ValueError('fractal_n must be >= 1')
        if not 0.0 < retrace_pct < 1.0:
            raise ValueError('retrace_pct must be between 0.0 and 1.0')
        if not 0.0 < tp_range_pct <= 3.0:
            raise ValueError('tp_range_pct must be between 0.0 and 3.0')
        if sl_rr_ratio < 1.0:
            raise ValueError('sl_rr_ratio must be >= 1.0')
        if sl_mode not in {'symmetric', 'mss_bar', 'structural'}:
            raise ValueError("sl_mode must be 'symmetric', 'mss_bar', or 'structural'")
        if tf_trend not in {None, 'H4', 'D1'}:
            raise ValueError("tf_trend must be None, 'H4', or 'D1'")
        if ema_fast < 1 or ema_slow < 1:
            raise ValueError('ema_fast and ema_slow must be >= 1')
        if ema_fast >= ema_slow:
            raise ValueError('ema_fast must be less than ema_slow')
        if min_engulf_body_pct < 0.0 or min_engulf_body_pct > 1.0:
            raise ValueError('min_engulf_body_pct must be between 0.0 and 1.0')
        if close_extreme_pct <= 0.0 or close_extreme_pct > 1.0:
            raise ValueError('close_extreme_pct must be between 0.0 and 1.0')

        self.tf_bias = tf_bias
        self.tf_entry = tf_entry
        self.fractal_n = fractal_n
        self.retrace_pct = retrace_pct
        self.tp_range_pct = tp_range_pct
        self.sl_rr_ratio = sl_rr_ratio
        self.sl_mode = sl_mode
        self.require_fvg = require_fvg
        self._blocked = frozenset(blocked_hours)
        self.min_sl_pips = min_sl_pips
        self._pip_sizes = pip_sizes or {}
        self.tf_trend = tf_trend
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.ema_sep_pct = ema_sep_pct
        self.min_engulf_range_pips = min_engulf_range_pips
        self.min_engulf_body_pct = min_engulf_body_pct
        self.close_extreme_pct = close_extreme_pct
        self.require_engulf_color = require_engulf_color

        self.TIMEFRAMES = [tf_bias, tf_entry]
        if tf_trend and tf_trend not in self.TIMEFRAMES:
            self.TIMEFRAMES.append(tf_trend)
        self.NAME = name or f'CandleConfirmation_{tf_bias}_{tf_entry}'

        self._prev_bias_bar: dict[str, BarEvent | None] = {}
        self._entry_bars: dict[str, deque] = {}
        self._bias: dict[str, dict | None] = {}
        self._signal_fired: dict[str, bool] = {}
        self._trend_ema_fast: dict[str, float | None] = {}
        self._trend_ema_slow: dict[str, float | None] = {}
        self._trend_fast_sum: dict[str, float] = {}
        self._trend_slow_sum: dict[str, float] = {}
        self._trend_count: dict[str, int] = {}

    def reset(self):
        self._prev_bias_bar.clear()
        self._entry_bars.clear()
        self._bias.clear()
        self._signal_fired.clear()
        self._trend_ema_fast.clear()
        self._trend_ema_slow.clear()
        self._trend_fast_sum.clear()
        self._trend_slow_sum.clear()
        self._trend_count.clear()

    def notify_loss(self, symbol: str):
        self._bias[symbol] = None
        self._signal_fired[symbol] = False

    def notify_win(self, symbol: str):
        self._bias[symbol] = None
        self._signal_fired[symbol] = False

    def generate_signal(self, event: BarEvent) -> Signal | None:
        symbol = event.symbol
        if symbol not in self._bias:
            self._prev_bias_bar[symbol] = None
            self._entry_bars[symbol] = deque(maxlen=1000)
            self._bias[symbol] = None
            self._signal_fired[symbol] = False
            self._init_trend_state(symbol)

        if self.tf_trend and event.timeframe == self.tf_trend:
            self._update_trend_ema(symbol, event)
            return None
        if event.timeframe == self.tf_bias:
            return self._on_bias_bar(symbol, event)
        if event.timeframe == self.tf_entry:
            return self._on_entry_bar(symbol, event)
        return None

    def _on_bias_bar(self, symbol: str, bar: BarEvent) -> Signal | None:
        prev = self._prev_bias_bar[symbol]

        if prev is not None:
            bullish_engulf = bar.close > max(prev.open, prev.close)
            bearish_engulf = bar.close < min(prev.open, prev.close)

            if not self._signal_fired[symbol]:
                if bullish_engulf:
                    if self._valid_engulf_quality(symbol, 'BUY', bar):
                        self._set_bias(symbol, 'BUY', bar)
                elif bearish_engulf:
                    if self._valid_engulf_quality(symbol, 'SELL', bar):
                        self._set_bias(symbol, 'SELL', bar)

        self._prev_bias_bar[symbol] = bar
        return None

    def _set_bias(self, symbol: str, direction: str, bar: BarEvent):
        rng = bar.high - bar.low
        if rng <= 0:
            self._bias[symbol] = None
            self._signal_fired[symbol] = False
            return

        if not self._trend_allows(symbol, direction):
            self._bias[symbol] = None
            self._signal_fired[symbol] = False
            return

        if direction == 'BUY':
            retrace_level = bar.high - self.retrace_pct * rng
            tp = bar.low + self.tp_range_pct * rng
        else:
            retrace_level = bar.low + self.retrace_pct * rng
            tp = bar.high - self.tp_range_pct * rng

        self._bias[symbol] = {
            'direction': direction,
            'engulf_high': bar.high,
            'engulf_low': bar.low,
            'retrace_level': retrace_level,
            'tp': tp,
            'in_zone': False,
        }
        self._signal_fired[symbol] = False
        self._entry_bars[symbol].clear()

    def _expire_bias(self, symbol: str):
        self._bias[symbol] = None
        self._signal_fired[symbol] = False

    def _on_entry_bar(self, symbol: str, bar: BarEvent) -> Signal | None:
        bias = self._bias[symbol]
        if bias is None:
            return None

        if self._signal_fired[symbol]:
            return None

        if self._blocked and bar.timestamp.hour in self._blocked:
            return None

        self._entry_bars[symbol].append(bar)

        if bias['direction'] == 'BUY':
            return self._check_buy(symbol, bar, bias)
        return self._check_sell(symbol, bar, bias)

    def _check_buy(self, symbol: str, bar: BarEvent, bias: dict) -> Signal | None:
        if bar.high >= bias['engulf_high']:
            self._expire_bias(symbol)
            return None

        if bar.low <= bias['retrace_level']:
            bias['in_zone'] = True

        if not bias['in_zone']:
            return None

        return self._detect_bullish_mss(symbol, bar, bias, list(self._entry_bars[symbol]))

    def _check_sell(self, symbol: str, bar: BarEvent, bias: dict) -> Signal | None:
        if bar.low <= bias['engulf_low']:
            self._expire_bias(symbol)
            return None

        if bar.high >= bias['retrace_level']:
            bias['in_zone'] = True

        if not bias['in_zone']:
            return None

        return self._detect_bearish_mss(symbol, bar, bias, list(self._entry_bars[symbol]))

    def _detect_bullish_mss(
        self, symbol: str, bar: BarEvent, bias: dict, bars: list[BarEvent]
    ) -> Signal | None:
        n = len(bars)
        fn = self.fractal_n
        if n < 2 * fn + 2:
            return None

        current = bars[-1]
        swing_high_idxs = self._swing_high_idxs(bars, fn, n - fn - 1)
        broken = [idx for idx in swing_high_idxs if current.close > bars[idx].high]
        if not broken:
            return None

        sh_idx = max(broken)
        swing_low_idxs = self._swing_low_idxs(bars, fn, sh_idx)
        leg_start = max(swing_low_idxs) if swing_low_idxs else 0
        structural_sl = bars[leg_start].low if swing_low_idxs else min(
            b.low for b in bars[leg_start:sh_idx + 1]
        )
        leg = bars[leg_start:n]
        if self.require_fvg and not self._has_bullish_fvg(leg):
            return None

        entry = current.close
        tp = bias['tp']
        sl = self._calc_buy_sl(structural_sl, entry, tp, current.low)
        if not self._valid_buy_geometry(entry, sl, tp):
            return None
        if not self._valid_sl_distance(symbol, entry, sl):
            return None

        self._signal_fired[symbol] = True
        return Signal(
            symbol=symbol,
            direction='BUY',
            order_type=self.ORDER_TYPE,
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            strategy_name=self.NAME,
            timestamp=bar.timestamp,
        )

    def _detect_bearish_mss(
        self, symbol: str, bar: BarEvent, bias: dict, bars: list[BarEvent]
    ) -> Signal | None:
        n = len(bars)
        fn = self.fractal_n
        if n < 2 * fn + 2:
            return None

        current = bars[-1]
        swing_low_idxs = self._swing_low_idxs(bars, fn, n - fn - 1)
        broken = [idx for idx in swing_low_idxs if current.close < bars[idx].low]
        if not broken:
            return None

        sl_idx = max(broken)
        swing_high_idxs = self._swing_high_idxs(bars, fn, sl_idx)
        leg_start = max(swing_high_idxs) if swing_high_idxs else 0
        structural_sl = bars[leg_start].high if swing_high_idxs else max(
            b.high for b in bars[leg_start:sl_idx + 1]
        )
        leg = bars[leg_start:n]
        if self.require_fvg and not self._has_bearish_fvg(leg):
            return None

        entry = current.close
        tp = bias['tp']
        sl = self._calc_sell_sl(structural_sl, entry, tp, current.high)
        if not self._valid_sell_geometry(entry, sl, tp):
            return None
        if not self._valid_sl_distance(symbol, entry, sl):
            return None

        self._signal_fired[symbol] = True
        return Signal(
            symbol=symbol,
            direction='SELL',
            order_type=self.ORDER_TYPE,
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            strategy_name=self.NAME,
            timestamp=bar.timestamp,
        )

    def _calc_buy_sl(
        self,
        structural_sl: float,
        entry: float,
        tp: float,
        mss_bar_low: float,
    ) -> float:
        if self.sl_mode == 'mss_bar':
            return mss_bar_low
        if self.sl_mode == 'structural':
            return structural_sl
        return entry - (tp - entry) / self.sl_rr_ratio

    def _calc_sell_sl(
        self,
        structural_sl: float,
        entry: float,
        tp: float,
        mss_bar_high: float,
    ) -> float:
        if self.sl_mode == 'mss_bar':
            return mss_bar_high
        if self.sl_mode == 'structural':
            return structural_sl
        return entry + (entry - tp) / self.sl_rr_ratio

    @staticmethod
    def _valid_buy_geometry(entry: float, sl: float, tp: float) -> bool:
        return sl < entry < tp

    @staticmethod
    def _valid_sell_geometry(entry: float, sl: float, tp: float) -> bool:
        return tp < entry < sl

    def _valid_sl_distance(self, symbol: str, entry: float, sl: float) -> bool:
        if self.min_sl_pips <= 0:
            return True
        pip_size = self._pip_sizes.get(symbol, 0.01 if symbol == 'USDJPY' else 0.0001)
        return abs(entry - sl) / pip_size >= self.min_sl_pips

    def _valid_engulf_quality(self, symbol: str, direction: str, bar: BarEvent) -> bool:
        rng = bar.high - bar.low
        if rng <= 0:
            return False

        pip_size = self._pip_sizes.get(symbol, 0.01 if symbol == 'USDJPY' else 0.0001)
        if self.min_engulf_range_pips > 0 and rng / pip_size < self.min_engulf_range_pips:
            return False

        body = abs(bar.close - bar.open)
        if self.min_engulf_body_pct > 0 and body / rng < self.min_engulf_body_pct:
            return False

        if self.require_engulf_color:
            if direction == 'BUY' and bar.close <= bar.open:
                return False
            if direction == 'SELL' and bar.close >= bar.open:
                return False

        if direction == 'BUY':
            return (bar.high - bar.close) / rng <= self.close_extreme_pct
        return (bar.close - bar.low) / rng <= self.close_extreme_pct

    def _init_trend_state(self, symbol: str):
        if symbol in self._trend_count:
            return
        self._trend_ema_fast[symbol] = None
        self._trend_ema_slow[symbol] = None
        self._trend_fast_sum[symbol] = 0.0
        self._trend_slow_sum[symbol] = 0.0
        self._trend_count[symbol] = 0

    def _update_trend_ema(self, symbol: str, bar: BarEvent):
        self._init_trend_state(symbol)
        self._trend_count[symbol] += 1
        count = self._trend_count[symbol]
        self._trend_ema_fast[symbol], self._trend_fast_sum[symbol] = self._update_ema(
            bar.close, self._trend_ema_fast[symbol], count,
            self._trend_fast_sum[symbol], self.ema_fast,
        )
        self._trend_ema_slow[symbol], self._trend_slow_sum[symbol] = self._update_ema(
            bar.close, self._trend_ema_slow[symbol], count,
            self._trend_slow_sum[symbol], self.ema_slow,
        )

    def _trend_allows(self, symbol: str, direction: str) -> bool:
        if not self.tf_trend:
            return True

        fast = self._trend_ema_fast.get(symbol)
        slow = self._trend_ema_slow.get(symbol)
        if fast is None or slow is None:
            return False

        if self.ema_sep_pct > 0 and abs(fast - slow) / slow < self.ema_sep_pct:
            return False

        return (direction == 'BUY' and fast > slow) or (direction == 'SELL' and fast < slow)

    @staticmethod
    def _update_ema(
        close: float,
        prev_ema: float | None,
        bar_count: int,
        sma_sum: float,
        period: int,
    ) -> tuple[float | None, float]:
        if bar_count <= period:
            sma_sum += close
            if bar_count == period:
                return sma_sum / period, sma_sum
            return None, sma_sum

        k = 2.0 / (period + 1)
        return close * k + prev_ema * (1 - k), sma_sum

    @staticmethod
    def _swing_high_idxs(bars: list[BarEvent], fractal_n: int, before_idx: int) -> list[int]:
        return [
            i for i in range(fractal_n, before_idx)
            if all(bars[i].high > bars[i - k].high for k in range(1, fractal_n + 1))
            and all(bars[i].high > bars[i + k].high for k in range(1, fractal_n + 1))
        ]

    @staticmethod
    def _swing_low_idxs(bars: list[BarEvent], fractal_n: int, before_idx: int) -> list[int]:
        return [
            i for i in range(fractal_n, before_idx)
            if all(bars[i].low < bars[i - k].low for k in range(1, fractal_n + 1))
            and all(bars[i].low < bars[i + k].low for k in range(1, fractal_n + 1))
        ]

    @staticmethod
    def _has_bullish_fvg(leg: list[BarEvent]) -> bool:
        return any(leg[i + 2].low > leg[i].high for i in range(len(leg) - 2))

    @staticmethod
    def _has_bearish_fvg(leg: list[BarEvent]) -> bool:
        return any(leg[i + 2].high < leg[i].low for i in range(len(leg) - 2))
