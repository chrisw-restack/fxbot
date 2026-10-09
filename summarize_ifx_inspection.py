"""Write the IFX coverage comparison from saved, hash-checked audit results."""
import json
import csv
from pathlib import Path

from data.histdata_provenance import file_hash

ROOT=Path('output/ifx_inspection_20261008')


def day(value):
    return str(value)[:10] if value else 'None'


def main():
    manifest=json.loads((ROOT/'inspection.json').read_text())
    complete=json.loads((ROOT/'complete.json').read_text())
    quality=json.loads((ROOT/'quality.json').read_text())
    clocks=json.loads((ROOT/'clock_audit.json').read_text())
    comparison=json.loads((ROOT/'comparison.json').read_text())['symbols']
    if quality['input_manifest_sha256'] != file_hash(ROOT/'inspection.json'):
        raise RuntimeError('Audit and collection manifest differ')
    if complete['files']!=55 or not complete['hashes_match'] or any(file_hash(r['file'])!=r['sha256'] for r in manifest['history']):
        raise RuntimeError('Incomplete or changed download')
    from live_config import live_symbols
    active=set(live_symbols())
    lines=['# IFX chart history comparison, 8 October 2026','',
        'IFX did not provide a longer uninterrupted intraday archive than our other broker downloads. '
        'Its earlier dates include higher-timeframe substitutes. Raw exports remain research files, '
        'and must not be replayed before bounded clock conversion and gap review.','',
        f"Downloaded {complete['files']} CSV files containing {complete['rows']:,} rows across M5, M15, H1, H4, and D1. "
        'The eleven symbols include all nine symbols in the current DEMO suite, plus NZDUSD and USDCHF '
        'for comparison with prior broker collections. Requests span 1970-01-01 through '
        '2026-10-08 in the unreviewed server clock, retaining completed candles through 7 October. '
        'All file hashes match the collection manifest.','',
        'Attached explicitly to `C:\\Program Files\\IFX Brokers MetaTrader 5\\terminal64.exe`, '
        f"account {manifest['account']['login']} on `{manifest['account']['server']}`. MT5 trade_mode=0 identifies "
        'a demo account despite the Real server name. Active FX instruments use `.ifx`; '
        'Nasdaq cash is `T100.ifx_m`, mapped to USTEC. The unsuffixed major FX symbols are disabled '
        'and were not used for the final collection.','',
        'No credentials, account login changes, order submission, cancellation, bot parameters, '
        'risk settings, or DEMO deployment changes were made. The post-14-July-2026 forward '
        'holdout was downloaded for storage and coverage inspection only. The price-based clock '
        'audit excludes it. No strategy replay or optimization was run.','',
        '## Coverage comparison','',
        '| Instrument | Current DEMO | IFX first returned | IFX dense M5 | IC Markets stored M5 first | Exness dense M5 | XM dense M5 |',
        '|---|---|---|---|---|---|---|']
    for symbol,c in comparison.items():
        m=c['ifx']
        lines.append(f"| {symbol} | {'Yes' if symbol in active else 'No'} | {day(m['reported_first'])} | {day(m.get('first_dense_weekday_window'))} | {day(c['icmarkets_stored_m5_first'])} | {day(c['exness_m5_dense_first'])} | {day(c['xm_m5_dense_first'])} |")
    lines += ['',
        'IFX/XM dates in this table are raw server-clock dates. Exness dates are UTC, and IC Markets '
        'dates are from the stored UTC exports. IC Markets was not freshly queried on this device. '
        'These are observations for the tested accounts and servers, not universal broker limits. '
        'XM dense first dates can precede holes inside its archive, including several 2018 intervals. '
        'XM historical clock coverage is also bounded. See the prior '
        '[Exness report](exness_inspection_20261001.md), '
        '[XM report](xm_inspection_20261001.md), and [XM preparation audit](xm_data_audit_20261001.md).','',
        'A dense start requires five consecutive observed weekdays with at least 150 M5, 50 M15, '
        '16 H1, or four H4 candles per day. OHLC and tick-volume equality with higher timeframes '
        'flags substitutes. These diagnostics do not certify that all later timestamps have '
        'native resolution or that every missing candle is a data defect.','',
        '## IFX detail','',
        '| Instrument | M5 rows | Dense M5/M15 first | Dense H1 first | Dense H4 first | First D1 | Long intraday M5 gaps after dense start |',
        '|---|---:|---|---|---|---|---:|']
    for symbol,frames in quality['symbols'].items():
        m=frames['M5']
        lines.append(f"| {symbol} | {m['rows']:,} | {day(m.get('first_dense_weekday_window'))} / {day(frames['M15'].get('first_dense_weekday_window'))} | {day(frames['H1'].get('first_dense_weekday_window'))} | {day(frames['H4'].get('first_dense_weekday_window'))} | {day(frames['D1']['reported_first'])} | {m['dense_history_gaps']['same_day_weekday_gaps_at_least_60_minutes']} |")
    lines += ['', 'The full quality audit records coarse months, monthly counts, short sessions, '
        'and gap candidates for every required timeframe. Long intraday gaps here mean '
        'at least 60 elapsed minutes between observations within the same weekday server date. '
        'The index has regular trading pauses, so its count needs its own session calendar.','']
    for symbol,frames in quality['symbols'].items():
        g=frames['M5']['dense_history_gaps']
        examples='; '.join(f"{r['previous']} to {r['next']}, {r['missing_grid_slots']} missing five-minute slots" for r in g['largest_same_day_weekday_gaps'][:4])
        lines.append(f"- {symbol}: {g['same_day_weekday_gap_events']} same-day weekday gaps. Largest candidates: {examples or 'none'}. Full empty weekday candidates excluding 1 January/25 December: {', '.join(g['full_empty_weekdays']) or 'none'}.")
    lines += ['', 'Christmas/New Year and weekend closures are recorded separately. Boxing Day can also '
        'explain a full missing session. A shared midday FX hole needs investigation even when '
        'annual bar counts look normal. No gap was filled from another broker.','',
        '## Clock evidence','',
        'Compared raw M5 returns with hash-bound native UTC Dukascopy references, using offsets '
        '0, 1, 2, and 3 hours. Windows split around European and US DST disagreement periods. '
        'Verification requires at least 50 consecutive matched returns, rank correlation at '
        'least 0.8, and a margin of at least 0.3 over the next offset. Coarse/short windows fail '
        'these thresholds and do not establish clock coverage.','',
        '| Instrument | Verified clock windows | Candidate rules by year |',
        '|---|---:|---|']
    for symbol,c in clocks['symbols'].items():
        yearly='; '.join(f"{year}: {','.join(rules) or 'none'}" for year,rules in c['compatible_rules_by_year'].items())
        lines.append(f"| {symbol} | {sum(w['verified'] for w in c['windows'])} | {yearly} |")
    lines += ['', 'A single timeless broker offset is not approved by this audit. Per-year compatible '
        'rules are evidence from observed windows, not permission to extrapolate beyond them. '
        'UTC conversion must retain those boundaries and native parent-session consistency. '
        'Raw sidecars declare `ifx_server_unreviewed` and `raw_unreviewed`; the existing loader '
        'rejects them even if UTC is explicitly requested.','',
        '## Maximum-history checks and files','',
        f"The connected terminal reports a {manifest['maxbars']:,}-bar chart limit. No final request reached it. "
        'The first cache-limited EURUSD probe returned only June 2025 onward; after the terminal '
        'reconnected/restarted, the broad request returned the longer archive recorded above. '
        'Do not use that preliminary probe as the broker limit. '
        'MetaTrader documents that chart limits constrain Python history requests in its '
        '[copy_rates_range reference](https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesrange_py).','',
        'Saved files are under `output/ifx_inspection_20261008/history/`. The snapshot also contains '
        '`inspection.json`, `complete.json`, `quality.json`, `clock_audit.json`, and `comparison.json`. '
        'The collector and audit are `inspect_ifx_mt5.py` and `audit_ifx_history.py`; '
        '`summarize_ifx_inspection.py` rebuilds this report. Focused collection, identity, cutoff, '
        'gap, and loader-rejection checks are in `tests/test_ifx_collection.py`.','',
        'For a future walk-forward run, use IFX only as an additional recent broker feed after '
        'UTC preparation and splitting at unexplained gaps. It does not solve the request for '
        'a longer gap-free archive. Do not enlarge the selection period into the protected '
        'forward holdout or stitch prices from different brokers.','']
    probe_path=ROOT/'archive_probes.json'
    if probe_path.exists():
        probes=json.loads(probe_path.read_text())
        old=[r for r in probes['checks'] if r['purpose']=='before_archive']
        coarse=[r for r in probes['checks'] if r['purpose']=='coarse_prefix']
        holes=[r for r in probes['checks'] if r['purpose']=='intraday_hole']
        lines += ['## Direct archive probes','',
            f"Re-requested 4-9 January 2010 for {len(old)} instruments. {sum(r.get('rows',0)==0 for r in old)} returned no retained rows inside the tested window. "
            'This confirms no data was obtained for those tested old dates. API errors are retained '
            'in `archive_probes.json`. Broad requests beginning 1970 also returned only the archive '
            'dates in the tables above.','',
            'The 6-11 January 2020 M5 requests returned these completed row counts: '
            + ', '.join(f"{r['symbol']} {r.get('rows',0)}" for r in coarse)+'. '
            'A five-day FX window should have hundreds of bars per day at five-minute resolution. '
            'These probes support the coarse-prefix finding.','',
            '| Instrument | Date | Timeframe | Completed rows | Gaps of at least 60 minutes |',
            '|---|---|---|---:|---|']
        for r in holes:
            text='; '.join(f"{x['previous'][11:]} to {x['next'][11:]}, {x['elapsed_minutes']:g} minutes" for x in r.get('gaps_at_least_60_minutes',[])) or 'None returned'
            lines.append(f"| {r['symbol']} | {r['start']} | {r['timeframe']} | {r.get('rows',0)} | {text} |")
        lines += ['', 'These direct M1/M5 requests test whether the same broker can supply the '
            'missing observations. The small M1 samples are diagnostic files, not a full M1 archive. '
            'Probe CSVs and raw sidecars are under `probes/`, with recorded hashes.','']
    path=Path('strategy_log/ifx_inspection_20261008.md')
    path.write_text('\n'.join(lines),encoding='utf-8')
    with (ROOT/'coverage_comparison.csv').open('w',newline='',encoding='utf-8') as output:
        fields=['symbol','current_demo','ifx_first_returned','ifx_dense_m5','ifx_dense_m15',
            'ifx_dense_h1','ifx_dense_h4','ifx_m5_bars','ifx_long_intraday_m5_gaps',
            'icmarkets_stored_m5_first','exness_dense_m5','xm_dense_m5']
        writer=csv.DictWriter(output,fieldnames=fields)
        writer.writeheader()
        for symbol,c in comparison.items():
            frames=quality['symbols'][symbol]
            writer.writerow(dict(symbol=symbol,current_demo=symbol in active,
                ifx_first_returned=frames['M5']['reported_first'],
                ifx_dense_m5=frames['M5'].get('first_dense_weekday_window'),
                ifx_dense_m15=frames['M15'].get('first_dense_weekday_window'),
                ifx_dense_h1=frames['H1'].get('first_dense_weekday_window'),
                ifx_dense_h4=frames['H4'].get('first_dense_weekday_window'),
                ifx_m5_bars=frames['M5']['rows'],
                ifx_long_intraday_m5_gaps=frames['M5']['dense_history_gaps']['same_day_weekday_gaps_at_least_60_minutes'],
                icmarkets_stored_m5_first=c['icmarkets_stored_m5_first'],
                exness_dense_m5=c['exness_m5_dense_first'],xm_dense_m5=c['xm_m5_dense_first']))
    print(path.resolve())


if __name__=='__main__':
    main()
