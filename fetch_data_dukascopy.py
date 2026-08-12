"""Download historical OHLC data from Dukascopy for backtesting.

Timestamps are UTC. Output CSVs use the project convention:
    data/historical/<SYMBOL>_<TF>_<YYYYMMDD>-<YYYYMMDD>.csv

Examples:
    python fetch_data_dukascopy.py --symbols EURUSD GBPUSD --timeframes M5 H1
    python fetch_data_dukascopy.py --start-date 2016-01-01 --end-date 2026-08-01

The end date is exclusive. Downloads are made in yearly chunks to avoid
excessive memory use.
"""

import argparse
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import dukascopy_python
from dukascopy_python import instruments


DEFAULT_SYMBOLS = [
    'AUDCAD', 'AUDJPY', 'AUDNZD', 'AUDUSD', 'CADJPY', 'EURAUD', 'EURCAD',
    'EURCHF', 'EURGBP', 'EURJPY', 'EURUSD', 'GBPAUD', 'GBPCAD', 'GBPJPY',
    'GBPNZD', 'GBPUSD', 'NZDJPY', 'NZDUSD', 'USA100', 'USA30', 'USA500',
    'USDCAD', 'USDCHF', 'USDJPY', 'XAUUSD',
]
DEFAULT_TIMEFRAMES = ['M5', 'M15', 'H1', 'H4', 'D1']
DEFAULT_START_DATE = datetime(2016, 1, 1, tzinfo=timezone.utc)
DEFAULT_END_DATE = datetime(2026, 8, 1, tzinfo=timezone.utc)
OUTPUT_DIR = Path('data/historical')


INSTRUMENT_MAP = {
    'EURUSD': instruments.INSTRUMENT_FX_MAJORS_EUR_USD,
    'GBPUSD': instruments.INSTRUMENT_FX_MAJORS_GBP_USD,
    'AUDUSD': instruments.INSTRUMENT_FX_MAJORS_AUD_USD,
    'NZDUSD': instruments.INSTRUMENT_FX_MAJORS_NZD_USD,
    'USDJPY': instruments.INSTRUMENT_FX_MAJORS_USD_JPY,
    'USDCHF': instruments.INSTRUMENT_FX_MAJORS_USD_CHF,
    'USDCAD': instruments.INSTRUMENT_FX_MAJORS_USD_CAD,
    'AUDCAD': instruments.INSTRUMENT_FX_CROSSES_AUD_CAD,
    'AUDJPY': instruments.INSTRUMENT_FX_CROSSES_AUD_JPY,
    'AUDNZD': instruments.INSTRUMENT_FX_CROSSES_AUD_NZD,
    'CADJPY': instruments.INSTRUMENT_FX_CROSSES_CAD_JPY,
    'EURAUD': instruments.INSTRUMENT_FX_CROSSES_EUR_AUD,
    'EURCAD': instruments.INSTRUMENT_FX_CROSSES_EUR_CAD,
    'EURCHF': instruments.INSTRUMENT_FX_CROSSES_EUR_CHF,
    'EURGBP': instruments.INSTRUMENT_FX_CROSSES_EUR_GBP,
    'EURJPY': instruments.INSTRUMENT_FX_CROSSES_EUR_JPY,
    'GBPAUD': instruments.INSTRUMENT_FX_CROSSES_GBP_AUD,
    'GBPCAD': instruments.INSTRUMENT_FX_CROSSES_GBP_CAD,
    'GBPJPY': instruments.INSTRUMENT_FX_CROSSES_GBP_JPY,
    'GBPNZD': instruments.INSTRUMENT_FX_CROSSES_GBP_NZD,
    'NZDJPY': instruments.INSTRUMENT_FX_CROSSES_NZD_JPY,
    'XAUUSD': instruments.INSTRUMENT_FX_METALS_XAU_USD,
    'US30': instruments.INSTRUMENT_IDX_AMERICA_E_D_J_IND,
    'US500': instruments.INSTRUMENT_IDX_AMERICA_E_SANDP_500,
    'USTEC': instruments.INSTRUMENT_IDX_AMERICA_E_NQ_100,
    'DE40': instruments.INSTRUMENT_IDX_EUROPE_E_DAAX,
    # Historical names used by this project's Dukascopy backtests.
    'USA100': instruments.INSTRUMENT_IDX_AMERICA_E_NQ_100,
    'USA30': instruments.INSTRUMENT_IDX_AMERICA_E_D_J_IND,
    'USA500': instruments.INSTRUMENT_IDX_AMERICA_E_SANDP_500,
}


INTERVAL_MAP = {
    'M1': dukascopy_python.INTERVAL_MIN_1,
    'M5': dukascopy_python.INTERVAL_MIN_5,
    'M15': dukascopy_python.INTERVAL_MIN_15,
    'H1': dukascopy_python.INTERVAL_HOUR_1,
    'H4': dukascopy_python.INTERVAL_HOUR_4,
    'D1': dukascopy_python.INTERVAL_DAY_1,
}


def parse_date(value: str) -> datetime:
    return datetime.strptime(value, '%Y-%m-%d').replace(tzinfo=timezone.utc)


def parse_args():
    parser = argparse.ArgumentParser(description='Fetch Dukascopy OHLC history.')
    parser.add_argument('--symbols', nargs='+', default=DEFAULT_SYMBOLS)
    parser.add_argument(
        '--timeframes', nargs='+', default=DEFAULT_TIMEFRAMES,
        choices=INTERVAL_MAP.keys(),
    )
    parser.add_argument('--start-date', type=parse_date, default=DEFAULT_START_DATE)
    parser.add_argument('--end-date', type=parse_date, default=DEFAULT_END_DATE)
    parser.add_argument('--output-dir', type=Path, default=OUTPUT_DIR)
    parser.add_argument('--sleep', type=float, default=1.0)
    parser.add_argument('--retries', type=int, default=3)
    parser.add_argument('--skip-existing', action='store_true')
    return parser.parse_args()


def yearly_periods(start_date: datetime, end_date: datetime):
    cursor = start_date
    while cursor < end_date:
        boundary = datetime(cursor.year + 1, 1, 1, tzinfo=timezone.utc)
        chunk_end = min(boundary, end_date)
        yield cursor, chunk_end
        cursor = chunk_end


def fetch_chunk(instrument, interval, start, end, retries: int, delay: float):
    for attempt in range(1, retries + 1):
        try:
            return dukascopy_python.fetch(
                instrument,
                interval,
                dukascopy_python.OFFER_SIDE_BID,
                start,
                end,
            )
        except Exception:
            if attempt == retries:
                raise
            time.sleep(delay * attempt)


def price_decimals(symbol: str) -> int:
    if symbol in {
        'US30', 'US500', 'USTEC', 'DE40',
        'USA30', 'USA500', 'USA100', 'XAUUSD',
    }:
        return 2
    if 'JPY' in symbol:
        return 3
    return 5


def main():
    args = parse_args()
    if args.start_date >= args.end_date:
        raise SystemExit('--start-date must be earlier than --end-date')

    args.output_dir.mkdir(parents=True, exist_ok=True)
    failures = []

    for symbol_arg in args.symbols:
        symbol = symbol_arg.upper()
        instrument = INSTRUMENT_MAP.get(symbol)
        if instrument is None:
            print(f'WARNING: No Dukascopy instrument mapping for {symbol}; skipping')
            failures.append((symbol, '*', 'no instrument mapping'))
            continue

        for tf in args.timeframes:
            if args.skip_existing and list(args.output_dir.glob(f'{symbol}_{tf}_*.csv')):
                print(f'Skipping existing {symbol} {tf}')
                continue

            interval = INTERVAL_MAP[tf]
            print(f"\n{'=' * 60}\nFetching {symbol} {tf}\n{'=' * 60}")
            all_chunks = []
            pair_failed = False

            for start, end in yearly_periods(args.start_date, args.end_date):
                print(f'  {start.date()} to {end.date()}...', end=' ', flush=True)
                started = time.time()
                try:
                    df = fetch_chunk(
                        instrument, interval, start, end, args.retries, args.sleep,
                    )
                    all_chunks.append(df)
                    print(f'{len(df):,} rows ({time.time() - started:.1f}s)', flush=True)
                except Exception as exc:
                    print(f'ERROR: {exc}', flush=True)
                    failures.append((
                        symbol, tf, f'{start.date()} to {end.date()}: {exc}',
                    ))
                    pair_failed = True
                    break
                time.sleep(args.sleep)

            if pair_failed or not all_chunks:
                continue

            full_df = pd.concat(all_chunks)
            full_df.sort_index(inplace=True)
            full_df = full_df[~full_df.index.duplicated(keep='first')]
            if full_df.empty:
                failures.append((symbol, tf, 'provider returned no rows'))
                continue

            if full_df.index.tz is not None:
                full_df.index = full_df.index.tz_localize(None)
            full_df.index.name = 'time'
            full_df = full_df.reset_index()
            # dukascopy_python treats its end boundary as inclusive. Keep this
            # script's documented end date exclusive.
            exclusive_end = args.end_date.replace(tzinfo=None)
            full_df = full_df[full_df['time'] < exclusive_end]
            if full_df.empty:
                failures.append((symbol, tf, 'no rows before exclusive end date'))
                continue

            for col in ['open', 'high', 'low', 'close']:
                full_df[col] = full_df[col].round(price_decimals(symbol))

            start_str = full_df['time'].iloc[0].strftime('%Y%m%d')
            end_str = full_df['time'].iloc[-1].strftime('%Y%m%d')
            filepath = args.output_dir / f'{symbol}_{tf}_{start_str}-{end_str}.csv'
            temp_path = filepath.with_suffix('.csv.part')
            full_df.to_csv(temp_path, index=False)
            temp_path.replace(filepath)
            print(f'  Saved: {filepath}')
            print(
                f"  Rows: {len(full_df):,}  "
                f"Range: {full_df['time'].iloc[0]} to {full_df['time'].iloc[-1]}"
            )

    if failures:
        print('\nFailures:')
        for symbol, tf, detail in failures:
            print(f'  {symbol} {tf}: {detail}')
        raise SystemExit(1)
    print('\nDone.')


if __name__ == '__main__':
    main()
