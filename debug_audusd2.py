"""Check what D1 bars the loader actually feeds to the strategy after the weekend filter."""

import logging
from datetime import datetime

from data.historical_loader import find_csv, load_and_merge, filter_bars

logging.basicConfig(level=logging.INFO)

csv_paths = []
for tf in ['D1', 'H1']:
    csv_paths.extend(find_csv('AUDUSD', tf))

print(f"CSV files: {csv_paths}\n")

all_bars = load_and_merge(csv_paths)
bars = filter_bars(all_bars, start=datetime(2026, 3, 8))

# Show all D1 bars
print(f"\nD1 bars from March 8 onward:")
for b in bars:
    if b.timeframe == 'D1':
        wd = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][b.timestamp.weekday()]
        print(f"  {b.timestamp}  {wd}  O={b.open:.5f} H={b.high:.5f} L={b.low:.5f} C={b.close:.5f}  vol={b.volume:.0f}")
