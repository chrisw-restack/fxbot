"""Read-only EmaFibRunning audit and sequential fixed-parameter source replays."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import inspect
import hashlib
import json
import logging
from pathlib import Path
import subprocess
import time

from backtest_engine import BacktestEngine
from data.historical_loader import load_and_merge, bar_close_time
from data.histdata_provenance import file_hash, metadata_path, write_json
from research_ema_fib_review import paths_for, metrics, PERIODS
from research_ema_fib_running_baseline import EmaFibRunningStrategy, REVISION, SOURCE
import config

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'output/ema_fib_running_review_20260925'
SOURCES = ('dukascopy','histdata','mt5_icmarkets_utc')


def settings():
    # Preserve the reviewed settings after retirement from the DEMO suite.
    s = EmaFibRunningStrategy(fib_entry=.786, fib_tp=2.5, fractal_n=2,
        min_swing_pips=30, ema_sep_pct=0., cooldown_bars=0,
        invalidate_swing_on_loss=True, blocked_hours=(*range(20,24),*range(0,9)))
    symbols = ['EURUSD','GBPUSD','AUDUSD','NZDUSD','USDJPY','USDCAD','USDCHF']
    params = {k:getattr(s,k) for k in inspect.signature(EmaFibRunningStrategy).parameters}
    params['blocked_hours'] = sorted(params['blocked_hours'])
    return params,symbols


class ObservedRunning(EmaFibRunningStrategy):
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.execution = None
        self.audit = Counter()
        self.examples = {}
        self.accepted = {}

    def note(self,key,**data):
        self.audit[key] += 1
        if len(self.examples.setdefault(key,[])) < 3:
            self.examples[key].append(deepcopy(data))

    def snapshot(self,symbol):
        return self._pending_anchor_low.get(symbol),self._pending_anchor_high.get(symbol)

    def generate_signal(self,event):
        symbol = event.symbol
        pending = self._pending_entry.get(symbol)
        occupied = self.execution.get_open_positions() if self.execution else []
        low_bar,high_bar = self._fractal_low_bar.get(symbol),self._fractal_high_bar.get(symbol)
        signal = super().generate_signal(event)
        if event.timeframe == 'H1':
            if pending is not None and event.low <= pending <= event.high:
                actual = [p for p in occupied if p.get('open_time') is None]
                if actual:
                    self.note('heuristic_consumed_unfilled_order',time=event.timestamp,local_entry=pending,orders=actual)
            window = list(self._h1_window[symbol])
            if len(window) == self._window_size:
                closes = [b.close for b in window[self.fractal_n:]]
                for direction,old,new,actual,expected in (
                    ('BUY',low_bar,self._fractal_low_bar[symbol],self._running_high[symbol],max(closes)),
                    ('SELL',high_bar,self._fractal_high_bar[symbol],self._running_low[symbol],min(closes))):
                    if old != new and actual is not None and abs(actual-expected)>1e-12:
                        self.note('new_anchor_omits_known_close_extreme',time=event.timestamp,direction=direction,
                                  actual=actual,expected_since_anchor=expected)
        if signal and signal.direction != 'CANCEL' and occupied:
            self.note('proposal_while_slot_occupied',time=event.timestamp,anchor=self.snapshot(symbol),orders=occupied)
        return signal

    def notify_order_accepted(self,signal,ticket,details=None):
        self.accepted[ticket] = self.snapshot(signal.symbol)
        self.note('accepted_orders',ticket=ticket,time=signal.timestamp)

    def notify_order_cancelled(self,order):
        self.accepted.pop(order['ticket'],None)
        self.note('confirmed_cancellations',ticket=order['ticket'])

    def notify_trade_closed(self,trade):
        symbol = trade['symbol']
        origin = self.accepted.pop(trade['ticket'],None)
        if trade['result'] == 'LOSS':
            super().notify_loss(symbol)
            used = self._used_fractal_low[symbol],self._used_fractal_high[symbol]
            # Only compare the direction-relevant anchor with this accepted trade.
            slot = 0 if trade['direction']=='BUY' else 1
            if origin is not None and origin[slot] != used[slot]:
                self.note('loss_invalidated_wrong_anchor',ticket=trade['ticket'],time=trade['close_time'],
                          origin=origin,used=used,direction=trade['direction'])
        elif trade['result'] == 'WIN':
            super().notify_win(symbol)
        if self._pending_entry.get(symbol) is not None:
            self.note('close_left_local_pending',ticket=trade['ticket'],time=trade['close_time'],
                      local_pending=self._pending_entry[symbol])


def replay(bars,symbol,params,start,end,spread=None,observed=True):
    engine = BacktestEngine(spread_pips=config.BACKTEST_SPREAD_PIPS if spread is None else spread)
    s = (ObservedRunning if observed else EmaFibRunningStrategy)(**params)
    if observed:
        s.execution = engine.execution
    engine.add_strategy(s,[symbol])
    trades = engine.replay(bars,start_date=start,end_date=end)
    return trades,engine,s


def main():
    logging.disable(logging.CRITICAL)
    OUT.mkdir(parents=True,exist_ok=True)
    params,symbols = settings()
    files = {s:{src:paths_for(src,s) for src in SOURCES} for s in symbols}
    code = ['research_ema_fib_running_review.py','research_ema_fib_running_baseline.py','strategies/ema_fib_running.py','engine.py',
            'backtest_engine.py','execution/simulated_execution.py','risk/risk_manager.py',
            'portfolio/portfolio_manager.py','data/historical_loader.py','data/histdata_provenance.py',
            'research_ema_fib_review.py','config.py','live_config.py']
    manifest = dict(created_utc=datetime.now(timezone.utc),revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        workers=1,parameters=params,symbols=symbols,frozen_strategy_revision=REVISION,
        frozen_strategy_source_sha256=hashlib.sha256(SOURCE.encode()).hexdigest(),
        code_hashes={p:file_hash(ROOT/p) for p in code},
        input_hashes={p:file_hash(p) for sources in files.values() for paths in sources.values() for p in paths},
        sidecar_hashes={str(metadata_path(p)):file_hash(metadata_path(p)) for sources in files.values()
                       for paths in sources.values() for p in paths if metadata_path(p).exists()},
        assumptions=dict(initial_balance=10000,risk_pct=config.RISK_PCT,
            spread_pips={s:config.BACKTEST_SPREAD_PIPS[s] for s in symbols},commission_per_lot=config.COMMISSION_PER_LOT,
            execution_timeframe='M5',warmup_days=180,swaps=False,variable_spreads=False,extra_slippage=False,
            shared_portfolio=False,daily_loss_gate=False,news=False,optimization=False,
            aggregate='Independent pair net R, not pooled account returns',cutoff='2026-07-15 00:00 UTC',
            usdcad_broker_start='2025-01-01 22:00 UTC; excluded from 2020-2025'),periods=PERIODS)
    write_json(OUT/'manifest.json',manifest)
    results,groups,controls = [],{},[]
    for symbol in symbols:
        for source,paths in files[symbol].items():
            print(f'Loading {source} {symbol}',flush=True)
            start = datetime(2025,1,1) if symbol=='USDCAD' and source=='mt5_icmarkets_utc' else datetime(2019,7,1)
            bars = load_and_merge(paths,start=start,end=PERIODS[-1][2])
            jobs = [(label,a,b,None) for label,a,b in PERIODS if not
                    (symbol=='USDCAD' and source=='mt5_icmarkets_utc' and label=='2020_2025')]
            if not (symbol=='USDCAD' and source=='mt5_icmarkets_utc'):
                jobs.append(('spread_1pip',PERIODS[0][1],PERIODS[0][2],1.0))
            if symbol=='USDCAD':
                jobs.append(('2025_h2',datetime(2025,7,1),datetime(2026,1,1),None))
            for label,a,b,spread in jobs:
                selected = [e for e in bars if e.timestamp >= a-timedelta(days=180) and bar_close_time(e)<=b]
                for tf in ('M5','H1','D1'):
                    assert min(e.timestamp for e in selected if e.timeframe==tf)<=a-timedelta(days=173)
                began = time.monotonic()
                ts,engine,s = replay(selected,symbol,params,a,b,spread)
                if source=='dukascopy' and symbol in ('EURUSD','AUDUSD') and label=='2020_2025':
                    plain,pe,_ = replay(selected,symbol,params,a,b,spread,observed=False)
                    assert ts==plain and engine.execution.get_open_positions()==pe.execution.get_open_positions()
                    controls.append(dict(source=source,symbol=symbol,all_trade_fields_match=True,ending_exposure_matches=True))
                result = dict(source=source,symbol=symbol,label=label,start=a,end=b,metrics=metrics(ts),
                    audit=dict(s.audit),examples=s.examples,open_exposure=engine.execution.get_open_positions(),
                    bars=dict(Counter(e.timeframe for e in selected)),seconds=time.monotonic()-began)
                name = f'{source}_{symbol}_{label}'
                write_json(OUT/(name+'.json'),result)
                write_json(OUT/(name+'_trades.json'),ts)
                results.append(result)
                groups.setdefault((source,label),[]).extend(ts)
                if symbol!='USDCAD':
                    groups.setdefault((source,'six_'+label),[]).extend(ts)
                print(json.dumps(dict(job=name,metrics=result['metrics'],audit=result['audit'],seconds=result['seconds'])),flush=True)
                write_json(OUT/'results.json',results)
            del bars
    aggregate = [dict(source=src,label=label,metrics=metrics(ts),
        years={str(y):metrics([t for t in ts if t['close_time'].year==y]) for y in sorted({t['close_time'].year for t in ts})})
        for (src,label),ts in groups.items()]
    write_json(OUT/'aggregate.json',aggregate)
    write_json(OUT/'observer_controls.json',controls)
    assert all(file_hash(ROOT/p)==sha for p,sha in manifest['code_hashes'].items())
    write_json(OUT/'complete.json',dict(replays=len(results),observer_controls=len(controls),code_hashes_match=True))
    print('Completed Running source and cost comparison.',flush=True)


if __name__=='__main__':
    main()
