"""
IMS Reversal Strategy

Same HTF dealing range and bias logic as ImsStrategy, but trades in the OPPOSITE
direction to the HTF bias — fading the over-extension back to equilibrium.

Concept:
  - Bullish HTF bias: wait for price to trade in premium (above 50%), then look for a
    LTF bearish MSS + bearish FVG. Enter SELL toward the HTF 50% level.
  - Bearish HTF bias: wait for price to trade in discount (below 50%), then look for a
    LTF bullish MSS + bullish FVG. Enter BUY toward the HTF 50% level.

HTF bias detection is identical to ImsStrategy:
  - Fractal MSS on HTF with FVG confirmation
  - Same expiry: swing origin taken out; depth push beyond 30/70%; FVG disrespected
  - Same dynamic range extension

Zone gate (reversed from IMS continuation):
  - IMS: waits for price to RETRACE into the range (BUY: price drops to 60% level)
  - IMSReversal: waits for price to PUSH INTO premium/discount
    BUY bias → SELL entry: gate when bar.high >= HTF 50% (price entered premium)
    SELL bias → BUY entry: gate when bar.low  <= HTF 50% (price entered discount)

LTF entry:
  - BUY bias → SELL: LTF bearish MSS (close below swing low) + bearish FVG in leg
    LTF swing high must be >= HTF 50% (in premium)
    SELL PENDING at 50% of LTF bearish leg
    SL at wick high of LTF swing high bar
    TP at HTF 50% (htf_50 mode) or risk manager R:R (rr mode)

  - SELL bias → BUY: LTF bullish MSS (close above swing high) + bullish FVG in leg
    LTF swing low must be <= HTF 50% (in discount)
    BUY PENDING at 50% of LTF bullish leg
    SL at wick low of LTF swing low bar
    TP at HTF 50% (htf_50 mode) or risk manager R:R (rr mode)

Supported TF combos: H4/M15, D1/H4
"""

import logging
from collections import deque
from datetime import timedelta

from models import BarEvent, Signal

logger = logging.getLogger(__name__)


class ImsReversalStrategy:
    ORDER_TYPE = 'PENDING'

    def __init__(
        self,
        tf_htf: str = 'H4',
        tf_ltf: str = 'M15',
        fractal_n: int = 1,
        ltf_fractal_n: int = 1,
        htf_lookback: int = 30,
        entry_mode: str = 'pending',
        tp_mode: str = 'htf_pct',  # 'htf_pct' | 'rr'
        htf_tp_pct: float = 0.5,   # fraction into range for htf_pct TP
                                    # 0.5 = midpoint (50%); 0.6 = 60% into range from entry
                                    # SELL on bullish: TP = swing_low + (1-htf_tp_pct)*range
                                    # BUY on bearish:  TP = swing_low + htf_tp_pct*range
        rr_ratio: float = 2.5,
        zone_pct: float = 0.5,     # fraction of range that gates LTF monitoring
                                    # 0.5 = price above 50% for SELL setup (default)
                                    # 0.6 = price must be above 60% — more extended into premium
        cooldown_bars: int = 0,
        blocked_hours: tuple = (),
        ema_fast: int = 20,
        ema_slow: int = 50,
        ema_sep: float = 0.001,
        sl_anchor: str = 'swing',
        sl_buffer_pips: float = 0.0,
        sl_atr_mult: float = 0.0,
        pip_sizes: dict | None = None,
        max_losses_per_bias: int = 1,
        adx_period: int = 14,
        adx_threshold: float = 0.0,  # 0 = disabled; >0 blocks signals when D1 ADX > threshold
        adx_tf: str = 'D1',
        er_period: int = 14,
        er_threshold: float = 0.0,   # 0 = disabled; >0 blocks signals when D1 ER > threshold
        er_tf: str = 'D1',           # ER near 1 = trending, near 0 = ranging
        streak_pause_after: int = 0,  # 0 = disabled; pause after this many consecutive losses
        streak_pause_days: int = 7,   # how many calendar days to pause after streak fires
    ):
        self.tf_htf = tf_htf
        self.tf_ltf = tf_ltf
        self.fractal_n = fractal_n
        self.ltf_fractal_n = ltf_fractal_n
        self.htf_lookback = htf_lookback
        self.entry_mode = entry_mode
        self.tp_mode = tp_mode
        self.htf_tp_pct = htf_tp_pct
        self.rr_ratio = rr_ratio
        self.zone_pct = zone_pct
        self.cooldown_bars = cooldown_bars
        self.blocked_hours = set(blocked_hours)
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.ema_sep = ema_sep
        self.sl_anchor = sl_anchor
        self.sl_buffer_pips = sl_buffer_pips
        self.sl_atr_mult = sl_atr_mult
        self.max_losses_per_bias = max_losses_per_bias
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold
        self.adx_tf = adx_tf
        self.er_period = er_period
        self.er_threshold = er_threshold
        self.er_tf = er_tf
        self.streak_pause_after = streak_pause_after
        self.streak_pause_days = streak_pause_days
        self._pip_sizes = pip_sizes or {}

        tfs = [tf_htf, tf_ltf]
        if adx_period > 0 and adx_threshold > 0 and adx_tf not in tfs:
            tfs.append(adx_tf)
        if er_period > 0 and er_threshold > 0 and er_tf not in tfs:
            tfs.append(er_tf)
        self.TIMEFRAMES = tfs
        self.NAME = f'IMSRev_{tf_htf}_{tf_ltf}'
        self.ORDER_TYPE = 'MARKET' if entry_mode == 'market' else 'PENDING'

        # Per-symbol state
        self._htf_bars: dict[str, deque] = {}
        self._ltf_bars: dict[str, deque] = {}
        self._htf_bias: dict[str, dict | None] = {}
        self._ltf_in_zone: dict[str, bool] = {}
        self._ltf_signal_fired: dict[str, bool] = {}
        self._ltf_last_sl_ts: dict = {}
        self._last_signal_entry: dict[str, float] = {}
        self._last_signal_sl: dict[str, float] = {}
        self._cooldown: dict[str, int] = {}
        self._bias_loss_count: dict[str, int] = {}
        # HTF EMA state
        self._htf_ema_fast: dict[str, float | None] = {}
        self._htf_ema_slow: dict[str, float | None] = {}
        self._htf_ema_fast_sum: dict[str, float] = {}
        self._htf_ema_slow_sum: dict[str, float] = {}
        self._htf_bar_count: dict[str, int] = {}
        # LTF ATR state
        self._ltf_prev_close: dict[str, float | None] = {}
        self._ltf_atr: dict[str, float | None] = {}
        self._ltf_atr_buf: dict[str, list] = {}
        # D1 ADX regime filter state
        self._adx_bars: dict[str, deque] = {}
        self._adx_val: dict[str, float | None] = {}
        # D1 Efficiency Ratio regime filter state
        self._er_bars: dict[str, deque] = {}
        self._er_val: dict[str, float | None] = {}
        # Global circuit breaker: pause after N consecutive losses (cross-symbol streak)
        self._global_loss_streak: int = 0
        self._paused_until = None   # datetime | None

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
        self._bias_loss_count.clear()
        self._htf_ema_fast.clear()
        self._htf_ema_slow.clear()
        self._htf_ema_fast_sum.clear()
        self._htf_ema_slow_sum.clear()
        self._htf_bar_count.clear()
        self._ltf_prev_close.clear()
        self._ltf_atr.clear()
        self._ltf_atr_buf.clear()
        self._adx_bars.clear()
        self._adx_val.clear()
        self._er_bars.clear()
        self._er_val.clear()
        self._global_loss_streak = 0
        self._paused_until = None

    def notify_loss(self, symbol: str):
        """After a loss: increment bias loss counter. If limit reached, expire the bias.
        Otherwise reset LTF state so a fresh setup can form on the same bias."""
        # Global circuit breaker: count consecutive losses across all symbols
        if self.streak_pause_after > 0:
            self._global_loss_streak += 1

        self._bias_loss_count[symbol] = self._bias_loss_count.get(symbol, 0) + 1
        if self._bias_loss_count[symbol] >= self.max_losses_per_bias:
            # Bias has used up its allowed losses — retire it
            self._htf_bias[symbol] = None
            self._reset_ltf(symbol)  # also resets _bias_loss_count
            return
        # Still within the allowance — reset LTF state only, keep the bias alive
        self._ltf_in_zone[symbol] = False
        self._ltf_signal_fired[symbol] = False
        self._ltf_last_sl_ts[symbol] = None
        self._last_signal_entry[symbol] = 0.0
        self._last_signal_sl[symbol] = 0.0
        self._ltf_bars[symbol].clear()
        if self.cooldown_bars > 0:
            self._cooldown[symbol] = self.cooldown_bars

    def notify_win(self, symbol: str):
        """After a win: reset the global consecutive-loss streak."""
        self._global_loss_streak = 0

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
            self._bias_loss_count[symbol] = 0
            self._htf_ema_fast[symbol] = None
            self._htf_ema_slow[symbol] = None
            self._htf_ema_fast_sum[symbol] = 0.0
            self._htf_ema_slow_sum[symbol] = 0.0
            self._htf_bar_count[symbol] = 0
            self._ltf_prev_close[symbol] = None
            self._ltf_atr[symbol] = None
            self._ltf_atr_buf[symbol] = []
            self._adx_bars[symbol] = deque(maxlen=self.adx_period * 4 + 5)
            self._adx_val[symbol] = None
            self._er_bars[symbol] = deque(maxlen=self.er_period + 5)
            self._er_val[symbol] = None

        if event.timeframe == self.tf_htf:
            if self.adx_threshold > 0 and event.timeframe == self.adx_tf:
                self._on_adx_bar(symbol, event)
            if self.er_threshold > 0 and event.timeframe == self.er_tf:
                self._on_er_bar(symbol, event)
            return self._on_htf_bar(symbol, event)
        elif event.timeframe == self.tf_ltf:
            return self._on_ltf_bar(symbol, event)
        else:
            if self.adx_threshold > 0 and event.timeframe == self.adx_tf:
                self._on_adx_bar(symbol, event)
            if self.er_threshold > 0 and event.timeframe == self.er_tf:
                self._on_er_bar(symbol, event)
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
        if self.ema_fast == 0 or self.ema_slow == 0:
            return 'ANY'
        fast = self._htf_ema_fast[symbol]
        slow = self._htf_ema_slow[symbol]
        if fast is None or slow is None:
            return None
        if self.ema_sep > 0 and abs(fast - slow) / slow < self.ema_sep:
            return None
        if fast > slow:
            return 'BUY'
        if fast < slow:
            return 'SELL'
        return None

    # ── D1 ADX regime filter ──────────────────────────────────────────────────

    def _on_adx_bar(self, symbol: str, bar: BarEvent):
        self._adx_bars[symbol].append(bar)
        self._adx_val[symbol] = self._compute_adx(list(self._adx_bars[symbol]), self.adx_period)

    def _compute_adx(self, bars: list, period: int) -> float | None:
        """Wilder's ADX. Needs at least period*2 + 1 bars (period for ATR init,
        period for DX-to-ADX init, +1 because each TR needs a previous bar)."""
        if len(bars) < period * 2 + 1:
            return None

        trs, pdms, mdms = [], [], []
        for i in range(1, len(bars)):
            prev, cur = bars[i - 1], bars[i]
            tr  = max(cur.high - cur.low,
                      abs(cur.high - prev.close),
                      abs(cur.low  - prev.close))
            up   = cur.high - prev.high
            down = prev.low  - cur.low
            trs.append(tr)
            pdms.append(up   if up   > down and up   > 0 else 0.0)
            mdms.append(down if down > up   and down > 0 else 0.0)

        # Wilder initialisation: simple sum of first `period` values
        atr   = sum(trs[:period])
        pdm_s = sum(pdms[:period])
        mdm_s = sum(mdms[:period])

        dx_values: list[float] = []
        for i in range(period, len(trs)):
            atr   = atr   - atr   / period + trs[i]
            pdm_s = pdm_s - pdm_s / period + pdms[i]
            mdm_s = mdm_s - mdm_s / period + mdms[i]
            pdi = 100.0 * pdm_s / atr if atr > 0 else 0.0
            mdi = 100.0 * mdm_s / atr if atr > 0 else 0.0
            denom = pdi + mdi
            dx_values.append(100.0 * abs(pdi - mdi) / denom if denom > 0 else 0.0)

        if len(dx_values) < period:
            return None

        # Wilder ADX: initialise with average of first `period` DX values, then smooth
        adx = sum(dx_values[:period]) / period
        for dx in dx_values[period:]:
            adx = (adx * (period - 1) + dx) / period
        return adx

    # ── D1 Efficiency Ratio regime filter ────────────────────────────────────

    def _on_er_bar(self, symbol: str, bar: BarEvent):
        self._er_bars[symbol].append(bar)
        self._er_val[symbol] = self._compute_er(list(self._er_bars[symbol]), self.er_period)

    @staticmethod
    def _compute_er(bars: list, period: int) -> float | None:
        """Efficiency Ratio = |net_change| / sum(|bar_changes|) over `period` bars.
        Near 1.0 = price moved efficiently in one direction (trending).
        Near 0.0 = price oscillated without progress (ranging)."""
        if len(bars) < period + 1:
            return None
        recent = bars[-(period + 1):]
        net  = abs(recent[-1].close - recent[0].close)
        path = sum(abs(recent[i].close - recent[i - 1].close) for i in range(1, len(recent)))
        return net / path if path > 0 else 0.0

    # ── SL helpers ───────────────────────────────────────────────────────────

    _ATR_PERIOD = 14

    def _pip_size(self, symbol: str) -> float:
        return self._pip_sizes.get(symbol, 0.0001)

    def _update_ltf_atr(self, symbol: str, bar: BarEvent):
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
        if self.sl_anchor == 'body':
            anchor = min(bars[sl_idx].open, bars[sl_idx].close)
        elif self.sl_anchor == 'fvg':
            fvg_bottoms = [leg[i].high for i in range(len(leg) - 2)
                           if leg[i + 2].low > leg[i].high]
            anchor = min(fvg_bottoms)
        else:  # 'swing'
            anchor = bars[sl_idx].low
        return anchor - self._sl_buffer(symbol)

    def _compute_sl_sell(self, symbol: str, bars: list, sh_idx: int, leg: list) -> float:
        if self.sl_anchor == 'body':
            anchor = max(bars[sh_idx].open, bars[sh_idx].close)
        elif self.sl_anchor == 'fvg':
            fvg_tops = [leg[i].low for i in range(len(leg) - 2)
                        if leg[i + 2].high < leg[i].low]
            anchor = max(fvg_tops)
        else:  # 'swing'
            anchor = bars[sh_idx].high
        return anchor + self._sl_buffer(symbol)

    def _sl_buffer(self, symbol: str) -> float:
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

        # Expiry checks (identical to IMS — based on HTF bias structural validity)
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

            # Dynamic range update
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
        n = len(bars)
        lookback_start = max(fn, n - self.htf_lookback)
        bullish = self._find_bullish_htf(bars, fn, n, lookback_start)
        bearish = self._find_bearish_htf(bars, fn, n, lookback_start)
        if bullish and bearish:
            return bullish if bullish['_swing_ts'] >= bearish['_swing_ts'] else bearish
        return bullish or bearish

    def _find_bullish_htf(self, bars, fn, n, lookback_start) -> dict | None:
        swing_low_idxs = [
            i for i in range(lookback_start, n - fn)
            if all(bars[i].low < bars[i - k].low for k in range(1, fn + 1))
            and all(bars[i].low < bars[i + k].low for k in range(1, fn + 1))
        ]
        for sl_idx in reversed(swing_low_idxs):
            swing_low_price = bars[sl_idx].low

            prev_sh_idxs = [
                i for i in range(fn, sl_idx)
                if all(bars[i].high > bars[i - k].high for k in range(1, fn + 1))
                and all(bars[i].high > bars[i + k].high for k in range(1, fn + 1))
            ]
            if not prev_sh_idxs:
                continue

            prev_sh_price = bars[max(prev_sh_idxs)].high
            leg = bars[sl_idx:]
            leg_high = max(b.high for b in leg)
            if leg_high <= prev_sh_price:
                continue

            fvg_lows = [leg[i].high for i in range(len(leg) - 2) if leg[i + 2].low > leg[i].high]
            if not fvg_lows:
                continue

            dealing_50 = swing_low_price + (leg_high - swing_low_price) * 0.5
            return {
                'direction':  'BUY',
                'swing_low':  swing_low_price,
                'swing_high': leg_high,
                'dealing_50': dealing_50,
                'fvg_level':  min(fvg_lows),
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

            fvg_highs = [leg[i].low for i in range(len(leg) - 2) if leg[i + 2].high < leg[i].low]
            if not fvg_highs:
                continue

            dealing_50 = swing_high_price - (swing_high_price - leg_low) * 0.5
            return {
                'direction':  'SELL',
                'swing_high': swing_high_price,
                'swing_low':  leg_low,
                'dealing_50': dealing_50,
                'fvg_level':  max(fvg_highs),
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
        self._bias_loss_count[symbol] = 0

    # ── LTF ───────────────────────────────────────────────────────────────────

    def _get_htf_tp_price(self, bias: dict) -> float:
        """TP level inside the HTF range, measured by htf_tp_pct from the bias origin.

        htf_tp_pct=0.5 → midpoint (equilibrium) for both directions.
        htf_tp_pct=0.6 → 60% into the range from the bias origin:
          BUY bias → SELL trade: TP = swing_low + (1 - 0.6) * range = 40% from bottom
          SELL bias → BUY trade: TP = swing_low + 0.6 * range = 60% from bottom
        """
        rng = bias['swing_high'] - bias['swing_low']
        if bias['direction'] == 'BUY':
            return bias['swing_low'] + (1.0 - self.htf_tp_pct) * rng
        else:
            return bias['swing_low'] + self.htf_tp_pct * rng

    def _on_ltf_bar(self, symbol: str, bar: BarEvent) -> Signal | None:
        self._update_ltf_atr(symbol, bar)

        bias = self._htf_bias[symbol]
        if bias is None:
            return None

        # Expiry check on LTF bars (HTF bars are infrequent)
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
            if self.tp_mode == 'htf_pct':
                tp_level = self._get_htf_tp_price(bias)
                # BUY bias → SELL trade: price dropped to TP level
                if bias['direction'] == 'BUY' and bar.low <= tp_level:
                    return self._expire_bias(symbol, bar)
                # SELL bias → BUY trade: price rose to TP level
                if bias['direction'] == 'SELL' and bar.high >= tp_level:
                    return self._expire_bias(symbol, bar)
            else:  # rr mode
                entry = self._last_signal_entry[symbol]
                sl = self._last_signal_sl[symbol]
                if entry != 0.0:
                    if bias['direction'] == 'BUY':   # SELL trade
                        if bar.low <= entry - self.rr_ratio * (sl - entry):
                            return self._expire_bias(symbol, bar)
                    else:                             # BUY trade
                        if bar.high >= entry + self.rr_ratio * (entry - sl):
                            return self._expire_bias(symbol, bar)

        # Zone gate (reversed from IMS continuation):
        # BUY bias → SELL entry: wait for price to push into premium (above zone_pct level)
        # SELL bias → BUY entry: wait for price to push into discount (below 1-zone_pct level)
        if not self._ltf_in_zone[symbol]:
            rng = bias['swing_high'] - bias['swing_low']
            buy_gate  = bias['swing_low'] + self.zone_pct * rng
            sell_gate = bias['swing_low'] + (1.0 - self.zone_pct) * rng
            if bias['direction'] == 'BUY' and bar.high >= buy_gate:
                self._ltf_in_zone[symbol] = True
            elif bias['direction'] == 'SELL' and bar.low <= sell_gate:
                self._ltf_in_zone[symbol] = True

        if not self._ltf_in_zone[symbol]:
            return None

        # Circuit breaker: pause all new signals after N consecutive losses
        if self.streak_pause_after > 0:
            from datetime import timedelta
            if self._paused_until is None and self._global_loss_streak >= self.streak_pause_after:
                self._paused_until = bar.timestamp + timedelta(days=self.streak_pause_days)
                logger.debug(
                    f"Circuit breaker fired: {self._global_loss_streak} consecutive losses — "
                    f"pausing until {self._paused_until.date()}"
                )
            if self._paused_until is not None:
                if bar.timestamp < self._paused_until:
                    return None
                else:
                    # Pause expired — reset streak and resume
                    self._paused_until = None
                    self._global_loss_streak = 0

        # ADX regime filter: block new signals when market is trending too hard
        if self.adx_threshold > 0:
            adx = self._adx_val.get(symbol)
            if adx is not None and adx > self.adx_threshold:
                return None

        # Efficiency Ratio regime filter: block when price is moving too efficiently
        if self.er_threshold > 0:
            er = self._er_val.get(symbol)
            if er is not None and er > self.er_threshold:
                return None

        # EMA trend filter: EMA must confirm HTF bias direction
        ema_trend = self._htf_ema_trend(symbol)
        if ema_trend is None:
            return None
        if ema_trend != 'ANY' and ema_trend != bias['direction']:
            return None

        # LTF reversal detection (opposite to bias direction)
        ltf_bars = list(self._ltf_bars[symbol])
        if bias['direction'] == 'BUY':
            return self._detect_ltf_sell_reversal(symbol, bar, bias, ltf_bars)
        else:
            return self._detect_ltf_buy_reversal(symbol, bar, bias, ltf_bars)

    def _detect_ltf_sell_reversal(
        self, symbol: str, bar: BarEvent, bias: dict, bars: list
    ) -> Signal | None:
        """Bearish LTF MSS on bullish HTF bias → SELL pending into HTF equilibrium."""
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

        # LTF bearish MSS: current bar closes below a confirmed swing low
        broken = [i for i in swing_low_idxs if current.close < bars[i].low]
        if not broken:
            return None

        sl_struct_idx = max(broken)

        # Most recent confirmed LTF swing high before the broken swing low (origin of leg)
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

        swing_sh = bars[sh_idx].high

        # LTF swing high must be in premium (above HTF 50%) — origin of the reversal leg
        if swing_sh < bias['dealing_50']:
            return None

        # Bearish FVG required in the LTF leg
        leg = bars[sh_idx: sl_struct_idx + 1]
        if len(leg) < 3 or not any(leg[i + 2].high < leg[i].low for i in range(len(leg) - 2)):
            return None

        ltf_sl_price = bars[sl_struct_idx].low

        # Guard: swing high must be above swing low — choppy structure can produce degenerate legs
        if swing_sh <= ltf_sl_price:
            return None

        tp_price = self._get_htf_tp_price(bias) if self.tp_mode == 'htf_pct' else None
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
            f"IMSRev SELL | {symbol} | {bar.timestamp} | "
            f"HTF bias=BUY swing_low={bias['swing_low']:.5f} swing_high={bias['swing_high']:.5f} "
            f"50pct={bias['dealing_50']:.5f} | "
            f"LTF sh={sl_price:.5f} sl={ltf_sl_price:.5f} entry={entry_price:.5f} "
            f"tp={tp_price}"
        )

        if self._ltf_signal_fired[symbol]:
            return None

        self._ltf_signal_fired[symbol] = True
        self._ltf_last_sl_ts[symbol] = sh_ts
        self._last_signal_entry[symbol] = entry_price
        self._last_signal_sl[symbol] = sl_price
        return new_signal

    def _detect_ltf_buy_reversal(
        self, symbol: str, bar: BarEvent, bias: dict, bars: list
    ) -> Signal | None:
        """Bullish LTF MSS on bearish HTF bias → BUY pending into HTF equilibrium."""
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

        # LTF bullish MSS: current bar closes above a confirmed swing high
        broken = [i for i in swing_high_idxs if current.close > bars[i].high]
        if not broken:
            return None

        sh_idx = max(broken)

        # Most recent confirmed LTF swing low before the broken swing high (origin of leg)
        swing_low_idxs = [
            i for i in range(fn, sh_idx)
            if all(bars[i].low < bars[i - k].low for k in range(1, fn + 1))
            and all(bars[i].low < bars[i + k].low for k in range(1, fn + 1))
        ]
        if not swing_low_idxs:
            return None

        sl_idx = max(swing_low_idxs)
        sl_ts = bars[sl_idx].timestamp

        if sl_ts == self._ltf_last_sl_ts[symbol]:
            return None

        swing_sl = bars[sl_idx].low

        # LTF swing low must be in discount (below HTF 50%) — origin of the reversal leg
        if swing_sl > bias['dealing_50']:
            return None

        # Bullish FVG required in the LTF leg
        leg = bars[sl_idx: sh_idx + 1]
        if len(leg) < 3 or not any(leg[i + 2].low > leg[i].high for i in range(len(leg) - 2)):
            return None

        ltf_sh_price = bars[sh_idx].high

        # Guard: swing high must be above swing low — choppy structure can produce degenerate legs
        if ltf_sh_price <= swing_sl:
            return None

        tp_price = self._get_htf_tp_price(bias) if self.tp_mode == 'htf_pct' else None
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
            f"IMSRev BUY | {symbol} | {bar.timestamp} | "
            f"HTF bias=SELL swing_high={bias['swing_high']:.5f} swing_low={bias['swing_low']:.5f} "
            f"50pct={bias['dealing_50']:.5f} | "
            f"LTF sl={sl_price:.5f} sh={ltf_sh_price:.5f} entry={entry_price:.5f} "
            f"tp={tp_price}"
        )

        if self._ltf_signal_fired[symbol]:
            return None

        self._ltf_signal_fired[symbol] = True
        self._ltf_last_sl_ts[symbol] = sl_ts
        self._last_signal_entry[symbol] = entry_price
        self._last_signal_sl[symbol] = sl_price
        return new_signal
