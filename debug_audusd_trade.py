"""Debug the AUDUSD SELL on 2026-03-19 to check EMA state."""

import logging
import sys
from datetime import datetime

from strategies.ema_fib_retracement import EmaFibRetracementStrategy
from data.historical_loader import find_csv, load_and_merge, filter_bars
from models import BarEvent

logging.basicConfig(level=logging.ERROR)

strat = EmaFibRetracementStrategy(
    cooldown_bars=10, invalidate_swing_on_loss=True,
    min_swing_pips=15, ema_sep_pct=0.001,
)

csv_paths = []
for tf in ['D1', 'H1']:
    csv_paths.extend(find_csv('AUDUSD', tf))

all_bars = load_and_merge(csv_paths)
# Use data from 2025 onward to have EMAs warmed up, but focus on March 2026
bars = filter_bars(all_bars, start=datetime(2025, 1, 1))

print(f"Processing {len(bars)} bars\n")

sym = 'AUDUSD'
for bar in bars:
    signal = strat.generate_signal(bar)

    # Print D1 EMA state on each D1 bar in March 2026
    if bar.timeframe == 'D1' and bar.timestamp >= datetime(2026, 3, 10):
        d1_fast = strat._d1_ema_fast.get(sym)
        d1_slow = strat._d1_ema_slow.get(sym)
        bias = 'BUY' if (d1_fast and d1_slow and d1_fast > d1_slow) else 'SELL'
        print(f"D1 {bar.timestamp}  close={bar.close:.5f}  "
              f"EMA10={d1_fast:.5f}  EMA20={d1_slow:.5f}  bias={bias}")

    # Print H1 EMA state and signals around March 17-19
    if bar.timeframe == 'H1' and datetime(2026, 3, 14) <= bar.timestamp <= datetime(2026, 3, 20):
        h1_fast = strat._h1_ema_fast.get(sym)
        h1_slow = strat._h1_ema_slow.get(sym)
        h1_bias = 'BUY' if (h1_fast and h1_slow and h1_fast > h1_slow) else 'SELL'
        pending = strat._pending_direction.get(sym)
        pending_entry = strat._pending_entry.get(sym)

        line = (f"H1 {bar.timestamp}  O={bar.open:.5f} H={bar.high:.5f} L={bar.low:.5f} C={bar.close:.5f}  "
                f"EMA10={h1_fast:.5f}  EMA20={h1_slow:.5f}  h1_bias={h1_bias}")
        if pending:
            line += f"  PENDING {pending} @ {pending_entry:.5f}"
        if signal:
            line += f"  >>> SIGNAL: {signal.direction} entry={signal.entry_price:.5f} sl={signal.stop_loss:.5f} tp={signal.take_profit:.5f}"
        print(line)
