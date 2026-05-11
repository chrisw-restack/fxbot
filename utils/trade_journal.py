import csv
import json
import os
from datetime import datetime, timezone
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


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return '' if value is None else str(value)


def _round(value: Any, digits: int = 5) -> Any:
    return round(value, digits) if isinstance(value, (float, int)) else value


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

    def _write(self, row: dict[str, Any]):
        complete = {field: row.get(field, '') for field in JOURNAL_FIELDS}
        with self.path.open('a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=JOURNAL_FIELDS)
            writer.writerow(complete)

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

    def log_close(self, trade: dict):
        self._write({
            'journal_time_utc': _utc_now_iso(),
            'event': 'CLOSE',
            'ticket': trade.get('ticket', ''),
            'symbol': trade.get('symbol', ''),
            'strategy_name': trade.get('strategy_name', ''),
            'direction': trade.get('direction', ''),
            'result': trade.get('result', ''),
            'pnl': trade.get('pnl', ''),
            'r_multiple': trade.get('r_multiple', ''),
            'close_time_utc': _iso(trade.get('close_time')),
        })
