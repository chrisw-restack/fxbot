from collections import deque
from dataclasses import dataclass

from models import BarEvent, Signal


@dataclass
class _Zone:
    zone_type: str   # 'DEMAND' or 'SUPPLY'
    top: float
    bottom: float
    created_len: int  # bar_count when zone was created — prevents retroactive fractals


class SmcZoneStrategy:
    """
    SMC Zone strategy: swing pivot zones with fractal BOS + wick rejection entry.

    ── Zone detection ────────────────────────────────────────────────────────
    Identifies swing pivot highs/lows using swing_length bars on each side
    (7-candle Williams fractal with swing_length=3).

      Demand zone: bottom = swing_low,  top = swing_low + ATR × zone_atr_mult
      Supply zone: top = swing_high, bottom = swing_high - ATR × zone_atr_mult

    ── Zone quality filter ───────────────────────────────────────────────────
    zone_leg_atr: the impulse displacement away from the pivot (measured over
    the swing_length bars on the far side) must be ≥ zone_leg_atr × ATR.
    Filters out weak pivots formed by slow grinds. Set to 0 to disable.

    ── Bias filter ───────────────────────────────────────────────────────────
    D1 EMA(d1_ema_period): demand zones only in uptrend, supply zones only in
    downtrend.

    ── Entry sequence ────────────────────────────────────────────────────────
    Step 1 — 3-candle fractal inside zone:
      Watch for a Williams fractal (1 bar each side) whose extreme is inside
      the zone boundary:
        Demand: fractal HIGH with high < zone.top
        Supply: fractal LOW  with low  > zone.bottom

    Step 2 — BOS close:
      A bar closes beyond the fractal level, confirming short-term structure
      was broken in the zone's favour:
        Demand: close > fractal_high  → BOS confirmed
        Supply: close < fractal_low   → BOS confirmed

    Step 3 — Wick rejection entry (MARKET):
      After BOS is confirmed AND at least min_bos_retest_bars bars have elapsed,
      watch for a bar that wicks INTO the zone but closes back OUTSIDE it AND is
      a directional close (close > open for demand, close < open for supply):
        Demand: bar.low <= zone.top  AND  bar.close > zone.top  AND  bar.close > bar.open
          → MARKET BUY at bar.close
        Supply: bar.high >= zone.bottom  AND  bar.close < zone.bottom  AND  bar.close < bar.open
          → MARKET SELL at bar.close

      The wick shows price tested the zone; the directional close confirms rejection.

    ── Stop-loss ─────────────────────────────────────────────────────────────
    Placed sl_buffer_atr × ATR beyond the far side of the zone:
      Demand: SL = zone.bottom - sl_buffer_atr × ATR  (below swing low)
      Supply: SL = zone.top    + sl_buffer_atr × ATR  (above swing high)

    SL is larger than a pending-stop entry because the market entry is at the
    close above zone.top rather than at zone.top itself, but price confirmation
    (the wick rejection) increases the probability the zone holds.

    ── BOS invalidation ──────────────────────────────────────────────────────
    If price closes through the far side of the zone before entry, clear state:
      Demand: close < zone.bottom  →  zone broken, reset
      Supply: close > zone.top     →  zone broken, reset
    (No CANCEL signal needed — MARKET orders have no pending to cancel.)
    """

    TIMEFRAMES: list  # set dynamically from tf_entry
    ORDER_TYPE = 'MARKET'
    NAME = 'SmcZone'

    def __init__(
        self,
        swing_length: int = 3,
        tf_entry: str = 'H4',
        atr_period: int = 50,
        zone_atr_mult: float = 2.0,     # zone width = ATR × this
        sl_buffer_atr: float = 0.5,     # SL placed this many ATRs outside zone
        zone_leg_atr: float = 0.0,      # min impulse move away from pivot (0 = disabled)
        d1_ema_period: int = 50,
        min_bos_retest_bars: int = 0,   # min bars between BOS and wick rejection entry
        blocked_hours: tuple = (),
        pip_sizes: dict | None = None,
    ):
        self.swing_length = swing_length
        self.tf_entry = tf_entry
        self.TIMEFRAMES = ['D1', tf_entry]
        self.atr_period = atr_period
        self.zone_atr_mult = zone_atr_mult
        self.sl_buffer_atr = sl_buffer_atr
        self.zone_leg_atr = zone_leg_atr
        self.d1_ema_period = d1_ema_period
        self.min_bos_retest_bars = min_bos_retest_bars
        self._blocked = frozenset(blocked_hours)
        self.pip_sizes = pip_sizes or {
            'EURUSD': 0.0001, 'GBPUSD': 0.0001, 'AUDUSD': 0.0001,
            'NZDUSD': 0.0001, 'USDJPY': 0.01,   'USDCAD': 0.0001,
            'USDCHF': 0.0001,
        }

        # Per-symbol state
        self._bars: dict[str, deque] = {}
        self._bar_count: dict[str, int] = {}
        self._d1_ema: dict[str, float | None] = {}
        self._d1_count: dict[str, int] = {}
        self._atr: dict[str, float | None] = {}
        self._atr_count: dict[str, int] = {}

        # Zone and entry sequence state
        self._zone: dict[str, _Zone | None] = {}
        self._fractal_price: dict[str, float | None] = {}  # fractal level found inside zone
        self._bos_confirmed: dict[str, bool] = {}          # BOS close fired; zone cleared on entry
        self._bos_bar: dict[str, int] = {}                 # bar_count when BOS was confirmed

    def reset(self):
        self._bars.clear()
        self._bar_count.clear()
        self._d1_ema.clear()
        self._d1_count.clear()
        self._atr.clear()
        self._atr_count.clear()
        self._zone.clear()
        self._fractal_price.clear()
        self._bos_confirmed.clear()
        self._bos_bar.clear()

    def generate_signal(self, event: BarEvent) -> Signal | None:
        s = event.symbol
        self._init(s)

        if event.timeframe == 'D1':
            self._update_d1_ema(s, event.close)
            return None

        # ── Entry-timeframe bar ───────────────────────────────────────────────

        # 1. Update ATR before appending (so prev_close is correct)
        self._bar_count[s] += 1
        self._update_atr(s, event)

        # 2. BOS invalidation — if zone is broken before entry, clear state
        if self._check_zone_broken(s, event):
            self._clear_zone(s)

        # 3. Append current bar
        self._bars[s].append(event)

        zone = self._zone[s]
        if zone is None:
            pass  # fall through to pivot detection

        else:
            # ── Entry sequence steps ─────────────────────────────────────────

            # 4. Fractal detection (passive, runs even in blocked hours)
            if not self._bos_confirmed[s] and self._fractal_price[s] is None:
                self._update_fractal(s, zone)

            # 5. BOS close — fractal found, waiting for close above/below it
            if not self._bos_confirmed[s] and self._fractal_price[s] is not None:
                self._check_bos_close(s, event)

            # 6. Wick rejection entry — BOS confirmed, watching for zone retest
            #    Only during allowed hours
            if (self._bos_confirmed[s]
                    and not (self._blocked and event.timestamp.hour in self._blocked)):
                sig = self._check_wick_rejection(s, event, zone)
                if sig:
                    return sig

        # 7. New zone pivot detection (requires warmup + trading hours)
        if (not (self._blocked and event.timestamp.hour in self._blocked)
                and self._atr_count[s] >= self.atr_period
                and self._d1_count[s] >= self.d1_ema_period):
            self._detect_pivot(s, event)

        return None

    # ── Zone invalidation ─────────────────────────────────────────────────────

    def _check_zone_broken(self, s: str, event: BarEvent) -> bool:
        """Return True if price closed through the zone's far side."""
        zone = self._zone[s]
        if zone is None:
            return False
        return (
            (zone.zone_type == 'DEMAND' and event.close < zone.bottom) or
            (zone.zone_type == 'SUPPLY' and event.close > zone.top)
        )

    # ── Step 4: Fractal detection ─────────────────────────────────────────────

    def _update_fractal(self, s: str, zone: _Zone):
        """
        Look for a 3-candle Williams fractal (1 bar each side) whose extreme
        is inside the zone.  Only considers bars added after zone was created.

        Demand: fractal HIGH with b1.high < zone.top
        Supply: fractal LOW  with b1.low  > zone.bottom
        """
        if self._bar_count[s] - zone.created_len < 3:
            return

        bars = list(self._bars[s])
        if len(bars) < 3:
            return

        b0, b1, b2 = bars[-3], bars[-2], bars[-1]

        if zone.zone_type == 'DEMAND':
            if b1.high > b0.high and b1.high > b2.high and b1.high < zone.top:
                self._fractal_price[s] = b1.high

        else:  # SUPPLY
            if b1.low < b0.low and b1.low < b2.low and b1.low > zone.bottom:
                self._fractal_price[s] = b1.low

    # ── Step 5: BOS close ─────────────────────────────────────────────────────

    def _check_bos_close(self, s: str, event: BarEvent):
        """
        Confirm BOS: a bar closes beyond the fractal level.
          Demand: close > fractal_high
          Supply: close < fractal_low
        """
        fp = self._fractal_price[s]
        zone = self._zone[s]

        if zone.zone_type == 'DEMAND' and event.close > fp:
            self._bos_confirmed[s] = True
            self._bos_bar[s] = self._bar_count[s]
        elif zone.zone_type == 'SUPPLY' and event.close < fp:
            self._bos_confirmed[s] = True
            self._bos_bar[s] = self._bar_count[s]

    # ── Step 6: Wick rejection entry ──────────────────────────────────────────

    def _check_wick_rejection(self, s: str, event: BarEvent, zone: _Zone) -> Signal | None:
        """
        After BOS is confirmed, watch for a bar that wicks into the zone but
        closes back outside it — confirming the zone is acting as support/resistance.

        Demand: bar.low <= zone.top  AND  bar.close > zone.top  → MARKET BUY
        Supply: bar.high >= zone.bottom  AND  bar.close < zone.bottom  → MARKET SELL

        Entry price: bar.close (market order fills at next bar open in simulation).
        SL: sl_buffer_atr × ATR beyond the far zone boundary.
        """
        atr = self._atr[s]
        sl_buffer = atr * self.sl_buffer_atr

        bars_since_bos = self._bar_count[s] - self._bos_bar[s]

        if zone.zone_type == 'DEMAND':
            if (event.low <= zone.top
                    and event.close > zone.top
                    and event.close > event.open           # filter #1: bullish bar
                    and bars_since_bos >= self.min_bos_retest_bars):  # filter #2: spacing
                sl = zone.bottom - sl_buffer
                self._clear_zone(s)
                return Signal(
                    symbol=s,
                    direction='BUY',
                    order_type='MARKET',
                    entry_price=event.close,
                    stop_loss=sl,
                    strategy_name=self.NAME,
                    timestamp=event.timestamp,
                )

        elif zone.zone_type == 'SUPPLY':
            if (event.high >= zone.bottom
                    and event.close < zone.bottom
                    and event.close < event.open           # filter #1: bearish bar
                    and bars_since_bos >= self.min_bos_retest_bars):  # filter #2: spacing
                sl = zone.top + sl_buffer
                self._clear_zone(s)
                return Signal(
                    symbol=s,
                    direction='SELL',
                    order_type='MARKET',
                    entry_price=event.close,
                    stop_loss=sl,
                    strategy_name=self.NAME,
                    timestamp=event.timestamp,
                )

        return None

    # ── Step 7: Zone creation from pivot ─────────────────────────────────────

    def _detect_pivot(self, s: str, event: BarEvent):
        """
        Check if the bar at position -(swing_length) in the deque is a pivot.
        Creates a new zone if one is not already in progress.
        Does not emit a signal — entry waits for fractal → BOS → wick sequence.
        """
        bars = list(self._bars[s])
        n = len(bars)
        pi = n - 1 - self.swing_length

        if pi < self.swing_length:
            return

        pivot = bars[pi]

        is_high = all(
            bars[pi - j].high < pivot.high and bars[pi + j].high < pivot.high
            for j in range(1, self.swing_length + 1)
        )
        is_low = all(
            bars[pi - j].low > pivot.low and bars[pi + j].low > pivot.low
            for j in range(1, self.swing_length + 1)
        )

        if not is_high and not is_low:
            return

        atr = self._atr[s]
        d1_ema = self._d1_ema[s]
        zone_width = atr * self.zone_atr_mult
        current_close = event.close

        # Zone leg filter: the impulse move away from the pivot must be strong enough.
        # Measured over the swing_length bars on the far side of the pivot (bars[pi+1..pi+N]).
        if self.zone_leg_atr > 0:
            min_leg = atr * self.zone_leg_atr
            after_bars = [bars[pi + j] for j in range(1, self.swing_length + 1)]
            if is_high:
                leg = pivot.high - min(b.low for b in after_bars)
            else:
                leg = max(b.high for b in after_bars) - pivot.low
            if leg < min_leg:
                return

        if is_high and current_close < d1_ema:
            new_zone = _Zone(
                zone_type='SUPPLY',
                top=pivot.high,
                bottom=pivot.high - zone_width,
                created_len=self._bar_count[s],
            )
            self._set_zone(s, new_zone)

        elif is_low and current_close > d1_ema:
            new_zone = _Zone(
                zone_type='DEMAND',
                top=pivot.low + zone_width,
                bottom=pivot.low,
                created_len=self._bar_count[s],
            )
            self._set_zone(s, new_zone)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_zone(self, s: str, zone: _Zone):
        """Replace the current zone."""
        self._zone[s] = zone
        self._fractal_price[s] = None
        self._bos_confirmed[s] = False
        self._bos_bar[s] = 0

    def _clear_zone(self, s: str):
        self._zone[s] = None
        self._fractal_price[s] = None
        self._bos_confirmed[s] = False
        self._bos_bar[s] = 0

    def _update_d1_ema(self, s: str, close: float):
        self._d1_count[s] += 1
        if self._d1_ema[s] is None:
            self._d1_ema[s] = close
        else:
            k = 2.0 / (self.d1_ema_period + 1)
            self._d1_ema[s] = close * k + self._d1_ema[s] * (1 - k)

    def _update_atr(self, s: str, event: BarEvent):
        prev_close = self._bars[s][-1].close if self._bars[s] else event.close
        tr = max(
            event.high - event.low,
            abs(event.high - prev_close),
            abs(event.low - prev_close),
        )
        self._atr_count[s] += 1
        count = self._atr_count[s]
        if count == 1:
            self._atr[s] = tr
        elif count <= self.atr_period:
            self._atr[s] = (self._atr[s] * (count - 1) + tr) / count
        else:
            self._atr[s] = (self._atr[s] * (self.atr_period - 1) + tr) / self.atr_period

    def _init(self, s: str):
        if s in self._bars:
            return
        self._bars[s] = deque(maxlen=self.swing_length * 2 + 10)
        self._bar_count[s] = 0
        self._d1_ema[s] = None
        self._d1_count[s] = 0
        self._atr[s] = None
        self._atr_count[s] = 0
        self._zone[s] = None
        self._fractal_price[s] = None
        self._bos_confirmed[s] = False
        self._bos_bar[s] = 0
