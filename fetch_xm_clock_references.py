"""Fetch hash-bound, native UTC bid candles to check older XM server clocks.

Sequential HTTPS requests to the public Dukascopy chart service. No MT5 calls.
The references are evidence for timing, not replacements for missing XM prices.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlparse

import pandas as pd
import requests

from data.histdata_provenance import file_hash, write_json, validate_frame

URL = 'https://freeserv.dukascopy.com/2.0/index.php'
SYMBOLS = ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCAD', 'USDCHF', 'CADJPY']


def decode_response(payload):
    prefix, suffix = 'xm_clock_reference(', ');'
    if not payload.startswith(prefix) or not payload.endswith(suffix):
        raise ValueError('Unexpected public chart response')
    rows = json.loads(payload[len(prefix):-len(suffix)])
    frame = pd.DataFrame(rows, columns=['epoch_ms', 'open', 'high', 'low', 'close', 'volume'])
    frame['time'] = pd.to_datetime(frame.pop('epoch_ms'), unit='ms', utc=True).dt.tz_localize(None)
    if not frame.empty:
        validate_frame(frame, 'Dukascopy UTC chart response')
    return frame[['time', 'open', 'high', 'low', 'close', 'volume']]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('output/xm_clock_references_20261001'))
    parser.add_argument('--symbols', nargs='+', choices=SYMBOLS, default=SYMBOLS)
    parser.add_argument('--max-pages', type=int, default=8, help='Bound requests per symbol; output may be partial')
    parser.add_argument('--cached-only', action='store_true', help='Process saved HTTPS responses without network requests')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    start, end = pd.Timestamp('2008-01-01'), pd.Timestamp('2016-01-05')
    session = requests.Session()
    for symbol in args.symbols:
        destination = args.output/f'{symbol}_M5_clock_reference.csv'
        sidecar = Path(str(destination)+'.meta.json')
        if destination.exists() and sidecar.exists():
            metadata = json.loads(sidecar.read_text())
            if metadata.get('sha256') != file_hash(destination):
                raise ValueError('Saved reference changed')
            print(symbol, 'reused reference', flush=True)
            continue
        frames, receipts = [], []
        cursor = int(start.tz_localize('UTC').timestamp()*1000)
        while cursor < int(end.tz_localize('UTC').timestamp()*1000):
            parameters = dict(path='chart/json3', splits='true', stocks='true',
                time_direction='N', jsonp='xm_clock_reference', last_update=cursor,
                offer_side='B', instrument=symbol[:3]+'/'+symbol[3:], interval='5MIN', limit=30000)
            cache = args.output/'responses'/f'{symbol}_{cursor}.json'
            receipt_path = Path(str(cache)+'.meta.json')
            if cache.exists() and receipt_path.exists():
                receipt = json.loads(receipt_path.read_text())
                if receipt['sha256'] != file_hash(cache) or not receipt['tls_verified']:
                    raise ValueError('Cached HTTPS response changed')
                payload = cache.read_text(encoding='utf-8')
            else:
                if args.cached_only or len(receipts) >= args.max_pages:
                    break
                for attempt in range(3):
                    try:
                        response = session.get(URL, params=parameters, timeout=(15, 45),
                            headers={'Referer':'https://freeserv.dukascopy.com/2.0/',
                                     'User-Agent':'Mozilla/5.0'}, verify=True)
                        response.raise_for_status()
                        if any(urlparse(r.url).scheme != 'https' or
                               urlparse(r.url).hostname != 'freeserv.dukascopy.com'
                               for r in [*response.history, response]):
                            raise ValueError('Unexpected redirect away from official HTTPS service')
                        payload = response.text
                        decode_response(payload)
                        break
                    except (requests.RequestException, ValueError):
                        if attempt == 2:
                            raise
                        time.sleep(1)
                cache.parent.mkdir(exist_ok=True)
                cache.write_bytes(response.content)
                receipt = dict(url=response.url, sha256=hashlib.sha256(response.content).hexdigest(),
                    tls_verified=True, status_code=response.status_code,
                    received_at_utc=datetime.now(timezone.utc).isoformat(), parameters=parameters)
                write_json(receipt_path, receipt)
            frame = decode_response(payload)
            if frame.empty:
                raise ValueError('Empty reference before requested end')
            frame = frame.loc[frame.time >= pd.to_datetime(cursor, unit='ms')]
            if frame.empty:
                raise ValueError('Reference cursor did not advance')
            frames.append(frame.loc[frame.time < end])
            receipts.append(dict(receipt, response_file=str(cache.resolve())))
            cursor = int(frame.time.iloc[-1].tz_localize('UTC').timestamp()*1000)+300000
            print(symbol, len(receipts), str(frame.time.iloc[-1]), flush=True)
        if not frames:
            print(symbol, 'no cached reference', flush=True)
            continue
        combined = pd.concat(frames, ignore_index=True)
        validate_frame(combined, symbol)
        combined.to_csv(destination, index=False)
        write_json(sidecar, dict(provider='Dukascopy', time_basis='utc', offer_side='bid',
            sha256=file_hash(destination), rows=len(combined), requested_start=str(start),
            requested_end=str(end), actual_first=str(combined.time.iloc[0]),
            actual_last=str(combined.time.iloc[-1]),
            complete_requested_range=bool(combined.time.iloc[0] <= start and
                cursor >= int(end.tz_localize('UTC').timestamp()*1000)),
            receipts=receipts, script_sha256=file_hash(__file__)))
        print(symbol, 'saved', len(combined), flush=True)


if __name__ == '__main__':
    main()
