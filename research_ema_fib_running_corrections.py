"""Sequential fixed-parameter Running corrections and historical revalidation.

No MT5 access, parameter selection, or changes to the DEMO configuration.
"""
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
from pathlib import Path
import time

import config
from backtest_engine import BacktestEngine
from data.historical_loader import load_and_merge, bar_close_time
from data.histdata_provenance import file_hash, metadata_path, write_json
from research_ema_fib_review import paths_for, metrics, PERIODS
from research_ema_fib_running_baseline import EmaFibRunningStrategy as Original, REVISION, SOURCE
from research_ema_fib_running_review import settings, SOURCES, OUT as PREVIOUS
from strategies.ema_fib_running import EmaFibRunningStrategy

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/ema_fib_running_corrections_20260925'
FOLDS=[(datetime(y,1,1),datetime(y+4,1,1),datetime(y+6,1,1)) for y in (2016,2018,2020)]


class TrackingOnlyRunning(EmaFibRunningStrategy):
    """Research control: retain the original extreme initialization only."""
    def _initial_running_extreme(self, window, direction):
        return None


CLASSES={'original':Original,'tracking':TrackingOnlyRunning,'corrected':EmaFibRunningStrategy}


def replay(bars,source,symbol,variant,label,start,end,params,spread=None):
    selected=[b for b in bars if b.timestamp >= start-timedelta(days=180) and bar_close_time(b)<=end]
    if start.year != 2016:
        for tf in ('M5','H1','D1'):
            assert min(b.timestamp for b in selected if b.timeframe==tf)<=start-timedelta(days=173)
    strategy=CLASSES[variant](**params)
    engine=BacktestEngine(spread_pips=config.BACKTEST_SPREAD_PIPS if spread is None else spread)
    engine.add_strategy(strategy,[symbol])
    began=time.monotonic()
    trades=engine.replay(selected,start_date=start,end_date=end)
    exposure=engine.execution.get_open_positions()
    if variant!='original':
        assert not strategy._proposals, 'Unresolved proposal'
        assert {r['attempt_id'] for r in strategy._orders.values()}=={p['attempt_id'] for p in exposure}, 'Exposure ownership mismatch'
    result=dict(source=source,symbol=symbol,variant=variant,label=label,start=start,end=end,
                metrics=metrics(trades),open_exposure=exposure,bars=dict(Counter(b.timeframe for b in selected)),
                seconds=time.monotonic()-began)
    name=f'{source}_{symbol}_{variant}_{label}'
    write_json(OUT/(name+'.json'),result)
    write_json(OUT/(name+'_trades.json'),trades)
    print(json.dumps(dict(job=name,metrics=result['metrics'],seconds=result['seconds'])),flush=True)
    return result,trades


def main():
    logging.disable(logging.CRITICAL)
    OUT.mkdir(parents=True,exist_ok=True)
    params,symbols=settings()
    old=json.loads((PREVIOUS/'manifest.json').read_text())
    assert params==old['parameters'] and symbols==old['symbols']
    pipeline=['engine.py','backtest_engine.py','execution/simulated_execution.py','risk/risk_manager.py',
              'portfolio/portfolio_manager.py','data/historical_loader.py','data/histdata_provenance.py',
              'research_ema_fib_review.py','config.py','live_config.py']
    # Membership is irrelevant to these isolated replays; retired settings are frozen above.
    assert all(file_hash(ROOT/p)==old['code_hashes'][p] for p in pipeline if p!='live_config.py'), 'Baseline pipeline changed'
    files={s:{src:paths_for(src,s) for src in SOURCES} for s in symbols}
    inputs={p:file_hash(p) for sources in files.values() for paths in sources.values() for p in paths}
    sidecars={str(metadata_path(p)):file_hash(metadata_path(p)) for p in inputs if metadata_path(p).exists()}
    assert inputs==old['input_hashes'] and sidecars==old['sidecar_hashes'], 'Baseline inputs changed'
    code=pipeline+['strategies/ema_fib_running.py','research_ema_fib_running_corrections.py',
                   'research_ema_fib_running_baseline.py','research_ema_fib_running_review.py']
    manifest=dict(created_utc=datetime.now(timezone.utc),workers=1,parameters=params,symbols=symbols,
                  frozen_revision=REVISION,frozen_source_sha256=hashlib.sha256(SOURCE.encode()).hexdigest(),
                  code_hashes={p:file_hash(ROOT/p) for p in code},input_hashes=inputs,sidecar_hashes=sidecars,
                  baseline_artifact_hashes={str(p):file_hash(p) for p in PREVIOUS.glob('*.json')},
                  assumptions=old['assumptions'],folds=FOLDS,
                  rolling_validation='Fixed parameters; historical reuse, not fresh holdout. No pre-2016 warmup.',
                  variants={'tracking':'Accepted-order lifecycle only; original extreme initialization',
                            'corrected':'Lifecycle plus completed closes from actual anchor through confirmation'})
    write_json(OUT/'manifest.json',manifest)
    results,groups,controls=[],{},[]
    for symbol in symbols:
        for source,paths in files[symbol].items():
            print(f'Loading {source} {symbol}',flush=True)
            limited=symbol=='USDCAD' and source=='mt5_icmarkets_utc'
            load_start=datetime(2025,1,1) if limited else datetime(2019,7,1) if source=='mt5_icmarkets_utc' else datetime(2016,1,1)
            bars=load_and_merge(paths,start=load_start,end=PERIODS[-1][2])
            jobs=[]
            for label,a,b in PERIODS:
                if limited and label=='2020_2025':
                    continue
                jobs.extend((v,label,a,b,None) for v in ('tracking','corrected'))
            if not limited:
                jobs.append(('corrected','spread_1pip',PERIODS[0][1],PERIODS[0][2],1.0))
            if symbol=='USDCAD':
                jobs.extend((v,'2025_h2',datetime(2025,7,1),datetime(2026,1,1),None) for v in ('tracking','corrected'))
            if source!='mt5_icmarkets_utc':
                for a,split,b in FOLDS:
                    jobs.extend([('corrected',f'fold_{split.year}_train',a,split,None),
                                 ('corrected',f'fold_{split.year}_test',split,b,None)])
            elif not limited:
                jobs.extend([('corrected','fold_2024_train',datetime(2020,1,1),datetime(2024,1,1),None),
                             ('corrected','fold_2024_test',datetime(2024,1,1),datetime(2026,1,1),None)])
            if source=='dukascopy' and symbol in ('EURUSD','AUDUSD'):
                result,ts=replay(bars,source,symbol,'original','control',PERIODS[0][1],PERIODS[0][2],params)
                previous=json.loads((PREVIOUS/f'{source}_{symbol}_2020_2025_trades.json').read_text())
                assert json.loads(json.dumps(ts,default=str))==previous, 'Frozen baseline drift'
                assert result['open_exposure']==[], 'Baseline ending exposure drift'
                controls.append(dict(source=source,symbol=symbol,all_trade_fields_match=True))
            for variant,label,a,b,spread in jobs:
                result,ts=replay(bars,source,symbol,variant,label,a,b,params,spread)
                results.append(result)
                groups.setdefault((source,variant,label),[]).extend(ts)
                if symbol!='USDCAD':
                    groups.setdefault((source,variant,'six_'+label),[]).extend(ts)
                write_json(OUT/'results.json',results)
            write_json(OUT/'aggregate.json',[dict(source=s,variant=v,label=l,metrics=metrics(ts),
                years={str(y):metrics([t for t in ts if t['close_time'].year==y]) for y in sorted({t['close_time'].year for t in ts})})
                for (s,v,l),ts in groups.items()])
            del bars
    folds=[]
    for source in SOURCES:
        for _,split,_ in FOLDS:
            if source=='mt5_icmarkets_utc' and split.year!=2024:
                continue
            train=metrics(groups[(source,'corrected',f'fold_{split.year}_train')])
            test=metrics(groups[(source,'corrected',f'fold_{split.year}_test')])
            retention=test['expectancy']/train['expectancy'] if train['expectancy'] and train['expectancy']>0 else None
            verdict=('FAIL' if test['total_r']<=0 else 'UNDEFINED' if retention is None else
                     'STRONG' if retention>=.7 else 'MODERATE' if retention>=.4 else 'WEAK')
            folds.append(dict(source=source,test_start=split,train=train,test=test,retention=retention,verdict=verdict))
    write_json(OUT/'folds.json',folds)
    write_json(OUT/'controls.json',controls)
    assert all(file_hash(ROOT/p)==sha for p,sha in manifest['code_hashes'].items()), 'Code changed during research'
    assert all(file_hash(p)==sha for p,sha in inputs.items()), 'Input changed during research'
    write_json(OUT/'complete.json',dict(replays=len(results),baseline_controls=len(controls),code_and_input_hashes_match=True))
    print('Completed corrections comparison and historical rolling validation.',flush=True)


if __name__=='__main__':
    main()
