"""
Engulfing Bar Play (EBP)

Bias timeframe (default D1):
  - Bullish: current low < prev low AND current close > prev open
  - Bearish: current high > prev high AND current close < prev open

Entry timeframe (default H4):
  - Wait for price to retrace 25-75% into the engulfing bar's range (high-to-low)
  - Look for a Market Structure Shift (MSS): a bar closes above a confirmed swing
    high (fractal with fractal_n bars each side)
  - MSS is only valid if the bullish leg from the prior swing low to the MSS bar
    contains at least one Fair Value Gap (FVG: bar[i+2].low > bar[i].high)
  - MARKET entry on MSS confirmation
  - SL: most recent confirmed swing low on entry TF
  - TP: engulfing bar high (fixed price target, overrides risk manager)

FVG pending variation (use_fvg_entry=True):
  - Instead of MARKET, place PENDING BUY LIMIT at bar[i+2].low of the FVG nearest
    to current price (top of the gap — catches any intention to fill without needing
    a full fill). Same swing-low SL. Emits CANCEL if bias expires.

Bias expires when:
  - A new engulfing bar forms (bias replaced)
  - Price closes below the 75% retracement level on entry TF (too deep)
  - Price reaches the engulfing bar high/low on either TF (TP level, no longer needed)
  - A trade closes at SL (notify_loss)

SL modes (sl_mode param):
  - 'structural': confirmed swing low before MSS swing high (default, deepest)
  - 'mss_bar':    low of the MSS candle itself (tighter structural reference)
  - 'symmetric':  entry - (TP - entry), pure 1:1 R:R with no structural reference

Variations:
  - D1/H4 (default) or H4/M15 via tf_bias/tf_entry args
"""

from collections import deque

from models import BarEvent, Signal


class EbpStrategy:

    ORDER_TYPE = 'MARKET'  # overridden to PENDING when use_fvg_entry=True

    def __init__(
        self,
        tf_bias: str = 'D1',
        tf_entry: str = 'H4',
        fractal_n: int = 1,
        min_retrace_pct: float = 0.25,
        max_retrace_pct: float = 0.75,
        use_fvg_entry: bool = False,
        require_fvg: bool = True,
        sl_mode: str = 'structural',  # 'structural' | 'mss_bar' | 'symmetric'
        blocked_hours: tuple = (),     # entry-TF bars during these UTC hours are skipped
    ):
        self.tf_bias = tf_bias
        self.tf_entry = tf_entry
        self.fractal_n = fractal_n
        self.min_retrace_pct = min_retrace_pct
        self.max_retrace_pct = max_retrace_pct
        self.use_fvg_entry = use_fvg_entry
        self.require_fvg = require_fvg
        self.sl_mode = sl_mode
        self._blocked = frozenset(blocked_hours)

        self.TIMEFRAMES = [tf_bias, tf_entry]
        self.NAME = f'EBP_{tf_bias}_{tf_entry}'
        self.ORDER_TYPE = 'PENDING' if use_fvg_entry else 'MARKET'

        # Per-symbol state
        self._prev_bias_bar: dict[str, BarEvent | None] = {}
        self._entry_bars: dict[str, deque] = {}
        self._bias: dict[str, dict | None] = {}   # None = no active bias
        self._signal_fired: dict[str, bool] = {}  # True once signal emitted for current bias

    def reset(self):
        self._prev_bias_bar.clear()
        self._entry_bars.clear()
        self._bias.clear()
        self._signal_fired.clear()

    def notify_loss(self, symbol: str):
        """Reset bias after a loss — one trade attempt per bias."""
        self._bias[symbol] = None
        self._signal_fired[symbol] = False

    def generate_signal(self, event: BarEvent) -> Signal | None:
        symbol = event.symbol

        if symbol not in self._bias:
            self._prev_bias_bar[symbol] = None
            self._entry_bars[symbol] = deque(maxlen=200)
            self._bias[symbol] = None
            self._signal_fired[symbol] = False

        if event.timeframe == self.tf_bias:
            return self._on_bias_bar(symbol, event)
        elif event.timeframe == self.tf_entry:
            return self._on_entry_bar(symbol, event)
        return None

    # ── Bias timeframe ────────────────────────────────────────────────────────

    def _on_bias_bar(self, symbol: str, bar: BarEvent) -> Signal | None:
        prev = self._prev_bias_bar[symbol]

        if prev is not None:
            bullish_engulf = bar.low < prev.low and bar.close > prev.open
            bearish_engulf = bar.high > prev.high and bar.close < prev.open

            if bullish_engulf:
                self._set_bias(symbol, 'BUY', bar)
            elif bearish_engulf:
                self._set_bias(symbol, 'SELL', bar)
            else:
                # Check if TP level reached on bias TF (bias expires, no need for entry)
                cancel = self._check_tp_expiry(symbol, bar)
                if cancel:
                    return cancel

        self._prev_bias_bar[symbol] = bar
        return None

    def _set_bias(self, symbol: str, direction: str, bar: BarEvent):
        rng = bar.high - bar.low
        if direction == 'BUY':
            zone_entry = bar.high - self.min_retrace_pct * rng  # 25% down from high
            zone_exit  = bar.high - self.max_retrace_pct * rng  # 75% down from high
        else:
            zone_entry = bar.low + self.min_retrace_pct * rng   # 25% up from low
            zone_exit  = bar.low + self.max_retrace_pct * rng   # 75% up from low

        self._bias[symbol] = {
            'direction':   direction,
            'engulf_high': bar.high,
            'engulf_low':  bar.low,
            'range':       rng,
            'zone_entry':  zone_entry,  # price must trade through this to be "in zone"
            'zone_exit':   zone_exit,   # price closing beyond this invalidates bias
            'tp':          bar.high if direction == 'BUY' else bar.low,
            'in_zone':     False,
        }
        self._signal_fired[symbol] = False
        self._entry_bars[symbol].clear()

    def _check_tp_expiry(self, symbol: str, bar: BarEvent) -> Signal | None:
        """Expire bias if price reaches the TP level (no longer a fresh setup)."""
        bias = self._bias[symbol]
        if bias is None or self._signal_fired[symbol]:
            return None
        if bias['direction'] == 'BUY' and bar.high >= bias['tp']:
            return self._expire_bias(symbol, bar)
        if bias['direction'] == 'SELL' and bar.low <= bias['tp']:
            return self._expire_bias(symbol, bar)
        return None

    def _expire_bias(self, symbol: str, bar: BarEvent) -> Signal | None:
        """Clear bias and emit CANCEL if we have a live pending order."""
        had_pending = self.use_fvg_entry and self._signal_fired[symbol]
        self._bias[symbol] = None
        self._signal_fired[symbol] = False
        if had_pending:
            return Signal(
                symbol=symbol,
                direction='CANCEL',
                order_type='PENDING',
                entry_price=0.0,
                stop_loss=0.0,
                strategy_name=self.NAME,
                timestamp=bar.timestamp,
            )
        return None

    # ── Entry timeframe ───────────────────────────────────────────────────────

    def _on_entry_bar(self, symbol: str, bar: BarEvent) -> Signal | None:
        bias = self._bias[symbol]
        if bias is None:
            return None

        if self._blocked and bar.timestamp.hour in self._blocked:
            return None

        self._entry_bars[symbol].append(bar)

        # Once signal is fired, only check for pending expiry
        if self._signal_fired[symbol]:
            return self._check_tp_expiry(symbol, bar)

        if bias['direction'] == 'BUY':
            return self._check_buy(symbol, bar, bias)
        else:
            return self._check_sell(symbol, bar, bias)

    def _check_buy(self, symbol: str, bar: BarEvent, bias: dict) -> Signal | None:
        zone_entry = bias['zone_entry']  # 25% level — must trade below this
        zone_exit  = bias['zone_exit']   # 75% level — close below this invalidates
        engulf_high = bias['engulf_high']

        # Bias invalidation: price closes below 75% level
        if bar.close < zone_exit:
            return self._expire_bias(symbol, bar)

        # Bias invalidation: price reaches engulf high
        if bar.high >= engulf_high:
            return self._expire_bias(symbol, bar)

        # Mark as in-zone once price trades below the 25% level
        if bar.low <= zone_entry:
            bias['in_zone'] = True

        if not bias['in_zone']:
            return None

        bars = list(self._entry_bars[symbol])
        return self._detect_bullish_mss(symbol, bar, bias, bars)

    def _check_sell(self, symbol: str, bar: BarEvent, bias: dict) -> Signal | None:
        zone_entry  = bias['zone_entry']  # 25% level — must trade above this
        zone_exit   = bias['zone_exit']   # 75% level — close above this invalidates
        engulf_low  = bias['engulf_low']

        # Bias invalidation: price closes above 75% level
        if bar.close > zone_exit:
            return self._expire_bias(symbol, bar)

        # Bias invalidation: price reaches engulf low
        if bar.low <= engulf_low:
            return self._expire_bias(symbol, bar)

        # Mark as in-zone once price trades above the 25% level
        if bar.high >= zone_entry:
            bias['in_zone'] = True

        if not bias['in_zone']:
            return None

        bars = list(self._entry_bars[symbol])
        return self._detect_bearish_mss(symbol, bar, bias, bars)

    # ── SL calculation ────────────────────────────────────────────────────────

    def _calc_sl_buy(
        self,
        structural_sl: float,
        entry_price: float,
        tp_price: float,
        mss_bar_low: float,
    ) -> float:
        if self.sl_mode == 'mss_bar':
            return mss_bar_low
        if self.sl_mode == 'symmetric':
            return entry_price - (tp_price - entry_price)
        return structural_sl  # 'structural' (default)

    def _calc_sl_sell(
        self,
        structural_sl: float,
        entry_price: float,
        tp_price: float,
        mss_bar_high: float,
    ) -> float:
        if self.sl_mode == 'mss_bar':
            return mss_bar_high
        if self.sl_mode == 'symmetric':
            return entry_price + (entry_price - tp_price)
        return structural_sl  # 'structural' (default)

    # ── MSS detection ─────────────────────────────────────────────────────────

    def _detect_bullish_mss(
        self, symbol: str, bar: BarEvent, bias: dict, bars: list
    ) -> Signal | None:
        n = len(bars)
        fn = self.fractal_n
        if n < 2 * fn + 2:
            return None

        current = bars[-1]

        # Confirmed swing highs: index i has fn bars on each side, all with lower highs
        # Confirmed at index i means bar[i+fn] has already arrived
        swing_high_idxs = [
            i for i in range(fn, n - fn - 1)
            if all(bars[i].high > bars[i - k].high for k in range(1, fn + 1))
            and all(bars[i].high > bars[i + k].high for k in range(1, fn + 1))
        ]
        if not swing_high_idxs:
            return None

        # MSS: current bar closes above a confirmed swing high
        broken = [i for i in swing_high_idxs if current.close > bars[i].high]
        if not broken:
            return None

        sh_idx = max(broken)  # most recently broken swing high

        # Find the most recent confirmed swing low before the broken swing high
        # This defines the start of the bullish leg
        swing_low_idxs = [
            i for i in range(fn, sh_idx)
            if all(bars[i].low < bars[i - k].low for k in range(1, fn + 1))
            and all(bars[i].low < bars[i + k].low for k in range(1, fn + 1))
        ]
        leg_start = max(swing_low_idxs) if swing_low_idxs else 0

        # Structural SL: most recent confirmed swing low before the broken swing high
        if swing_low_idxs:
            structural_sl = bars[max(swing_low_idxs)].low
        else:
            structural_sl = min(b.low for b in bars[leg_start:sh_idx + 1])

        # FVGs in the bullish leg: bar[i+2].low > bar[i].high
        fvgs = [
            {'top': bars[i + 2].low, 'bottom': bars[i].high, 'idx': i}
            for i in range(leg_start, n - 2)
            if bars[i + 2].low > bars[i].high
        ]
        if self.require_fvg and not fvgs:
            return None

        # MSS confirmed (+ FVG if required) — emit signal
        self._signal_fired[symbol] = True
        tp_price = bias['engulf_high']

        if self.use_fvg_entry and fvgs:
            # BUY LIMIT at bar[i+2].low (top of the FVG) — pick the FVG that
            # maximises R:R: (tp - fvg_top) / (fvg_top - sl).
            def fvg_rr(f):
                dist_to_tp = tp_price - f['top']
                dist_to_sl = f['top'] - structural_sl
                return dist_to_tp / dist_to_sl if dist_to_sl > 0 else 0.0
            best_fvg = max(fvgs, key=fvg_rr)
            if fvg_rr(best_fvg) <= 0:
                self._signal_fired[symbol] = False
                return None
            entry_price = best_fvg['top']
            sl_price = self._calc_sl_buy(structural_sl, entry_price, tp_price, current.low)
            return Signal(
                symbol=symbol,
                direction='BUY',
                order_type='PENDING',
                entry_price=entry_price,
                stop_loss=sl_price,
                take_profit=tp_price,
                strategy_name=self.NAME,
                timestamp=bar.timestamp,
            )

        entry_price = current.close
        sl_price = self._calc_sl_buy(structural_sl, entry_price, tp_price, current.low)
        return Signal(
            symbol=symbol,
            direction='BUY',
            order_type='MARKET',
            entry_price=entry_price,
            stop_loss=sl_price,
            take_profit=tp_price,
            strategy_name=self.NAME,
            timestamp=bar.timestamp,
        )

    def _detect_bearish_mss(
        self, symbol: str, bar: BarEvent, bias: dict, bars: list
    ) -> Signal | None:
        n = len(bars)
        fn = self.fractal_n
        if n < 2 * fn + 2:
            return None

        current = bars[-1]

        # Confirmed swing lows
        swing_low_idxs = [
            i for i in range(fn, n - fn - 1)
            if all(bars[i].low < bars[i - k].low for k in range(1, fn + 1))
            and all(bars[i].low < bars[i + k].low for k in range(1, fn + 1))
        ]
        if not swing_low_idxs:
            return None

        # MSS: current bar closes below a confirmed swing low
        broken = [i for i in swing_low_idxs if current.close < bars[i].low]
        if not broken:
            return None

        sl_struct_idx = max(broken)  # most recently broken swing low

        # Find the most recent confirmed swing high before the broken swing low
        swing_high_idxs = [
            i for i in range(fn, sl_struct_idx)
            if all(bars[i].high > bars[i - k].high for k in range(1, fn + 1))
            and all(bars[i].high > bars[i + k].high for k in range(1, fn + 1))
        ]
        leg_start = max(swing_high_idxs) if swing_high_idxs else 0

        # Structural SL: most recent confirmed swing high before the broken swing low
        if swing_high_idxs:
            structural_sl = bars[max(swing_high_idxs)].high
        else:
            structural_sl = max(b.high for b in bars[leg_start:sl_struct_idx + 1])

        # Bearish FVGs in the leg: bar[i+2].high < bar[i].low
        fvgs = [
            {'top': bars[i].low, 'bottom': bars[i + 2].high, 'idx': i}
            for i in range(leg_start, n - 2)
            if bars[i + 2].high < bars[i].low
        ]
        if self.require_fvg and not fvgs:
            return None

        # MSS confirmed (+ FVG if required)
        self._signal_fired[symbol] = True
        tp_price = bias['engulf_low']

        if self.use_fvg_entry and fvgs:
            # SELL LIMIT at bar[i+2].high (bottom of the FVG) — pick the FVG
            # that maximises R:R: (sl - fvg_bottom) / (fvg_bottom - tp).
            def fvg_rr(f):
                dist_to_tp = f['bottom'] - tp_price
                dist_to_sl = structural_sl - f['bottom']
                return dist_to_tp / dist_to_sl if dist_to_sl > 0 else 0.0
            best_fvg = max(fvgs, key=fvg_rr)
            if fvg_rr(best_fvg) <= 0:
                self._signal_fired[symbol] = False
                return None
            entry_price = best_fvg['bottom']
            sl_price = self._calc_sl_sell(structural_sl, entry_price, tp_price, current.high)
            return Signal(
                symbol=symbol,
                direction='SELL',
                order_type='PENDING',
                entry_price=entry_price,
                stop_loss=sl_price,
                take_profit=tp_price,
                strategy_name=self.NAME,
                timestamp=bar.timestamp,
            )

        entry_price = current.close
        sl_price = self._calc_sl_sell(structural_sl, entry_price, tp_price, current.high)
        return Signal(
            symbol=symbol,
            direction='SELL',
            order_type='MARKET',
            entry_price=entry_price,
            stop_loss=sl_price,
            take_profit=tp_price,
            strategy_name=self.NAME,
            timestamp=bar.timestamp,
        )
