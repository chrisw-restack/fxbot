"""A/B test: does cancelling pending orders when price passes TP help or hurt?"""

import logging
import sys
import io
import contextlib
import copy

from backtest_engine import BacktestEngine
from strategies.ema_fib_retracement import EmaFibRetracementStrategy
from data.historical_loader import find_csv, load_and_merge

logging.basicConfig(level=logging.ERROR)

SYMBOLS = ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDJPY', 'USDCAD', 'USDCHF']
INITIAL_BALANCE = 10_000.0
RR_RATIO = 2.0
SPREAD_PIPS = 2.0
RISK_PCT_OVERRIDES = {'EmaFibRetracement': 0.007}

PARAMS = dict(cooldown_bars=10, invalidate_swing_on_loss=True,
              min_swing_pips=15, ema_sep_pct=0.001)

csv_paths = []
for sym in SYMBOLS:
    for tf in ['D1', 'H1']:
        csv_paths.extend(find_csv(sym, tf))

print("Loading bar data...")
all_bars = load_and_merge(csv_paths)
print(f"Loaded {len(all_bars):,} bars\n")


def run_test(strategy, label):
    engine = BacktestEngine(
        initial_balance=INITIAL_BALANCE, rr_ratio=RR_RATIO,
        spread_pips=SPREAD_PIPS, risk_pct_overrides=RISK_PCT_OVERRIDES,
    )
    engine.add_strategy(strategy, symbols=SYMBOLS)

    with contextlib.redirect_stdout(io.StringIO()):
        for bar in all_bars:
            closed_trades = engine.execution.check_fills(bar)
            for trade in closed_trades:
                engine.portfolio.record_close(trade['symbol'], trade['pnl'])
                engine.trade_logger.log_close(trade['ticket'], trade)
                engine.event_engine.notify_trade_closed(trade)
            engine.event_engine.process_bar(bar)

    trades = engine.execution.get_closed_trades()
    total = len(trades)
    if total == 0:
        print(f"{label}: 0 trades")
        return

    wins = sum(1 for t in trades if t['result'] == 'WIN')
    total_r = sum(t['r_multiple'] for t in trades)
    gp = sum(t['r_multiple'] for t in trades if t['result'] == 'WIN')
    gl = abs(sum(t['r_multiple'] for t in trades if t['result'] == 'LOSS'))
    pf = gp / gl if gl > 0 else 0.0

    peak = running = max_dd = 0.0
    for t in trades:
        running += t['r_multiple']
        peak = max(peak, running)
        max_dd = max(max_dd, peak - running)

    worst = cur = 0
    for t in trades:
        if t['result'] == 'LOSS':
            cur += 1
            worst = max(worst, cur)
        else:
            cur = 0

    print(f"{label}:")
    print(f"  Trades: {total}  WR: {wins/total*100:.1f}%  TotalR: {total_r:+.1f}  "
          f"PF: {pf:.2f}  Expect: {total_r/total:+.3f}  MaxDD: {max_dd:.1f}R  "
          f"LStreak: {worst}")


# ── Version A: original (no TP-pass cancel) ──────────────────────────────────
print("Running version A (original - no TP-pass cancel)...")
strat_a = EmaFibRetracementStrategy(**PARAMS)
run_test(strat_a, "A) Original")

# ── Version B: with TP-pass cancel ───────────────────────────────────────────
# Monkey-patch the strategy to add TP-pass cancellation

class EmaFibWithTPCancel(EmaFibRetracementStrategy):
    """Same as original but cancels pending if price has passed the TP level."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._pending_tp: dict[str, float | None] = {}

    def reset(self):
        super().reset()
        self._pending_tp.clear()

    def _init_symbol(self, symbol):
        super()._init_symbol(symbol)
        if symbol not in self._pending_tp:
            self._pending_tp[symbol] = None

    def _process_h1(self, symbol, event):
        from models import Signal

        # Update EMAs
        self._h1_bar_count[symbol] += 1
        count = self._h1_bar_count[symbol]

        fast, self._h1_sma_sum_fast[symbol] = self._update_ema(
            event.close, self._h1_ema_fast[symbol], count,
            self._h1_sma_sum_fast[symbol], self.ema_fast,
        )
        slow, self._h1_sma_sum_slow[symbol] = self._update_ema(
            event.close, self._h1_ema_slow[symbol], count,
            self._h1_sma_sum_slow[symbol], self.ema_slow,
        )
        self._h1_ema_fast[symbol] = fast
        self._h1_ema_slow[symbol] = slow

        self._h1_counter[symbol] += 1
        bar_idx = self._h1_counter[symbol]

        self._h1_window[symbol].append(event)
        self._detect_swings(symbol)

        # Check pending
        pending = self._pending_entry[symbol]
        if pending is not None:
            if event.low <= pending <= event.high:
                self._pending_entry[symbol] = None
                self._pending_direction[symbol] = None
                self._pending_tp[symbol] = None
                return None

            # NEW: Cancel if price has passed TP without filling entry
            tp = self._pending_tp[symbol]
            direction = self._pending_direction[symbol]
            if tp is not None and direction is not None:
                if direction == 'BUY' and event.high >= tp:
                    self._pending_entry[symbol] = None
                    self._pending_direction[symbol] = None
                    self._pending_tp[symbol] = None
                    return Signal(
                        symbol=symbol, direction='CANCEL',
                        order_type=self.ORDER_TYPE, entry_price=0.0,
                        stop_loss=0.0, strategy_name=self.NAME,
                        timestamp=event.timestamp,
                    )
                if direction == 'SELL' and event.low <= tp:
                    self._pending_entry[symbol] = None
                    self._pending_direction[symbol] = None
                    self._pending_tp[symbol] = None
                    return Signal(
                        symbol=symbol, direction='CANCEL',
                        order_type=self.ORDER_TYPE, entry_price=0.0,
                        stop_loss=0.0, strategy_name=self.NAME,
                        timestamp=event.timestamp,
                    )

            # Bias flip cancel
            h1_bias = self._get_bias(self._h1_ema_fast[symbol], self._h1_ema_slow[symbol])
            if h1_bias is not None and h1_bias != self._pending_direction[symbol]:
                self._pending_entry[symbol] = None
                self._pending_direction[symbol] = None
                self._pending_tp[symbol] = None
                return Signal(
                    symbol=symbol, direction='CANCEL',
                    order_type=self.ORDER_TYPE, entry_price=0.0,
                    stop_loss=0.0, strategy_name=self.NAME,
                    timestamp=event.timestamp,
                )
            return None

        # All filters (same as parent)
        if bar_idx < self._cooldown_until[symbol]:
            return None
        if self.blocked_hours and event.timestamp.hour in self.blocked_hours:
            return None
        if self.min_d1_atr_pips > 0:
            d1_atr = self._d1_atr.get(symbol)
            if d1_atr is None:
                return None
            if d1_atr / self._pip_size(symbol) < self.min_d1_atr_pips:
                return None

        d1_bias = self._get_bias(self._d1_ema_fast[symbol], self._d1_ema_slow[symbol])
        h1_bias = self._get_bias(self._h1_ema_fast[symbol], self._h1_ema_slow[symbol])
        if d1_bias is None or h1_bias is None:
            return None
        if d1_bias != h1_bias:
            return None

        if self.ema_sep_pct > 0:
            h1_fast_val = self._h1_ema_fast[symbol]
            h1_slow_val = self._h1_ema_slow[symbol]
            if abs(h1_fast_val - h1_slow_val) / h1_slow_val < self.ema_sep_pct:
                return None

        swing_high = self._swing_high[symbol]
        swing_low = self._swing_low[symbol]
        if swing_high is None or swing_low is None:
            return None

        high_age = bar_idx - self._swing_high_bar[symbol]
        low_age = bar_idx - self._swing_low_bar[symbol]
        if high_age > self.swing_max_age or low_age > self.swing_max_age:
            return None

        if self.invalidate_swing_on_loss:
            if (swing_high == self._used_swing_high[symbol]
                    and swing_low == self._used_swing_low[symbol]):
                return None

        if swing_high <= swing_low:
            return None

        swing_range = swing_high - swing_low
        if self.min_swing_pips > 0:
            if swing_range / self._pip_size(symbol) < self.min_swing_pips:
                return None

        direction = d1_bias
        if direction == 'BUY':
            entry_price = swing_high - self.fib_entry * swing_range
            stop_loss = swing_low
            take_profit = swing_low + self.fib_tp * swing_range
        else:
            entry_price = swing_low + self.fib_entry * swing_range
            stop_loss = swing_high
            take_profit = swing_high - self.fib_tp * swing_range

        self._pending_entry[symbol] = entry_price
        self._pending_direction[symbol] = direction
        self._pending_tp[symbol] = take_profit  # Store TP for cancel check

        return Signal(
            symbol=symbol, direction=direction, order_type=self.ORDER_TYPE,
            entry_price=entry_price, stop_loss=stop_loss,
            strategy_name=self.NAME, timestamp=event.timestamp,
            take_profit=take_profit,
        )


print("\nRunning version B (with TP-pass cancel)...")
strat_b = EmaFibWithTPCancel(**PARAMS)
run_test(strat_b, "B) TP-pass cancel")
