import logging
import time

from models import BarEvent
from risk.risk_manager import RiskManager
from portfolio.portfolio_manager import PortfolioManager
from execution.base_execution import BaseExecution
from utils.trade_logger import TradeLogger
from utils.trade_journal import TradeJournal
from data.news_filter import NewsFilter

logger = logging.getLogger(__name__)

CANCEL_RETRY_INTERVAL_SECONDS = 60
CANCEL_MAX_ATTEMPTS = 5


class EventEngine:
    """
    Central event dispatcher. Receives BarEvents, routes them to subscribed
    strategies, then passes any signals through the risk → portfolio → execution
    pipeline.
    """

    def __init__(
        self,
        risk_manager: RiskManager,
        portfolio_manager: PortfolioManager,
        execution: BaseExecution,
        trade_logger: TradeLogger,
        notifier=None,
        news_filter: NewsFilter | None = None,
        trade_journal: TradeJournal | None = None,
    ):
        self.risk = risk_manager
        self.portfolio = portfolio_manager
        self.execution = execution
        self.logger = trade_logger
        self.notifier = notifier
        self.news_filter = news_filter
        self.trade_journal = trade_journal
        # (symbol, timeframe) -> list of strategy instances
        self._subscriptions: dict[tuple[str, str], list] = {}
        # strategy NAME -> strategy instance (for trade-closed callbacks)
        self._strategies_by_name: dict[str, object] = {}
        self._symbols_by_strategy_name: dict[str, set[str]] = {}
        # ticket -> cancellation intent retained after a temporary broker failure
        self._pending_cancel_retries: dict[int, dict] = {}

    def register(self, strategy, symbols: list[str]):
        """Subscribe a strategy to receive BarEvents for the given symbols."""
        for symbol in symbols:
            for tf in strategy.TIMEFRAMES:
                key = (symbol, tf)
                self._subscriptions.setdefault(key, []).append(strategy)
        # Index by NAME for trade-closed callbacks
        self._strategies_by_name[strategy.NAME] = strategy
        self._symbols_by_strategy_name[strategy.NAME] = set(symbols)
        logger.info(
            f"Registered {strategy.__class__.__name__} "
            f"for {symbols} on {strategy.TIMEFRAMES}"
        )

    def get_subscribed_pairs(self) -> list[tuple[str, str]]:
        """Return all (symbol, timeframe) pairs that have at least one subscriber."""
        return list(self._subscriptions.keys())

    def warmup_bar(self, event: BarEvent):
        """
        Feed a bar through subscribed strategies without placing any orders.
        Used on startup to seed EMAs, ATR, fractal windows, etc.
        """
        key = (event.symbol, event.timeframe)
        for strategy in self._subscriptions.get(key, []):
            strategy.generate_signal(event)

    def process_bar(self, event: BarEvent):
        """
        Process a single BarEvent through the full pipeline.
        Daily loss check is performed first; if exceeded no new trades are placed.
        """
        # Advance the portfolio date so the daily loss counter resets correctly
        # in both live (date.today()) and backtest (bar's date) contexts.
        self.portfolio.set_current_date(event.timestamp.date())

        balance = self.execution.get_account_balance()
        if self.portfolio.is_daily_loss_exceeded(balance):
            return

        key = (event.symbol, event.timeframe)
        strategies = self._subscriptions.get(key, [])

        for strategy in strategies:
            signal = strategy.generate_signal(event)
            if signal is None:
                continue
            # Tag the signal with the timeframe of the bar that generated it.
            # The execution layer uses this to restrict fill/SL-TP checks to
            # bars of the appropriate granularity.
            if signal.direction != 'CANCEL':
                signal.entry_timeframe = event.timeframe
            context = self._journal_context(strategy, signal.symbol)
            if self.trade_journal:
                self.trade_journal.log_signal(signal, context)

            logger.info(
                f"Signal: {signal.symbol} {signal.direction} {signal.order_type} "
                f"entry={signal.entry_price:.5f} sl={signal.stop_loss:.5f} "
                f"({signal.strategy_name})"
            )

            if signal.direction == 'CANCEL':
                if self.trade_journal:
                    self.trade_journal.log_cancel_requested(signal, context)
                self._handle_cancel(signal)
                continue

            # Block signals near high-impact news events
            if self.news_filter and self.news_filter.is_blocked(
                signal.symbol, signal.timestamp
            ):
                logger.info(f"Blocked by news filter: {signal.symbol} {signal.direction}")
                if self.trade_journal:
                    self.trade_journal.log_rejected(signal, 'news_filter', context)
                continue

            enriched = self.risk.process(signal)
            if enriched is None:
                logger.info(f"Rejected by risk manager: {signal.symbol} {signal.direction}")
                if self.trade_journal:
                    self.trade_journal.log_rejected(signal, 'risk_manager', context)
                continue

            if not self.portfolio.approve(enriched):
                if self.trade_journal:
                    self.trade_journal.log_rejected(signal, 'portfolio', context)
                continue

            ticket = self.execution.place_order(
                symbol=enriched.symbol,
                direction=enriched.direction,
                order_type=enriched.order_type,
                entry_price=enriched.entry_price,
                lot_size=enriched.lot_size,
                sl=enriched.stop_loss,
                tp=enriched.take_profit,
                strategy_name=enriched.strategy_name,
                entry_timeframe=enriched.entry_timeframe,
                tp_locked=enriched.tp_locked,
                signal_time=enriched.timestamp,
            )

            if ticket:
                logger.info(
                    f"Order placed: {enriched.symbol} {enriched.direction} "
                    f"{enriched.order_type} entry={enriched.entry_price:.5f} "
                    f"sl={enriched.stop_loss:.5f} tp={enriched.take_profit:.5f} "
                    f"lots={enriched.lot_size} ticket={ticket}"
                )
                self.portfolio.record_open(enriched, ticket)
                self.logger.log_open(enriched, ticket)
                if self.trade_journal:
                    execution_details = None
                    if hasattr(self.execution, 'get_last_order_details'):
                        execution_details = self.execution.get_last_order_details()
                    self.trade_journal.log_order_placed(enriched, ticket, context, execution_details)
                if self.notifier:
                    self.notifier.notify_order_placed(
                        symbol=enriched.symbol,
                        direction=enriched.direction,
                        entry=enriched.entry_price,
                        sl=enriched.stop_loss,
                        tp=enriched.take_profit,
                        lots=enriched.lot_size,
                        strategy=enriched.strategy_name,
                    )
            elif self.trade_journal:
                failure_context = dict(context or {})
                if hasattr(self.execution, 'get_last_order_error'):
                    failure_context['execution_error'] = self.execution.get_last_order_error()
                self.trade_journal.log_rejected(
                    signal,
                    'execution_order_failed',
                    failure_context,
                )

    def _handle_cancel(self, signal):
        """Cancel pending orders matching the signal's symbol and strategy."""
        matched = False
        for pos in self.execution.get_open_positions():
            if (pos['symbol'] == signal.symbol
                    and pos['strategy_name'] == signal.strategy_name
                    and pos.get('open_time') is None):
                matched = True
                if self._cancel_pending_order(pos['ticket']):
                    self._record_cancelled(pos, reason='strategy_cancel')
                else:
                    details = self._last_cancel_error()
                    self._record_cancel_failed(pos, 'broker_cancel_failed', details)
                    self._pending_cancel_retries[pos['ticket']] = {
                        'pos': dict(pos),
                        'attempts': 1,
                        'next_attempt': time.monotonic() + CANCEL_RETRY_INTERVAL_SECONDS,
                    }
                    if self.notifier and hasattr(self.notifier, 'notify_operational_alert'):
                        broker_reason = (details or {}).get('broker_comment') or 'broker error'
                        self.notifier.notify_operational_alert(
                            f"Cancellation delayed for {signal.symbol} ticket={pos['ticket']} "
                            f"({signal.strategy_name}): {broker_reason}. "
                            "The bot will retry automatically."
                        )
        if not matched:
            logger.info(
                f"No matching pending order to cancel: {signal.symbol} "
                f"({signal.strategy_name})"
            )

    def retry_pending_cancellations(self, now_monotonic: float | None = None):
        """Retry temporary broker cancellation failures without closing fills."""
        if not self._pending_cancel_retries:
            return

        now = time.monotonic() if now_monotonic is None else now_monotonic
        due = {
            ticket: retry
            for ticket, retry in self._pending_cancel_retries.items()
            if now >= retry['next_attempt']
        }
        if not due:
            return

        current_by_ticket = {
            pos['ticket']: pos
            for pos in self.execution.get_open_positions()
        }
        for ticket, retry in due.items():
            original = retry['pos']
            current = current_by_ticket.get(ticket)
            if current is not None and current.get('open_time') is not None:
                self._record_filled_before_cancel(original)
                del self._pending_cancel_retries[ticket]
                continue

            history_state = None
            if current is None and hasattr(self.execution, 'get_historical_order_state'):
                history_state = self.execution.get_historical_order_state(original)
            if history_state == 'FILLED':
                self._record_filled_before_cancel(original)
                del self._pending_cancel_retries[ticket]
                continue
            if history_state == 'CANCELLED':
                self._record_cancelled(original, reason='strategy_cancel_confirmed_later')
                del self._pending_cancel_retries[ticket]
                continue

            if self._cancel_pending_order(ticket):
                self._record_cancelled(original, reason='strategy_cancel_retry')
                del self._pending_cancel_retries[ticket]
                continue

            retry['attempts'] += 1
            details = self._last_cancel_error()
            self._record_cancel_failed(original, 'broker_cancel_retry_failed', details)
            if retry['attempts'] >= CANCEL_MAX_ATTEMPTS:
                del self._pending_cancel_retries[ticket]
                if self.notifier and hasattr(self.notifier, 'notify_operational_alert'):
                    self.notifier.notify_operational_alert(
                        f"Failed to cancel {original['symbol']} ticket={ticket} "
                        f"for {original['strategy_name']} after "
                        f"{CANCEL_MAX_ATTEMPTS} attempts. Check MT5 immediately."
                    )
                continue
            retry['next_attempt'] = now + CANCEL_RETRY_INTERVAL_SECONDS

    def _cancel_pending_order(self, ticket: int) -> bool:
        cancel = getattr(self.execution, 'cancel_pending_order', None)
        if cancel is not None:
            return cancel(ticket)
        return self.execution.close_order(ticket)

    def _last_cancel_error(self) -> dict | None:
        if hasattr(self.execution, 'get_last_cancel_error'):
            return self.execution.get_last_cancel_error()
        return None

    def _record_cancelled(self, pos: dict, reason: str):
        self.portfolio.record_close(pos['symbol'], 0.0, pos['strategy_name'])
        if self.trade_journal:
            self.trade_journal.log_order_cancelled(pos, reason=reason)
        logger.info(
            f"Cancelled pending order: {pos['symbol']} "
            f"ticket={pos['ticket']} ({pos['strategy_name']})"
        )

    def _record_cancel_failed(self, pos: dict, reason: str, details: dict | None):
        if self.trade_journal:
            self.trade_journal.log_cancel_failed(pos, reason=reason, details=details)
        logger.error(
            f"Failed to cancel pending order: {pos['symbol']} "
            f"ticket={pos['ticket']} ({pos['strategy_name']}) details={details}"
        )

    def _record_filled_before_cancel(self, pos: dict):
        details = {'broker_comment': 'order filled before cancellation retry'}
        self._record_cancel_failed(pos, 'order_filled_before_cancel_retry', details)
        if self.notifier and hasattr(self.notifier, 'notify_operational_alert'):
            self.notifier.notify_operational_alert(
                f"Pending {pos['symbol']} ticket={pos['ticket']} "
                f"for {pos['strategy_name']} filled before cancellation could complete. "
                "The position remains open with its broker SL/TP."
            )

    def notify_trade_closed(self, trade: dict):
        """Notify the originating strategy that a trade closed (for filters like cooldown)."""
        strategy_name = trade.get('strategy_name')
        strategy = self._strategies_by_name.get(strategy_name)
        if strategy is None:
            return
        if trade.get('symbol') not in self._symbols_by_strategy_name.get(strategy_name, set()):
            return
        if trade.get('result') == 'LOSS' and hasattr(strategy, 'notify_loss'):
            strategy.notify_loss(trade['symbol'])
        elif trade.get('result') == 'WIN' and hasattr(strategy, 'notify_win'):
            strategy.notify_win(trade['symbol'])

    def _journal_context(self, strategy, symbol: str) -> dict:
        if hasattr(strategy, 'get_last_signal_context'):
            context = strategy.get_last_signal_context(symbol)
            if context:
                return context
        if hasattr(strategy, 'get_status'):
            try:
                status = strategy.get_status(symbol)
            except Exception:
                status = None
            if status:
                return {'status': status}
        return {}
