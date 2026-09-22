"""Pure strategy state for IMS setup identity and entry-attempt accounting."""
import logging
from datetime import timezone

logger = logging.getLogger(__name__)


class ImsSetupTracking:
    def _init_setup_tracking(self):
        self._setup_losses = {}
        self._retired_setups = set()
        self._setup_attempts = {}
        self._processed_setup_closes = set()

    def _setup_id(self, symbol, bias=None):
        bias = self._htf_bias.get(symbol) if bias is None else bias
        if bias is None:
            return None
        stamp = bias['_swing_ts']
        if stamp.tzinfo is not None:
            stamp = stamp.astimezone(timezone.utc).replace(tzinfo=None)
        return '|'.join((self.NAME, symbol, self.tf_htf, bias['direction'], stamp.isoformat()))

    def _is_retired_origin(self, symbol, direction, stamp):
        return self._setup_id(symbol, {'direction': direction, '_swing_ts': stamp}) in self._retired_setups

    def generate_signal(self, event):
        previous = self._setup_id(event.symbol)
        signal = self._generate_signal(event)
        if signal is None:
            return None
        signal.setup_id = previous if signal.direction == 'CANCEL' else self._setup_id(event.symbol)
        if signal.direction == 'CANCEL':
            return signal
        # One identity per completed-bar proposal; broker order ID identifies its execution.
        signal.attempt_id = signal.setup_id + '|' + event.timestamp.isoformat() + '|' + signal.direction
        self._setup_attempts[signal.attempt_id] = {
            'setup_id': signal.setup_id, 'attempt_id': signal.attempt_id,
            'symbol': signal.symbol, 'strategy_name': self.NAME, 'direction': signal.direction,
            'state': 'PROPOSED', 'submitted_tp': signal.take_profit,
        }
        return signal

    def notify_order_accepted(self, signal, ticket, details=None):
        if not signal.setup_id:
            return
        details = details or {}
        self.sync_order_state(dict(setup_id=signal.setup_id, attempt_id=signal.attempt_id,
            symbol=signal.symbol, strategy_name=self.NAME, direction=signal.direction,
            ticket=ticket, origin_order_ticket=ticket,
            state='PENDING' if signal.order_type == 'PENDING' else 'OPEN',
            submitted_tp=details.get('tp', signal.take_profit)))

    def sync_order_state(self, order):
        attempt = order.get('attempt_id')
        if not attempt or not order.get('setup_id'):
            return
        record = self._setup_attempts.setdefault(attempt, {})
        record.update({k: order[k] for k in ('setup_id', 'attempt_id', 'symbol', 'strategy_name',
            'direction', 'state', 'submitted_tp', 'ticket', 'origin_order_ticket', 'has_pending') if k in order})
        if record.get('state') in ('PENDING', 'OPEN') and self._setup_id(order['symbol']) == order['setup_id']:
            self._ltf_signal_fired[order['symbol']] = True

    def notify_proposal_rejected(self, signal):
        record = self._setup_attempts.get(getattr(signal, 'attempt_id', None))
        if record is None or record.get('state') != 'PROPOSED':
            return
        record['state'] = 'REJECTED'
        active = any(r.get('state') in ('PENDING', 'OPEN') and r['setup_id'] == record['setup_id']
                     for r in self._setup_attempts.values())
        if not active and self._setup_id(signal.symbol) == record['setup_id']:
            self.notify_signal_rejected(signal.symbol)

    def notify_order_cancelled(self, order):
        record = self._setup_attempts.get(order.get('attempt_id'), {})
        filled = record.get('state') == 'OPEN'
        self.sync_order_state(dict(order, state='OPEN' if filled else 'CANCELLED', has_pending=False))
        symbol = order['symbol']
        another_accepted = any(r.get('state') in ('PENDING', 'OPEN') and r.get('setup_id') == order.get('setup_id')
                               for r in self._setup_attempts.values())
        if not another_accepted and self._setup_id(symbol) == order.get('setup_id'):
            self._ltf_signal_fired[symbol] = False
            # Keep the last LTF origin: the cancelled attempt must not replay immediately.

    def notify_trade_closed(self, trade):
        if trade.get('is_final') is False or trade.get('remaining_volume', 0) > 0:
            return
        setup = trade.get('setup_id')
        origin = trade.get('origin_order_ticket') or trade.get('position_id') or trade.get('ticket')
        if not setup or not origin:
            logger.warning('Close has no originating setup: %s ticket=%s; setup loss count unchanged',
                           trade.get('symbol'), trade.get('ticket'))
            return
        identity = (setup, str(origin))
        if identity in self._processed_setup_closes:
            return
        self._processed_setup_closes.add(identity)
        self.sync_order_state(dict(trade, state='CLOSED', has_pending=False))
        symbol = trade['symbol']
        if trade.get('result') == 'LOSS':
            if self.streak_pause_after > 0:
                self._global_loss_streak += 1
            losses = self._setup_losses.get(setup, 0) + 1
            self._setup_losses[setup] = losses
            if losses >= self.max_losses_per_bias:
                self._retired_setups.add(setup)
            # An older trade never resets the newer bias or its LTF entry state.
            if self._setup_id(symbol) == setup:
                if setup in self._retired_setups:
                    self._htf_bias[symbol] = None
                    self._reset_ltf(symbol)
                else:
                    self._reset_ltf(symbol)
                    self._cooldown[symbol] = self.cooldown_bars
        elif trade.get('result') == 'WIN':
            self._global_loss_streak = 0
        # Preserve the prior post-win signal latch; changing re-entry after a win
        # is a separate strategy decision. Filled trades are never pending entries.

    def _pending_target_touched(self, symbol, bar, bias):
        if self.entry_mode != 'pending':
            return False
        setup = self._setup_id(symbol, bias)
        pending = [r for r in self._setup_attempts.values()
                   if r.get('setup_id') == setup and (r.get('state') == 'PENDING' or r.get('has_pending'))]
        for order in pending:
            target = order.get('submitted_tp')
            if self.pending_target_reference == 'moving' and self.tp_mode == 'htf_pct':
                target = self._get_htf_tp_price(bias)
            if target is not None and ((order['direction'] == 'SELL' and bar.low <= target)
                                       or (order['direction'] == 'BUY' and bar.high >= target)):
                return True
        return False
