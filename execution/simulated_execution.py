import logging
from datetime import timedelta

import config
from execution.base_execution import BaseExecution
from models import BarEvent
from data.historical_loader import bar_close_time
from risk.validation import valid_levels, floor_volume

logger = logging.getLogger(__name__)

# Timeframe granularity in minutes — used to determine which bars are fine enough
# to check fills and SL/TP against for a given entry timeframe.
_TF_MINUTES: dict[str, int] = {
    'M1': 1, 'M5': 5, 'M15': 15, 'M30': 30,
    'H1': 60, 'H4': 240, 'D1': 1440,
}


class SimulatedExecution(BaseExecution):
    """
    Simulates order fills for backtesting.

    Fill rules:
    - MARKET orders: filled at the open of the next bar after the signal.
    - PENDING orders: BUY triggers from ask, SELL from bid. Gaps use the opening
      quote; other fills use the submitted order price.
    - SL/TP: checked on every subsequent bar using high/low. If both SL and TP are
      touched in the same bar, SL is assumed hit first (conservative assumption).
    - Market entries are checked on the opening bar; pending ambiguity is SL-first.
    """

    def __init__(self, initial_balance: float, spread_pips: dict[str, float] | float = 0.1,
                 breakeven_at_r: float | None = None,
                 rr_ratio: float = config.DEFAULT_RR_RATIO,
                 commission_per_lot: dict[str, float] | float = config.BACKTEST_COMMISSION_PER_LOT):
        self._balance = initial_balance
        self._spread_pips = spread_pips
        self._breakeven_at_r = breakeven_at_r
        self._rr_ratio = rr_ratio
        self._commission_per_lot = commission_per_lot
        self._pending: dict[int, dict] = {}   # ticket -> position (not yet filled)
        self._positions: dict[int, dict] = {} # ticket -> position (open/filled)
        self._closed_trades: list[dict] = []
        self._next_ticket = 1
        self._execution_timeframes = {}
        self._quotes = {}
        self._rejected_orders = []
        self._equity_peak = initial_balance
        self.max_equity_drawdown_pct = 0.0

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
        entry_timeframe: str | None = None,
        tp_locked: bool = False,
        signal_time=None,
        risk_budget: float | None = None,
    ) -> int:
        if not valid_levels(direction, entry_price, sl, tp, config.MIN_RR_RATIO):
            return 0
        ticket = self._next_ticket
        self._next_ticket += 1
        self._pending[ticket] = {
            'ticket':          ticket,
            'symbol':          symbol,
            'direction':       direction,
            'order_type':      order_type,
            'entry_price':     entry_price,
            'lot_size':        lot_size,
            'sl':              sl,
            'tp':              tp,
            'strategy_name':   strategy_name,
            'entry_timeframe': entry_timeframe,
            'tp_locked':       tp_locked,
            'signal_time':     signal_time,
            'risk_budget':     risk_budget,
            'submitted_time': (signal_time + timedelta(minutes=_TF_MINUTES[entry_timeframe])
                               if signal_time is not None and entry_timeframe else signal_time),
            'pending_type': self._pending_type(symbol, direction, entry_price) if order_type == 'PENDING' else None,
            'requested_entry': entry_price,
            'requested_rr': abs(tp - entry_price) / abs(entry_price - sl),
        }
        return ticket

    def configure_timeframes(self, bars):
        """Choose one execution stream per symbol, preventing overlapping OHLC checks."""
        for bar in bars:
            old = self._execution_timeframes.get(bar.symbol)
            if old is None or _TF_MINUTES[bar.timeframe] < _TF_MINUTES[old]:
                self._execution_timeframes[bar.symbol] = bar.timeframe

    def _pending_type(self, symbol, direction, entry):
        quote = self._quotes.get(symbol)
        if quote is None:
            return None  # Direct legacy calls use a touch-only order.
        current = self._entry_price(quote, symbol, direction)
        return 'STOP' if (entry > current if direction == 'BUY' else entry < current) else 'LIMIT'

    def pip_value(self, symbol, price=None):
        """USD conversion from available historical quotes; CFD values follow config."""
        currencies = {'USD', 'EUR', 'GBP', 'AUD', 'NZD', 'CAD', 'CHF', 'JPY'}
        if len(symbol) == 6 and symbol[:3] in currencies and symbol[3:] in currencies:
            counter = symbol[3:]
            value = 100_000 * config.PIP_SIZE[symbol]
            if counter == 'USD':
                return value
            if symbol[:3] == 'USD' and price:
                return value / price
            if self._quotes.get(counter + 'USD'):
                return value * self._quotes[counter + 'USD']
            if self._quotes.get('USD' + counter):
                return value / self._quotes['USD' + counter]
        return config.PIP_VALUE_USD[symbol]

    def loss_per_lot(self, symbol, direction, entry, sl):
        return abs(entry - sl) / config.PIP_SIZE[symbol] * self.pip_value(symbol, sl)

    def take_rejected_orders(self):
        rejected, self._rejected_orders = self._rejected_orders, []
        return rejected

    def check_fills(self, bar: BarEvent) -> list[dict]:
        """Execute only the finest configured stream, then publish its closing quote.

        Orders become available at signal-bar close. Market orders fill at the
        following bar open. Intrabar pending fills use SL-first ambiguity, but
        never use an earlier high to award a TP before a limit entry happened.
        """
        execution_tf = self._execution_timeframes.get(bar.symbol)
        if execution_tf is not None and bar.timeframe != execution_tf:
            return []
        self._quotes[bar.symbol] = bar.open
        closed = []
        intrabar_entries = set()
        for ticket, pos in list(self._pending.items()):
            if pos['symbol'] != bar.symbol:
                continue
            entry_tf = pos.get('entry_timeframe')
            if execution_tf is None and entry_tf and entry_tf != bar.timeframe:
                continue
            available = pos.get('submitted_time')
            if available is not None and bar.timestamp < available:
                continue
            spread = self._spread_price(bar.symbol) if pos['direction'] == 'BUY' else 0.0
            opening, low, high = bar.open + spread, bar.low + spread, bar.high + spread
            entry = pos['entry_price']
            at_open = pos['order_type'] == 'MARKET'
            if at_open:
                fill = self._entry_price(bar.open, bar.symbol, pos['direction'])
            else:
                subtype = pos.get('pending_type')
                buy = pos['direction'] == 'BUY'
                if subtype == 'STOP':
                    at_open = opening >= entry if buy else opening <= entry
                    touched = high >= entry if buy else low <= entry
                elif subtype == 'LIMIT':
                    at_open = opening <= entry if buy else opening >= entry
                    touched = low <= entry if buy else high >= entry
                else:
                    touched = low <= entry <= high
                    at_open = opening == entry
                if not touched:
                    continue
                fill = opening if at_open and subtype else entry
            pos['entry_price'] = fill
            if pos['order_type'] == 'MARKET':
                self._recalc_tp(pos)
                budget = pos.get('risk_budget')
                if budget is not None and valid_levels(pos['direction'], fill, pos['sl']):
                    pos['lot_size'] = floor_volume(min(pos['lot_size'], budget / self.loss_per_lot(
                        bar.symbol, pos['direction'], fill, pos['sl'])))
                if not pos['lot_size'] or not valid_levels(pos['direction'], fill, pos['sl'], pos['tp'], config.MIN_RR_RATIO):
                    self._rejected_orders.append(self._pending.pop(ticket))
                    continue
            pos['initial_risk'] = self.loss_per_lot(bar.symbol, pos['direction'], fill, pos['sl']) * pos['lot_size']
            pos['open_time'] = bar.timestamp if at_open else bar_close_time(bar)
            self._positions[ticket] = self._pending.pop(ticket)
            if not at_open:
                intrabar_entries.add(ticket)
        for ticket, pos in list(self._positions.items()):
            if pos['symbol'] != bar.symbol:
                continue
            if execution_tf is None and _TF_MINUTES[bar.timeframe] > _TF_MINUTES.get(pos.get('entry_timeframe'), 1440):
                continue
            # Intrabar order: a TP is certain only if the close crosses it after
            # entry; an SL touch is conservatively assigned to after entry.
            result = self._check_sl_tp(pos, bar, intrabar=ticket in intrabar_entries)
            if result:
                del self._positions[ticket]
                self._balance += result['pnl']
                self._closed_trades.append(result)
                closed.append(result)
        self._quotes[bar.symbol] = bar.close
        equity = self.get_equity()
        self._equity_peak = max(self._equity_peak, equity)
        if self._equity_peak > 0:
            self.max_equity_drawdown_pct = max(self.max_equity_drawdown_pct,
                                               (self._equity_peak - equity) / self._equity_peak * 100)
        return closed

    def get_equity(self):
        equity = self._balance
        for pos in self._positions.values():
            quote = self._quotes.get(pos['symbol'], pos['entry_price'])
            exit_price = self._exit_price(quote, pos['symbol'], pos['direction'])
            delta = exit_price - pos['entry_price']
            if pos['direction'] == 'SELL':
                delta = -delta
            equity += delta / config.PIP_SIZE[pos['symbol']] * self.pip_value(pos['symbol'], exit_price) * pos['lot_size']
            equity -= self._commission(pos['symbol']) * pos['lot_size']
        return equity

    def _commission(self, symbol):
        return (self._commission_per_lot.get(symbol, config.COMMISSION_PER_LOT)
                if isinstance(self._commission_per_lot, dict) else self._commission_per_lot)

    def _check_sl_tp(self, pos: dict, bar: BarEvent, intrabar=False) -> dict | None:
        """
        Returns a closed trade dict if SL or TP was hit, otherwise None.
        If both are hit in the same bar, SL is assumed to have been hit first.
        """
        if pos['direction'] == 'BUY':
            sl_hit = bar.low <= pos['sl']
            if not intrabar and bar.open >= pos['tp']:
                sl_hit = False
            tp_hit = (bar.close if intrabar else bar.high) >= pos['tp']
            if sl_hit:
                exit_price = pos['sl'] if intrabar else min(pos['sl'], bar.open)
                result = 'BE' if pos.get('_be_active') else 'LOSS'
            elif tp_hit:
                exit_price, result = pos['tp'], 'WIN'
            else:
                self._update_breakeven(pos, bar)
                return None
        else:  # SELL
            ask_high = bar.high + self._spread_price(pos['symbol'])
            ask_low = bar.low + self._spread_price(pos['symbol'])
            sl_hit = ask_high >= pos['sl']
            if not intrabar and bar.open + self._spread_price(pos['symbol']) <= pos['tp']:
                sl_hit = False
            tp_hit = (bar.close + self._spread_price(pos['symbol']) if intrabar else ask_low) <= pos['tp']
            if sl_hit:
                exit_price = pos['sl'] if intrabar else max(pos['sl'], bar.open + self._spread_price(pos['symbol']))
                result = 'BE' if pos.get('_be_active') else 'LOSS'
            elif tp_hit:
                exit_price, result = pos['tp'], 'WIN'
            else:
                self._update_breakeven(pos, bar)
                return None

        pip_size  = config.PIP_SIZE.get(pos['symbol'], 0.0001)
        pip_value = self.pip_value(pos['symbol'], exit_price)

        open_time = pos.get('open_time')
        duration_hours = round((bar_close_time(bar) - open_time).total_seconds() / 3600, 1) if open_time else None
        signal_time = pos.get('signal_time')
        pending_hours = round((open_time - signal_time).total_seconds() / 3600, 1) if (open_time and signal_time) else None

        if pos['direction'] == 'BUY':
            pips = (exit_price - pos['entry_price']) / pip_size
        else:
            pips = (pos['entry_price'] - exit_price) / pip_size

        commission_per_lot = (
            self._commission_per_lot.get(pos['symbol'], config.COMMISSION_PER_LOT)
            if isinstance(self._commission_per_lot, dict)
            else self._commission_per_lot
        )
        commission = commission_per_lot * pos['lot_size']
        pnl = pips * pip_value * pos['lot_size'] - commission
        original_sl = pos.get('_original_sl', pos['sl'])
        sl_pips = abs(pos['entry_price'] - original_sl) / pip_size
        initial_risk = pos.get('initial_risk') or sl_pips * pip_value * pos['lot_size']
        gross_r = (pnl + commission) / initial_risk if initial_risk else 0.0
        net_r = pnl / initial_risk if initial_risk else 0.0
        exit_reason = result
        result = 'WIN' if pnl > 0 else 'LOSS' if pnl < 0 else 'BE'

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
            'pending_hours': pending_hours,
            'duration_hours': duration_hours,
            'lot_size':      pos['lot_size'],
            'result':        result,
            'r_multiple':    net_r,
            'net_r':         net_r,
            'gross_r':       gross_r,
            'initial_risk':  initial_risk,
            'exit_reason':   exit_reason,
            'pnl':           pnl,
            'commission':    round(commission, 2),
            'open_time':     open_time,
            'close_time':    bar_close_time(bar),
        }

    def _update_breakeven(self, pos, bar):
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

    def _recalc_tp(self, pos: dict):
        """Recalculate TP from actual fill price so R:R is measured from real entry.
        Skipped when tp_locked=True (strategy set a fixed price-level TP)."""
        if pos.get('tp_locked'):
            return
        sl_dist = abs(pos['entry_price'] - pos['sl'])
        if pos['direction'] == 'BUY':
            pos['tp'] = pos['entry_price'] + sl_dist * pos.get('requested_rr', self._rr_ratio)
        else:
            pos['tp'] = pos['entry_price'] - sl_dist * pos.get('requested_rr', self._rr_ratio)

    def _spread_price(self, symbol: str) -> float:
        pip_size = config.PIP_SIZE.get(symbol, 0.0001)
        if isinstance(self._spread_pips, dict):
            spread_pips = self._spread_pips.get(symbol, 0.1)
        else:
            spread_pips = self._spread_pips
        return spread_pips * pip_size

    def _entry_price(self, bid_price: float, symbol: str, direction: str) -> float:
        # Historical OHLC bars are treated as bid prices.
        return bid_price + self._spread_price(symbol) if direction == 'BUY' else bid_price

    def _exit_price(self, bid_price: float, symbol: str, direction: str) -> float:
        # BUY closes sell at bid; SELL closes buy at ask.
        return bid_price if direction == 'BUY' else bid_price + self._spread_price(symbol)

    def close_order(self, ticket_id: int) -> bool:
        if ticket_id in self._positions:
            del self._positions[ticket_id]
            return True
        if ticket_id in self._pending:
            del self._pending[ticket_id]
            return True
        return False

    def cancel_pending_order(self, ticket_id: int) -> bool:
        if ticket_id not in self._pending:
            return False
        del self._pending[ticket_id]
        return True

    def get_open_positions(self) -> list[dict]:
        return list(self._positions.values()) + list(self._pending.values())

    def get_account_balance(self) -> float:
        return self._balance

    def get_closed_trades(self) -> list[dict]:
        return list(self._closed_trades)
