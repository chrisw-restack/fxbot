"""Sequential before/after validation of Failed2 fixes; no MT5 connection."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import time

import config
from analyze_icmarkets_replay import MemoryJournal
from backtest_engine import BacktestEngine
from data.historical_loader import load_and_merge, bar_close_time
from data.histdata_provenance import file_hash, write_json
from research_failed2_baseline import BaselineFailed2, SOURCE, REVISION
from research_failed2_review import ROOT, OUT as BASE, SOURCES, FOLDS, settings, paths_for
from research_ema_fib_review import metrics, PERIODS
from strategies.failed2 import Failed2Strategy

OUT = ROOT / 'output/failed2_corrections_20260928'


def replay(bars, symbol, params, start, end, variant='corrected', spread=1):
    daily = [b for b in bars if b.timeframe == 'D1' and bar_close_time(b) <= start][-250:]
    selected = [b for b in bars if bar_close_time(b) <= end and (
        bar_close_time(b) > start or (b.timestamp >= start-timedelta(days=180) and
                                    (variant != 'corrected' or b.timeframe != 'D1')))]
    if variant == 'corrected':
        selected.extend(daily)
        rank = {'M5':0, 'H1':1, 'H4':2, 'D1':3}
        selected.sort(key=lambda b: (bar_close_time(b), rank[b.timeframe], b.symbol))
    cls = BaselineFailed2 if variant == 'baseline' else Failed2Strategy
    params = deepcopy(params)
    params['pip_sizes'][symbol] = config.PIP_SIZE[symbol]
    s = cls(**params)
    e = BacktestEngine(spread_pips=spread)
    e.add_strategy(s, [symbol])
    journal = MemoryJournal()
    e.event_engine.trade_journal = journal
    e.execution.configure_timeframes(selected)
    for bar in selected:
        if bar_close_time(bar) <= start:
            e.event_engine.warmup_bar(bar)
        else:
            e.process_bar(bar)
    trades = e.execution.get_closed_trades()
    return dict(metrics=metrics(trades), open_exposure=e.execution.get_open_positions(),
        warmup_bars=dict(Counter(b.timeframe for b in selected if bar_close_time(b) <= start)),
        ending_balance=e.execution.get_account_balance(),
        rejections=dict(Counter(r['reason'] for r in journal.rows if r['event']=='REJECTED'))), trades


def main():
    logging.disable(logging.CRITICAL)
    OUT.mkdir(parents=True, exist_ok=True)
    params = settings()
    baseline_manifest = json.loads((BASE/'manifest.json').read_text())
    # Canonicalize sets/tuples just as the JSON artifact does.
    assert json.loads(json.dumps(params, default=list)) == baseline_manifest['parameters']
    paths = {source:paths_for(source) for source in SOURCES}
    input_hashes = {p:file_hash(p) for _, files in paths.values() for p in files}
    assert input_hashes == baseline_manifest['input_hashes']
    # Only strategy/membership research files may differ from the reviewed pipeline.
    for path, digest in baseline_manifest['code_hashes'].items():
        if path not in ('research_failed2_review.py', 'strategies/failed2.py'):
            assert file_hash(ROOT/path) == digest, path
    code = list(baseline_manifest['code_hashes']) + [
        'research_failed2_corrections.py','research_failed2_baseline.py',
        'main_live.py','utils/warmup.py','utils/setup_ledger.py','utils/strategy_state.py']
    manifest = dict(created_utc=datetime.now(timezone.utc), parameters=params, workers=1,
        baseline_revision=REVISION, baseline_source_sha256=hashlib.sha256(SOURCE.encode()).hexdigest(),
        code_hashes={p:file_hash(ROOT/p) for p in code}, input_hashes=input_hashes,
        metadata_hashes=baseline_manifest['metadata_hashes'],
        assumptions=dict(baseline_manifest['assumptions'], corrected_daily_warmup=250),
        note='Same numeric parameters and data cutoff. Tracking variant retains original warm-up. '
             'Corrected variant adds 250 D1 warm-up bars when history exists. First 2016 fold has no prehistory.')
    write_json(OUT/'manifest.json', manifest)
    rows, controls = [], []
    for source, (symbol, files) in paths.items():
        print('Loading '+source, flush=True)
        bars = load_and_merge(files, start=datetime(2018,7,1) if source=='mt5_icmarkets_utc' else datetime(2016,1,1), end=PERIODS[-1][2])
        jobs = [('baseline', *PERIODS[0], 1), ('tracking', *PERIODS[0], 1)]
        jobs.extend(('corrected', *period, 1) for period in PERIODS)
        for a, split, b in FOLDS:
            if source=='mt5_icmarkets_utc' and split.year!=2024:
                continue
            jobs.extend([('corrected', f'fold_{split.year}_train', a, split, 1),
                         ('corrected', f'fold_{split.year}_test', split, b, 1)])
        jobs.extend(('corrected', f'spread_{spread}', PERIODS[0][1], PERIODS[0][2], spread) for spread in (2,5))
        for variant, label, start, end, spread in jobs:
            began = time.monotonic()
            result, trades = replay(bars, symbol, params, start, end, variant, spread)
            result.update(source=source, variant=variant, label=label, start=start, end=end,
                          spread=spread, seconds=time.monotonic()-began)
            if variant=='baseline':
                saved=json.loads((BASE/f'{source}_current_{label}_trades.json').read_text())
                assert json.loads(json.dumps(trades, default=str)) == saved, source+' baseline trades changed'
                saved_result=json.loads((BASE/f'{source}_current_{label}.json').read_text())
                assert json.loads(json.dumps(result['open_exposure'], default=str)) == saved_result['open_exposure']
                controls.append(dict(source=source, all_trade_fields_match=True, ending_exposure_matches=True))
                write_json(OUT/'controls.json', controls)
            name = f'{source}_{variant}_{label}'
            write_json(OUT/(name+'_trades.json'), trades)
            write_json(OUT/(name+'.json'), result)
            rows.append(result)
            write_json(OUT/'results.json', rows)
            print(json.dumps(dict(job=name, metrics=result['metrics'], seconds=result['seconds'])), flush=True)
        del bars
    folded=[]
    index={(r['source'],r['label']):r for r in rows if r['variant']=='corrected'}
    for source in SOURCES:
        for _, split, _ in FOLDS:
            if (source,f'fold_{split.year}_train') not in index:
                continue
            train=index[source,f'fold_{split.year}_train']['metrics']
            test=index[source,f'fold_{split.year}_test']['metrics']
            retention=test['expectancy']/train['expectancy'] if train['expectancy']>0 else None
            verdict='FAIL' if test['total_r']<=0 else 'UNDEFINED' if retention is None else 'STRONG' if retention>=.7 else 'MODERATE' if retention>=.4 else 'WEAK'
            folded.append(dict(source=source,test_year=split.year,train=train,test=test,retention=retention,verdict=verdict))
    write_json(OUT/'folds.json', folded)
    assert all(file_hash(ROOT/p)==digest for p,digest in manifest['code_hashes'].items())
    write_json(OUT/'complete.json', dict(replays=len(rows), controls=len(controls), code_hashes_match=True))
    print('Failed2 correction validation complete.', flush=True)


if __name__=='__main__':
    main()
