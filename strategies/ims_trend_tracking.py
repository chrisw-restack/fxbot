"""Pure IMS trend setup/order state. Broker outcomes arrive through callbacks."""
import logging
from datetime import timezone

from models import Signal

logger = logging.getLogger(__name__)


class ImsTrendTracking:
    def _init_tracking(self):
        self._orders = {}
        self._proposals = {}
        self._retired_setups = set()
        self._finished_orders = set()
        self._processed_closes = set()
        self._cancelled_order_ids = set()

    def _setup_id(self, symbol, bias=None):
        bias = self._htf_bias.get(symbol) if bias is None else bias
        if bias is None:
            return None
        stamp = bias['_swing_ts']
        if stamp.tzinfo is not None:
            stamp = stamp.astimezone(timezone.utc).replace(tzinfo=None)
        return '|'.join((self.NAME, symbol, self.tf_htf, bias['direction'], stamp.isoformat()))

    def _active_orders(self, symbol):
        return [o for o in self._orders.values() if o['symbol'] == symbol]

    def generate_signal(self, event):
        signal = self._generate_signal(event)
        if signal is not None and signal.direction != 'CANCEL':
            signal.setup_id = self._setup_id(event.symbol)
            stamp = event.timestamp
            if stamp.tzinfo is not None:
                stamp = stamp.astimezone(timezone.utc).replace(tzinfo=None)
            signal.attempt_id = signal.setup_id + '|' + stamp.isoformat()
            self._proposals[signal.attempt_id] = signal.setup_id
        if signal is not None:
            return signal
        # Keep a failed cancellation visible even after the bias changed or expired.
        # Filled exposure is retained, but never generates a cancellation by itself.
        for order in self._active_orders(event.symbol):
            obsolete = order.get('setup_id') and order['setup_id'] != self._setup_id(event.symbol)
            if (order.get('cancel_requested') or obsolete) and self._is_pending(order):
                return self._order_cancel(event, order)
        return None

    @staticmethod
    def _is_pending(order):
        return order['state'] == 'PENDING' or order.get('has_pending', False)

    def _order_cancel(self, event, order):
        order['cancel_requested'] = True
        return Signal(event.symbol, 'CANCEL', 'PENDING', 0., 0., self.NAME, event.timestamp,
                      setup_id=order.get('setup_id'), attempt_id=order.get('attempt_id'))

    def _cancel_setup(self, symbol, bar, setup):
        for order in self._active_orders(symbol):
            if setup and order.get('setup_id') == setup and self._is_pending(order):
                return self._order_cancel(bar, order)
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
        identities = self._identities(order)
        for existing, record in self._orders.items():
            if identities & self._identities(record):
                return existing, record
        return key, None

    def notify_order_accepted(self, signal, ticket, details=None):
        self._proposals.pop(signal.attempt_id, None)
        details = details or {}
        self.sync_order_state(dict(symbol=signal.symbol, direction=signal.direction,
            strategy_name=self.NAME, setup_id=signal.setup_id, attempt_id=signal.attempt_id,
            ticket=ticket, origin_order_ticket=ticket,
            state='PENDING' if signal.order_type == 'PENDING' else 'OPEN',
            submitted_tp=details.get('tp', signal.take_profit), entry_price=signal.entry_price,
            sl=signal.stop_loss))

    def sync_order_state(self, order):
        key, record = self._find_order(order)
        ids = self._identities(order)
        state = order.get('state') or ('OPEN' if order.get('open_time') is not None else 'PENDING')
        if key is None or key in self._processed_closes or ids & self._processed_closes:
            return
        if state != 'OPEN' and (key in self._finished_orders or ids & self._cancelled_order_ids):
            return
        canonical = self._order_key(order)
        if order.get('attempt_id') and canonical != key:
            self._orders.pop(key, None)
            key = canonical
        record = record if record is not None else {}
        was_open = record.get('state') == 'OPEN'
        record.update({k: order[k] for k in ('symbol', 'direction', 'setup_id', 'attempt_id',
            'ticket', 'origin_order_ticket', 'position_id', 'submitted_tp', 'entry_price', 'sl')
                       if order.get(k) is not None})
        record['state'] = 'OPEN' if was_open or state == 'OPEN' else 'PENDING'
        record['has_pending'] = order.get('has_pending', state == 'PENDING')
        self._orders[key] = record
        if record.get('setup_id') in self._retired_setups:
            record['cancel_requested'] = True
        if record.get('setup_id') and record['setup_id'] == self._setup_id(order['symbol']):
            self._ltf_signal_fired[order['symbol']] = True

    def notify_proposal_rejected(self, signal):
        attempt = getattr(signal, 'attempt_id', None)
        setup = self._proposals.pop(attempt, None)
        if setup and self._setup_id(signal.symbol) == setup:
            if not any(o.get('setup_id') == setup for o in self._active_orders(signal.symbol)):
                self.notify_signal_rejected(signal.symbol)
        elif getattr(signal, 'ticket', None):
            self.notify_order_cancelled(vars(signal))

    def notify_order_cancelled(self, order):
        key, record = self._find_order(order)
        if key in self._processed_closes or self._identities(order) & self._processed_closes:
            return  # A late remainder-cancel event cannot change a final trade outcome.
        setup = order.get('setup_id') or (record or {}).get('setup_id')
        if setup:
            self._retired_setups.add(setup)
        if record is not None and record['state'] == 'OPEN':
            record['has_pending'] = False
        else:
            if key:
                self._orders.pop(key, None)
                self._finished_orders.add(key)
            self._cancelled_order_ids.update(self._identities(order))
            if record:
                self._cancelled_order_ids.update(self._identities(record))
        # A delayed cancellation for an old setup must not reset the current one.
        if setup and setup == self._setup_id(order['symbol']):
            self._htf_bias[order['symbol']] = None
            self._reset_ltf(order['symbol'])

    def notify_trade_closed(self, trade):
        if trade.get('is_final') is False or trade.get('remaining_volume', 0) > 0:
            return
        key, record = self._find_order(trade)
        ids = self._identities(trade) | (self._identities(record) if record else set())
        if key is None or key in self._processed_closes or ids & self._processed_closes:
            return
        self._processed_closes.add(key)
        self._processed_closes.update(ids)
        self._finished_orders.add(key)
        self._orders.pop(key, None)
        setup = trade.get('setup_id') or (record or {}).get('setup_id')
        if not setup:
            logger.warning('IMS legacy close has no originating setup: %s ticket=%s',
                           trade['symbol'], trade.get('ticket'))
            return
        if trade.get('result') == 'WIN':
            self._retired_setups.add(setup)
        if setup != self._setup_id(trade['symbol']):
            return
        if trade.get('result') == 'WIN':
            self.notify_win(trade['symbol'])
        elif trade.get('result') == 'LOSS':
            self.notify_loss(trade['symbol'])

    def _pending_target_touched(self, symbol, bar):
        setup = self._setup_id(symbol)
        for order in self._active_orders(symbol):
            target = order.get('submitted_tp')
            if setup and order.get('setup_id') == setup and self._is_pending(order) and target is not None:
                # A structural bid-price touch, not a claim about an executable SELL TP.
                if ((order['direction'] == 'BUY' and bar.high >= target)
                        or (order['direction'] == 'SELL' and bar.low <= target)):
                    return True
        return False
