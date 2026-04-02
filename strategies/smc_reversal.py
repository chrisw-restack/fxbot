from collections import deque
from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

from models import BarEvent, Signal


@dataclass
class OrderBlock:
    high: float       # max of series bodies (open for bearish series, close for bullish series)
    low: float        # min of series bodies
    direction: str    # 'BULL' | 'BEAR'
    tf: str
    timestamp: datetime


class SmcReversalStrategy:
    """
    ICT-style multi-timeframe reversal strategy for US equity indices.

    Designed for USA100, USA30, and USA500. All price-level parameters are expressed
    as fractions of the current price so they scale automatically across symbols.

    Structure:
      D1  — bias from SSL/BSL liquidity sweep (fractal-based)
      H4/H1/M15 — order block confluence (need 2-of-3 TFs to overlap)
      M5  — engulfing bar entry within NY session window (9:45–11:00 AM ET)

    Order Block definition:
      - Zone = bodies only (no wicks), all consecutive non-opposing candles
        (doji does NOT break the series)
      - Displacement confirmed by an FVG forming within fvg_window candles after the series:
          Bullish FVG: bars[i].high < bars[i+2].low  (gap between candle 1 top and candle 3 bottom)
          Bearish FVG: bars[i].low  > bars[i+2].high
      - Bullish OB: bearish/doji series + bullish FVG within fvg_window candles after series
      - Bearish OB: bullish/doji series + bearish FVG within fvg_window candles after series

    Bias invalidation (LONG):
      - Wick above any D1 fractal high → invalidated (liquidity taken, lack of conviction)
      - Close below any D1 fractal low  → invalidated (structure broken)
    Inverse for SHORT.

    OB invalidation:
      - Bullish OB: a candle CLOSES below OB.low  → mitigated, removed
      - Bearish OB: a candle CLOSES above OB.high → mitigated, removed

    M15 OBs reset each new trading day (cleared on new D1 bar).
    H4/H1 OBs persist until price mitigates them.
    """

    TIMEFRAMES = ['D1', 'H4', 'H1', 'M15', 'M5']
    ORDER_TYPE = 'MARKET'
    NAME = 'SmcReversal'

    def __init__(
        self,
        fractal_n: int = 3,
        fvg_window: int = 4,
        ob_max_per_tf: int = 3,
        wiggle_room_pct: float = 0.003,
        sl_buffer_pct: float = 0.0006,
        multiple_trades_per_bias: bool = True,
    ):
        """
        Args:
            wiggle_room_pct: OB overlap tolerance as a fraction of zone midpoint price.
                             0.003 = 0.3%, which equals ~54 pts on NAS100@18K,
                             ~120 pts on DOW@40K, ~15 pts on SPX@5K.
            sl_buffer_pct:   Extra buffer below/above the SL swing as a fraction of
                             that swing price. 0.0006 = 0.06% ≈ 11 pts on NAS100@18K.
        """
        self.fractal_n = fractal_n
        self.fvg_window = fvg_window
        self.ob_max_per_tf = ob_max_per_tf
        self.wiggle_room_pct = wiggle_room_pct
        self.sl_buffer_pct = sl_buffer_pct
        self.multiple_trades_per_bias = multiple_trades_per_bias
        self._tz = ZoneInfo('America/New_York')
        self._ny_open = time(9, 45)
        self._ny_close = time(11, 0)

        # Per-symbol state
        self._d1_bars:          dict[str, deque] = {}
        self._d1_fractal_lows:  dict[str, list]  = {}
        self._d1_fractal_highs: dict[str, list]  = {}
        self._d1_bias:          dict[str, str | None] = {}
        self._current_day:      dict[str, int | None] = {}

        self._h4_bars: dict[str, deque] = {}
        self._h4_obs:  dict[str, list]  = {}

        self._h1_bars: dict[str, deque] = {}
        self._h1_obs:  dict[str, list]  = {}

        self._m15_bars: dict[str, deque] = {}
        self._m15_obs:  dict[str, list]  = {}

        self._m5_bars:        dict[str, deque]       = {}
        self._in_zone:        dict[str, bool]         = {}
        self._zone_extreme:   dict[str, float]        = {}  # min low (long) or max high (short)
        self._last_direction: dict[str, str | None]   = {}

    def reset(self):
        for d in (
            self._d1_bars, self._d1_fractal_lows, self._d1_fractal_highs,
            self._d1_bias, self._current_day,
            self._h4_bars, self._h4_obs,
            self._h1_bars, self._h1_obs,
            self._m15_bars, self._m15_obs,
            self._m5_bars, self._in_zone, self._zone_extreme, self._last_direction,
        ):
            d.clear()

    # ── Initialisation ───────────────────────────────────────────────────────

    def _init_symbol(self, symbol: str):
        if symbol in self._d1_bars:
            return
        lb = 150
        self._d1_bars[symbol]          = deque(maxlen=lb)
        self._d1_fractal_lows[symbol]  = []
        self._d1_fractal_highs[symbol] = []
        self._d1_bias[symbol]          = None
        self._current_day[symbol]      = None
        self._h4_bars[symbol]          = deque(maxlen=lb)
        self._h4_obs[symbol]           = []
        self._h1_bars[symbol]          = deque(maxlen=lb)
        self._h1_obs[symbol]           = []
        self._m15_bars[symbol]         = deque(maxlen=lb)
        self._m15_obs[symbol]          = []
        self._m5_bars[symbol]          = deque(maxlen=50)
        self._in_zone[symbol]          = False
        self._zone_extreme[symbol]     = float('inf')
        self._last_direction[symbol]   = None

    # ── Routing ──────────────────────────────────────────────────────────────

    def generate_signal(self, event: BarEvent) -> Signal | None:
        symbol = event.symbol
        self._init_symbol(symbol)
        tf = event.timeframe

        if tf == 'D1':
            self._process_d1(event, symbol)
        elif tf == 'H4':
            self._process_htf(event, symbol, 'H4', self._h4_bars, self._h4_obs)
        elif tf == 'H1':
            self._process_htf(event, symbol, 'H1', self._h1_bars, self._h1_obs)
        elif tf == 'M15':
            self._process_m15(event, symbol)
        elif tf == 'M5':
            return self._process_m5(event, symbol)
        return None

    # ── D1 bias ──────────────────────────────────────────────────────────────

    def _process_d1(self, event: BarEvent, symbol: str):
        bars = self._d1_bars[symbol]
        bars.append(event)

        # Reset M15 bars, OBs and M5 zone state on each new trading day.
        # Must clear the deque too — otherwise _process_m15 rescans old bars
        # and re-adds yesterday's OBs on the first new M15 bar.
        day = event.timestamp.toordinal()
        if self._current_day[symbol] != day:
            self._current_day[symbol] = day
            self._m15_bars[symbol].clear()
            self._m15_obs[symbol] = []
            self._in_zone[symbol] = False
            self._zone_extreme[symbol] = float('inf')

        bl = list(bars)
        n = self.fractal_n

        # Confirm fractal at index -(n+1): it now has n confirmed bars to its right
        if len(bl) >= 2 * n + 1:
            idx = len(bl) - n - 1
            cand = bl[idx]

            if all(bl[idx - k].low > cand.low for k in range(1, n + 1)) and \
               all(bl[idx + k].low > cand.low for k in range(1, n + 1)):
                fl = self._d1_fractal_lows[symbol]
                fl.append(cand.low)
                if len(fl) > 10:
                    fl.pop(0)

            if all(bl[idx - k].high < cand.high for k in range(1, n + 1)) and \
               all(bl[idx + k].high < cand.high for k in range(1, n + 1)):
                fh = self._d1_fractal_highs[symbol]
                fh.append(cand.high)
                if len(fh) > 10:
                    fh.pop(0)

        self._update_d1_bias(event, symbol)

    def _update_d1_bias(self, event: BarEvent, symbol: str):
        lows  = self._d1_fractal_lows[symbol]
        highs = self._d1_fractal_highs[symbol]
        bias  = self._d1_bias[symbol]

        # Invalidate before checking for new bias (avoids flip on same bar)
        if bias == 'LONG':
            if highs and event.high > highs[-1]:       # wick above swing high
                self._d1_bias[symbol] = None
                return
            if lows and event.close < lows[-1]:         # close below swing low
                self._d1_bias[symbol] = None
                return

        elif bias == 'SHORT':
            if lows and event.low < lows[-1]:           # wick below swing low
                self._d1_bias[symbol] = None
                return
            if highs and event.close > highs[-1]:       # close above swing high
                self._d1_bias[symbol] = None
                return

        # Set new bias from SSL/BSL sweep (only when no current bias)
        if bias is None:
            if lows:
                recent_low = lows[-1]
                if event.low < recent_low and event.close > recent_low:
                    self._d1_bias[symbol] = 'LONG'
                    return
            if highs:
                recent_high = highs[-1]
                if event.high > recent_high and event.close < recent_high:
                    self._d1_bias[symbol] = 'SHORT'
                    return

    # ── HTF OB detection (H4, H1) ────────────────────────────────────────────

    def _process_htf(self, event: BarEvent, symbol: str, tf: str,
                     bars_dict: dict, obs_dict: dict):
        bars_dict[symbol].append(event)
        obs_dict[symbol] = self._detect_obs(list(bars_dict[symbol]), tf)

    def _process_m15(self, event: BarEvent, symbol: str):
        self._m15_bars[symbol].append(event)
        self._m15_obs[symbol] = self._detect_obs(list(self._m15_bars[symbol]), 'M15')

    # ── OB detection ─────────────────────────────────────────────────────────

    def _detect_obs(self, bars: list[BarEvent], tf: str) -> list[OrderBlock]:
        """Return up to ob_max_per_tf most recent active OBs (both directions)."""
        return (
            self._scan_obs(bars, 'BULL', tf) +
            self._scan_obs(bars, 'BEAR', tf)
        )

    def _scan_obs(self, bars: list[BarEvent], direction: str, tf: str) -> list[OrderBlock]:
        """
        Scan bars (oldest first) for OBs in one direction.

        BULL OB: consecutive non-bullish series (close <= open, doji included),
                 validated by a bullish FVG (bars[k].high < bars[k+2].low)
                 forming within fvg_window candles after the series end.

        BEAR OB: consecutive non-bearish series (close >= open),
                 validated by a bearish FVG (bars[k].low > bars[k+2].high)
                 within fvg_window candles after the series end.

        Zone = bodies only (no wicks).
        """
        n = len(bars)
        obs: list[OrderBlock] = []
        i = 0

        while i < n and len(obs) < self.ob_max_per_tf:
            bar = bars[i]

            # Skip candles that can't start a series in this direction
            if direction == 'BULL' and bar.close > bar.open:
                i += 1
                continue
            if direction == 'BEAR' and bar.close < bar.open:
                i += 1
                continue

            # Collect the series: consecutive non-opposing candles (doji OK)
            series_start = i
            j = i
            if direction == 'BULL':
                while j < n and bars[j].close <= bars[j].open:
                    j += 1
            else:
                while j < n and bars[j].close >= bars[j].open:
                    j += 1
            series_end = j - 1
            series = bars[series_start:series_end + 1]

            # OB zone — bodies only
            if direction == 'BULL':
                ob_high = max(b.open  for b in series)   # top of bodies
                ob_low  = min(b.close for b in series)   # bottom of bodies
            else:
                ob_high = max(b.close for b in series)
                ob_low  = min(b.open  for b in series)

            # Validate displacement via FVG within fvg_window candles after series
            # FVG needs 3 candles: check all 3-candle windows in [j, j+fvg_window)
            fvg_end = min(j + self.fvg_window, n - 2)
            displaced = False
            for k in range(j, fvg_end):
                if direction == 'BULL' and bars[k].high < bars[k + 2].low:
                    displaced = True
                    break
                if direction == 'BEAR' and bars[k].low > bars[k + 2].high:
                    displaced = True
                    break

            if displaced:
                # Check not already mitigated by a subsequent close
                mitigated = False
                for k in range(j, n):
                    if direction == 'BULL' and bars[k].close < ob_low:
                        mitigated = True
                        break
                    if direction == 'BEAR' and bars[k].close > ob_high:
                        mitigated = True
                        break

                if not mitigated:
                    obs.append(OrderBlock(
                        high=ob_high,
                        low=ob_low,
                        direction=direction,
                        tf=tf,
                        timestamp=bars[series_start].timestamp,
                    ))

            i = series_end + 1

        # Return the most recent ob_max_per_tf (list was built oldest→newest)
        return obs[-self.ob_max_per_tf:]

    # ── Confluence zone ───────────────────────────────────────────────────────

    def _get_confluence_zone(self, symbol: str) -> tuple[float, float] | None:
        """
        Return (zone_low, zone_high) if M15 has an active OB AND at least one
        of H4/H1 has an OB that overlaps with it (within wiggle_room_points).
        M15 is always required. H4 and H1 are interchangeable — only one needed.
        """
        bias = self._d1_bias[symbol]
        if bias is None:
            return None

        direction = 'BULL' if bias == 'LONG' else 'BEAR'

        h4  = [ob for ob in self._h4_obs[symbol]  if ob.direction == direction]
        h1  = [ob for ob in self._h1_obs[symbol]  if ob.direction == direction]
        m15 = [ob for ob in self._m15_obs[symbol] if ob.direction == direction]

        if not m15:
            return None

        # M15 required — check H4+M15, then H1+M15
        for htf_list in [h4, h1]:
            zone = self._find_ob_overlap(htf_list, m15)
            if zone:
                return zone
        return None

    def _find_ob_overlap(
        self,
        obs_a: list[OrderBlock],
        obs_b: list[OrderBlock],
    ) -> tuple[float, float] | None:
        """
        Return the union zone of the nearest overlapping pair from two OB lists.
        Zones are considered overlapping if the gap between them is <= wiggle_room_pct
        of the zone midpoint price. Most recent OBs checked first (newest-last).
        """
        for a in reversed(obs_a):
            for b in reversed(obs_b):
                zone_mid = (a.high + a.low + b.high + b.low) / 4.0
                w = zone_mid * self.wiggle_room_pct
                # Gap between zones: positive = they don't overlap, negative = they do
                gap = max(a.low, b.low) - min(a.high, b.high)
                if gap <= w:
                    return (min(a.low, b.low), max(a.high, b.high))
        return None

    # ── M5 entry logic ───────────────────────────────────────────────────────

    def _in_ny_window(self, ts: datetime) -> bool:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=ZoneInfo('UTC'))
        ny = ts.astimezone(self._tz).time()
        return self._ny_open <= ny < self._ny_close

    def _process_m5(self, event: BarEvent, symbol: str) -> Signal | None:
        m5 = self._m5_bars[symbol]

        if not m5:
            m5.append(event)
            return None

        prev = m5[-1]
        m5.append(event)

        bias = self._d1_bias[symbol]
        if bias is None:
            self._in_zone[symbol] = False
            return None

        if not self._in_ny_window(event.timestamp):
            return None

        zone = self._get_confluence_zone(symbol)
        if zone is None:
            self._in_zone[symbol] = False
            return None

        zone_low, zone_high = zone

        if bias == 'LONG':
            # Enter zone when M5 low taps into the OB
            if event.low <= zone_high:
                if not self._in_zone[symbol]:
                    self._in_zone[symbol] = True
                    self._zone_extreme[symbol] = event.low
                else:
                    self._zone_extreme[symbol] = min(self._zone_extreme[symbol], event.low)

            # OB violated if M5 CLOSES below zone_low → reset zone
            if event.close < zone_low:
                self._in_zone[symbol] = False
                self._zone_extreme[symbol] = float('inf')
                return None

            if not self._in_zone[symbol]:
                return None

            # Engulf trigger: current bar closes above previous bar's open
            if event.close > prev.open and event.close > event.open:
                if not self.multiple_trades_per_bias and self._last_direction[symbol] == 'BUY':
                    return None
                extreme = self._zone_extreme[symbol]
                sl = extreme - extreme * self.sl_buffer_pct
                self._in_zone[symbol] = False
                self._last_direction[symbol] = 'BUY'
                return Signal(
                    symbol=symbol,
                    direction='BUY',
                    order_type=self.ORDER_TYPE,
                    entry_price=event.close,
                    stop_loss=sl,
                    strategy_name=self.NAME,
                    timestamp=event.timestamp,
                )

        else:  # SHORT
            if event.high >= zone_low:
                if not self._in_zone[symbol]:
                    self._in_zone[symbol] = True
                    self._zone_extreme[symbol] = event.high
                else:
                    self._zone_extreme[symbol] = max(self._zone_extreme[symbol], event.high)

            if event.close > zone_high:
                self._in_zone[symbol] = False
                self._zone_extreme[symbol] = float('-inf')
                return None

            if not self._in_zone[symbol]:
                return None

            if event.close < prev.open and event.close < event.open:
                if not self.multiple_trades_per_bias and self._last_direction[symbol] == 'SELL':
                    return None
                extreme = self._zone_extreme[symbol]
                sl = extreme + extreme * self.sl_buffer_pct
                self._in_zone[symbol] = False
                self._last_direction[symbol] = 'SELL'
                return Signal(
                    symbol=symbol,
                    direction='SELL',
                    order_type=self.ORDER_TYPE,
                    entry_price=event.close,
                    stop_loss=sl,
                    strategy_name=self.NAME,
                    timestamp=event.timestamp,
                )

        return None
