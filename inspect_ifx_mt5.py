"""Download IFX chart history without login, credentials, or trading calls.

Raw server-clock files stay outside the backtest data directories. Historical
clock and resolution review is required before any replay. Downloads are
sequential; completed pairs can be resumed with hash verification.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time

import numpy as np
import pandas as pd

from data.histdata_provenance import file_hash, write_json

TERMINAL = r'C:\Program Files\IFX Brokers MetaTrader 5\terminal64.exe'
SYMBOLS = {s: s + '.ifx' for s in ('EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD',
    'NZDUSD', 'USDCAD', 'USDCHF', 'EURAUD', 'CADJPY', 'GBPCAD')}
SYMBOLS['USTEC'] = 'T100.ifx_m'
MINUTES = {'M5': 5, 'M15': 15, 'H1': 60, 'H4': 240, 'D1': 1440}


def verify_terminal(mt5, path, login, server):
    terminal, account = mt5.terminal_info(), mt5.account_info()
    if terminal is None or account is None or not terminal.connected:
        raise RuntimeError('IFX terminal/account unavailable or disconnected')
    if os.path.normcase(str(Path(terminal.path).resolve())) != os.path.normcase(str(Path(path).resolve().parent)):
        raise RuntimeError('Connected terminal differs from requested IFX installation')
    if account.login != login or account.server != server:
        raise RuntimeError('Account identity changed during collection')
    if account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
        raise RuntimeError('This collector requires a demo account')
    if 'ifx' not in account.company.lower() or 'ifx' not in account.server.lower():
        raise RuntimeError('Account is not identified as IFX')
    return terminal, account


def completed_frame(rates, tf, start, end):
    frame = pd.DataFrame(rates)
    if frame.empty:
        return frame
    frame['time'] = pd.to_datetime(frame['time'], unit='s')
    frame = frame.loc[(frame['time'] >= start) &
        (frame['time'] + pd.Timedelta(minutes=MINUTES[tf]) <= end)].copy()
    if frame['time'].duplicated().any() or not frame['time'].is_monotonic_increasing:
        raise RuntimeError('Duplicate or unordered source timestamps')
    cols = ['open', 'high', 'low', 'close']
    if not np.isfinite(frame[cols].to_numpy()).all() or (frame[cols] <= 0).any().any() or not (
        (frame['high'] >= frame[cols].max(axis=1)) &
        (frame['low'] <= frame[cols].min(axis=1))).all():
        raise RuntimeError('Invalid source OHLC')
    return frame.rename(columns={'tick_volume': 'volume'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--terminal-path', default=TERMINAL)
    parser.add_argument('--expected-login', type=int, required=True)
    parser.add_argument('--expected-server', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--start', default='1970-01-01')
    parser.add_argument('--end', default='2026-10-08')
    parser.add_argument('--symbols', nargs='+', choices=list(SYMBOLS), default=list(SYMBOLS))
    parser.add_argument('--timeframes', nargs='+', choices=list(MINUTES), default=list(MINUTES))
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    start, end = pd.Timestamp(args.start), pd.Timestamp(args.end)
    if start >= end or end > pd.Timestamp.now(tz='UTC').tz_localize(None):
        parser.error('Invalid request boundaries')
    root = args.output_dir
    if root.exists() and any(root.iterdir()) and not args.resume:
        parser.error('Use an empty directory or --resume')
    import MetaTrader5 as mt5
    if not mt5.initialize(args.terminal_path, timeout=20000):
        raise RuntimeError(f'Cannot attach to IFX: {mt5.last_error()}')
    try:
        terminal, account = verify_terminal(mt5, args.terminal_path, args.expected_login, args.expected_server)
        root.mkdir(parents=True, exist_ok=True)
        if args.resume and (root/'inspection.json').exists():
            report = json.loads((root/'inspection.json').read_text())
            if report['account']['login'] != account.login or report['account']['server'] != account.server or report['start'] != str(start) or report['end'] != str(end) or report['script_sha256'] != file_hash(__file__):
                raise RuntimeError('Resume identity, dates, or collector source differ')
            for row in report['history']:
                if row.get('file') and file_hash(row['file']) != row['sha256']:
                    raise RuntimeError('Previously collected file changed')
        else:
            report = dict(provider='IFX', collected_at_utc=datetime.now(timezone.utc).isoformat(),
                terminal_path=terminal.path, terminal_build=terminal.build, maxbars=terminal.maxbars,
                connector_version=mt5.__version__, script_sha256=file_hash(__file__),
                account={k: getattr(account, k) for k in ('login','server','company','currency','trade_mode')},
                start=str(start), end=str(end), time_basis='ifx_server_unreviewed',
                protected_forward_boundary_utc='2026-07-15T00:00:00+00:00',
                symbol_mapping=SYMBOLS, symbols={}, history=[],
                note='Raw server-clock export, not approved UTC. Contains forward-period data; '
                     'do not use post-2026-07-14 prices for selection. No trading calls. '
                     'Returned history is not proof of the broker maximum or gap-free coverage.')
        inventory = mt5.symbols_get()
        if inventory is None:
            raise RuntimeError('Symbol inventory unavailable')
        write_json(root/'all_symbols.json', [dict(name=s.name, path=s.path, description=s.description,
            trade_mode=s.trade_mode) for s in inventory])
        done = {(r['symbol'],r['timeframe']) for r in report['history'] if r.get('file')}
        for canonical in args.symbols:
            broker = SYMBOLS[canonical]
            verify_terminal(mt5, args.terminal_path, args.expected_login, args.expected_server)
            if not mt5.symbol_select(broker, True):
                raise RuntimeError(f'Symbol selection failed: {broker}, {mt5.last_error()}')
            info, tick = mt5.symbol_info(broker), mt5.symbol_info_tick(broker)
            if info is None or info.trade_mode == mt5.SYMBOL_TRADE_MODE_DISABLED:
                raise RuntimeError(f'Missing/disabled mapped instrument: {broker}')
            observed = datetime.now(timezone.utc)
            report['symbols'][canonical] = dict(broker_symbol=broker, properties=info._asdict(),
                quote=tick._asdict() if tick else None, observed_at_utc=observed.isoformat(),
                tick_epoch_minus_observed_seconds=tick.time-observed.timestamp() if tick and tick.time else None)
            write_json(root/'inspection.json', report)
            for tf in args.timeframes:
                if (canonical,tf) in done:
                    continue
                t, _ = verify_terminal(mt5, args.terminal_path, args.expected_login, args.expected_server)
                began, attempts, rates = time.monotonic(), [], None
                for attempt in range(3):
                    print(f'[REQUEST] {canonical} {broker} {tf} attempt {attempt+1}', flush=True)
                    rates = mt5.copy_rates_range(broker, getattr(mt5,'TIMEFRAME_'+tf),
                        start.to_pydatetime().replace(tzinfo=timezone.utc),
                        end.to_pydatetime().replace(tzinfo=timezone.utc))
                    error = mt5.last_error()
                    attempts.append(dict(attempt=attempt+1, last_error=error,
                        returned_bars=len(rates) if rates is not None else 0))
                    verify_terminal(mt5, args.terminal_path, args.expected_login, args.expected_server)
                    if rates is not None and len(rates):
                        break
                row = dict(symbol=canonical, broker_symbol=broker, timeframe=tf,
                    seconds=time.monotonic()-began, attempts=attempts, bars=0, terminal_maxbars=t.maxbars)
                if rates is not None and len(rates):
                    frame = completed_frame(rates,tf,start,end)
                    if not frame.empty:
                        first,last = frame['time'].iloc[0],frame['time'].iloc[-1]
                        path = root/'history'/f'{canonical}_{tf}_{first:%Y%m%d}-{last:%Y%m%d}.csv'
                        path.parent.mkdir(exist_ok=True)
                        frame.to_csv(path,index=False)
                        row.update(file=str(path),sha256=file_hash(path),bars=len(frame),
                            first_server=str(first),last_server=str(last),raw_returned_bars=len(rates),
                            at_terminal_cap=len(rates)>=t.maxbars,
                            yearly_counts={str(k):int(v) for k,v in frame.groupby(frame['time'].dt.year).size().items()})
                        write_json(str(path)+'.meta.json',dict(provider='IFX', symbol=canonical,
                            broker_symbol=broker, timeframe=tf, time_basis='ifx_server_unreviewed',
                            research_status='raw_unreviewed',csv_sha256=row['sha256'],
                            server=account.server,account_login=account.login,
                            requested_start=str(start),requested_end=str(end),
                            collected_at_utc=datetime.now(timezone.utc).isoformat(),
                            spread='Integer MT5 points',volume='tick_volume',properties=info._asdict()))
                report['history'] = [r for r in report['history'] if (r['symbol'],r['timeframe'])!=(canonical,tf)]
                report['history'].append(row)
                write_json(root/'inspection.json',report)
                print(json.dumps(row),flush=True)
        write_json(root/'complete.json',dict(files=sum(bool(r.get('file')) for r in report['history']),
            rows=sum(r['bars'] for r in report['history']),
            expected_pairs=len(args.symbols)*len(args.timeframes),
            hashes_match=all(file_hash(r['file'])==r['sha256'] for r in report['history'] if r.get('file'))))
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
