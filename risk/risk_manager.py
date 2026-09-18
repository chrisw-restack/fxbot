import logging
from typing import Callable

import config
from models import Signal, EnrichedSignal
from risk.validation import positive, valid_levels, floor_volume

logger = logging.getLogger(__name__)


class RiskManager:
    def __init__(self, account_balance_fn: Callable[[], float], rr_ratio=None,
                 risk_pct_overrides=None, entry_price_fn=None,
                 loss_per_lot_fn=None, volume_limits_fn=None):
        self._get_balance = account_balance_fn
        self.rr_ratio = rr_ratio if rr_ratio is not None else config.DEFAULT_RR_RATIO
        self._risk_pct_overrides = risk_pct_overrides or {}
        self._entry_price = entry_price_fn
        self._loss_per_lot = loss_per_lot_fn
        self._volume_limits = volume_limits_fn

    def process(self, signal: Signal) -> EnrichedSignal | None:
        if signal.order_type not in ('MARKET', 'PENDING') or not valid_levels(
            signal.direction, signal.entry_price, signal.stop_loss,
            signal.take_profit, config.MIN_RR_RATIO,
        ):
            logger.warning('Rejected invalid signal levels: %s %s', signal.strategy_name, signal.symbol)
            return None
        pip_size = config.PIP_SIZE.get(signal.symbol)
        if not positive(pip_size):
            return None
        entry = self._entry_price(signal) if self._entry_price else signal.entry_price
        sl = signal.stop_loss
        if not valid_levels(signal.direction, entry, sl):
            return None
        sl_pips = abs(entry - sl) / pip_size
        if sl_pips + 1e-10 < config.MIN_SL_PIPS:
            return None
        tp_locked = signal.take_profit is not None
        tp = signal.take_profit
        if not tp_locked:
            distance = abs(entry - sl) * self.rr_ratio
            tp = entry + distance if signal.direction == 'BUY' else entry - distance
        if not valid_levels(signal.direction, entry, sl, tp, config.MIN_RR_RATIO):
            logger.warning('Rejected executable R:R: %s %s', signal.strategy_name, signal.symbol)
            return None
        balance = self._get_balance()
        if not positive(balance):
            return None
        risk_pct = self._risk_pct_overrides.get(signal.strategy_name, config.RISK_PCT)
        if not positive(risk_pct) or risk_pct > 1:
            return None
        budget = balance * risk_pct if config.LOT_SIZE_MODE == 'DYNAMIC' else None
        if budget is not None:
            if self._loss_per_lot:
                loss = self._loss_per_lot(signal.symbol, signal.direction, entry, sl)
            else:
                value = config.PIP_VALUE_USD.get(signal.symbol)
                if not positive(value):
                    return None
                loss = sl_pips * value
            if not positive(loss):
                return None
            volume = budget / loss
        else:
            volume = config.FIXED_LOT_SIZE
        limits = self._volume_limits(signal.symbol) if self._volume_limits else {}
        volume = floor_volume(volume, **limits)
        if not volume:
            logger.warning('Rejected volume below broker minimum within risk budget: %s', signal.symbol)
            return None
        return EnrichedSignal(
            symbol=signal.symbol, direction=signal.direction, order_type=signal.order_type,
            entry_price=entry, stop_loss=sl, take_profit=tp, lot_size=volume,
            strategy_name=signal.strategy_name, timestamp=signal.timestamp,
            entry_timeframe=signal.entry_timeframe, tp_locked=tp_locked,
            risk_budget=budget,
        )
