  ---
  Getting a Backtest Running

  Part 1 — Set up your development machine (Linux, one-time)

  1. Check Python version — needs 3.10 or higher
  python3 --version

  2. Create and activate a virtual environment
  cd /home/chris/Documents/claude_workspace/trading_bot
  python3 -m venv venv
  source venv/bin/activate

  3. Install backtest-only dependencies (no MT5 package needed for backtesting)
  pip install -r requirements-backtest.txt

  ---
  Part 2 — Get historical data (run on your Windows VPS)

  The backtest needs CSV files. MT5 only runs on Windows, so you fetch data there and copy it over.

  4. On the Windows VPS — copy the project folder across (or clone/sync it)

  5. On the Windows VPS — create your .env file in the project root:
  MT5_LOGIN=12345678
  MT5_PASSWORD=your_password
  MT5_SERVER=YourBroker-Server

  6. On the Windows VPS — install full requirements
  pip install -r requirements.txt

  7. Edit fetch_data.py — set the symbols, timeframe, and date range you want:
  SYMBOLS    = ['EURUSD', 'GBPUSD']
  TIMEFRAMES = ['H1']
  START      = datetime(2023, 1, 1)
  END        = datetime(2024, 1, 1)

  8. Make sure MT5 is open and logged in, then run:
  python fetch_data.py
  You should see output like:
    ✓  data/historical/EURUSD_H1_20230101-20240101.csv
    ✓  data/historical/GBPUSD_H1_20230101-20240101.csv

  9. Copy the CSV files back to your Linux machine into data/historical/
  # Example using scp from your Linux machine:
  scp user@your-vps:/path/to/project/data/historical/*.csv data/historical/

  ---
  Part 3 — Run the backtest (back on Linux)

  10. Edit run_backtest.py — set symbols and settings to match the CSVs you downloaded:
  SYMBOLS         = ['EURUSD']
  INITIAL_BALANCE = 10_000.0
  RR_RATIO        = 2.0
  LOOKBACK        = 20

  11. Run it:
  python run_backtest.py

  You'll see output like:
  ================================================================================
  TRADE LOG
  ================================================================================
  Datetime              Symbol    Dir    Result  R       Strategy
  --------------------------------------------------------------------------------
  2023-02-14 09:00      EURUSD    BUY    WIN     +2.00   Breakout
  2023-03-01 14:00      EURUSD    SELL   LOSS    -1.00   Breakout
  ...

  ================================================================================
  PERFORMANCE SUMMARY
  ================================================================================
    Total trades       47
    Win rate           44.7%  (21W / 26L)
    Total R            +16.00R
    ...

  ---
  Troubleshooting

  ┌────────────────────────────────────────────────────┬────────────────────────────────────────────────────────────────────────────────────────────────────┐
  │                      Problem                       │                                                Fix                                                 │
  ├────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ ModuleNotFoundError: No module named 'MetaTrader5' │ You're running fetch_data.py on Linux. It must be run on the Windows VPS.                          │
  ├────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ No CSV found for EURUSD H1                         │ The CSV filename must match the pattern EURUSD_H1_*.csv. Check data/historical/.                   │
  ├────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ MT5 login failed                                   │ Make sure MT5 is open and logged into your broker account on the VPS before running fetch_data.py. │
  ├────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Backtest runs but shows 0 trades                   │ Increase the date range — you need at least LOOKBACK + 1 bars before the first signal can fire.    │
  └────────────────────────────────────────────────────┴────────────────────────────────────────────────────────────────────────────────────────────────────┘
