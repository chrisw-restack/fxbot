"""
Run this script on your Windows VPS (with MT5 installed and running) to download
historical data and save it as CSV files ready for backtesting.

Usage:
    python fetch_data.py

Edit the SYMBOLS, TIMEFRAMES, START and END below before running.
The CSVs will be saved to data/historical/ and are ready to copy to your
development machine for backtesting.
"""

import os
import sys
from datetime import datetime

from dotenv import load_dotenv

# ── Configuration — edit these before running ─────────────────────────────────
# SYMBOLS    = ['EURUSD','GBPUSD','AUDUSD','NZDUSD','USDCAD','USDJPY']
SYMBOLS    = ['AUDUSD']
TIMEFRAMES = ['D1']
# START      = datetime(2025, 4, 15)
# END        = datetime(2026, 3, 1)
START      = datetime(2026, 1, 1)
END        = datetime(2026, 3,20)
# ─────────────────────────────────────────────────────────────────────────────

load_dotenv()

try:
    import MetaTrader5 as mt5
except ImportError:
    print("ERROR: MetaTrader5 package not installed. Run this script on your Windows VPS.")
    sys.exit(1)

from data.mt5_data import connect, disconnect, save_historical

login    = int(os.environ['MT5_LOGIN'])
password = os.environ['MT5_PASSWORD']
server   = os.environ['MT5_SERVER']

if not connect(login, password, server):
    print("ERROR: Could not connect to MT5. Make sure MT5 is running on this machine.")
    sys.exit(1)

print(f"Fetching data for {SYMBOLS} on {TIMEFRAMES} from {START.date()} to {END.date()}")
print()

saved = []
for symbol in SYMBOLS:
    for timeframe in TIMEFRAMES:
        try:
            path = save_historical(symbol, timeframe, START, END)
            saved.append(path)
            print(f"  [OK]   {path}")
        except Exception as e:
            print(f"  [FAIL] {symbol} {timeframe}: {e}")

disconnect()

print()
print(f"Done. {len(saved)} file(s) saved to data/historical/")
print("Copy the CSV files to your development machine to run backtests.")
