"""Reproduce the 14 July Failed2 entry with 50 versus 61 warm-up daily bars."""
from collections import defaultdict
from datetime import datetime, timedelta
import json
import logging

from analyze_icmarkets_replay import MemoryJournal
from backtest_engine import BacktestEngine
from data.historical_loader import load_and_merge, bar_close_time
from data.histdata_provenance import file_hash, write_json
from research_failed2_review import OUT, paths_for, settings
from strategies.failed2 import Failed2Strategy


def main():
    logging.disable(logging.CRITICAL)
    start=datetime(2026,7,14,14,48,58)
    end=datetime(2026,7,14,15,15)
    _,paths=paths_for('mt5_icmarkets_utc')
    bars=load_and_merge(paths,start=start-timedelta(days=180),end=end)
    before=defaultdict(list)
    active=[]
    for b in bars:
        if bar_close_time(b)<=start:
            before[b.timeframe].append(b)
        elif bar_close_time(b)<=end:
            active.append(b)
    variants=[]
    rank={'M5':0,'H1':1,'H4':2,'D1':3}
    for days in (50,61):
        s=Failed2Strategy(**settings())
        e=BacktestEngine()
        e.add_strategy(s,['USTEC'])
        journal=MemoryJournal()
        e.event_engine.trade_journal=journal
        counts={'D1':days,'H4':100,'H1':100,'M5':250}
        warmup=[b for tf,n in counts.items() for b in before[tf][-n:]]
        warmup.sort(key=lambda b:(bar_close_time(b),rank[b.timeframe]))
        for b in warmup:
            e.event_engine.warmup_bar(b)
        e.execution.configure_timeframes(active)
        for b in active:
            e.process_bar(b)
        variants.append(dict(daily_warmup=days,rank=s._d1_range_percentile['USTEC'],
            blocked=s._d1_range_blocked['USTEC'],trend=s._trend_direction('USTEC','d1_ema'),
            events=journal.rows,ending_exposure=e.execution.get_open_positions()))
    signals=[r for r in variants[0]['events'] if r['event']=='SIGNAL']
    assert len(signals)==1 and signals[0]['signal_time']=='2026-07-14T15:05:00'
    assert abs(signals[0]['entry_price']-29649.4)<1e-6
    assert abs(signals[0]['stop_loss']-29360.8)<1e-6
    assert abs(signals[0]['take_profit']-30803.8)<1e-6
    assert variants[0]['rank']==31/49 and not variants[0]['blocked']
    assert variants[1]['rank']==.7 and variants[1]['blocked']
    assert variants[1]['events']==[]
    assert all(v['trend']=='BUY' for v in variants)
    write_json(OUT/'restart_reproduction.json',dict(start_utc=start,end_utc=end,variants=variants,
        journal_ticket='1807793687',logged_range_rank=31/49,
        log_file='logs/trading_20260715_065207.log',log_start_line=1,log_entry_lines=[68,69],
        code_sha256=file_hash('strategies/failed2.py'),data_hashes={p:file_hash(p) for p in paths},
        note='Current-code isolated reconstruction matches the historical signal time and entry/SL/TP with 50 D1 bars. '
             '61 D1 bars blocks it while trend remains BUY. This does not reconstruct other strategies or exact broker fills.'))
    print(json.dumps([{k:v[k] for k in ('daily_warmup','rank','blocked','trend')} for v in variants],indent=2))


if __name__=='__main__':
    main()
