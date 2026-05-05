import logging
from datetime import date

import config
from models import EnrichedSignal

logger = logging.getLogger(__name__)


class PortfolioManager:

    def __init__(
        self,
        max_open_trades: int = config.MAX_OPEN_TRADES,
        max_daily_loss_pct: float | None = config.MAX_DAILY_LOSS_PCT,
    ):
        # (symbol, strategy_name) -> {'ticket': int, 'signal': EnrichedSignal | None}
        self._open_positions: dict[tuple[str, str], dict] = {}
        self._daily_loss: float = 0.0
        self._current_date: date = date.today()
        self._max_open_trades = max_open_trades
        self._max_daily_loss_pct = max_daily_loss_pct  # None = disabled

    def set_current_date(self, d: date):
        """
        Advance the portfolio's view of the current date.
        In live mode this is always date.today(); in backtest mode the engine
        calls this with each bar's date so the daily loss counter resets correctly.
        """
        if d != self._current_date:
            self._daily_loss = 0.0
            self._current_date = d

    # ── Public API ────────────────────────────────────────────────────────────

    def approve(self, signal: EnrichedSignal) -> bool:
        """
        Returns True if the signal is allowed to proceed to execution.
        Checks: one position per (symbol, strategy), max open trades.
        Daily loss check is separate — call is_daily_loss_exceeded() before approve().
        """
        key = (signal.symbol, signal.strategy_name)
        if key in self._open_positions:
            logger.warning(
                f"Blocked: {signal.symbol} already has an open position "
                f"for {signal.strategy_name}"
            )
            return False

        if len(self._open_positions) >= self._max_open_trades:
            logger.warning(
                f"Blocked: max open trades ({self._max_open_trades}) reached — "
                f"signal for {signal.symbol} dropped"
            )
            return False

        return True

    def record_open(self, signal: EnrichedSignal, ticket: int):
        key = (signal.symbol, signal.strategy_name)
        self._open_positions[key] = {'ticket': ticket, 'signal': signal}
        logger.debug(f"Position recorded: {signal.symbol} ({signal.strategy_name}) ticket={ticket}")

    def record_existing(self, symbol: str, strategy_name: str, ticket: int):
        """Record an already-open broker position/order after startup/reconnect."""
        key = (symbol, strategy_name)
        self._open_positions[key] = {'ticket': ticket, 'signal': None}
        logger.debug(f"Existing position recorded: {symbol} ({strategy_name}) ticket={ticket}")

    def sync_existing(self, positions: list[dict]):
        """Replace portfolio slots with the broker's current bot-owned positions/orders."""
        self._open_positions.clear()
        for pos in positions:
            strategy_name = pos.get('strategy_name') or pos.get('comment') or ''
            if not strategy_name:
                continue
            self.record_existing(pos['symbol'], strategy_name, pos['ticket'])

    def record_close(self, symbol: str, pnl: float, strategy_name: str = ''):
        """Call when a position is closed. pnl in account currency."""
        key = (symbol, strategy_name)
        self._open_positions.pop(key, None)
        if pnl < 0:
            self._daily_loss += abs(pnl)
        logger.debug(f"Position closed: {symbol} ({strategy_name}) pnl={pnl:.2f} daily_loss={self._daily_loss:.2f}")

    def is_daily_loss_exceeded(self, account_balance: float) -> bool:
        if self._max_daily_loss_pct is None:
            return False
        limit = account_balance * self._max_daily_loss_pct
        if self._daily_loss >= limit:
            logger.warning(
                f"Daily loss limit reached: ${self._daily_loss:.2f} >= ${limit:.2f} — "
                f"no new trades for today"
            )
            return True
        return False

    def get_open_positions(self) -> dict:
        return dict(self._open_positions)
