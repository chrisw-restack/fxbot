"""
EBP Limit (Single Timeframe Engulfing Bar Play)

On a single timeframe:
  - Bullish engulf: close > prev.open AND low < prev.low
  - Bearish engulf: close < prev.open AND high > prev.high

Entry:
  - BUY LIMIT at high - entry_pct * range  (default 25% into bar from top)
  - SELL LIMIT at low  + entry_pct * range  (default 25% into bar from bottom)

SL:
  - BUY:  prev.low  (the low the engulf candle took out)
  - SELL: prev.high (the high the engulf candle took out)

TP: risk manager calculates at 2:1 R:R (no take_profit set on Signal)

Filters:
  - max_sl_pips: skip if SL distance (entry to sl) exceeds this in pips
  - min_range_pips: skip if engulf bar range is smaller than this in pips
  - tf_trend / ema_fast / ema_slow: optional higher-timeframe EMA trend filter.
      tf_trend is the timeframe whose EMA is checked (e.g. 'D1' when tf='H4').
      Only BUY signals when fast EMA > slow EMA on that TF, SELL when fast < slow.
      Set ema_fast=0 to disable.

Cancel conditions:
  - New engulfing bar: cancel old pending, place new one (deferred one bar)
  - TP level hit before fill: if price reaches the 2R target while the pending
    has not been filled, the move already happened without us — cancel

Invalid geometry (SL on wrong side of entry) is silently skipped.
"""

from models import BarEvent, Signal

# Default pip sizes — USDJPY is 0.01, everything else 0.0001
_DEFAULT_PIP_SIZES = {
    'USDJPY': 0.01,
}


class EbpLimitStrategy:
    ORDER_TYPE = 'PENDING'

    def __init__(
        self,
        tf: str = 'H4',
        entry_pct: float = 0.25,    # how far into the bar to place the limit entry
        tp_r: float = 2.0,          # R multiple for TP (used for cancel-if-TP-hit check)
        max_sl_pips: float = 80,    # skip if SL distance > this many pips (0 = disabled)
        min_range_pips: float = 0,  # skip if engulf bar range < this many pips (0 = disabled)
        tf_trend: str | None = None,  # higher TF to read EMA trend from (e.g. 'D1')
        ema_fast: int = 20,           # EMA fast period on tf_trend (0 = disabled)
        ema_slow: int = 50,           # EMA slow period on tf_trend
        pip_sizes: dict | None = None,
    ):
        self.tf = tf
        self.entry_pct = entry_pct
        self.tp_r = tp_r
        self.max_sl_pips = max_sl_pips
        self.min_range_pips = min_range_pips
        self.tf_trend = tf_trend
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.pip_sizes = {**_DEFAULT_PIP_SIZES, **(pip_sizes or {})}

        tfs = [tf]
        if tf_trend and ema_fast > 0:
            tfs = list(dict.fromkeys([tf_trend, tf]))  # trend TF first, preserve order
        self.TIMEFRAMES = tfs
        self.NAME = f'EBPLimit_{tf}'

        self._prev_bar: dict[str, BarEvent | None] = {}
        self._signal_fired: dict[str, bool] = {}
        self._pending_signal: dict[str, Signal | None] = {}
        # Details of the live pending order — needed for cancel-if-TP-hit check
        self._pending_entry: dict[str, float] = {}
        self._pending_tp: dict[str, float] = {}
        self._pending_dir: dict[str, str] = {}

        # Per-symbol EMA state on the trend TF
        self._ema_fast: dict[str, float | None] = {}
        self._ema_slow: dict[str, float | None] = {}
        self._ema_fast_sum: dict[str, float] = {}
        self._ema_slow_sum: dict[str, float] = {}
        self._ema_bar_count: dict[str, int] = {}

    def reset(self):
        self._prev_bar.clear()
        self._signal_fired.clear()
        self._pending_signal.clear()
        self._pending_entry.clear()
        self._pending_tp.clear()
        self._pending_dir.clear()
        self._ema_fast.clear()
        self._ema_slow.clear()
        self._ema_fast_sum.clear()
        self._ema_slow_sum.clear()
        self._ema_bar_count.clear()

    def notify_loss(self, symbol: str):
        self._signal_fired[symbol] = False
        self._pending_entry.pop(symbol, None)
        self._pending_tp.pop(symbol, None)
        self._pending_dir.pop(symbol, None)

    # ── EMA helpers ───────────────────────────────────────────────────────────

    def _init_ema_state(self, symbol: str):
        if symbol not in self._ema_bar_count:
            self._ema_fast[symbol] = None
            self._ema_slow[symbol] = None
            self._ema_fast_sum[symbol] = 0.0
            self._ema_slow_sum[symbol] = 0.0
            self._ema_bar_count[symbol] = 0

    def _update_ema(self, close: float, prev: float | None, count: int,
                    sma_sum: float, period: int) -> tuple[float | None, float]:
        sma_sum += close
        if count < period:
            return None, sma_sum
        if count == period:
            return sma_sum / period, sma_sum
        k = 2.0 / (period + 1)
        return close * k + prev * (1 - k), sma_sum

    def _ema_trend(self, symbol: str) -> str | None:
        """Return 'BUY', 'SELL', 'ANY' (disabled), or None (not ready)."""
        if not self.tf_trend or self.ema_fast == 0:
            return 'ANY'
        fast = self._ema_fast.get(symbol)
        slow = self._ema_slow.get(symbol)
        if fast is None or slow is None:
            return None
        if fast > slow:
            return 'BUY'
        if fast < slow:
            return 'SELL'
        return None

    def _on_trend_bar(self, symbol: str, bar: BarEvent):
        """Update EMA state from a trend-TF bar."""
        self._init_ema_state(symbol)
        self._ema_bar_count[symbol] += 1
        count = self._ema_bar_count[symbol]
        self._ema_fast[symbol], self._ema_fast_sum[symbol] = self._update_ema(
            bar.close, self._ema_fast[symbol], count, self._ema_fast_sum[symbol], self.ema_fast,
        )
        self._ema_slow[symbol], self._ema_slow_sum[symbol] = self._update_ema(
            bar.close, self._ema_slow[symbol], count, self._ema_slow_sum[symbol], self.ema_slow,
        )

    # ── Main signal generation ────────────────────────────────────────────────

    def generate_signal(self, event: BarEvent) -> Signal | None:
        symbol = event.symbol

        # Route trend-TF bars to EMA updater; don't generate entry signals from them
        if self.tf_trend and event.timeframe == self.tf_trend:
            self._on_trend_bar(symbol, event)
            return None

        # ── Entry TF logic ────────────────────────────────────────────────────
        if symbol not in self._prev_bar:
            self._prev_bar[symbol] = None
            self._signal_fired[symbol] = False
            self._pending_signal[symbol] = None
            self._init_ema_state(symbol)

        # Emit any deferred signal queued from a cancel+replace on the previous bar
        if self._pending_signal[symbol] is not None:
            sig = self._pending_signal[symbol]
            self._pending_signal[symbol] = None
            return sig

        # Cancel-if-TP-hit: while a pending is live, check if price reached the
        # TP level without ever retracing to fill the entry
        if self._signal_fired[symbol] and symbol in self._pending_entry:
            entry = self._pending_entry[symbol]
            tp    = self._pending_tp[symbol]
            dirn  = self._pending_dir[symbol]
            if dirn == 'BUY':
                tp_hit     = event.high >= tp
                not_filled = event.low > entry   # low stayed above entry — no fill
            else:
                tp_hit     = event.low <= tp
                not_filled = event.high < entry  # high stayed below entry — no fill
            if tp_hit and not_filled:
                self._signal_fired[symbol] = False
                self._pending_entry.pop(symbol, None)
                self._pending_tp.pop(symbol, None)
                self._pending_dir.pop(symbol, None)
                return Signal(
                    symbol=symbol, direction='CANCEL', order_type='PENDING',
                    entry_price=0.0, stop_loss=0.0,
                    strategy_name=self.NAME, timestamp=event.timestamp,
                )

        prev = self._prev_bar[symbol]
        self._prev_bar[symbol] = event

        if prev is None:
            return None

        bullish = event.low < prev.low and event.close > prev.open
        bearish = event.high > prev.high and event.close < prev.open

        if not bullish and not bearish:
            return None

        rng = event.high - event.low
        pip = self.pip_sizes.get(symbol, 0.0001)

        # Minimum bar size filter
        if self.min_range_pips > 0 and rng / pip < self.min_range_pips:
            return None

        if bullish:
            entry = event.high - self.entry_pct * rng
            sl    = prev.low
            if sl >= entry:          # SL must be below entry for a BUY
                return None
            direction = 'BUY'
            sl_dist   = entry - sl
            tp_price  = entry + self.tp_r * sl_dist
        else:
            entry = event.low + self.entry_pct * rng
            sl    = prev.high
            if sl <= entry:          # SL must be above entry for a SELL
                return None
            direction = 'SELL'
            sl_dist   = sl - entry
            tp_price  = entry - self.tp_r * sl_dist

        # Max SL filter
        if self.max_sl_pips > 0 and sl_dist / pip > self.max_sl_pips:
            return None

        # EMA trend filter
        trend = self._ema_trend(symbol)
        if trend is None:
            return None               # EMAs not warmed up yet
        if trend != 'ANY' and trend != direction:
            return None               # trade against trend — skip

        new_signal = Signal(
            symbol=symbol,
            direction=direction,
            order_type='PENDING',
            entry_price=entry,
            stop_loss=sl,
            strategy_name=self.NAME,
            timestamp=event.timestamp,
        )

        if self._signal_fired[symbol]:
            # New engulf while pending is live: cancel old, defer new to next bar
            self._pending_signal[symbol] = new_signal
            # Update pending details to the new setup
            self._pending_entry[symbol] = entry
            self._pending_tp[symbol]    = tp_price
            self._pending_dir[symbol]   = direction
            return Signal(
                symbol=symbol, direction='CANCEL', order_type='PENDING',
                entry_price=0.0, stop_loss=0.0,
                strategy_name=self.NAME, timestamp=event.timestamp,
            )

        self._signal_fired[symbol] = True
        self._pending_entry[symbol] = entry
        self._pending_tp[symbol]    = tp_price
        self._pending_dir[symbol]   = direction
        return new_signal
