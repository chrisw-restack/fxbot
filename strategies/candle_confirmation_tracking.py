"""Pure Candle Confirmation order attribution; confirmed outcomes arrive as callbacks."""
from datetime import datetime, timezone
import json
import logging

logger = logging.getLogger(__name__)


class CandleConfirmationTracking:
    def _init_tracking(self):
        self._orders = {}
        self._proposals = {}
        self._finished_setups = set()
        self._finished_attempts = set()
        self._cancelled_attempts = set()
        self._cancelled_ids = set()
        self._processed_closes = set()
        self._last_signal_context = {}

    def get_last_signal_context(self, symbol):
        return dict(self._last_signal_context.get(symbol, {}))

    def _record_signal_context(self, symbol, bias, bars, pivot, leg_start):
        buy = bias['direction'] == 'BUY'
        level = bars[pivot].high if buy else bars[pivot].low
        self._last_signal_context[symbol] = dict(
            engulf_time_utc=self._utc_stamp(bias['timestamp']),
            engulf_high=bias['engulf_high'], engulf_low=bias['engulf_low'],
            retrace_level=bias['retrace_level'], pivot_time_utc=self._utc_stamp(bars[pivot].timestamp),
            pivot_level=level, previous_close=bars[-2].close,
            fresh_cross=bars[-2].close <= level if buy else bars[-2].close >= level,
            leg_start_time_utc=self._utc_stamp(bars[leg_start].timestamp),
            opposite_extreme_breached=any(b.low <= bias['engulf_low'] if buy else
                b.high >= bias['engulf_high'] for b in bars),
            trend_allows_at_signal=self._trend_allows(symbol, bias['direction']))

    @staticmethod
    def _utc_stamp(value):
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.isoformat()

    def _setup_id(self, symbol, bias=None):
        bias = self._bias.get(symbol) if bias is None else bias
        if not bias or not bias.get('timestamp'):
            return None
        return self.NAME + '|v1|' + json.dumps(
            [symbol, bias['direction'], self._utc_stamp(bias['timestamp'])], separators=(',', ':'))

    def _validated_setup(self, order):
        setup = order.get('setup_id') or ''
        prefix = self.NAME + '|v1|'
        if not isinstance(setup, str) or not setup.startswith(prefix):
            return None
        try:
            symbol, direction, stamp = json.loads(setup[len(prefix):])
            datetime.fromisoformat(stamp)
        except (ValueError, TypeError):
            return None
        if symbol != order.get('symbol') or direction not in ('BUY', 'SELL'):
            return None
        if order.get('direction') and order['direction'] != direction:
            return None
        if order.get('strategy_name') and order['strategy_name'] != self.NAME:
            return None
        return setup

    def _active_orders(self, symbol):
        return [r for r in self._orders.values() if r['symbol'] == symbol]

    @staticmethod
    def _identities(order):
        return {(order['symbol'], str(order[k])) for k in
                ('ticket', 'origin_order_ticket', 'position_id') if order.get(k)}

    @staticmethod
    def _order_key(order):
        origin = order.get('origin_order_ticket') or order.get('position_id') or order.get('ticket')
        return order.get('attempt_id') or (f'legacy|{origin}' if origin else None)

    def _find_order(self, order):
        key = self._order_key(order)
        if key in self._orders:
            return key, self._orders[key]
        ids = self._identities(order)
        for existing, record in self._orders.items():
            if ids & self._identities(record):
                return existing, record
        return key, None

    def generate_signal(self, event):
        signal = self._generate_signal(event)
        if signal is not None:
            setup = self._setup_id(signal.symbol)
            signal.setup_id = setup
            signal.attempt_id = setup + '|' + self._utc_stamp(signal.timestamp)
            signal.min_stop_distance = max(0., self.min_sl_pips) * self._pip_size(signal.symbol)
            self._proposals[signal.attempt_id] = setup
        return signal

    def notify_order_accepted(self, signal, ticket, details=None):
        self._proposals.pop(signal.attempt_id, None)
        details = details or {}
        self.sync_order_state(dict(symbol=signal.symbol, direction=signal.direction,
            strategy_name=self.NAME, setup_id=signal.setup_id, attempt_id=signal.attempt_id,
            ticket=ticket, origin_order_ticket=ticket,
            state='OPEN' if details.get('fill_price') else 'PENDING',
            submitted_tp=details.get('tp', signal.take_profit)))

    def sync_order_state(self, order):
        key, record = self._find_order(order)
        ids = self._identities(order)
        state = order.get('state') or ('OPEN' if order.get('open_time') is not None else 'PENDING')
        if key is None or key in self._finished_attempts or key in self._processed_closes or ids & self._processed_closes:
            return
        if state != 'OPEN' and (key in self._cancelled_attempts or ids & self._cancelled_ids):
            return
        if order.get('strategy_name') and order['strategy_name'] != self.NAME:
            return
        canonical = self._order_key(order)
        if order.get('attempt_id') and canonical != key:
            self._orders.pop(key, None)
            key = canonical
        record = record if record is not None else {}
        was_open = record.get('state') == 'OPEN'
        record.update({k: order[k] for k in ('symbol', 'direction', 'ticket', 'origin_order_ticket',
            'position_id', 'attempt_id', 'submitted_tp') if order.get(k) is not None})
        setup = self._validated_setup(order)
        if setup:
            record['setup_id'] = setup
        record['state'] = 'OPEN' if was_open or state == 'OPEN' else 'PENDING'
        record['has_pending'] = order.get('has_pending', state == 'PENDING')
        self._orders[key] = record
        if record.get('setup_id') and record['setup_id'] == self._setup_id(order['symbol']):
            self._signal_fired[order['symbol']] = True

    def notify_proposal_rejected(self, signal):
        attempt = getattr(signal, 'attempt_id', None)
        setup = self._proposals.pop(attempt, None)
        # A queued simulated market order can fail at its next-open fill. Only
        # that identified unfilled attempt may release an accepted order record.
        if getattr(signal, 'ticket', None):
            order = vars(signal)
            key, record = self._find_order(order)
            if record and record['state'] != 'OPEN':
                setup = record.get('setup_id')
                self._orders.pop(key)
                self._finished_attempts.add(key)
        if setup and setup == self._setup_id(signal.symbol) and not self._active_orders(signal.symbol):
            self._signal_fired[signal.symbol] = False

    def notify_signal_rejected(self, symbol):
        """Compatibility for unsubmitted proposals; accepted exposure owns the slot."""
        if not self._active_orders(symbol):
            self._signal_fired[symbol] = False
            self._proposals = {a:s for a,s in self._proposals.items() if not (
                s == self._setup_id(symbol))}

    def notify_order_cancelled(self, order):
        key, record = self._find_order(order)
        if not record or key in self._processed_closes or self._identities(order) & self._processed_closes:
            return
        if record['state'] == 'OPEN':
            record['has_pending'] = False  # A cancelled remainder does not remove filled exposure.
            return
        self._orders.pop(key)
        self._cancelled_attempts.add(key)
        self._cancelled_ids.update(self._identities(order) | self._identities(record))
        setup = record.get('setup_id')
        if setup and setup == self._setup_id(order['symbol']) and not self._active_orders(order['symbol']):
            self._signal_fired[order['symbol']] = False

    def notify_trade_closed(self, trade):
        if trade.get('is_final') is False or trade.get('remaining_volume', 0) > 0:
            return
        key, record = self._find_order(trade)
        ids = self._identities(trade) | (self._identities(record) if record else set())
        if key is None or key in self._processed_closes or ids & self._processed_closes:
            return
        self._processed_closes.add(key)
        self._processed_closes.update(ids)
        self._finished_attempts.add(key)
        self._orders.pop(key, None)
        setup = self._validated_setup(trade) or (record or {}).get('setup_id')
        if not setup:
            logger.warning('Candle Confirmation legacy close has no originating setup: %s ticket=%s',
                           trade['symbol'], trade.get('ticket'))
            return
        self._finished_setups.add(setup)
        if setup == self._setup_id(trade['symbol']) and not self._active_orders(trade['symbol']):
            self._expire_bias(trade['symbol'])

    def notify_win(self, symbol):
        logger.warning('Candle Confirmation win needs ticket/setup attribution: %s', symbol)

    def notify_loss(self, symbol):
        logger.warning('Candle Confirmation loss needs ticket/setup attribution: %s', symbol)
