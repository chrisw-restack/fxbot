"""
London Breakout Strategy (LBS)

Range: NY midnight–2:55am (Asian session, 36 M5 bars). Range high = max(high), range low = min(low).
SL:    midpoint of range — (range_high + range_low) / 2. Same level for BUY and SELL.
TP:    risk manager applies rr_ratio (not set on Signal).
Entry: PENDING at range_high (BUY) or range_low (SELL) on first close outside the range.
       One signal per day. Entry window NY 3:00–6:59am (London open).
Cancel: at NY 7:00am if pending is unfilled.
"""

from zoneinfo import ZoneInfo

from models import BarEvent, Signal

_NY_TZ = ZoneInfo('America/New_York')
_UTC_TZ = ZoneInfo('UTC')


class LondonBreakoutStrategy:
    TIMEFRAMES = ['M5']
    ORDER_TYPE = 'PENDING'
    NAME = 'LondonBreakout'

    def __init__(self, rr_ratio: float = 2.5):
        self.rr_ratio = rr_ratio

        self._range_high: dict[str, float | None] = {}
        self._range_low: dict[str, float | None] = {}
        self._range_date: dict = {}
        self._range_locked: dict[str, bool] = {}
        self._signal_fired: dict[str, bool] = {}
        self._done_today: dict[str, bool] = {}

    def reset(self):
        self._range_high.clear()
        self._range_low.clear()
        self._range_date.clear()
        self._range_locked.clear()
        self._signal_fired.clear()
        self._done_today.clear()

    def _init_symbol(self, symbol: str):
        self._range_high[symbol] = None
        self._range_low[symbol] = None
        self._range_date[symbol] = None
        self._range_locked[symbol] = False
        self._signal_fired[symbol] = False
        self._done_today[symbol] = False

    def _reset_day(self, symbol: str):
        self._range_high[symbol] = None
        self._range_low[symbol] = None
        self._range_locked[symbol] = False
        self._signal_fired[symbol] = False
        self._done_today[symbol] = False

    def generate_signal(self, event: BarEvent) -> Signal | None:
        symbol = event.symbol
        if symbol not in self._range_high:
            self._init_symbol(symbol)

        ts_ny = event.timestamp.replace(tzinfo=_UTC_TZ).astimezone(_NY_TZ)
        ny_hour = ts_ny.hour
        ny_date = ts_ny.date()

        if ny_date != self._range_date[symbol]:
            self._range_date[symbol] = ny_date
            self._reset_day(symbol)

        # Accumulate range: NY midnight–2:55am (Asian session, hours 0, 1, 2)
        if ny_hour in (0, 1, 2):
            rh = self._range_high[symbol]
            rl = self._range_low[symbol]
            self._range_high[symbol] = event.high if rh is None else max(rh, event.high)
            self._range_low[symbol] = event.low  if rl is None else min(rl, event.low)

        # Lock range at NY 3:00am (London open)
        if ny_hour >= 3 and not self._range_locked[symbol] and self._range_high[symbol] is not None:
            self._range_locked[symbol] = True

        if not self._range_locked[symbol] or self._done_today[symbol]:
            return None

        # Cancel unfilled pending at NY 7:00am
        if ny_hour >= 7:
            self._done_today[symbol] = True
            if self._signal_fired[symbol]:
                self._signal_fired[symbol] = False
                return Signal(
                    symbol=symbol, direction='CANCEL', order_type='PENDING',
                    entry_price=0.0, stop_loss=0.0,
                    strategy_name=self.NAME, timestamp=event.timestamp,
                )
            return None

        if ny_hour < 3:
            return None

        range_high = self._range_high[symbol]
        range_low  = self._range_low[symbol]
        midpoint   = (range_high + range_low) / 2
        close      = event.close
        signal     = None

        if close > range_high:
            signal = Signal(
                symbol=symbol, direction='BUY', order_type='PENDING',
                entry_price=range_high, stop_loss=midpoint,
                strategy_name=self.NAME, timestamp=event.timestamp,
            )
        elif close < range_low:
            signal = Signal(
                symbol=symbol, direction='SELL', order_type='PENDING',
                entry_price=range_low, stop_loss=midpoint,
                strategy_name=self.NAME, timestamp=event.timestamp,
            )

        if signal is not None:
            self._signal_fired[symbol] = True
            self._done_today[symbol] = True

        return signal
