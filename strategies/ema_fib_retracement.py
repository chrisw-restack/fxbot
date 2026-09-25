from collections import deque
from datetime import datetime, timedelta, timezone
import json
import logging
import math

from models import BarEvent, Signal

logger = logging.getLogger(__name__)


class EmaFibRetracementStrategy:
    """
    Multi-timeframe EMA + Fibonacci retracement strategy.

    D1 + H1 EMA bias must agree (10 EMA vs 20 EMA). When aligned, places
    PENDING orders at a configured Fibonacci retracement of the latest H1
    swings. Execution callbacks own order state; candle touches do not imply fills.
    """

    TIMEFRAMES = ['D1', 'H1']
    ORDER_TYPE = 'PENDING'
    NAME = 'EmaFibRetracement'

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
        require_recent_swing_alignment: bool = False,
        pending_max_age_bars: int = 0,
        cancel_if_virtual_tp_hit: bool = False,
        pending_cancel_at_r: float | None = None,
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
        self.require_recent_swing_alignment = require_recent_swing_alignment
        self.pending_max_age_bars = pending_max_age_bars
        self.cancel_if_virtual_tp_hit = cancel_if_virtual_tp_hit
        self.pending_cancel_at_r = pending_cancel_at_r
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

        self._swing_high: dict[str, float | None] = {}
        self._swing_low: dict[str, float | None] = {}
        self._swing_high_bar: dict[str, int] = {}
        self._swing_low_bar: dict[str, int] = {}

        self._pending_entry: dict[str, float | None] = {}
        self._pending_direction: dict[str, str | None] = {}
        # Diagnostic view of the pending order. Its permanent origin is in _orders.
        self._pending_swing_high: dict[str, float | None] = {}
        self._pending_swing_low: dict[str, float | None] = {}
        # H1 bar index at which the pending was placed — used for max-age check.
        self._pending_placed_bar: dict[str, int | None] = {}

        # Filter state
        self._cooldown_until: dict[str, int] = {}
        self._used_swing_high: dict[str, float | None] = {}
        self._used_swing_low: dict[str, float | None] = {}
        self._orders = {}
        self._proposals = {}
        self._finished_orders = set()
        self._processed_closes = set()
        self._swing_high_time = {}
        self._swing_low_time = {}
        self._h1_close_times = {}
        self._last_loss_time = {}

    def reset(self):
        """Clear all internal state."""
        self._d1_ema_fast.clear()
        self._d1_ema_slow.clear()
        self._d1_bar_count.clear()
        self._d1_sma_sum_fast.clear()
        self._d1_sma_sum_slow.clear()

        self._d1_prev_close.clear()
        self._d1_tr_window.clear()
        self._d1_atr.clear()

        self._h1_ema_fast.clear()
        self._h1_ema_slow.clear()
        self._h1_bar_count.clear()
        self._h1_sma_sum_fast.clear()
        self._h1_sma_sum_slow.clear()

        self._h1_window.clear()
        self._h1_counter.clear()

        self._swing_high.clear()
        self._swing_low.clear()
        self._swing_high_bar.clear()
        self._swing_low_bar.clear()

        self._pending_entry.clear()
        self._pending_direction.clear()
        self._pending_swing_high.clear()
        self._pending_swing_low.clear()
        self._pending_placed_bar.clear()

        self._cooldown_until.clear()
        self._used_swing_high.clear()
        self._used_swing_low.clear()
        self._orders.clear()
        self._proposals.clear()
        self._finished_orders.clear()
        self._processed_closes.clear()
        self._swing_high_time.clear()
        self._swing_low_time.clear()
        self._h1_close_times.clear()
        self._last_loss_time.clear()

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

        self._swing_high[symbol] = None
        self._swing_low[symbol] = None
        self._swing_high_bar[symbol] = 0
        self._swing_low_bar[symbol] = 0

        self._pending_entry[symbol] = None
        self._pending_direction[symbol] = None
        self._pending_swing_high[symbol] = None
        self._pending_swing_low[symbol] = None
        self._pending_placed_bar[symbol] = None

        self._cooldown_until[symbol] = 0
        self._used_swing_high[symbol] = None
        self._used_swing_low[symbol] = None
        self._swing_high_time[symbol] = None
        self._swing_low_time[symbol] = None
        self._h1_close_times[symbol] = deque(maxlen=max(1, self.cooldown_bars + 1))

    # ── EMA helpers ──────────────────────────────────────────────────────────

    def _update_ema(self, close: float, prev_ema: float | None, bar_count: int,
                    sma_sum: float, period: int) -> tuple[float | None, float]:
        """
        Returns (ema_value_or_None, updated_sma_sum).
        SMA-seeds for the first `period` bars, then switches to recursive EMA.
        """
        sma_sum += close
        if bar_count < period:
            return None, sma_sum
        if bar_count == period:
            return sma_sum / period, sma_sum
        k = 2.0 / (period + 1)
        return close * k + prev_ema * (1 - k), sma_sum

    def _pending_levels(self, symbol: str) -> tuple[float, float, float] | None:
        swing_high = self._pending_swing_high.get(symbol)
        swing_low = self._pending_swing_low.get(symbol)
        direction = self._pending_direction.get(symbol)
        if swing_high is None or swing_low is None or direction is None:
            return None
        if swing_high <= swing_low:
            return None

        swing_range = swing_high - swing_low
        if direction == 'BUY':
            entry = swing_high - self.fib_entry * swing_range
            stop_loss = swing_low
            take_profit = swing_low + self.fib_tp * swing_range
        else:
            entry = swing_low + self.fib_entry * swing_range
            stop_loss = swing_high
            take_profit = swing_high - self.fib_tp * swing_range
        return entry, stop_loss, take_profit

    def _pending_stale_by_price(self, symbol: str, event: BarEvent) -> bool:
        levels = self._pending_levels(symbol)
        if levels is None:
            return False

        entry, stop_loss, take_profit = levels
        direction = self._pending_direction[symbol]
        risk = abs(entry - stop_loss)
        if risk <= 0:
            return False

        if direction == 'BUY':
            if self.cancel_if_virtual_tp_hit and event.high >= take_profit:
                return True
            if self.pending_cancel_at_r is not None:
                return event.high >= entry + self.pending_cancel_at_r * risk
        else:
            if self.cancel_if_virtual_tp_hit and event.low <= take_profit:
                return True
            if self.pending_cancel_at_r is not None:
                return event.low <= entry - self.pending_cancel_at_r * risk

        return False

    def _clear_pending(self, symbol: str):
        self._pending_entry[symbol] = None
        self._pending_direction[symbol] = None
        self._pending_swing_high[symbol] = None
        self._pending_swing_low[symbol] = None
        self._pending_placed_bar[symbol] = None

    def _cancel_signal(self, symbol: str, event: BarEvent, order: dict) -> Signal:
        return Signal(
            symbol=symbol,
            direction='CANCEL',
            order_type=self.ORDER_TYPE,
            entry_price=0.0,
            stop_loss=0.0,
            strategy_name=self.NAME,
            timestamp=event.timestamp,
            setup_id=order.get('setup_id'),
            attempt_id=order.get('attempt_id'),
        )

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

        # Append to fractal window and check for new swings
        self._h1_window[symbol].append(event)
        self._detect_swings(symbol)

        active = [o for o in self._orders.values() if o['symbol'] == symbol]
        for order in active:
            if order['state'] != 'PENDING' and not order.get('has_pending'):
                continue
            self._show_pending(symbol, order)
            # Retain accepted state until execution confirms cancellation.
            h1_bias = self._get_bias(self._h1_ema_fast[symbol], self._h1_ema_slow[symbol])
            d1_bias = self._get_bias(self._d1_ema_fast[symbol], self._d1_ema_slow[symbol])
            pending_dir = self._pending_direction[symbol]
            h1_flipped = h1_bias is not None and h1_bias != pending_dir
            d1_flipped = d1_bias is not None and d1_bias != pending_dir

            placed_bar = self._pending_placed_bar[symbol]
            aged_out = (
                self.pending_max_age_bars > 0
                and placed_bar is not None
                and (bar_idx - placed_bar) >= self.pending_max_age_bars
            )
            price_stale = self._pending_stale_by_price(symbol, event)

            if h1_flipped or d1_flipped or aged_out or price_stale:
                return self._cancel_signal(symbol, event, order)
        if active:
            return None  # Pending or filled exposure owns this symbol's slot.

        # ── Filter 1: Cooldown after stop-out ────────────────────────────────
        if bar_idx < self._cooldown_until[symbol]:
            return None

        # ── Filter 5: Session filter ────────────────────────────────────────
        if self.blocked_hours and event.timestamp.hour in self.blocked_hours:
            return None

        # ── Filter 6: D1 ATR minimum ────────────────────────────────────────
        if self.min_d1_atr_pips > 0:
            d1_atr = self._d1_atr.get(symbol)
            if d1_atr is None:
                return None
            atr_pips = d1_atr / self._pip_size(symbol)
            if atr_pips < self.min_d1_atr_pips:
                return None

        # Need both D1 and H1 EMAs to be seeded
        d1_bias = self._get_bias(self._d1_ema_fast[symbol], self._d1_ema_slow[symbol])
        h1_bias = self._get_bias(self._h1_ema_fast[symbol], self._h1_ema_slow[symbol])

        if d1_bias is None or h1_bias is None:
            return None

        # Biases must agree
        if d1_bias != h1_bias:
            return None

        # ── Filter 4: EMA separation / trend strength ────────────────────────
        if self.ema_sep_pct > 0:
            h1_fast_val = self._h1_ema_fast[symbol]
            h1_slow_val = self._h1_ema_slow[symbol]
            separation = abs(h1_fast_val - h1_slow_val) / h1_slow_val
            if separation < self.ema_sep_pct:
                return None

        # Need valid swings
        swing_high = self._swing_high[symbol]
        swing_low = self._swing_low[symbol]
        if swing_high is None or swing_low is None:
            return None

        # Check swing age
        high_age = bar_idx - self._swing_high_bar[symbol]
        low_age = bar_idx - self._swing_low_bar[symbol]
        if high_age > self.swing_max_age or low_age > self.swing_max_age:
            return None

        # ── Filter 2: Invalidate swing after loss ────────────────────────────
        if self.invalidate_swing_on_loss:
            if (swing_high == self._used_swing_high[symbol]
                    and swing_low == self._used_swing_low[symbol]):
                return None

        # Swing must make sense (high > low)
        if swing_high <= swing_low:
            return None

        # ── Filter 7: Recent swing direction alignment ──────────────────────
        # For a BUY (uptrend retracement) we want the most recent swing point
        # to be a HIGH — i.e. price made a high and is pulling back into our
        # entry. For a SELL we want the most recent swing to be a LOW.
        # Without this, a stale opposing swing can produce a "retracement"
        # entry against the actual recent move.
        if self.require_recent_swing_alignment:
            high_bar = self._swing_high_bar[symbol]
            low_bar = self._swing_low_bar[symbol]
            if d1_bias == 'BUY' and low_bar > high_bar:
                return None
            if d1_bias == 'SELL' and high_bar > low_bar:
                return None

        swing_range = swing_high - swing_low

        # ── Filter 3: Minimum swing range ────────────────────────────────────
        if self.min_swing_pips > 0:
            swing_pips = swing_range / self._pip_size(symbol)
            if swing_pips < self.min_swing_pips:
                return None

        direction = d1_bias

        if direction == 'BUY':
            entry_price = swing_high - self.fib_entry * swing_range
            stop_loss = swing_low
            take_profit = swing_low + self.fib_tp * swing_range
        else:
            entry_price = swing_low + self.fib_entry * swing_range
            stop_loss = swing_high
            take_profit = swing_high - self.fib_tp * swing_range

        # Persist recoverable origin prices in the identity. Bar times distinguish
        # later swings at identical prices; loss invalidation retains its existing
        # price-pair rule. An unaccepted proposal never owns the order slot.
        setup = self.NAME + '|v1|' + json.dumps([
            symbol, swing_high, swing_low,
            str(self._swing_high_time[symbol]), str(self._swing_low_time[symbol]),
        ], separators=(',', ':'))
        attempt = setup + '|' + self._utc(event.timestamp).isoformat()
        self._proposals[attempt] = dict(symbol=symbol, swing=(swing_high, swing_low), placed_bar=bar_idx)
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

    # ── Post-trade feedback ──────────────────────────────────────────────────

    def notify_loss(self, symbol: str):
        """Compatibility only: symbol-only feedback cannot identify an order."""
        logger.warning('EmaFib loss needs ticket/setup attribution: %s', symbol)

    def notify_win(self, symbol: str):
        """Compatibility only; confirmed closes must include order identity."""
        logger.warning('EmaFib win needs ticket/setup attribution: %s', symbol)

    @staticmethod
    def _utc(value):
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value

    def _origin_swing(self, order):
        setup = order.get('setup_id') or ''
        prefix = self.NAME + '|v1|'
        if not setup.startswith(prefix):
            return None
        try:
            symbol, high, low, _, _ = json.loads(setup[len(prefix):])
            if symbol == order['symbol'] and all(math.isfinite(p) and p > 0 for p in (high, low)) and high > low:
                return high, low
        except (ValueError, TypeError):
            pass
        return None

    @staticmethod
    def _order_key(order):
        origin = order.get('origin_order_ticket') or order.get('position_id') or order.get('ticket')
        return order.get('attempt_id') or (f'legacy|{origin}' if origin else None)

    def _find_order(self, order):
        key = self._order_key(order)
        if key in self._orders:
            return key, self._orders[key]
        ids = {str(order[k]) for k in ('ticket', 'origin_order_ticket', 'position_id') if order.get(k)}
        for existing, record in self._orders.items():
            if record['symbol'] == order['symbol'] and ids.intersection(
                str(record[k]) for k in ('ticket', 'origin_order_ticket', 'position_id') if record.get(k)
            ):
                return existing, record
        return key, None

    @staticmethod
    def _close_identities(order):
        return {(order['symbol'], str(order[k])) for k in
                ('ticket', 'origin_order_ticket', 'position_id') if order.get(k)}

    def _show_pending(self, symbol, order):
        swing = order.get('swing') or (None, None)
        self._pending_entry[symbol] = order.get('entry_price', order.get('open_price'))
        self._pending_direction[symbol] = order['direction']
        self._pending_swing_high[symbol], self._pending_swing_low[symbol] = swing
        self._pending_placed_bar[symbol] = order.get('placed_bar')

    def _refresh_pending(self, symbol):
        self._clear_pending(symbol)
        for order in self._orders.values():
            if order['symbol'] == symbol and (order['state'] == 'PENDING' or order.get('has_pending')):
                self._show_pending(symbol, order)
                break

    def notify_order_accepted(self, signal, ticket, details=None):
        proposal = self._proposals.pop(signal.attempt_id, {})
        self.sync_order_state(dict(symbol=signal.symbol, direction=signal.direction,
            setup_id=signal.setup_id, attempt_id=signal.attempt_id, ticket=ticket,
            origin_order_ticket=ticket, state='PENDING', entry_price=signal.entry_price,
            swing=proposal.get('swing'), placed_bar=proposal.get('placed_bar')))

    def sync_order_state(self, order):
        symbol = order['symbol']
        self._init_symbol(symbol)
        key, record = self._find_order(order)
        if key is None or key in self._finished_orders or self._close_identities(order) & self._processed_closes:
            return
        canonical = self._order_key(order)
        if order.get('attempt_id') and canonical != key:
            self._orders.pop(key, None)
            key = canonical
        record = record if record is not None else {}
        was_open = record.get('state') == 'OPEN'
        state = order.get('state') or ('OPEN' if order.get('open_time') is not None else 'PENDING')
        record.update({k: order[k] for k in ('symbol', 'direction', 'setup_id', 'attempt_id', 'ticket',
            'origin_order_ticket', 'position_id', 'entry_price', 'open_price', 'placed_bar') if k in order})
        record['state'] = 'OPEN' if was_open or state == 'OPEN' else 'PENDING'
        record['has_pending'] = order.get('has_pending', state == 'PENDING')
        if record.get('swing') is None:
            record['swing'] = order.get('swing') or self._origin_swing(order)
        self._orders[key] = record
        self._refresh_pending(symbol)

    def notify_proposal_rejected(self, signal):
        # Execution can reject an accepted pending order at fill time, too.
        attempt = getattr(signal, 'attempt_id', None)
        if attempt in self._proposals:
            self._proposals.pop(attempt)
        elif getattr(signal, 'ticket', None):
            self.notify_order_cancelled(vars(signal))

    def notify_order_cancelled(self, order):
        key, record = self._find_order(order)
        if record is None:
            if key:
                self._finished_orders.add(key)
            return
        if record['state'] == 'OPEN':
            record['has_pending'] = False  # A filled remainder still owns the slot.
        else:
            self._orders.pop(key)
            self._finished_orders.add(key)
        self._refresh_pending(order['symbol'])

    def notify_trade_closed(self, trade):
        if trade.get('is_final') is False or trade.get('remaining_volume', 0) > 0:
            return
        symbol = trade['symbol']
        self._init_symbol(symbol)
        key, record = self._find_order(trade)
        identities = self._close_identities(trade) | (self._close_identities(record) if record else set())
        if key is None or key in self._processed_closes or identities & self._processed_closes:
            return
        self._processed_closes.add(key)
        self._processed_closes.update(identities)
        self._finished_orders.add(key)
        self._orders.pop(key, None)
        self._refresh_pending(symbol)
        if trade.get('result') != 'LOSS':
            return
        closed = self._utc(trade['close_time']) if trade.get('close_time') else None
        previous = self._last_loss_time.get(symbol)
        if closed is not None and previous is not None and closed < previous:
            return
        if closed is not None:
            self._last_loss_time[symbol] = closed
        elapsed = sum(t > closed for t in self._h1_close_times[symbol]) if closed else 0
        self._cooldown_until[symbol] = max(self._cooldown_until[symbol],
            self._h1_counter[symbol] + max(0, self.cooldown_bars - elapsed))
        swing = record.get('swing') if record else self._origin_swing(trade)
        if self.invalidate_swing_on_loss and swing is not None:
            self._used_swing_high[symbol], self._used_swing_low[symbol] = swing
        elif self.invalidate_swing_on_loss:
            logger.warning('EmaFib legacy close has no originating swing: %s ticket=%s', symbol, trade.get('ticket'))

    # ── Diagnostics ─────────────────────────────────────────────────────────

    def get_status(self, symbol: str) -> dict:
        """Return current strategy state for a symbol (for diagnostic logging)."""
        d1_bias = self._get_bias(self._d1_ema_fast.get(symbol), self._d1_ema_slow.get(symbol))
        h1_bias = self._get_bias(self._h1_ema_fast.get(symbol), self._h1_ema_slow.get(symbol))

        h1_fast = self._h1_ema_fast.get(symbol)
        h1_slow = self._h1_ema_slow.get(symbol)
        ema_sep = abs(h1_fast - h1_slow) / h1_slow if (h1_fast and h1_slow) else 0.0

        d1_atr = self._d1_atr.get(symbol)
        atr_pips = d1_atr / self._pip_size(symbol) if d1_atr else 0.0

        swing_h = self._swing_high.get(symbol)
        swing_l = self._swing_low.get(symbol)
        swing_pips = (swing_h - swing_l) / self._pip_size(symbol) if (swing_h and swing_l and swing_h > swing_l) else 0.0

        bar_idx = self._h1_counter.get(symbol, 0)
        h_age = bar_idx - self._swing_high_bar.get(symbol, 0) if swing_h else None
        l_age = bar_idx - self._swing_low_bar.get(symbol, 0) if swing_l else None

        pending = self._pending_direction.get(symbol)

        # Determine the blocking reason
        blocker = None
        if pending:
            entry = self._pending_entry[symbol]
            blocker = f'PENDING {pending} @ {entry:.5f}' if entry is not None else f'PENDING {pending}'
        elif any(o['symbol'] == symbol for o in self._orders.values()):
            blocker = 'OPEN POSITION'
        elif bar_idx < self._cooldown_until.get(symbol, 0):
            blocker = 'COOLDOWN'
        elif d1_atr is None or atr_pips < self.min_d1_atr_pips:
            blocker = f'ATR {atr_pips:.0f} < {self.min_d1_atr_pips}'
        elif d1_bias is None or h1_bias is None:
            blocker = 'EMA NOT SEEDED'
        elif d1_bias != h1_bias:
            blocker = f'BIAS DISAGREE D1={d1_bias} H1={h1_bias}'
        elif ema_sep < self.ema_sep_pct:
            blocker = f'EMA SEP {ema_sep:.5f} < {self.ema_sep_pct}'
        elif swing_h is None or swing_l is None:
            blocker = 'NO SWING'
        elif swing_pips < self.min_swing_pips:
            blocker = f'SWING {swing_pips:.0f} < {self.min_swing_pips} pips'
        elif (self.invalidate_swing_on_loss
              and swing_h == self._used_swing_high.get(symbol)
              and swing_l == self._used_swing_low.get(symbol)):
            blocker = 'SWING USED (loss)'
        else:
            blocker = 'READY (blocked_hours?)'

        return {
            'd1_bias': d1_bias,
            'h1_bias': h1_bias,
            'ema_sep': f'{ema_sep:.5f}',
            'atr_pips': f'{atr_pips:.0f}',
            'swing': f'{swing_l}-{swing_h}' if (swing_h and swing_l) else 'None',
            'swing_pips': f'{swing_pips:.0f}',
            'swing_age': f'H={h_age} L={l_age}',
            'blocker': blocker,
        }

    # ── Swing detection (fractal method) ─────────────────────────────────────

    def _detect_swings(self, symbol: str):
        window = self._h1_window[symbol]
        if len(window) < self._window_size:
            return

        mid = self.fractal_n  # index of the middle bar in the window
        mid_bar = window[mid]

        # Check fractal high: middle bar's high exceeds all N bars on each side
        is_swing_high = all(
            mid_bar.high > window[i].high
            for i in range(self._window_size)
            if i != mid
        )
        if is_swing_high:
            self._swing_high[symbol] = mid_bar.high
            self._swing_high_bar[symbol] = self._h1_counter[symbol] - self.fractal_n
            self._swing_high_time[symbol] = self._utc(mid_bar.timestamp)

        # Check fractal low: middle bar's low is below all N bars on each side
        is_swing_low = all(
            mid_bar.low < window[i].low
            for i in range(self._window_size)
            if i != mid
        )
        if is_swing_low:
            self._swing_low[symbol] = mid_bar.low
            self._swing_low_bar[symbol] = self._h1_counter[symbol] - self.fractal_n
            self._swing_low_time[symbol] = self._utc(mid_bar.timestamp)

    # ── Pip size helper ───────────────────────────────────────────────────────

    def _pip_size(self, symbol: str) -> float:
        return self.pip_sizes.get(symbol, 0.0001)

    # ── Bias helper ──────────────────────────────────────────────────────────

    @staticmethod
    def _get_bias(ema_fast: float | None, ema_slow: float | None) -> str | None:
        if ema_fast is None or ema_slow is None:
            return None
        return 'BUY' if ema_fast > ema_slow else 'SELL'

    def notify_signal_rejected(self, symbol: str):
        """Release an unsubmitted proposal, retaining indicators and setup context."""
        self._proposals = {k: p for k, p in self._proposals.items() if p['symbol'] != symbol}
