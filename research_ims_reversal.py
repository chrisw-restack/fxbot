"""Sequential, pre-cutoff IMS Reversal audit and parameter research.

Never imports MT5 or changes the demo configuration. Research observations use
the current engine, M5 fills, and at most 2026-07-14 historical candles.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import config
from backtest_engine import BacktestEngine
from data.historical_loader import find_csv, load_and_merge, bar_close_time
from research_ims_baseline import ImsReversalStrategy

OUT = Path('output/ims_reversal_review_20260918')
CUTOFF = datetime(2026, 7, 15)
BASE = dict(tf_htf='H4', tf_ltf='M15', fractal_n=1, ltf_fractal_n=2,
            htf_lookback=30, entry_mode='pending', tp_mode='htf_pct', htf_tp_pct=.5,
            zone_pct=.5, cooldown_bars=0, blocked_hours=(*range(12), *range(17,24)),
            ema_fast=20, ema_slow=50, ema_sep=.001, sl_anchor='swing',
            sl_buffer_pips=0., max_losses_per_bias=1, pip_sizes=dict(config.PIP_SIZE))
VARIANTS = {
    'baseline': {},
    'target_40': {'htf_tp_pct': .4},
    'target_60': {'htf_tp_pct': .6},
    'fixed_2R': {'tp_mode': 'rr', 'rr_ratio': 2.},
    'fixed_3R': {'tp_mode': 'rr', 'rr_ratio': 3.},
    'zone_65': {'zone_pct': .65},
    'zone_75': {'zone_pct': .75},
    'stop_buffer_1pip': {'sl_buffer_pips': 1.},
    'stop_buffer_2pips': {'sl_buffer_pips': 2.},
    'ltf_fractal_1': {'ltf_fractal_n': 1},
    'ltf_fractal_3': {'ltf_fractal_n': 3},
    'ema_sep_005pct': {'ema_sep': .0005},
    'ema_sep_020pct': {'ema_sep': .002},
    'research_retire_loss': {'_retire_loss': True},
    'research_pending_lifecycle': {'_pending_lifecycle': True},
    'research_both': {'_retire_loss': True, '_pending_lifecycle': True},
}


class AuditedIMS(ImsReversalStrategy):
    """Record setup lifecycle problems without altering production decisions."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.audit = Counter()
        self.retired = set()
        self.lost = set()
        self.signal_context = {}

    def reset(self):
        super().reset()
        self.audit.clear()
        self.retired.clear()
        self.lost.clear()
        self.signal_context.clear()

    def key(self, symbol):
        bias = self._htf_bias.get(symbol)
        return (symbol, bias['direction'], bias['_swing_ts']) if bias else None

    def _expire_bias(self, symbol, bar):
        key = self.key(symbol)
        if key:
            self.retired.add(key)
        return super()._expire_bias(symbol, bar)

    def notify_loss(self, symbol):
        key = self.key(symbol)
        if key:
            self.lost.add(key)
        return super().notify_loss(symbol)

    def generate_signal(self, event):
        prior = self.key(event.symbol)
        signal = super().generate_signal(event)
        current = self.key(event.symbol)
        if current and current != prior and current in self.retired:
            self.audit['expired_bias_reactivated'] += 1
        if current and current != prior and current in self.lost:
            self.audit['loss_retired_bias_reactivated'] += 1
        if signal is not None and signal.direction != 'CANCEL':
            self.audit['entry_proposals'] += 1
            if current in self.retired:
                self.audit['proposals_on_previously_expired_bias'] += 1
            if current in self.lost:
                self.audit['proposals_on_previously_losing_bias'] += 1
            self.signal_context[event.timestamp.isoformat()] = {
                'bias_key': str(current), 'previously_losing_bias': current in self.lost,
                'previously_expired_bias': current in self.retired,
                'entry': signal.entry_price, 'sl': signal.stop_loss, 'tp': signal.take_profit,
            }
        return signal


class ResearchLifecycleIMS(AuditedIMS):
    """Isolated experiments, deliberately absent from demo and strategy registry.

    Retirement applies to the active bias notified by the existing callback.
    It does not solve attribution when an older trade closes after a bias change.
    """
    def __init__(self, retire_loss=False, pending_lifecycle=False, **kwargs):
        super().__init__(**kwargs)
        self.retire_loss=retire_loss
        self.pending_lifecycle=pending_lifecycle
        self.submitted_targets={}
        self._cancel_target=None

    def reset(self):
        super().reset()
        self.submitted_targets.clear()
        self._cancel_target=None

    def _find_bullish_htf(self, bars, fn, n, lookback_start):
        result=super()._find_bullish_htf(bars,fn,n,lookback_start)
        key=(bars[-1].symbol,result['direction'],result['_swing_ts']) if result else None
        return None if self.retire_loss and key in self.lost else result

    def _find_bearish_htf(self, bars, fn, n, lookback_start):
        result=super()._find_bearish_htf(bars,fn,n,lookback_start)
        key=(bars[-1].symbol,result['direction'],result['_swing_ts']) if result else None
        return None if self.retire_loss and key in self.lost else result

    def _get_htf_tp_price(self, bias):
        if self._cancel_target is not None:
            return self._cancel_target
        return super()._get_htf_tp_price(bias)

    def _on_ltf_bar(self,symbol,bar):
        bias=self._htf_bias[symbol]
        target=self.submitted_targets.get(symbol)
        pending=self.pending_lifecycle and self.entry_mode=='pending' and self._ltf_signal_fired[symbol]
        if pending and bias is not None and target is not None:
            reached=(bias['direction']=='BUY' and bar.low<=target) or (bias['direction']=='SELL' and bar.high>=target)
            if reached:
                self._update_ltf_atr(symbol,bar)
                return self._expire_bias(symbol,bar)
            self._cancel_target=target
        try:
            return super()._on_ltf_bar(symbol,bar)
        finally:
            self._cancel_target=None

    def generate_signal(self,event):
        signal=super().generate_signal(event)
        if signal is not None and signal.direction!='CANCEL':
            distance=abs(signal.entry_price-signal.stop_loss)
            self.submitted_targets[event.symbol]=signal.take_profit if signal.take_profit is not None else (
                signal.entry_price+(1 if signal.direction=='BUY' else -1)*self.rr_ratio*distance)
        return signal


def metrics(trades):
    rs=[x['net_r'] for x in trades]
    pos=sum(x for x in rs if x>0); neg=-sum(x for x in rs if x<0)
    cum=peak=drawdown=0.; w=l=maxw=maxl=0
    for r in rs:
        cum+=r; peak=max(peak,cum); drawdown=max(drawdown,peak-cum)
        w=w+1 if r>0 else 0; l=l+1 if r<0 else 0
        maxw=max(maxw,w); maxl=max(maxl,l)
    n=len(rs)
    return dict(trades=n, win_rate=100*sum(r>0 for r in rs)/n if n else None,
                total_r=sum(rs), gross_r=sum(x['gross_r'] for x in trades),
                profit_factor=pos/neg if neg else None,
                expectancy=sum(rs)/n if n else None, max_dd_r=drawdown,
                max_win_streak=maxw, max_loss_streak=maxl,
                pnl=sum(x['pnl'] for x in trades))


def paths_for(source, symbol):
    files=[]
    for tf in ['M5','M15','H4']:
        found=find_csv(symbol,tf,data_source=source)
        if not found:
            raise ValueError(f'Missing {source} {symbol} {tf}')
        files.extend(found)
    return files


def run(bars, source, symbol, variant, start, end, spread=None):
    if end>CUTOFF:
        raise ValueError('The EURUSD forward trial is protected after 2026-07-14')
    params=BASE | VARIANTS[variant]
    retire=params.pop('_retire_loss',False); pending=params.pop('_pending_lifecycle',False)
    strategy=ResearchLifecycleIMS(retire_loss=retire,pending_lifecycle=pending,**params) if retire or pending else AuditedIMS(**params)
    engine=BacktestEngine(initial_balance=10000, rr_ratio=params.get('rr_ratio',2.5),
                          spread_pips=spread if spread is not None else config.BACKTEST_SPREAD_PIPS)
    engine.add_strategy(strategy,[symbol])
    began=time.monotonic()
    trades=engine.replay(bars,start_date=start,end_date=end)
    result=dict(source=source,symbol=symbol,variant=variant,start=start.isoformat(),end=end.isoformat(),
                parameters=params,metrics=metrics(trades),audit=dict(strategy.audit),
                research_flags=dict(retire_loss=retire,pending_lifecycle=pending),
                execution_assumptions=dict(spread_pips=spread if spread is not None else config.BACKTEST_SPREAD_PIPS,
                                           risk_pct=config.RISK_PCT, default_commission_per_lot=config.COMMISSION_PER_LOT,
                                           daily_loss_gate=False, swaps=False),
                ending_balance=engine.execution.get_account_balance(),
                max_equity_dd_pct=engine.execution.max_equity_drawdown_pct,
                open_exposure=len(engine.execution.get_open_positions()),seconds=time.monotonic()-began)
    result['direction']={direction:metrics([t for t in trades if t['direction']==direction]) for direction in ['BUY','SELL']}
    name=f'{source}_{symbol}_{variant}_{start:%Y%m%d}_{end:%Y%m%d}'
    if spread is not None: name += f'_spread{spread}'
    (OUT/f'{name}.json').write_text(json.dumps(result,indent=2,default=str))
    (OUT/f'{name}_trades.json').write_text(json.dumps(trades,indent=2,default=str))
    (OUT/f'{name}_signals.json').write_text(json.dumps(strategy.signal_context,indent=2,default=str))
    print(json.dumps({k:result[k] for k in ['source','symbol','variant','start','end','metrics','audit','seconds']}),flush=True)
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',default='dukascopy',choices=['dukascopy','histdata','mt5_icmarkets_utc'])
    parser.add_argument('--symbol',default='EURUSD')
    parser.add_argument('--start',default='2016-01-01')
    parser.add_argument('--end',default='2020-01-01')
    parser.add_argument('--variants',nargs='+',default=['baseline'],choices=list(VARIANTS))
    parser.add_argument('--spread',type=float)
    parser.add_argument('--workflow',action='store_true')
    args=parser.parse_args()
    if args.workflow:
        workflow(args.source,args.symbol)
        return
    start=datetime.fromisoformat(args.start); end=datetime.fromisoformat(args.end)
    if end>CUTOFF: parser.error('End must be <=2026-07-15, exclusive')
    OUT.mkdir(parents=True,exist_ok=True)
    files=paths_for(args.source,args.symbol)
    print(f'Loading {args.source} {args.symbol}: M5 fills, H4/M15 signals; one worker',flush=True)
    bars=load_and_merge(files,start=start-timedelta(days=180),end=end)
    counts=Counter(b.timeframe for b in bars)
    print(f'Loaded {len(bars):,} candles {dict(counts)}',flush=True)
    manifest=dict(source=args.source,files=[dict(path=f,sha256=hashlib.sha256(Path(f).read_bytes()).hexdigest()) for f in files],
                  first=min(b.timestamp for b in bars),last=max(bar_close_time(b) for b in bars),counts=dict(counts),
                  strategy_sha256=hashlib.sha256(Path('strategies/ims_reversal.py').read_bytes()).hexdigest())
    (OUT/f'manifest_{args.source}_{args.symbol}_{start:%Y%m%d}_{end:%Y%m%d}.json').write_text(json.dumps(manifest,indent=2,default=str))
    for name in args.variants:
        run(bars,args.source,args.symbol,name,start,end,args.spread)


def workflow(source,symbol):
    """Rolling training-only selection, with results persisted after every run."""
    OUT.mkdir(parents=True,exist_ok=True)
    files=paths_for(source,symbol)
    print(f'Loading {source} {symbol} workflow, one worker',flush=True)
    all_bars=load_and_merge(files,start=datetime(2015,7,1),end=CUTOFF)
    manifest=dict(source=source,files=[dict(path=f,sha256=hashlib.sha256(Path(f).read_bytes()).hexdigest()) for f in files],
                  first=min(b.timestamp for b in all_bars),last=max(bar_close_time(b) for b in all_bars),
                  counts=dict(Counter(b.timeframe for b in all_bars)),
                  strategy_sha256=hashlib.sha256(Path('strategies/ims_reversal.py').read_bytes()).hexdigest())
    (OUT/f'manifest_{source}_workflow.json').write_text(json.dumps(manifest,indent=2,default=str))
    selected=[]
    def obtain(variant,start,end,bars):
        # Recompute on later invocations: saved results may belong to different
        # engine, cost, parameter, or data revisions.
        return run(bars,source,symbol,variant,start,end)
    for year in [2020,2022,2024]:
        start=datetime(year-4,1,1);end=datetime(year,1,1);test_end=datetime(year+2,1,1)
        train_bars=[b for b in all_bars if start-timedelta(days=180)<=b.timestamp<end]
        if source=='dukascopy':
            training=[obtain(v,start,end,train_bars) for v in VARIANTS if not v.startswith('research_')]
            eligible=[r for r in training if r['metrics']['trades']>=30 and (r['metrics']['profit_factor'] or 0)>=1.10]
            best=max(eligible,key=lambda r:(r['metrics']['total_r'],-r['metrics']['max_dd_r'])) if eligible else next(r for r in training if r['variant']=='baseline')
            choice=dict(year=year,variant=best['variant'],training_metrics=best['metrics'],threshold_passed=bool(eligible))
        else:
            selection=json.loads((OUT/'selection_dukascopy.json').read_text())
            choice=next(c for c in selection if c['year']==year).copy()
        print('SELECTION '+json.dumps(choice),flush=True)
        test_bars=[b for b in all_bars if end-timedelta(days=180)<=b.timestamp<test_end]
        choice['test']=obtain(choice['variant'],end,test_end,test_bars)['metrics']
        choice['baseline_test']=obtain('baseline',end,test_end,test_bars)['metrics']
        selected.append(choice)
        (OUT/f'selection_{source}.json').write_text(json.dumps(selected,indent=2))
    # Previously viewed recent data, never part of selection in this workflow.
    start=datetime(2026,1,1)
    recent=[b for b in all_bars if start-timedelta(days=180)<=b.timestamp<CUTOFF]
    for variant in dict.fromkeys(['baseline',selected[-1]['variant']]):
        obtain(variant,start,CUTOFF,recent)


if __name__=='__main__':
    logging.disable(logging.CRITICAL)
    main()
