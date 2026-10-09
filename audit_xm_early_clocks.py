"""Inspect daily clock shifts in weak older XM monthly clock windows."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from data.histdata_provenance import file_hash, write_json


def daily_offsets(raw, reference, offsets=tuple(range(-1,6))):
    source = raw.set_index('time').close
    ref = reference.set_index('time').close
    if source.index.has_duplicates or ref.index.has_duplicates:
        raise ValueError('Clock inputs must have unique timestamps')
    result = []
    for day, group in source.groupby(source.index.normalize()):
        scores = {}
        for offset in offsets:
            shifted = group.copy()
            shifted.index -= pd.Timedelta(hours=offset)
            joined = pd.concat([shifted.rename('xm'),ref.rename('reference')],axis=1,join='inner').dropna()
            changes = joined.pct_change(fill_method=None).loc[joined.index.to_series().diff()==pd.Timedelta(minutes=5)].dropna()
            correlation = changes.xm.rank().corr(changes.reference.rank()) if len(changes)>=50 else np.nan
            scores[str(offset)] = dict(pairs=len(changes),correlation=float(correlation) if np.isfinite(correlation) else None)
        ranked = sorted((s['correlation'],int(o)) for o,s in scores.items() if s['correlation'] is not None)
        verified = len(ranked)==len(offsets) and ranked[-1][0]>=.8 and ranked[-1][0]-ranked[-2][0]>=.3
        result.append(dict(day=str(day.date()),observed_offset=ranked[-1][1] if ranked else None,
            verified=verified,scores=scores))
    return result


def main():
    root = Path('output/xm_processed_20261001')
    earlier = json.loads((root/'earlier_clock_diagnostic.json').read_text())
    manifest = json.loads(Path('output/xm_inspection_20261001_final/inspection.json').read_text())
    raw_path = next(r['file'] for r in manifest['history'] if r['symbol']=='EURUSD' and r['timeframe']=='M5')
    reference_path = Path('output/xm_clock_references_20261001/EURUSD_M5_clock_reference.csv')
    if file_hash(raw_path)!=earlier['raw_sha256'] or file_hash(reference_path)!=earlier['reference_sha256']:
        raise ValueError('Older clock evidence no longer matches its prices')
    months = {w['month'] for w in earlier['windows'] if not w['verified']}
    raw = pd.read_csv(raw_path,usecols=['time','close'],parse_dates=['time'])
    raw = raw.loc[raw.time.dt.strftime('%Y-%m').isin(months)]
    reference = pd.read_csv(reference_path,usecols=['time','close'],parse_dates=['time'])
    evidence = daily_offsets(raw,reference)
    write_json(root/'earlier_daily_clock_audit.json',dict(raw_sha256=earlier['raw_sha256'],
        reference_sha256=earlier['reference_sha256'],auditor_sha256=file_hash(__file__),
        weak_months=sorted(months),days=evidence,
        note='Diagnostic only. No older source row or clock regime is approved by this check.'))
    print([(d['day'],d['observed_offset'],d['verified']) for d in evidence],flush=True)


if __name__ == '__main__':
    main()
