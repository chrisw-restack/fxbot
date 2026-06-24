"""
Live trading entry point.

Requires:
- Windows environment with MetaTrader5 installed and running.
- A .env file at the project root with MT5_LOGIN, MT5_PASSWORD, MT5_SERVER.

To add or remove strategies, edit the 'strategies' list in main() below.
"""

import os
import time
import logging
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv

from engine import EventEngine
from risk.risk_manager import RiskManager
from portfolio.portfolio_manager import PortfolioManager
from execution.mt5_execution import MT5Execution
from utils.trade_logger import TradeLogger
from utils.trade_journal import TradeJournal
from data.mt5_data import connect, disconnect, reconnect, get_latest_completed_bar, get_recent_bars
from data.historical_loader import bar_close_time
from live_config import create_live_strategy_specs, live_symbols, live_risk_pct_overrides

from utils.telegram_notifier import TelegramNotifier
import config

HEARTBEAT_HOUR = 8  # 8am UTC+2
HEARTBEAT_TZ = timezone(timedelta(hours=2))

os.makedirs('logs', exist_ok=True)

# Roll over existing log on startup — keeps one archive per run
_log_path = 'logs/trading.log'
if os.path.exists(_log_path):
    _ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    os.rename(_log_path, f'logs/trading_{_ts}.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s  %(name)s — %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/trading.log'),
    ],
)
logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 5
CLOSE_HISTORY_GRACE_SECONDS = 30
CLOSE_HISTORY_ALERT_SECONDS = 120
TF_RANK = {'M1': 0, 'M5': 1, 'M15': 2, 'M30': 3, 'H1': 4, 'H4': 5, 'D1': 6}


def _sort_pairs(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return sorted(pairs, key=lambda p: (TF_RANK.get(p[1], 99), p[0]))


def _is_same_live_slot(a: dict, b: dict) -> bool:
    return (
        a.get('symbol') == b.get('symbol')
        and (a.get('strategy_name') or a.get('comment')) == (b.get('strategy_name') or b.get('comment'))
        and a.get('direction') == b.get('direction')
        and a.get('state') != b.get('state')
    )


def _reconcile_portfolio(portfolio: PortfolioManager, execution: MT5Execution) -> dict[int, dict]:
    current_positions = execution.get_open_positions()
    portfolio.sync_existing(current_positions)
    return {p['ticket']: p for p in current_positions}

def _duplicate_live_slots(positions: list[dict]) -> list[tuple[str, str, list[int]]]:
    slots: dict[tuple[str, str], list[int]] = {}
    for pos in positions:
        key = (
            pos.get('symbol', ''),
            pos.get('strategy_name') or pos.get('comment') or '',
        )
        slots.setdefault(key, []).append(pos.get('ticket'))
    return [
        (symbol, strategy_name, tickets)
        for (symbol, strategy_name), tickets in slots.items()
        if symbol and strategy_name and len(tickets) > 1
    ]


def main():
    load_dotenv()
    config.validate()

    login    = int(os.environ['MT5_LOGIN'])
    password = os.environ['MT5_PASSWORD']
    server   = os.environ['MT5_SERVER']

    if not connect(login, password, server):
        logger.error("Could not connect to MT5 — aborting")
        return

    try:
        execution    = MT5Execution(magic_numbers=config.MAGIC_NUMBERS)
        portfolio    = PortfolioManager()
        trade_logger = TradeLogger()
        trade_journal = TradeJournal()
        risk         = RiskManager(
            account_balance_fn=execution.get_account_balance,
            rr_ratio=2.5,  # engulfing uses 2.5R (fib strategies set their own TP and bypass this)
            risk_pct_overrides=live_risk_pct_overrides(),
        )

        notifier = TelegramNotifier()

        event_engine = EventEngine(
            risk_manager=risk,
            portfolio_manager=portfolio,
            execution=execution,
            trade_logger=trade_logger,
            notifier=notifier,
            trade_journal=trade_journal,
        )

        strategy_specs = create_live_strategy_specs()
        strategies = [strategy for strategy, _ in strategy_specs]
        missing_magic = sorted({
            strategy.NAME
            for strategy in strategies
            if strategy.NAME not in config.MAGIC_NUMBERS
        })
        if missing_magic:
            raise RuntimeError(
                f"Live strategies missing MT5 magic numbers: {missing_magic}"
            )
        for strategy, symbols in strategy_specs:
            event_engine.register(strategy, symbols)

        # ── Bar-detection state ───────────────────────────────────────────────
        # Tracks the timestamp of the last processed bar per (symbol, timeframe).
        last_bar_time: dict[tuple[str, str], datetime] = {}
        subscribed_pairs = _sort_pairs(event_engine.get_subscribed_pairs())

        # ── Warm-up: feed historical bars so EMAs/ATR/fractals are seeded ────
        # D1 needs ~50 bars for EMA(20) + ATR(14) with margin.
        # H4/H1 need ~100 bars for fractal window + swing detection.
        # M15 needs ~200 bars for fractal window + swing detection on faster TF.
        WARMUP_BARS = {'D1': 50, 'H4': 100, 'H1': 100, 'M15': 200, 'M5': 250}
        logger.info("Warming up strategy state with historical bars...")
        warmup_count = 0
        warmup_events = []
        warmup_pairs = subscribed_pairs
        for symbol, timeframe in warmup_pairs:
            count = WARMUP_BARS.get(timeframe, 50)
            bars = get_recent_bars(symbol, timeframe, count)
            if bars:
                warmup_events.extend(bars)
                # Set last_bar_time so the poll loop doesn't re-process the last bar
                last_bar_time[(symbol, timeframe)] = bars[-1].timestamp
        warmup_events.sort(key=lambda b: (bar_close_time(b), TF_RANK.get(b.timeframe, 99), b.symbol))
        for bar in warmup_events:
            event_engine.warmup_bar(bar)
            warmup_count += 1
        logger.info(f"Warm-up complete: {warmup_count} bars processed across {len(subscribed_pairs)} pairs")

        tracked_tickets = _reconcile_portfolio(portfolio, execution)
        missing_close_since: dict[int, datetime] = {}
        close_pending_journaled: set[int] = set()
        close_pending_alerted: set[int] = set()
        last_duplicate_slots: list[tuple[str, str, list[int]]] = []
        logger.info(f"Reconciled {len(tracked_tickets)} existing MT5 positions/orders")
        duplicate_slots = _duplicate_live_slots(list(tracked_tickets.values()))
        if duplicate_slots:
            message = f"Duplicate broker strategy slots detected: {duplicate_slots}"
            logger.critical(message)
            notifier.notify_operational_alert(message)
        last_duplicate_slots = duplicate_slots

        logger.info(f"Live trading started — watching {len(subscribed_pairs)} symbol/timeframe pairs")
        notifier.notify_started(live_symbols(), [s.NAME for s in strategies])

        consecutive_failures = 0
        last_heartbeat_date = None

        while True:
            # Daily heartbeat at 8am UTC+2
            now_local = datetime.now(HEARTBEAT_TZ)
            if now_local.hour >= HEARTBEAT_HOUR and last_heartbeat_date != now_local.date():
                last_heartbeat_date = now_local.date()
                notifier.notify_heartbeat(
                    balance=execution.get_account_balance(),
                    open_positions=len(execution.get_open_positions()),
                )

            try:
                # Detect closed trades by comparing tracked tickets to current positions
                current_positions = execution.get_open_positions()
                current_tickets = {p['ticket'] for p in current_positions}
                for ticket, pos in list(tracked_tickets.items()):
                    if ticket not in current_tickets:
                        if any(_is_same_live_slot(pos, current) for current in current_positions):
                            # Pending order likely filled into a broker position with a new ticket.
                            del tracked_tickets[ticket]
                            missing_close_since.pop(ticket, None)
                            continue
                        # Position closed (SL/TP hit on broker side)
                        closed = execution.get_recent_closed_trade(pos)
                        if closed is None:
                            now_utc = datetime.now(timezone.utc)
                            first_missing = missing_close_since.setdefault(ticket, now_utc)
                            wait_seconds = (now_utc - first_missing).total_seconds()
                            if ticket not in close_pending_journaled:
                                trade_journal.log_close_pending(pos)
                                close_pending_journaled.add(ticket)
                            if wait_seconds < CLOSE_HISTORY_GRACE_SECONDS:
                                if wait_seconds < POLL_INTERVAL_SECONDS:
                                    logger.info(
                                        f"Waiting for MT5 close history: {pos['symbol']} "
                                        f"ticket={ticket}"
                                    )
                                continue

                        if closed is None and pos.get('state') == 'PENDING':
                            del tracked_tickets[ticket]
                            missing_close_since.pop(ticket, None)
                            close_pending_journaled.discard(ticket)
                            close_pending_alerted.discard(ticket)
                            strategy_name = pos.get('strategy_name') or pos.get('comment') or ''
                            portfolio.record_close(pos['symbol'], 0.0, strategy_name)
                            trade_journal.log_order_cancelled(pos, reason='pending_missing_from_broker')
                            logger.info(
                                f"Pending order no longer active: {pos['symbol']} "
                                f"ticket={ticket} ({strategy_name})"
                            )
                            continue
                        if closed is None:
                            if (
                                wait_seconds >= CLOSE_HISTORY_ALERT_SECONDS
                                and ticket not in close_pending_alerted
                            ):
                                message = (
                                    f"MT5 close history unavailable for {pos['symbol']} "
                                    f"ticket={ticket} after {int(wait_seconds)} seconds. "
                                    "The close remains pending reconciliation; cached P/L was not used."
                                )
                                logger.error(message)
                                notifier.notify_operational_alert(message)
                                close_pending_alerted.add(ticket)
                            continue

                        del tracked_tickets[ticket]
                        missing_close_since.pop(ticket, None)
                        close_pending_journaled.discard(ticket)
                        close_pending_alerted.discard(ticket)
                        strategy_name = closed['strategy_name']
                        logger.info(
                            f"Trade closed by broker: {closed['symbol']} {closed['direction']} "
                            f"ticket={ticket} result={closed['result']} pnl={closed['pnl']:.2f} "
                            f"r={closed.get('r_multiple')} source={closed.get('r_source', 'fallback')}"
                        )
                        trade_journal.log_close(closed)
                        notifier.notify_order_closed(
                            symbol=closed['symbol'],
                            direction=closed['direction'],
                            result=closed['result'],
                            r_multiple=closed.get('r_multiple'),
                            pnl=closed['pnl'],
                            strategy=strategy_name,
                        )
                        portfolio.record_close(closed['symbol'], closed['pnl'], strategy_name)
                        portfolio.is_daily_loss_exceeded(execution.get_account_balance())
                        event_engine.notify_trade_closed({
                            'symbol':        closed['symbol'],
                            'strategy_name': strategy_name,
                            'result':        closed['result'],
                        })
                # Update tracked positions with latest profit values
                for p in current_positions:
                    missing_close_since.pop(p['ticket'], None)
                    close_pending_journaled.discard(p['ticket'])
                    close_pending_alerted.discard(p['ticket'])
                    tracked_tickets[p['ticket']] = p
                portfolio.sync_existing(current_positions)
                duplicate_slots = _duplicate_live_slots(current_positions)
                if duplicate_slots and duplicate_slots != last_duplicate_slots:
                    logger.critical(f"Duplicate broker strategy slots detected: {duplicate_slots}")
                    notifier.notify_operational_alert(
                        f"Duplicate broker strategy slots detected: {duplicate_slots}"
                    )
                last_duplicate_slots = duplicate_slots

                for symbol, timeframe in subscribed_pairs:
                    bar = get_latest_completed_bar(symbol, timeframe)
                    if bar is None:
                        continue

                    key = (symbol, timeframe)
                    if last_bar_time.get(key) == bar.timestamp:
                        continue  # No new completed bar yet

                    last_bar_time[key] = bar.timestamp
                    logger.info(f"New bar: {symbol} {timeframe} @ {bar.timestamp}  O={bar.open} H={bar.high} L={bar.low} C={bar.close}")
                    event_engine.process_bar(bar)

                    # Log strategy status after each D1 bar (daily diagnostic)
                    if timeframe == 'D1':
                        for strat in strategies:
                            if hasattr(strat, 'get_status'):
                                status = strat.get_status(symbol)
                                parts = [f"D1={status.get('d1_bias')} H1={status.get('h1_bias')}",
                                         f"ATR={status.get('atr_pips')}p",
                                         f"EMA_sep={status.get('ema_sep')}"]
                                if 'swing' in status:
                                    parts.append(
                                        f"swing={status['swing']} "
                                        f"({status['swing_pips']}p age {status['swing_age']})"
                                    )
                                if 'blocker' in status:
                                    parts.append(f"→ {status['blocker']}")
                                logger.info(f"Status [{strat.NAME}] {symbol}: " + "  ".join(parts))

                consecutive_failures = 0
            except Exception:
                consecutive_failures += 1
                logger.exception(f"Error in poll loop (failure #{consecutive_failures})")
                if consecutive_failures >= 3:
                    logger.warning("Multiple consecutive failures — attempting MT5 reconnect")
                    if not reconnect():
                        logger.error("Reconnect failed — shutting down")
                        return
                    tracked_tickets = _reconcile_portfolio(portfolio, execution)
                    missing_close_since.clear()
                    close_pending_journaled.clear()
                    close_pending_alerted.clear()
                    last_duplicate_slots = _duplicate_live_slots(
                        list(tracked_tickets.values())
                    )
                    consecutive_failures = 0

            time.sleep(POLL_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        logger.info("Shutdown requested by user")
    except Exception:
        logger.exception("Unexpected error in main loop")
    finally:
        disconnect()


if __name__ == '__main__':
    main()
