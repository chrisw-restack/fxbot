"""Compare IFX raw chart coverage, resolution, gaps, and historical clocks."""
import argparse
import json
from pathlib import Path

import pandas as pd

from audit_xm_history import clock_windows, resolution_details
from data.histdata_provenance import file_hash, write_json

DEPENDENCY_HASHES={name:file_hash(name) for name in ('audit_exness_history.py','audit_xm_history.py')}


def gap_details(frame, tf):
    """Inventory observations; do not assume every missing grid slot was tradable."""
    minutes = {'M5':5,'M15':15,'H1':60,'H4':240,'D1':1440}[tf]
    index = frame.index
    delta = index.to_series().diff().dt.total_seconds()/60
    gaps = pd.DataFrame({'previous':index.to_series().shift(), 'next':index,
        'elapsed_minutes':delta}).loc[delta>minutes]
    gaps['missing_grid_slots'] = (gaps['elapsed_minutes']/minutes-1).astype(int)
    gaps['same_weekday_session'] = ((gaps['previous'].dt.date==gaps['next'].dt.date) &
        (gaps['next'].dt.weekday<5))
    serious = gaps.loc[gaps['same_weekday_session'] & (gaps['elapsed_minutes']>=60)]
    counts = frame.resample('D').size()
    missing = counts.loc[(counts.index.weekday<5) & (counts==0)]
    closures = [str(d.date()) for d in missing.index if (d.month,d.day) in [(1,1),(12,25)]]
    others = [str(d.date()) for d in missing.index if (d.month,d.day) not in [(1,1),(12,25)]]
    return dict(grid_gap_events=len(gaps), same_day_weekday_gap_events=int(gaps['same_weekday_session'].sum()),
        same_day_weekday_gaps_at_least_60_minutes=len(serious),
        largest_same_day_weekday_gaps=serious.sort_values('elapsed_minutes',ascending=False).head(25).astype({'previous':str,'next':str}).to_dict('records'),
        full_empty_weekdays=others, christmas_new_year_closure_candidates=closures,
        note='Raw server-clock observations. Weekend, holiday, maintenance, and no-quote '
             'intervals are not automatically data faults. Empty weekdays and long intraday '
             'gaps need session-calendar review. No interpolation or rows removed.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot',type=Path)
    args=parser.parse_args()
    report=json.loads((args.snapshot/'inspection.json').read_text())
    quality,clocks={},{}
    for symbol in report['symbols']:
        rows=[r for r in report['history'] if r['symbol']==symbol and r.get('file')]
        frames={}
        for r in rows:
            if file_hash(r['file'])!=r['sha256']:
                raise ValueError('Source hash changed')
            frames[r['timeframe']]=pd.read_csv(r['file'],parse_dates=['time']).set_index('time')
        if not frames:
            continue
        quality[symbol]={}
        for tf,frame in frames.items():
            detail=resolution_details(frames,tf)
            boundary=detail.get('first_dense_weekday_window') or detail.get('native_first')
            if boundary:
                recent=frame.loc[pd.Timestamp(boundary):]
                detail['dense_history_gaps']=gap_details(recent,tf)
                detail['dense_history_first']=str(recent.index[0])
                detail['dense_history_rows']=len(recent)
            quality[symbol][tf]=detail
        reference_symbol='USA100' if symbol=='USTEC' else symbol
        paths=list(Path('data/historical').glob(reference_symbol+'_M5_*.csv'))
        if len(paths)==1 and 'M5' in frames:
            ref=pd.read_csv(paths[0],usecols=['time','close'],parse_dates=['time'])
            # Preserve the forward holdout. Clock audit uses only past data.
            raw=frames['M5'].reset_index()
            raw=raw.loc[raw['time']<pd.Timestamp('2026-07-15')]
            ref=ref.loc[ref['time']<pd.Timestamp('2026-07-15')]
            clocks[symbol]=clock_windows(raw,ref,offsets=(0,1,2,3))
            clocks[symbol].update(reference_file=str(paths[0]),reference_sha256=file_hash(paths[0]),
                raw_sha256=next(r['sha256'] for r in rows if r['timeframe']=='M5'))
        print(symbol,{tf:(r['reported_first'],r.get('first_dense_weekday_window'),r.get('suspect_coarse_months'))
            for tf,r in quality[symbol].items()},flush=True)
        write_json(args.snapshot/'quality.json',dict(symbols=quality,
            input_manifest_sha256=file_hash(args.snapshot/'inspection.json'),audit_sha256=file_hash(__file__),
            dependency_sha256=DEPENDENCY_HASHES))
        write_json(args.snapshot/'clock_audit.json',dict(symbols=clocks,
            input_manifest_sha256=file_hash(args.snapshot/'inspection.json'),audit_sha256=file_hash(__file__),
            dependency_sha256=DEPENDENCY_HASHES))
    comparisons={}
    for symbol in quality:
        ex_path=Path('output/exness_inspection_20261001_full/quality.json')
        xm_path=Path('output/xm_inspection_20261001_final/quality.json')
        ex=json.loads(ex_path.read_text())['symbols'].get(symbol,{}) if ex_path.exists() else {}
        xm=json.loads(xm_path.read_text())['symbols'].get(symbol,{}) if xm_path.exists() else {}
        ic_paths=list(Path('data/historical/mt5_icmarkets_utc').glob(symbol+'_M5_*.csv'))
        ic_first=min((str(pd.read_csv(p,usecols=['time'],nrows=1)['time'].iloc[0]) for p in ic_paths),default=None)
        comparisons[symbol]=dict(ifx=quality[symbol].get('M5'),
            exness_m5_dense_first=ex.get('M5',{}).get('first_dense_weekday_window'),
            xm_m5_dense_first=xm.get('M5',{}).get('first_dense_weekday_window'),
            xm_m5_coarse_months=xm.get('M5',{}).get('suspect_coarse_months'),icmarkets_stored_m5_first=ic_first)
    write_json(args.snapshot/'comparison.json',dict(symbols=comparisons,
        note='IFX and XM dates are unconverted server clock. Exness dense dates are UTC. '
             'IC Markets is stored export coverage, not a fresh broker maximum probe. '
             'Dense first dates do not certify uninterrupted native resolution.'))


if __name__=='__main__':
    main()
