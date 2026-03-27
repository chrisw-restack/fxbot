"""
Download historical OHLC data from Dukascopy for backtesting.
Timestamps are UTC. Output CSV matches the project convention:
    data/historical/<SYMBOL>_<TF>_<YYYYMMDD>-<YYYYMMDD>.csv
    Columns: time, open, high, low, close, volume

Usage:
    python fetch_data_dukascopy.py

Edit SYMBOLS, TIMEFRAMES, START_YEAR, and END_DATE below before running.
Downloads in yearly chunks to avoid memory issues.
"""

import os
import time
from datetime import datetime

import pandas as pd
import dukascopy_python
from dukascopy_python import instruments

# ── Configuration — edit these before running ─────────────────────────────────
# SYMBOLS = ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDJPY', 'USDCAD', 'USDCHF']
SYMBOLS = ['USA100', 'USA500', 'USA30', 'XAUUSD']
# SYMBOLS = ['USDCHF']
TIMEFRAMES = ['D1']        # Any of: M5, M15, H1, H4, D1
START_YEAR = 2016
END_DATE = datetime(2026, 3, 20)
OUTPUT_DIR = 'data/historical'
# ──────────────────────────────────────────────────────────────────────────────

# Map our symbol names to dukascopy instrument IDs
INSTRUMENT_MAP = {
    'EURUSD': instruments.INSTRUMENT_FX_MAJORS_EUR_USD,
    'GBPUSD': instruments.INSTRUMENT_FX_MAJORS_GBP_USD,
    'AUDUSD': instruments.INSTRUMENT_FX_MAJORS_AUD_USD,
    'NZDUSD': instruments.INSTRUMENT_FX_MAJORS_NZD_USD,
    'USDJPY': instruments.INSTRUMENT_FX_MAJORS_USD_JPY,
    'USDCHF': instruments.INSTRUMENT_FX_MAJORS_USD_CHF,
    'USDCAD': instruments.INSTRUMENT_FX_MAJORS_USD_CAD,
    'XAUUSD': instruments.INSTRUMENT_FX_METALS_XAU_USD,       # Gold spot
    'USA30':  instruments.INSTRUMENT_IDX_AMERICA_E_D_J_IND,   # Dow Jones
    'USA500': instruments.INSTRUMENT_IDX_AMERICA_E_SANDP_500, # S&P 500
    'USA100': instruments.INSTRUMENT_IDX_AMERICA_E_NQ_100,    # Nasdaq 100
}

# Map our timeframe names to dukascopy interval constants
INTERVAL_MAP = {
    'M5':  dukascopy_python.INTERVAL_MIN_5,
    'M15': dukascopy_python.INTERVAL_MIN_15,
    'H1':  dukascopy_python.INTERVAL_HOUR_1,
    'H4':  dukascopy_python.INTERVAL_HOUR_4,
    'D1':  dukascopy_python.INTERVAL_DAY_1,
}

os.makedirs(OUTPUT_DIR, exist_ok=True)

for symbol in SYMBOLS:
    instrument = INSTRUMENT_MAP.get(symbol)
    if instrument is None:
        print(f"WARNING: No Dukascopy instrument mapping for {symbol} — skipping")
        continue

    for tf in TIMEFRAMES:
        interval = INTERVAL_MAP.get(tf)
        if interval is None:
            print(f"WARNING: Unknown timeframe '{tf}' — skipping")
            continue

        print(f"\n{'='*60}")
        print(f"Fetching {symbol} {tf}")
        print(f"{'='*60}")

        all_chunks = []

        for year in range(START_YEAR, END_DATE.year + 1):
            start = datetime(year, 1, 1)
            end = datetime(year + 1, 1, 1) if year < END_DATE.year else END_DATE

            if start >= END_DATE:
                break

            print(f"  {year}...", end=' ', flush=True)
            t0 = time.time()

            try:
                df = dukascopy_python.fetch(
                    instrument,
                    interval,
                    dukascopy_python.OFFER_SIDE_BID,
                    start,
                    end,
                )
                all_chunks.append(df)
                elapsed = time.time() - t0
                print(f"{len(df)} rows ({elapsed:.1f}s)", flush=True)
            except Exception as e:
                print(f"ERROR: {e}", flush=True)

            time.sleep(1)

        if not all_chunks:
            print(f"  No data retrieved for {symbol} {tf}")
            continue

        # Combine, deduplicate, sort
        full_df = pd.concat(all_chunks)
        full_df.sort_index(inplace=True)
        full_df = full_df[~full_df.index.duplicated(keep='first')]

        # Convert timezone-aware UTC index to naive UTC datetime column
        full_df.index = full_df.index.tz_localize(None)
        full_df.index.name = 'time'
        full_df = full_df.reset_index()

        # Round prices: 2dp for indices/gold, 3dp for JPY pairs, 5dp for others
        if symbol in ('USA30', 'USA500', 'USA100'):
            decimals = 2
        elif symbol == 'XAUUSD':
            decimals = 2
        elif 'JPY' in symbol:
            decimals = 3
        else:
            decimals = 5
        for col in ['open', 'high', 'low', 'close']:
            full_df[col] = full_df[col].round(decimals)

        # Build filename matching project convention
        start_str = full_df['time'].iloc[0].strftime('%Y%m%d')
        end_str = full_df['time'].iloc[-1].strftime('%Y%m%d')
        filename = f"{symbol}_{tf}_{start_str}-{end_str}.csv"
        filepath = os.path.join(OUTPUT_DIR, filename)

        full_df.to_csv(filepath, index=False)
        print(f"  Saved: {filepath}")
        print(f"  Rows: {len(full_df)}  Range: {full_df['time'].iloc[0]} to {full_df['time'].iloc[-1]}")

print("\nDone.")
