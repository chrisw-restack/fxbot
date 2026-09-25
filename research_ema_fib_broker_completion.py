"""Extend the corrected EmaFib study without treating truncated history as complete."""
from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path

import pandas as pd

from data.historical_loader import load_and_merge
from data.histdata_provenance import file_hash, write_json
from research_ema_fib_review import current_settings, paths_for, metrics, PERIODS
import research_ema_fib_tracking as study
from summarize_ema_fib_tracking import table


ROOT = Path(__file__).resolve().parent
PREVIOUS = ROOT/'output/ema_fib_tracking_20260925'
OUT = ROOT/'output/ema_fib_broker_completion_20260925'
SOURCES = ('dukascopy', 'histdata', 'mt5_icmarkets_utc')


def read(path):
    return json.loads(path.read_text())


def main():
    logging.disable(logging.CRITICAL)
    OUT.mkdir(parents=True, exist_ok=True)
    study.OUT = OUT
    params, symbols = current_settings()
    previous = read(PREVIOUS/'manifest.json')
    final = read(PREVIOUS/'recovery_hardening_verification.json')
    # Reused results must still match their strategy, execution, settings, and inputs.
    assert all(file_hash(ROOT/p) == sha for p,sha in final['final_code_hashes'].items())
    assert params == previous['parameters']
    assert all(file_hash(Path(p)) == sha for p,sha in previous['input_hashes'].items())
    files = {s:paths_for('mt5_icmarkets_utc',s) for s in symbols}
    coverage = []
    for symbol, paths in files.items():
        for path in paths:
            times = pd.read_csv(path, usecols=['time'])['time']
            coverage.append(dict(symbol=symbol,timeframe=Path(path).name.split('_')[1],path=path,
                                 rows=len(times),first=times.min(),last=times.max(),sha256=file_hash(path)))
    write_json(OUT/'coverage.json',coverage)
    results = []
    for symbol in ('NZDUSD','USDCHF','USDCAD'):
        for source in (SOURCES if symbol == 'USDCAD' else ('mt5_icmarkets_utc',)):
            paths = paths_for(source,symbol)
            start = datetime(2025,1,1) if symbol == 'USDCAD' else datetime(2019,7,1)
            bars = load_and_merge(paths,start=start,end=study.CUTOFF)
            periods = ([('2025_h2',datetime(2025,7,1),datetime(2026,1,1)),PERIODS[1]]
                       if symbol == 'USDCAD' else PERIODS)
            for label,a,b in periods:
                # Require pre-period history in all streams, allowing a weekend/holiday.
                for tf in ('M5','H1','D1'):
                    first = min(e.timestamp for e in bars if e.timeframe == tf)
                    assert first <= a-timedelta(days=173), (source,symbol,tf,first,a)
                r,_ = study.run(bars,source,symbol,label,a,b,params)
                results.append(r)
            del bars
    write_json(OUT/'results.json',results)

    def get_trades(source,symbol,label):
        name = f'{source}_{symbol}_{label}_trades.json'
        path = OUT/name if (OUT/name).exists() else PREVIOUS/name
        return read(path)

    six = [s for s in symbols if s != 'USDCAD']
    groups = []
    for label,members in [('2020_2025',six),('2026_to_july14',symbols)]:
        for source in SOURCES:
            ts = sum([get_trades(source,s,label) for s in members],[])
            groups.append(dict(source=source,label=label,symbols=members,metrics=metrics(ts)))
    write_json(OUT/'aggregate.json',groups)
    code_hashes = {p:file_hash(ROOT/p) for p in final['final_code_hashes']}
    assert code_hashes == final['final_code_hashes']
    write_json(OUT/'manifest.json',dict(created_utc=datetime.now(timezone.utc),workers=1,parameters=params,
        code_hashes=code_hashes,script_sha256=file_hash(Path(__file__)),
        previous_manifest_sha256=file_hash(PREVIOUS/'manifest.json'),
        previous_recovery_sha256=file_hash(PREVIOUS/'recovery_hardening_verification.json'),
        input_hashes={p:file_hash(Path(p)) for s in symbols for src in SOURCES for p in paths_for(src,s)},
        reused_result_hashes={p.name:file_hash(p) for p in PREVIOUS.glob('*_trades.json')},
        completed_runs=len(results),assumptions=previous['assumptions']))
    sections = ['# EmaFib broker-history extension, 25 September 2026',
        'NZDUSD and USDCHF M5 exports are now available from January 2016. USDCAD M5, H1, and D1 all begin on 1 January 2025 at 22:00 UTC. A successful export means rows were saved; it does not establish coverage of the requested date range. The earlier assumption that existing USDCAD H1/D1 files supplied the full period was incorrect.',
        '## Method',
        'The corrected implementation, numeric settings, spread, and commission are unchanged. Ten additional replays run sequentially. Previous compatible results are reused only after checking code, parameter, and input hashes. New orders and ending exposure pass the same strategy/execution consistency checks. Each replay uses 180 days of warm-up, with no trades after 14 July 2026. This is descriptive historical validation, not a new optimization or untouched holdout.',
        'The tables sum independent pair net-R histories in close-time order. They are not pooled account returns or equity drawdowns. They include modeled spread and commission but omit swap, variable spreads, extra slippage, and shared DEMO portfolio/daily-loss gates. Broker D1 session boundaries differ from UTC-day data. HistData and Dukascopy remain highly similar price series, not independent feed confirmation.',
        '## Six matched pairs, 2020 through 2025',
        'Pairs: '+', '.join(six)+'. USDCAD is excluded from every source in this table because its broker history does not cover these years.',
        table([(g['source'],g['metrics']) for g in groups if g['label']=='2020_2025']),
        '## Seven matched pairs, 1 January through 14 July 2026',
        table([(g['source'],g['metrics']) for g in groups if g['label']=='2026_to_july14']),
        'The new M5 exports end at 21:00 UTC on 14 July, as shown by the exporter. The requested end date does not imply complete coverage through UTC midnight. Closed-trade metrics exclude any ending open or pending exposure.',
        '## Added long-history broker pairs',
        table([(r['symbol'],r['metrics']) for r in results if r['label']=='2020_2025']),
        '## USDCAD only, 1 July through 31 December 2025',
        'Starting in July permits a full 180-day warm-up in all three broker streams. Starting in January 2025 would not. All three sources start fresh on the same July date.',
        table([(r['source'],r['metrics']) for r in results if r['symbol']=='USDCAD' and r['label']=='2025_h2']),
        '## USDCAD only, 2026 through 14 July',
        table([(r['source'],r['metrics']) for r in results if r['symbol']=='USDCAD' and r['label']=='2026_to_july14']),
        '## Accepted coverage limit',
        'The repeated host export returned the same earliest timestamp, 1 January 2025 at 22:00 UTC, for all three USDCAD timeframes. It saved 114,263 M5 bars, 9,527 H1 bars, and 398 D1 bars through 14 July 2026. Treat this as the available history limit for the current broker/terminal setup. This does not prove that every IC Markets server has the same limit. No further download is requested.',
        'The completed scope is six matched pairs over 2020 through 2025 and seven pairs over the recent period. USDCAD is excluded from every source in the long-history comparison. Its shorter tests use adequate warm-up and yielded no closed trades on any source, so they do not establish an edge. A seven-pair long-history broker result is unavailable; this limitation does not prevent using the completed comparisons. No DEMO configuration or risk change was made.',
        '## Artifacts',
        'Run `.venv\\Scripts\\python.exe research_ema_fib_broker_completion.py` to reproduce this extension. Input coverage, hashes, trades, metrics, and period-end exposure are in `output/ema_fib_broker_completion_20260925/`. The original 134-run study and its outputs remain unchanged.']
    exposure = [f"- {r['source']} {r['symbol']} {r['label']}: {len(r['open_exposure'])}" for r in results if r['open_exposure']]
    sections.extend(['## Ending exposure', '\n'.join(exposure) if exposure else 'All ten additional runs ended flat.'])
    (ROOT/'strategy_log/ema_fib_broker_completion_20260925.md').write_text('\n\n'.join(sections)+'\n',encoding='utf-8')
    print(json.dumps(groups),flush=True)


if __name__ == '__main__':
    main()
