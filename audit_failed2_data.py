"""Compare the exact input files used by the Failed2 review, before the cutoff."""
import json
from pathlib import Path

import pandas as pd
from data.histdata_provenance import write_json
from research_failed2_review import OUT, SOURCES, paths_for


def main():
    frames={}
    coverage=[]
    for src in SOURCES:
        _,files=paths_for(src)
        for name in files:
            tf=Path(name).name.split('_')[1]
            df=pd.read_csv(name,parse_dates=['time'])
            df=df[(df.time>='2020-01-01')&(df.time<'2026-07-15')].set_index('time').sort_index()
            frames[(src,tf)]=df
            coverage.append(dict(source=src,timeframe=tf,rows=len(df),first=df.index.min(),last=df.index.max(),
                opening_hours=sorted(int(h) for h in df.index.hour.unique()),duplicate_times=int(df.index.duplicated().sum())))
    comparisons=[]
    for src in SOURCES[1:]:
        for tf in ('M5','H1','H4','D1'):
            a=frames[('dukascopy',tf)]
            b=frames[(src,tf)]
            shared=a.index.intersection(b.index)
            same=((a.loc[shared,['open','high','low','close']]-b.loc[shared,['open','high','low','close']]).abs()<1e-8).all(axis=1)
            comparisons.append(dict(other_source=src,timeframe=tf,shared_times=len(shared),
                identical_ohlc=int(same.sum()),identical_pct=float(100*same.mean()) if len(shared) else None,
                duka_times_missing_other=len(a.index.difference(b.index)),other_times_missing_duka=len(b.index.difference(a.index))))
    write_json(OUT/'data_audit.json',dict(coverage=coverage,comparison=comparisons,
        note='Raw source-file timestamps and OHLC, before loader weekend-D1 removal. Calendar/session differences are not automatically missing data.'))
    print(json.dumps(comparisons,indent=2))


if __name__=='__main__':
    main()
