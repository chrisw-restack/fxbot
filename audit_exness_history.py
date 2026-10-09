"""Identify coarse-history prefixes returned by the Exness MT5 demo server."""
import argparse
import json
from pathlib import Path

import pandas as pd

from data.histdata_provenance import file_hash, write_json


FIELDS = ['open', 'high', 'low', 'close', 'volume']
RANK = ['M5', 'M15', 'H1', 'H4', 'D1']


def examine(frames, tf):
    frame = frames[tf]
    rows = dict(rows=len(frame), reported_first=str(frame.index[0]), last=str(frame.index[-1]))
    if tf == 'D1':
        rows.update(native_first=str(frame.index[0]), coarse_prefix_rows=0,
                    native_rows=len(frame), higher_matches={})
        return rows
    matches = pd.Series(False, index=frame.index)
    examples = {}
    for higher in RANK[RANK.index(tf)+1:]:
        if higher not in frames:
            continue
        coarse = frames[higher].reindex(frame.index)
        equal = frame[FIELDS].eq(coarse[FIELDS]).all(axis=1)
        matches |= equal
        examples[higher] = dict(equal_rows=int(equal.sum()),
            before_2020_equal_rows=int(equal.loc[equal.index<pd.Timestamp('2020-01-01')].sum()))
    own = frame.loc[~matches]
    if own.empty:
        rows.update(native_first=None, coarse_prefix_rows=len(frame), native_rows=0, higher_matches=examples)
        return rows
    first = own.index[0]
    native = frame.loc[first:]
    counts = native.resample('D').size()
    monthly = native.resample('MS').size()
    threshold = {'M5':150, 'M15':50, 'H1':16, 'H4':4}[tf]
    weekdays = counts.loc[counts.index.weekday<5]
    steady = weekdays.rolling(5, min_periods=5).min() >= threshold
    first_steady = None
    if steady.any():
        last_day = steady.loc[steady].index[0]
        first_steady = weekdays.index[weekdays.index.get_loc(last_day)-4]
    rows.update(native_first=str(first), coarse_prefix_rows=int((frame.index<first).sum()),
        native_rows=len(native), higher_matches=examples,
        first_dense_weekday_window=str(first_steady) if first_steady is not None else None,
        dense_threshold_per_day=threshold,
        # Remaining occasional equal bars can be genuine sparse trading; report them, don't silently remove them.
        later_higher_matches=int(matches.loc[first:].sum()),
        first_native_rows=native.head(3).reset_index().to_dict('records'),
        monthly_counts={str(k.date()):int(v) for k,v in monthly.items()},
        weekday_short_sessions={str(k.date()):int(v) for k,v in counts.items()
            if k.weekday()<5 and v<({'M5':200,'M15':65,'H1':16,'H4':4}[tf])},
        weekend_bar_count=int((native.index.dayofweek>=5).sum()))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    args = parser.parse_args()
    report = json.loads((args.snapshot/'inspection.json').read_text())
    complete = json.loads((args.snapshot/'complete.json').read_text())
    assert complete['hashes_match'] and complete['files']==55
    results = {}
    for symbol in report['symbols']:
        rows = [r for r in report['history'] if r['symbol']==symbol]
        frames = {}
        for r in rows:
            assert file_hash(r['file'])==r['sha256']
            frame = pd.read_csv(r['file'], parse_dates=['time']).set_index('time')
            assert len(frame)==r['bars'] and not frame.index.duplicated().any()
            frames[r['timeframe']] = frame
        results[symbol] = {tf:examine(frames,tf) for tf in RANK}
        print(symbol, json.dumps({tf:{k:r[k] for k in ('native_first','native_rows','coarse_prefix_rows')}
                                   for tf,r in results[symbol].items()}), flush=True)
    write_json(args.snapshot/'quality.json', dict(symbols=results,
        input_manifest_sha256=file_hash(args.snapshot/'inspection.json'),
        audit_source_sha256=file_hash(__file__),
        note='Native first is the first row not exactly equal in OHLC and tick volume to any '
            'returned higher timeframe at the same timestamp. A lone distinct bar does NOT '
            'establish proper resolution. First dense window requires five consecutive observed '
            'weekdays above the declared per-day count threshold. Both are diagnostics, not '
            'proof of tick provenance or gap-free coverage. '
            'No raw CSV rows were altered, promoted or replayed.'))


if __name__ == '__main__':
    main()
