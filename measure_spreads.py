"""
Live spread monitor for MT5.

Polls bid/ask for each symbol at a configurable interval and reports
min, max, mean, and median spread (in pips) after the run completes.

Usage (on Windows VPS with MT5 running):
    python measure_spreads.py
    python measure_spreads.py --duration 300 --interval 0.5
    python measure_spreads.py --duration 60 --symbols EURUSD GBPUSD USDJPY

Options:
    --duration   N     Total run time in seconds (default: 60)
    --interval   N     Polling interval in seconds (default: 0.25)
    --symbols    ...   Symbols to monitor (default: all 7 live pairs)
"""

import argparse
import os
import sys
import time
from collections import defaultdict

from dotenv import load_dotenv

try:
    import MetaTrader5 as mt5
except ImportError:
    print("ERROR: MetaTrader5 package not found. Run this script on the Windows VPS.")
    sys.exit(1)

# ── Pip sizes ────────────────────────────────────────────────────────────────
PIP_SIZE = {
    'EURUSD': 0.0001, 'GBPUSD': 0.0001, 'AUDUSD': 0.0001,
    'NZDUSD': 0.0001, 'USDJPY': 0.01,   'USDCAD': 0.0001,
    'USDCHF': 0.0001, 'XAUUSD': 0.1,    'XAGUSD': 0.01,
    'USA30':  1.0,    'USA500': 0.1,     'USA100': 0.1,
}

DEFAULT_SYMBOLS = ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDJPY', 'USDCAD', 'USDCHF']

# ── Args ─────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description='Measure live MT5 bid/ask spreads.')
parser.add_argument('--duration', type=float, default=60.0,
                    help='How long to run in seconds (default: 60)')
parser.add_argument('--interval', type=float, default=0.25,
                    help='Poll interval in seconds (default: 0.25)')
parser.add_argument('--symbols', nargs='+', default=DEFAULT_SYMBOLS,
                    help='Symbols to monitor')
args = parser.parse_args()

SYMBOLS   = args.symbols
DURATION  = args.duration
INTERVAL  = args.interval

# ── Connect ──────────────────────────────────────────────────────────────────
load_dotenv()
login    = int(os.environ['MT5_LOGIN'])
password = os.environ['MT5_PASSWORD']
server   = os.environ['MT5_SERVER']

print(f"Connecting to MT5 ({server})...")
if not mt5.initialize(login=login, password=password, server=server):
    print(f"ERROR: MT5 connection failed — {mt5.last_error()}")
    sys.exit(1)

info = mt5.account_info()
print(f"Connected: account {info.login}  balance {info.balance:.2f} {info.currency}\n")

# ── Collect ──────────────────────────────────────────────────────────────────
spreads: dict[str, list[float]] = defaultdict(list)

print(f"Monitoring {len(SYMBOLS)} symbols for {DURATION:.0f}s "
      f"(poll every {INTERVAL*1000:.0f}ms)...")
print("  " + "  ".join(SYMBOLS))
print()

start = time.perf_counter()
samples = 0

try:
    while True:
        elapsed = time.perf_counter() - start
        if elapsed >= DURATION:
            break

        for sym in SYMBOLS:
            tick = mt5.symbol_info_tick(sym)
            if tick is None or tick.ask == 0 or tick.bid == 0:
                continue
            raw_spread = tick.ask - tick.bid
            pip = PIP_SIZE.get(sym, 0.0001)
            spreads[sym].append(raw_spread / pip)

        samples += 1

        remaining = DURATION - (time.perf_counter() - start)
        sleep_for = min(INTERVAL, remaining)
        if sleep_for > 0:
            time.sleep(sleep_for)

except KeyboardInterrupt:
    print("\nInterrupted early.")

mt5.shutdown()

elapsed = time.perf_counter() - start
print(f"\nRan for {elapsed:.1f}s — {samples} samples per symbol\n")

# ── Report ───────────────────────────────────────────────────────────────────
W = 70
print('=' * W)
print(f"{'SPREAD REPORT (pips)':^{W}}")
print('=' * W)
print(f"{'Symbol':<10} {'Samples':>7} {'Min':>7} {'Avg':>7} {'Median':>7} "
      f"{'Max':>7} {'p95':>7}")
print('-' * W)

for sym in SYMBOLS:
    data = spreads.get(sym, [])
    if not data:
        print(f"  {sym:<8} {'no data':>7}")
        continue

    data_sorted = sorted(data)
    n = len(data_sorted)
    mn  = data_sorted[0]
    mx  = data_sorted[-1]
    avg = sum(data_sorted) / n
    med = data_sorted[n // 2]
    p95 = data_sorted[int(n * 0.95)]

    print(f"  {sym:<8} {n:>7} {mn:>7.1f} {avg:>7.1f} {med:>7.1f} "
          f"{mx:>7.1f} {p95:>7.1f}")

print('=' * W)
print()
print("Recommended backtest spread (conservative = ~p95 of session):")
print()
for sym in SYMBOLS:
    data = spreads.get(sym, [])
    if not data:
        continue
    data_sorted = sorted(data)
    p95 = data_sorted[int(len(data_sorted) * 0.95)]
    print(f"  '{sym}': {p95:.1f} pips")
