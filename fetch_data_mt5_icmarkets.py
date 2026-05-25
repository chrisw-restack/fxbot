"""
Fetch as much broker-native MT5 history as the terminal will provide.

Run this on the Windows VPS where MetaTrader 5 is installed, logged in, and
connected to the IC Markets demo/live account.

Example:
    python fetch_data_mt5_icmarkets.py --start 2016-01-01
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

import config
from data.historical_loader import _server_to_utc
from live_config import create_live_strategy_specs


TIMEFRAME_MAP: dict[str, str] = {
    'M5': 'TIMEFRAME_M5',
    'M15': 'TIMEFRAME_M15',
    'H1': 'TIMEFRAME_H1',
    'H4': 'TIMEFRAME_H4',
    'D1': 'TIMEFRAME_D1',
}


def _parse_date(value: str) -> datetime:
    return datetime.strptime(value, '%Y-%m-%d').replace(tzinfo=timezone.utc)


def _mt5_time_to_utc(timestamp: int | float) -> datetime:
    server_time = datetime.utcfromtimestamp(timestamp)
    return _server_to_utc(server_time)


def _live_pairs() -> list[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for strategy, symbols in create_live_strategy_specs():
        for symbol in symbols:
            for timeframe in strategy.TIMEFRAMES:
                pairs.add((symbol, timeframe))
    rank = {'M5': 0, 'M15': 1, 'H1': 2, 'H4': 3, 'D1': 4}
    return sorted(pairs, key=lambda p: (p[0], rank.get(p[1], 99)))


def _all_config_pairs() -> list[tuple[str, str]]:
    return [(symbol, timeframe) for symbol in config.PIP_SIZE for timeframe in config.TIMEFRAMES]


def _merge_existing(filepath: Path, df: pd.DataFrame) -> pd.DataFrame:
    if filepath.exists() and filepath.stat().st_size > 0:
        existing = pd.read_csv(filepath, parse_dates=['time'])
        df = pd.concat([existing, df], ignore_index=True)
    df = df.drop_duplicates(subset=['time'], keep='last')
    df = df.sort_values('time').reset_index(drop=True)
    return df


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Fetch IC Markets MT5 OHLC history for demo/live validation.'
    )
    parser.add_argument('--start', default='2016-01-01', help='UTC start date, YYYY-MM-DD')
    parser.add_argument('--end', default=None, help='UTC end date, YYYY-MM-DD; default now')
    parser.add_argument(
        '--output-dir',
        default='data/historical/mt5_icmarkets_utc',
        help='Directory for UTC-normalized CSV output',
    )
    parser.add_argument(
        '--symbols',
        nargs='*',
        default=None,
        help='Optional symbol list. Default uses symbols/timeframes from live_config.py',
    )
    parser.add_argument(
        '--timeframes',
        nargs='*',
        choices=sorted(TIMEFRAME_MAP),
        default=None,
        help='Optional timeframe list. Default uses live strategy subscriptions',
    )
    parser.add_argument(
        '--all-config-symbols',
        action='store_true',
        help='Fetch every symbol in config.PIP_SIZE across config.TIMEFRAMES',
    )
    args = parser.parse_args()

    load_dotenv()

    try:
        import MetaTrader5 as mt5
    except ImportError:
        print('ERROR: MetaTrader5 package not installed. Run this on the Windows VPS.')
        return 1

    required = ['MT5_LOGIN', 'MT5_PASSWORD', 'MT5_SERVER']
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        print(f"ERROR: missing environment variables: {', '.join(missing)}")
        return 1

    login = int(os.environ['MT5_LOGIN'])
    password = os.environ['MT5_PASSWORD']
    server = os.environ['MT5_SERVER']

    if not mt5.initialize(login=login, password=password, server=server):
        print(f'ERROR: MT5 initialize failed: {mt5.last_error()}')
        return 1

    start = _parse_date(args.start)
    end = _parse_date(args.end) if args.end else datetime.now(timezone.utc)

    if args.all_config_symbols:
        pairs = _all_config_pairs()
    elif args.symbols or args.timeframes:
        symbols = args.symbols or sorted({symbol for symbol, _ in _live_pairs()})
        timeframes = args.timeframes or sorted({timeframe for _, timeframe in _live_pairs()})
        pairs = [(symbol, timeframe) for symbol in symbols for timeframe in timeframes]
    else:
        pairs = _live_pairs()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f'Connected to MT5 server={server} account={login}')
    print(f'Fetching {len(pairs)} symbol/timeframe pairs from {start.date()} to {end.date()}')
    print(f'Output: {output_dir}')
    print()

    saved = 0
    failed = 0
    for symbol, timeframe in pairs:
        tf_attr = TIMEFRAME_MAP.get(timeframe)
        if tf_attr is None:
            print(f'[SKIP] {symbol} {timeframe}: unsupported timeframe')
            continue

        if not mt5.symbol_select(symbol, True):
            failed += 1
            print(f'[FAIL] {symbol} {timeframe}: symbol_select failed {mt5.last_error()}')
            continue

        rates = mt5.copy_rates_range(symbol, getattr(mt5, tf_attr), start, end)
        if rates is None or len(rates) == 0:
            failed += 1
            print(f'[FAIL] {symbol} {timeframe}: no bars returned {mt5.last_error()}')
            continue

        df = pd.DataFrame(rates)
        df['time'] = df['time'].apply(_mt5_time_to_utc)
        df = df[['time', 'open', 'high', 'low', 'close', 'tick_volume']].rename(
            columns={'tick_volume': 'volume'}
        )

        first = df['time'].iloc[0].strftime('%Y%m%d')
        last = df['time'].iloc[-1].strftime('%Y%m%d')
        filepath = output_dir / f'{symbol}_{timeframe}_{first}-{last}.csv'

        df = _merge_existing(filepath, df)
        df.to_csv(filepath, index=False)
        saved += 1

        print(
            f'[OK]   {symbol:<8} {timeframe:<3} '
            f'{len(df):>7} bars  {df["time"].iloc[0]} -> {df["time"].iloc[-1]}  {filepath}'
        )

    mt5.shutdown()
    print()
    print(f'Done. Saved {saved} file(s), failed {failed} pair(s).')
    return 0 if saved else 1


if __name__ == '__main__':
    sys.exit(main())
