import math

from models import BarEvent, Signal


class GaussianChannelStrategy:
    """
    Gaussian Channel breakout strategy (D1).

    Computes a multi-pole Gaussian filter on HLC3 with filtered True Range bands.
    BUY when the daily close is above the upper band.
    SELL when the daily close is below the lower band.
    Stop-loss at the opposite band. TP via risk manager at 2:1 R:R.
    """

    TIMEFRAMES = ['H4']
    ORDER_TYPE = 'MARKET'
    NAME = 'GaussianChannel'

    def __init__(
        self,
        period: int = 144,
        poles: int = 4,
        tr_mult: float = 1.414,
        cooldown_bars: int = 0,
    ):
        self.period = period
        self.poles = poles
        self.tr_mult = tr_mult
        self.cooldown_bars = cooldown_bars

        # Precompute Gaussian filter coefficients
        self._alpha, self._coeff = self._compute_coefficients(period, poles)

        # Per-symbol state
        self._filter_hl2: dict[str, list[list[float]]] = {}
        self._filter_tr: dict[str, list[list[float]]] = {}
        self._prev_close: dict[str, float | None] = {}
        self._upper_band: dict[str, float | None] = {}
        self._lower_band: dict[str, float | None] = {}
        self._bar_count: dict[str, int] = {}
        self._last_direction: dict[str, str | None] = {}
        self._cooldown_until: dict[str, int] = {}

    @staticmethod
    def _compute_coefficients(period: int, poles: int) -> tuple[float, list[float]]:
        """
        Compute the alpha and recursive coefficients for a multi-pole Gaussian filter.

        beta = (1 - cos(2*pi/period)) / (2^(1/poles) - 1)
        alpha = -beta + sqrt(beta^2 + 2*beta)
        """
        beta = (1.0 - math.cos(2.0 * math.pi / period)) / (2.0 ** (1.0 / poles) - 1.0)
        alpha = -beta + math.sqrt(beta * beta + 2.0 * beta)

        one_minus_alpha = 1.0 - alpha
        coeff = []
        for i in range(1, poles + 1):
            binom = math.comb(poles, i)
            sign = (-1) ** (i + 1)
            coeff.append(sign * binom * (one_minus_alpha ** i))

        return alpha, coeff

    def reset(self):
        """Clear all internal state."""
        self._filter_hl2.clear()
        self._filter_tr.clear()
        self._prev_close.clear()
        self._upper_band.clear()
        self._lower_band.clear()
        self._bar_count.clear()
        self._last_direction.clear()
        self._cooldown_until.clear()

    def _init_symbol(self, symbol: str):
        if symbol in self._bar_count:
            return
        self._filter_hl2[symbol] = [[] for _ in range(self.poles)]
        self._filter_tr[symbol] = [[] for _ in range(self.poles)]
        self._prev_close[symbol] = None
        self._upper_band[symbol] = None
        self._lower_band[symbol] = None
        self._bar_count[symbol] = 0
        self._last_direction[symbol] = None
        self._cooldown_until[symbol] = 0

    def _apply_filter(self, value: float, history: list[list[float]]) -> float | None:
        """
        Apply the multi-pole Gaussian filter to a new input value.
        Returns the filtered value, or None if not enough history yet.
        """
        alpha_pow = self._alpha ** self.poles

        current = value
        for pole in range(self.poles):
            hist = history[pole]

            if len(hist) < len(self._coeff):
                # Not enough history — seed with raw value
                hist.append(current)
            else:
                filtered = alpha_pow * current
                for i, c in enumerate(self._coeff):
                    filtered += c * hist[-(i + 1)]

                hist.append(filtered)
                current = filtered

                # Keep history bounded
                max_hist = len(self._coeff) + 2
                if len(hist) > max_hist:
                    del hist[:len(hist) - max_hist]

        if any(len(h) < len(self._coeff) for h in history):
            return None

        return current

    def generate_signal(self, event: BarEvent) -> Signal | None:
        symbol = event.symbol
        self._init_symbol(symbol)

        self._bar_count[symbol] += 1
        bar_idx = self._bar_count[symbol]

        # Compute HLC3 (typical price) and True Range
        hlc3 = (event.high + event.low + event.close) / 3.0

        prev_close = self._prev_close[symbol]
        if prev_close is not None:
            tr = max(event.high - event.low,
                     abs(event.high - prev_close),
                     abs(event.low - prev_close))
        else:
            tr = event.high - event.low
        self._prev_close[symbol] = event.close

        # Apply Gaussian filter to HLC3 and TR
        filtered_hl2 = self._apply_filter(hlc3, self._filter_hl2[symbol])
        filtered_tr = self._apply_filter(tr, self._filter_tr[symbol])

        if filtered_hl2 is None or filtered_tr is None:
            return None

        upper = filtered_hl2 + filtered_tr * self.tr_mult
        lower = filtered_hl2 - filtered_tr * self.tr_mult
        self._upper_band[symbol] = upper
        self._lower_band[symbol] = lower

        # Cooldown check
        if bar_idx <= self._cooldown_until[symbol]:
            return None

        signal = None

        # BUY: close above upper band, SL at midline
        if event.close > upper and self._last_direction[symbol] != 'BUY':
            signal = Signal(
                symbol=symbol,
                direction='BUY',
                order_type=self.ORDER_TYPE,
                entry_price=event.close,
                stop_loss=filtered_hl2,
                strategy_name=self.NAME,
                timestamp=event.timestamp,
            )
            self._last_direction[symbol] = 'BUY'

        # SELL: close below lower band, SL at midline
        elif event.close < lower and self._last_direction[symbol] != 'SELL':
            signal = Signal(
                symbol=symbol,
                direction='SELL',
                order_type=self.ORDER_TYPE,
                entry_price=event.close,
                stop_loss=filtered_hl2,
                strategy_name=self.NAME,
                timestamp=event.timestamp,
            )
            self._last_direction[symbol] = 'SELL'

        return signal

    def notify_loss(self, symbol: str):
        """Activate cooldown after a losing trade."""
        bar_idx = self._bar_count.get(symbol, 0)
        self._cooldown_until[symbol] = bar_idx + self.cooldown_bars
        self._last_direction[symbol] = None
