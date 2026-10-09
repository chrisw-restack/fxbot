"""Collect XM demo history as unreviewed broker-clock research files.

No .env, login, order submission or changes to the trading bot. UTC conversion
is deliberately deferred until historical clock evidence has been reviewed.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time

import pandas as pd
import numpy as np

from data.histdata_provenance import file_hash, write_json

TERMINAL = r'C:\Program Files\XM Global MT5\terminal64.exe'
SYMBOLS = {s: s+'#' for s in ('EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD',
    'NZDUSD', 'USDCAD', 'USDCHF', 'EURAUD', 'CADJPY', 'GBPCAD')}
SYMBOLS['USTEC'] = 'US100Cash#'
MINUTES = {'M5': 5, 'M15': 15, 'H1': 60, 'H4': 240, 'D1': 1440}


def verify_terminal(mt5, path, login, server):
    terminal, account = mt5.terminal_info(), mt5.account_info()
    if terminal is None or account is None or not terminal.connected:
        raise RuntimeError('Terminal/account unavailable or disconnected')
    if os.path.normcase(str(Path(terminal.path).resolve())) != os.path.normcase(str(Path(path).resolve().parent)):
        raise RuntimeError('Connected terminal differs from the requested XM installation')
    if account.login != login or account.server != server:
        raise RuntimeError('Account identity changed during collection')
    if account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
        raise RuntimeError('A demo account is required')
    if 'xm' not in account.company.lower() or not account.server.lower().startswith('xm'):
        raise RuntimeError('The connected account is not identified as XM')
    return terminal, account


def raw_completed_frame(rates, tf, start, end):
    frame = pd.DataFrame(rates)
    if frame.empty:
        return frame
    # The epoch is rendered as broker wall-clock, NOT asserted to be UTC.
    frame['time'] = pd.to_datetime(frame['time'], unit='s')
    frame = frame.loc[(frame['time'] >= start) &
        (frame['time']+pd.Timedelta(minutes=MINUTES[tf]) <= end)].copy()
    if frame['time'].duplicated().any() or not frame['time'].is_monotonic_increasing:
        raise RuntimeError('Duplicate or unordered broker timestamps')
    cols = ['open', 'high', 'low', 'close']
    if not np.isfinite(frame[cols].to_numpy()).all() or (frame[cols] <= 0).any().any() or not ((frame['high'] >= frame[cols].max(axis=1)) &
            (frame['low'] <= frame[cols].min(axis=1))).all():
        raise RuntimeError('Invalid source OHLC')
    return frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--terminal-path', default=TERMINAL)
    parser.add_argument('--expected-login', type=int, required=True)
    parser.add_argument('--expected-server', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--start', default='2008-01-01')
    parser.add_argument('--end', default='2026-07-15', help='Conservative broker-clock research cutoff')
    parser.add_argument('--sample-seconds', type=int, default=60)
    parser.add_argument('--symbols', nargs='+', choices=list(SYMBOLS), default=list(SYMBOLS))
    parser.add_argument('--timeframes', nargs='+', choices=list(MINUTES), default=list(MINUTES))
    parser.add_argument('--details-only', action='store_true')
    args = parser.parse_args()
    if args.details_only:
        args.timeframes = []
    start, end = pd.Timestamp(args.start), pd.Timestamp(args.end)
    if start >= end or end > pd.Timestamp.now() or not 0 <= args.sample_seconds <= 3600:
        parser.error('Invalid date boundary or quote sample duration')
    root = args.output_dir
    if root.exists() and any(root.iterdir()):
        parser.error('Use a new empty snapshot directory')
    import MetaTrader5 as mt5
    if not mt5.initialize(args.terminal_path, timeout=15000):
        raise RuntimeError(f'Cannot attach to XM: {mt5.last_error()}')
    try:
        terminal, account = verify_terminal(mt5, args.terminal_path, args.expected_login, args.expected_server)
        root.mkdir(parents=True, exist_ok=True)
        report = dict(collected_at_utc=datetime.now(timezone.utc).isoformat(),
            terminal_path=terminal.path, terminal_build=terminal.build, maxbars=terminal.maxbars,
            connector_version=mt5.__version__, script_sha256=file_hash(__file__),
            account={k:getattr(account,k) for k in ('login','server','company','currency',
                'trade_mode','margin_mode','leverage','balance')},
            time_basis='xm_server_unreviewed', start=str(start), end=str(end),
            symbol_mapping=SYMBOLS, symbols={}, history=[],
            note='Raw broker-clock timestamps, not UTC. Conservative cutoff omits late '
                 'July 14 UTC bars if the server is ahead of UTC. No trading calls.')
        inventory = mt5.symbols_get()
        if inventory is None:
            raise RuntimeError('Symbol inventory unavailable')
        write_json(root/'all_symbol_names.json', [s.name for s in inventory])
        for canonical in args.symbols:
            broker = SYMBOLS[canonical]
            verify_terminal(mt5, args.terminal_path, args.expected_login, args.expected_server)
            if not mt5.symbol_select(broker, True):
                raise RuntimeError(f'Symbol selection failed for {broker}: {mt5.last_error()}')
            info, tick = mt5.symbol_info(broker), mt5.symbol_info_tick(broker)
            if info is None or 'ultra low' not in info.path.lower():
                raise RuntimeError(f'Unexpected Ultra Low instrument: {broker}')
            observed = datetime.now(timezone.utc)
            report['symbols'][canonical] = dict(broker_symbol=broker, properties=info._asdict(),
                quote=tick._asdict() if tick else None,
                observed_at_utc=observed.isoformat(),
                tick_epoch_minus_observed_seconds=tick.time-observed.timestamp() if tick else None)
            write_json(root/'inspection.json', report)
            print(f'[SYMBOL] {canonical} = {broker}; {info.path}', flush=True)
            for tf in args.timeframes:
                t, _ = verify_terminal(mt5, args.terminal_path, args.expected_login, args.expected_server)
                began = time.monotonic()
                print(f'[REQUEST] {canonical} {tf}', flush=True)
                # Datetimes are UTC-aware to prevent Python's local clock conversion;
                # MT5's returned epoch clock contract is reviewed separately.
                attempts = []
                for attempt in range(3):
                    rates = mt5.copy_rates_range(broker, getattr(mt5, 'TIMEFRAME_'+tf),
                        start.to_pydatetime().replace(tzinfo=timezone.utc),
                        end.to_pydatetime().replace(tzinfo=timezone.utc))
                    error = mt5.last_error()
                    attempts.append(dict(attempt=attempt+1, last_error=error,
                        returned_bars=len(rates) if rates is not None else 0))
                    if rates is not None and len(rates):
                        break
                    print(f'[RETRY] {canonical} {tf}: {error}',flush=True)
                    verify_terminal(mt5, args.terminal_path, args.expected_login, args.expected_server)
                verify_terminal(mt5, args.terminal_path, args.expected_login, args.expected_server)
                row = dict(symbol=canonical, broker_symbol=broker, timeframe=tf,
                    seconds=time.monotonic()-began, last_error=error, attempts=attempts,
                    bars=0, terminal_maxbars=t.maxbars)
                if rates is not None and len(rates):
                    frame = raw_completed_frame(rates, tf, start, end)
                    if not frame.empty:
                        first, last = frame['time'].iloc[0], frame['time'].iloc[-1]
                        path = root/'history'/f'{canonical}_{tf}_{first:%Y%m%d}-{last:%Y%m%d}.csv'
                        path.parent.mkdir(exist_ok=True)
                        frame.rename(columns={'tick_volume':'volume'}).to_csv(path, index=False)
                        row.update(file=str(path), sha256=file_hash(path), bars=len(frame),
                            first_server=str(first), last_server=str(last), raw_returned_bars=len(rates),
                            at_terminal_cap=len(rates)>=t.maxbars,
                            yearly_counts={str(k):int(v) for k,v in frame.groupby(frame['time'].dt.year).size().items()})
                        write_json(str(path)+'.meta.json', dict(provider='XM', symbol=canonical,
                            broker_symbol=broker, timeframe=tf, time_basis='xm_server_unreviewed',
                            research_status='raw_unreviewed', server=account.server,
                            account_login=account.login, csv_sha256=row['sha256'],
                            collected_at_utc=datetime.now(timezone.utc).isoformat(),
                            requested_start=str(start), requested_end=str(end),
                            spread='Integer MT5 points', volume='tick_volume', properties=info._asdict()))
                report['history'].append(row)
                write_json(root/'inspection.json', report)
                print(json.dumps(row), flush=True)
        from config import PIP_SIZE
        quotes = []
        deadline = time.monotonic()+args.sample_seconds
        while time.monotonic()<deadline:
            verify_terminal(mt5, args.terminal_path, args.expected_login, args.expected_server)
            observed = datetime.now(timezone.utc)
            for canonical in args.symbols:
                broker = SYMBOLS[canonical]
                tick = mt5.symbol_info_tick(broker)
                if tick and 0<tick.bid<=tick.ask:
                    observed = datetime.now(timezone.utc)
                    # Do not assume the epoch is UTC to filter freshness. Preserve
                    # its apparent offset and count distinct updates in the report.
                    quotes.append(dict(symbol=canonical, sampled_at_utc=observed.isoformat(),
                        tick_time_msc=tick.time_msc, epoch_minus_observed_seconds=tick.time-observed.timestamp(),
                        bid=tick.bid, ask=tick.ask, spread_project_pips=(tick.ask-tick.bid)/PIP_SIZE[canonical]))
            time.sleep(min(1., max(0.,deadline-time.monotonic())))
        pd.DataFrame(quotes).to_csv(root/'quote_samples.csv', index=False)
        write_json(root/'complete.json', dict(files=sum(bool(r.get('file')) for r in report['history']),
            rows=sum(r['bars'] for r in report['history']),
            hashes_match=all(file_hash(r['file'])==r['sha256'] for r in report['history'] if r.get('file'))))
        print(f'Snapshot: {root.resolve()}', flush=True)
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
