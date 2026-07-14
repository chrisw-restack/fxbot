import csv
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import config
from models import EnrichedSignal, Signal


JOURNAL_FIELDS = [
    'journal_time_utc',
    'event',
    'ticket',
    'symbol',
    'strategy_name',
    'direction',
    'order_type',
    'entry_timeframe',
    'signal_time_utc',
    'entry_price_expected',
    'entry_price_actual',
    'stop_loss',
    'take_profit',
    'lot_size',
    'tp_locked',
    'risk_pips',
    'rr_ratio',
    'result',
    'pnl',
    'r_multiple',
    'close_time_utc',
    'reason',
    'spread_pips',
    'htf_bias_type',
    'session_hour',
    'd1_trend_alignment',
    'h4_trend_alignment',
    'd1_range_percentile',
    'd1_range_blocked',
    'context_json',
]

TERMINAL_EVENTS = {'CLOSE', 'ORDER_CANCELLED'}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return '' if value is None else str(value)


def _round(value: Any, digits: int = 5) -> Any:
    return round(value, digits) if isinstance(value, (float, int)) else value


def _ticket(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


class TradeJournal:
    """Append-only CSV journal for live/demo signal, order, and close auditing."""

    def __init__(self, path: str = 'logs/trade_journal.csv'):
        self.path = Path(path)
        os.makedirs(self.path.parent, exist_ok=True)
        if not self.path.exists() or self.path.stat().st_size == 0:
            with self.path.open('w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=JOURNAL_FIELDS)
                writer.writeheader()
        self._terminal_tickets = {
            ticket
            for row in self._read_rows()
            if row.get('event') in TERMINAL_EVENTS
            for ticket in [_ticket(row.get('ticket'))]
            if ticket is not None
        }

    def _read_rows(self) -> list[dict[str, str]]:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return []
        with self.path.open(newline='') as f:
            return list(csv.DictReader(f))

    def _write(self, row: dict[str, Any]):
        complete = {field: row.get(field, '') for field in JOURNAL_FIELDS}
        with self.path.open('a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=JOURNAL_FIELDS)
            writer.writerow(complete)
        ticket = _ticket(complete.get('ticket'))
        if ticket is not None and complete.get('event') in TERMINAL_EVENTS:
            self._terminal_tickets.add(ticket)

    def has_terminal_event(self, ticket: int) -> bool:
        return int(ticket) in self._terminal_tickets

    def get_unresolved_orders(
        self,
        max_age_days: int | None = None,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Return placed orders that have no journalled close or cancellation."""
        unresolved: dict[int, dict[str, Any]] = {}
        for row in self._read_rows():
            ticket = _ticket(row.get('ticket'))
            if ticket is None:
                continue
            if row.get('event') == 'ORDER_PLACED':
                order_type = row.get('order_type', '')
                unresolved[ticket] = {
                    'ticket': ticket,
                    'position_id': ticket,
                    'symbol': row.get('symbol', ''),
                    'strategy_name': row.get('strategy_name', ''),
                    'direction': row.get('direction', ''),
                    'state': 'PENDING' if order_type == 'PENDING' else 'OPEN',
                    'open_price': _float(
                        row.get('entry_price_actual') or row.get('entry_price_expected')
                    ),
                    'sl': _float(row.get('stop_loss')),
                    'tp': _float(row.get('take_profit')),
                    'volume': _float(row.get('lot_size')),
                    '_journal_time_utc': row.get('journal_time_utc', ''),
                }
            elif row.get('event') in TERMINAL_EVENTS:
                unresolved.pop(ticket, None)

        if max_age_days is not None:
            now = now or datetime.now(timezone.utc)
            cutoff = now - timedelta(days=max_age_days)
            unresolved = {
                ticket: pos
                for ticket, pos in unresolved.items()
                if self._is_at_or_after(pos.get('_journal_time_utc'), cutoff)
            }

        for pos in unresolved.values():
            pos.pop('_journal_time_utc', None)
        return list(unresolved.values())

    @staticmethod
    def _is_at_or_after(value: str | None, cutoff: datetime) -> bool:
        if not value:
            return True
        try:
            timestamp = datetime.fromisoformat(value)
        except ValueError:
            return True
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp >= cutoff

    def _base_from_signal(self, signal: Signal | EnrichedSignal, context: dict | None = None) -> dict[str, Any]:
        risk = abs(signal.entry_price - signal.stop_loss) if signal.stop_loss is not None else None
        pip_size = config.PIP_SIZE.get(signal.symbol)
        rr_ratio = None
        take_profit = getattr(signal, 'take_profit', None)
        if risk and take_profit is not None:
            rr_ratio = abs(take_profit - signal.entry_price) / risk

        context = context or {}
        return {
            'journal_time_utc': _utc_now_iso(),
            'symbol': signal.symbol,
            'strategy_name': signal.strategy_name,
            'direction': signal.direction,
            'order_type': signal.order_type,
            'entry_timeframe': signal.entry_timeframe or '',
            'signal_time_utc': _iso(signal.timestamp),
            'entry_price_expected': _round(signal.entry_price),
            'stop_loss': _round(signal.stop_loss),
            'take_profit': _round(take_profit),
            'lot_size': getattr(signal, 'lot_size', ''),
            'tp_locked': getattr(signal, 'tp_locked', ''),
            'risk_pips': round(risk / pip_size, 1) if risk is not None and pip_size else '',
            'rr_ratio': round(rr_ratio, 3) if rr_ratio is not None else '',
            'htf_bias_type': context.get('htf_bias_type', ''),
            'session_hour': context.get('session_hour', ''),
            'd1_trend_alignment': context.get('d1_trend_alignment', ''),
            'h4_trend_alignment': context.get('h4_trend_alignment', ''),
            'd1_range_percentile': context.get('d1_range_percentile', ''),
            'd1_range_blocked': context.get('d1_range_blocked', ''),
            'context_json': json.dumps(_json_safe(context), sort_keys=True) if context else '',
        }

    def log_signal(self, signal: Signal, context: dict | None = None):
        row = self._base_from_signal(signal, context)
        row['event'] = 'SIGNAL'
        self._write(row)

    def log_rejected(self, signal: Signal, reason: str, context: dict | None = None):
        row = self._base_from_signal(signal, context)
        row['event'] = 'REJECTED'
        row['reason'] = reason
        self._write(row)

    def log_order_placed(
        self,
        signal: EnrichedSignal,
        ticket: int,
        context: dict | None = None,
        execution_details: dict | None = None,
    ):
        row = self._base_from_signal(signal, context)
        row['event'] = 'ORDER_PLACED'
        row['ticket'] = ticket
        if execution_details:
            row['entry_price_actual'] = _round(execution_details.get('fill_price'))
            row['spread_pips'] = execution_details.get('spread_pips', '')
        self._write(row)

    def log_cancel_requested(self, signal: Signal, context: dict | None = None):
        row = self._base_from_signal(signal, context)
        row['event'] = 'CANCEL_REQUESTED'
        self._write(row)

    def log_order_cancelled(self, pos: dict, reason: str = ''):
        self._write({
            'journal_time_utc': _utc_now_iso(),
            'event': 'ORDER_CANCELLED',
            'ticket': pos.get('ticket', ''),
            'symbol': pos.get('symbol', ''),
            'strategy_name': pos.get('strategy_name') or pos.get('comment', ''),
            'direction': pos.get('direction', ''),
            'entry_price_actual': _round(pos.get('open_price')),
            'stop_loss': _round(pos.get('sl')),
            'take_profit': _round(pos.get('tp')),
            'lot_size': pos.get('volume', ''),
            'reason': reason,
        })

    def log_cancel_failed(self, pos: dict, reason: str, details: dict | None = None):
        self._write({
            'journal_time_utc': _utc_now_iso(),
            'event': 'CANCEL_FAILED',
            'ticket': pos.get('ticket', ''),
            'symbol': pos.get('symbol', ''),
            'strategy_name': pos.get('strategy_name') or pos.get('comment', ''),
            'direction': pos.get('direction', ''),
            'entry_price_actual': _round(pos.get('open_price')),
            'stop_loss': _round(pos.get('sl')),
            'take_profit': _round(pos.get('tp')),
            'lot_size': pos.get('volume', ''),
            'reason': reason,
            'context_json': json.dumps(_json_safe(details), sort_keys=True) if details else '',
        })

    def log_close_pending(self, pos: dict, reason: str = 'broker_history_pending'):
        self._write({
            'journal_time_utc': _utc_now_iso(),
            'event': 'CLOSE_PENDING_RECONCILIATION',
            'ticket': pos.get('ticket', ''),
            'symbol': pos.get('symbol', ''),
            'strategy_name': pos.get('strategy_name') or pos.get('comment', ''),
            'direction': pos.get('direction', ''),
            'entry_price_actual': _round(pos.get('open_price')),
            'stop_loss': _round(pos.get('sl')),
            'take_profit': _round(pos.get('tp')),
            'lot_size': pos.get('volume', ''),
            'reason': reason,
        })

    def log_close(self, trade: dict):
        self._write({
            'journal_time_utc': _utc_now_iso(),
            'event': 'CLOSE',
            'ticket': trade.get('ticket', ''),
            'symbol': trade.get('symbol', ''),
            'strategy_name': trade.get('strategy_name', ''),
            'direction': trade.get('direction', ''),
            'entry_price_actual': _round(trade.get('entry_price')),
            'stop_loss': _round(trade.get('sl')),
            'take_profit': _round(trade.get('tp')),
            'lot_size': trade.get('lot_size', ''),
            'result': trade.get('result', ''),
            'pnl': trade.get('pnl', ''),
            'r_multiple': trade.get('r_multiple', ''),
            'close_time_utc': _iso(trade.get('close_time')),
            'reason': trade.get('close_reason', ''),
        })
