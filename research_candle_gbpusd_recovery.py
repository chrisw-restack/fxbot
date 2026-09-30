"""Predeclared GBP recovery-only gates, one worker, no DEMO promotion.

Main test retains all current GBP parameters. Recovery may require an opposite
extreme touch only, or also a close back inside the engulf range. This idea was
suggested by already-seen historical subgroups; later windows are retrospective.
"""
from collections import Counter
from datetime import datetime,timedelta
import json
import logging
from pathlib import Path
import time

from backtest_engine import BacktestEngine
from data.historical_loader import load_and_merge,bar_close_time
from data.histdata_provenance import file_hash,metadata_path,write_json
from research_candle_gbpusd_review import ObservedCandle,settings,paths_for,SOURCES
from research_candle_usdjpy_corrected import ResearchJournal
from research_ema_fib_review import metrics
from strategies.candle_confirmation import CandleConfirmationStrategy
from utils.warmup import warmup_days

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/candle_gbpusd_recovery_20260930'
PREVIOUS=ROOT/'output/candle_gbpusd_review_20260930'
START,END,LOAD=datetime(2017,1,1),datetime(2026,7,15),datetime(2016,1,1)
POLICIES=('off','touch','inside')


class RecoveryCandle(ObservedCandle):
    """Research gates applied before the production wrapper records a proposal."""
    def __init__(self,recovery='touch',**params):
        if recovery not in POLICIES:
            raise ValueError('recovery must be off, touch, or inside')
        super().__init__(variant='current',**params)
        self.recovery=recovery

    def _observe(self,signal):
        signal=super()._observe(signal)
        if signal is None or self.recovery=='off':
            return signal
        context=self.get_last_signal_context(signal.symbol)
        if not context['opposite_extreme_breached']:
            self._signal_fired[signal.symbol]=False
            self.note('no_opposite_touch_filtered',time=signal.timestamp)
            return None
        inside=(context['engulf_low']<signal.entry_price<context['engulf_high'])
        if self.recovery=='inside' and not inside:
            self._signal_fired[signal.symbol]=False
            self.note('not_back_inside_filtered',time=signal.timestamp)
            return None
        self._last_signal_context[signal.symbol].update(recovery_policy=self.recovery,
                                                       close_back_inside_range=inside)
        return signal


def replay(bars,params,policy='off',spread=.2,start=START,end=END,plain=False):
    strategy=CandleConfirmationStrategy(**params) if plain else RecoveryCandle(recovery=policy,**params)
    engine=BacktestEngine(spread_pips=spread)
    engine.add_strategy(strategy,['GBPUSD'])
    journal=ResearchJournal(strategy)
    engine.event_engine.trade_journal=journal
    warmup=Counter(b.timeframe for b in bars if bar_close_time(b)<=start)
    assert all(warmup[tf]>=n for tf,n in CandleConfirmationStrategy(**params).warmup_requirements().items())
    engine.execution.configure_timeframes(bars)
    for bar in bars:
        if bar_close_time(bar)<=start:
            engine.event_engine.warmup_bar(bar)
        elif bar_close_time(bar)<=end:
            if hasattr(strategy,'active'):
                strategy.active=True
            engine.process_bar(bar)
    trades=engine.execution.get_closed_trades()
    final=engine.execution.get_open_positions()
    assert len(strategy._orders)==len(final) and not strategy._proposals
    assert all(abs(t['entry_price']-t['sl'])/.0001+1e-8>=params['min_sl_pips'] for t in trades)
    assert all(abs(t['tp']-t['entry_price'])/abs(t['entry_price']-t['sl'])+1e-8>=1 for t in trades)
    contexts={x['attempt_id']:x for x in journal.contexts}
    assert len(contexts)==len(journal.contexts)
    for context in contexts.values():
        if policy!='off':
            assert context['context']['opposite_extreme_breached']
        if policy=='inside':
            assert context['context']['close_back_inside_range']
    balance,previous_close=10000.,None
    budget_trades=[]
    for t in sorted(trades,key=lambda t:t['close_time']):
        assert previous_close is None or previous_close<=t['open_time']
        budget_trades.append(dict(t,net_r=t['pnl']/(balance*.005)))
        balance+=t['pnl']
        previous_close=t['close_time']
        assert contexts[t['attempt_id']]['setup_id']==t['setup_id']
    assert abs(balance-engine.execution.get_account_balance())<1e-7
    windows={'2017_2019':(START,datetime(2020,1,1)),
        '2020_2025':(datetime(2020,1,1),datetime(2026,1,1)),
        '2026_to_july14':(datetime(2026,1,1),END)}
    windows.update({str(y):(datetime(y,1,1),min(datetime(y+1,1,1),END)) for y in range(2017,2027)})
    result=dict(metrics=metrics(trades),budget_metrics=metrics(budget_trades),
        windows={k:metrics([t for t in trades if a<=t['open_time'] and t['close_time']<b])
                 for k,(a,b) in windows.items()},
        directions={d:metrics([t for t in trades if t['direction']==d]) for d in ('BUY','SELL')},
        ending_balance=balance,growth_pct=(balance/10000-1)*100,
        equity_dd_pct=engine.execution.max_equity_drawdown_pct,final_exposure=final,
        rejected=dict(Counter(r['reason'] for r in journal.rows if r['event']=='REJECTED')),
        accepted_orders=len(journal.contexts),audit=dict(getattr(strategy,'audit',{})),
        minimum_filled_stop_pips=min((abs(t['entry_price']-t['sl'])/.0001 for t in trades),default=None),
        warmup_bars=dict(warmup),start=start,end=end)
    assert len(trades)+len(final)+sum(result['rejected'].values())==result['accepted_orders']
    return result,trades,journal.contexts


def main():
    logging.disable(logging.CRITICAL)
    OUT.mkdir(parents=True,exist_ok=True)
    assert not (OUT/'manifest.json').exists(),'Use a new output directory.'
    params=settings()
    files={s:paths_for(s) for s in SOURCES}
    previous=json.loads((PREVIOUS/'manifest.json').read_text())
    assert params==previous['params'],'Current GBP settings changed.'
    code=['research_candle_gbpusd_recovery.py','research_candle_gbpusd_review.py',
        'research_candle_usdjpy_corrected.py','research_ema_fib_review.py',
        'analyze_icmarkets_replay.py','strategies/candle_confirmation.py',
        'strategies/candle_confirmation_tracking.py','backtest_engine.py','engine.py',
        'models.py','config.py','live_config.py','execution/simulated_execution.py',
        'risk/risk_manager.py','risk/validation.py','data/historical_loader.py','utils/warmup.py']
    manifest=dict(start=START,end=END,load_start=LOAD,params=params,risk_pct=.005,
        policies={'off':'Current unchanged GBP strategy',
            'touch':'Opposite engulf extreme touched since setup, by or on the signal bar',
            'inside':'Same touch requirement plus signal close strictly inside engulf range'},
        selection='No parameter search or production selection; rules fixed before replay.',
        code_hashes={p:file_hash(ROOT/p) for p in code},
        input_hashes={str(p):file_hash(p) for paths in files.values() for p in paths},
        metadata_hashes={str(metadata_path(p)):file_hash(metadata_path(p))
            for paths in files.values() for p in paths if metadata_path(p).exists()},
        earlier_manifest_sha256=file_hash(PREVIOUS/'manifest.json'))
    assert manifest['input_hashes']==previous['input_hashes']
    write_json(OUT/'manifest.json',manifest)
    results,controls=[],[]
    def run(bars,source,policy,spread=.2,start=START,end=END,window='full'):
        t0=time.monotonic()
        r,ts,contexts=replay(bars,params,policy,spread,start,end)
        r.update(source=source,policy=policy,spread_pips=spread,window=window,seconds=time.monotonic()-t0)
        name=f'{source}_{policy}_spread{spread:g}_{window}'
        write_json(OUT/f'{name}_trades.json',ts)
        write_json(OUT/f'{name}_contexts.json',contexts)
        results.append(r)
        write_json(OUT/'results.json',results)
        print(json.dumps(dict(job=name,metrics=r['metrics'],growth=r['growth_pct'],seconds=r['seconds'])),flush=True)
        return r,ts
    for source,paths in files.items():
        bars=load_and_merge(paths,start=LOAD,end=END)
        for policy in POLICIES:
            r,ts=run(bars,source,policy)
            if policy=='off':
                old=json.loads((PREVIOUS/f'{source}_current_spread0.2_trades.json').read_text())
                assert json.loads(json.dumps(ts,default=str))==old,'Baseline no longer matches the previous review.'
                plain,plain_ts,_=replay(bars,params,plain=True)
                assert plain_ts==ts and plain['final_exposure']==r['final_exposure']
                controls.append(dict(source=source,previous_trade_fields_match=True,plain_production_matches=True))
                write_json(OUT/'controls.json',controls)
        if source=='mt5_icmarkets_utc':
            for spread in (1.,2.):
                for policy in POLICIES:
                    run(bars,source,policy,spread)
            for year in (2020,2022,2024):
                start,end=datetime(year,7,1),datetime(year+2,7,1)
                load_start=start-timedelta(days=warmup_days([(CandleConfirmationStrategy(**params),['GBPUSD'])]))
                fold_bars=[b for b in bars if load_start<=b.timestamp and bar_close_time(b)<=end]
                for policy in POLICIES:
                    run(fold_bars,source,policy,start=start,end=end,window=f'cold_{year}')
        del bars
    assert all(file_hash(ROOT/p)==h for p,h in manifest['code_hashes'].items())
    assert all(file_hash(p)==h for p,h in manifest['input_hashes'].items())
    assert all(file_hash(p)==h for p,h in manifest['metadata_hashes'].items())
    write_json(OUT/'complete.json',dict(research_replays=len(results),baseline_controls=len(controls),hashes_match=True))


if __name__=='__main__':
    main()
