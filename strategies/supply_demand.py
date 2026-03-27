from collections import deque
from dataclasses import dataclass

from models import BarEvent, Signal


@dataclass
class Zone:
    zone_type: str    # 'DEMAND' or 'SUPPLY'
    high: float
    low: float
    created_bar: int  # bar index when detected
    leg_pips: float   # size of the departure leg
    touch_count: int = 0
    _in_zone: bool = False  # tracks whether price is currently inside the zone


class SupplyDemandStrategy:
    """
    Supply and demand zone strategy on H4.

    Detects zones where price consolidated in a tight base (cluster of
    small-bodied candles) then departed with a fast move that left a fair
    value gap. Trades the retest with a MARKET order after a rejection
    candle forms at the zone (confirmation entry, not blind limit).

    Zone types:
      DEMAND — base followed by a bullish leg out with FVG → BUY on rejection candle
      SUPPLY — base followed by a bearish leg out with FVG → SELL on rejection candle
    """

    TIMEFRAMES = ['H4']
    ORDER_TYPE = 'MARKET'
    NAME = 'SupplyDemand'

    def __init__(
        self,
        leg_min_pips: float = 30.0,
        base_min_candles: int = 2,
        base_max_candles: int = 4,
        base_max_body_pips: float = 15.0,
        max_retests: int = 3,
        zone_max_age_bars: int = 120,
        min_sl_pips: float = 5.0,
        max_sl_pips: float = 60.0,
        min_leg_zone_ratio: float = 2.0,
        min_fvg_pips: float = 3.0,
        ema_period: int = 50,
        lookback: int = 60,
        pip_sizes: dict[str, float] | None = None,
    ):
        self.leg_min_pips = leg_min_pips
        self.base_min_candles = base_min_candles
        self.base_max_candles = base_max_candles
        self.base_max_body_pips = base_max_body_pips
        self.max_retests = max_retests
        self.zone_max_age_bars = zone_max_age_bars
        self.min_sl_pips = min_sl_pips
        self.max_sl_pips = max_sl_pips
        self.min_leg_zone_ratio = min_leg_zone_ratio
        self.min_fvg_pips = min_fvg_pips
        self.ema_period = ema_period
        self.lookback = lookback
        self.pip_sizes = pip_sizes or {
            'EURUSD': 0.0001, 'GBPUSD': 0.0001, 'AUDUSD': 0.0001,
            'NZDUSD': 0.0001, 'USDJPY': 0.01,   'USDCAD': 0.0001,
            'USDCHF': 0.0001, 'XAUUSD': 0.10,
        }

        # ── Per-symbol state ─────────────────────────────────────────────────
        self._bars: dict[str, deque] = {}
        self._bar_count: dict[str, int] = {}
        self._zones: dict[str, list[Zone]] = {}
        self._ema: dict[str, float | None] = {}
        self._last_direction: dict[str, str | None] = {}

    def reset(self):
        """Clear all internal state."""
        self._bars.clear()
        self._bar_count.clear()
        self._zones.clear()
        self._ema.clear()
        self._last_direction.clear()

    def generate_signal(self, event: BarEvent) -> Signal | None:
        s = event.symbol
        self._init_symbol(s)
        self._bar_count[s] += 1
        bar_idx = self._bar_count[s]

        # Update EMA
        self._update_ema(s, event.close)

        # 1. Invalidate broken zones and update touch counts
        self._update_zones(s, event)

        # 2. Check for rejection candle at a zone (BEFORE appending current bar)
        signal = self._check_rejection(s, event)

        # 3. Append current bar
        self._bars[s].append(event)

        # 4. Detect new zones from the updated window
        new_zone = self._detect_zone(s, bar_idx)
        if new_zone and not self._overlaps_existing(s, new_zone):
            self._zones[s].append(new_zone)

        # 5. Expire old zones
        self._zones[s] = [
            z for z in self._zones[s]
            if bar_idx - z.created_bar <= self.zone_max_age_bars
        ]

        return signal

    # ── Initialisation ────────────────────────────────────────────────────────

    def _init_symbol(self, s: str):
        if s in self._bars:
            return
        self._bars[s] = deque(maxlen=self.lookback)
        self._bar_count[s] = 0
        self._zones[s] = []
        self._ema[s] = None
        self._last_direction[s] = None

    def _pip_size(self, s: str) -> float:
        return self.pip_sizes.get(s, 0.0001)

    def _update_ema(self, s: str, close: float):
        """Update exponential moving average."""
        if self._ema[s] is None:
            self._ema[s] = close
        else:
            k = 2.0 / (self.ema_period + 1)
            self._ema[s] = close * k + self._ema[s] * (1 - k)

    # ══════════════════════════════════════════════════════════════════════════
    # Zone detection
    # ══════════════════════════════════════════════════════════════════════════

    def _detect_zone(self, s: str, bar_idx: int) -> Zone | None:
        """
        Check if the most recent bars form a new supply/demand zone.

        Pattern: [... base candles ...] [FVG leg out (3 bars)]
        The FVG in the last 3 bars confirms a fast departure.
        The base candles before the leg form the zone.
        """
        bars = list(self._bars[s])
        n = len(bars)
        if n < self.base_min_candles + 3:
            return None

        pip = self._pip_size(s)

        # Check last 3 bars for FVG
        b0, b1, b2 = bars[-3], bars[-2], bars[-1]

        bull_fvg = b2.low > b0.high   # bullish gap: bar3 low above bar1 high
        bear_fvg = b2.high < b0.low   # bearish gap: bar3 high below bar1 low

        if not bull_fvg and not bear_fvg:
            return None

        # Check FVG size is meaningful
        if bull_fvg:
            fvg_size = (b2.low - b0.high) / pip
        else:
            fvg_size = (b0.low - b2.high) / pip

        if fvg_size < self.min_fvg_pips:
            return None

        # Measure leg distance
        leg_low = min(b0.low, b1.low, b2.low)
        leg_high = max(b0.high, b1.high, b2.high)
        leg_pips = (leg_high - leg_low) / pip

        if leg_pips < self.leg_min_pips:
            return None

        zone_type = 'DEMAND' if bull_fvg else 'SUPPLY'

        # Look for base candles before the leg (bars before bars[-3])
        base_end_idx = n - 4
        if base_end_idx < 0:
            return None

        base_bars = []
        for i in range(base_end_idx, max(-1, base_end_idx - self.base_max_candles), -1):
            body_pips = abs(bars[i].close - bars[i].open) / pip
            if body_pips <= self.base_max_body_pips:
                base_bars.insert(0, bars[i])
            else:
                break

        if len(base_bars) < self.base_min_candles:
            return None

        zone_high = max(b.high for b in base_bars)
        zone_low = min(b.low for b in base_bars)
        zone_width = (zone_high - zone_low) / pip

        if zone_width < self.min_sl_pips:
            return None

        # Leg must be significantly larger than zone (strong rejection)
        if zone_width > 0 and leg_pips / zone_width < self.min_leg_zone_ratio:
            return None

        return Zone(zone_type=zone_type, high=zone_high, low=zone_low,
                    created_bar=bar_idx, leg_pips=leg_pips)

    # ══════════════════════════════════════════════════════════════════════════
    # Rejection candle detection
    # ══════════════════════════════════════════════════════════════════════════

    def _check_rejection(self, s: str, event: BarEvent) -> Signal | None:
        """
        Check if the current bar is a rejection candle at an active zone.

        Demand zone rejection: bar wicks into the zone but closes above it
        (bullish pin bar / hammer pattern).

        Supply zone rejection: bar wicks into the zone but closes below it
        (bearish pin bar / shooting star pattern).
        """
        pip = self._pip_size(s)
        ema = self._ema[s]

        # Need EMA to be seeded
        if ema is None or self._bar_count[s] < self.ema_period:
            return None

        for z in self._zones[s]:
            # EMA trend filter
            if z.zone_type == 'DEMAND' and event.close < ema:
                continue  # don't buy in downtrend
            if z.zone_type == 'SUPPLY' and event.close > ema:
                continue  # don't sell in uptrend

            if z.zone_type == 'DEMAND':
                # Bar must wick into the zone: low touches or enters the zone
                if event.low > z.high:
                    continue  # bar didn't reach the zone
                if event.low < z.low:
                    continue  # bar went through the zone — not a rejection

                # Must close above the zone (rejection confirmed)
                if event.close <= z.high:
                    continue

                # Must be a bullish candle (close > open)
                if event.close <= event.open:
                    continue

                # Lower wick must be significant (rejection strength)
                body_top = max(event.open, event.close)
                body_bot = min(event.open, event.close)
                lower_wick = body_bot - event.low
                body = body_top - body_bot
                if body > 0 and lower_wick < body:
                    continue  # weak rejection — wick should be >= body

                direction = 'BUY'
                entry = event.close
                sl = z.low  # SL below zone

            else:  # SUPPLY
                # Bar must wick into the zone
                if event.high < z.low:
                    continue
                if event.high > z.high:
                    continue  # went through

                # Must close below the zone
                if event.close >= z.low:
                    continue

                # Must be a bearish candle
                if event.close >= event.open:
                    continue

                # Upper wick must be significant
                body_top = max(event.open, event.close)
                body_bot = min(event.open, event.close)
                upper_wick = event.high - body_top
                body = body_top - body_bot
                if body > 0 and upper_wick < body:
                    continue

                direction = 'SELL'
                entry = event.close
                sl = z.high  # SL above zone

            # Check SL distance
            sl_pips = abs(entry - sl) / pip
            if sl_pips < self.min_sl_pips or sl_pips > self.max_sl_pips:
                continue

            # Suppress duplicate direction
            if self._last_direction[s] == direction:
                continue

            self._last_direction[s] = direction

            return Signal(
                symbol=s,
                direction=direction,
                order_type=self.ORDER_TYPE,
                entry_price=entry,
                stop_loss=sl,
                strategy_name=self.NAME,
                timestamp=event.timestamp,
            )

        return None

    # ══════════════════════════════════════════════════════════════════════════
    # Zone management
    # ══════════════════════════════════════════════════════════════════════════

    def _update_zones(self, s: str, event: BarEvent):
        """Invalidate broken zones and track retests."""
        valid = []
        for z in self._zones[s]:
            broken = False

            if z.zone_type == 'DEMAND':
                if event.close < z.low:
                    broken = True
                price_in_zone = event.low <= z.high
                if price_in_zone and not z._in_zone:
                    z.touch_count += 1
                z._in_zone = price_in_zone

            else:  # SUPPLY
                if event.close > z.high:
                    broken = True
                price_in_zone = event.high >= z.low
                if price_in_zone and not z._in_zone:
                    z.touch_count += 1
                z._in_zone = price_in_zone

            if broken or z.touch_count > self.max_retests:
                continue

            valid.append(z)

        self._zones[s] = valid

    def _overlaps_existing(self, s: str, new_zone: Zone) -> bool:
        """Check if a new zone overlaps significantly with an existing zone of the same type."""
        for z in self._zones[s]:
            if z.zone_type != new_zone.zone_type:
                continue
            overlap_high = min(z.high, new_zone.high)
            overlap_low = max(z.low, new_zone.low)
            if overlap_high > overlap_low:
                overlap = overlap_high - overlap_low
                new_width = new_zone.high - new_zone.low
                if new_width > 0 and overlap / new_width > 0.5:
                    return True
        return False

    def notify_loss(self, symbol: str):
        self._last_direction[symbol] = None  # allow re-entry after loss

    def get_zones(self, symbol: str) -> list[dict]:
        """Diagnostic: return active zones for a symbol."""
        return [
            {'type': z.zone_type, 'high': z.high, 'low': z.low,
             'touches': z.touch_count, 'age': self._bar_count.get(symbol, 0) - z.created_bar}
            for z in self._zones.get(symbol, [])
        ]
