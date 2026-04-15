"""
ICT Market Structure (IMS)

Higher timeframe (HTF) dealing range and bias:
  - Identifies the most recent confirmed fractal swing low (bullish) within htf_lookback bars
    where the subsequent leg:
    (a) takes out the most recent confirmed HTF fractal swing high (MSS on HTF), and
    (b) contains at least one bullish FVG (bar[i+2].low > bar[i].high)
  - Dealing range: HTF swing low -> running max high (updates dynamically on each new HTF high)
  - 50% level recalculates with each new HTF high
  - Bias expires when: HTF swing origin is taken out; price pushes below 30% of the HTF
    range (BUY) / above 70% (SELL); or a HTF bar closes below the lowest bullish FVG in
    the leg (BUY) / above the highest bearish FVG (SELL) — disrespecting the imbalance
    that confirmed the bias signals the move is failing

Stop-loss placement (sl_anchor):
  'swing' — SL at LTF swing low wick (default, original behaviour)
  'body'  — SL at body of the swing low candle (min(open,close)), ignores spike wicks
  'fvg'   — SL at bottom of lowest bullish FVG in the LTF leg; structurally tighter
             since price should respect the imbalance that created the MSS
Additional buffers (applied below/above the anchor):
  sl_buffer_pips — fixed pip buffer (requires pip_sizes dict for non-4dp symbols)
  sl_atr_mult    — dynamic buffer: sl_atr_mult × ATR(14) on LTF bars
  - Mirror logic for bearish (swing high -> running min low, broken below prev swing low)
  - Optional EMA filter on HTF (ema_fast/ema_slow, default 10/20): only take BUY signals
    when HTF EMA fast > slow, SELL when fast < slow. Trades against the HTF EMA trend
    are skipped.

Lower timeframe (LTF) entry:
  - Wait for price to retrace into 50% of the HTF dealing range (bar touches or crosses 50%)
  - Once in zone, look for LTF MSS: close above a confirmed LTF fractal swing high
    (uses ltf_fractal_n, default 2 = 5-candle fractal, 2 lower/higher bars each side)
    where the LTF leg (LTF swing low -> broken swing high) contains a bullish FVG
  - PENDING BUY LIMIT at 50% of the LTF leg
  - SL: LTF swing low
  - TP: HTF swing high (tp_mode='htf_high') or let risk manager calculate from R:R (tp_mode='rr')
# chris note: to test: parameter sweeps: best trading sessions, best fractals, best symbols, htf_lookback, cooldown_bars, tp levels, entry mode, ema values and ema points

Pending order updates:
  - Once a pending is live it is NOT replaced by newer LTF setups — original entry stays.
    This keeps SL at the original level and avoids chasing.
  - Pending is canceled when TP is reached:
      tp_mode='htf_high': canceled when price reaches bias['swing_high'] (BUY) / ['swing_low'] (SELL)
      tp_mode='rr': canceled when price reaches entry ± rr_ratio × SL_distance
  - On HTF bias direction change: cancel pending and reset LTF state
  - On loss (notify_loss): reset LTF state, apply cooldown, HTF bias preserved
  - HTF bias expires when swing origin is taken out (cancel any live pending)

Supported combos: D1/H4, H4/H1, H4/M15
"""

import logging
from collections import deque

from models import BarEvent, Signal

logger = logging.getLogger(__name__)


class ImsStrategy:
    ORDER_TYPE = 'PENDING'

    def __init__(
        self,
        tf_htf: str = 'D1',
        tf_ltf: str = 'H4',
        fractal_n: int = 1,       # HTF fractal: 1 = 3-candle (1 bar each side)
        ltf_fractal_n: int = 2,   # LTF fractal: 2 = 5-candle (2 bars each side)
        htf_lookback: int = 50,
        entry_mode: str = 'pending',  # 'pending' (limit at 50% of LTF leg) | 'market' (close of MSS bar)
        tp_mode: str = 'htf_high',  # 'htf_high' | 'rr'
        rr_ratio: float = 2.0,     # used when tp_mode='rr' to set and cancel pending at target
        cooldown_bars: int = 0,
        blocked_hours: tuple = (),
        ema_fast: int = 10,       # HTF EMA filter — set both to 0 to disable
        ema_slow: int = 20,
        ema_sep: float = 0.0,     # min separation as fraction of price (e.g. 0.001 = 0.1%); 0 = disabled
        sl_anchor: str = 'swing', # 'swing' | 'body' | 'fvg' — SL anchor point on LTF
        sl_buffer_pips: float = 0.0,  # extra pips below/above anchor; 0 = disabled
        sl_atr_mult: float = 0.0,    # extra ATR(14) × mult below/above anchor; 0 = disabled
        pip_sizes: dict | None = None,  # {symbol: pip_size} for sl_buffer_pips conversion
    ):
        self.tf_htf = tf_htf
        self.tf_ltf = tf_ltf
        self.fractal_n = fractal_n
        self.ltf_fractal_n = ltf_fractal_n
        self.htf_lookback = htf_lookback
        self.entry_mode = entry_mode
        self.tp_mode = tp_mode
        self.rr_ratio = rr_ratio
        self.cooldown_bars = cooldown_bars
        self.blocked_hours = set(blocked_hours)
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.ema_sep = ema_sep
        self.sl_anchor = sl_anchor
        self.sl_buffer_pips = sl_buffer_pips
        self.sl_atr_mult = sl_atr_mult
        self._pip_sizes = pip_sizes or {}

        self.TIMEFRAMES = [tf_htf, tf_ltf]
        self.NAME = f'IMS_{tf_htf}_{tf_ltf}'
        self.ORDER_TYPE = 'MARKET' if entry_mode == 'market' else 'PENDING'

        # Per-symbol state
        self._htf_bars: dict[str, deque] = {}
        self._ltf_bars: dict[str, deque] = {}
        self._htf_bias: dict[str, dict | None] = {}
        self._ltf_in_zone: dict[str, bool] = {}
        self._ltf_signal_fired: dict[str, bool] = {}
        self._ltf_last_sl_ts: dict = {}       # timestamp of LTF swing low used in last signal
        self._last_signal_entry: dict[str, float] = {}  # entry price of live pending (for rr TP check)
        self._last_signal_sl: dict[str, float] = {}     # SL price of live pending (for rr TP check)
        self._cooldown: dict[str, int] = {}
        # HTF EMA state
        self._htf_ema_fast: dict[str, float | None] = {}
        self._htf_ema_slow: dict[str, float | None] = {}
        self._htf_ema_fast_sum: dict[str, float] = {}
        self._htf_ema_slow_sum: dict[str, float] = {}
        self._htf_bar_count: dict[str, int] = {}
        # LTF ATR state (Wilder's 14-period, for sl_atr_mult)
        self._ltf_prev_close: dict[str, float | None] = {}
        self._ltf_atr: dict[str, float | None] = {}
        self._ltf_atr_buf: dict[str, list] = {}  # accumulates TRs for initial SMA

    def reset(self):
        self._htf_bars.clear()
        self._ltf_bars.clear()
        self._htf_bias.clear()
        self._ltf_in_zone.clear()
        self._ltf_signal_fired.clear()
        self._ltf_last_sl_ts.clear()
        self._last_signal_entry.clear()
        self._last_signal_sl.clear()
        self._cooldown.clear()
        self._htf_ema_fast.clear()
        self._htf_ema_slow.clear()
        self._htf_ema_fast_sum.clear()
        self._htf_ema_slow_sum.clear()
        self._htf_bar_count.clear()
        self._ltf_prev_close.clear()
        self._ltf_atr.clear()
        self._ltf_atr_buf.clear()

    def notify_loss(self, symbol: str):
        """After a loss: reset LTF state and start cooldown. HTF bias is preserved."""
        self._ltf_in_zone[symbol] = False
        self._ltf_signal_fired[symbol] = False
        self._ltf_last_sl_ts[symbol] = None
        self._last_signal_entry[symbol] = 0.0
        self._last_signal_sl[symbol] = 0.0
        self._ltf_bars[symbol].clear()
        if self.cooldown_bars > 0:
            self._cooldown[symbol] = self.cooldown_bars

    def generate_signal(self, event: BarEvent) -> Signal | None:
        symbol = event.symbol
        if symbol not in self._htf_bias:
            self._htf_bars[symbol] = deque(maxlen=300)
            self._ltf_bars[symbol] = deque(maxlen=1000)
            self._htf_bias[symbol] = None
            self._ltf_in_zone[symbol] = False
            self._ltf_signal_fired[symbol] = False
            self._ltf_last_sl_ts[symbol] = None
            self._last_signal_entry[symbol] = 0.0
            self._last_signal_sl[symbol] = 0.0
            self._cooldown[symbol] = 0
            self._htf_ema_fast[symbol] = None
            self._htf_ema_slow[symbol] = None
            self._htf_ema_fast_sum[symbol] = 0.0
            self._htf_ema_slow_sum[symbol] = 0.0
            self._htf_bar_count[symbol] = 0
            self._ltf_prev_close[symbol] = None
            self._ltf_atr[symbol] = None
            self._ltf_atr_buf[symbol] = []

        if event.timeframe == self.tf_htf:
            return self._on_htf_bar(symbol, event)
        elif event.timeframe == self.tf_ltf:
            return self._on_ltf_bar(symbol, event)
        return None

    # ── EMA helper ────────────────────────────────────────────────────────────

    def _update_ema(self, close: float, prev: float | None, count: int,
                    sma_sum: float, period: int) -> tuple[float | None, float]:
        sma_sum += close
        if count < period:
            return None, sma_sum
        if count == period:
            return sma_sum / period, sma_sum
        k = 2.0 / (period + 1)
        return close * k + prev * (1 - k), sma_sum

    def _htf_ema_trend(self, symbol: str) -> str | None:
        """Return 'BUY', 'SELL', or None if EMAs are not yet ready or disabled."""
        if self.ema_fast == 0 or self.ema_slow == 0:
            return 'ANY'  # filter disabled
        fast = self._htf_ema_fast[symbol]
        slow = self._htf_ema_slow[symbol]
        if fast is None or slow is None:
            return None
        if self.ema_sep > 0 and abs(fast - slow) / slow < self.ema_sep:
            return None  # EMAs too close — trend unclear, skip
        if fast > slow:
            return 'BUY'
        if fast < slow:
            return 'SELL'
        return None

    # ── SL helpers ───────────────────────────────────────────────────────────

    _ATR_PERIOD = 14

    def _pip_size(self, symbol: str) -> float:
        return self._pip_sizes.get(symbol, 0.0001)

    def _update_ltf_atr(self, symbol: str, bar: BarEvent):
        """Update Wilder's ATR(14) on each LTF bar."""
        prev = self._ltf_prev_close[symbol]
        if prev is not None:
            tr = max(bar.high - bar.low,
                     abs(bar.high - prev),
                     abs(bar.low  - prev))
            atr = self._ltf_atr[symbol]
            buf = self._ltf_atr_buf[symbol]
            if atr is None:
                buf.append(tr)
                if len(buf) >= self._ATR_PERIOD:
                    self._ltf_atr[symbol] = sum(buf) / self._ATR_PERIOD
            else:
                self._ltf_atr[symbol] = (atr * (self._ATR_PERIOD - 1) + tr) / self._ATR_PERIOD
        self._ltf_prev_close[symbol] = bar.close

    def _compute_sl_buy(self, symbol: str, bars: list, sl_idx: int, leg: list) -> float:
        """Return the final SL price for a BUY signal."""
        if self.sl_anchor == 'body':
            anchor = min(bars[sl_idx].open, bars[sl_idx].close)
        elif self.sl_anchor == 'fvg':
            fvg_bottoms = [leg[i].high for i in range(len(leg) - 2)
                           if leg[i + 2].low > leg[i].high]
            anchor = min(fvg_bottoms)  # guaranteed non-empty — FVG check already passed
        else:  # 'swing'
            anchor = bars[sl_idx].low
        buf = self._sl_buffer(symbol)
        return anchor - buf

    def _compute_sl_sell(self, symbol: str, bars: list, sh_idx: int, leg: list) -> float:
        """Return the final SL price for a SELL signal."""
        if self.sl_anchor == 'body':
            anchor = max(bars[sh_idx].open, bars[sh_idx].close)
        elif self.sl_anchor == 'fvg':
            fvg_tops = [leg[i].low for i in range(len(leg) - 2)
                        if leg[i + 2].high < leg[i].low]
            anchor = max(fvg_tops)  # guaranteed non-empty
        else:  # 'swing'
            anchor = bars[sh_idx].high
        buf = self._sl_buffer(symbol)
        return anchor + buf

    def _sl_buffer(self, symbol: str) -> float:
        """Return total price buffer to add/subtract from the SL anchor."""
        buf = 0.0
        if self.sl_buffer_pips > 0:
            buf += self.sl_buffer_pips * self._pip_size(symbol)
        if self.sl_atr_mult > 0:
            atr = self._ltf_atr.get(symbol)
            if atr:
                buf += self.sl_atr_mult * atr
        return buf

    # ── HTF ───────────────────────────────────────────────────────────────────

    def _on_htf_bar(self, symbol: str, bar: BarEvent) -> Signal | None:
        self._htf_bars[symbol].append(bar)
        bars = list(self._htf_bars[symbol])
        fn = self.fractal_n
        bias = self._htf_bias[symbol]

        # Update HTF EMAs
        self._htf_bar_count[symbol] += 1
        count = self._htf_bar_count[symbol]
        self._htf_ema_fast[symbol], self._htf_ema_fast_sum[symbol] = self._update_ema(
            bar.close, self._htf_ema_fast[symbol], count,
            self._htf_ema_fast_sum[symbol], self.ema_fast,
        )
        self._htf_ema_slow[symbol], self._htf_ema_slow_sum[symbol] = self._update_ema(
            bar.close, self._htf_ema_slow[symbol], count,
            self._htf_ema_slow_sum[symbol], self.ema_slow,
        )

        # Expiry: swing origin taken out, price pushes too deeply into the range,
        # or HTF bar closes through the imbalance (FVG disrespected)
        if bias is not None:
            if bias['direction'] == 'BUY' and bar.low < bias['swing_low']:
                return self._expire_bias(symbol, bar)
            if bias['direction'] == 'SELL' and bar.high > bias['swing_high']:
                return self._expire_bias(symbol, bar)
            rng = bias['swing_high'] - bias['swing_low']
            if bias['direction'] == 'BUY' and bar.low < bias['swing_low'] + 0.3 * rng:
                return self._expire_bias(symbol, bar)
            if bias['direction'] == 'SELL' and bar.high > bias['swing_low'] + 0.7 * rng:
                return self._expire_bias(symbol, bar)
            if bias['direction'] == 'BUY' and bar.close < bias['fvg_level']:
                return self._expire_bias(symbol, bar)
            if bias['direction'] == 'SELL' and bar.close > bias['fvg_level']:
                return self._expire_bias(symbol, bar)

            # Dynamic range update: extend as price makes new extremes
            if bias['direction'] == 'BUY' and bar.high > bias['swing_high']:
                bias['swing_high'] = bar.high
                bias['dealing_50'] = bias['swing_low'] + (bar.high - bias['swing_low']) * 0.5
            elif bias['direction'] == 'SELL' and bar.low < bias['swing_low']:
                bias['swing_low'] = bar.low
                bias['dealing_50'] = bias['swing_high'] - (bias['swing_high'] - bar.low) * 0.5

        if len(bars) < 2 * fn + 3:
            return None

        new_bias = self._scan_htf_bias(bars, fn)
        if new_bias is None:
            return None

        existing = self._htf_bias[symbol]
        if existing is not None:
            same = (
                existing['direction'] == new_bias['direction']
                and existing['_swing_ts'] == new_bias['_swing_ts']
            )
            if same:
                return None
            # Different bias: cancel pending if live, then switch
            cancel = None
            if self._ltf_signal_fired[symbol] and self.entry_mode == 'pending':
                cancel = Signal(
                    symbol=symbol, direction='CANCEL', order_type='PENDING',
                    entry_price=0.0, stop_loss=0.0,
                    strategy_name=self.NAME, timestamp=bar.timestamp,
                )
            self._htf_bias[symbol] = new_bias
            self._reset_ltf(symbol)
            return cancel

        self._htf_bias[symbol] = new_bias
        return None

    def _scan_htf_bias(self, bars: list, fn: int) -> dict | None:
        """Return the most recent valid bullish or bearish HTF bias, or None."""
        n = len(bars)
        lookback_start = max(fn, n - self.htf_lookback)
        bullish = self._find_bullish_htf(bars, fn, n, lookback_start)
        bearish = self._find_bearish_htf(bars, fn, n, lookback_start)
        if bullish and bearish:
            return bullish if bullish['_swing_ts'] >= bearish['_swing_ts'] else bearish
        return bullish or bearish

    def _find_bullish_htf(self, bars, fn, n, lookback_start) -> dict | None:
        # Confirmed fractal swing lows in lookback window
        swing_low_idxs = [
            i for i in range(lookback_start, n - fn)
            if all(bars[i].low < bars[i - k].low for k in range(1, fn + 1))
            and all(bars[i].low < bars[i + k].low for k in range(1, fn + 1))
        ]
        for sl_idx in reversed(swing_low_idxs):
            swing_low_price = bars[sl_idx].low

            # Previous confirmed swing highs BEFORE this swing low
            prev_sh_idxs = [
                i for i in range(fn, sl_idx)
                if all(bars[i].high > bars[i - k].high for k in range(1, fn + 1))
                and all(bars[i].high > bars[i + k].high for k in range(1, fn + 1))
            ]
            if not prev_sh_idxs:
                continue

            # MSS: the leg (swing low to current) exceeds the most recent prev swing high
            prev_sh_price = bars[max(prev_sh_idxs)].high
            leg = bars[sl_idx:]
            leg_high = max(b.high for b in leg)
            if leg_high <= prev_sh_price:
                continue

            # Bullish FVG in the leg
            fvg_lows = [leg[i].high for i in range(len(leg) - 2) if leg[i + 2].low > leg[i].high]
            if not fvg_lows:
                continue

            dealing_50 = swing_low_price + (leg_high - swing_low_price) * 0.5
            return {
                'direction':  'BUY',
                'swing_low':  swing_low_price,
                'swing_high': leg_high,
                'dealing_50': dealing_50,
                'fvg_level':  min(fvg_lows),  # lowest FVG bottom — close below = bias invalid
                '_swing_ts':  bars[sl_idx].timestamp,
            }
        return None

    def _find_bearish_htf(self, bars, fn, n, lookback_start) -> dict | None:
        swing_high_idxs = [
            i for i in range(lookback_start, n - fn)
            if all(bars[i].high > bars[i - k].high for k in range(1, fn + 1))
            and all(bars[i].high > bars[i + k].high for k in range(1, fn + 1))
        ]
        for sh_idx in reversed(swing_high_idxs):
            swing_high_price = bars[sh_idx].high

            prev_sl_idxs = [
                i for i in range(fn, sh_idx)
                if all(bars[i].low < bars[i - k].low for k in range(1, fn + 1))
                and all(bars[i].low < bars[i + k].low for k in range(1, fn + 1))
            ]
            if not prev_sl_idxs:
                continue

            prev_sl_price = bars[max(prev_sl_idxs)].low
            leg = bars[sh_idx:]
            leg_low = min(b.low for b in leg)
            if leg_low >= prev_sl_price:
                continue

            # Bearish FVG in the leg
            fvg_highs = [leg[i].low for i in range(len(leg) - 2) if leg[i + 2].high < leg[i].low]
            if not fvg_highs:
                continue

            dealing_50 = swing_high_price - (swing_high_price - leg_low) * 0.5
            return {
                'direction':  'SELL',
                'swing_high': swing_high_price,
                'swing_low':  leg_low,
                'dealing_50': dealing_50,
                'fvg_level':  max(fvg_highs),  # highest FVG top — close above = bias invalid
                '_swing_ts':  bars[sh_idx].timestamp,
            }
        return None

    def _expire_bias(self, symbol: str, bar: BarEvent) -> Signal | None:
        had_pending = self._ltf_signal_fired[symbol] and self.entry_mode == 'pending'
        self._htf_bias[symbol] = None
        self._reset_ltf(symbol)
        if had_pending:
            return Signal(
                symbol=symbol, direction='CANCEL', order_type='PENDING',
                entry_price=0.0, stop_loss=0.0,
                strategy_name=self.NAME, timestamp=bar.timestamp,
            )
        return None

    def _reset_ltf(self, symbol: str):
        self._ltf_in_zone[symbol] = False
        self._ltf_signal_fired[symbol] = False
        self._ltf_last_sl_ts[symbol] = None
        self._ltf_bars[symbol].clear()

    # ── LTF ───────────────────────────────────────────────────────────────────

    def _on_ltf_bar(self, symbol: str, bar: BarEvent) -> Signal | None:
        self._update_ltf_atr(symbol, bar)

        bias = self._htf_bias[symbol]
        if bias is None:
            return None

        # Expiry check on LTF bars too (HTF bars are infrequent)
        if bias['direction'] == 'BUY' and bar.low < bias['swing_low']:
            return self._expire_bias(symbol, bar)
        if bias['direction'] == 'SELL' and bar.high > bias['swing_high']:
            return self._expire_bias(symbol, bar)
        rng = bias['swing_high'] - bias['swing_low']
        if bias['direction'] == 'BUY' and bar.close < bias['swing_low'] + 0.3 * rng:
            return self._expire_bias(symbol, bar)
        if bias['direction'] == 'SELL' and bar.close > bias['swing_low'] + 0.7 * rng:
            return self._expire_bias(symbol, bar)

        self._ltf_bars[symbol].append(bar)

        # Cooldown after a loss
        if self._cooldown[symbol] > 0:
            self._cooldown[symbol] -= 1
            return None

        # Blocked hours
        if bar.timestamp.hour in self.blocked_hours:
            return None

        # If TP is reached while a pending is live, cancel and expire
        if self._ltf_signal_fired[symbol]:
            if self.tp_mode == 'htf_high':
                if bias['direction'] == 'BUY' and bar.high >= bias['swing_high']:
                    return self._expire_bias(symbol, bar)
                if bias['direction'] == 'SELL' and bar.low <= bias['swing_low']:
                    return self._expire_bias(symbol, bar)
            else:  # rr mode: cancel when price reaches entry ± rr_ratio × SL_distance
                entry = self._last_signal_entry[symbol]
                sl = self._last_signal_sl[symbol]
                if entry != 0.0:
                    if bias['direction'] == 'BUY':
                        if bar.high >= entry + self.rr_ratio * (entry - sl):
                            return self._expire_bias(symbol, bar)
                    else:
                        if bar.low <= entry - self.rr_ratio * (sl - entry):
                            return self._expire_bias(symbol, bar)

        # Zone detection: price must retrace into the middle zone of the HTF range
        # BUY: price reaches 60% level (less retracement required vs strict 50%)
        # SELL: price reaches 40% level (60% from top — symmetric)
        if not self._ltf_in_zone[symbol]:
            rng = bias['swing_high'] - bias['swing_low']
            if bias['direction'] == 'BUY' and bar.low <= bias['swing_low'] + 0.6 * rng:
                self._ltf_in_zone[symbol] = True
            elif bias['direction'] == 'SELL' and bar.high >= bias['swing_low'] + 0.4 * rng:
                self._ltf_in_zone[symbol] = True

        if not self._ltf_in_zone[symbol]:
            return None

        # EMA trend filter: skip if HTF EMA disagrees with bias direction
        ema_trend = self._htf_ema_trend(symbol)
        if ema_trend is None:
            return None  # EMAs not ready yet
        if ema_trend != 'ANY' and ema_trend != bias['direction']:
            return None

        # LTF MSS detection
        ltf_bars = list(self._ltf_bars[symbol])
        if bias['direction'] == 'BUY':
            return self._detect_ltf_buy(symbol, bar, bias, ltf_bars)
        else:
            return self._detect_ltf_sell(symbol, bar, bias, ltf_bars)

    def _detect_ltf_buy(
        self, symbol: str, bar: BarEvent, bias: dict, bars: list
    ) -> Signal | None:
        n = len(bars)
        fn = self.ltf_fractal_n
        if n < 2 * fn + 2:
            return None

        current = bars[-1]

        # Confirmed LTF fractal swing highs
        swing_high_idxs = [
            i for i in range(fn, n - fn - 1)
            if all(bars[i].high > bars[i - k].high for k in range(1, fn + 1))
            and all(bars[i].high > bars[i + k].high for k in range(1, fn + 1))
        ]
        if not swing_high_idxs:
            return None

        # LTF MSS: current bar closes above a confirmed swing high
        broken = [i for i in swing_high_idxs if current.close > bars[i].high]
        if not broken:
            return None

        sh_idx = max(broken)

        # Most recent confirmed LTF swing low before the broken swing high
        swing_low_idxs = [
            i for i in range(fn, sh_idx)
            if all(bars[i].low < bars[i - k].low for k in range(1, fn + 1))
            and all(bars[i].low < bars[i + k].low for k in range(1, fn + 1))
        ]
        if not swing_low_idxs:
            return None

        sl_idx = max(swing_low_idxs)
        sl_ts = bars[sl_idx].timestamp

        # Skip if this is the same LTF swing low as the last signal — no update needed
        if sl_ts == self._ltf_last_sl_ts[symbol]:
            return None

        swing_sl = bars[sl_idx].low  # wick — used for zone/entry checks

        # The LTF swing low must be at or below the HTF 50% level — ensures the entry
        # leg genuinely started in the discount half, not above the midpoint
        if swing_sl > bias['dealing_50']:
            return None

        # Bullish FVG required in the LTF leg (swing low to broken swing high)
        leg = bars[sl_idx: sh_idx + 1]
        if len(leg) < 3 or not any(leg[i + 2].low > leg[i].high for i in range(len(leg) - 2)):
            return None

        ltf_sh_price = bars[sh_idx].high
        tp_price = bias['swing_high'] if self.tp_mode == 'htf_high' else None
        sl_price = self._compute_sl_buy(symbol, bars, sl_idx, leg)

        if self.entry_mode == 'market':
            entry_price = bar.close
            order_type = 'MARKET'
        else:
            entry_price = swing_sl + (ltf_sh_price - swing_sl) * 0.5
            order_type = 'PENDING'

        new_signal = Signal(
            symbol=symbol, direction='BUY', order_type=order_type,
            entry_price=entry_price, stop_loss=sl_price,
            take_profit=tp_price, strategy_name=self.NAME, timestamp=bar.timestamp,
        )

        logger.debug(
            f"IMS BUY signal | {symbol} | {bar.timestamp} | "
            f"HTF swing_low={bias['swing_low']:.5f} swing_high={bias['swing_high']:.5f} "
            f"50pct={bias['dealing_50']:.5f} | "
            f"LTF sl={sl_price:.5f} sh={ltf_sh_price:.5f} entry={entry_price:.5f} "
            f"tp={tp_price}"
        )

        if self._ltf_signal_fired[symbol]:
            return None  # already in this setup

        self._ltf_signal_fired[symbol] = True
        self._ltf_last_sl_ts[symbol] = sl_ts
        self._last_signal_entry[symbol] = entry_price
        self._last_signal_sl[symbol] = sl_price
        return new_signal

    def _detect_ltf_sell(
        self, symbol: str, bar: BarEvent, bias: dict, bars: list
    ) -> Signal | None:
        n = len(bars)
        fn = self.ltf_fractal_n
        if n < 2 * fn + 2:
            return None

        current = bars[-1]

        # Confirmed LTF fractal swing lows
        swing_low_idxs = [
            i for i in range(fn, n - fn - 1)
            if all(bars[i].low < bars[i - k].low for k in range(1, fn + 1))
            and all(bars[i].low < bars[i + k].low for k in range(1, fn + 1))
        ]
        if not swing_low_idxs:
            return None

        # LTF MSS bearish: current bar closes below a confirmed swing low
        broken = [i for i in swing_low_idxs if current.close < bars[i].low]
        if not broken:
            return None

        sl_struct_idx = max(broken)

        # Most recent confirmed LTF swing high before the broken swing low
        swing_high_idxs = [
            i for i in range(fn, sl_struct_idx)
            if all(bars[i].high > bars[i - k].high for k in range(1, fn + 1))
            and all(bars[i].high > bars[i + k].high for k in range(1, fn + 1))
        ]
        if not swing_high_idxs:
            return None

        sh_idx = max(swing_high_idxs)
        sh_ts = bars[sh_idx].timestamp

        if sh_ts == self._ltf_last_sl_ts[symbol]:
            return None

        swing_sh = bars[sh_idx].high  # wick — used for zone/entry checks

        # The LTF swing high must be at or above the HTF 50% level — ensures the entry
        # leg genuinely started in the premium half, not below the midpoint
        if swing_sh < bias['dealing_50']:
            return None

        # Bearish FVG required in the LTF leg (swing high to broken swing low)
        leg = bars[sh_idx: sl_struct_idx + 1]
        if len(leg) < 3 or not any(leg[i + 2].high < leg[i].low for i in range(len(leg) - 2)):
            return None

        ltf_sl_price = bars[sl_struct_idx].low
        tp_price = bias['swing_low'] if self.tp_mode == 'htf_high' else None
        sl_price = self._compute_sl_sell(symbol, bars, sh_idx, leg)

        if self.entry_mode == 'market':
            entry_price = bar.close
            order_type = 'MARKET'
        else:
            entry_price = swing_sh - (swing_sh - ltf_sl_price) * 0.5
            order_type = 'PENDING'

        new_signal = Signal(
            symbol=symbol, direction='SELL', order_type=order_type,
            entry_price=entry_price, stop_loss=sl_price,
            take_profit=tp_price, strategy_name=self.NAME, timestamp=bar.timestamp,
        )

        logger.debug(
            f"IMS SELL signal | {symbol} | {bar.timestamp} | "
            f"HTF swing_high={bias['swing_high']:.5f} swing_low={bias['swing_low']:.5f} "
            f"50pct={bias['dealing_50']:.5f} | "
            f"LTF sh={sl_price:.5f} sl={ltf_sl_price:.5f} entry={entry_price:.5f} "
            f"tp={tp_price}"
        )

        if self._ltf_signal_fired[symbol]:
            return None  # already in this setup

        self._ltf_signal_fired[symbol] = True
        self._ltf_last_sl_ts[symbol] = sh_ts
        self._last_signal_entry[symbol] = entry_price
        self._last_signal_sl[symbol] = sl_price
        return new_signal
