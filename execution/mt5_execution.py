import logging
from datetime import datetime, timezone

import MetaTrader5 as mt5

from execution.base_execution import BaseExecution

logger = logging.getLogger(__name__)

MT5_TIMEFRAME_MAP = {
    'M5':  mt5.TIMEFRAME_M5,
    'M15': mt5.TIMEFRAME_M15,
    'H1':  mt5.TIMEFRAME_H1,
    'H4':  mt5.TIMEFRAME_H4,
    'D1':  mt5.TIMEFRAME_D1,
}


class MT5Execution(BaseExecution):

    def __init__(self, magic_numbers: dict[str, int] | None = None):
        """
        magic_numbers: maps strategy NAME → MT5 magic integer.
        When provided, every order is tagged and get_open_positions filters
        to only return positions belonging to this bot.
        """
        self._magic_numbers = magic_numbers or {}
        self._known_magic: set[int] = set(self._magic_numbers.values())

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
        entry_timeframe: str | None = None,  # informational — MT5 handles fills natively
        tp_locked: bool = False,              # informational — MT5 uses the tp price directly
        signal_time=None,                     # informational — not used by MT5 execution
    ) -> int:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error(f"Could not get tick for {symbol}")
            return 0

        if order_type == 'MARKET':
            action = mt5.TRADE_ACTION_DEAL
            price = tick.ask if direction == 'BUY' else tick.bid
            mt5_type = mt5.ORDER_TYPE_BUY if direction == 'BUY' else mt5.ORDER_TYPE_SELL
        else:
            # PENDING — infer subtype from direction vs. current price
            action = mt5.TRADE_ACTION_PENDING
            price = entry_price
            current = tick.ask if direction == 'BUY' else tick.bid
            if direction == 'BUY':
                mt5_type = mt5.ORDER_TYPE_BUY_STOP if entry_price > current else mt5.ORDER_TYPE_BUY_LIMIT
            else:
                mt5_type = mt5.ORDER_TYPE_SELL_STOP if entry_price < current else mt5.ORDER_TYPE_SELL_LIMIT

        magic = self._magic_numbers.get(strategy_name, 0)
        if magic == 0 and self._magic_numbers:
            logger.warning(f"No magic number configured for strategy '{strategy_name}' — using 0")

        request = {
            'action':       action,
            'symbol':       symbol,
            'volume':       lot_size,
            'type':         mt5_type,
            'price':        price,
            'sl':           sl,
            'tp':           tp,
            'magic':        magic,
            'comment':      strategy_name,
            'type_time':    mt5.ORDER_TIME_GTC,
            'type_filling': mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            code = result.retcode if result else 'None'
            comment = result.comment if result else ''
            logger.error(f"Order failed for {symbol}: retcode={code} {comment}")
            return 0

        logger.info(f"Order placed: {symbol} {direction} {order_type} ticket={result.order}")
        return result.order

    def close_order(self, ticket_id: int) -> bool:
        # Cancel a pending order if it exists
        orders = mt5.orders_get(ticket=ticket_id)
        if orders:
            request = {
                'action': mt5.TRADE_ACTION_REMOVE,
                'order':  ticket_id,
            }
            result = mt5.order_send(request)
            if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
                code = result.retcode if result else 'None'
                logger.error(f"Cancel pending order failed for ticket {ticket_id}: retcode={code}")
                return False
            logger.info(f"Pending order cancelled: ticket={ticket_id}")
            return True

        # Otherwise close a filled position
        positions = mt5.positions_get(ticket=ticket_id)
        if not positions:
            logger.warning(f"No open position or pending order found for ticket {ticket_id}")
            return False

        pos = positions[0]
        close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        tick = mt5.symbol_info_tick(pos.symbol)
        price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask

        request = {
            'action':       mt5.TRADE_ACTION_DEAL,
            'position':     ticket_id,
            'symbol':       pos.symbol,
            'volume':       pos.volume,
            'type':         close_type,
            'price':        price,
            'type_filling': mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Close failed for ticket {ticket_id}: {result}")
            return False
        return True

    def get_open_positions(self) -> list[dict]:
        result = []

        # Filled/open positions — filter to bot-owned trades when magic numbers are configured
        positions = mt5.positions_get()
        if positions:
            result.extend([
                {
                    'ticket':        p.ticket,
                    'symbol':        p.symbol,
                    'direction':     'BUY' if p.type == mt5.ORDER_TYPE_BUY else 'SELL',
                    'volume':        p.volume,
                    'open_price':    p.price_open,
                    'sl':            p.sl,
                    'tp':            p.tp,
                    'profit':        p.profit,
                    'comment':       p.comment,
                    'strategy_name': p.comment,
                    'open_time':     datetime.fromtimestamp(p.time, tz=timezone.utc),
                }
                for p in positions
                if not self._known_magic or p.magic in self._known_magic
            ])

        # Pending (unfilled) orders — included so _handle_cancel can find and delete them
        orders = mt5.orders_get()
        if orders:
            result.extend([
                {
                    'ticket':        o.ticket,
                    'symbol':        o.symbol,
                    'direction':     'BUY' if o.type in (
                        mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_BUY_STOP,
                    ) else 'SELL',
                    'volume':        o.volume_current,
                    'open_price':    o.price_open,
                    'sl':            o.sl,
                    'tp':            o.tp,
                    'profit':        0.0,
                    'comment':       o.comment,
                    'strategy_name': o.comment,
                    # No open_time key — _handle_cancel uses open_time is None to
                    # identify pending orders
                }
                for o in orders
                if not self._known_magic or o.magic in self._known_magic
            ])

        return result

    def get_account_balance(self) -> float:
        info = mt5.account_info()
        return info.balance if info else 0.0
