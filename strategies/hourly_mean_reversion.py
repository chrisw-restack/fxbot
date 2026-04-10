"""
HourlyMeanReversion — ICT Power-of-3 / Institutional Candle Mean-Reversion

Concept (inspired by @itstomtrades):
  - An H1 candle runs cleanly in one direction for the first 20–40 minutes
    (minimal retracements — the "one-directional move").
  - Within that window, a Market Structure Shift (MSS) forms on the lower
    timeframe in the OPPOSITE direction to the run.
  - Entry on MSS bar close:
      SL  — absolute peak (SELL) or trough (BUY) of the H1 run
      TP  — 50 % retracement of the H1 candle range: open → peak / trough

Designed for XAUUSD on Asian + London sessions (UTC hours 0–16).

MSS detection (what counts as a "market structure shift"):
  For a UP run → SELL setup:
    1. A fractal swing HIGH is confirmed during/before the entry window.
    2. Primary MSS = close breaks BELOW the swing HIGH bar's own LOW
       (price takes out the range of the peak bar — the "break of candle low").
    3. If a fractal swing LOW also formed ABOVE the candle low (genuine
       internal structure near the peak): MSS = close breaks BELOW that
       fractal low instead (traditional ICT MSS, less restrictive).
    4. Early-hour fractal lows that are BELOW the candle low are ignored —
       they would require an unreachable price drop and block most setups.
  Mirror logic for DOWN run → BUY.

D1 bias filter (use_d1_bias=True):
  Subscribes to D1 bars to track a fast/slow EMA. Only takes signals that
  align with the daily trend direction:
    - D1 bullish (fast EMA > slow EMA) → only BUY signals (fade down-runs)
    - D1 bearish (fast EMA < slow EMA) → only SELL signals (fade up-runs)
  Before D1 EMAs are seeded, both directions are allowed.
  This prevents fighting a strong daily trend (e.g. gold bull market 2022+).

ATR volatility gate (atr_max_pips > 0):
  Subscribes to D1 bars to compute a rolling ATR(atr_period). If the prior
  day's ATR exceeds atr_max_pips, the signal is skipped. High ATR = trending /
  volatile day; low ATR = ranging / mean-reverting conditions where this
  strategy thrives. Set atr_max_pips=0 (default) to disable.

TP geometry check:
  For SELL: entry must be in the upper half of the H1 range (entry > H1 midpoint).
  If the run was very concentrated (one big M5 bar) the entry will be near the
  midpoint already and no signal fires. This is correct — those setups have no
  room to the TP. Use higher min_move_pips or switch to M1 for more setups.

Data:
  - Default tf_lower='M5': uses XAUUSD_M5 CSV — ready to backtest now.
  - For tf_lower='M1': download with fetch_data_dukascopy.py (add 'M1' to
    TIMEFRAMES). M1 gives much more precise MSS detection and more signals.
"""

from collections import deque

from models import BarEvent, Signal


class HourlyMeanReversionStrategy:
    ORDER_TYPE = 'MARKET'
    NAME = 'HourlyMeanReversion'

    def __init__(
        self,
        tf_lower: str = 'M5',          # lower TF for MSS detection: 'M5' or 'M1'
        min_move_pips: float = 100.0,  # min H1 run (pips) before checking for MSS
        entry_window_start: int = 20,  # minutes into H1 to start MSS watch
        entry_window_end: int = 40,    # minutes into H1 to stop watching (exclusive)
        fractal_n: int = 2,            # bars each side for swing point confirmation
        max_pullback_pips: float = 50.0,  # max intra-run pullback (pips); 0 = disabled
        session_hours: tuple[int, ...] = (*range(0, 17),),  # UTC: Asian 0–8, London 8–16
        pip_sizes: dict[str, float] | None = None,
        use_d1_bias: bool = False,     # gate signals by D1 EMA trend direction
        d1_ema_fast: int = 10,         # D1 fast EMA period (bias filter)
        d1_ema_slow: int = 20,         # D1 slow EMA period (bias filter)
        atr_max_pips: float = 0.0,     # skip signals when prior-day ATR > this (0=off)
        atr_period: int = 14,          # ATR rolling period (D1 bars)
    ):
        # TIMEFRAMES is an instance attribute so the engine routes the correct feed.
        self.TIMEFRAMES = ['D1', tf_lower] if (use_d1_bias or atr_max_pips > 0) else [tf_lower]
        self._tf = tf_lower
        self.use_d1_bias = use_d1_bias
        self.d1_ema_fast = d1_ema_fast
        self.d1_ema_slow = d1_ema_slow
        self.atr_max_pips = atr_max_pips
        self.atr_period = atr_period
        self.min_move_pips = min_move_pips
        self.entry_window_start = entry_window_start
        self.entry_window_end = entry_window_end
        self.fractal_n = fractal_n
        self.max_pullback_pips = max_pullback_pips
        self._session_hours = set(session_hours)
        self.pip_sizes = pip_sizes or {
            'XAUUSD': 0.10,
            'EURUSD': 0.0001, 'GBPUSD': 0.0001, 'AUDUSD': 0.0001,
            'NZDUSD': 0.0001, 'USDJPY': 0.01,   'USDCAD': 0.0001,
            'USDCHF': 0.0001,
            'USA100': 1.0,  'USTEC': 1.0,
            'USA30':  1.0,  'US30':  1.0,
            'USA500': 0.1,  'US500': 0.1,
        }
        self._buf_size = 2 * fractal_n + 1

        # ── Per-symbol state ──────────────────────────────────────────────────
        self._h1_id: dict[str, tuple | None] = {}
        self._h1_open: dict[str, float] = {}

        # Running peak / trough and intra-run pullback tracking
        self._peak: dict[str, float] = {}
        self._trough: dict[str, float] = {}
        self._peak_pullback_low: dict[str, float] = {}
        self._trough_pullback_high: dict[str, float] = {}
        self._max_up_pullback: dict[str, float] = {}
        self._max_dn_pullback: dict[str, float] = {}

        # Fractal swing detection
        self._buf: dict[str, deque] = {}

        # Most recent confirmed swing HIGH and LOW (price and full bar)
        self._last_sh: dict[str, float | None] = {}
        self._last_sh_bar: dict[str, BarEvent | None] = {}
        self._last_sl: dict[str, float | None] = {}
        self._last_sl_bar: dict[str, BarEvent | None] = {}

        # One signal per H1 candle
        self._fired: dict[str, bool] = {}

        # D1 bias filter state (used only when use_d1_bias=True)
        self._d1_bar_count: dict[str, int] = {}
        self._d1_ema_f: dict[str, float | None] = {}   # fast EMA value
        self._d1_ema_s: dict[str, float | None] = {}   # slow EMA value
        self._d1_sum_f: dict[str, float] = {}          # SMA accumulator (fast)
        self._d1_sum_s: dict[str, float] = {}          # SMA accumulator (slow)

        # ATR volatility gate state (used only when atr_max_pips > 0)
        self._d1_prev_close: dict[str, float | None] = {}
        self._d1_tr_buf: dict[str, deque] = {}         # rolling True Range buffer
        self._d1_atr: dict[str, float | None] = {}     # current ATR (pips)

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def reset(self):
        """Clear all internal state. Called before reusing across backtests."""
        self._h1_id.clear()
        self._h1_open.clear()
        self._peak.clear()
        self._trough.clear()
        self._peak_pullback_low.clear()
        self._trough_pullback_high.clear()
        self._max_up_pullback.clear()
        self._max_dn_pullback.clear()
        self._buf.clear()
        self._last_sh.clear()
        self._last_sh_bar.clear()
        self._last_sl.clear()
        self._last_sl_bar.clear()
        self._fired.clear()
        self._d1_bar_count.clear()
        self._d1_ema_f.clear()
        self._d1_ema_s.clear()
        self._d1_sum_f.clear()
        self._d1_sum_s.clear()
        self._d1_prev_close.clear()
        self._d1_tr_buf.clear()
        self._d1_atr.clear()

    # ── Main entry point ───────────────────────────────────────────────────────

    def generate_signal(self, event: BarEvent) -> Signal | None:
        sym = event.symbol
        self._init(sym)

        # D1 bars: update bias EMA and/or ATR — no signal from daily bars
        if event.timeframe == 'D1':
            if self.use_d1_bias:
                self._update_d1_ema(sym, event.close)
            if self.atr_max_pips > 0:
                self._update_d1_atr(sym, event)
            return None

        ts = event.timestamp
        candle_id = (ts.year, ts.month, ts.day, ts.hour)

        # ── Detect new H1 candle and reset per-candle state ──────────────────
        if candle_id != self._h1_id[sym]:
            self._h1_id[sym] = candle_id
            self._h1_open[sym] = event.open
            self._peak[sym] = event.high
            self._trough[sym] = event.low
            self._peak_pullback_low[sym] = event.low
            self._trough_pullback_high[sym] = event.high
            self._max_up_pullback[sym] = 0.0
            self._max_dn_pullback[sym] = 0.0
            self._buf[sym] = deque(maxlen=self._buf_size)
            self._last_sh[sym] = None
            self._last_sh_bar[sym] = None
            self._last_sl[sym] = None
            self._last_sl_bar[sym] = None
            self._fired[sym] = False

        # ── Session filter ────────────────────────────────────────────────────
        if ts.hour not in self._session_hours:
            self._buf[sym].append(event)
            return None

        # ── Update running high / low and intra-run pullback depth ────────────
        if event.high > self._peak[sym]:
            self._peak[sym] = event.high
            self._peak_pullback_low[sym] = event.low
        else:
            self._peak_pullback_low[sym] = min(self._peak_pullback_low[sym], event.low)

        if event.low < self._trough[sym]:
            self._trough[sym] = event.low
            self._trough_pullback_high[sym] = event.high
        else:
            self._trough_pullback_high[sym] = max(self._trough_pullback_high[sym], event.high)

        # Persist max pullback seen (survives resets when new highs/lows form)
        self._max_up_pullback[sym] = max(
            self._max_up_pullback[sym],
            self._peak[sym] - self._peak_pullback_low[sym],
        )
        self._max_dn_pullback[sym] = max(
            self._max_dn_pullback[sym],
            self._trough_pullback_high[sym] - self._trough[sym],
        )

        # ── Fractal swing detection ───────────────────────────────────────────
        self._buf[sym].append(event)
        self._update_fractals(sym)

        # ── Entry window check ────────────────────────────────────────────────
        minutes = ts.minute
        if minutes < self.entry_window_start or minutes >= self.entry_window_end:
            return None

        if self._fired[sym]:
            return None

        # ── Compute run quality metrics ───────────────────────────────────────
        pip = self._pip(sym)
        h1_open = self._h1_open[sym]
        last_sh = self._last_sh[sym]
        last_sh_bar = self._last_sh_bar[sym]
        last_sl = self._last_sl[sym]
        last_sl_bar = self._last_sl_bar[sym]

        up_dist = (self._peak[sym] - h1_open) / pip
        up_pullback = self._max_up_pullback[sym] / pip
        dn_dist = (h1_open - self._trough[sym]) / pip
        dn_pullback = self._max_dn_pullback[sym] / pip

        clean = self.max_pullback_pips <= 0

        # ── ATR volatility gate ───────────────────────────────────────────────
        if self.atr_max_pips > 0:
            atr = self._d1_atr.get(sym)
            if atr is not None and atr > self.atr_max_pips:
                return None

        # ── D1 bias (None = not seeded yet → allow both directions) ─────────────
        d1_bias = self._d1_bias(sym) if self.use_d1_bias else None

        # ── UP run → SELL on MSS down ─────────────────────────────────────────
        if (up_dist >= self.min_move_pips
                and (clean or up_pullback <= self.max_pullback_pips)
                and last_sh is not None
                and (d1_bias is None or d1_bias == 'SELL')):

            # MSS level: use break of peak bar's candle low as primary.
            # Use fractal low only if it's ABOVE candle low (genuine internal
            # structure shift near the peak, not an early-hour dip).
            candle_low = last_sh_bar.low if last_sh_bar is not None else None
            if last_sl is not None and candle_low is not None and last_sl > candle_low:
                mss_level = last_sl
            else:
                mss_level = candle_low

            if mss_level is not None and event.close < mss_level:
                tp = h1_open + 0.5 * (self._peak[sym] - h1_open)
                sl = self._peak[sym]
                # Geometry: SL above entry (price hasn't gone past peak),
                # entry above TP (entry is in the upper half of the H1 range,
                # ensuring acceptable R:R with the 50% TP).
                if sl > event.close > tp:
                    self._fired[sym] = True
                    return Signal(
                        symbol=sym,
                        direction='SELL',
                        order_type=self.ORDER_TYPE,
                        entry_price=event.close,
                        stop_loss=sl,
                        strategy_name=self.NAME,
                        timestamp=ts,
                        take_profit=tp,
                    )

        # ── DOWN run → BUY on MSS up ──────────────────────────────────────────
        if (dn_dist >= self.min_move_pips
                and (clean or dn_pullback <= self.max_pullback_pips)
                and last_sl is not None
                and (d1_bias is None or d1_bias == 'BUY')):

            # Mirror of SELL logic: use break of trough bar's candle high as
            # primary. Use fractal high only if BELOW candle high.
            candle_high = last_sl_bar.high if last_sl_bar is not None else None
            if last_sh is not None and candle_high is not None and last_sh < candle_high:
                mss_level = last_sh
            else:
                mss_level = candle_high

            if mss_level is not None and event.close > mss_level:
                tp = h1_open - 0.5 * (h1_open - self._trough[sym])
                sl = self._trough[sym]
                if sl < event.close < tp:
                    self._fired[sym] = True
                    return Signal(
                        symbol=sym,
                        direction='BUY',
                        order_type=self.ORDER_TYPE,
                        entry_price=event.close,
                        stop_loss=sl,
                        strategy_name=self.NAME,
                        timestamp=ts,
                        take_profit=tp,
                    )

        return None

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _update_fractals(self, sym: str):
        """Detect fractal swing highs and lows from the rolling bar buffer."""
        buf = self._buf[sym]
        if len(buf) < self._buf_size:
            return
        mid = self.fractal_n
        mid_bar = buf[mid]

        if all(mid_bar.high > buf[i].high for i in range(self._buf_size) if i != mid):
            self._last_sh[sym] = mid_bar.high
            self._last_sh_bar[sym] = mid_bar

        if all(mid_bar.low < buf[i].low for i in range(self._buf_size) if i != mid):
            self._last_sl[sym] = mid_bar.low
            self._last_sl_bar[sym] = mid_bar

    def _init(self, sym: str):
        """Initialise per-symbol state dicts on first encounter."""
        if sym in self._h1_id:
            return
        self._h1_id[sym] = None
        self._h1_open[sym] = 0.0
        self._peak[sym] = 0.0
        self._trough[sym] = float('inf')
        self._peak_pullback_low[sym] = float('inf')
        self._trough_pullback_high[sym] = 0.0
        self._max_up_pullback[sym] = 0.0
        self._max_dn_pullback[sym] = 0.0
        self._buf[sym] = deque(maxlen=self._buf_size)
        self._last_sh[sym] = None
        self._last_sh_bar[sym] = None
        self._last_sl[sym] = None
        self._last_sl_bar[sym] = None
        self._fired[sym] = False
        self._d1_bar_count[sym] = 0
        self._d1_ema_f[sym] = None
        self._d1_ema_s[sym] = None
        self._d1_sum_f[sym] = 0.0
        self._d1_sum_s[sym] = 0.0
        self._d1_prev_close[sym] = None
        self._d1_tr_buf[sym] = deque(maxlen=self.atr_period)
        self._d1_atr[sym] = None

    def _update_d1_ema(self, sym: str, close: float):
        """SMA-seeded EMA for D1 bias (same approach as EmaFibRetracement)."""
        self._d1_bar_count[sym] += 1
        count = self._d1_bar_count[sym]
        self._d1_sum_f[sym] += close
        self._d1_sum_s[sym] += close

        if count == self.d1_ema_fast:
            self._d1_ema_f[sym] = self._d1_sum_f[sym] / self.d1_ema_fast
        elif count > self.d1_ema_fast:
            k = 2.0 / (self.d1_ema_fast + 1)
            self._d1_ema_f[sym] = close * k + self._d1_ema_f[sym] * (1 - k)

        if count == self.d1_ema_slow:
            self._d1_ema_s[sym] = self._d1_sum_s[sym] / self.d1_ema_slow
        elif count > self.d1_ema_slow:
            k = 2.0 / (self.d1_ema_slow + 1)
            self._d1_ema_s[sym] = close * k + self._d1_ema_s[sym] * (1 - k)

    def _update_d1_atr(self, sym: str, event: BarEvent):
        """Compute True Range and update rolling ATR (in pips) from D1 bars."""
        pip = self._pip(sym)
        prev_close = self._d1_prev_close.get(sym)
        if prev_close is not None:
            tr = max(
                event.high - event.low,
                abs(event.high - prev_close),
                abs(event.low - prev_close),
            ) / pip
        else:
            tr = (event.high - event.low) / pip
        self._d1_prev_close[sym] = event.close

        buf = self._d1_tr_buf[sym]
        buf.append(tr)
        if len(buf) >= self.atr_period:
            self._d1_atr[sym] = sum(buf) / len(buf)

    def _d1_bias(self, sym: str) -> str | None:
        """Returns 'BUY', 'SELL', or None if D1 EMAs not yet seeded."""
        f = self._d1_ema_f.get(sym)
        s = self._d1_ema_s.get(sym)
        if f is None or s is None:
            return None
        return 'BUY' if f > s else 'SELL'

    def _pip(self, sym: str) -> float:
        return self.pip_sizes.get(sym, 0.0001)
