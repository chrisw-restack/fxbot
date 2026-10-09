"""Verify the completed XM dataset and write its practical research report."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from data.histdata_provenance import file_hash, write_json
from data.historical_loader import load_csv
from prepare_xm_history import FREQUENCIES, MINUTES, allowed_intervals, xm_utc

ROOT = Path('output/xm_processed_20261001')
REPORT = Path('strategy_log/xm_data_audit_20261001.md')


def count_csv_rows(path):
    # Processor outputs only numeric cells and single-line timestamp fields.
    with Path(path).open('rb') as stream:
        return sum(chunk.count(b'\n') for chunk in iter(lambda:stream.read(1024*1024),b''))-1


def partial_comparison(utc_m5, native_higher, tf, point):
    raw = utc_m5.copy()
    raw.index = raw.index.tz_localize('UTC').tz_convert('Europe/Helsinki').tz_localize(None)
    group = raw.resample(FREQUENCIES[tf])
    aggregate = group.agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'})
    count = group.size()
    partial = aggregate.loc[(count>0) & (count<MINUTES[tf]//5)]
    partial = partial.loc[partial.index.intersection(native_higher.index)]
    native = native_higher.reindex(partial.index)
    same = np.isclose(partial[['open','high','low','close']],native[['open','high','low','close']],rtol=0,atol=point*.1).all(axis=1)
    return dict(partial_bars_compared=len(partial), ohlc_matches=int(same.sum()),
        ohlc_differences=int((~same).sum()),
        difference_server_times=[str(t) for t in partial.index[~same]],
        note='A partial finer grid can miss prices. Differences are diagnostics, not corrections to native candles.')


def restrict_price_hazards(info, partial):
    hazards = []
    evidence = []
    for tf,comparison in partial.items():
        for t in comparison['difference_server_times']:
            start = pd.Timestamp(t)
            left,right = xm_utc(pd.DatetimeIndex([start,start+pd.Timedelta(minutes=MINUTES[tf])]))
            if pd.isna(left) or pd.isna(right) or right<=left:
                raise ValueError('Unresolved clock on partial-price hazard')
            hazards.append((left,right))
            evidence.append(dict(timeframe=tf,server_open=t,start=str(left),end=str(right),
                reason='Native parent OHLC differs from available finer prices; missing/excluded quotes can hide an exit'))
    for tf,t in info['timeframes'].items():
        intervals=[]
        for old in t['replay_intervals']:
            intervals.extend(allowed_intervals(pd.Timestamp(old['start']),pd.Timestamp(old['end']),hazards))
        t['replay_intervals']=[dict(start=str(l),end=str(r)) for l,r in intervals]
        metadata_path=Path(t['file']+'.meta.json')
        metadata=json.loads(metadata_path.read_text())
        metadata.update(replay_intervals=t['replay_intervals'],partial_price_hazard_intervals=evidence)
        write_json(metadata_path,metadata)
    common=[]
    for old in info['joint_all_timeframe_intervals']:
        common.extend(allowed_intervals(pd.Timestamp(old['start']),pd.Timestamp(old['end']),hazards))
    info['joint_all_timeframe_intervals']=[dict(start=str(l),end=str(r),days=(r-l).total_seconds()/86400) for l,r in common]
    info['longest_joint_intervals']=sorted(info['joint_all_timeframe_intervals'],key=lambda i:i['days'],reverse=True)[:10]
    info['partial_price_hazard_intervals']=evidence


def main():
    report = json.loads((ROOT/'audit.json').read_text())
    complete = json.loads((ROOT/'complete.json').read_text())
    if complete['files']!=55 or complete['audit_sha256']!=file_hash(ROOT/'audit.json'):
        raise ValueError('Dataset audit is incomplete or changed')
    write_json(ROOT/'verification.json',dict(status='checking',audit_sha256=complete['audit_sha256']))
    snapshot = Path('output/xm_inspection_20261001_final')
    if (file_hash(snapshot/'inspection.json')!=report['input_manifest_sha256'] or
            file_hash(snapshot/'quality.json')!=report['quality_sha256'] or
            file_hash(snapshot/'clock_audit.json')!=report['clock_audit_sha256']):
        raise ValueError('Source snapshot or clock/resolution certificate changed')
    inspection = json.loads((snapshot/'inspection.json').read_text())
    contracts = {}
    for canonical,symbol in report['symbols'].items():
        properties = inspection['symbols'][canonical]['properties']
        if properties['chart_mode']!=0:
            raise ValueError('Unexpected chart mode; bid OHLC is required')
        for tf,info in symbol['timeframes'].items():
            path = Path(info['file'])
            if file_hash(path)!=info['csv_sha256'] or file_hash(info['excluded_file'])!=info['excluded_sha256']:
                raise ValueError('Prepared/quarantine file changed')
            source = symbol['raw_files'][tf]
            if (file_hash(source['file'])!=source['sha256'] or
                    count_csv_rows(source['file'])!=info['raw_rows'] or
                    count_csv_rows(path)!=info['retained_rows'] or
                    count_csv_rows(info['excluded_file'])!=info['excluded_rows'] or
                    info['raw_rows']!=info['retained_rows']+info['excluded_rows']):
                raise ValueError('Raw/prepared/excluded row accounting does not balance')
            sidecar = Path(str(path)+'.meta.json')
            metadata = json.loads(sidecar.read_text())
            metadata.update(price_basis='bid',spread_units='MT5 integer points',
                point=properties['point'],digits=properties['digits'],
                property_snapshot_date_utc='2026-10-01',
                current_contract_properties={k:properties[k] for k in ('trade_contract_size','volume_min','volume_step',
                    'currency_profit','swap_mode','swap_long','swap_short','swap_rollover3days')},
                note='Current contract properties are not a historical fee schedule. Zero spread fields are unknown costs.',
                finalizer_sha256=file_hash(__file__))
            write_json(sidecar,metadata)
            contracts[path.name] = dict(csv_sha256=info['csv_sha256'],metadata_sha256=file_hash(sidecar))
    write_json(ROOT/'history'/'xm_dataset.json',dict(provider='XM',processing_schema_version=1,
        audit_sha256=complete['audit_sha256'],files=contracts))
    rows,partial_reports,long_gaps,clock_summaries,joint_rows = [],{},{},[],[]
    for symbol,info in report['symbols'].items():
        m5 = info['timeframes']['M5']
        low = pd.read_csv(m5['file'],parse_dates=['time']).set_index('time')
        if len(low)!=m5['retained_rows'] or low.index.has_duplicates or not low.index.is_monotonic_increasing:
            raise ValueError('Prepared M5 count or timestamps changed')
        partial_reports[symbol] = {}
        long_gaps[symbol] = {}
        point = inspection['symbols'][symbol]['properties']['point']
        for tf,t in info['timeframes'].items():
            path = Path(t['file'])
            if tf!='M5':
                native = pd.read_csv(info['raw_files'][tf]['file'],parse_dates=['time']).set_index('time')
                partial_reports[symbol][tf] = partial_comparison(low,native,tf,point)
            gaps = pd.read_csv(ROOT/symbol/f'{symbol}_{tf}_prepared_gaps.csv')
            large = gaps.loc[gaps.requires_replay_boundary] if len(gaps) else gaps
            long_gaps[symbol][tf] = large.to_dict('records')
            rows.append(dict(symbol=symbol,timeframe=tf,raw_rows=t['raw_rows'],retained_rows=t['retained_rows'],
                excluded_rows=t['excluded_rows'],raw_first_server=t['raw_first'],raw_last_server=t['raw_last'],
                first_utc=t['first_utc'],end_utc_exclusive=t['end_utc_exclusive'],
                intervals=len(t['replay_intervals']),unexplained_long_gaps=len(large),
                zero_volume_retained=int((low.volume==0).sum()) if tf=='M5' else None,
                zero_spread_retained=int((low.spread==0).sum()) if tf=='M5' else None))
        restrict_price_hazards(info,partial_reports[symbol])
        write_json(ROOT/symbol/'audit.json',info)
        for row in rows[-5:]:
            row['intervals']=len(info['timeframes'][row['timeframe']]['replay_intervals'])
        valid = [w for w in info['clock_windows'] if w['verified']]
        clock_summaries.append(dict(symbol=symbol,verified_windows=len(valid),
            lowest_correlation=min(w['scores'][str(w['observed_offset'])]['correlation'] for w in valid),
            rule='European DST, UTC+2 winter / UTC+3 summer'))
        joint_rows.extend(dict(symbol=symbol,**i) for i in info['joint_all_timeframe_intervals'])
        print('[VERIFIED]',symbol,flush=True)
    write_json(ROOT/'partial_session_consistency.json',partial_reports)
    report['partial_price_hazards_policy']='Block the entire parent period on all required streams when native OHLC differs from available finer prices'
    report['partial_consistency_sha256']=file_hash(ROOT/'partial_session_consistency.json')
    report['finalizer_sha256']=file_hash(__file__)
    write_json(ROOT/'audit.json',report)
    complete['audit_sha256']=file_hash(ROOT/'audit.json')
    write_json(ROOT/'complete.json',complete)
    # Finalize metadata contracts after every additional price-hazard boundary.
    contracts={}
    for symbol in report['symbols'].values():
        for t in symbol['timeframes'].values():
            path=Path(t['file'])
            contracts[path.name]=dict(csv_sha256=t['csv_sha256'],metadata_sha256=file_hash(str(path)+'.meta.json'))
    write_json(ROOT/'history'/'xm_dataset.json',dict(provider='XM',processing_schema_version=1,
        audit_sha256=complete['audit_sha256'],files=contracts))
    for symbol in report['symbols'].values():
        for t in symbol['timeframes'].values():
            segment=max(t['replay_intervals'],key=lambda i:pd.Timestamp(i['end'])-pd.Timestamp(i['start']))
            times=pd.read_csv(t['file'],usecols=['time'],parse_dates=['time']).time
            candidates=times.loc[(times>=pd.Timestamp(segment['start']))&(times<pd.Timestamp(segment['end']))]
            if candidates.empty:
                raise ValueError(f'No actual candle inside final interval: {t["file"]}')
            left=candidates.iloc[0]
            right=min(pd.Timestamp(segment['end']),left+pd.Timedelta(days=2))
            events=load_csv(t['file'],start=left.to_pydatetime(),end=right.to_pydatetime())
            if not events:
                raise ValueError('Loader returned no bars in final audited interval')
    pd.DataFrame(rows).to_csv(ROOT/'coverage_summary.csv',index=False)
    pd.DataFrame(joint_rows).to_csv(ROOT/'joint_replay_intervals.csv',index=False)
    pd.DataFrame(clock_summaries).to_csv(ROOT/'clock_summary.csv',index=False)
    write_json(ROOT/'unexplained_long_gaps.json',long_gaps)
    frame = pd.DataFrame(rows)
    totals = report['totals']
    comparisons = sum(t.get('aggregation',{}).get('complete_bars_compared',0) for v in report['symbols'].values() for t in v['timeframes'].values())
    mismatches = sum(t.get('aggregation',{}).get('ohlc_mismatches',0) for v in report['symbols'].values() for t in v['timeframes'].values())
    lines = ['# XM historical data audit, 1 October 2026','',
        'Research data only. The IC Markets DEMO strategy suite and risk are unchanged. No MT5 trading calls or strategy performance tests were made.',
        '',f'Audited all 55 source files containing {totals["raw_rows"]:,} records across eleven instruments and M5/M15/H1/H4/D1. Prepared {totals["retained_rows"]:,} UTC records and retained {totals["excluded_rows"]:,} excluded records separately with their original server timestamps and exclusion flags. Counts include overlapping timeframes, so they are not counts of independent observations.',
        '', 'Prepared candles are in `output/xm_processed_20261001/history/`. Raw downloads remain unchanged in `output/xm_inspection_20261001_final/history/`. The dataset ends conservatively at July 14, 2026, 21:00 UTC for most streams. No later prices were admitted to parameter research.',
        '', '## Timing','',
        'For the accepted recent windows, XM uses UTC+2 in winter and UTC+3 in summer, following European daylight-saving dates. Each instrument was checked against native UTC Dukascopy prices by month and separately during European/US DST disagreement periods. The weakest accepted monthly return correlation was '+f'{min(x["lowest_correlation"] for x in clock_summaries):.3f}'+'. This establishes alignment in measured windows, not independent price-feed provenance or a tick-by-tick timing guarantee.',
        '', 'A recent March 16, 2026 server timestamp of 00:00 converts to March 15 at 22:00 UTC. March 30 at 00:00 converts to March 29 at 21:00 UTC. The US changes clocks earlier in March, so the IC Markets US-DST conversion must not be reused for XM.',
        '', 'The older archive needs different treatment. Fresh official HTTPS Dukascopy chart responses cover an EURUSD reference sample from January 2012 through January 2014. Most verified older windows fit UTC+1 winter and UTC+2 summer, one hour different from the recent XM rule. June 2013 is mixed even within the same month. Daily comparisons identify UTC+3 on June 6, 7, 10, 11, 12, 13, 27, and 28; other tested weekdays align at UTC+2. Those daily correlations are about 0.925 to 0.997. The full older changeover and other instruments have not been established. All pre-2016 candles remain quarantined, including portions of 2012/2013 with useful individual clock evidence.',
        '', 'An additional event check supports the older June 19 offset. The Federal Reserve scheduled its June 19, 2013 statement for 14:00 Eastern, which is 18:00 UTC that day. The largest EURUSD five-minute range appears at 18:00 in the UTC reference and 20:00 in XM. This is corroboration, not a reason to approve every older timestamp. [Federal Reserve meeting page](https://www.federalreserve.gov/monetarypolicy/A4110FBE934A4A278474425B2BA9A0D8.htm).',
        '', 'The request for an older public candle-file endpoint timed out. The chart service response to a 2008 start request actually began in January 2012. These limitations are recorded; neither establishes that the 2008 XM prices are wrong or that older Dukascopy history does not exist.',
        '', '## Prepared coverage','',
        'These bounds describe the retained files. They do not promise one uninterrupted usable backtest. Each file has allowed replay intervals in its sidecar.',
        '', '| Instrument | First retained M5, UTC | Retained M5 rows | Excluded M5 rows | M5 unexplained long gaps |',
        '|---|---|---:|---:|---:|']
    for s,v in report['symbols'].items():
        t=v['timeframes']['M5']
        count=int(frame.loc[(frame.symbol==s)&(frame.timeframe=='M5'),'unexplained_long_gaps'].iloc[0])
        lines.append(f'| {s} | {t["first_utc"]} | {t["retained_rows"]:,} | {t["excluded_rows"]:,} | {count} |')
    lines.extend(['','## Resolution and mislabeled records','',
        'Older lower-timeframe requests contain daily and hourly substitutes. A proxy candle can expose its parent’s later high, low, and close at the start of a five-minute interval. That would cause look-ahead in a replay. The processor excludes the prefix before regular detailed history, flagged coarse months, and unproven nonflat candles that exactly match a higher candle in OHLC and tick volume. For M15/H1/H4, verified finer M5 candles can demonstrate that the values belong entirely to the requested period. This preserves genuine short sessions, such as a final Friday M15 candle that also equals the shortened H1 candle. Remaining individual equality flags are conservative candidates and stay quarantined.',
        '', 'The month exclusion is deliberately conservative. For GBPUSD, USDJPY, and USDCHF, May through September 2018 are excluded from M5/M15, including some genuine candles near the edges. USDCAD excludes August and September 2018. AUDUSD/NZDUSD/EURAUD/GBPCAD detailed M5 begins late September 2018, but the flagged September boundary month is excluded, so the prepared files start with the following session. USTEC starts with the first session after its flagged October 2016 boundary month. The raw/excluded files preserve these edge days for later review.',
        '',f'Across all instruments, {comparisons:,} complete M5 groups were compared with native higher-timeframe candles. OHLC differences: {mismatches}. Higher candles retain XM server-session boundaries; they were not rebuilt around UTC midnight. Partial sessions are checked separately in `partial_session_consistency.json`. Of '+f'{sum(t["partial_bars_compared"] for s in partial_reports.values() for t in s.values()):,}'+ ' partial groups, '+f'{sum(t["ohlc_differences"] for s in partial_reports.values() for t in s.values()):,}'+ ' differ in OHLC. A difference on a partial finer grid can reflect missing/excluded quotes; it is not automatically a bad native parent candle. The entire affected parent period is blocked on all timeframe streams, because finer prices may otherwise miss a stop or target. Those extra boundaries are recorded in `partial_price_hazard_intervals` in the audit and sidecars.',
        '', '## Gaps and trading sessions','',
        'Every nominal-grid hole is listed per instrument/timeframe. Reports distinguish likely weekends, holiday closures, recurrent overnight breaks, short quote gaps, rollover candidates, and unexplained long gaps. For US index holidays beyond Christmas/New Year, the classifier also requires a fully covered UTC reference window with no M5 records. A rare overnight index pattern needs at least five occurrences and reference absence, while common recurring patterns need twenty occurrences. These labels are evidence-based candidates rather than a complete historical exchange calendar. A reference candle within a hole shows activity on another feed; it does not prove XM was open or lost a tick.',
        '', 'US-equity holiday names and early closes provide calendar context. They are not a verified historical XM CFD session schedule. [NYSE holiday and trading-hours calendar](https://www.nyse.com/trade/hours-calendars).',
        '', 'Nasdaq cash has regular overnight pauses and holiday short sessions. Treating the nominal 24-hour grid as uninterrupted trading would overstate missing data. FX has occasional missing five-minute records and thin rollover periods. Small gaps remain explicit; no interpolation or fabricated bid/ask prices were added.',
        '', 'Long unexplained gaps require independent replay segments. Native D1/H4 candles spanning European clock changes can have a UTC duration different from their nominal 24/four hours. The current engine assumes fixed durations, so these particular parent candles are quarantined and create additional boundaries. Otherwise native short Sunday sessions are preserved, including genuine broker weekday candles whose UTC timestamp falls on Sunday.',
        '', '| Instrument | All-timeframe shared intervals | Longest shared interval, UTC | Length, days |',
        '|---|---:|---|---:|'])
    for s,v in report['symbols'].items():
        longest=v['longest_joint_intervals'][0]
        lines.append(f'| {s} | {len(v["joint_all_timeframe_intervals"])} | {longest["start"]} to {longest["end"]} | {longest["days"]:.1f} |')
    lines.extend(['','These are conservative intervals shared by all five timeframes for each instrument. A strategy using fewer timeframes can use the intersection of just those files’ allowed intervals. A portfolio also needs the intersection across its instruments. Warmup must fit within the selected interval. Start each independent segment with fresh strategy/portfolio state and report any exposure still open at its end. Do not stitch segments into one uninterrupted account curve or carry exposure across their gaps.',
        '', '## Volume, spreads, and other limitations','',
        'The volume column is MT5 tick volume, not exchange traded volume. Many older candles have zero recorded volume despite moving prices. The retained files still contain some zero volume records before 2019. Keep those prices for OHLC research, but do not assume those zero values represent a verified absence of activity or use them to validate a volume filter.',
        '', 'Many historical spread values are zero. They are treated as unavailable cost evidence. Nonzero MT5 spread fields are integer symbol points, not automatically FX pips or Nasdaq points, and do not establish bid/ask movement throughout the candle. These are bid OHLC files. Commission, spread, slippage, minimum volume, and overnight financing still need explicit broker-specific simulation assumptions.',
        '', '## Outputs and validation','',
        '- `coverage_summary.csv` lists all 55 prepared files, retained/excluded counts, and bounds.',
        '- `joint_replay_intervals.csv` lists the shared interval boundaries for each instrument.',
        '- Per-instrument `*_raw_gaps.csv` and `*_prepared_gaps.csv` list every hole and reference activity.',
        '- Per-instrument `*_excluded_server_clock.csv` preserves rejected source rows and all applicable reason flags.',
        '- `audit.json`, `complete.json`, sidecars, and `history/xm_dataset.json` bind outputs and replay metadata to source hashes.',
        '- `earlier_clock_diagnostic.json` and `earlier_daily_clock_audit.json` retain the older clock findings.',
        '', 'The loader checks prepared CSV hashes and completed dataset sidecar hashes, blocks a second clock conversion, rejects bounds outside verified coverage, and refuses a replay that crosses an excluded interval or unexplained long gap. A missing sidecar in the XM prepared folder also fails. All 55 file hashes matched, row accounting balanced, and the actual loader accepted a bounded sample from every prepared file. No strategy trades were simulated.',
        '', 'The preparation tests cover copied parent candles, genuine short sessions proven by M5, flat sparse candles, interval boundaries, weekends/holidays versus intraday gaps, complete versus partial aggregation, mixed offsets within a month, European/US clock differences, DST duration, changed files/sidecars, missing metadata, and out-of-coverage dates. The full unit suite passes. Detailed test output is in `output/xm_preparation_tests_20261001.txt`.',
        '', 'Reproduce offline preparation with `python prepare_xm_history.py`, then `python audit_xm_early_clocks.py`, then `python summarize_xm_preparation.py`. The optional `fetch_xm_clock_references.py --cached-only` rebuilds the already-downloaded older reference without network access. Its network mode is sequential and request-bounded; it does not guarantee the requested early dates are available.',
        '', 'XM remains useful for research, but the apparent 2008 coverage is not yet approved UTC history. The next data step is to reconstruct older per-instrument clock regimes from independent UTC anchors, then review the coarse-month edge days. For strategy testing now, use the verified recent intervals and frozen parameters with measured costs. No DEMO deployment, parameter choice, real-money trading, commit, or push occurred.'])
    REPORT.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    write_json(ROOT/'verification.json',dict(status='complete',files_checked=len(rows),loader_samples_passed=len(rows),
        row_accounting_balanced=all(t['raw_rows']==t['retained_rows']+t['excluded_rows'] for v in report['symbols'].values() for t in v['timeframes'].values()),
        hashes_match=True, audit_sha256=complete['audit_sha256'],dataset_manifest_sha256=file_hash(ROOT/'history'/'xm_dataset.json'),
        report_sha256=file_hash(REPORT),verifier_sha256=file_hash(__file__)))
    print('Report:',REPORT,flush=True)


if __name__ == '__main__':
    main()
