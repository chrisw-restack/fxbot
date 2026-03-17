"""
Download Forex Factory economic calendar data from Hugging Face and normalize to UTC.

Usage:
    python fetch_news_data.py

Output:
    data/news/forex_factory_calendar.csv

Columns: datetime_utc, currency, impact, event
"""

import os

import pandas as pd
import requests

OUTPUT_DIR = os.path.join('data', 'news')
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'forex_factory_calendar.csv')

# Hugging Face dataset: Ehsanrs2/Forex_Factory_Calendar
# Direct CSV download via the datasets API
DATASET_URL = (
    'https://huggingface.co/datasets/Ehsanrs2/Forex_Factory_Calendar'
    '/resolve/main/forex_factory_cache.csv'
)

# Only keep events for currencies we trade
CURRENCIES = {'USD', 'EUR', 'GBP', 'AUD', 'NZD', 'JPY', 'CAD'}

# Map raw impact strings to simple labels
IMPACT_MAP = {
    'High Impact Expected': 'HIGH',
    'Medium Impact Expected': 'MEDIUM',
    'Low Impact Expected': 'LOW',
    'Non-Economic': 'LOW',
}


def download_raw(url: str) -> str:
    """Download the raw CSV file, return local temp path."""
    print(f"Downloading from {url} ...")
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    tmp_path = os.path.join(OUTPUT_DIR, '_raw_download.csv')
    with open(tmp_path, 'wb') as f:
        f.write(resp.content)
    size_mb = len(resp.content) / (1024 * 1024)
    print(f"Downloaded {size_mb:.1f} MB")
    return tmp_path


def process(raw_path: str):
    """Read raw CSV, normalize timezone to UTC, filter, and save."""
    print("Processing ...")
    df = pd.read_csv(raw_path)

    # The dataset DateTime column includes timezone offset (e.g. +03:30)
    df['datetime_utc'] = pd.to_datetime(df['DateTime'], utc=True)

    # Filter to currencies we care about
    df = df[df['Currency'].isin(CURRENCIES)].copy()

    # Map impact levels
    df['impact'] = df['Impact'].map(IMPACT_MAP).fillna('LOW')

    # Keep only the columns we need
    df = df[['datetime_utc', 'Currency', 'impact', 'Event']].copy()
    df.columns = ['datetime_utc', 'currency', 'impact', 'event']

    # Sort by time
    df = df.sort_values('datetime_utc').reset_index(drop=True)

    # Save — strip timezone info for simpler CSV handling (already UTC)
    df['datetime_utc'] = df['datetime_utc'].dt.tz_localize(None)
    df.to_csv(OUTPUT_FILE, index=False)

    # Clean up temp file
    os.remove(raw_path)

    print(f"\nSaved {len(df):,} events to {OUTPUT_FILE}")
    print(f"Date range: {df['datetime_utc'].min()} — {df['datetime_utc'].max()}")
    print(f"\nImpact breakdown:")
    print(df['impact'].value_counts().to_string())
    print(f"\nCurrency breakdown:")
    print(df['currency'].value_counts().to_string())


if __name__ == '__main__':
    raw = download_raw(DATASET_URL)
    process(raw)
