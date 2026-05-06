"""
Download and convert free HistData M1 bars into this project's CSV format.

HistData source notes:
- Free web downloads are organized by symbol/year/month ZIP files.
- M1 bar timestamps are treated as New York local market time.
- This script converts timestamps to naive UTC using New York DST rules.
- Output files are written under data/historical/histdata/ so backtests can use:
      python run_backtest.py live_suite --data-source histdata

Usage examples:
    python fetch_data_histdata.py --symbols EURUSD GBPUSD --timeframes M5 M15 H1 H4 D1
    python fetch_data_histdata.py --symbols EURUSD --start-year 2016 --end-date 2026-03-20 --insecure
    python fetch_data_histdata.py --from-zip-dir data/raw/histdata --symbols EURUSD --timeframes H1 D1
"""

from __future__ import annotations

import argparse
import io
import os
import re
import ssl
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


BASE_URL = 'https://www.histdata.com'
OUTPUT_DIR = Path('data/historical/histdata')
RAW_DIR = Path('data/raw/histdata')

DEFAULT_SYMBOLS = [
    'EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDJPY', 'USDCAD', 'USDCHF',
    'AUDCAD', 'AUDJPY', 'AUDNZD', 'CADJPY', 'EURAUD', 'EURCAD', 'EURCHF',
    'EURGBP', 'EURJPY', 'GBPAUD', 'GBPCAD', 'GBPJPY', 'GBPNZD', 'NZDJPY',
    'XAUUSD',
]
DEFAULT_TIMEFRAMES = ['M5', 'M15', 'H1', 'H4', 'D1']

# Project symbol -> HistData symbol. US30 is intentionally absent: HistData's
# closest comparable index is SPXUSD/NSXUSD, not Dow/US30.
HISTDATA_SYMBOLS = {symbol: symbol for symbol in DEFAULT_SYMBOLS}

RESAMPLE_RULES = {
    'M1': '1min',
    'M5': '5min',
    'M15': '15min',
    'H1': '1h',
    'H4': '4h',
    'D1': '1D',
}


def build_periods(start_year: int, end_date: datetime) -> list[tuple[int, int | None]]:
    last_year = end_date.year
    last_month = end_date.month
    if end_date.day == 1 and end_date.hour == 0 and end_date.minute == 0 and end_date.second == 0:
        last_month -= 1
        if last_month == 0:
            last_year -= 1
            last_month = 12

    periods = []
    for year in range(start_year, last_year + 1):
        if year < last_year:
            periods.append((year, None))
        else:
            for month in range(1, last_month + 1):
                periods.append((year, month))
    return periods


def make_context(insecure: bool):
    return ssl._create_unverified_context() if insecure else None


def fetch_html(url: str, context) -> str:
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=60, context=context) as response:
        return response.read().decode('utf-8', 'ignore')


def parse_hidden_form(html: str) -> dict[str, str]:
    fields = dict(re.findall(r'name="([^"]+)"[^>]+value="([^"]*)"', html))
    required = {'tk', 'date', 'datemonth', 'platform', 'timeframe', 'fxpair'}
    missing = required - fields.keys()
    if missing:
        raise RuntimeError(f'HistData download form changed; missing fields: {sorted(missing)}')
    return {key: fields[key] for key in required}


def download_zip(symbol: str, year: int, month: int | None, raw_dir: Path, context) -> Path:
    period_url = f'{BASE_URL}/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes/{symbol.lower()}/{year}'
    if month is not None:
        period_url += f'/{month}'

    html = fetch_html(period_url, context)
    fields = parse_hidden_form(html)
    body = urllib.parse.urlencode(fields).encode('ascii')
    req = urllib.request.Request(
        f'{BASE_URL}/get.php',
        data=body,
        headers={
            'User-Agent': 'Mozilla/5.0',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': period_url,
        },
    )
    with urllib.request.urlopen(req, timeout=180, context=context) as response:
        data = response.read()

    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise RuntimeError(f'HistData did not return a ZIP for {symbol} {year}/{month or ""}')

    raw_dir.mkdir(parents=True, exist_ok=True)
    suffix = f'{year}{month:02d}' if month is not None else str(year)
    path = raw_dir / f'DAT_ASCII_{symbol.upper()}_M1_{suffix}.zip'
    path.write_bytes(data)
    return path


def find_zip(raw_dir: Path, symbol: str, year: int, month: int | None) -> Path | None:
    suffix = f'{year}{month:02d}' if month is not None else str(year)
    matches = sorted(raw_dir.glob(f'*{symbol.upper()}*M1*{suffix}*.zip'))
    return matches[0] if matches else None


def read_histdata_zip(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as zf:
        names = [name for name in zf.namelist() if name.lower().endswith(('.csv', '.txt'))]
        if not names:
            raise ValueError(f'No CSV/TXT file found inside {path}')
        with zf.open(names[0]) as f:
            df = pd.read_csv(
                f,
                sep=';',
                header=None,
                names=['time_est', 'open', 'high', 'low', 'close', 'volume'],
            )

    local_time = pd.to_datetime(df['time_est'], format='%Y%m%d %H%M%S')
    df['time'] = (
        local_time
        .dt.tz_localize(ZoneInfo('America/New_York'), ambiguous='infer', nonexistent='shift_forward')
        .dt.tz_convert('UTC')
        .dt.tz_localize(None)
    )
    return df[['time', 'open', 'high', 'low', 'close', 'volume']]


def round_prices(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if symbol == 'XAUUSD':
        decimals = 2
    elif 'JPY' in symbol:
        decimals = 3
    else:
        decimals = 5
    for col in ['open', 'high', 'low', 'close']:
        df[col] = df[col].round(decimals)
    return df


def resample(df_m1: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    if timeframe == 'M1':
        return df_m1.copy()
    rule = RESAMPLE_RULES[timeframe]
    ohlc = (
        df_m1.set_index('time')
        .resample(rule, label='left', closed='left')
        .agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum',
        })
        .dropna(subset=['open', 'high', 'low', 'close'])
        .reset_index()
    )
    return ohlc


def save_timeframe(df_m1: pd.DataFrame, symbol: str, timeframe: str, output_dir: Path):
    df = resample(df_m1, timeframe)
    df = round_prices(df, symbol)
    output_dir.mkdir(parents=True, exist_ok=True)
    start = df['time'].iloc[0].strftime('%Y%m%d')
    end = df['time'].iloc[-1].strftime('%Y%m%d')
    path = output_dir / f'{symbol}_{timeframe}_{start}-{end}.csv'
    df.to_csv(path, index=False)
    print(f'  saved {path} ({len(df):,} rows)')


def parse_args():
    parser = argparse.ArgumentParser(description='Fetch/convert HistData M1 data.')
    parser.add_argument('--symbols', nargs='+', default=DEFAULT_SYMBOLS)
    parser.add_argument('--timeframes', nargs='+', default=DEFAULT_TIMEFRAMES, choices=RESAMPLE_RULES.keys())
    parser.add_argument('--start-year', type=int, default=2016)
    parser.add_argument('--end-date', type=lambda s: datetime.strptime(s, '%Y-%m-%d'), default=datetime(2026, 3, 20))
    parser.add_argument('--raw-dir', type=Path, default=RAW_DIR)
    parser.add_argument('--output-dir', type=Path, default=OUTPUT_DIR)
    parser.add_argument('--from-zip-dir', type=Path, default=None, help='Convert existing HistData ZIPs instead of downloading.')
    parser.add_argument('--download-missing', action='store_true', help='With --from-zip-dir, download ZIPs not found locally.')
    parser.add_argument('--insecure', action='store_true', help='Disable SSL certificate verification for HistData downloads.')
    parser.add_argument('--sleep', type=float, default=1.0, help='Delay between HistData web downloads.')
    return parser.parse_args()


def main():
    args = parse_args()
    context = make_context(args.insecure)
    source_zip_dir = args.from_zip_dir or args.raw_dir
    periods = build_periods(args.start_year, args.end_date)

    for project_symbol in args.symbols:
        hist_symbol = HISTDATA_SYMBOLS.get(project_symbol)
        if hist_symbol is None:
            print(f'WARNING: no HistData mapping for {project_symbol}; skipping')
            continue

        print(f'\n{project_symbol}: collecting {len(periods)} ZIP periods')
        chunks = []
        for year, month in periods:
            zip_path = find_zip(source_zip_dir, hist_symbol, year, month)
            if zip_path is None:
                if args.from_zip_dir is not None and not args.download_missing:
                    print(f'  missing local ZIP: {hist_symbol} {year}/{month or ""}')
                    continue
                print(f'  downloading {hist_symbol} {year}/{month or ""}...')
                zip_path = download_zip(hist_symbol, year, month, args.raw_dir, context)
                time.sleep(args.sleep)
            chunks.append(read_histdata_zip(zip_path))

        if not chunks:
            print(f'  no data for {project_symbol}')
            continue

        df_m1 = pd.concat(chunks, ignore_index=True)
        df_m1 = df_m1.drop_duplicates(subset=['time']).sort_values('time')
        df_m1 = df_m1[df_m1['time'] < args.end_date]

        if df_m1.empty:
            print(f'  no rows before end date for {project_symbol}')
            continue

        for timeframe in args.timeframes:
            save_timeframe(df_m1, project_symbol, timeframe, args.output_dir)


if __name__ == '__main__':
    main()
