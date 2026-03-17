import logging
from datetime import date

import config
from models import EnrichedSignal

logger = logging.getLogger(__name__)


class PortfolioManager:

    def __init__(self):
        # symbol -> {'ticket': int, 'signal': EnrichedSignal}
        self._open_positions: dict[str, dict] = {}
        self._daily_loss: float = 0.0
        self._current_date: date = date.today()

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
        Checks: one position per symbol, max open trades.
        Daily loss check is separate — call is_daily_loss_exceeded() before approve().
        """
        if signal.symbol in self._open_positions:
            logger.warning(f"Blocked: {signal.symbol} already has an open position")
            return False

        if len(self._open_positions) >= config.MAX_OPEN_TRADES:
            logger.warning(
                f"Blocked: max open trades ({config.MAX_OPEN_TRADES}) reached — "
                f"signal for {signal.symbol} dropped"
            )
            return False

        return True

    def record_open(self, signal: EnrichedSignal, ticket: int):
        self._open_positions[signal.symbol] = {'ticket': ticket, 'signal': signal}
        logger.debug(f"Position recorded: {signal.symbol} ticket={ticket}")

    def record_close(self, symbol: str, pnl: float):
        """Call when a position is closed. pnl in account currency."""
        self._open_positions.pop(symbol, None)
        if pnl < 0:
            self._daily_loss += abs(pnl)
        logger.debug(f"Position closed: {symbol} pnl={pnl:.2f} daily_loss={self._daily_loss:.2f}")

    def is_daily_loss_exceeded(self, account_balance: float) -> bool:
        limit = account_balance * config.MAX_DAILY_LOSS_PCT
        if self._daily_loss >= limit:
            logger.warning(
                f"Daily loss limit reached: ${self._daily_loss:.2f} >= ${limit:.2f} — "
                f"no new trades for today"
            )
            return True
        return False

    def get_open_positions(self) -> dict:
        return dict(self._open_positions)
