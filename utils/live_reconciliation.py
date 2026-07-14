import logging


def _same_strategy_slot(expected: dict, current: dict) -> bool:
    return (
        expected.get('symbol') == current.get('symbol')
        and expected.get('strategy_name') == (
            current.get('strategy_name') or current.get('comment') or ''
        )
        and expected.get('direction') == current.get('direction')
    )


def recover_offline_journal_orders(
    execution,
    trade_journal,
    notifier,
    current_positions: list[dict],
    logger: logging.Logger,
) -> tuple[int, int, list[int]]:
    """Backfill broker outcomes that occurred while the Python bot was offline."""
    recovered_closes = 0
    recovered_cancellations = 0
    unresolved_open = []
    current_tickets = {pos['ticket'] for pos in current_positions}

    for pos in trade_journal.get_unresolved_orders(max_age_days=30):
        ticket = pos['ticket']
        if ticket in current_tickets or any(
            _same_strategy_slot(pos, current) for current in current_positions
        ):
            continue

        closed = execution.get_recent_closed_trade(pos, lookback_days=30)
        if closed is not None:
            trade_journal.log_close(closed)
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
            trade_journal.log_order_cancelled(pos, reason='startup_missing_from_broker')
            logger.info(
                f"Recovered offline pending-order cancellation: {pos['symbol']} ticket={ticket}"
            )
            recovered_cancellations += 1
        else:
            unresolved_open.append(ticket)

    return recovered_closes, recovered_cancellations, unresolved_open
