"""Untuned controls for missing bars and H4 boundaries; no MT5 operations."""
from collections import Counter
from datetime import datetime, timezone
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from data.historical_loader import load_and_merge, bar_close_time
from data.histdata_provenance import file_hash
from models import BarEvent
from research_ims_reversal_xm import OUT, ROOT, COSTS, replay, write
from research_ims_reversal import metrics

CONTROL = ROOT/'output/ims_reversal_feed_variance_20261002'


def window(segment):
    return {k:datetime.fromisoformat(v) for k,v in segment.items()}


def load(inputs, source, segment):
    bars = load_and_merge([i['path'] for i in inputs[source]], start=segment['load_start'], end=segment['end'])
    return [b for b in bars if bar_close_time(b) <= segment['end']]


def anchored_h4(m5, anchors):
    """Aggregate unchanged M5 prices into audited native XM H4 open times.

    Use only each bucket's own M5 prices. Do not forward-fill or invent quotes.
    OHLC is delivered to replay only at bucket open + four hours.
    """
    frame = pd.DataFrame([dict(time=b.timestamp, open=b.open, high=b.high, low=b.low,
                              close=b.close, volume=b.volume) for b in m5])
    stamps = pd.DatetimeIndex(sorted(anchors))
    frame['bucket_index'] = stamps.searchsorted(pd.DatetimeIndex(frame.time), side='right')-1
    frame = frame[frame.bucket_index >= 0].copy()
    frame['bucket'] = stamps[frame.bucket_index]
    frame = frame[frame.time+pd.Timedelta(minutes=5) <= frame.bucket+pd.Timedelta(hours=4)]
    group = frame.groupby('bucket', sort=True).agg(open=('open','first'), high=('high','max'),
        low=('low','min'), close=('close','last'), volume=('volume','sum'), m5_count=('close','size'))
    bars = [BarEvent('EURUSD','H4',t.to_pydatetime(),r.open,r.high,r.low,r.close,r.volume)
            for t,r in group.iterrows()]
    return bars, dict(buckets=len(group), full_48_m5_buckets=int((group.m5_count == 48).sum()),
                     partial_buckets=int((group.m5_count < 48).sum()))


def main():
    logging.disable(logging.CRITICAL)
    CONTROL.mkdir(parents=True, exist_ok=True)
    previous = json.loads((OUT/'manifest.json').read_text())
    sources = previous['inputs']
    for paths in sources.values():
        assert all(file_hash(i['path']) == i['sha256'] for i in paths)
    cost = COSTS['xm_costs']
    second = window(previous['segments']['2020_2025'][1])
    dk = load(sources,'dukascopy',second)
    hd = load(sources,'histdata',second)
    hist_keys = {(b.timeframe,b.timestamp) for b in hd}
    masked = [b for b in dk if (b.timeframe,b.timestamp) in hist_keys]
    removed = Counter(b.timeframe for b in dk if (b.timeframe,b.timestamp) not in hist_keys)
    missing = replay(masked, second, cost)
    missing.update(control='Dukascopy prices, HistData bar availability, original remaining OHLC',
        removed_bars=dict(removed), yearly={str(y):metrics([t for t in missing['trades'] if t['close_time'].year == y])
                                         for y in (2022,2023,2024)})
    write(CONTROL/'missing_bar_control.json',missing)
    print('Missing-bar control:',json.dumps(missing['yearly'],default=str),flush=True)
    del dk,hd,masked

    recent = window(previous['segments']['2026_viewed'][0])
    dk = load(sources,'dukascopy',recent)
    xm = load(sources,'xm',recent)
    anchors = [b.timestamp for b in xm if b.timeframe == 'H4']
    rebuilt, audit = anchored_h4([b for b in dk if b.timeframe == 'M5'],anchors)
    merged = [b for b in dk if b.timeframe != 'H4']+rebuilt
    durations={'M5':5,'M15':15,'H4':240}
    merged.sort(key=lambda b:(bar_close_time(b),durations[b.timeframe]))
    boundary = replay(merged, recent, cost)
    boundary.update(control='Dukascopy M5/M15 prices, H4 rebuilt on XM native openings', aggregation=audit)
    write(CONTROL/'h4_boundary_control.json',boundary)
    print('H4-boundary control:',json.dumps(boundary['metrics'],default=str),flush=True)
    baseline = {s:json.loads((OUT/f'{s}_2026_viewed_segment1_xm_costs.json').read_text())
                for s in ('dukascopy','xm','mt5_icmarkets_utc')}
    summary = dict(created_at_utc=datetime.now(timezone.utc), cost=cost,
        missing_bar_2023=dict(dukascopy=-5.872671, histdata=19.025982,
                             controlled=missing['yearly']['2023']),
        h4_boundary_2026={s:r['metrics'] for s,r in baseline.items()},
        h4_boundary_control=boundary['metrics'],
        baseline_manifest_sha256=file_hash(OUT/'manifest.json'),
        diagnostic_code_sha256=file_hash(Path(__file__)), parameters_unchanged=True)
    # Retrieve exact saved annual figures, never hardcode rounded references.
    old = json.loads((OUT/'summary.json').read_text())
    for source in ('dukascopy','histdata'):
        summary['missing_bar_2023'][source] = next(s['metrics']['yearly']['2023']
            for s in old if (s['source'],s['period'],s['cost_id']) == (source,'2020_2025','xm_costs'))
    write(CONTROL/'summary.json',summary)


if __name__ == '__main__':
    main()
