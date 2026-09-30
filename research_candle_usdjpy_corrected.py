"""Fixed Candle parameters after attribution/stop corrections, one worker.

    .venv/Scripts/python.exe research_candle_usdjpy_corrected.py

No parameter selection, no forward-demo prices, and no reuse of old outputs.
"""
from collections import Counter
from datetime import datetime
import json
import logging
from pathlib import Path
import time

from analyze_icmarkets_replay import MemoryJournal
from backtest_engine import BacktestEngine
from data.historical_loader import load_and_merge, bar_close_time
from data.histdata_provenance import file_hash, metadata_path, write_json
from research_candle_usdjpy_baseline import CandleConfirmationStrategy as FrozenCandle, SOURCE_SHA256, REVISION
from research_candle_usdjpy_review import settings, paths_for, SOURCES
from research_ema_fib_review import metrics
from strategies.candle_confirmation import CandleConfirmationStrategy

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'output/candle_usdjpy_corrected_20260930'
START, END = datetime(2017,1,1),datetime(2026,7,15)
LOAD = datetime(2016,1,1)


class TrackingOnly(CandleConfirmationStrategy):
    """Isolate order attribution from the executable stop correction."""
    def generate_signal(self,event):
        signal = super().generate_signal(event)
        if signal:
            signal.min_stop_distance = None
        return signal


class ResearchJournal(MemoryJournal):
    def __init__(self,strategy):
        super().__init__()
        self.strategy = strategy
        self.contexts = []

    def log_order_placed(self,signal,ticket,context=None,execution_details=None):
        super().log_order_placed(signal,ticket,context,execution_details)
        self.contexts.append(dict(ticket=ticket,setup_id=signal.setup_id,attempt_id=signal.attempt_id,
            signal_time=signal.timestamp,minimum=signal.min_stop_distance,context=context))


def replay(bars,cls,params):
    s = cls(**params)
    e = BacktestEngine(spread_pips=.2)
    e.add_strategy(s,['USDJPY'])
    journal = ResearchJournal(s)
    e.event_engine.trade_journal = journal
    warmup = Counter(b.timeframe for b in bars if bar_close_time(b)<=START)
    # Identical sufficient warmup for frozen, tracking-only, and corrected.
    assert all(warmup[tf]>=n for tf,n in CandleConfirmationStrategy(**params).warmup_requirements().items())
    trades = e.replay(bars,start_date=START,end_date=END)
    balance = 10000.
    budget_trades = []
    for t in sorted(trades,key=lambda t:t['close_time']):
        budget_trades.append(dict(t,net_r=t['pnl']/(balance*.005)))
        balance += t['pnl']
    assert abs(balance-e.execution.get_account_balance())<1e-7
    final = e.execution.get_open_positions()
    min_sl = min((abs(t['entry_price']-t['sl'])/.01 for t in trades),default=None)
    if cls is CandleConfirmationStrategy:
        assert min_sl is None or min_sl+1e-8>=params['min_sl_pips']
        assert all(t['setup_id'] and t['attempt_id'] for t in trades)
        assert len(getattr(s,'_orders',{}))==len(final)
        assert not s._proposals
    windows = {'2020_2025':(datetime(2020,1,1),datetime(2026,1,1)),
               '2026_to_july14':(datetime(2026,1,1),END)}
    windows.update({str(y):(datetime(y,1,1),min(datetime(y+1,1,1),END)) for y in range(2017,2027)})
    result = dict(metrics=metrics(trades),budget_metrics=metrics(budget_trades),
        windows={k:metrics([t for t in trades if a<=t['open_time'] and t['close_time']<b])
                 for k,(a,b) in windows.items()},
        ending_balance=balance,account_growth_pct=(balance/10000-1)*100,
        max_equity_drawdown_pct=e.execution.max_equity_drawdown_pct,
        final_exposure=final,minimum_actual_stop_pips=min_sl,warmup_bars=dict(warmup),
        rejected=dict(Counter(r['reason'] for r in journal.rows if r['event']=='REJECTED')),
        events=dict(Counter(r['event'] for r in journal.rows)))
    return result,trades,journal.contexts


def comparable(trades):
    attribution = {'setup_id','attempt_id','min_stop_distance'}
    return [{k:v for k,v in t.items() if k not in attribution} for t in trades]


def main():
    logging.disable(logging.CRITICAL)
    OUT.mkdir(parents=True,exist_ok=True)
    assert not (OUT/'manifest.json').exists(), 'Use a new output directory for a new run.'
    params = settings()
    files = {src:paths_for(src) for src in SOURCES}
    code = ['research_candle_usdjpy_corrected.py','research_candle_usdjpy_baseline.py',
            'strategies/candle_confirmation.py','strategies/candle_confirmation_tracking.py',
            'models.py','risk/risk_manager.py','risk/validation.py','engine.py','backtest_engine.py',
            'execution/simulated_execution.py','data/historical_loader.py','utils/warmup.py',
            'research_candle_usdjpy_review.py','research_ema_fib_review.py','config.py','live_config.py']
    manifest = dict(start=START,end=END,load_start=LOAD,params=params,spread_pips=.2,risk_pct=.005,
        frozen_revision=REVISION,frozen_signal_source_sha256=SOURCE_SHA256,
        code_hashes={p:file_hash(ROOT/p) for p in code},
        input_hashes={str(p):file_hash(p) for paths in files.values() for p in paths},
        metadata_hashes={str(metadata_path(p)):file_hash(metadata_path(p))
            for paths in files.values() for p in paths if metadata_path(p).exists()})
    write_json(OUT/'manifest.json',manifest)
    results,controls = [],[]
    for src,paths in files.items():
        bars = load_and_merge(paths,start=LOAD,end=END)
        original_trades = None
        for name,cls in [('original',FrozenCandle),('tracking_only',TrackingOnly),('corrected',CandleConfirmationStrategy)]:
            t0 = time.monotonic()
            r,ts,contexts = replay(bars,cls,params)
            r.update(source=src,variant=name,seconds=time.monotonic()-t0)
            results.append(r)
            write_json(OUT/f'{src}_{name}_trades.json',ts)
            write_json(OUT/f'{src}_{name}_contexts.json',contexts)
            write_json(OUT/'results.json',results)
            if name=='original':
                original_trades = comparable(ts)
            elif name=='tracking_only':
                assert original_trades==comparable(ts), 'Tracking changed uninterrupted entry/exit decisions.'
                controls.append(dict(source=src,all_economic_trade_fields_match=True))
                write_json(OUT/'controls.json',controls)
            print(json.dumps(dict(source=src,variant=name,metrics=r['metrics'],
                                  growth=r['account_growth_pct'],rejected=r['rejected'],seconds=r['seconds'])),flush=True)
        del bars
    assert all(file_hash(ROOT/p)==h for p,h in manifest['code_hashes'].items())
    assert all(file_hash(p)==h for p,h in manifest['input_hashes'].items())
    assert all(file_hash(p)==h for p,h in manifest['metadata_hashes'].items())
    write_json(OUT/'complete.json',dict(replays=len(results),controls=len(controls),hashes_match=True))


if __name__=='__main__':
    main()
