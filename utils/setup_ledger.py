"""Account-bound durable order attribution, independent of strategy checkpoints.

Only broker-confirmed IDs may bind an order to a position. Unknown legacy orders
remain unattributed. Atomic replacement retains a complete previous file on crash.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path


class SetupLedger:
    def __init__(self, path=None, account=None):
        self.path = Path(path) if path else None
        self.account = account
        self.orders = {}
        self.outcomes = {}
        self.intents = {}
        if self.path and self.path.exists():
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if data.get('version') != 1 or data.get('account') != account:
                raise ValueError('Setup ledger schema/account mismatch')
            self.orders = data['orders']
            self.outcomes = data['outcomes']
            self.intents = data.get('intents', {})
        self._committed = deepcopy((self.orders, self.outcomes, self.intents))

    def _save(self):
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        try:
            with temporary.open('w', encoding='utf-8') as stream:
                json.dump(dict(version=1, account=self.account, orders=self.orders,
                               outcomes=self.outcomes, intents=self.intents), stream, default=str, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except Exception:
            self.orders, self.outcomes, self.intents = deepcopy(self._committed)
            raise
        self._committed = deepcopy((self.orders, self.outcomes, self.intents))

    def prepare(self, **context):
        token = 'i:' + hashlib.sha256(context['attempt_id'].encode()).hexdigest()[:16]
        if token in self.intents:
            raise RuntimeError('Submission intent already exists; reconcile before retrying')
        self.intents[token] = dict(context, submitted_at=datetime.now(timezone.utc).isoformat())
        self._save()
        return token

    def pending_intents(self):
        accepted = {r['attempt_id'] for r in self.orders.values()}
        return {token: r for token, r in self.intents.items() if r['attempt_id'] not in accepted}

    def reject_intent(self, token):
        if token in self.intents:
            del self.intents[token]
            self._save()

    def recover_intent(self, ticket, comment, order):
        context = self.intents.get(comment)
        if context and all(context[k] == order.get(k) for k in ('symbol', 'strategy_name', 'direction')):
            if str(ticket) not in self.orders:
                self.accept(ticket, **context)
            return self.context(dict(order, ticket=ticket))
        return {}

    def accept(self, ticket, **context):
        if not context.get('setup_id'):
            return
        key = str(ticket)
        record = dict(context, origin_order_ticket=ticket, ticket=ticket)
        if key in self.orders and self.orders[key] != record:
            raise ValueError('Broker order already attributed to another record')
        self.orders[key] = record
        self._save()

    def context(self, order):
        record = self.orders.get(str(order.get('origin_order_ticket') or order.get('ticket')))
        if record is None and order.get('position_id'):
            matches = [r for r in self.orders.values() if r.get('position_id') == order['position_id']]
            record = matches[0] if len(matches) == 1 else None
        if record is None or any(order.get(k) and order[k] != record.get(k)
                                 for k in ('symbol', 'strategy_name', 'direction')):
            return {}
        if order.get('position_id') and record.get('position_id') not in (None, 0, order['position_id']):
            return {}
        return {k: record[k] for k in ('setup_id', 'attempt_id', 'origin_order_ticket', 'submitted_tp') if k in record}

    def bind(self, ticket, position_id):
        record = self.orders.get(str(ticket))
        if record is None or not position_id:
            return
        if record.get('position_id') not in (None, 0, position_id):
            raise ValueError('Order bound to conflicting broker position')
        if record.get('position_id') != position_id:
            record['position_id'] = position_id
            self._save()

    def cancel(self, order):
        context = self.context(order)
        if context:
            record = self.orders[str(context['origin_order_ticket'])]
            if record.get('state') != 'CLOSED':
                record['state'] = 'OPEN' if record.get('position_id') else 'CANCELLED'
            record['pending_cancelled'] = True
            self._save()

    def close(self, trade):
        context = self.context(trade)
        if not context or trade.get('is_final') is False or trade.get('remaining_volume', 0) > 0:
            return trade
        enriched = dict(trade, **context)
        key = str(context['origin_order_ticket'])
        if key not in self.outcomes:
            self.outcomes[key] = enriched
            self.orders[key]['state'] = 'CLOSED'
            self._save()
        return enriched

    def closed_trades(self):
        trades = deepcopy(list(self.outcomes.values()))
        for trade in trades:
            if isinstance(trade.get('close_time'), str):
                trade['close_time'] = datetime.fromisoformat(trade['close_time'])
        return trades

    def unresolved_orders(self):
        return [dict(r) for r in self.orders.values() if r.get('state') in ('PENDING', 'OPEN')]
