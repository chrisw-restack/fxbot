"""Fixed GBPUSD Candle review and isolated logic hypotheses, sequential replay."""
from collections import Counter
from datetime import datetime
import inspect
import json
import logging
from pathlib import Path
import time

from backtest_engine import BacktestEngine
from data.historical_loader import bar_close_time, find_csv, load_and_merge
from data.histdata_provenance import file_hash, metadata_path, write_json
from live_config import create_live_strategy_specs
from research_candle_usdjpy_baseline import CandleConfirmationStrategy as FrozenCandle, REVISION, SOURCE_SHA256
from research_candle_usdjpy_corrected import TrackingOnly, ResearchJournal, comparable
from research_ema_fib_review import metrics
from strategies.candle_confirmation import CandleConfirmationStrategy

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/candle_gbpusd_review_20260930'
START,END,LOAD=datetime(2017,1,1),datetime(2026,7,15),datetime(2016,1,1)
SOURCES=('dukascopy','histdata','mt5_icmarkets_utc')


def settings():
    s=next(s for s,_ in create_live_strategy_specs() if s.NAME=='CandleConfirmation_GBPUSD_H1_M5')
    aliases=dict(pip_sizes='_pip_sizes',blocked_hours='_blocked',name='NAME')
    p={k:getattr(s,aliases.get(k,k)) for k in inspect.signature(CandleConfirmationStrategy).parameters}
    p['blocked_hours']=sorted(p['blocked_hours'])
    return p


def paths_for(source):
    paths=[]
    for tf in ('M5','H1','D1'):
        found=find_csv('GBPUSD',tf,data_source=source)
        assert found and len(found)==1,(source,tf,found)
        paths.extend(found)
    return paths


class ObservedCandle(CandleConfirmationStrategy):
    """Production control or one isolated hypothesis; diagnostics never select params."""
    def __init__(self,variant='current',**params):
        super().__init__(**params)
        self.variant=variant
        self.active=False
        self.audit=Counter()
        self.examples={}

    def note(self,key,**details):
        if self.active:
            self.audit[key]+=1
            examples=self.examples.setdefault(key,[])
            if len(examples)<3:
                examples.append(details)

    def _record_signal_context(self,symbol,bias,bars,pivot,leg_start):
        super()._record_signal_context(symbol,bias,bars,pivot,leg_start)
        context=self.get_last_signal_context(symbol)
        assert pivot+self.fractal_n<len(bars)-1
        assert all(b.timestamp>=bias['timestamp'] for b in bars)
        self.note('detected',**context)
        for key in ('fresh_cross','opposite_extreme_breached','trend_allows_at_signal'):
            self.note(key+'_'+str(context[key]).lower(),**context)

    def _observe(self,signal):
        if signal and self.variant=='fresh_cross' and not self.get_last_signal_context(signal.symbol)['fresh_cross']:
            self._signal_fired[signal.symbol]=False
            self.note('fresh_cross_filtered',signal_time=signal.timestamp)
            return None
        return signal

    def _detect_bullish_mss(self,*args):
        return self._observe(super()._detect_bullish_mss(*args))

    def _detect_bearish_mss(self,*args):
        return self._observe(super()._detect_bearish_mss(*args))

    def _check_buy(self,symbol,bar,bias):
        if self.variant=='opposite_extreme' and bar.low<=bias['engulf_low']:
            self.note('opposite_extreme_expired',origin=bias['timestamp'],time=bar.timestamp)
            self._expire_bias(symbol)
            return None
        return super()._check_buy(symbol,bar,bias)

    def _check_sell(self,symbol,bar,bias):
        if self.variant=='opposite_extreme' and bar.high>=bias['engulf_high']:
            self.note('opposite_extreme_expired',origin=bias['timestamp'],time=bar.timestamp)
            self._expire_bias(symbol)
            return None
        return super()._check_sell(symbol,bar,bias)


def replay(bars,params,variant='current',spread=.2,plain=False):
    if variant=='original':
        s=FrozenCandle(**params)
    elif variant=='tracking_only':
        s=TrackingOnly(**params)
    elif plain:
        s=CandleConfirmationStrategy(**params)
    else:
        s=ObservedCandle(variant=variant,**params)
    e=BacktestEngine(spread_pips=spread)
    e.add_strategy(s,['GBPUSD'])
    journal=ResearchJournal(s)
    e.event_engine.trade_journal=journal
    warmup=Counter(b.timeframe for b in bars if bar_close_time(b)<=START)
    assert all(warmup[tf]>=n for tf,n in CandleConfirmationStrategy(**params).warmup_requirements().items())
    e.execution.configure_timeframes(bars)
    for b in bars:
        if bar_close_time(b)<=START:
            e.event_engine.warmup_bar(b)
        elif bar_close_time(b)<=END:
            if hasattr(s,'active'):
                s.active=True
            e.process_bar(b)
    trades=e.execution.get_closed_trades()
    balance,previous_close=10000.,None
    budget_trades=[]
    for t in sorted(trades,key=lambda t:t['close_time']):
        assert previous_close is None or previous_close<=t['open_time']
        budget_trades.append(dict(t,net_r=t['pnl']/(balance*.005)))
        balance+=t['pnl']
        previous_close=t['close_time']
    assert abs(balance-e.execution.get_account_balance())<1e-7
    final=e.execution.get_open_positions()
    if variant not in ('original','tracking_only'):
        assert all(abs(t['entry_price']-t['sl'])/.0001+1e-8>=params['min_sl_pips'] for t in trades)
        assert all(abs(t['tp']-t['entry_price'])/abs(t['entry_price']-t['sl'])+1e-8>=1 for t in trades)
        assert len(s._orders)==len(final) and not s._proposals
    windows={'2020_2025':(datetime(2020,1,1),datetime(2026,1,1)),
             '2026_to_july14':(datetime(2026,1,1),END)}
    windows.update({str(y):(datetime(y,1,1),min(datetime(y+1,1,1),END)) for y in range(2017,2027)})
    for y in (2020,2022,2024):
        windows[f'fold_{y}_train']=(max(START,datetime(y-4,7,1)),datetime(y,7,1))
        windows[f'fold_{y}_test']=(datetime(y,7,1),datetime(y+2,7,1))
    def subset(a,b):
        return [t for t in trades if a<=t['open_time'] and t['close_time']<b]
    tests=[t for t in trades if datetime(2020,7,1)<=t['open_time'] and t['close_time']<datetime(2026,7,1)]
    result=dict(metrics=metrics(trades),budget_metrics=metrics(budget_trades),
        directions={d:metrics([t for t in trades if t['direction']==d]) for d in ('BUY','SELL')},
        windows={k:metrics(subset(a,b)) for k,(a,b) in windows.items()},later_tests=metrics(tests),
        growth_pct=(balance/10000-1)*100,ending_balance=balance,
        equity_dd_pct=e.execution.max_equity_drawdown_pct,final_exposure=final,warmup_bars=dict(warmup),
        minimum_filled_stop_pips=min((abs(t['entry_price']-t['sl'])/.0001 for t in trades),default=None),
        rejected=dict(Counter(r['reason'] for r in journal.rows if r['event']=='REJECTED')),
        events=dict(Counter(r['event'] for r in journal.rows)),
        audit=dict(getattr(s,'audit',{})),examples=getattr(s,'examples',{}))
    return result,trades,journal.contexts


def main():
    logging.disable(logging.CRITICAL)
    OUT.mkdir(parents=True,exist_ok=True)
    assert not (OUT/'manifest.json').exists(),'Use a new output directory; historical results are immutable.'
    params=settings()
    files={src:paths_for(src) for src in SOURCES}
    code=['research_candle_gbpusd_review.py','research_candle_usdjpy_baseline.py',
        'research_candle_usdjpy_corrected.py','research_candle_usdjpy_review.py',
        'research_ema_fib_review.py','analyze_icmarkets_replay.py','backtest_engine.py','engine.py',
        'strategies/candle_confirmation.py','strategies/candle_confirmation_tracking.py',
        'execution/simulated_execution.py','risk/risk_manager.py','risk/validation.py',
        'models.py','config.py','live_config.py','data/historical_loader.py','utils/warmup.py']
    manifest=dict(start=START,end=END,load_start=LOAD,params=params,risk_pct=.005,
        frozen_revision=REVISION,frozen_signal_source_sha256=SOURCE_SHA256,
        hypotheses=['fresh_cross_only','expire_at_opposite_engulf_extreme_only'],
        code_hashes={p:file_hash(ROOT/p) for p in code},
        input_hashes={str(p):file_hash(p) for ps in files.values() for p in ps},
        metadata_hashes={str(metadata_path(p)):file_hash(metadata_path(p))
            for ps in files.values() for p in ps if metadata_path(p).exists()})
    write_json(OUT/'manifest.json',manifest)
    results,controls=[],[]
    for src,paths in files.items():
        bars=load_and_merge(paths,start=LOAD,end=END)
        jobs=[(v,.2) for v in ('original','tracking_only','current','fresh_cross','opposite_extreme')]
        if src=='mt5_icmarkets_utc':
            jobs.extend((v,spread) for spread in (1.,2.) for v in ('current','fresh_cross','opposite_extreme'))
        original=None
        for variant,spread in jobs:
            t0=time.monotonic()
            r,ts,contexts=replay(bars,params,variant,spread)
            r.update(source=src,variant=variant,spread_pips=spread,seconds=time.monotonic()-t0)
            name=f'{src}_{variant}_spread{spread:g}'
            write_json(OUT/f'{name}_trades.json',ts)
            write_json(OUT/f'{name}_contexts.json',contexts)
            results.append(r)
            write_json(OUT/'results.json',results)
            print(json.dumps(dict(job=name,metrics=r['metrics'],later=r['later_tests']['total_r'],
                growth=r['growth_pct'],seconds=r['seconds'])),flush=True)
            if variant=='original':
                original=comparable(ts)
            elif variant=='tracking_only':
                assert original==comparable(ts),'Attribution changed uninterrupted economic trades.'
                controls.append(dict(source=src,control='original_vs_tracking',all_fields_match=True))
            elif variant=='current' and spread==.2:
                plain,plain_ts,_=replay(bars,params,plain=True)
                assert plain_ts==ts and plain['final_exposure']==r['final_exposure'],'Observer changed production trades.'
                controls.append(dict(source=src,control='production_vs_observer',all_fields_match=True))
            write_json(OUT/'controls.json',controls)
        del bars
    assert all(file_hash(ROOT/p)==h for p,h in manifest['code_hashes'].items())
    assert all(file_hash(p)==h for p,h in manifest['input_hashes'].items())
    assert all(file_hash(p)==h for p,h in manifest['metadata_hashes'].items())
    write_json(OUT/'complete.json',dict(research_replays=len(results),controls=len(controls),hashes_match=True))


if __name__=='__main__':
    main()
