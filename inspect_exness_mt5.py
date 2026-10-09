"""Read the explicitly selected Exness DEMO terminal; never submit orders.

No .env loading, credentials, account login, or bot configuration changes.
History is kept in isolated research snapshots, using Exness's GMT+0 clock.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time

import pandas as pd

from data.histdata_provenance import file_hash, write_json

SYMBOLS = ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'NZDUSD', 'USDCAD',
           'USDCHF', 'EURAUD', 'CADJPY', 'GBPCAD', 'USTEC']
MINUTES = {'M5': 5, 'M15': 15, 'H1': 60, 'H4': 240, 'D1': 1440}
TERMINAL = r'C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe'


def utc_date(value):
    return datetime.strptime(value, '%Y-%m-%d').replace(tzinfo=timezone.utc)


def verify_terminal(mt5, terminal_path, expected_login, expected_server):
    terminal, account = mt5.terminal_info(), mt5.account_info()
    if terminal is None or account is None or not terminal.connected:
        raise RuntimeError('Terminal/account unavailable or disconnected')
    actual = os.path.normcase(str(Path(terminal.path).resolve()))
    expected = os.path.normcase(str(Path(terminal_path).resolve().parent))
    if actual != expected:
        raise RuntimeError('Connected terminal path differs from the requested Exness installation')
    if account.login != expected_login or account.server != expected_server:
        raise RuntimeError('The logged-in account changed; refusing to mix account data')
    if account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
        raise RuntimeError('This data collector requires a DEMO account')
    if 'exness' not in account.company.lower() or 'exness' not in account.server.lower():
        raise RuntimeError('The connected account is not identified as Exness')
    return terminal, account


def completed_frame(rates, timeframe, start, end):
    frame = pd.DataFrame(rates)
    if frame.empty:
        return frame
    frame['time'] = pd.to_datetime(frame['time'], unit='s', utc=True)
    close = frame['time'] + pd.Timedelta(minutes=MINUTES[timeframe])
    frame = frame.loc[(frame['time'] >= start) & (close <= end)].copy()
    if frame['time'].duplicated().any():
        raise RuntimeError('Duplicate source timestamps; inspect before replay')
    if not frame['time'].is_monotonic_increasing:
        raise RuntimeError('Source timestamps are not increasing')
    valid = ((frame['high'] >= frame[['open', 'close', 'low']].max(axis=1)) &
             (frame['low'] <= frame[['open', 'close', 'high']].min(axis=1)))
    if not valid.all():
        raise RuntimeError('Invalid OHLC geometry; inspect before replay')
    # No IC Markets conversion. Sidecar explicitly declares the UTC contract.
    frame['time'] = frame['time'].dt.tz_localize(None)
    return frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--terminal-path', default=TERMINAL)
    parser.add_argument('--expected-login', type=int, required=True)
    parser.add_argument('--expected-server', required=True)
    parser.add_argument('--symbols', nargs='+', default=SYMBOLS)
    parser.add_argument('--timeframes', nargs='+', choices=MINUTES, default=list(MINUTES))
    parser.add_argument('--start', default='2008-01-01')
    parser.add_argument('--end', default='2026-07-15', help='Exclusive UTC research boundary')
    parser.add_argument('--download', action='store_true', help='Also retrieve completed OHLC history')
    parser.add_argument('--sample-seconds', type=int, default=0, help='Poll quotes once per second, independently of historical spread fields')
    parser.add_argument('--output-dir', default=None, help='New, empty research snapshot directory')
    args = parser.parse_args()
    start, end = utc_date(args.start), min(utc_date(args.end), datetime.now(timezone.utc))
    if start >= end:
        parser.error('start must precede end')
    if not 0 <= args.sample_seconds <= 3600:
        parser.error('sample-seconds must be between zero and 3600')
    import MetaTrader5 as mt5
    if not mt5.initialize(args.terminal_path, timeout=15000):
        raise RuntimeError(f'Could not attach to Exness MT5: {mt5.last_error()}')
    try:
        terminal, account = verify_terminal(mt5, args.terminal_path, args.expected_login, args.expected_server)
        now = datetime.now(timezone.utc)
        root = Path(args.output_dir or f'output/exness_inspection_{now:%Y%m%d_%H%M%S_%f}')
        if root.exists() and any(root.iterdir()):
            raise RuntimeError('Use a new empty output directory; snapshots are immutable')
        root.mkdir(parents=True, exist_ok=True)
        available = mt5.symbols_get()
        if available is None:
            raise RuntimeError(f'Symbol inventory unavailable: {mt5.last_error()}')
        inventory = {s.name: s for s in available}
        report = dict(collected_at_utc=now.isoformat(), terminal_path=terminal.path,
            terminal_build=terminal.build, connector_version=mt5.__version__, maxbars=terminal.maxbars,
            account={k:getattr(account,k) for k in ('login','server','company','currency','trade_mode',
                                                    'margin_mode','leverage','balance')},
            script_sha256=file_hash(__file__), start=start.isoformat(), end=end.isoformat(),
            time_basis='utc', timezone_evidence='https://get.exness.help/hc/en-us/articles/360014390760-What-is-the-default-timezone-set-for-MetaTrader',
            symbols={}, history=[], note='Returned coverage is not proof of broker maximum history. '
                'Terminal maxbars and asynchronous history loading can limit each request. '
                'Quotes/spreads are snapshots, not measured session costs. No trading calls.')
        write_json(root/'all_symbol_names.json', list(inventory))
        for symbol in args.symbols:
            verify_terminal(mt5, args.terminal_path, args.expected_login, args.expected_server)
            if symbol not in inventory:
                report['symbols'][symbol] = dict(error='Exact symbol missing',
                    candidates=[s for s in inventory if s.startswith(symbol)])
                continue
            if not mt5.symbol_select(symbol, True):
                report['symbols'][symbol] = dict(error='symbol_select failed', details=mt5.last_error())
                continue
            info, tick = mt5.symbol_info(symbol), mt5.symbol_info_tick(symbol)
            if info is None:
                raise RuntimeError(f'Symbol properties unavailable: {symbol}')
            detail = dict(properties=info._asdict(), quote=tick._asdict() if tick else None)
            if tick:
                detail.update(quote_time_utc=datetime.fromtimestamp(tick.time, timezone.utc).isoformat(),
                              quote_age_seconds=now.timestamp()-tick.time,
                              spread_price=tick.ask-tick.bid)
                if tick.ask > 1:
                    detail['buy_one_lot_loss_for_one_price_unit'] = mt5.order_calc_profit(
                        mt5.ORDER_TYPE_BUY, symbol, 1., tick.ask, tick.ask-1.)
            report['symbols'][symbol] = detail
            write_json(root/'inspection.json', report)
            print(f"[SYMBOL] {symbol}: {info.path}; contract={info.trade_contract_size:g}; "
                  f"min/step={info.volume_min:g}/{info.volume_step:g}", flush=True)
            if not args.download:
                continue
            for timeframe in args.timeframes:
                request_terminal, _ = verify_terminal(mt5, args.terminal_path, args.expected_login, args.expected_server)
                began = time.monotonic()
                rates = mt5.copy_rates_range(symbol, getattr(mt5, 'TIMEFRAME_'+timeframe), start, end)
                error = mt5.last_error()
                verify_terminal(mt5, args.terminal_path, args.expected_login, args.expected_server)
                row = dict(symbol=symbol, timeframe=timeframe, seconds=time.monotonic()-began,
                           last_error=error, bars=0, terminal_maxbars=request_terminal.maxbars)
                if rates is not None and len(rates):
                    frame = completed_frame(rates, timeframe, start, end)
                    if not frame.empty:
                        first, last = frame['time'].iloc[0], frame['time'].iloc[-1]
                        path = root/'history'/f'{symbol}_{timeframe}_{first:%Y%m%d}-{last:%Y%m%d}.csv'
                        path.parent.mkdir(exist_ok=True)
                        # Spread is MT5 integer points, not our project pip convention.
                        frame.rename(columns={'tick_volume':'volume'}).to_csv(path, index=False)
                        sha = file_hash(path)
                        row.update(bars=len(frame), first_utc=str(first), last_utc=str(last),
                            file=str(path), sha256=sha,
                            yearly_counts={str(k):int(v) for k,v in frame.groupby(frame['time'].dt.year).size().items()},
                            at_terminal_cap=len(rates)>=request_terminal.maxbars,
                            raw_returned_bars=len(rates), open_hour_counts={str(k):int(v) for k,v in frame['time'].dt.hour.value_counts().items()})
                        write_json(str(path)+'.meta.json', dict(provider='Exness',
                            time_basis='utc', session_origin='exness', symbol=symbol, timeframe=timeframe,
                            research_status='raw_unreviewed',
                            server=account.server, account_login=account.login, source='MT5 copy_rates_range',
                            csv_sha256=sha, collected_at_utc=datetime.now(timezone.utc).isoformat(),
                            requested_start=start.isoformat(), requested_end=end.isoformat(),
                            terminal_maxbars=request_terminal.maxbars, source_timezone='GMT+0',
                            timezone_evidence=report['timezone_evidence'], volume='tick_volume',
                            spread='Integer MT5 points, not pips', properties=info._asdict()))
                report['history'].append(row)
                write_json(root/'inspection.json', report)
                print(json.dumps(row), flush=True)
        if args.sample_seconds:
            from config import PIP_SIZE
            quote_rows = []
            deadline = time.monotonic()+args.sample_seconds
            while time.monotonic()<deadline:
                verify_terminal(mt5, args.terminal_path, args.expected_login, args.expected_server)
                observed = datetime.now(timezone.utc)
                for symbol, detail in report['symbols'].items():
                    if 'properties' not in detail:
                        continue
                    tick = mt5.symbol_info_tick(symbol)
                    if tick and 0<tick.bid<=tick.ask and 0<=observed.timestamp()-tick.time<=30:
                        quote_rows.append(dict(symbol=symbol, sampled_at_utc=observed.isoformat(),
                            tick_time_msc=tick.time_msc, bid=tick.bid, ask=tick.ask,
                            spread_price=tick.ask-tick.bid,
                            spread_project_pips=(tick.ask-tick.bid)/PIP_SIZE.get(symbol,detail['properties']['point'])))
                time.sleep(min(1., max(0.,deadline-time.monotonic())))
            quotes = pd.DataFrame(quote_rows)
            quotes.to_csv(root/'quote_samples.csv',index=False)
            summaries = {}
            if not quotes.empty:
                for symbol, group in quotes.groupby('symbol'):
                    values = group['spread_project_pips']
                    summaries[symbol] = dict(samples=len(group), distinct_ticks=group['tick_time_msc'].nunique(),
                        mean=float(values.mean()), median=float(values.median()), p95=float(values.quantile(.95)),
                        max=float(values.max()), min=float(values.min()))
            report['spread_sample'] = dict(duration_seconds=args.sample_seconds, symbols=summaries,
                note='Time-weighted one-second samples of quotes no older than 30 seconds. '
                     'One short collection is not representative of NY entries, rollover or execution.')
            write_json(root/'inspection.json',report)
        write_json(root/'complete.json', dict(symbols=len(report['symbols']), pairs=len(report['history']),
            files=sum(bool(r.get('file')) for r in report['history']),
            hashes_match=all(file_hash(r['file'])==r['sha256'] for r in report['history'] if r.get('file'))))
        print(f'Snapshot: {root.resolve()}', flush=True)
    finally:
        mt5.shutdown()  # Disconnect Python only; leave the terminal running.


if __name__ == '__main__':
    main()
