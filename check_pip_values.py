"""
Check pip sizes and pip values for metals and index CFDs on ICMarkets MT5.

Run this on the Windows VPS with MT5 running:
    python check_pip_values.py

Prints MT5's own tick_size and tick_value for each symbol so you can verify
(or correct) the PIP_SIZE and PIP_VALUE_USD entries in config.py.

How to read the output:
  tick_size        — the smallest price increment MT5 allows (= our pip_size)
  tick_value       — USD value of one tick per 1 standard lot (= our pip_value_usd)
  contract_size    — number of units per 1 lot (e.g. 100 oz for XAUUSD)
  currency_profit  — currency the P&L is settled in (USD or EUR etc.)
"""

import os
import sys

from dotenv import load_dotenv

try:
    import MetaTrader5 as mt5
except ImportError:
    print("ERROR: MetaTrader5 package not found. Run this script on the Windows VPS.")
    sys.exit(1)

SYMBOLS = ['XAUUSD', 'US30', 'US500', 'USTEC', 'DE40']

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

W = 80
print('=' * W)
print(f"{'PIP / TICK VALUE CHECK':^{W}}")
print('=' * W)
print(f"{'Symbol':<10} {'contract_size':>14} {'tick_size':>10} {'tick_value':>11} {'currency':>10}")
print('-' * W)

for sym in SYMBOLS:
    si = mt5.symbol_info(sym)
    if si is None:
        print(f"  {sym:<8}  NOT FOUND — check the symbol name in MT5 Market Watch")
        continue
    print(f"  {sym:<8}  {si.trade_contract_size:>14.1f}  {si.trade_tick_size:>10.4f}  "
          f"{si.trade_tick_value:>11.4f}  {si.currency_profit:>10}")

print('=' * W)
print()
print("Compare tick_size → config.PIP_SIZE and tick_value → config.PIP_VALUE_USD.")
print("If currency_profit is not USD (e.g. EUR for DE40), tick_value is in that")
print("currency — multiply by current EURUSD rate to get the USD equivalent.")

mt5.shutdown()
