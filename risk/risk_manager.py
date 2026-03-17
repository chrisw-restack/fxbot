import logging
from typing import Callable

import config
from models import Signal, EnrichedSignal

logger = logging.getLogger(__name__)


class RiskManager:

    def __init__(self, account_balance_fn: Callable[[], float], rr_ratio: float | None = None):
        """
        account_balance_fn: callable that returns the current account balance.
        rr_ratio: overrides config.DEFAULT_RR_RATIO when provided.
        """
        self._get_balance = account_balance_fn
        self.rr_ratio = rr_ratio if rr_ratio is not None else config.DEFAULT_RR_RATIO

    def process(self, signal: Signal) -> EnrichedSignal | None:
        if signal.stop_loss is None:
            logger.error(f"Signal from {signal.strategy_name} rejected: no stop_loss set")
            return None

        pip_size = config.PIP_SIZE.get(signal.symbol)
        pip_value = config.PIP_VALUE_USD.get(signal.symbol)
        if pip_size is None or pip_value is None:
            logger.error(f"No pip config for {signal.symbol} — signal rejected")
            return None

        sl_distance = abs(signal.entry_price - signal.stop_loss)
        sl_pips = sl_distance / pip_size

        if sl_pips < config.MIN_SL_PIPS:
            logger.warning(
                f"Signal rejected | {signal.strategy_name} | {signal.symbol} {signal.direction:<4} | "
                f"{signal.timestamp.strftime('%Y-%m-%d %H:%M')} | "
                f"SL too small: {sl_pips:.1f} pips (minimum {config.MIN_SL_PIPS})"
            )
            return None

        # ── Lot size ──────────────────────────────────────────────────────────
        if config.LOT_SIZE_MODE == 'FIXED':
            lot_size = config.FIXED_LOT_SIZE
        else:
            balance = self._get_balance()
            risk_amount = balance * config.RISK_PCT
            lot_size = risk_amount / (sl_pips * pip_value)
            lot_size = round(lot_size, 2)
            if lot_size < 0.01:
                logger.warning(
                    f"Lot size clamped | {signal.strategy_name} | {signal.symbol} {signal.direction:<4} | "
                    f"{signal.timestamp.strftime('%Y-%m-%d %H:%M')} | "
                    f"Calculated {lot_size:.4f} lots, clamped to 0.01 "
                    f"(actual risk {((0.01 * sl_pips * pip_value) / balance * 100):.2f}% vs target {config.RISK_PCT * 100:.1f}%)"
                )
                lot_size = 0.01

        # ── Take-profit ───────────────────────────────────────────────────────
        if signal.take_profit is not None:
            take_profit = signal.take_profit
        else:
            tp_distance = sl_distance * self.rr_ratio
            if signal.direction == 'BUY':
                take_profit = signal.entry_price + tp_distance
            else:
                take_profit = signal.entry_price - tp_distance

        return EnrichedSignal(
            symbol=signal.symbol,
            direction=signal.direction,
            order_type=signal.order_type,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=round(take_profit, 5),
            lot_size=lot_size,
            strategy_name=signal.strategy_name,
            timestamp=signal.timestamp,
        )
