"""Audit XM raw candle resolution and clock against hash-bound UTC references."""
import argparse
import json
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from audit_exness_history import examine, RANK, FIELDS
from data.histdata_provenance import file_hash, write_json


def resolution_details(frames, tf):
    result = examine(frames, tf)
    if tf == 'D1':
        return result
    frame = frames[tf]
    matches = pd.Series(False,index=frame.index)
    for higher in RANK[RANK.index(tf)+1:]:
        if higher in frames:
            matches |= frame[FIELDS].eq(frames[higher].reindex(frame.index)[FIELDS]).all(axis=1)
    monthly = matches.resample('MS').sum()
    total_monthly = frame.resample('MS').size()
    counts = frame.resample('D').size()
    weekdays = counts.loc[counts.index.weekday<5]
    medians = weekdays.resample('MS').median()
    threshold = {'M5':150,'M15':50,'H1':16,'H4':4}[tf]
    result['higher_match_monthly'] = {str(k.date()):int(v) for k,v in monthly.items()}
    result['weekday_count_median_by_month'] = {str(k.date()):float(v) for k,v in medians.items()}
    result['suspect_coarse_months'] = [str(k.date()) for k,v in monthly.items()
        if (v>=50 or v>=10 and v/max(1,total_monthly.get(k,0))>=.5)
        and medians.get(k,0)<threshold]
    return result


def clock_windows(raw, reference, offsets=(0,2,3)):
    source = raw.set_index('time')['close']
    ref = reference.set_index('time')['close']
    if source.index.has_duplicates or ref.index.has_duplicates:
        raise ValueError('Clock comparison requires unique timestamps')
    local = pd.Series(source.index)
    eu_offset = ((local-local.dt.tz_localize('Europe/Helsinki', ambiguous='NaT',
        nonexistent='NaT').dt.tz_convert('UTC').dt.tz_localize(None)).dt.total_seconds()/3600)
    # New York midnight plus seven hours matches the usual NY-close broker rule.
    ny_wall = local-pd.Timedelta(hours=7)
    ny_utc = ny_wall.dt.tz_localize('America/New_York', ambiguous='NaT',
        nonexistent='NaT').dt.tz_convert('UTC').dt.tz_localize(None)
    ny_offset = (local-ny_utc).dt.total_seconds()/3600
    groups = pd.DataFrame({'month':source.index.strftime('%Y-%m'),
        'eu':eu_offset.to_numpy(), 'ny':ny_offset.to_numpy()}, index=source.index)
    results = []
    for (month, eu, ny), group in groups.groupby(['month','eu','ny']):
        scores = {}
        for offset in offsets:
            sample = source.loc[group.index].copy()
            sample.index -= pd.Timedelta(hours=offset)
            joined = pd.concat([sample.rename('xm'),ref.rename('utc')],axis=1,join='inner').dropna()
            consecutive = joined.index.to_series().diff()==pd.Timedelta(minutes=5)
            changes = joined.pct_change(fill_method=None).loc[consecutive].dropna()
            corr = changes['xm'].rank().corr(changes['utc'].rank()) if len(changes)>=50 else np.nan
            scores[str(offset)] = dict(pairs=len(changes), correlation=float(corr) if np.isfinite(corr) else None)
        ranked = sorted((s['correlation'], int(o)) for o,s in scores.items() if s['correlation'] is not None)
        good = len(ranked)==len(offsets) and len(ranked)>=2 and ranked[-1][0]>=.8 and ranked[-1][0]-ranked[-2][0]>=.3
        results.append(dict(month=month, eu_offset=int(eu), ny_offset=int(ny),
            observed_offset=ranked[-1][1] if ranked else None, verified=good, scores=scores))
    valid = [r for r in results if r['verified']]
    compatible = [name for name,key in [('european_dst','eu_offset'),('us_dst','ny_offset')]
        if valid and all(r['observed_offset']==r[key] for r in valid)]
    if valid and all(r['observed_offset']==0 for r in valid):
        compatible.append('utc')
    return dict(windows=results, compatible_rules=compatible,
        compatible_rules_by_year={year:[name for name,key in [('european_dst','eu_offset'),('us_dst','ny_offset')]
            if all(r['observed_offset']==r[key] for r in valid if r['month'].startswith(year))]
            for year in sorted({r['month'][:4] for r in valid})},
        european_rule_disagreements=[{k:r[k] for k in ('month','eu_offset','ny_offset','observed_offset')}
            for r in valid if r['observed_offset']!=r['eu_offset']],
        note='Only overlapping windows with at least 50 consecutive M5 returns and '
             'rank correlation >=0.8, margin >=0.3 are verified. No CSV is converted.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    args = parser.parse_args()
    manifest_bytes = (args.snapshot/'inspection.json').read_bytes()
    report = json.loads(manifest_bytes)
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    audit_sha = file_hash(__file__)
    old_quality, old_clock = {}, {}
    for name,target in [('quality.json',old_quality),('clock_audit.json',old_clock)]:
        path = args.snapshot/name
        if path.exists():
            previous = json.loads(path.read_text())
            if previous.get('audit_sha256')==audit_sha:
                target.update(previous)
    results = {}
    clocks = {}
    input_hashes = {}
    for symbol in report['symbols']:
        rows = [r for r in report['history'] if r['symbol']==symbol and r.get('file')]
        input_hashes[symbol] = {r['timeframe']:r['sha256'] for r in rows}
        if any(file_hash(r['file'])!=r['sha256'] for r in rows):
            raise ValueError('Raw file hash changed')
        if (len(rows)==5 and old_quality.get('input_hashes',{}).get(symbol)==input_hashes[symbol]
                and symbol in old_quality.get('symbols',{})):
            cached = old_clock.get('symbols',{}).get(symbol)
            if cached is None or file_hash(cached['reference_file'])==cached['reference_sha256']:
                results[symbol] = old_quality['symbols'][symbol]
                if cached:
                    clocks[symbol] = cached
                print(symbol,'reused unchanged hash-bound audit',flush=True)
                continue
        frames = {}
        for r in rows:
            frames[r['timeframe']] = pd.read_csv(r['file'],parse_dates=['time']).set_index('time')
        results[symbol] = {tf:resolution_details(frames,tf) for tf in RANK if tf in frames}
        if 'M5' in frames:
            # Prefer native UTC over a broker export converted with a historical
            # clock assumption. Cross-checks exposed old IC Markets discrepancies.
            reference_symbol = 'USA100' if symbol=='USTEC' else symbol
            paths = list(Path('data/historical').glob(reference_symbol+'_M5_*.csv'))
            if not paths:
                paths = list(Path('data/historical/mt5_icmarkets_utc').glob(symbol+'_M5_*.csv'))
            if len(paths)==1:
                reference = pd.read_csv(paths[0],usecols=['time','close'],parse_dates=['time'])
                clocks[symbol] = clock_windows(frames['M5'].reset_index(),reference)
                clocks[symbol].update(reference_file=str(paths[0]), reference_sha256=file_hash(paths[0]),
                    reference_contract='Native UTC Dukascopy preferred; normalized IC Markets fallback. '
                        'Timestamp alignment is not proof of independent feed')
        print(symbol, {tf:(r['reported_first'],r.get('first_dense_weekday_window')) for tf,r in results[symbol].items()},flush=True)
    write_json(args.snapshot/'quality.json',dict(symbols=results,
        input_manifest_sha256=manifest_sha, input_hashes=input_hashes, audit_sha256=audit_sha,
        note='Times in this resolution audit are raw broker clock. Native first alone '
             'does not certify resolution; dense windows and remaining gaps need review.'))
    write_json(args.snapshot/'clock_audit.json',dict(symbols=clocks,
        input_manifest_sha256=manifest_sha, input_hashes=input_hashes, audit_sha256=audit_sha))


if __name__ == '__main__':
    main()
