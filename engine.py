import logging

from models import BarEvent
from risk.risk_manager import RiskManager
from portfolio.portfolio_manager import PortfolioManager
from execution.base_execution import BaseExecution
from utils.trade_logger import TradeLogger
from utils.trade_journal import TradeJournal
from data.news_filter import NewsFilter

logger = logging.getLogger(__name__)


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

    def register(self, strategy, symbols: list[str]):
        """Subscribe a strategy to receive BarEvents for the given symbols."""
        for symbol in symbols:
            for tf in strategy.TIMEFRAMES:
                key = (symbol, tf)
                self._subscriptions.setdefault(key, []).append(strategy)
        # Index by NAME for trade-closed callbacks
        self._strategies_by_name[strategy.NAME] = strategy
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
                self.trade_journal.log_rejected(signal, 'execution_order_failed', context)

    def _handle_cancel(self, signal):
        """Cancel pending orders matching the signal's symbol and strategy."""
        for pos in self.execution.get_open_positions():
            if (pos['symbol'] == signal.symbol
                    and pos['strategy_name'] == signal.strategy_name
                    and pos.get('open_time') is None):
                self.execution.close_order(pos['ticket'])
                self.portfolio.record_close(signal.symbol, 0.0, signal.strategy_name)
                if self.trade_journal:
                    self.trade_journal.log_order_cancelled(pos, reason='strategy_cancel')
                logger.info(
                    f"Cancelled pending order: {signal.symbol} "
                    f"ticket={pos['ticket']} ({signal.strategy_name})"
                )

    def notify_trade_closed(self, trade: dict):
        """Notify the originating strategy that a trade closed (for filters like cooldown)."""
        strategy = self._strategies_by_name.get(trade.get('strategy_name'))
        if strategy is None:
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
