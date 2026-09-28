"""Fixed-parameter Failed2 market audit. One worker; never connects to MT5."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import inspect
import json
import logging
from pathlib import Path
import time

import config
from backtest_engine import BacktestEngine
from data.historical_loader import find_csv, load_and_merge, bar_close_time
from data.histdata_provenance import file_hash, metadata_path, write_json
from live_config import create_live_strategy_specs
from research_ema_fib_review import metrics, PERIODS
from strategies.failed2 import Failed2Strategy
from analyze_icmarkets_replay import MemoryJournal

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/failed2_review_20260928'
SOURCES=('dukascopy','histdata','mt5_icmarkets_utc')
FOLDS=[(datetime(y,1,1),datetime(y+4,1,1),datetime(y+6,1,1)) for y in (2016,2018,2020)]


def settings():
    s=next(s for s,_ in create_live_strategy_specs() if s.NAME=='Failed2_H4_H1_M5_market')
    params={k:getattr(s,k) for k in inspect.signature(Failed2Strategy).parameters if k not in ('name','tp_rr_ratio')}
    params['name']=s.NAME
    params['blocked_hours']=sorted(params['blocked_hours'])
    return params


class ObservedFailed2(Failed2Strategy):
    def __init__(self,**params):
        super().__init__(**params)
        self.audit=Counter()
        self.examples={}
        self.ticket_context={}
        self.execution=None
        self.active=False
        self.last_proposal=None

    def note(self,key,**details):
        if not self.active:
            return
        self.audit[key]+=1
        if len(self.examples.setdefault(key,[]))<3:
            self.examples[key].append(deepcopy(details))

    def generate_signal(self,event):
        old_bias=deepcopy(self._bias.get(event.symbol))
        old_setup=deepcopy(self._itf_setup.get(event.symbol))
        signal=super().generate_signal(event)
        new_bias=self._bias.get(event.symbol)
        if old_bias and new_bias and old_bias['timestamp']!=new_bias['timestamp'] and old_bias['direction']==new_bias['direction']:
            self.note('same_direction_bias_refresh',time=event.timestamp,had_h1_setup=bool(old_setup))
        if signal and signal.direction!='CANCEL':
            bars=list(self._entry_bars[event.symbol])
            buy=signal.direction=='BUY'
            idxs=self._swing_high_idxs(bars,self.mss_fractal_n,len(bars)-1) if buy else self._swing_low_idxs(bars,self.mss_fractal_n,len(bars)-1)
            broken=[i for i in idxs if (event.close>bars[i].high if buy else event.close<bars[i].low)]
            idx=max(broken)
            level=bars[idx].high if buy else bars[idx].low
            beyond=lambda b: b.close>level if buy else b.close<level
            setup=self._itf_setup[event.symbol]
            earlier=[b for b in bars[idx+1:-1] if beyond(b)]
            details=dict(time=event.timestamp,direction=signal.direction,level=level,
                         swing_time=bars[idx].timestamp,setup_close=setup['close_time'],
                         previous_close=bars[-2].close,first_earlier_break=earlier[0].timestamp if earlier else None)
            self.last_proposal=details
            self.note('signals',**details)
            if beyond(bars[-2]):
                self.note('signal_without_fresh_cross',**details)
            if any(bar_close_time(b)<=setup['close_time'] for b in earlier):
                self.note('selected_swing_broken_before_h1_confirmation',**details)
            if self.execution and self.execution.get_open_positions():
                self.note('signal_while_occupied',**details)
        return signal

    def notify_order_accepted(self,signal,ticket,details=None):
        super().notify_order_accepted(signal,ticket,details)
        self.ticket_context[ticket]=deepcopy(self.last_proposal)
        self.note('accepted',ticket=ticket,context=self.last_proposal)
        if self.last_proposal:
            c=self.last_proposal
            if (c['previous_close']>c['level'] if signal.direction=='BUY' else c['previous_close']<c['level']):
                self.note('accepted_without_fresh_cross',ticket=ticket,**c)


class FreshCrossFailed2(Failed2Strategy):
    """Research hypothesis only: require the immediately previous close to be unbroken."""
    def _detect_buy(self,symbol,bar,setup,bars):
        signal=super()._detect_buy(symbol,bar,setup,bars)
        if signal:
            idx=max(i for i in self._swing_high_idxs(bars,self.mss_fractal_n,len(bars)-1) if bar.close>bars[i].high)
            if bars[-2].close>bars[idx].high:
                return None
        return signal

    def _detect_sell(self,symbol,bar,setup,bars):
        signal=super()._detect_sell(symbol,bar,setup,bars)
        if signal:
            idx=max(i for i in self._swing_low_idxs(bars,self.mss_fractal_n,len(bars)-1) if bar.close<bars[i].low)
            if bars[-2].close<bars[idx].low:
                return None
        return signal


def paths_for(source):
    symbol='USTEC' if source=='mt5_icmarkets_utc' else 'USA100'
    paths=[]
    for tf in ('M5','H1','H4','D1'):
        found=find_csv(symbol,tf,data_source=source)
        assert found, (source,symbol,tf)
        # The newer full broker H4 export supersedes its shorter July snapshot.
        if source=='mt5_icmarkets_utc' and tf=='H4':
            found=[p for p in found if '20160103-20260918' in p]
            assert len(found)==1
        paths.extend(found)
    return symbol,paths


def replay(bars,symbol,params,start,end,variant='current',spread=1.,observed=True):
    selected=[b for b in bars if b.timestamp>=start-timedelta(days=180) and bar_close_time(b)<=end]
    p=deepcopy(params)
    p['pip_sizes'][symbol]=config.PIP_SIZE[symbol]
    cls=FreshCrossFailed2 if variant=='fresh_cross' else ObservedFailed2 if observed else Failed2Strategy
    s=cls(**p)
    e=BacktestEngine(spread_pips=spread)
    e.add_strategy(s,[symbol])
    journal=MemoryJournal()
    e.event_engine.trade_journal=journal
    if isinstance(s,ObservedFailed2):
        s.execution=e.execution
    e.execution.configure_timeframes(selected)
    for b in selected:
        if bar_close_time(b)<=start:
            e.event_engine.warmup_bar(b)
        else:
            if isinstance(s,ObservedFailed2):
                s.active=True
            e.process_bar(b)
    ts=e.execution.get_closed_trades()
    result=dict(metrics=metrics(ts),open_exposure=e.execution.get_open_positions(),
        ending_balance=e.execution.get_account_balance(),max_equity_dd_pct=e.execution.max_equity_drawdown_pct,
        audit=dict(getattr(s,'audit',{})),examples=getattr(s,'examples',{}),
        rejections=dict(Counter(r['reason'] for r in journal.rows if r['event']=='REJECTED')),
        years={str(y):metrics([t for t in ts if t['close_time'].year==y]) for y in sorted({t['close_time'].year for t in ts})},
        directions={d:metrics([t for t in ts if t['direction']==d]) for d in ('BUY','SELL')},
        warmup_bars=dict(Counter(b.timeframe for b in selected if bar_close_time(b)<=start)))
    return result,ts


def main():
    logging.disable(logging.CRITICAL)
    OUT.mkdir(parents=True,exist_ok=True)
    params=settings()
    paths={src:paths_for(src) for src in SOURCES}
    code=['research_failed2_review.py','strategies/failed2.py','engine.py','backtest_engine.py',
          'execution/simulated_execution.py','risk/risk_manager.py','risk/validation.py',
          'portfolio/portfolio_manager.py','data/historical_loader.py','data/histdata_provenance.py','live_config.py','config.py']
    manifest=dict(created_utc=datetime.now(timezone.utc),parameters=params,workers=1,
        code_hashes={p:file_hash(ROOT/p) for p in code},
        input_hashes={p:file_hash(p) for _,files in paths.values() for p in files},
        metadata_hashes={str(metadata_path(p)):file_hash(metadata_path(p)) for _,files in paths.values() for p in files if metadata_path(p).exists()},
        assumptions=dict(risk_pct=config.RISK_PCT,initial_balance=10000,commission=0,default_spread_points=1,
            warmup_days=180,cutoff='2026-07-15',news=False,shared_portfolio=False,daily_loss_gate=False,
            variable_spread=False,swap=False,extra_slippage=False,optimization=False),
        note='Current DEMO parameters. Fresh-cross is a separate unpromoted rule hypothesis. Reused historical periods, not fresh OOS.')
    write_json(OUT/'manifest.json',manifest)
    results=[]
    controls=[]
    for source,(symbol,files) in paths.items():
        print('Loading '+source,flush=True)
        bars=load_and_merge(files,start=datetime(2019,7,1) if source=='mt5_icmarkets_utc' else datetime(2016,1,1),end=PERIODS[-1][2])
        jobs=[(v,label,a,b,1.) for v in ('current','fresh_cross') for label,a,b in PERIODS]
        jobs.extend(('current',f'spread_{spread:g}',PERIODS[0][1],PERIODS[0][2],spread) for spread in (2.,5.))
        for a,split,b in FOLDS:
            if source=='mt5_icmarkets_utc' and split.year!=2024:
                continue
            jobs.extend([('current',f'fold_{split.year}_train',a,split,1.),('current',f'fold_{split.year}_test',split,b,1.)])
        for variant,label,a,b,spread in jobs:
            began=time.monotonic()
            result,ts=replay(bars,symbol,params,a,b,variant,spread)
            result.update(source=source,symbol=symbol,variant=variant,label=label,start=a,end=b,spread=spread,seconds=time.monotonic()-began)
            name=f'{source}_{variant}_{label}'
            write_json(OUT/(name+'_trades.json'),ts)
            write_json(OUT/(name+'.json'),result)
            results.append(result)
            write_json(OUT/'results.json',results)
            print(json.dumps(dict(job=name,metrics=result['metrics'],seconds=result['seconds'])),flush=True)
            if variant=='current' and label=='2020_2025':
                plain,plain_ts=replay(bars,symbol,params,a,b,observed=False)
                assert plain_ts==ts and plain['open_exposure']==result['open_exposure']
                controls.append(dict(source=source,all_trade_fields_match=True,ending_exposure_matches=True))
        del bars
    indexed={(r['source'],r['label']):r for r in results if r['variant']=='current'}
    folds=[]
    for source in SOURCES:
        for _,split,_ in FOLDS:
            if (source,f'fold_{split.year}_train') not in indexed:
                continue
            train=indexed[(source,f'fold_{split.year}_train')]['metrics']
            test=indexed[(source,f'fold_{split.year}_test')]['metrics']
            retention=test['expectancy']/train['expectancy'] if train['expectancy'] and train['expectancy']>0 else None
            verdict='FAIL' if test['total_r']<=0 else 'UNDEFINED' if retention is None else 'STRONG' if retention>=.7 else 'MODERATE' if retention>=.4 else 'WEAK'
            folds.append(dict(source=source,test_year=split.year,train=train,test=test,retention=retention,verdict=verdict))
    write_json(OUT/'folds.json',folds)
    write_json(OUT/'controls.json',controls)
    assert all(file_hash(ROOT/p)==h for p,h in manifest['code_hashes'].items())
    write_json(OUT/'complete.json',dict(replays=len(results),controls=len(controls),code_hashes_match=True))
    print('Failed2 review complete.',flush=True)


if __name__=='__main__':
    main()
