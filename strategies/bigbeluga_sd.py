from collections import deque
from dataclasses import dataclass

from models import BarEvent, Signal


@dataclass
class _Zone:
    zone_type: str   # 'DEMAND' or 'SUPPLY'
    top: float
    bottom: float


class BigBelugaSdStrategy:
    """
    Supply and demand zones based on BigBeluga's 3-candle momentum detection,
    with wick rejection market entry.

    ── Zone detection ────────────────────────────────────────────────────────
    Supply zone: 3 consecutive bearish candles, above-average volume on the
    middle bar (bar[-2] from current). Scans back up to 6 bars to find the
    most recent bullish origin candle. Zone anchored to that candle's low:
      bottom = origin.low
      top    = origin.low + ATR × zone_atr_mult

    Demand zone: 3 consecutive bullish candles, above-average volume on the
    middle bar. Origin = most recent bearish candle within 6 bars. Zone:
      top    = origin.high
      bottom = origin.high - ATR × zone_atr_mult

    Cooldown of cooldown_bars between zone detections (per direction) to
    prevent duplicate zones on consecutive bars.

    ── Bias filter ───────────────────────────────────────────────────────────
    D1 EMA(d1_ema_period): demand zones only in uptrend (close > EMA),
    supply zones only in downtrend (close < EMA).

    ── Volume filter (optional) ──────────────────────────────────────────────
    require_volume=True: the middle bar of the 3-candle pattern must have
    volume above the rolling average (vol_lookback bars). With tick_volume
    data this is a proxy; disable to test pattern alone.

    ── Entry ─────────────────────────────────────────────────────────────────
    Wick rejection into zone — bar wicks into zone but closes back outside,
    AND the bar closes in the directional direction (bullish for demand,
    bearish for supply):
      Demand: bar.low <= zone.top  AND  bar.close > zone.top  AND  close > open
      Supply: bar.high >= zone.bottom  AND  bar.close < zone.bottom  AND  close < open
    → MARKET order at bar.close.

    ── Stop-loss ─────────────────────────────────────────────────────────────
      Demand: SL = zone.bottom - sl_buffer_atr × ATR
      Supply: SL = zone.top    + sl_buffer_atr × ATR

    ── Zone invalidation ─────────────────────────────────────────────────────
      Supply: close > zone.top    → zone broken, reset
      Demand: close < zone.bottom → zone broken, reset
    """

    TIMEFRAMES: list
    ORDER_TYPE = 'MARKET'
    NAME = 'BigBelugaSd'

    def __init__(
        self,
        tf_entry: str = 'H4',
        atr_period: int = 200,
        zone_atr_mult: float = 2.0,
        sl_buffer_atr: float = 0.5,
        vol_lookback: int = 200,
        require_volume: bool = True,
        d1_ema_period: int = 50,
        cooldown_bars: int = 15,
        blocked_hours: tuple = (),
    ):
        self.tf_entry = tf_entry
        self.TIMEFRAMES = ['D1', tf_entry]
        self.atr_period = atr_period
        self.zone_atr_mult = zone_atr_mult
        self.sl_buffer_atr = sl_buffer_atr
        self.vol_lookback = vol_lookback
        self.require_volume = require_volume
        self.d1_ema_period = d1_ema_period
        self.cooldown_bars = cooldown_bars
        self._blocked = frozenset(blocked_hours)

        # Per-symbol state
        self._bars: dict[str, deque] = {}
        self._atr: dict[str, float | None] = {}
        self._atr_count: dict[str, int] = {}
        self._vol_history: dict[str, deque] = {}
        self._d1_ema: dict[str, float | None] = {}
        self._d1_count: dict[str, int] = {}
        self._bar_count: dict[str, int] = {}

        # Active zone (one per symbol — D1 bias ensures only one direction active)
        self._zone: dict[str, _Zone | None] = {}

        # Cooldown counters (separate for each direction)
        self._supply_cd: dict[str, int] = {}   # bars remaining in cooldown
        self._demand_cd: dict[str, int] = {}

    def reset(self):
        self._bars.clear()
        self._atr.clear()
        self._atr_count.clear()
        self._vol_history.clear()
        self._d1_ema.clear()
        self._d1_count.clear()
        self._bar_count.clear()
        self._zone.clear()
        self._supply_cd.clear()
        self._demand_cd.clear()

    def generate_signal(self, event: BarEvent) -> Signal | None:
        s = event.symbol
        self._init(s)

        if event.timeframe == 'D1':
            self._update_d1_ema(s, event.close)
            return None

        # ── Indicators ───────────────────────────────────────────────────────
        self._bar_count[s] += 1
        self._update_atr(s, event)
        self._vol_history[s].append(event.volume)

        # ── Append bar FIRST so all bar_at() calls see current bar ───────────
        self._bars[s].append(event)

        # ── Cooldown tick ─────────────────────────────────────────────────────
        if self._supply_cd[s] > 0:
            self._supply_cd[s] -= 1
        if self._demand_cd[s] > 0:
            self._demand_cd[s] -= 1

        # ── Zone invalidation ─────────────────────────────────────────────────
        zone = self._zone[s]
        if zone is not None:
            if zone.zone_type == 'SUPPLY' and event.close > zone.top:
                self._zone[s] = None
                zone = None
            elif zone.zone_type == 'DEMAND' and event.close < zone.bottom:
                self._zone[s] = None
                zone = None

        atr = self._atr[s]
        d1_ema = self._d1_ema[s]

        if atr is None or d1_ema is None:
            return None
        if self._atr_count[s] < self.atr_period or self._d1_count[s] < self.d1_ema_period:
            return None

        blocked = self._blocked and event.timestamp.hour in self._blocked

        # ── Entry check ───────────────────────────────────────────────────────
        if zone is not None and not blocked:
            sig = self._check_wick_rejection(s, event, zone, atr)
            if sig:
                return sig

        # ── Zone detection ────────────────────────────────────────────────────
        if not blocked:
            self._detect_zone(s, event, atr, d1_ema)

        return None

    # ── Zone detection ────────────────────────────────────────────────────────

    def _detect_zone(self, s: str, event: BarEvent, atr: float, d1_ema: float):
        """
        Detect 3-candle momentum pattern and create a zone from the origin candle.
        Requires at least 6 bars in history for the origin scan.
        """
        if len(self._bars[s]) < 6:
            return

        b = [self._bar_at(s, i) for i in range(6)]  # b[0]=current, b[1]=prev, ...
        if any(x is None for x in b):
            return

        avg_vol = (sum(self._vol_history[s]) / len(self._vol_history[s])
                   if self._vol_history[s] else 0.0)

        zone_width = atr * self.zone_atr_mult

        # ── Supply: 3 consecutive bearish candles ─────────────────────────────
        if (b[0].close < b[0].open
                and b[1].close < b[1].open
                and b[2].close < b[2].open
                and (not self.require_volume or b[1].volume > avg_vol)
                and self._supply_cd[s] == 0
                and event.close < d1_ema):          # D1 downtrend bias

            for i in range(6):
                bar_i = b[i]
                if bar_i.close > bar_i.open:        # first bullish candle found
                    new_zone = _Zone(
                        zone_type='SUPPLY',
                        top=bar_i.low + zone_width,
                        bottom=bar_i.low,
                    )
                    # Only replace zone if new one is above current price (valid supply)
                    if event.close < new_zone.bottom:
                        self._zone[s] = new_zone
                        self._supply_cd[s] = self.cooldown_bars
                    break

        # ── Demand: 3 consecutive bullish candles ─────────────────────────────
        elif (b[0].close > b[0].open
                and b[1].close > b[1].open
                and b[2].close > b[2].open
                and (not self.require_volume or b[1].volume > avg_vol)
                and self._demand_cd[s] == 0
                and event.close > d1_ema):          # D1 uptrend bias

            for i in range(6):
                bar_i = b[i]
                if bar_i.close < bar_i.open:        # first bearish candle found
                    new_zone = _Zone(
                        zone_type='DEMAND',
                        top=bar_i.high,
                        bottom=bar_i.high - zone_width,
                    )
                    # Only replace zone if new one is below current price (valid demand)
                    if event.close > new_zone.top:
                        self._zone[s] = new_zone
                        self._demand_cd[s] = self.cooldown_bars
                    break

    # ── Wick rejection entry ──────────────────────────────────────────────────

    def _check_wick_rejection(
        self, s: str, event: BarEvent, zone: _Zone, atr: float
    ) -> Signal | None:
        sl_buffer = atr * self.sl_buffer_atr

        if zone.zone_type == 'DEMAND':
            if (event.low <= zone.top
                    and event.close > zone.top
                    and event.close > event.open):
                sl = zone.bottom - sl_buffer
                self._zone[s] = None
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
                    and event.close < event.open):
                sl = zone.top + sl_buffer
                self._zone[s] = None
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

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _bar_at(self, s: str, i: int) -> BarEvent | None:
        """Bar at relative index i (0 = most recent / current, 1 = one bar ago, ...)."""
        bars = list(self._bars[s])
        if i >= len(bars):
            return None
        return bars[-(i + 1)]

    def _update_atr(self, s: str, event: BarEvent):
        bars = list(self._bars[s])
        prev_close = bars[-1].close if bars else event.close
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

    def _update_d1_ema(self, s: str, close: float):
        self._d1_count[s] += 1
        if self._d1_ema[s] is None:
            self._d1_ema[s] = close
        else:
            k = 2.0 / (self.d1_ema_period + 1)
            self._d1_ema[s] = close * k + self._d1_ema[s] * (1 - k)

    def _init(self, s: str):
        if s in self._bars:
            return
        self._bars[s] = deque(maxlen=50)
        self._atr[s] = None
        self._atr_count[s] = 0
        self._vol_history[s] = deque(maxlen=self.vol_lookback)
        self._d1_ema[s] = None
        self._d1_count[s] = 0
        self._bar_count[s] = 0
        self._zone[s] = None
        self._supply_cd[s] = 0
        self._demand_cd[s] = 0
