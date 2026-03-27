"""Trace every signal and pending state for USDJPY around March 9-12 through the actual engine."""

import logging
import io
import contextlib
from datetime import datetime

from backtest_engine import BacktestEngine
from strategies.ema_fib_retracement import EmaFibRetracementStrategy
from data.historical_loader import find_csv, load_and_merge, filter_bars

logging.basicConfig(level=logging.WARNING)

strat = EmaFibRetracementStrategy(
    cooldown_bars=10, invalidate_swing_on_loss=True,
    min_swing_pips=15, ema_sep_pct=0.001,
)

csv_paths = []
for tf in ['D1', 'H1']:
    csv_paths.extend(find_csv('USDJPY', tf))

all_bars = load_and_merge(csv_paths)

sym = 'USDJPY'

engine = BacktestEngine(
    initial_balance=10_000.0, rr_ratio=2.0, spread_pips=2.0,
    risk_pct_overrides={'EmaFibRetracement': 0.007},
)
engine.add_strategy(strat, symbols=[sym])

for bar in all_bars:
    # Before processing, capture pending state
    pending_before = strat._pending_entry.get(sym)
    pending_dir = strat._pending_direction.get(sym)

    # Run the engine step
    closed_trades = engine.execution.check_fills(bar)
    for trade in closed_trades:
        engine.portfolio.record_close(trade['symbol'], trade['pnl'])
        engine.trade_logger.log_close(trade['ticket'], trade)
        engine.event_engine.notify_trade_closed(trade)

        if bar.timestamp >= datetime(2026, 3, 1):
            print(f"  TRADE CLOSED: {trade['symbol']} {trade['direction']} {trade['result']} "
                  f"R={trade['r_multiple']:+.2f} at {bar.timestamp} "
                  f"fill_price={trade.get('fill_price', 'N/A')} open_time={trade.get('open_time', 'N/A')}")

    signal = None
    with contextlib.redirect_stdout(io.StringIO()):
        engine.event_engine.process_bar(bar)

    # After processing, check if pending state changed
    pending_after = strat._pending_entry.get(sym)
    pending_dir_after = strat._pending_direction.get(sym)

    if bar.timeframe == 'H1' and datetime(2026, 3, 8) <= bar.timestamp <= datetime(2026, 3, 12):
        # Check if a signal was generated (pending changed from None to something)
        if pending_before is None and pending_after is not None:
            print(f"H1 {bar.timestamp}  NEW SIGNAL: {pending_dir_after} pending @ {pending_after:.3f}  "
                  f"(bar O={bar.open:.3f} H={bar.high:.3f} L={bar.low:.3f} C={bar.close:.3f})")
            print(f"  Swing H={strat._swing_high[sym]:.3f}  Swing L={strat._swing_low[sym]:.3f}")
            sh = strat._swing_high[sym]
            sl = strat._swing_low[sym]
            print(f"  Fib 61.8% entry = {sh - 0.618 * (sh - sl):.3f}")
            print(f"  D1 EMA10={strat._d1_ema_fast[sym]:.3f} EMA20={strat._d1_ema_slow[sym]:.3f}")
            print(f"  H1 EMA10={strat._h1_ema_fast[sym]:.3f} EMA20={strat._h1_ema_slow[sym]:.3f}")
        elif pending_before is not None and pending_after is None:
            # Pending was cleared (filled or cancelled)
            print(f"H1 {bar.timestamp}  PENDING CLEARED (was {pending_dir} @ {pending_before:.3f})  "
                  f"(bar O={bar.open:.3f} H={bar.high:.3f} L={bar.low:.3f} C={bar.close:.3f})")
        elif pending_before is not None and pending_after is not None and abs(pending_before - pending_after) > 0.001:
            print(f"H1 {bar.timestamp}  PENDING CHANGED: {pending_before:.3f} -> {pending_after:.3f}")
