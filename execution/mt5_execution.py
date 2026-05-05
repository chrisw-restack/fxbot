import logging
from datetime import datetime, timedelta, timezone
from math import floor

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

    @staticmethod
    def _round_to_step(value: float, step: float) -> float:
        if step <= 0:
            return value
        return round(round(value / step) * step, 10)

    def _normalize_volume(self, symbol: str, volume: float) -> float:
        info = mt5.symbol_info(symbol)
        if info is None:
            return volume
        step = getattr(info, 'volume_step', 0.01) or 0.01
        min_vol = getattr(info, 'volume_min', step) or step
        max_vol = getattr(info, 'volume_max', volume) or volume
        # Round down so risk is not accidentally increased by broker volume steps.
        normalized = floor(volume / step) * step
        normalized = max(min_vol, min(max_vol, normalized))
        return round(normalized, 10)

    def _normalize_price(self, symbol: str, price: float) -> float:
        info = mt5.symbol_info(symbol)
        if info is None:
            return price
        tick_size = getattr(info, 'trade_tick_size', 0.0) or getattr(info, 'point', 0.0)
        digits = getattr(info, 'digits', 5)
        if tick_size:
            price = self._round_to_step(price, tick_size)
        return round(price, digits)

    def _normalize_request_prices(self, symbol: str, request: dict) -> dict:
        for field in ('price', 'sl', 'tp'):
            if field in request and request[field]:
                request[field] = self._normalize_price(symbol, request[field])
        return request

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
        info = mt5.symbol_info(symbol)
        if info is None:
            logger.error(f"Could not get symbol info for {symbol}")
            return 0
        if not getattr(info, 'visible', True):
            mt5.symbol_select(symbol, True)

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
            'volume':       self._normalize_volume(symbol, lot_size),
            'type':         mt5_type,
            'price':        price,
            'sl':           sl,
            'tp':           tp,
            'magic':        magic,
            'comment':      strategy_name,
            'type_time':    mt5.ORDER_TIME_GTC,
            'type_filling': mt5.ORDER_FILLING_IOC,
        }
        request = self._normalize_request_prices(symbol, request)

        result = mt5.order_send(request)
        success_codes = {mt5.TRADE_RETCODE_DONE}
        if order_type != 'MARKET' and hasattr(mt5, 'TRADE_RETCODE_PLACED'):
            success_codes.add(mt5.TRADE_RETCODE_PLACED)
        if result is None or result.retcode not in success_codes:
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
                    'swap':          p.swap,
                    'magic':         p.magic,
                    'comment':       p.comment,
                    'strategy_name': p.comment,
                    'position_id':   getattr(p, 'identifier', p.ticket),
                    'state':         'OPEN',
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
                    'swap':          0.0,
                    'magic':         o.magic,
                    'comment':       o.comment,
                    'strategy_name': o.comment,
                    'position_id':   getattr(o, 'position_id', 0),
                    'state':         'PENDING',
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

    def get_recent_closed_trade(self, tracked_pos: dict, lookback_days: int = 14) -> dict | None:
        """Return realized close details for a recently closed bot-owned position/order."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=lookback_days)
        deals = mt5.history_deals_get(start, now)
        if not deals:
            return None

        ticket = tracked_pos.get('ticket')
        position_id = tracked_pos.get('position_id') or ticket
        strategy_name = tracked_pos.get('strategy_name') or tracked_pos.get('comment') or ''
        symbol = tracked_pos.get('symbol')

        matching = []
        for d in deals:
            if self._known_magic and getattr(d, 'magic', 0) not in self._known_magic:
                continue
            if strategy_name and getattr(d, 'comment', strategy_name) not in ('', strategy_name):
                continue
            if symbol and getattr(d, 'symbol', symbol) != symbol:
                continue
            deal_position_id = getattr(d, 'position_id', None)
            deal_order = getattr(d, 'order', None)
            deal_ticket = getattr(d, 'ticket', None)
            if position_id not in (deal_position_id, deal_order, deal_ticket) and ticket not in (
                deal_position_id, deal_order, deal_ticket,
            ):
                continue
            matching.append(d)

        if not matching:
            return None

        exit_entries = {
            getattr(mt5, 'DEAL_ENTRY_OUT', 1),
            getattr(mt5, 'DEAL_ENTRY_OUT_BY', 3),
        }
        exit_deals = [d for d in matching if getattr(d, 'entry', None) in exit_entries]
        if not exit_deals:
            return None

        pnl = sum(
            float(getattr(d, 'profit', 0.0))
            + float(getattr(d, 'commission', 0.0))
            + float(getattr(d, 'swap', 0.0))
            + float(getattr(d, 'fee', 0.0))
            for d in exit_deals
        )
        latest = max(exit_deals, key=lambda d: getattr(d, 'time', 0))
        result = 'WIN' if pnl > 0 else ('BE' if pnl == 0 else 'LOSS')
        return {
            'ticket': ticket,
            'symbol': symbol or getattr(latest, 'symbol', ''),
            'direction': tracked_pos.get('direction', ''),
            'strategy_name': strategy_name,
            'result': result,
            'pnl': round(pnl, 2),
            'close_time': datetime.fromtimestamp(getattr(latest, 'time', 0), tz=timezone.utc),
            'r_multiple': 0.0,
        }
