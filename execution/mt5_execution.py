import logging
import re
from datetime import datetime, timedelta, timezone
from math import floor

import MetaTrader5 as mt5

from execution.base_execution import BaseExecution

logger = logging.getLogger(__name__)

_SL_COMMENT_RE = re.compile(r'\[sl\s+([0-9]+(?:\.[0-9]+)?)\]', re.IGNORECASE)

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
        self._last_order_details: dict | None = None

    @staticmethod
    def _round_to_step(value: float, step: float) -> float:
        if step <= 0:
            return value
        return round(round(value / step) * step, 10)

    @staticmethod
    def _last_error_text() -> str:
        try:
            return str(mt5.last_error())
        except Exception as exc:
            return f"last_error unavailable: {exc}"

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
        spread_pips = None
        info_point = config_pip_size = None
        try:
            from config import PIP_SIZE
            config_pip_size = PIP_SIZE.get(symbol)
            if config_pip_size:
                spread_pips = (tick.ask - tick.bid) / config_pip_size
        except Exception:
            spread_pips = None

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
            logger.error(
                f"Order failed for {symbol}: retcode={code} {comment} "
                f"last_error={self._last_error_text()}"
            )
            return 0

        fill_price = getattr(result, 'price', None) or price
        self._last_order_details = {
            'ticket': result.order,
            'deal': getattr(result, 'deal', 0),
            'fill_price': fill_price,
            'request_price': price,
            'bid': getattr(tick, 'bid', None),
            'ask': getattr(tick, 'ask', None),
            'spread_pips': round(spread_pips, 2) if spread_pips is not None else '',
        }
        logger.info(f"Order placed: {symbol} {direction} {order_type} ticket={result.order}")
        return result.order

    def get_last_order_details(self) -> dict | None:
        return self._last_order_details

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
                comment = result.comment if result else ''
                logger.error(
                    f"Cancel pending order failed for ticket {ticket_id}: "
                    f"retcode={code} {comment} last_error={self._last_error_text()}"
                )
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
            logger.error(f"Close failed for ticket {ticket_id}: {result} last_error={self._last_error_text()}")
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

    @staticmethod
    def _valid_price(value) -> float | None:
        try:
            price = float(value)
        except (TypeError, ValueError):
            return None
        return price if price > 0 else None

    @staticmethod
    def _dedupe_history(items) -> list:
        unique = {}
        for item in items or ():
            key = getattr(item, 'ticket', None)
            if key is None:
                key = (
                    getattr(item, 'time_msc', getattr(item, 'time', 0)),
                    getattr(item, 'order', None),
                    getattr(item, 'entry', None),
                )
            unique[key] = item
        return list(unique.values())

    def _get_position_deals(
        self,
        position_id,
        identifiers: set,
        symbol: str | None,
        start: datetime,
        end: datetime,
    ) -> list:
        if position_id not in (None, 0, ''):
            try:
                deals = mt5.history_deals_get(position=int(position_id))
            except (TypeError, ValueError):
                deals = None
            if deals:
                return self._dedupe_history(deals)

        deals = [
            deal for deal in (mt5.history_deals_get(start, end) or ())
            if not symbol or getattr(deal, 'symbol', symbol) == symbol
        ]
        matched_position_ids = {
            getattr(deal, 'position_id', None)
            for deal in deals
            if not identifiers.isdisjoint({
                getattr(deal, 'position_id', None),
                getattr(deal, 'order', None),
                getattr(deal, 'ticket', None),
            })
            and getattr(deal, 'position_id', None) not in (None, 0, '')
        }
        matching = []
        for deal in deals:
            deal_ids = {
                getattr(deal, 'position_id', None),
                getattr(deal, 'order', None),
                getattr(deal, 'ticket', None),
            }
            if (
                not identifiers.isdisjoint(deal_ids)
                or getattr(deal, 'position_id', None) in matched_position_ids
            ):
                matching.append(deal)
        return self._dedupe_history(matching)

    def _get_original_order(self, position_id, ticket, symbol: str | None):
        queries = []
        if position_id not in (None, 0, ''):
            try:
                queries.append({'position': int(position_id)})
            except (TypeError, ValueError):
                pass
        if ticket not in (None, 0, ''):
            try:
                queries.append({'ticket': int(ticket)})
            except (TypeError, ValueError):
                pass

        orders = []
        for query in queries:
            try:
                result = mt5.history_orders_get(**query)
            except (AttributeError, TypeError, ValueError):
                result = None
            if result:
                orders.extend(result)

        candidates = [
            order for order in self._dedupe_history(orders)
            if (not symbol or getattr(order, 'symbol', symbol) == symbol)
            and self._valid_price(getattr(order, 'sl', None)) is not None
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda order: getattr(
                order,
                'time_setup_msc',
                getattr(order, 'time_setup', getattr(order, 'time_done', 0)),
            ),
        )

    def _entry_price_from_deals(self, deals: list) -> float | None:
        entry_values = {
            getattr(mt5, 'DEAL_ENTRY_IN', 0),
            getattr(mt5, 'DEAL_ENTRY_INOUT', 2),
        }
        entries = [
            deal for deal in deals
            if getattr(deal, 'entry', None) in entry_values
            and self._valid_price(getattr(deal, 'price', None)) is not None
        ]
        total_volume = sum(float(getattr(deal, 'volume', 0.0)) for deal in entries)
        if total_volume > 0:
            return sum(
                float(deal.price) * float(getattr(deal, 'volume', 0.0))
                for deal in entries
            ) / total_volume
        if entries:
            return float(entries[0].price)
        return None

    def get_recent_closed_trade(self, tracked_pos: dict, lookback_days: int = 14) -> dict | None:
        """Return realized close details for a recently closed bot-owned position/order."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=lookback_days)

        ticket = tracked_pos.get('ticket')
        position_id = tracked_pos.get('position_id') or ticket
        strategy_name = tracked_pos.get('strategy_name') or tracked_pos.get('comment') or ''
        symbol = tracked_pos.get('symbol')

        identifiers = {
            value for value in (ticket, position_id)
            if value not in (None, 0, '')
        }

        matching = self._get_position_deals(position_id, identifiers, symbol, start, now)
        if not matching:
            return None

        exit_entries = {
            getattr(mt5, 'DEAL_ENTRY_OUT', 1),
            getattr(mt5, 'DEAL_ENTRY_OUT_BY', 3),
        }
        exit_deals = [d for d in matching if getattr(d, 'entry', None) in exit_entries]
        if not exit_deals:
            return None

        # Net the full matched deal set, not only the exit deals. Entry commissions
        # are charged on the entry deal while realized price P/L appears on exit.
        pnl = sum(
            float(getattr(d, 'profit', 0.0))
            + float(getattr(d, 'commission', 0.0))
            + float(getattr(d, 'swap', 0.0))
            + float(getattr(d, 'fee', 0.0))
            for d in matching
        )
        commission = sum(float(getattr(d, 'commission', 0.0)) for d in matching)
        swap = sum(float(getattr(d, 'swap', 0.0)) for d in matching)
        fee = sum(float(getattr(d, 'fee', 0.0)) for d in matching)
        latest = max(exit_deals, key=lambda d: getattr(d, 'time', 0))
        exit_price = float(getattr(latest, 'price', 0.0))
        entry_price = self._valid_price(tracked_pos.get('open_price'))
        if entry_price is None:
            entry_price = self._entry_price_from_deals(matching)

        sl = self._valid_price(tracked_pos.get('sl'))
        tp = self._valid_price(tracked_pos.get('tp'))
        r_source = 'tracked_position'
        if sl is None:
            original_order = self._get_original_order(position_id, ticket, symbol)
            if original_order is not None:
                sl = self._valid_price(getattr(original_order, 'sl', None))
                tp = tp or self._valid_price(getattr(original_order, 'tp', None))
                r_source = 'order_history'

        close_reason = getattr(latest, 'comment', '')
        if sl is None:
            sl_match = _SL_COMMENT_RE.search(str(close_reason))
            if sl_match:
                sl = self._valid_price(sl_match.group(1))
                r_source = 'sl_comment'

        direction = tracked_pos.get('direction', '')
        r_multiple = None
        if entry_price is not None and sl is not None:
            if direction == 'BUY':
                risk = entry_price - sl
                move = exit_price - entry_price
            else:
                risk = sl - entry_price
                move = entry_price - exit_price
            if risk > 0:
                r_multiple = round(move / risk, 2)

        result = 'WIN' if pnl > 0 else ('BE' if pnl == 0 else 'LOSS')
        return {
            'ticket': ticket,
            'symbol': symbol or getattr(latest, 'symbol', ''),
            'direction': direction,
            'strategy_name': strategy_name,
            'result': result,
            'pnl': round(pnl, 2),
            'close_time': datetime.fromtimestamp(getattr(latest, 'time', 0), tz=timezone.utc),
            'r_multiple': r_multiple,
            'r_source': r_source if r_multiple is not None else 'unavailable',
            'entry_price': entry_price or '',
            'exit_price': exit_price,
            'sl': sl or '',
            'tp': tp or '',
            'lot_size': tracked_pos.get('volume', ''),
            'commission': round(commission, 2),
            'swap': round(swap, 2),
            'fee': round(fee, 2),
            'close_reason': close_reason,
        }
