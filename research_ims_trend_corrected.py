"""Sequential IMS correction controls, reruns, and predeclared policy comparisons.

No MT5 connection. July 15 onward remains excluded. Default DEMO policies stay
unchanged. Retains the September 29 pre-correction result directory untouched.
"""
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path
import time

import config
from backtest_engine import BacktestEngine
from data.historical_loader import load_and_merge
from data.histdata_provenance import file_hash, write_json
from research_ema_fib_review import metrics
from research_ims_trend_baseline import ImsStrategy as BaselineIms, SOURCE_SHA256, REVISION
from research_ims_trend_review import ROOT, OUT as OLD, START, END, paths_for, settings
from strategies.ims import ImsStrategy
from analyze_icmarkets_replay import MemoryJournal

OUT = ROOT/'output/ims_trend_corrected_20260929'
POLICIES = {'current': {}, 'all_hours': {'pending_cancel_hours':'all'},
            'fresh_break': {'fresh_break_required':True}}
FOUR = ['USDJPY','AUDUSD','EURUSD','GBPUSD']


def run(bars, params, symbol, start, strategy_class=ImsStrategy):
    strategy = strategy_class(**params)
    engine = BacktestEngine(rr_ratio=2.5)
    engine.add_strategy(strategy,[symbol])
    journal = MemoryJournal()
    engine.event_engine.trade_journal = journal
    trades = engine.replay(bars,start_date=start,end_date=END)
    return trades, engine, strategy, journal


def main():
    logging.disable(logging.CRITICAL)
    OUT.mkdir(parents=True,exist_ok=True)
    params,symbols = settings()
    old = json.loads((OLD/'manifest.json').read_text())
    for path,digest in old['input_hashes'].items():
        assert file_hash(path)==digest, f'Input changed since baseline: {path}'
    assert old['parameters']==params
    code = ['strategies/ims.py','strategies/ims_trend_tracking.py','engine.py',
        'execution/simulated_execution.py','backtest_engine.py','config.py','live_config.py',
        'risk/risk_manager.py','data/historical_loader.py','research_ims_trend_corrected.py',
        'research_ims_trend_baseline.py','utils/strategy_state.py']
    manifest = dict(created_at=datetime.now(timezone.utc),parameters=params,policies=POLICIES,
        source_manifest_sha256=file_hash(OLD/'manifest.json'),input_hashes=old['input_hashes'],
        sidecar_hashes=old['sidecar_hashes'],baseline_revision=REVISION,baseline_sha256=SOURCE_SHA256,
        code_hashes={p:file_hash(ROOT/p) for p in code},workers=1,cutoff=END,
        assumptions=old['assumptions'],
        policy_design='Broker four-symbol diagnostics, one change at a time. '
        'Fixed policies replayed continuously from 2016-07-01. '
        'Rolling 4-year training/2-year test slices begin 2020-07-01, 2022-07-01, 2024-07-01. '
        'Choose training net R only, at least 20 closed training trades and PF > 1. '
        'Default wins ties. No eligible alternative means retain default for comparison. '
        'Exclude trades opened before each evaluation boundary. '
        'These historical dates have prior research exposure; this is not untouched OOS validation.')
    existing = OUT/'manifest.json'
    if existing.exists():
        previous = json.loads(existing.read_text())
        for field in ('parameters','policies','input_hashes','sidecar_hashes','code_hashes'):
            assert previous[field]==manifest[field], f'Cannot resume changed study: {field}'
    else:
        write_json(existing,manifest)
    # Exact old-source control on identical data and current unchanged engine.
    control = OUT/'baseline_control.json'
    if not control.exists():
        print('Frozen EURUSD control',flush=True)
        bars = load_and_merge(paths_for('dukascopy','EURUSD'),start=START-timedelta(days=180),end=END)
        trades,engine,_,_ = run(bars,params,'EURUSD',START,BaselineIms)
        saved = json.loads((OLD/'dukascopy_EURUSD_trades.json').read_text())
        assert json.loads(json.dumps(trades,default=str))==saved
        write_json(control,dict(passed=True,trades=len(trades),comparison='Every saved trade field matches'))
        del bars,engine
    jobs = []
    for source in ('dukascopy','histdata','mt5_icmarkets_utc'):
        for symbol in symbols:
            if not (OLD/f'{source}_{symbol}.json').exists():
                continue
            jobs.append((source,symbol))
    for source,symbol in jobs:
        name = f'{source}_{symbol}'
        if (OUT/f'{name}.json').exists():
            continue
        print('Corrected',name,flush=True)
        began = time.monotonic()
        start = datetime(2025,4,1) if source=='mt5_icmarkets_utc' and symbol=='USDCAD' else START
        bars = load_and_merge(paths_for(source,symbol),start=start-timedelta(days=180),end=END)
        trades,engine,strategy,journal = run(bars,params,symbol,start)
        write_json(OUT/f'{name}_trades.json',trades)
        write_json(OUT/f'{name}.json',dict(source=source,symbol=symbol,start=start,end=END,
            metrics=metrics(trades),final_exposure=engine.execution.get_open_positions(),
            tracked_orders=strategy._orders,proposals=strategy._proposals,
            retired_origins=len(strategy._retired_setups),events=dict(Counter(r['event'] for r in journal.rows)),
            rejections=dict(Counter(r['reason'] for r in journal.rows if r['event']=='REJECTED')),
            seconds=time.monotonic()-began))
        assert not strategy._proposals
        assert len(strategy._orders)==len(engine.execution.get_open_positions())
        print(name,metrics(trades),flush=True)
        del bars,engine,strategy,journal
    # Separate chronology for policy research; never substitute it into the fixed baseline comparison.
    for symbol in FOUR:
        source = 'mt5_icmarkets_utc'
        if all((OUT/f'policy_{symbol}_{p}.json').exists() for p in POLICIES):
            continue
        start = datetime(2016,7,1)
        print('Policy history',symbol,flush=True)
        bars = load_and_merge(paths_for(source,symbol),start=datetime(2016,1,1),end=END)
        for policy,overrides in POLICIES.items():
            path = OUT/f'policy_{symbol}_{policy}.json'
            if path.exists():
                continue
            trades,engine,strategy,_ = run(bars,dict(params,**overrides),symbol,start)
            assert not strategy._proposals
            assert len(strategy._orders)==len(engine.execution.get_open_positions())
            write_json(path,dict(policy=policy,symbol=symbol,metrics=metrics(trades),
                final_exposure=engine.execution.get_open_positions()))
            write_json(OUT/f'policy_{symbol}_{policy}_trades.json',trades)
            print(symbol,policy,metrics(trades),flush=True)
        del bars,engine,strategy


if __name__=='__main__':
    main()
