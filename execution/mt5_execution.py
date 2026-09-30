import logging
import re
import time
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import config
from risk.validation import positive, valid_levels, valid_stop_distance, floor_volume

import MetaTrader5 as mt5

from data.mt5_data import mt5_time_to_utc, validate_demo_account
from execution.base_execution import BaseExecution
from utils.setup_ledger import SetupLedger

logger = logging.getLogger(__name__)

_SL_COMMENT_RE = re.compile(r'\[sl\s+([0-9]+(?:\.[0-9]+)?)\]', re.IGNORECASE)
# IC Markets accepted 23-character comments but rejected 30-character comments.
# Keep a little margin because MetaTrader limits can vary by terminal/broker build.
MT5_ORDER_COMMENT_MAX_CHARS = 20

MT5_TIMEFRAME_MAP = {
    'M5':  mt5.TIMEFRAME_M5,
    'M15': mt5.TIMEFRAME_M15,
    'H1':  mt5.TIMEFRAME_H1,
    'H4':  mt5.TIMEFRAME_H4,
    'D1':  mt5.TIMEFRAME_D1,
}


class MT5Execution(BaseExecution):

    def __init__(self, magic_numbers: dict[str, int] | None = None, expected_account=None, setup_ledger=None):
        """
        magic_numbers: maps strategy NAME → MT5 magic integer.
        When provided, every order is tagged and get_open_positions filters
        to only return positions belonging to this bot.
        """
        self._magic_numbers = magic_numbers or {}
        self._expected_account = expected_account
        self.setup_ledger = setup_ledger if setup_ledger is not None else SetupLedger()
        if len(set(self._magic_numbers.values())) != len(self._magic_numbers):
            raise ValueError("MT5 magic numbers must be unique per strategy")
        self._known_magic: set[int] = set(self._magic_numbers.values())
        self._strategy_by_magic = {
            magic: strategy_name
            for strategy_name, magic in self._magic_numbers.items()
        }
        self._last_order_details: dict | None = None
        self._last_order_error: dict | None = None
        self._last_cancel_error: dict | None = None

    def strategy_name_for_magic(self, magic: int, broker_comment: str = '') -> str:
        """Resolve canonical strategy identity from the non-truncated magic tag."""
        return self._strategy_by_magic.get(magic, broker_comment)

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

    @staticmethod
    def _broker_order_comment(strategy_name: str) -> str:
        """Return an MT5-safe diagnostic comment; magic remains canonical identity."""
        sanitized = ''.join(
            ch if 32 <= ord(ch) < 127 else '_'
            for ch in (strategy_name or '')
        )
        sanitized = sanitized.strip() or 'fxbot'
        return sanitized[:MT5_ORDER_COMMENT_MAX_CHARS]

    @staticmethod
    def _mt5_timestamp_utc(timestamp: int | float) -> datetime:
        """Convert IC Markets' server-wall-clock timestamp to aware UTC."""
        converted = mt5_time_to_utc(timestamp)
        if converted.tzinfo is None:
            return converted.replace(tzinfo=timezone.utc)
        return converted.astimezone(timezone.utc)

    def _normalize_volume(self, symbol: str, volume: float) -> float:
        info = mt5.symbol_info(symbol)
        if info is None:
            raise RuntimeError(f'MT5 volume rules unavailable: {symbol}')
        step = getattr(info, 'volume_step', 0.01) or 0.01
        min_vol = getattr(info, 'volume_min', step) or step
        max_vol = getattr(info, 'volume_max', volume) or volume
        # Round down so risk is not accidentally increased by broker volume steps.
        return floor_volume(volume, step, min_vol, max_vol)

    def volume_limits(self, symbol: str) -> dict:
        info = mt5.symbol_info(symbol)
        if info is None:
            raise RuntimeError(f'MT5 symbol information unavailable: {symbol}')
        return dict(step=info.volume_step, minimum=info.volume_min, maximum=info.volume_max)

    def signal_entry_price(self, signal) -> float:
        if signal.order_type != 'MARKET':
            return self._normalize_price(signal.symbol, signal.entry_price)
        tick = mt5.symbol_info_tick(signal.symbol)
        if tick is None or not positive(tick.ask) or not positive(tick.bid):
            raise RuntimeError(f'MT5 quote unavailable: {signal.symbol}')
        return tick.ask if signal.direction == 'BUY' else tick.bid

    def loss_per_lot(self, symbol, direction, entry, sl) -> float:
        order_type = mt5.ORDER_TYPE_BUY if direction == 'BUY' else mt5.ORDER_TYPE_SELL
        loss = mt5.order_calc_profit(order_type, symbol, 1.0, entry, sl)
        if loss is None or not positive(-loss):
            raise RuntimeError(f'MT5 stop-risk calculation failed: {symbol}')
        return -loss

    def get_daily_loss(self, now: datetime) -> float:
        """Gross losing position cash flows realized today, including deal costs.

        Query a padded server-time window, then filter converted UTC timestamps.
        Group partial deals by position; do not confuse a failed query with zero loss.
        """
        deals = mt5.history_deals_get(now - timedelta(days=2), now + timedelta(days=1))
        if deals is None:
            raise RuntimeError(f'MT5 daily deal history unavailable: {self._last_error_text()}')
        pnl_by_position = defaultdict(float)
        seen = set()
        for deal in deals:
            if deal.ticket in seen:
                continue
            seen.add(deal.ticket)
            if self._known_magic and deal.magic not in self._known_magic:
                continue
            if deal.type not in (mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_SELL):
                continue
            timestamp = self._mt5_timestamp_utc(deal.time)
            if timestamp.date() != now.date() or timestamp > now:
                continue
            pnl_by_position[deal.position_id] += sum(
                getattr(deal, field, 0.0) for field in ('profit', 'swap', 'commission', 'fee')
            )
        return sum(-pnl for pnl in pnl_by_position.values() if pnl < 0)

    def _normalize_price(self, symbol: str, price: float) -> float:
        info = mt5.symbol_info(symbol)
        if info is None:
            raise RuntimeError(f'MT5 price rules unavailable: {symbol}')
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
        risk_budget: float | None = None,
        setup_id: str | None = None,
        attempt_id: str | None = None,
        min_stop_distance: float | None = None,
    ) -> int:
        self._last_order_details = None
        self._last_order_error = None
        if self._expected_account is not None:
            validate_demo_account(mt5.account_info(), **self._expected_account)
        if order_type not in ('MARKET', 'PENDING') or not valid_levels(
            direction, entry_price, sl, tp, config.MIN_RR_RATIO
        ) or not positive(lot_size):
            self._last_order_error = {'stage': 'risk_validation', 'broker_comment': 'invalid order levels or volume'}
            return 0
        info = mt5.symbol_info(symbol)
        if info is None:
            logger.error(f"Could not get symbol info for {symbol}")
            self._last_order_error = {
                'stage': 'symbol_info',
                'symbol': symbol,
                'last_error': self._last_error_text(),
            }
            return 0
        if not getattr(info, 'visible', True):
            mt5.symbol_select(symbol, True)

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error(f"Could not get tick for {symbol}")
            self._last_order_error = {
                'stage': 'symbol_info_tick',
                'symbol': symbol,
                'last_error': self._last_error_text(),
            }
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
            'comment':      self._broker_order_comment(strategy_name),
            'type_time':    mt5.ORDER_TIME_GTC,
            'type_filling': mt5.ORDER_FILLING_IOC,
        }
        request = self._normalize_request_prices(symbol, request)

        # Refresh R:R and size using the actual request, after broker rounding.
        if order_type == 'MARKET' and not tp_locked:
            rr = abs(tp - entry_price) / abs(entry_price - sl)
            distance = abs(request['price'] - request['sl']) * rr
            request['tp'] = self._normalize_price(
                symbol, request['price'] + distance if direction == 'BUY' else request['price'] - distance
            )
        if not valid_levels(direction, request['price'], request['sl'], request['tp'], config.MIN_RR_RATIO):
            self._last_order_error = {'stage': 'risk_validation', 'broker_comment': 'executable levels violate minimum R:R'}
            return 0
        if not valid_stop_distance(request['price'], request['sl'], min_stop_distance):
            self._last_order_error = {'stage': 'risk_validation',
                'broker_comment': 'executable stop distance below strategy minimum',
                'min_stop_distance': min_stop_distance,
                'actual_stop_distance': abs(request['price']-request['sl'])}
            return 0
        if risk_budget is not None:
            if not positive(risk_budget):
                return 0
            loss = self.loss_per_lot(symbol, direction, request['price'], request['sl'])
            request['volume'] = self._normalize_volume(symbol, min(lot_size, risk_budget / loss))
        if not positive(request['volume']):
            self._last_order_error = {'stage': 'risk_validation', 'broker_comment': 'minimum lot exceeds risk budget'}
            return 0

        if setup_id:
            if any(r['symbol'] == symbol and r['strategy_name'] == strategy_name
                   for r in self.setup_ledger.pending_intents().values()):
                raise RuntimeError('Unresolved broker submission in this strategy slot; reconcile before submitting')
            # Persist identity before the external side effect. An exact comment
            # match can recover an acknowledgement lost to a process crash.
            request['comment'] = self.setup_ledger.prepare(setup_id=setup_id, attempt_id=attempt_id,
                symbol=symbol, strategy_name=strategy_name, direction=direction,
                state='PENDING' if order_type == 'PENDING' else 'OPEN',
                submitted_tp=request['tp'], sl=request['sl'], tp=request['tp'],
                open_price=request['price'], volume=request['volume'])
        check_result = None
        if hasattr(mt5, 'order_check'):
            try:
                check_result = mt5.order_check(request)
            except Exception as exc:
                raise RuntimeError(f'MT5 order_check failed for {symbol}') from exc
            if check_result is None:
                raise RuntimeError(f'MT5 order_check unavailable for {symbol}')

        # A failed preflight is a rejected order, not permission to send it anyway.
        result = (check_result if check_result is not None and check_result.retcode != 0
                  else mt5.order_send(request))
        success_codes = {mt5.TRADE_RETCODE_DONE}
        if hasattr(mt5, 'TRADE_RETCODE_DONE_PARTIAL'):
            success_codes.add(mt5.TRADE_RETCODE_DONE_PARTIAL)
        if order_type != 'MARKET' and hasattr(mt5, 'TRADE_RETCODE_PLACED'):
            success_codes.add(mt5.TRADE_RETCODE_PLACED)

        invalid_fill = getattr(mt5, 'TRADE_RETCODE_INVALID_FILL', None)
        if result is not None and result.retcode == invalid_fill:
            filling_modes = [
                getattr(mt5, 'ORDER_FILLING_FOK', None),
                getattr(mt5, 'ORDER_FILLING_RETURN', None),
            ]
            for filling_mode in filling_modes:
                if filling_mode is None or filling_mode == request['type_filling']:
                    continue
                retry_request = dict(request, type_filling=filling_mode)
                retry_result = mt5.order_send(retry_request)
                if retry_result is not None:
                    result = retry_result
                    request = retry_request
                if result is not None and result.retcode in success_codes:
                    break
                if result is None or result.retcode != invalid_fill:
                    break

        if result is None or result.retcode not in success_codes:
            if setup_id and result is not None:
                self.setup_ledger.reject_intent(request['comment'])
            code = result.retcode if result else 'None'
            comment = result.comment if result else ''
            self._last_order_error = {
                'stage': 'order_send',
                'symbol': symbol,
                'strategy_name': strategy_name,
                'retcode': code,
                'broker_comment': comment,
                'last_error': self._last_error_text(),
                'request': {
                    'action': request.get('action'),
                    'type': request.get('type'),
                    'type_filling': request.get('type_filling'),
                    'volume': request.get('volume'),
                    'price': request.get('price'),
                    'sl': request.get('sl'),
                    'tp': request.get('tp'),
                    'magic': request.get('magic'),
                    'comment': request.get('comment'),
                },
                'bid': getattr(tick, 'bid', None),
                'ask': getattr(tick, 'ask', None),
                'trade_stops_level': getattr(info, 'trade_stops_level', None),
                'trade_freeze_level': getattr(info, 'trade_freeze_level', None),
                'symbol_filling_mode': getattr(info, 'filling_mode', None),
                'order_check_retcode': getattr(check_result, 'retcode', None),
                'order_check_comment': getattr(check_result, 'comment', ''),
            }
            logger.error(
                f"Order failed for {symbol}: retcode={code} {comment} "
                f"last_error={self._last_error_text()} "
                f"request={self._last_order_error['request']}"
            )
            return 0

        reported_fill = getattr(result, 'price', None)
        fill_price = reported_fill if positive(reported_fill) else request['price']
        fill_risk = abs(fill_price - request['sl'])
        fill_reward = request['tp'] - fill_price if direction == 'BUY' else fill_price - request['tp']
        fill_rr = fill_reward / fill_risk if fill_risk else 0.0
        if order_type == 'MARKET' and fill_rr + 1e-10 < config.MIN_RR_RATIO:
            logger.error('Actual fill R:R below minimum: %s ticket=%s rr=%s', symbol, result.order, fill_rr)
        fill_stop_valid = valid_levels(direction, fill_price, request['sl']) and valid_stop_distance(
            fill_price, request['sl'], min_stop_distance)
        if order_type == 'MARKET' and not positive(reported_fill):
            fill_stop_valid = None  # The request quote is not proof of a broker fill.
            if min_stop_distance is not None:
                logger.warning('Actual fill price unavailable for stop validation: %s ticket=%s',
                               symbol, result.order)
        if order_type == 'MARKET' and fill_stop_valid is False:
            logger.error('Actual fill stop distance below strategy minimum: %s ticket=%s distance=%s minimum=%s',
                         symbol, result.order, fill_risk, min_stop_distance)
        self._last_order_details = {
            'ticket': result.order,
            'deal': getattr(result, 'deal', 0),
            'fill_price': fill_price,
            'request_price': request['price'],
            'fill_price_source': 'broker' if positive(reported_fill) else 'request',
            'volume': getattr(result, 'volume', 0) or request['volume'],
            'sl': request['sl'],
            'tp': request['tp'],
            'fill_rr': fill_rr,
            'min_stop_distance': min_stop_distance,
            'fill_stop_distance_valid': fill_stop_valid,
            'actual_stop_distance': abs(reported_fill-request['sl']) if positive(reported_fill) else None,
            'risk_budget': risk_budget,
            'bid': getattr(tick, 'bid', None),
            'ask': getattr(tick, 'ask', None),
            'spread_pips': round(spread_pips, 2) if spread_pips is not None else '',
        }
        self.setup_ledger.accept(result.order, setup_id=setup_id, attempt_id=attempt_id,
            symbol=symbol, strategy_name=strategy_name, direction=direction,
            state='PENDING' if order_type == 'PENDING' else 'OPEN',
            submitted_tp=request['tp'], sl=request['sl'], tp=request['tp'],
            open_price=fill_price, volume=self._last_order_details['volume'])
        logger.info(f"Order placed: {symbol} {direction} {order_type} ticket={result.order}")
        return result.order

    def get_last_order_details(self) -> dict | None:
        return self._last_order_details

    def get_last_order_error(self) -> dict | None:
        return self._last_order_error

    def get_last_cancel_error(self) -> dict | None:
        return self._last_cancel_error

    def cancel_pending_order(self, ticket_id: int) -> bool:
        """Cancel only an active pending order; never close a filled position."""
        self._last_cancel_error = None
        orders = mt5.orders_get(ticket=ticket_id)
        if orders is None:
            self._last_cancel_error = {
                'ticket': ticket_id,
                'retcode': '',
                'broker_comment': 'orders_get failed before cancellation',
                'last_error': self._last_error_text(),
            }
            logger.error(
                f"Could not inspect pending order ticket={ticket_id}: "
                f"last_error={self._last_error_text()}"
            )
            return False
        if not orders:
            self._last_cancel_error = {
                'ticket': ticket_id, 'retcode': '',
                'broker_comment': 'pending order is no longer active',
                'last_error': self._last_error_text(),
            }
            return False

        request = {
            'action': mt5.TRADE_ACTION_REMOVE,
            'order':  ticket_id,
        }
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            code = result.retcode if result else 'None'
            comment = result.comment if result else ''
            self._last_cancel_error = {
                'ticket': ticket_id,
                'retcode': code,
                'broker_comment': comment,
                'last_error': self._last_error_text(),
            }
            logger.error(
                f"Cancel pending order failed for ticket {ticket_id}: "
                f"retcode={code} {comment} last_error={self._last_error_text()}"
            )
            return False
        for _ in range(8):
            remaining = mt5.orders_get(ticket=ticket_id)
            if remaining is not None and not remaining:
                logger.info(f"Pending order cancelled: ticket={ticket_id}")
                return True
            time.sleep(0.25)
        self._last_cancel_error = {
            'ticket': ticket_id,
            'retcode': getattr(result, 'retcode', ''),
            'broker_comment': 'broker did not confirm order removal',
            'last_error': self._last_error_text(),
        }
        logger.error(f"Cancellation not confirmed by broker for ticket={ticket_id}")
        return False

    def close_order(self, ticket_id: int) -> bool:
        # Preserve the general close API for explicit/manual use.
        orders = mt5.orders_get(ticket=ticket_id)
        if orders is None:
            self._last_cancel_error = {
                'ticket': ticket_id, 'retcode': '',
                'broker_comment': 'orders_get failed before close',
                'last_error': self._last_error_text(),
            }
            return False
        if orders:
            return self.cancel_pending_order(ticket_id)

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
        if positions is None:
            raise RuntimeError(f'MT5 position query failed: {self._last_error_text()}')
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
                    'broker_comment': p.comment,
                    'strategy_name': self.strategy_name_for_magic(p.magic, p.comment),
                    'position_id':   getattr(p, 'identifier', p.ticket),
                    'state':         'OPEN',
                    'open_time':     self._mt5_timestamp_utc(p.time),
                }
                for p in positions
                if not self._known_magic or p.magic in self._known_magic
            ])

        # Pending entry orders — included so _handle_cancel can find and delete them.
        # Broker-generated close orders, such as temporary SL/TP market orders, are
        # not strategy slots and must not be tracked as separate positions.
        orders = mt5.orders_get()
        if orders is None:
            raise RuntimeError(f'MT5 order query failed: {self._last_error_text()}')
        if orders:
            buy_pending_types = {
                mt5.ORDER_TYPE_BUY_LIMIT,
                mt5.ORDER_TYPE_BUY_STOP,
            }
            sell_pending_types = {
                mt5.ORDER_TYPE_SELL_LIMIT,
                mt5.ORDER_TYPE_SELL_STOP,
            }
            pending_order_types = buy_pending_types | sell_pending_types
            result.extend([
                {
                    'ticket':        o.ticket,
                    'symbol':        o.symbol,
                    'direction':     'BUY' if o.type in buy_pending_types else 'SELL',
                    'volume':        o.volume_current,
                    'open_price':    o.price_open,
                    'sl':            o.sl,
                    'tp':            o.tp,
                    'profit':        0.0,
                    'swap':          0.0,
                    'magic':         o.magic,
                    'comment':       o.comment,
                    'broker_comment': o.comment,
                    'strategy_name': self.strategy_name_for_magic(o.magic, o.comment),
                    'position_id':   getattr(o, 'position_id', 0),
                    'state':         'PENDING',
                    # No open_time key — _handle_cancel uses open_time is None to
                    # identify pending orders
                }
                for o in orders
                if o.type in pending_order_types
                and (not self._known_magic or o.magic in self._known_magic)
            ])

        return [self._attach_setup_context(pos) for pos in result]

    def _attach_setup_context(self, pos, deals=None):
        # Older orders have no setup ID, but their entry deal can still prove an
        # order-to-position transition. This prevents matching unrelated trades
        # merely because they share a symbol and strategy.
        position_id = pos.get('position_id')
        if position_id and pos.get('state') == 'OPEN':
            origins = getattr(self, '_position_origin_orders', {})
            if position_id not in origins:
                history = getattr(mt5, 'history_deals_get', None)
                if deals is None and history is not None:
                    deals = history(position=int(position_id))
                tickets = {getattr(d, 'order', None) for d in deals or ()
                           if getattr(d, 'entry', None) == getattr(mt5, 'DEAL_ENTRY_IN', 0)} - {None, 0}
                if len(tickets) == 1:
                    origins[position_id] = next(iter(tickets))
                    self._position_origin_orders = origins
            if position_id in origins:
                pos = dict(pos, origin_order_ticket=origins[position_id])
        context = self.setup_ledger.context(pos)
        if not context and pos.get('state') == 'PENDING':
            context = self.setup_ledger.recover_intent(pos['ticket'], pos.get('broker_comment'), pos)
        if not context and position_id and (self.setup_ledger.orders or self.setup_ledger.intents):
            if deals is None:
                deals = mt5.history_deals_get(position=int(position_id))
            candidates = {}
            for deal in deals or ():
                if getattr(deal, 'entry', None) != getattr(mt5, 'DEAL_ENTRY_IN', 0):
                    continue
                order_ticket = getattr(deal, 'order', None)
                candidate = self.setup_ledger.context(dict(pos, ticket=order_ticket))
                if not candidate:
                    candidate = self.setup_ledger.recover_intent(order_ticket, getattr(deal, 'comment', ''), pos)
                if candidate:
                    candidates[order_ticket] = candidate
            if len(candidates) == 1:
                origin, context = next(iter(candidates.items()))
                self.setup_ledger.bind(origin, position_id)
        if context and position_id and pos.get('state') == 'OPEN':
            self.setup_ledger.bind(context['origin_order_ticket'], position_id)
        return dict(pos, **context)

    def recover_setup_intents(self):
        """Recover broker acknowledgements missing from local records after a crash."""
        intents = self.setup_ledger.pending_intents()
        if not intents:
            return
        start = min(datetime.fromisoformat(r['submitted_at']) for r in intents.values()) - timedelta(days=1)
        history = mt5.history_orders_get(start, datetime.now(timezone.utc))
        if history is None:
            raise RuntimeError('Cannot recover setup submissions: broker order history unavailable')
        buy_types = {mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_BUY_STOP}
        for order in history:
            comment = getattr(order, 'comment', '')
            if comment not in intents:
                continue
            pos = dict(ticket=order.ticket, symbol=order.symbol,
                       strategy_name=self.strategy_name_for_magic(order.magic, comment),
                       direction='BUY' if order.type in buy_types else 'SELL')
            if self.setup_ledger.recover_intent(order.ticket, comment, pos):
                self.setup_ledger.bind(order.ticket, getattr(order, 'position_id', 0))
        # Unmatched intents remain explicit; no association by symbol or price.
        if self.setup_ledger.pending_intents():
            logger.warning('Unresolved setup submission intents: %s', list(self.setup_ledger.pending_intents()))

    def get_account_balance(self) -> float:
        info = mt5.account_info()
        if self._expected_account is not None:
            validate_demo_account(info, **self._expected_account)
        if info is None or not positive(info.balance):
            raise RuntimeError(f'MT5 balance unavailable or non-positive: {self._last_error_text()}')
        return info.balance

    def get_historical_order_state(self, tracked_pos: dict) -> str | None:
        """Return CANCELLED, FILLED, ACTIVE, or None for a broker-history order."""
        ticket = tracked_pos.get('ticket')
        if ticket in (None, 0, ''):
            return None
        try:
            orders = mt5.history_orders_get(ticket=int(ticket))
        except (AttributeError, TypeError, ValueError):
            return None
        if not orders:
            return None

        latest = max(
            orders,
            key=lambda order: getattr(
                order, 'time_done_msc', getattr(order, 'time_done', 0)
            ),
        )
        state = getattr(latest, 'state', None)
        cancelled_states = {
            getattr(mt5, 'ORDER_STATE_CANCELED', 2),
            getattr(mt5, 'ORDER_STATE_REJECTED', 5),
            getattr(mt5, 'ORDER_STATE_EXPIRED', 6),
        }
        filled_states = {
            getattr(mt5, 'ORDER_STATE_PARTIAL', 3),
            getattr(mt5, 'ORDER_STATE_FILLED', 4),
        }
        if state in cancelled_states:
            return 'CANCELLED'
        if state in filled_states:
            return 'FILLED'
        return 'ACTIVE'

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

        # A partial exit is not a completed trade. Resolve the stable identifier
        # from the entry deals, because a pending ticket can differ from it.
        entries = [d for d in matching if getattr(d, 'entry', None) == getattr(mt5, 'DEAL_ENTRY_IN', 0)]
        position_ids = {getattr(d, 'position_id', None) for d in entries} - {None, 0}
        if len(position_ids) == 1:
            position_id = next(iter(position_ids))
        positions = mt5.positions_get()
        if positions is None:
            raise RuntimeError('Cannot confirm final position closure: MT5 position query failed')
        if any(getattr(p, 'identifier', p.ticket) == position_id or p.ticket == ticket for p in positions):
            return None
        entered = sum(float(getattr(d, 'volume', 0)) for d in entries)
        exited = sum(float(getattr(d, 'volume', 0)) for d in exit_deals)
        if entered > 0 and exited + 1e-8 < entered:
            return None  # Final exit history is not yet complete.
        attributed = self._attach_setup_context(dict(tracked_pos, position_id=position_id), matching)
        if attributed.get('setup_id'):
            remainder = mt5.orders_get(ticket=int(attributed['origin_order_ticket']))
            if remainder is None:
                raise RuntimeError('Cannot confirm final setup closure: MT5 order query failed')
            if remainder:
                return None  # A partially filled entry may still execute its remainder.

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
        history_entry_price = self._entry_price_from_deals(matching)
        if tracked_pos.get('state') == 'PENDING' or entry_price is None:
            entry_price = history_entry_price or entry_price

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
        trade = {
            'ticket': ticket,
            'position_id': position_id,
            'is_final': True,
            'symbol': symbol or getattr(latest, 'symbol', ''),
            'direction': direction,
            'strategy_name': strategy_name,
            'result': result,
            'pnl': round(pnl, 2),
            'close_time': self._mt5_timestamp_utc(getattr(latest, 'time', 0)),
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
        trade.update({k: attributed[k] for k in ('setup_id', 'attempt_id', 'origin_order_ticket', 'submitted_tp')
                      if k in attributed})
        return self.setup_ledger.close(trade)
