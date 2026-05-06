  ---
  Steps to getting a Backtest Running

  Part 1 — Set up your development machine (Linux, one-time)

  1. Check Python version — needs 3.10 or higher
  python3 --version

  2. Create and activate a virtual environment
  cd /home/chris/Documents/claude_workspace/fxbot
  python3 -m venv venv
  source venv/bin/activate

  3. Install dependencies
  pip install -r requirements.txt

  ---
  Part 2 — Get historical data

  Option A — Dukascopy (preferred — 10+ years, runs on Linux, no MT5 needed)

  4. Edit fetch_data_dukascopy.py — set the symbols, timeframes, and start year:
  SYMBOLS    = ['EURUSD', 'XAUUSD']
  TIMEFRAMES = ['H1', 'M5']
  START_YEAR = 2016

  5. Run it:
  python fetch_data_dukascopy.py
  You should see output like:
    ✓  data/historical/EURUSD_H1_20160103-20260319.csv
    ✓  data/historical/XAUUSD_M5_20160103-20260319.csv

  ---
  Option B — HistData (free independent cross-check against Dukascopy)

  4. Download HistData M1 ZIPs, convert New York local market timestamps to UTC, and resample locally:
  python fetch_data_histdata.py --symbols EURUSD GBPUSD AUDUSD NZDUSD USDJPY USDCAD USDCHF XAUUSD EURAUD CADJPY GBPCAD GBPNZD AUDJPY AUDCAD --timeframes M5 M15 H1 H4 D1 --start-year 2016 --end-date 2026-03-20 --insecure

  5. Run a backtest against the HistData folder:
  python run_backtest.py live_suite --data-source histdata

  HistData files are saved under data/historical/histdata/.
  Use --insecure only if your machine rejects HistData's SSL certificate.
  US30 is not mapped because HistData does not provide a direct Dow/US30 equivalent.

  ---
  Option C — MT5 (recent data only, Windows VPS required)

  4. On the Windows VPS — copy the project folder across (or clone/sync it)

  5. On the Windows VPS — create your .env file in the project root:
  MT5_LOGIN=12345678
  MT5_PASSWORD=your_password
  MT5_SERVER=YourBroker-Server

  6. On the Windows VPS — make sure MT5 is open and logged in, then run:
  python fetch_data.py

  7. Copy the CSV files back to your Linux machine:
  scp user@your-vps:/path/to/fxbot/data/historical/*.csv data/historical/

  ---
  Part 3 — Run the backtest (on Linux)

  8. Run a backtest by strategy name:
  python run_backtest.py ema_fib_retracement
  python run_backtest.py three_line_strike
  python run_backtest.py hmr

  Optional flags:
    --start-date 2022-01-01     # limit date range
    --end-date 2025-01-01
    --news-filter high          # block signals near high-impact news

  You'll see output like:
  ================================================================================
  TRADE LOG
  ================================================================================
  Datetime              Symbol    Dir    Result  R       Strategy
  --------------------------------------------------------------------------------
  2023-02-14 09:00      EURUSD    BUY    WIN     +2.00   EmaFibRetracement
  2023-03-01 14:00      EURUSD    SELL   LOSS    -1.00   EmaFibRetracement
  ...

  ================================================================================
  PERFORMANCE SUMMARY
  ================================================================================
    Total trades       47
    Win rate           44.7%  (21W / 26L)
    Total R            +16.00R
    Profit factor      1.48
    Expectancy         +0.340R
    Max drawdown       4.0R  (8.0%)
    ...

  ---
  Part 4 — Parameter sweep and walk-forward (before going live)

  9. Run a parameter sweep to find the best params:
  python param_sweep.py

  10. Validate with walk-forward (the key step — proves params generalise):
  python walk_forward.py ema_fib_retracement
  python walk_forward.py three_line_strike --train-years 4 --test-years 2

  OOS retention guide:
    >= 70%  → STRONG (parameters generalise — live-eligible)
    40-70%  → MODERATE (some overfitting — acceptable with caution)
    < 40%   → WEAK/FAIL (curve-fit — do not trade live)

  ---
  Troubleshooting

  ┌────────────────────────────────────────────────────┬────────────────────────────────────────────────────────────────────────────────────────────────────┐
  │                      Problem                       │                                                Fix                                                 │
  ├────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ ModuleNotFoundError: No module named 'MetaTrader5' │ fetch_data.py requires Windows + MT5. Use fetch_data_dukascopy.py on Linux instead.                │
  ├────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ No CSV found for EURUSD H1                         │ The CSV filename must match the pattern EURUSD_H1_*.csv. Check data/historical/.                   │
  ├────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ MT5 login failed                                   │ Make sure MT5 is open and logged into your broker account on the VPS before running fetch_data.py. │
  ├────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Backtest runs but shows 0 trades                   │ Increase the date range — strategy needs enough warm-up bars before the first signal fires.        │
  └────────────────────────────────────────────────────┴────────────────────────────────────────────────────────────────────────────────────────────────────┘
