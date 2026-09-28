from collections import deque
from datetime import datetime, timedelta, timezone
import json
import logging
import math

from models import BarEvent, Signal

logger = logging.getLogger(__name__)


class EmaFibRunningStrategy:
    """
    Multi-timeframe EMA + Fibonacci retracement with running swing extreme.

    Variant of EmaFibRetracement. Key differences:

    1. Running extreme: The anchor point (swing low for BUY, swing high for
       SELL) is a fractal. The other side is a running extreme — the highest
       close since the swing low (BUY) or lowest close since swing high (SELL).

    2. Body-based fib: The swing range is defined on candle bodies, not wicks.
       - BUY swing low = min(open, close) of the fractal candle (body low)
       - BUY running high = max(close) of all bars since the fractal low
       - Entry/TP calculated from this body range
       - SL still at the fractal wick (actual low)

    3. FVG filter: The swing must contain at least one Fair Value Gap to
       confirm impulsive price action (filters out choppy ranges).

    BUY setup:
      - Swing body low = min(open, close) of fractal low candle
      - Running close high = max(close) since fractal low
      - body_range = running_close_high - swing_body_low
      - Entry = running_close_high - 0.618 × body_range
      - SL = fractal low (wick)
      - TP = swing_body_low + 2.0 × body_range

    SELL setup:
      - Swing body high = max(open, close) of fractal high candle
      - Running close low = min(close) since fractal high
      - body_range = swing_body_high - running_close_low
      - Entry = running_close_low + 0.618 × body_range
      - SL = fractal high (wick)
      - TP = swing_body_high - 2.0 × body_range
    """

    TIMEFRAMES = ['D1', 'H1']
    ORDER_TYPE = 'PENDING'
    NAME = 'EmaFibRunning'

    def __init__(
        self,
        ema_fast: int = 10,
        ema_slow: int = 20,
        fractal_n: int = 3,
        fib_entry: float = 0.618,
        fib_tp: float = 2.0,
        use_fib_tp: bool = True,
        swing_max_age: int = 100,
        cooldown_bars: int = 10,
        min_swing_pips: float = 15.0,
        ema_sep_pct: float = 0.0005,
        invalidate_swing_on_loss: bool = True,
        blocked_hours: tuple[int, ...] = (16, 17, 18, 19, 20, 21, 22, 23),
        min_d1_atr_pips: float = 50.0,
        d1_atr_period: int = 14,
        pip_sizes: dict[str, float] | None = None,
    ):
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.fractal_n = fractal_n
        self.fib_entry = fib_entry
        self.fib_tp = fib_tp
        self.use_fib_tp = use_fib_tp
        self.swing_max_age = swing_max_age
        self.cooldown_bars = cooldown_bars
        self.min_swing_pips = min_swing_pips
        self.ema_sep_pct = ema_sep_pct
        self.invalidate_swing_on_loss = invalidate_swing_on_loss
        self.blocked_hours = set(blocked_hours)
        self.min_d1_atr_pips = min_d1_atr_pips
        self.d1_atr_period = d1_atr_period
        self.pip_sizes = pip_sizes or {
            'EURUSD': 0.0001, 'GBPUSD': 0.0001, 'AUDUSD': 0.0001,
            'NZDUSD': 0.0001, 'USDJPY': 0.01,   'USDCAD': 0.0001,
            'USDCHF': 0.0001,
            'XAUUSD': 0.10,
            # JPY crosses — must be explicit; fallback default is 0.0001 (wrong for JPY)
            'AUDJPY': 0.01, 'CADJPY': 0.01, 'EURJPY': 0.01,
            'GBPJPY': 0.01, 'NZDJPY': 0.01,
        }

        self._window_size = 2 * fractal_n + 1

        # Per-symbol state
        self._d1_ema_fast: dict[str, float | None] = {}
        self._d1_ema_slow: dict[str, float | None] = {}
        self._d1_bar_count: dict[str, int] = {}
        self._d1_sma_sum_fast: dict[str, float] = {}
        self._d1_sma_sum_slow: dict[str, float] = {}

        self._d1_prev_close: dict[str, float | None] = {}
        self._d1_tr_window: dict[str, deque] = {}
        self._d1_atr: dict[str, float | None] = {}

        self._h1_ema_fast: dict[str, float | None] = {}
        self._h1_ema_slow: dict[str, float | None] = {}
        self._h1_bar_count: dict[str, int] = {}
        self._h1_sma_sum_fast: dict[str, float] = {}
        self._h1_sma_sum_slow: dict[str, float] = {}

        self._h1_window: dict[str, deque] = {}
        self._h1_counter: dict[str, int] = {}

        # Fractal swings (anchor points)
        self._fractal_high: dict[str, float | None] = {}       # wick high
        self._fractal_low: dict[str, float | None] = {}        # wick low
        self._fractal_high_body: dict[str, float | None] = {}  # max(open, close)
        self._fractal_low_body: dict[str, float | None] = {}   # min(open, close)
        self._fractal_high_bar: dict[str, int] = {}
        self._fractal_low_bar: dict[str, int] = {}

        # Running extremes — highest/lowest CLOSE since anchor fractal
        self._running_high: dict[str, float | None] = {}
        self._running_low: dict[str, float | None] = {}

        # FVG tracking — has a bullish/bearish FVG occurred since the anchor fractal?
        self._fvg_since_fractal_low: dict[str, bool] = {}   # bullish FVG since fractal low
        self._fvg_since_fractal_high: dict[str, bool] = {}  # bearish FVG since fractal high
        self._h1_recent: dict[str, deque] = {}  # last 3 bars for FVG detection

        self._pending_entry: dict[str, float | None] = {}
        self._pending_direction: dict[str, str | None] = {}
        # Diagnostic pending view. Immutable accepted anchors live in _orders.
        self._pending_anchor_low: dict[str, float | None] = {}
        self._pending_anchor_high: dict[str, float | None] = {}

        # Filter state
        self._cooldown_until: dict[str, int] = {}
        self._used_fractal_high: dict[str, float | None] = {}
        self._used_fractal_low: dict[str, float | None] = {}
        self._orders = {}
        self._proposals = {}
        self._finished_orders = set()
        self._processed_closes = set()
        self._cancelled_order_ids = set()
        self._fractal_high_time = {}
        self._fractal_low_time = {}
        self._h1_close_times = {}
        self._last_loss_time = {}

    def reset(self):
        """Clear all internal state."""
        for attr in vars(self):
            val = getattr(self, attr)
            if isinstance(val, (dict, set)) and attr.startswith('_'):
                val.clear()

    def generate_signal(self, event: BarEvent) -> Signal | None:
        symbol = event.symbol
        self._init_symbol(symbol)

        if event.timeframe == 'D1':
            self._update_d1(symbol, event)
            return None

        if event.timeframe == 'H1':
            return self._process_h1(symbol, event)

        return None

    # ── Initialisation ───────────────────────────────────────────────────────

    def _init_symbol(self, symbol: str):
        if symbol in self._d1_bar_count:
            return
        self._d1_ema_fast[symbol] = None
        self._d1_ema_slow[symbol] = None
        self._d1_bar_count[symbol] = 0
        self._d1_sma_sum_fast[symbol] = 0.0
        self._d1_sma_sum_slow[symbol] = 0.0

        self._d1_prev_close[symbol] = None
        self._d1_tr_window[symbol] = deque(maxlen=self.d1_atr_period)
        self._d1_atr[symbol] = None

        self._h1_ema_fast[symbol] = None
        self._h1_ema_slow[symbol] = None
        self._h1_bar_count[symbol] = 0
        self._h1_sma_sum_fast[symbol] = 0.0
        self._h1_sma_sum_slow[symbol] = 0.0

        self._h1_window[symbol] = deque(maxlen=self._window_size)
        self._h1_counter[symbol] = 0

        self._fractal_high[symbol] = None
        self._fractal_low[symbol] = None
        self._fractal_high_body[symbol] = None
        self._fractal_low_body[symbol] = None
        self._fractal_high_bar[symbol] = 0
        self._fractal_low_bar[symbol] = 0

        self._running_high[symbol] = None
        self._running_low[symbol] = None

        self._fvg_since_fractal_low[symbol] = False
        self._fvg_since_fractal_high[symbol] = False
        self._h1_recent[symbol] = deque(maxlen=3)

        self._pending_entry[symbol] = None
        self._pending_direction[symbol] = None
        self._pending_anchor_low[symbol] = None
        self._pending_anchor_high[symbol] = None

        self._cooldown_until[symbol] = 0
        self._used_fractal_high[symbol] = None
        self._used_fractal_low[symbol] = None
        self._fractal_high_time[symbol] = None
        self._fractal_low_time[symbol] = None
        self._h1_close_times[symbol] = deque(maxlen=max(1, self.cooldown_bars + 1))

    # ── EMA helpers ──────────────────────────────────────────────────────────

    def _update_ema(self, close: float, prev_ema: float | None, bar_count: int,
                    sma_sum: float, period: int) -> tuple[float | None, float]:
        sma_sum += close
        if bar_count < period:
            return None, sma_sum
        if bar_count == period:
            return sma_sum / period, sma_sum
        k = 2.0 / (period + 1)
        return close * k + prev_ema * (1 - k), sma_sum

    # ── D1 processing ────────────────────────────────────────────────────────

    def _update_d1(self, symbol: str, event: BarEvent):
        self._d1_bar_count[symbol] += 1
        count = self._d1_bar_count[symbol]

        fast, self._d1_sma_sum_fast[symbol] = self._update_ema(
            event.close, self._d1_ema_fast[symbol], count,
            self._d1_sma_sum_fast[symbol], self.ema_fast,
        )
        slow, self._d1_sma_sum_slow[symbol] = self._update_ema(
            event.close, self._d1_ema_slow[symbol], count,
            self._d1_sma_sum_slow[symbol], self.ema_slow,
        )
        self._d1_ema_fast[symbol] = fast
        self._d1_ema_slow[symbol] = slow

        # D1 ATR
        prev = self._d1_prev_close[symbol]
        if prev is not None:
            tr = max(event.high - event.low,
                     abs(event.high - prev),
                     abs(event.low - prev))
        else:
            tr = event.high - event.low
        self._d1_prev_close[symbol] = event.close

        window = self._d1_tr_window[symbol]
        window.append(tr)
        if len(window) == self.d1_atr_period:
            self._d1_atr[symbol] = sum(window) / self.d1_atr_period

    # ── H1 processing ────────────────────────────────────────────────────────

    def _process_h1(self, symbol: str, event: BarEvent) -> Signal | None:
        # Update H1 EMAs
        self._h1_bar_count[symbol] += 1
        count = self._h1_bar_count[symbol]

        fast, self._h1_sma_sum_fast[symbol] = self._update_ema(
            event.close, self._h1_ema_fast[symbol], count,
            self._h1_sma_sum_fast[symbol], self.ema_fast,
        )
        slow, self._h1_sma_sum_slow[symbol] = self._update_ema(
            event.close, self._h1_ema_slow[symbol], count,
            self._h1_sma_sum_slow[symbol], self.ema_slow,
        )
        self._h1_ema_fast[symbol] = fast
        self._h1_ema_slow[symbol] = slow

        # Increment H1 bar counter
        self._h1_counter[symbol] += 1
        bar_idx = self._h1_counter[symbol]
        self._h1_close_times[symbol].append(self._utc(event.timestamp) + timedelta(hours=1))

        # Append to fractal window and detect fractal swings
        self._h1_window[symbol].append(event)
        self._detect_fractals(symbol)

        # Update running extremes
        self._update_running_extremes(symbol, event)

        # Determine bias
        d1_bias = self._get_bias(self._d1_ema_fast[symbol], self._d1_ema_slow[symbol])
        h1_bias = self._get_bias(self._h1_ema_fast[symbol], self._h1_ema_slow[symbol])

        active = [o for o in self._orders.values() if o['symbol'] == symbol]
        for order in active:
            if order['state'] != 'PENDING' and not order.get('has_pending'):
                continue
            self._show_pending(symbol, order)
            pending = self._pending_entry[symbol]
            # Cancel if EITHER D1 or H1 bias flipped against the pending
            # direction. Entry required both to agree, so either disagreeing
            # invalidates the setup.
            pending_dir = self._pending_direction[symbol]
            h1_flipped = h1_bias is not None and h1_bias != pending_dir
            d1_flipped = d1_bias is not None and d1_bias != pending_dir
            if h1_flipped or d1_flipped:
                return self._cancel_signal(symbol, event, order)

            # Check if running extreme changed → update pending order
            new_entry, new_sl, new_tp = self._calc_entry(symbol, pending_dir)
            if new_entry is not None and pending is not None and abs(new_entry - pending) > self._pip_size(symbol):
                # Cancel old, will re-place with updated levels on next bar
                return self._cancel_signal(symbol, event, order)

        if active:
            return None  # Accepted pending or filled exposure owns the slot.

        # ── Filters ────────────────────────────────────────────────────────────
        if bar_idx < self._cooldown_until[symbol]:
            return None

        if self.blocked_hours and event.timestamp.hour in self.blocked_hours:
            return None

        if self.min_d1_atr_pips > 0:
            d1_atr = self._d1_atr.get(symbol)
            if d1_atr is None:
                return None
            if d1_atr / self._pip_size(symbol) < self.min_d1_atr_pips:
                return None

        if d1_bias is None or h1_bias is None:
            return None

        if d1_bias != h1_bias:
            return None

        if self.ema_sep_pct > 0:
            h1_fast_val = self._h1_ema_fast[symbol]
            h1_slow_val = self._h1_ema_slow[symbol]
            if abs(h1_fast_val - h1_slow_val) / h1_slow_val < self.ema_sep_pct:
                return None

        direction = d1_bias

        # Get the anchor fractal and running extreme
        entry_price, stop_loss, take_profit = self._calc_entry(symbol, direction)
        if entry_price is None:
            return None

        # FVG filter: require at least one FVG since the anchor fractal
        if direction == 'BUY' and not self._fvg_since_fractal_low[symbol]:
            return None
        if direction == 'SELL' and not self._fvg_since_fractal_high[symbol]:
            return None

        # Check swing age (anchor fractal age)
        if direction == 'BUY':
            anchor_age = bar_idx - self._fractal_low_bar[symbol]
            anchor_val = self._fractal_low[symbol]
        else:
            anchor_age = bar_idx - self._fractal_high_bar[symbol]
            anchor_val = self._fractal_high[symbol]

        if anchor_age > self.swing_max_age:
            return None

        # Invalidate after loss
        if self.invalidate_swing_on_loss:
            if direction == 'BUY':
                if anchor_val == self._used_fractal_low[symbol]:
                    return None
            else:
                if anchor_val == self._used_fractal_high[symbol]:
                    return None

        # SL distance check
        pip = self._pip_size(symbol)
        sl_pips = abs(entry_price - stop_loss) / pip
        if sl_pips < self.min_swing_pips:
            return None

        # A proposal owns no broker slot until execution accepts it. Keep the
        # anchor recoverable in the setup ledger even without a checkpoint.
        body = self._fractal_low_body[symbol] if direction == 'BUY' else self._fractal_high_body[symbol]
        anchor_time = self._fractal_low_time[symbol] if direction == 'BUY' else self._fractal_high_time[symbol]
        setup = self.NAME + '|v1|' + json.dumps(
            [symbol, direction, anchor_val, body, str(anchor_time)], separators=(',', ':'))
        attempt = setup + '|' + self._utc(event.timestamp).isoformat()
        self._proposals[attempt] = dict(symbol=symbol, anchor=anchor_val)

        return Signal(
            symbol=symbol,
            direction=direction,
            order_type=self.ORDER_TYPE,
            entry_price=entry_price,
            stop_loss=stop_loss,
            strategy_name=self.NAME,
            timestamp=event.timestamp,
            take_profit=take_profit if self.use_fib_tp else None,
            setup_id=setup,
            attempt_id=attempt,
        )

    # ── Entry calculation ────────────────────────────────────────────────────

    def _calc_entry(self, symbol: str, direction: str) -> tuple[float | None, float, float]:
        """Calculate entry, SL, TP from body-based swing range.
        SL is at the fractal wick. Entry/TP from body range.
        Returns (entry, sl, tp) or (None, 0, 0) if invalid."""
        if direction == 'BUY':
            body_low = self._fractal_low_body[symbol]   # min(open, close) of fractal candle
            body_high = self._running_high[symbol]      # highest close since fractal low
            wick_low = self._fractal_low[symbol]         # actual fractal low (SL)
            if body_low is None or body_high is None or wick_low is None:
                return None, 0.0, 0.0
            if body_high <= body_low:
                return None, 0.0, 0.0
            body_range = body_high - body_low
            entry = body_high - self.fib_entry * body_range
            sl = wick_low
            tp = body_low + self.fib_tp * body_range
        else:
            body_high = self._fractal_high_body[symbol]  # max(open, close) of fractal candle
            body_low = self._running_low[symbol]         # lowest close since fractal high
            wick_high = self._fractal_high[symbol]       # actual fractal high (SL)
            if body_high is None or body_low is None or wick_high is None:
                return None, 0.0, 0.0
            if body_high <= body_low:
                return None, 0.0, 0.0
            body_range = body_high - body_low
            entry = body_low + self.fib_entry * body_range
            sl = wick_high
            tp = body_high - self.fib_tp * body_range

        return entry, sl, tp

    # ── Running extreme tracking ─────────────────────────────────────────────

    def _update_running_extremes(self, symbol: str, event: BarEvent):
        """Update the running close high/low and detect FVGs."""
        # Running high: highest CLOSE since the fractal low was set
        if self._fractal_low[symbol] is not None:
            if (self._running_high[symbol] is None
                    or event.close > self._running_high[symbol]):
                self._running_high[symbol] = event.close

        # Running low: lowest CLOSE since the fractal high was set
        if self._fractal_high[symbol] is not None:
            if (self._running_low[symbol] is None
                    or event.close < self._running_low[symbol]):
                self._running_low[symbol] = event.close

        # FVG detection on last 3 bars
        recent = self._h1_recent[symbol]
        recent.append(event)
        if len(recent) < 3:
            return

        bar0, bar1, bar2 = recent[0], recent[1], recent[2]

        # Bullish FVG: bar2 low > bar0 high (gap up, bar1 bridges)
        if bar2.low > bar0.high:
            self._fvg_since_fractal_low[symbol] = True

        # Bearish FVG: bar2 high < bar0 low (gap down, bar1 bridges)
        if bar2.high < bar0.low:
            self._fvg_since_fractal_high[symbol] = True

    # ── Fractal detection ────────────────────────────────────────────────────

    def _initial_running_extreme(self, window, direction):
        """Include completed closes from the anchor through its confirmation."""
        closes = [bar.close for bar in list(window)[self.fractal_n:]]
        return max(closes) if direction == 'BUY' else min(closes)

    def _detect_fractals(self, symbol: str):
        window = self._h1_window[symbol]
        if len(window) < self._window_size:
            return

        mid = self.fractal_n
        mid_bar = window[mid]

        # Check fractal high
        is_fractal_high = all(
            mid_bar.high > window[i].high
            for i in range(self._window_size)
            if i != mid
        )
        if is_fractal_high:
            self._fractal_high[symbol] = mid_bar.high
            self._fractal_high_body[symbol] = max(mid_bar.open, mid_bar.close)
            self._fractal_high_bar[symbol] = self._h1_counter[symbol] - self.fractal_n
            self._fractal_high_time[symbol] = self._utc(mid_bar.timestamp)
            # Reset running low and bearish FVG flag
            self._running_low[symbol] = self._initial_running_extreme(window, 'SELL')
            self._fvg_since_fractal_high[symbol] = False

        # Check fractal low
        is_fractal_low = all(
            mid_bar.low < window[i].low
            for i in range(self._window_size)
            if i != mid
        )
        if is_fractal_low:
            self._fractal_low[symbol] = mid_bar.low
            self._fractal_low_body[symbol] = min(mid_bar.open, mid_bar.close)
            self._fractal_low_bar[symbol] = self._h1_counter[symbol] - self.fractal_n
            self._fractal_low_time[symbol] = self._utc(mid_bar.timestamp)
            # Reset running high and bullish FVG flag
            self._running_high[symbol] = self._initial_running_extreme(window, 'BUY')
            self._fvg_since_fractal_low[symbol] = False

    # ── Post-trade feedback ──────────────────────────────────────────────────

    def notify_loss(self, symbol: str):
        """Symbol-only feedback cannot identify the accepted trade."""
        logger.warning('Running loss needs order attribution: %s', symbol)

    def notify_win(self, symbol: str):
        """Confirmed outcomes must include order identity."""
        logger.warning('Running win needs order attribution: %s', symbol)

    def _clear_pending_state(self, symbol: str):
        """Clear the diagnostic view; accepted anchors live in _orders."""
        self._pending_entry[symbol] = None
        self._pending_direction[symbol] = None
        self._pending_anchor_low[symbol] = None
        self._pending_anchor_high[symbol] = None

    @staticmethod
    def _utc(value):
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value

    def _origin_anchor(self, order):
        setup = order.get('setup_id') or ''
        prefix = self.NAME + '|v1|'
        if not setup.startswith(prefix):
            return None
        try:
            symbol, direction, wick, body, _ = json.loads(setup[len(prefix):])
            if (symbol == order['symbol'] and direction == order.get('direction')
                    and direction in ('BUY', 'SELL')
                    and all(math.isfinite(p) and p > 0 for p in (wick, body))
                    and (wick <= body if direction == 'BUY' else wick >= body)):
                return wick
        except (TypeError, ValueError):
            pass
        return None

    @staticmethod
    def _order_key(order):
        origin = order.get('origin_order_ticket') or order.get('position_id') or order.get('ticket')
        return order.get('attempt_id') or (f'legacy|{origin}' if origin else None)

    @staticmethod
    def _identities(order):
        return {(order['symbol'], str(order[k])) for k in
                ('ticket', 'origin_order_ticket', 'position_id') if order.get(k)}

    def _find_order(self, order):
        key = self._order_key(order)
        if key in self._orders:
            return key, self._orders[key]
        ids = self._identities(order)
        for existing, record in self._orders.items():
            if ids & self._identities(record):
                return existing, record
        return key, None

    def _show_pending(self, symbol, order):
        self._pending_entry[symbol] = order.get('entry_price', order.get('open_price'))
        self._pending_direction[symbol] = order['direction']
        self._pending_anchor_low[symbol] = order.get('anchor') if order['direction'] == 'BUY' else None
        self._pending_anchor_high[symbol] = order.get('anchor') if order['direction'] == 'SELL' else None

    def _refresh_pending(self, symbol):
        self._clear_pending_state(symbol)
        for order in self._orders.values():
            if order['symbol'] == symbol and (order['state'] == 'PENDING' or order.get('has_pending')):
                self._show_pending(symbol, order)
                break

    def notify_order_accepted(self, signal, ticket, details=None):
        proposal = self._proposals.pop(signal.attempt_id, {})
        self.sync_order_state(dict(symbol=signal.symbol, direction=signal.direction,
            setup_id=signal.setup_id, attempt_id=signal.attempt_id, ticket=ticket,
            origin_order_ticket=ticket, state='PENDING', entry_price=signal.entry_price,
            anchor=proposal.get('anchor')))

    def sync_order_state(self, order):
        symbol = order['symbol']
        self._init_symbol(symbol)
        key, record = self._find_order(order)
        ids = self._identities(order)
        state = order.get('state') or ('OPEN' if order.get('open_time') is not None else 'PENDING')
        if key is None or key in self._processed_closes or ids & self._processed_closes:
            return
        # Removing a remainder can race with a partial fill. A confirmed OPEN
        # snapshot must still be adopted after cancellation; stale pending
        # snapshots stay blocked. A final close blocks both states above.
        if state != 'OPEN' and (key in self._finished_orders or ids & self._cancelled_order_ids):
            return
        canonical = self._order_key(order)
        if order.get('attempt_id') and canonical != key:
            self._orders.pop(key, None)
            key = canonical
        record = record if record is not None else {}
        was_open = record.get('state') == 'OPEN'
        record.update({k: order[k] for k in ('symbol', 'direction', 'setup_id', 'attempt_id', 'ticket',
            'origin_order_ticket', 'position_id', 'entry_price', 'open_price') if order.get(k) is not None})
        record['state'] = 'OPEN' if was_open or state == 'OPEN' else 'PENDING'
        record['has_pending'] = order.get('has_pending', state == 'PENDING')
        if record.get('anchor') is None:
            record['anchor'] = order.get('anchor') or self._origin_anchor(record)
        self._orders[key] = record
        self._refresh_pending(symbol)

    def notify_proposal_rejected(self, signal):
        attempt = getattr(signal, 'attempt_id', None)
        if attempt in self._proposals:
            self._proposals.pop(attempt)
        elif getattr(signal, 'ticket', None):
            self.notify_order_cancelled(vars(signal))

    def notify_order_cancelled(self, order):
        key, record = self._find_order(order)
        if record is not None and record['state'] == 'OPEN':
            record['has_pending'] = False  # Cancelling a remainder does not close its filled part.
        else:
            if key:
                self._orders.pop(key, None)
                self._finished_orders.add(key)
            self._cancelled_order_ids.update(self._identities(order))
            if record:
                self._cancelled_order_ids.update(self._identities(record))
        self._refresh_pending(order['symbol'])

    def notify_trade_closed(self, trade):
        if trade.get('is_final') is False or trade.get('remaining_volume', 0) > 0:
            return
        symbol = trade['symbol']
        self._init_symbol(symbol)
        key, record = self._find_order(trade)
        ids = self._identities(trade) | (self._identities(record) if record else set())
        if key is None or key in self._processed_closes or ids & self._processed_closes:
            return
        self._processed_closes.add(key)
        self._processed_closes.update(ids)
        self._finished_orders.add(key)
        self._orders.pop(key, None)
        self._refresh_pending(symbol)
        if trade.get('result') != 'LOSS':
            return
        direction = record['direction'] if record else trade.get('direction')
        closed = self._utc(trade['close_time']) if trade.get('close_time') else None
        previous = self._last_loss_time.get((symbol, direction))
        if closed is not None and previous is not None and closed < previous:
            return
        if closed is not None:
            self._last_loss_time[(symbol, direction)] = closed
        elapsed = sum(t > closed for t in self._h1_close_times[symbol]) if closed else 0
        self._cooldown_until[symbol] = max(self._cooldown_until[symbol],
            self._h1_counter[symbol] + max(0, self.cooldown_bars - elapsed))
        anchor = record.get('anchor') if record else self._origin_anchor(trade)
        if self.invalidate_swing_on_loss and anchor is not None:
            used = self._used_fractal_low if direction == 'BUY' else self._used_fractal_high
            used[symbol] = anchor
        elif self.invalidate_swing_on_loss:
            logger.warning('Running legacy close has no originating anchor: %s ticket=%s', symbol, trade.get('ticket'))

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _cancel_signal(self, symbol: str, event: BarEvent, order: dict) -> Signal:
        return Signal(
            symbol=symbol, direction='CANCEL', order_type=self.ORDER_TYPE,
            entry_price=0.0, stop_loss=0.0,
            strategy_name=self.NAME, timestamp=event.timestamp,
            setup_id=order.get('setup_id'), attempt_id=order.get('attempt_id'),
        )

    def _pip_size(self, symbol: str) -> float:
        return self.pip_sizes.get(symbol, 0.0001)

    @staticmethod
    def _get_bias(ema_fast: float | None, ema_slow: float | None) -> str | None:
        if ema_fast is None or ema_slow is None:
            return None
        return 'BUY' if ema_fast > ema_slow else 'SELL'

    def get_status(self, symbol: str) -> dict:
        d1_bias = self._get_bias(self._d1_ema_fast.get(symbol), self._d1_ema_slow.get(symbol))
        h1_bias = self._get_bias(self._h1_ema_fast.get(symbol), self._h1_ema_slow.get(symbol))

        h1_fast = self._h1_ema_fast.get(symbol)
        h1_slow = self._h1_ema_slow.get(symbol)
        ema_sep = abs(h1_fast - h1_slow) / h1_slow if (h1_fast and h1_slow) else 0.0

        d1_atr = self._d1_atr.get(symbol)
        atr_pips = d1_atr / self._pip_size(symbol) if d1_atr else 0.0

        pip = self._pip_size(symbol)
        frac_h = self._fractal_high.get(symbol)
        frac_l = self._fractal_low.get(symbol)
        run_h = self._running_high.get(symbol)
        run_l = self._running_low.get(symbol)

        bar_idx = self._h1_counter.get(symbol, 0)
        pending = self._pending_direction.get(symbol)
        price = self._pending_entry.get(symbol)
        blocker = (f'PENDING {pending} @ {price:.5f}' if price is not None else f'PENDING {pending}') if pending else (
            'OPEN POSITION' if any(o['symbol'] == symbol for o in self._orders.values()) else 'READY')

        return {
            'd1_bias': d1_bias,
            'h1_bias': h1_bias,
            'ema_sep': f'{ema_sep:.5f}',
            'atr_pips': f'{atr_pips:.0f}',
            'fractal_high': frac_h,
            'fractal_low': frac_l,
            'running_high_close': run_h,
            'running_low_close': run_l,
            'fvg_bull': self._fvg_since_fractal_low.get(symbol, False),
            'fvg_bear': self._fvg_since_fractal_high.get(symbol, False),
            'blocker': blocker,
        }

    def notify_signal_rejected(self, symbol: str):
        """Legacy callback: release proposals without clearing accepted exposure."""
        for attempt, proposal in list(self._proposals.items()):
            if proposal['symbol'] == symbol:
                self._proposals.pop(attempt)
