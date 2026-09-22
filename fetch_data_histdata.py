"""
Download and convert free HistData M1 bars into this project's CSV format.

HistData source notes:
- Free web downloads are organized by symbol/year/month ZIP files.
- HistData's FAQ declares fixed EST, but supplied years can follow US or European DST.
- Conversion requires hash-bound clock verification; it never guesses the clock.
- Output files are written under data/historical/histdata/ so backtests can use:
      python run_backtest.py live_suite --data-source histdata

Usage examples:
    python fetch_data_histdata.py --symbols EURUSD GBPUSD --timeframes M5 M15 H1 H4 D1
    python fetch_data_histdata.py --symbols EURUSD --start-year 2016 --end-date 2026-03-20 --download-only
    python fetch_data_histdata.py --from-zip-dir data/raw/histdata --symbols EURUSD --timeframes H1 D1
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import ssl
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
import certifi
import pandas as pd
from data.histdata_provenance import (file_hash, metadata_path, read_raw_archive,
    verified_archive_metadata, to_utc, validate_frame, write_json)


BASE_URL = 'https://www.histdata.com'
OUTPUT_DIR = Path('data/historical/histdata')
RAW_DIR = Path('data/raw/histdata')

DEFAULT_SYMBOLS = [
    'EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDJPY', 'USDCAD', 'USDCHF',
    'AUDCAD', 'AUDJPY', 'AUDNZD', 'CADJPY', 'EURAUD', 'EURCAD', 'EURCHF',
    'EURGBP', 'EURJPY', 'GBPAUD', 'GBPCAD', 'GBPJPY', 'GBPNZD', 'NZDJPY',
    'XAUUSD', 'USA100', 'USA500',
]
DEFAULT_TIMEFRAMES = ['M5', 'M15', 'H1', 'H4', 'D1']

# Project symbol -> HistData symbol. USA30/US30 is intentionally absent because
# HistData has no Dow feed; do not substitute a different index.
HISTDATA_SYMBOLS = {symbol: symbol for symbol in DEFAULT_SYMBOLS}
HISTDATA_SYMBOLS.update({
    'USA100': 'NSXUSD',
    'USTEC': 'NSXUSD',
    'USA500': 'SPXUSD',
    'US500': 'SPXUSD',
})

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
    return ssl._create_unverified_context() if insecure else ssl.create_default_context(cafile=certifi.where())


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
    suffix = f'{year}{month:02d}' if month is not None else str(year)
    expected = dict(fxpair=symbol.upper(), timeframe='M1', platform='ASCII', date=str(year), datemonth=suffix)
    if any(fields.get(k) != value for k, value in expected.items()):
        raise ValueError(f'HistData form does not match requested archive: {expected}')
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
        final_url = response.geturl()
    if urllib.parse.urlsplit(final_url).scheme != 'https' or urllib.parse.urlsplit(final_url).hostname not in ('histdata.com', 'www.histdata.com'):
        raise ValueError(f'Unexpected HistData download origin: {final_url}')

    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise RuntimeError(f'HistData did not return a ZIP for {symbol} {year}/{month or ""}')

    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f'DAT_ASCII_{symbol.upper()}_M1_{suffix}.zip'
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        expected_member = path.stem + '.csv'
        if len([n for n in archive.namelist() if Path(n).name.upper() == expected_member.upper()]) != 1 or archive.testzip() is not None:
            raise ValueError(f'Invalid HistData archive members or CRC: {path.name}')
    temporary = path.with_suffix('.zip.part')
    temporary.write_bytes(data)
    temporary.replace(path)
    write_json(metadata_path(path), dict(schema_version=1, provider='HistData',
        source_url=period_url, download_url=final_url, downloaded_at_utc=datetime.now(timezone.utc).isoformat(),
        tls_verified=context is None or context.verify_mode == ssl.CERT_REQUIRED,
        source_symbol=symbol.upper(), period=suffix, sha256=file_hash(path), size_bytes=len(data)))
    return path


def find_zip(raw_dir: Path, symbol: str, year: int, month: int | None) -> Path | None:
    suffix = f'{year}{month:02d}' if month is not None else str(year)
    matches = sorted(raw_dir.glob(f'DAT_ASCII_{symbol.upper()}_M1_{suffix}.zip'))
    return matches[0] if matches else None


def has_verified_download(path: Path) -> bool:
    """An old cached ZIP cannot stand in for an authenticated download receipt."""
    try:
        meta = json.loads(metadata_path(path).read_text(encoding='utf-8'))
        return (meta.get('schema_version') == 1 and meta.get('provider') == 'HistData'
                and meta.get('tls_verified') is True and meta.get('sha256') == file_hash(path)
                and bool(meta.get('source_url')))
    except (OSError, ValueError):
        return False


def read_histdata_zip(path: Path) -> pd.DataFrame:
    meta = verified_archive_metadata(path)
    cleanup = meta['clock_verification'].get('raw_cleanup', {})
    quarantine = cleanup.get('conflict_policy') == 'exclude_all_versions_and_intersecting_candles'
    df = read_raw_archive(path, quarantine_conflicts=quarantine)
    if df.attrs['raw_cleanup'] != cleanup:
        raise ValueError(f'Archive cleanup differs from its verified clock evidence: {path}')
    df['time'] = to_utc(df['time'], meta['clock_verification']['source_clock'])
    validate_frame(df, str(path))
    df.attrs['histdata_source'] = meta
    return df


def round_prices(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if symbol == 'XAUUSD':
        decimals = 2
    elif symbol in {'USA100', 'USTEC', 'USA500', 'US500'}:
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


def save_timeframe(df_m1: pd.DataFrame, symbol: str, timeframe: str, output_dir: Path, sources=None):
    if not sources or any(s.get('clock_verification', {}).get('status') != 'verified'
                           or not s.get('sha256') or not s.get('source_url') or s.get('tls_verified') is not True
                           for s in sources):
        raise ValueError('Verified source receipts are required before writing HistData CSVs')
    df = resample(df_m1, timeframe)
    excluded = []
    for source in sources:
        proof = source['clock_verification']
        local = proof.get('raw_cleanup', {}).get('conflicting_local_minutes', [])
        if local:
            excluded.extend(to_utc(pd.Series(pd.to_datetime(local)), proof['source_clock']).tolist())
    # A candle built from the remaining minutes would conceal missing highs/lows.
    # Remove the whole containing candle, including H4/D1, rather than invent OHLC.
    excluded = sorted(set(excluded))
    affected = pd.DatetimeIndex(excluded).floor(RESAMPLE_RULES[timeframe]).unique()
    bad = df.time.isin(affected)
    omitted_candles = int(bad.sum())
    df = df.loc[~bad].reset_index(drop=True)
    validate_frame(df, f'{symbol} {timeframe}')
    df = round_prices(df, symbol)
    output_dir.mkdir(parents=True, exist_ok=True)
    start = df['time'].iloc[0].strftime('%Y%m%d')
    end = df['time'].iloc[-1].strftime('%Y%m%d')
    path = output_dir / f'{symbol}_{timeframe}_{start}-{end}.csv'
    temp_path = path.with_suffix('.csv.part')
    df.to_csv(temp_path, index=False)
    temp_path.replace(path)
    write_json(metadata_path(path), dict(schema_version=1, provider='HistData', provenance_status='verified',
        time_basis='utc', price_basis='bid', symbol=symbol, timeframe=timeframe, sha256=file_hash(path),
        resampling='UTC midnight aligned, left labelled, left closed; no invented missing candles',
        converted_at_utc=datetime.now(timezone.utc).isoformat(), sources=sources,
        data_quality=dict(conflict_policy='exclude_all_versions_and_intersecting_candles',
            conflicting_utc_minutes=[str(t) for t in excluded],
            resampled_candles_excluded=omitted_candles,
            note='Known conflicting minutes and containing candles omitted; other provider gaps are not filled.')))
    print(f'  saved {path} ({len(df):,} rows)')


def parse_args():
    parser = argparse.ArgumentParser(description='Fetch/convert HistData M1 data.')
    parser.add_argument('--symbols', nargs='+', default=DEFAULT_SYMBOLS)
    parser.add_argument('--timeframes', nargs='+', default=DEFAULT_TIMEFRAMES, choices=RESAMPLE_RULES.keys())
    parser.add_argument('--start-year', type=int, default=2016)
    parser.add_argument('--end-date', type=lambda s: datetime.strptime(s, '%Y-%m-%d'), default=datetime(2026, 8, 1))
    parser.add_argument('--raw-dir', type=Path, default=RAW_DIR)
    parser.add_argument('--output-dir', type=Path, default=OUTPUT_DIR)
    parser.add_argument('--from-zip-dir', type=Path, default=None, help='Convert existing HistData ZIPs instead of downloading.')
    parser.add_argument('--download-missing', action='store_true', help='With --from-zip-dir, download ZIPs not found locally.')
    parser.add_argument('--download-only', action='store_true', help='Download raw archives and receipts; verify their clocks before converting.')
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
        sources = []
        for year, month in periods:
            zip_path = find_zip(source_zip_dir, hist_symbol, year, month)
            if zip_path is not None and args.from_zip_dir is None and not has_verified_download(zip_path):
                zip_path = None
            if zip_path is None:
                if args.from_zip_dir is not None and not args.download_missing:
                    raise FileNotFoundError(f'Missing requested HistData period: {hist_symbol} {year}/{month or ""}')
                print(f'  downloading {hist_symbol} {year}/{month or ""}...')
                zip_path = download_zip(hist_symbol, year, month, args.raw_dir, context)
                time.sleep(args.sleep)
            if not args.download_only:
                chunk = read_histdata_zip(zip_path)
                sources.append(chunk.attrs.pop('histdata_source'))
                chunks.append(chunk)

        if args.download_only:
            continue

        if not chunks:
            print(f'  no data for {project_symbol}')
            continue

        df_m1 = pd.concat(chunks, ignore_index=True)
        df_m1 = df_m1.sort_values('time').reset_index(drop=True)
        validate_frame(df_m1, project_symbol)
        df_m1 = df_m1[df_m1['time'] < args.end_date]

        if df_m1.empty:
            print(f'  no rows before end date for {project_symbol}')
            continue

        for timeframe in args.timeframes:
            save_timeframe(df_m1, project_symbol, timeframe, args.output_dir, sources)


if __name__ == '__main__':
    main()
