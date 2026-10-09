"""Audit XM history and prepare hash-bound UTC candles with replay boundaries.

No interpolation, cross-broker price patching, strategy evaluation, or MT5 calls.
Only measured recent clock windows are eligible. Old clock evidence is retained
as a diagnostic, rather than extrapolated across an unknown historical change.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from functools import lru_cache

import numpy as np
import pandas as pd
from pandas.tseries.holiday import (AbstractHolidayCalendar, Holiday, nearest_workday,
    USMartinLutherKingJr, USPresidentsDay, GoodFriday, USMemorialDay, USLaborDay, USThanksgivingDay)

from audit_exness_history import FIELDS, RANK
from audit_xm_history import clock_windows
from data.histdata_provenance import file_hash, write_json
from inspect_xm_mt5 import MINUTES

FREQUENCIES = dict(M5='5min', M15='15min', H1='h', H4='4h', D1='D')
SCHEMA = 1


class IndexHolidayCandidates(AbstractHolidayCalendar):
    # Calendar context only, not a claim that this CFD always follows NYSE hours.
    rules = [Holiday('New Year',month=1,day=1,observance=nearest_workday),
        USMartinLutherKingJr,USPresidentsDay,GoodFriday,USMemorialDay,
        Holiday('Juneteenth',month=6,day=19,start_date='2022-01-01',observance=nearest_workday),
        Holiday('Independence Day',month=7,day=4,observance=nearest_workday),
        USLaborDay,USThanksgivingDay,Holiday('Christmas',month=12,day=25,observance=nearest_workday)]


@lru_cache(maxsize=40)
def index_holidays(year):
    return set(IndexHolidayCandidates().holidays(start=f'{year-1}-12-25',end=f'{year+1}-01-05').date)


def xm_utc(index):
    """Recent measured EU clock. NaT records are quarantined, never guessed."""
    return index.tz_localize('Europe/Helsinki', ambiguous='NaT', nonexistent='NaT').tz_convert('UTC').tz_localize(None)


def clock_keys(index):
    wall = pd.Series(index)
    eu = ((wall-pd.Series(xm_utc(index))).dt.total_seconds()/3600).fillna(-99).astype(int)
    ny = wall-pd.Timedelta(hours=7)
    ny_utc = ny.dt.tz_localize('America/New_York', ambiguous='NaT', nonexistent='NaT').dt.tz_convert('UTC').dt.tz_localize(None)
    us = ((wall-ny_utc).dt.total_seconds()/3600).fillna(-99).astype(int)
    return pd.MultiIndex.from_arrays([index.strftime('%Y-%m'), eu, us])


def coarser_matches(frames, tf, verified_m5=None):
    frame = frames[tf]
    matched = pd.Series('', index=frame.index, dtype='str')
    for higher in RANK[RANK.index(tf)+1:]:
        other = frames[higher].reindex(frame.index)
        exact = frame[FIELDS].eq(other[FIELDS]).all(axis=1)
        # A flat one-quote bar can legitimately equal its parent. Do not call it
        # mislabeled just because all OHLC values and volumes happen to match.
        nonflat = other.high > other.low
        matched.loc[exact & nonflat] = higher
    if tf!='M5' and verified_m5 is not None and len(verified_m5) and (matched!='').any():
        # Native short sessions can legitimately have identical OHLC and volume
        # in M15/H1/H4. Finer candles from the requested period prove that the
        # parent-looking values do not expose prices from a later period.
        aggregate = verified_m5.resample(FREQUENCIES[tf]).agg(
            {'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).reindex(frame.index)
        proven_own_window = aggregate[FIELDS].eq(frame[FIELDS]).all(axis=1)
        matched.loc[proven_own_window] = ''
    return matched


def invalid_rows(frame, tf):
    values = frame[['open', 'high', 'low', 'close', 'volume', 'spread']].to_numpy(dtype=float)
    finite = np.isfinite(values).all(axis=1)
    price_ok = (values[:, :4] > 0).all(axis=1)
    bounds = (frame.high >= frame[['open', 'low', 'close']].max(axis=1)) & (frame.low <= frame[['open', 'high', 'close']].min(axis=1))
    grid = (frame.index.minute % MINUTES[tf] == 0) if MINUTES[tf] < 60 else ((frame.index.minute == 0) & (frame.index.hour % (MINUTES[tf]//60) == 0))
    grid &= (frame.index.second == 0) & (frame.index.microsecond == 0)
    return pd.Series(~finite | ~price_ok | ~bounds.to_numpy() | ~grid | (values[:, 4:] < 0).any(axis=1), index=frame.index)


def mask_intervals(index, mask, minutes):
    """Group adjacent excluded source rows without inventing replacement prices."""
    positions = np.flatnonzero(np.asarray(mask))
    if not len(positions):
        return []
    groups = np.split(positions, np.flatnonzero(np.diff(positions)>1)+1)
    return [(index[g[0]], index[g[-1]]+pd.Timedelta(minutes=minutes)) for g in groups]


def union_intervals(intervals):
    result = []
    for start, end in sorted(intervals):
        if end <= start:
            raise ValueError('Invalid exclusion interval')
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], end))
        else:
            result.append((start, end))
    return result


def allowed_intervals(first, end, blocked):
    cursor, result = first, []
    for left, right in union_intervals(blocked):
        if right <= first or left >= end:
            continue
        left, right = max(first, left), min(end, right)
        if cursor < left:
            result.append((cursor, left))
        cursor = max(cursor, right)
    if cursor < end:
        result.append((cursor, end))
    return result


def aggregation_audit(m5, higher, tf, point):
    """Compare only complete M5 grids; partial sessions are reported separately."""
    grouped = m5.resample(FREQUENCIES[tf])
    aggregate = grouped.agg({'open':'first', 'high':'max', 'low':'min', 'close':'last', 'volume':'sum'})
    counts = grouped.size()
    needed = MINUTES[tf]//5
    complete = aggregate.loc[counts == needed]
    complete = complete.loc[complete.index.intersection(higher.index)]
    native = higher.reindex(complete.index)
    difference = np.abs(complete[['open','high','low','close']].to_numpy()-native[['open','high','low','close']].to_numpy())
    bad = (difference > point*.1).any(axis=1)
    return dict(complete_bars_compared=len(complete), ohlc_mismatches=int(bad.sum()),
        volume_mismatches=int((complete.volume != native.volume).sum()),
        missing_native_parent_bars=int(((counts==needed) & ~counts.index.isin(higher.index)).sum()),
        partial_or_sparse_m5_groups=int(((counts>0) & (counts<needed)).sum()),
        mismatch_server_times=[str(t) for t in complete.index[bad]])


def gap_inventory(index, tf, symbol, reference_index=None):
    """Inventory holes on a nominal grid, with evidence and cautious labels.

    A hole is not automatically lost quotes. Weekend/holiday/session labels are
    candidates, not proof. Long unexplained gaps require a fresh replay state.
    """
    minutes = MINUTES[tf]
    delta = pd.Timedelta(minutes=minutes)
    steps = index[1:]-index[:-1]
    positions = np.flatnonzero(steps > delta)
    # Common overnight breaks are inferred independently for each year.
    patterns = Counter((index[p].year, index[p].strftime('%H:%M'), index[p+1].strftime('%H:%M'), int(steps[p].total_seconds()/60))
        for p in positions if index[p].date()!=index[p+1].date() and steps[p]<=pd.Timedelta(hours=4)
        and index[p].weekday()<4 and index[p+1].weekday()<5)
    rows, blocked = [], []
    for p in positions:
        left, right = index[p], index[p+1]
        start = left+delta
        missing = int((right-start)/delta)
        dates = pd.date_range(start.normalize(), (right-pd.Timedelta(seconds=1)).normalize(), freq='D')
        weekdays = dates[dates.weekday<5]
        has_holiday = any((d.month,d.day) in [(1,1),(12,25),(12,26)] for d in dates)
        key = (left.year, left.strftime('%H:%M'), right.strftime('%H:%M'), int(steps[p].total_seconds()/60))
        # For higher frames, opening after the weekend can leave a Friday stub.
        weekend = (left.weekday() in (4,5) and right.weekday() in (6,0)
                   and right-left<=pd.Timedelta(days=4)
                   and all(d.weekday()>=5 or d.date() in (left.date(),right.date()) for d in dates))
        count,reference_covered = None,False
        ustart, uend = xm_utc(pd.DatetimeIndex([start, right]))
        if reference_index is not None and not pd.isna(ustart) and not pd.isna(uend) and uend>=reference_index[0] and ustart<=reference_index[-1]:
            count = int(reference_index.searchsorted(uend)-reference_index.searchsorted(ustart))
            reference_covered = ustart>=reference_index[0] and uend<=reference_index[-1]
        index_holiday = (symbol=='USTEC' and any(d.date() in index_holidays(d.year) for d in dates)
                         and reference_covered and count==0)
        if weekend:
            kind = 'weekend_closure_candidate'
        elif (has_holiday or index_holiday) and right-left<=pd.Timedelta(days=5):
            kind = 'holiday_closure_candidate'
        elif minutes>=1440 and len(weekdays)==0:
            kind = 'weekend_closure_candidate'
        elif minutes<=60 and steps[p]<=pd.Timedelta(hours=4) and (patterns[key]>=20 or
                symbol=='USTEC' and patterns[key]>=5 and reference_covered and count==0):
            kind = 'recurring_overnight_break_candidate'
        elif minutes<60 and start.hour==0 and right.hour==0 and right-start<=pd.Timedelta(minutes=30):
            kind = 'rollover_quote_gap_candidate'
        elif right-start<=pd.Timedelta(minutes=30):
            kind = 'short_quote_gap'
        else:
            kind = 'unexplained_long_gap'
        # Price activity elsewhere shows the instrument is not globally closed,
        # but different brokers can have different sessions or missing quotes.
        boundary = kind=='unexplained_long_gap'
        rows.append(dict(symbol=symbol, timeframe=tf, previous_server=str(left), next_server=str(right),
            missing_start_server=str(start), missing_end_server=str(right),
            missing_nominal_slots=missing, missing_minutes=(right-start).total_seconds()/60,
            kind=kind, reference_m5_records=count, reference_window_covered=reference_covered,
            requires_replay_boundary=boundary))
        if boundary:
            blocked.append((start,right))
    return pd.DataFrame(rows), blocked


def calendar_patterns(frame):
    return dict(weekday_rows={str(k):int(v) for k,v in frame.groupby(frame.index.dayofweek).size().items()},
        open_times_by_year={str(y):{str(k):int(v) for k,v in g.groupby(g.index.strftime('%H:%M')).size().items()}
            for y,g in frame.groupby(frame.index.year)},
        zero_volume_by_year={str(y):int((g.volume==0).sum()) for y,g in frame.groupby(frame.index.year)},
        zero_spread_by_year={str(y):int((g.spread==0).sum()) for y,g in frame.groupby(frame.index.year)},
        flat_price_by_year={str(y):int((g.high==g.low).sum()) for y,g in frame.groupby(frame.index.year)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=Path('output/xm_inspection_20261001_final'))
    parser.add_argument('--output', type=Path, default=Path('output/xm_processed_20261001'))
    parser.add_argument('--symbols', nargs='+')
    args = parser.parse_args()
    root = args.snapshot.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((root/'inspection.json').read_text())
    quality = json.loads((root/'quality.json').read_text())
    clocks = json.loads((root/'clock_audit.json').read_text())
    manifest_hash = file_hash(root/'inspection.json')
    for audit in [quality,clocks]:
        if audit['input_manifest_sha256']!=manifest_hash:
            raise ValueError('Audit does not match input snapshot manifest')
        if audit['audit_sha256']!=file_hash('audit_xm_history.py'):
            raise ValueError('Resolution/clock audit code changed; rerun it first')
    symbols = args.symbols or list(manifest['symbols'])
    report = dict(schema_version=SCHEMA, processed_at_utc=datetime.now(timezone.utc).isoformat(),
        processor_sha256=file_hash(__file__), input_manifest_sha256=manifest_hash,
        quality_sha256=file_hash(root/'quality.json'), clock_audit_sha256=file_hash(root/'clock_audit.json'),
        account=manifest['account'], symbols={},
        policy=dict(clock='Per-instrument verified month and EU/US DST regime only; Europe/Helsinki UTC conversion',
            coarse='Exclude prefix, flagged coarse months, and nonflat OHLC+volume exact copies of higher candles',
            gaps='No filling. Weekend/holiday/recurring labels are candidates. Unexplained gaps over 30 minutes split replay.',
            dst='Quarantine candles with non-nominal UTC duration; current replay uses fixed candle durations',
            costs='Zero historical spread is unavailable evidence, not free execution; tick volume is not exchange volume',
            replay='Choose an interval shared by all required timeframes; restart state and warm up after each boundary'))
    for symbol in symbols:
        print('[AUDIT]',symbol,flush=True)
        folder = args.output/symbol
        folder.mkdir(exist_ok=True)
        records = [r for r in manifest['history'] if r['symbol']==symbol and r.get('file')]
        if len(records)!=5:
            raise ValueError('Incomplete symbol snapshot')
        frames = {}
        for record in records:
            if file_hash(record['file'])!=record['sha256']:
                raise ValueError('Raw source hash changed')
            sidecar = json.loads(Path(record['file']+'.meta.json').read_text())
            if sidecar['csv_sha256']!=record['sha256'] or sidecar['provider']!='XM' or sidecar['time_basis']!='xm_server_unreviewed':
                raise ValueError('Raw sidecar contract changed')
            tf = record['timeframe']
            if quality['input_hashes'][symbol][tf]!=record['sha256'] or clocks['input_hashes'][symbol][tf]!=record['sha256']:
                raise ValueError('Audit refers to different source candles')
            frames[tf] = pd.read_csv(record['file'],parse_dates=['time']).set_index('time')
            if len(frames[tf])!=record['bars'] or frames[tf].index.has_duplicates or not frames[tf].index.is_monotonic_increasing:
                raise ValueError('Invalid source ordering/count')
        clock = clocks['symbols'][symbol]
        if clock['compatible_rules']!=['european_dst'] or file_hash(clock['reference_file'])!=clock['reference_sha256']:
            raise ValueError('Recent clock evidence is inconsistent or changed')
        ref = pd.read_csv(clock['reference_file'],usecols=['time','close'],parse_dates=['time'])
        ref = ref.loc[ref.time<pd.Timestamp('2026-07-15')]
        ref_index = pd.DatetimeIndex(ref.time)
        supported = pd.MultiIndex.from_tuples([(w['month'],w['eu_offset'],w['ny_offset'])
            for w in clock['windows'] if w['verified'] and w['observed_offset']==w['eu_offset']])
        symbol_report = dict(raw_files={r['timeframe']:dict(file=r['file'],sha256=r['sha256']) for r in records},
            clock_reference=dict(file=clock['reference_file'],sha256=clock['reference_sha256']),
            clock_windows=clock['windows'], timeframes={})
        clean, reasons, offsets = {}, {}, {}
        for tf in RANK:
            frame = frames[tf]
            minutes = MINUTES[tf]
            utc = xm_utc(frame.index)
            utc_end = xm_utc(frame.index+pd.Timedelta(minutes=minutes))
            verified_m5 = frames['M5'].loc[~reasons['M5'].any(axis=1)] if 'M5' in reasons else None
            all_equal_candidates = coarser_matches(frames,tf)
            matched = coarser_matches(frames,tf,verified_m5)
            first_dense = quality['symbols'][symbol][tf].get('first_dense_weekday_window')
            suspect = quality['symbols'][symbol][tf].get('suspect_coarse_months',[])
            resolution = pd.Series(False,index=frame.index)
            if tf!='D1':
                resolution = pd.Series(True,index=frame.index) if first_dense is None else pd.Series(frame.index<pd.Timestamp(first_dense),index=frame.index)
                resolution |= frame.index.strftime('%Y-%m-01').isin(suspect)
            flags = pd.DataFrame(dict(invalid_ohlc_or_grid=invalid_rows(frame,tf),
                unverified_clock=~clock_keys(frame.index).isin(supported),
                coarse_interval=resolution, copied_higher_candle=matched!='',
                non_nominal_utc_duration=(utc_end-utc)!=pd.Timedelta(minutes=minutes)),index=frame.index)
            bad = flags.any(axis=1)
            quarantine = frame.loc[bad].copy()
            for name in flags:
                quarantine[name] = flags.loc[bad,name]
            quarantine['copied_timeframe'] = matched.loc[bad]
            qpath = folder/f'{symbol}_{tf}_excluded_server_clock.csv'
            quarantine.to_csv(qpath,index_label='time')
            filtered = frame.loc[~bad].copy()
            filtered.index = utc[~bad]
            if filtered.empty or filtered.index.has_duplicates or not filtered.index.is_monotonic_increasing:
                raise ValueError('Prepared UTC output is empty, duplicate or unordered')
            clean[tf], reasons[tf], offsets[tf] = filtered,flags,utc
            gaps, blocked = gap_inventory(frame.index,tf,symbol,ref_index)
            gaps.to_csv(folder/f'{symbol}_{tf}_raw_gaps.csv',index=False)
            symbol_report['timeframes'][tf] = dict(raw_rows=len(frame), raw_first=str(frame.index[0]),raw_last=str(frame.index[-1]),
                excluded_rows=int(bad.sum()), retained_rows=len(filtered), exclusions_by_reason={k:int(v.sum()) for k,v in flags.items()},
                coarse_copy_by_timeframe=matched[matched!=''].value_counts().to_dict(),
                equal_candidates_proven_by_own_m5=int(((all_equal_candidates!='') & (matched=='')).sum()),
                excluded_file=str(qpath.resolve()), excluded_sha256=file_hash(qpath),
                source_patterns=calendar_patterns(frame),
                raw_gap_classes=gaps.kind.value_counts().to_dict() if len(gaps) else {},
                raw_missing_grid_slots_by_class=gaps.groupby('kind').missing_nominal_slots.sum().to_dict() if len(gaps) else {})
        # Complete-grid comparisons use original server boundaries, so H4/D1
        # are not rebuilt with UTC-midnight boundaries or another broker's bars.
        valid_m5 = frames['M5'].loc[~reasons['M5'].any(axis=1)]
        point = manifest['symbols'][symbol]['properties']['point']
        for tf in RANK[1:]:
            aggregation = aggregation_audit(valid_m5,frames[tf],tf,point)
            symbol_report['timeframes'][tf]['aggregation'] = aggregation
            if aggregation['ohlc_mismatches']:
                raise ValueError(f'Native {symbol} {tf} prices disagree with complete M5 candles; investigate before preparation')
        joint_blocked, joint_start, joint_end = [],[],[]
        for record in records:
            tf = record['timeframe']
            filtered = clean[tf]
            info = symbol_report['timeframes'][tf]
            # Re-audit the retained grid. Gaps created by quarantining source rows
            # have explicit exclusions, even when the raw API hid them with a proxy.
            server_kept = frames[tf].index[~reasons[tf].any(axis=1)]
            gaps, blocked_server = gap_inventory(server_kept,tf,symbol,ref_index)
            gaps.to_csv(folder/f'{symbol}_{tf}_prepared_gaps.csv',index=False)
            excluded = mask_intervals(frames[tf].index,reasons[tf].any(axis=1),MINUTES[tf])
            # A copied H1/H4/D1 record contains future prices across the parent
            # span, so its entire claimed parent span is a replay boundary.
            copies = coarser_matches(frames,tf,valid_m5)
            for t,higher in copies[copies!=''].items():
                excluded.append((t,t+pd.Timedelta(minutes=MINUTES[higher])))
            blocked = []
            for left,right in [*excluded,*blocked_server]:
                ul,ur = xm_utc(pd.DatetimeIndex([left,right]))
                if pd.isna(ul) or pd.isna(ur):
                    ul,ur = left-pd.Timedelta(hours=3),right-pd.Timedelta(hours=2)
                if ur>ul:
                    blocked.append((ul,ur))
            first, end = filtered.index[0], filtered.index[-1]+pd.Timedelta(minutes=MINUTES[tf])
            intervals = allowed_intervals(first,end,blocked)
            name = f'{symbol}_{tf}_{first:%Y%m%d}-{filtered.index[-1]:%Y%m%d}.csv'
            path = args.output/'history'/name
            path.parent.mkdir(exist_ok=True)
            filtered.to_csv(path,index_label='time')
            metadata = dict(provider='XM', session_origin='xm', time_basis='utc',
                research_status='approved_native_resolution', processing_schema_version=SCHEMA,
                csv_sha256=file_hash(path), source_sha256=record['sha256'],
                source_manifest_sha256=manifest_hash, processor_sha256=report['processor_sha256'],
                symbol=symbol, broker_symbol=record['broker_symbol'],timeframe=tf,
                clock_rule='Europe/Helsinki only in measured recent month/regime windows',
                coverage_start=str(first),coverage_end=str(end),
                replay_intervals=[dict(start=str(l),end=str(r)) for l,r in intervals],
                small_gaps_preserved=True, historical_spread_zero_is_unknown=True,
                evidence_clock_reference_sha256=clock['reference_sha256'],
                native_sessions_preserved=True)
            write_json(str(path)+'.meta.json',metadata)
            info.update(file=str(path.resolve()),csv_sha256=metadata['csv_sha256'],first_utc=str(first),end_utc_exclusive=str(end),
                prepared_gap_classes=gaps.kind.value_counts().to_dict() if len(gaps) else {},
                replay_intervals=metadata['replay_intervals'])
            joint_blocked.extend(blocked)
            joint_start.append(first)
            joint_end.append(end)
        common = allowed_intervals(max(joint_start),min(joint_end),joint_blocked)
        symbol_report['joint_all_timeframe_intervals'] = [dict(start=str(l),end=str(r),days=(r-l).total_seconds()/86400) for l,r in common]
        symbol_report['longest_joint_intervals'] = sorted(symbol_report['joint_all_timeframe_intervals'],key=lambda r:r['days'],reverse=True)[:10]
        write_json(folder/'audit.json',symbol_report)
        report['symbols'][symbol] = symbol_report
        write_json(args.output/'audit.json',report)
        print('[SAVED]',symbol,'UTC rows',sum(len(f) for f in clean.values()),'joint intervals',len(common),flush=True)
    # New evidence from the earlier public chart service is deliberately not
    # used to approve a clock across a historical regime boundary.
    old_reference = Path('output/xm_clock_references_20261001/EURUSD_M5_clock_reference.csv')
    if old_reference.exists():
        raw_record = next(r for r in manifest['history'] if r['symbol']=='EURUSD' and r['timeframe']=='M5')
        old_meta = json.loads(Path(str(old_reference)+'.meta.json').read_text())
        if file_hash(old_reference)!=old_meta['sha256']:
            raise ValueError('Earlier clock reference hash changed')
        reference = pd.read_csv(old_reference,usecols=['time','close'],parse_dates=['time'])
        raw = pd.read_csv(raw_record['file'],usecols=['time','close'],parse_dates=['time'])
        raw = raw.loc[raw.time.between(reference.time.min(),reference.time.max()+pd.Timedelta(hours=6))]
        old_clock = clock_windows(raw,reference,offsets=tuple(range(-1,6)))
        old_clock.update(reference_sha256=old_meta['sha256'],raw_sha256=raw_record['sha256'],
            verified_clock_candidates=[dict(month=w['month'],eu_offset=w['eu_offset'],observed_offset=w['observed_offset']) for w in old_clock['windows'] if w['verified']],
            status='diagnostic_only_historical_changeover_unresolved',
            note='Verified older windows fit Europe/Berlin UTC+1/+2, not recent Europe/Helsinki UTC+2/+3. '
                 'June 2013 is weak. No older rows approved by this diagnostic.')
        write_json(args.output/'earlier_clock_diagnostic.json',old_clock)
        report['earlier_clock_diagnostic_sha256'] = file_hash(args.output/'earlier_clock_diagnostic.json')
    report['totals'] = dict(raw_rows=sum(t['raw_rows'] for s in report['symbols'].values() for t in s['timeframes'].values()),
        retained_rows=sum(t['retained_rows'] for s in report['symbols'].values() for t in s['timeframes'].values()),
        excluded_rows=sum(t['excluded_rows'] for s in report['symbols'].values() for t in s['timeframes'].values()),
        files=sum(len(s['timeframes']) for s in report['symbols'].values()))
    write_json(args.output/'audit.json',report)
    write_json(args.output/'complete.json',dict(**report['totals'], audit_sha256=file_hash(args.output/'audit.json'),
        output_hashes_match=all(file_hash(t['file'])==t['csv_sha256'] for s in report['symbols'].values() for t in s['timeframes'].values())))
    print(report['totals'],flush=True)


if __name__ == '__main__':
    main()
