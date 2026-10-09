# Backtest setup and interpretation

The September 2026 pipeline corrections change historical fills and headline R. See [the implementation report and frozen comparison](strategy_log/codebase_improvements_20260907.md) before comparing new runs with older strategy logs.

For the tested Python 3.14 environment, install `requirements-backtest.lock`. For other supported Python versions, use `requirements-backtest.txt`; the exact lock has only been tested locally on Python 3.14. Run `python -m unittest discover -s tests -v` to check the pipeline without connecting to MT5.

CSV timestamps default to UTC. Raw broker-wall-clock files need `load_csv(..., time_basis='icmarkets')` or a sidecar named `<filename>.csv.meta.json` containing `{"time_basis": "icmarkets", "session_origin": "icmarkets"}`. Already converted broker data uses `{"time_basis": "utc", "session_origin": "icmarkets"}`. The named `mt5_icmarkets` and `mt5_icmarkets_utc` folders also identify those source contracts. The loader does not infer timezone from Sunday candles.

XM research data requires its own audit. Run `python prepare_xm_history.py` against the completed raw snapshot, then `python audit_xm_early_clocks.py` for the older diagnostic and `python summarize_xm_preparation.py` to verify outputs and finalize the dataset manifest. Prepared candles stay under `output/xm_processed_20261001/history/`; they do not replace existing data sources. See [the XM audit](strategy_log/xm_data_audit_20261001.md) and `output/xm_processed_20261001/joint_replay_intervals.csv`. Load a bounded interval shared by all required timeframe files, including warmup. The loader rejects changed CSVs/sidecars, unverified clocks, out-of-coverage dates, and ranges crossing quarantined sections or unexplained long gaps. Start each segment independently and report exposure left open at its end. XM historical spread zeros are unknown costs, and the older archive does not share one proven universal clock rule.

Backtest `r_multiple` now means net R after configured commission. `gross_r` and `initial_risk` remain available on trade records. Replay uses the finest loaded execution candles for each symbol, includes entry-candle exits and adverse stop gaps, and assumes SL first when OHLC ordering is ambiguous. Supply fine-candle coverage throughout the test period. Open trades at the end remain open and are reported alongside ending equity and drawdown measured at candle closes.

Keep sweep and walk-forward workers at one by default. To reproduce the code revision comparison, export baseline revision `0709948` with complete Python packages and run `python compare_engine_revisions.py --baseline-root <export-directory>`. This uses local Dukascopy data and a USA100 proxy for USTEC; it does not connect to the demo account.

  ---
  Steps to getting a Backtest Running

  Part 1 — Set up your development machine (Linux, one-time)

  1. Check Python version — needs 3.10 or higher
  python3 --version

  2. Create and activate a virtual environment
  cd /path/to/fxbot
  python3 -m venv .venv
  source .venv/bin/activate

  3. Install dependencies
  pip install -r requirements-backtest.txt

  ---
  Part 2 — Get historical data

  Option A — Dukascopy (preferred — 10+ years, runs on Linux, no MT5 needed)

  4. Run the downloader with explicit symbols, timeframes, and dates:
  python fetch_data_dukascopy.py --symbols EURUSD XAUUSD --timeframes H1 M5 --start-date 2016-01-01 --end-date 2026-08-01
  You should see output like:
    ✓  data/historical/EURUSD_H1_20160103-20260319.csv
    ✓  data/historical/XAUUSD_M5_20160103-20260319.csv

  ---
  Option B — HistData (source and clock verification required)

  4. Download raw ZIPs with HTTPS provenance receipts, verify their clocks against existing UTC M5 references, then convert and resample:
  python fetch_data_histdata.py --symbols EURUSD --start-year 2016 --end-date 2026-03-20 --download-only
  python audit_histdata_provenance.py --verify-clocks --raw-dir data/raw/histdata --resume
  python fetch_data_histdata.py --from-zip-dir data/raw/histdata --symbols EURUSD --timeframes M5 M15 H1 H4 D1 --start-year 2016 --end-date 2026-03-20

  5. Run a backtest against the HistData folder:
  python run_backtest.py live_suite --data-source histdata

  HistData files are saved under data/historical/histdata/.
  Keep each CSV and ZIP with its `.meta.json` sidecar. The loader rejects changed or unverified HistData CSVs. The verifier needs reference M5 coverage for the requested period; update the reference data first if coverage is insufficient. HTTPS verification uses the certifi CA bundle. Downloads made with `--insecure` cannot be certified for backtesting.
  Do not force all archives to fixed EST or New York time. Measured archive years can follow different DST calendars. HistData's price overlap with Dukascopy also prevents assuming an independent feed merely because the download websites differ.
  If the clock audit reports conflicting prices for one minute, first try a fresh official download. To explicitly quarantine unresolved conflicts, repeat the audit with `--quarantine-conflicts`. It excludes every price version for those minutes and the entire containing candle at each requested timeframe. The sidecars list the affected UTC minutes and omitted candle counts. No missing candles are invented. These gaps can still affect backtest execution.
  The [September 2026 provenance repair](strategy_log/histdata_provenance_20260921.md) documents the verified archives, clock rules, backups, and limits. Its `--download` and `--rebuild` migration commands use dated staging paths; normal future conversions use `fetch_data_histdata.py`.
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
  Part 4 — Parameter sweep and walk-forward before demo deployment

  9. Run a parameter sweep to find the best params:
  python param_sweep.py

  10. Validate with walk-forward (the key step — proves params generalise):
  python walk_forward.py ema_fib_retracement
  python walk_forward.py engulfing --train-years 4 --test-years 2

  OOS retention guide:
    >= 70%  → STRONG (parameters generalise; suitable for demo consideration)
    40-70%  → MODERATE (some overfitting; demo only with caution and approval)
    < 40%   → WEAK/FAIL (curve-fit; do not deploy)

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
