import logging

import config
from execution.base_execution import BaseExecution
from models import BarEvent

logger = logging.getLogger(__name__)


class SimulatedExecution(BaseExecution):
    """
    Simulates order fills for backtesting.

    Fill rules:
    - MARKET orders: filled at the open of the next bar after the signal.
    - PENDING orders: triggered when the bar's range (high/low) touches entry_price.
    - SL/TP: checked on every subsequent bar using high/low. If both SL and TP are
      touched in the same bar, SL is assumed hit first (conservative assumption).
    - Newly opened positions are not checked for SL/TP on their opening bar.
    """

    def __init__(self, initial_balance: float, spread_pips: float = 1.0,
                 breakeven_at_r: float | None = None,
                 rr_ratio: float = config.DEFAULT_RR_RATIO,
                 commission_per_lot: float = config.COMMISSION_PER_LOT):
        self._balance = initial_balance
        self._spread_pips = spread_pips
        self._breakeven_at_r = breakeven_at_r
        self._rr_ratio = rr_ratio
        self._commission_per_lot = commission_per_lot
        self._pending: dict[int, dict] = {}   # ticket -> position (not yet filled)
        self._positions: dict[int, dict] = {} # ticket -> position (open/filled)
        self._closed_trades: list[dict] = []
        self._next_ticket = 1

    def place_order(
        self,
        symbol: str,
        direction: str,
        order_type: str,
        entry_price: float,
        lot_size: float,
        sl: float,
        tp: float,
        strategy_name: str,
    ) -> int:
        ticket = self._next_ticket
        self._next_ticket += 1
        self._pending[ticket] = {
            'ticket':        ticket,
            'symbol':        symbol,
            'direction':     direction,
            'order_type':    order_type,
            'entry_price':   entry_price,
            'lot_size':      lot_size,
            'sl':            sl,
            'tp':            tp,
            'strategy_name': strategy_name,
        }
        return ticket

    def check_fills(self, bar: BarEvent) -> list[dict]:
        """
        Called at the start of each bar. Handles fills and SL/TP checks.
        Returns a list of closed trade result dicts for trades closed this bar.
        """
        closed = []
        just_opened = set()

        # 1. Fill MARKET orders placed on a previous bar — fill at this bar's open
        for ticket in list(self._pending):
            pos = self._pending[ticket]
            if pos['symbol'] == bar.symbol and pos['order_type'] == 'MARKET':
                pos['entry_price'] = self._apply_spread(bar.open, pos['symbol'], pos['direction'])
                self._recalc_tp(pos)
                pos['open_time'] = bar.timestamp
                self._positions[ticket] = self._pending.pop(ticket)
                just_opened.add(ticket)
                logger.debug(f"MARKET fill: {pos['symbol']} {pos['direction']} @ {pos['entry_price']:.5f} ticket={ticket}")

        # 2. Check PENDING limit/stop orders for this symbol
        for ticket in list(self._pending):
            pos = self._pending[ticket]
            if pos['symbol'] != bar.symbol:
                continue
            if bar.low <= pos['entry_price'] <= bar.high:
                pos['entry_price'] = self._apply_spread(pos['entry_price'], pos['symbol'], pos['direction'])
                pos['open_time'] = bar.timestamp
                self._positions[ticket] = self._pending.pop(ticket)
                just_opened.add(ticket)
                logger.debug(f"PENDING fill: {pos['symbol']} {pos['direction']} @ {pos['entry_price']:.5f} ticket={ticket}")

        # 3. Check open positions for SL/TP (skip positions just opened this bar)
        for ticket in list(self._positions):
            if ticket in just_opened:
                continue
            pos = self._positions[ticket]
            if pos['symbol'] != bar.symbol:
                continue
            result = self._check_sl_tp(pos, bar)
            if result:
                del self._positions[ticket]
                self._balance += result['pnl']
                self._closed_trades.append(result)
                closed.append(result)

        return closed

    def _check_sl_tp(self, pos: dict, bar: BarEvent) -> dict | None:
        """
        Returns a closed trade dict if SL or TP was hit, otherwise None.
        If both are hit in the same bar, SL is assumed to have been hit first.
        """
        # Break-even logic: move SL to entry once price reaches N×R in profit
        if self._breakeven_at_r is not None and not pos.get('_be_active'):
            sl_dist = abs(pos['entry_price'] - pos['sl'])
            be_target = sl_dist * self._breakeven_at_r
            if pos['direction'] == 'BUY':
                if bar.high >= pos['entry_price'] + be_target:
                    pos['_original_sl'] = pos['sl']
                    pos['sl'] = pos['entry_price']
                    pos['_be_active'] = True
            else:
                if bar.low <= pos['entry_price'] - be_target:
                    pos['_original_sl'] = pos['sl']
                    pos['sl'] = pos['entry_price']
                    pos['_be_active'] = True

        if pos['direction'] == 'BUY':
            sl_hit = bar.low <= pos['sl']
            tp_hit = bar.high >= pos['tp']
            if sl_hit:
                exit_price = pos['sl']
                result = 'BE' if pos.get('_be_active') else 'LOSS'
            elif tp_hit:
                exit_price, result = pos['tp'], 'WIN'
            else:
                return None
        else:  # SELL
            sl_hit = bar.high >= pos['sl']
            tp_hit = bar.low <= pos['tp']
            if sl_hit:
                exit_price = pos['sl']
                result = 'BE' if pos.get('_be_active') else 'LOSS'
            elif tp_hit:
                exit_price, result = pos['tp'], 'WIN'
            else:
                return None

        pip_size  = config.PIP_SIZE.get(pos['symbol'], 0.0001)
        pip_value = config.PIP_VALUE_USD.get(pos['symbol'], 10.0)

        open_time = pos.get('open_time')
        duration_hours = round((bar.timestamp - open_time).total_seconds() / 3600, 1) if open_time else None

        if pos['direction'] == 'BUY':
            pips = (exit_price - pos['entry_price']) / pip_size
        else:
            pips = (pos['entry_price'] - exit_price) / pip_size

        commission = self._commission_per_lot * pos['lot_size']
        pnl = pips * pip_value * pos['lot_size'] - commission
        original_sl = pos.get('_original_sl', pos['sl'])
        sl_pips = abs(pos['entry_price'] - original_sl) / pip_size
        r_multiple = round(pips / sl_pips, 2) if sl_pips > 0 else 0.0

        return {
            'ticket':        pos['ticket'],
            'symbol':        pos['symbol'],
            'direction':     pos['direction'],
            'strategy_name': pos['strategy_name'],
            'entry_price':   pos['entry_price'],
            'exit_price':    exit_price,
            'sl':            original_sl,
            'tp':            pos['tp'],
            'sl_pips':        round(sl_pips, 1),
            'duration_hours': duration_hours,
            'lot_size':      pos['lot_size'],
            'result':        result,
            'r_multiple':    r_multiple,
            'pnl':           round(pnl, 2),
            'commission':    round(commission, 2),
            'open_time':     open_time,
            'close_time':    bar.timestamp,
        }

    def _recalc_tp(self, pos: dict):
        """Recalculate TP from actual fill price so R:R is measured from real entry."""
        sl_dist = abs(pos['entry_price'] - pos['sl'])
        if pos['direction'] == 'BUY':
            pos['tp'] = pos['entry_price'] + sl_dist * self._rr_ratio
        else:
            pos['tp'] = pos['entry_price'] - sl_dist * self._rr_ratio

    def _apply_spread(self, price: float, symbol: str, direction: str) -> float:
        pip_size = config.PIP_SIZE.get(symbol, 0.0001)
        spread_price = self._spread_pips * pip_size
        return price + spread_price if direction == 'BUY' else price - spread_price

    def close_order(self, ticket_id: int) -> bool:
        if ticket_id in self._positions:
            del self._positions[ticket_id]
            return True
        if ticket_id in self._pending:
            del self._pending[ticket_id]
            return True
        return False

    def get_open_positions(self) -> list[dict]:
        return list(self._positions.values()) + list(self._pending.values())

    def get_account_balance(self) -> float:
        return self._balance

    def get_closed_trades(self) -> list[dict]:
        return list(self._closed_trades)
