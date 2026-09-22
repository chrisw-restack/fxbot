import logging


def _same_strategy_slot(expected: dict, current: dict) -> bool:
    return (
        expected.get('symbol') == current.get('symbol')
        and expected.get('strategy_name') == (
            current.get('strategy_name') or current.get('comment') or ''
        )
        and expected.get('direction') == current.get('direction')
    )


def same_broker_position(expected, current):
    """Match confirmed order/position identifiers, never just a strategy slot."""
    if not _same_strategy_slot(expected, current):
        return False
    old_order = expected.get('origin_order_ticket') or expected.get('ticket')
    new_order = current.get('origin_order_ticket') or current.get('ticket')
    return bool(old_order and old_order == new_order) or bool(
        expected.get('position_id') and expected['position_id'] == current.get('position_id'))


def recover_offline_journal_orders(
    execution,
    trade_journal,
    notifier,
    current_positions: list[dict],
    logger: logging.Logger,
    on_close=None,
    on_cancel=None,
) -> tuple[int, int, list[int]]:
    """Backfill broker outcomes that occurred while the Python bot was offline."""
    recovered_closes = 0
    recovered_cancellations = 0
    unresolved_open = []
    current_tickets = {pos['ticket'] for pos in current_positions}

    unresolved = {p['ticket']: p for p in trade_journal.get_unresolved_orders(max_age_days=30)}
    ledger = getattr(execution, 'setup_ledger', None)
    if ledger is not None:
        unresolved.update({p['ticket']: p for p in ledger.unresolved_orders()})
    for pos in unresolved.values():
        ticket = pos['ticket']
        if ticket in current_tickets or any(
            same_broker_position(pos, current) for current in current_positions
        ):
            continue

        closed = execution.get_recent_closed_trade(pos, lookback_days=30)
        if closed is not None:
            trade_journal.log_close(closed)
            if on_close is not None:
                on_close(closed)
            notifier.notify_order_closed(
                symbol=closed['symbol'],
                direction=closed['direction'],
                result=closed['result'],
                r_multiple=closed.get('r_multiple'),
                pnl=closed['pnl'],
                strategy=closed['strategy_name'],
            )
            logger.info(
                f"Recovered offline broker close: {closed['symbol']} {closed['direction']} "
                f"ticket={ticket} result={closed['result']} pnl={closed['pnl']:.2f}"
            )
            recovered_closes += 1
            continue

        state_lookup = getattr(execution, 'get_historical_order_state', None)
        order_state = state_lookup(pos) if state_lookup is not None else None
        if pos.get('state') == 'PENDING' and order_state == 'CANCELLED':
            if ledger is not None:
                ledger.cancel(pos)
            if on_cancel is not None:
                on_cancel(pos)
            trade_journal.log_order_cancelled(pos, reason='startup_missing_from_broker')
            logger.info(
                f"Recovered offline pending-order cancellation: {pos['symbol']} ticket={ticket}"
            )
            recovered_cancellations += 1
        else:
            unresolved_open.append(ticket)

    return recovered_closes, recovered_cancellations, unresolved_open


def apply_trade_updates(event_engine, trades, through):
    """Apply recovered outcomes in UTC order during completed-bar catch-up."""
    from datetime import timezone
    def utc_naive(value):
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
    remaining = []
    for trade in sorted(trades, key=lambda t: utc_naive(t['close_time'])):
        if utc_naive(trade['close_time']) <= utc_naive(through):
            event_engine.notify_trade_closed(trade)
        else:
            remaining.append(trade)
    return remaining
