"""Reproduce the frozen IMS Reversal study on repaired HistData, one worker.

No parameter search, MT5 connection, or forward-demo-period evaluation.
Earlier result files remain untouched. Current setup policies are additional
fixed-parameter comparisons, not replacements for the frozen-code data check.
"""
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
from pathlib import Path
import time

import pandas as pd
import config
from backtest_engine import BacktestEngine
from data.historical_loader import load_and_merge, bar_close_time, _is_us_dst
from data.histdata_provenance import file_hash, metadata_path, write_json
from models import BarEvent
import research_ims_reversal as previous
from research_ims_baseline import REVISION, SOURCE
from strategies.ims_reversal import ImsReversalStrategy

ROOT = Path(__file__).resolve().parent
OLD = ROOT/'output/ims_reversal_review_20260918'
OUT = ROOT/'output/ims_histdata_rerun_20260922'
START, END = datetime(2020, 1, 1), datetime(2026, 1, 1)
POLICIES = {f'{hours}_{target}': dict(pending_cancel_hours=hours, pending_target_reference=target)
            for hours in ('entry', 'all') for target in ('moving', 'submitted')}


def bounded(bars, start, end):
    if end > previous.CUTOFF:
        raise ValueError('Protected forward-demo period cannot be evaluated')
    return [b for b in bars if b.timestamp >= start-timedelta(days=180) and bar_close_time(b) <= end]


def proxy_h4(bars):
    """Match the old untuned H4 grouping experiment on the repaired prices."""
    frame = pd.DataFrame([dict(time=b.timestamp, open=b.open, high=b.high, low=b.low,
                              close=b.close, volume=b.volume) for b in bars if b.timeframe == 'M5'])
    offsets = frame.time.dt.normalize().map(lambda t: 3 if _is_us_dst(t.to_pydatetime()) else 2)
    delta = pd.to_timedelta(offsets, unit='h')
    frame['bucket'] = (frame.time+delta).dt.floor('4h')-delta
    grouped = frame.groupby('bucket', sort=True).agg(open=('open','first'), high=('high','max'),
        low=('low','min'), close=('close','last'), volume=('volume','sum'))
    h4 = [BarEvent('EURUSD','H4',t.to_pydatetime(),r.open,r.high,r.low,r.close,r.volume)
          for t,r in grouped.iterrows()]
    combined = [b for b in bars if b.timeframe != 'H4']+h4
    durations = {'M5':5, 'M15':15, 'H4':240}
    combined.sort(key=lambda b:(bar_close_time(b),durations[b.timeframe],b.symbol))
    return combined


def main():
    logging.disable(logging.CRITICAL)
    OUT.mkdir(parents=True, exist_ok=True)
    previous.OUT = OUT
    old_jobs = []
    for path in sorted(OLD.glob('histdata*.json')):
        result = json.loads(path.read_text())
        if isinstance(result, dict) and 'metrics' in result:
            old_jobs.append((path, result))
    assert len(old_jobs) == 15
    sources = {s:previous.paths_for(s,'EURUSD') for s in ('histdata','dukascopy')}
    code = ['research_ims_histdata_rerun.py','research_ims_reversal.py','research_ims_baseline.py',
            'strategies/ims_reversal.py','strategies/ims_setup_tracking.py','engine.py','backtest_engine.py',
            'execution/simulated_execution.py','risk/risk_manager.py','data/historical_loader.py',
            'data/histdata_provenance.py','config.py','live_config.py']
    assert config.RISK_PCT == .005 and config.BACKTEST_SPREAD_PIPS['EURUSD'] == .1 and config.COMMISSION_PER_LOT == 7.
    manifest = dict(created_at_utc=datetime.now(timezone.utc),
        symbol='EURUSD', cutoff=previous.CUTOFF, workers=1, parameters=previous.BASE, policies=POLICIES,
        purpose='Frozen rerun; no parameter selection', frozen_strategy_revision=REVISION,
        frozen_strategy_sha256=hashlib.sha256(SOURCE.encode()).hexdigest(),
        input_hashes={str(Path(p).relative_to(ROOT) if Path(p).is_absolute() else p):file_hash(p)
                      for files in sources.values() for p in files},
        sidecar_hashes={str(metadata_path(p)):file_hash(metadata_path(p)) for p in sources['histdata']},
        code_hashes={p:file_hash(ROOT/p) for p in code},
        prior_result_hashes={p.name:file_hash(p) for p,_ in old_jobs},
        prior_cost_evidence=dict(report='strategy_log/ims_reversal_review_20260918.md',
            note='Early JSON files omit costs; the dated report and spread1.0 filename fix 0.1/1.0-pip spread, 0.5% risk, and $7/lot commission.'),
        frozen_selection=json.loads((OLD/'selection_dukascopy.json').read_text()),
        cost_assumptions=dict(spread_pips=config.BACKTEST_SPREAD_PIPS['EURUSD'],
            commission_per_lot=config.COMMISSION_PER_LOT, risk_pct=config.RISK_PCT,
            swaps=False, daily_loss_gate=False, initial_balance=10000))
    write_json(OUT/'manifest.json',manifest)

    # An unchanged-data control detects engine/strategy drift before attributing
    # differences to the repaired HistData. Compare every original trade field.
    print('Control: frozen strategy on unchanged Dukascopy, 2020-2025',flush=True)
    control_bars = bounded(load_and_merge(sources['dukascopy'],start=START-timedelta(days=180),end=END),START,END)
    previous.run(control_bars,'dukascopy','EURUSD','baseline',START,END)
    control_name = 'dukascopy_EURUSD_baseline_20200101_20260101_trades.json'
    old_trades = json.loads((OLD/control_name).read_text())
    new_trades = json.loads((OUT/control_name).read_text())
    assert len(old_trades) == len(new_trades)
    for before, after in zip(old_trades,new_trades):
        for key,value in before.items():
            assert after.get(key) == value, f'Control drift: {key}: {value} -> {after.get(key)}'
    write_json(OUT/'control.json',dict(all_original_trade_fields_identical=True,trades=len(old_trades)))
    del control_bars

    bars = load_and_merge(sources['histdata'],start=START-timedelta(days=180),end=previous.CUTOFF)
    bars = [b for b in bars if bar_close_time(b) <= previous.CUTOFF]
    print(f'Loaded {len(bars):,} repaired bars: {dict(Counter(b.timeframe for b in bars))}',flush=True)
    comparisons = []
    for index,(path,old) in enumerate(old_jobs,1):
        start,end = datetime.fromisoformat(old['start']),datetime.fromisoformat(old['end'])
        selected = bounded(bars,start,end)
        if old['source'].endswith('_broker_h4_proxy'):
            selected = bounded(proxy_h4(selected),start,end)
        spread = old.get('execution_assumptions', {}).get('spread_pips',
            1.0 if '_spread1.0' in path.stem else config.BACKTEST_SPREAD_PIPS)
        if isinstance(spread,dict):
            assert spread == config.BACKTEST_SPREAD_PIPS
            spread = None
        print(f'Frozen rerun {index}/15: {path.stem}',flush=True)
        result = previous.run(selected,old['source'],'EURUSD',old['variant'],start,end,spread)
        assert result['parameters'] == old['parameters'] or json.loads(json.dumps(result['parameters'])) == old['parameters']
        if 'execution_assumptions' in old:
            assert result['execution_assumptions'] == old['execution_assumptions']
        comparisons.append(dict(name=path.stem,old=old['metrics'],new=result['metrics']))
        write_json(OUT/'data_comparison.json',comparisons)

    current = []
    jobs = [(policy,START,END,None) for policy in POLICIES]
    jobs += [('entry_moving',datetime(y,1,1),datetime(y+2,1,1),None) for y in (2020,2022,2024)]
    jobs += [('entry_moving',datetime(2026,1,1),previous.CUTOFF,None), ('entry_moving',START,END,1.0)]
    for index,(policy,start,end,spread) in enumerate(jobs,1):
        print(f'Current tracking {index}/9: {policy} {start.date()} to {end.date()}, spread={spread}',flush=True)
        strategy = ImsReversalStrategy(**previous.BASE,**POLICIES[policy])
        engine = BacktestEngine(initial_balance=10000,rr_ratio=2.5,
            spread_pips=config.BACKTEST_SPREAD_PIPS if spread is None else spread)
        engine.add_strategy(strategy,['EURUSD'])
        began = time.monotonic()
        trades = engine.replay(bounded(bars,start,end),start_date=start,end_date=end)
        assert all(start <= t['close_time'] <= end for t in trades)
        result = dict(policy=policy,start=start,end=end,spread=spread,metrics=previous.metrics(trades),
            ending_balance=engine.execution.get_account_balance(),max_equity_dd_pct=engine.execution.max_equity_drawdown_pct,
            open_exposure=len(engine.execution.get_open_positions()),seconds=time.monotonic()-began)
        name = f'current_{policy}_{start:%Y%m%d}_{end:%Y%m%d}'+(f'_spread{spread}' if spread is not None else '')
        write_json(OUT/(name+'.json'),result)
        write_json(OUT/(name+'_trades.json'),trades)
        current.append(result)
        write_json(OUT/'current_tracking.json',current)
        print(json.dumps(result,default=str),flush=True)
    print('Completed 25 sequential replays, including unchanged-data control.',flush=True)


if __name__ == '__main__':
    main()
