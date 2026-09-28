"""Recheck the logged July entry against the corrected cold-start policy."""
from collections import defaultdict
from datetime import datetime, timedelta
import json
import logging

from analyze_icmarkets_replay import MemoryJournal
from backtest_engine import BacktestEngine
from data.historical_loader import load_and_merge, bar_close_time
from data.histdata_provenance import file_hash, write_json
from research_failed2_baseline import BaselineFailed2, REVISION
from research_failed2_corrections import OUT
from research_failed2_review import settings, paths_for
from strategies.failed2 import Failed2Strategy
from utils.warmup import warmup_counts


def main():
    logging.disable(logging.CRITICAL)
    start, end = datetime(2026,7,14,14,48,58), datetime(2026,7,14,15,15)
    _, paths = paths_for('mt5_icmarkets_utc')
    bars = load_and_merge(paths, start=start-timedelta(days=550), end=end)
    before, active = defaultdict(list), []
    for bar in bars:
        if bar_close_time(bar) <= start:
            before[bar.timeframe].append(bar)
        elif bar_close_time(bar) <= end:
            active.append(bar)
    results=[]
    production_counts=warmup_counts([(Failed2Strategy(**settings()), ['USTEC'])])
    for label, cls, daily in [('baseline_50', BaselineFailed2, 50),
                             ('corrected_50', Failed2Strategy, 50),
                             ('corrected_61', Failed2Strategy, 61),
                             ('corrected_startup', Failed2Strategy, production_counts['USTEC','D1']),
                             ('corrected_reference', Failed2Strategy, len(before['D1']))]:
        s=cls(**settings())
        e=BacktestEngine()
        e.add_strategy(s,['USTEC'])
        journal=MemoryJournal()
        e.event_engine.trade_journal=journal
        counts={'D1':daily,'H4':100,'H1':100,'M5':250}
        assert all(len(before[tf])>=n for tf,n in counts.items())
        warmup=[bar for tf,n in counts.items() for bar in before[tf][-n:]]
        rank={'M5':0,'H1':1,'H4':2,'D1':3}
        warmup.sort(key=lambda b:(bar_close_time(b), rank[b.timeframe]))
        for bar in warmup:
            e.event_engine.warmup_bar(bar)
        e.execution.configure_timeframes(active)
        for bar in active:
            e.process_bar(bar)
        results.append(dict(label=label, daily_bars=daily,
            rank=s._d1_range_percentile['USTEC'],
            filter_passes=s._passes_entry_filters('USTEC','BUY'),
            ema_fast=s._d1_ema_fast['USTEC'],ema_slow=s._d1_ema_slow['USTEC'],
            signals=[r for r in journal.rows if r['event']=='SIGNAL']))
    signal=results[0]['signals'][0]
    assert len(results[0]['signals'])==1 and signal['signal_time']=='2026-07-14T15:05:00'
    assert abs(signal['entry_price']-29649.4)<1e-6
    assert abs(signal['stop_loss']-29360.8)<1e-6
    assert abs(signal['take_profit']-30803.8)<1e-6
    assert all(not r['signals'] and not r['filter_passes'] for r in results[1:])
    assert results[3]['rank']==results[4]['rank']==.7
    write_json(OUT/'restart_validation.json',dict(variants=results,baseline_revision=REVISION,
        code_hashes={p:file_hash(p) for p in ('strategies/failed2.py','utils/warmup.py','validate_failed2_restart.py')},
        data_hashes={p:file_hash(p) for p in paths},
        note='Matches historical signal, not exact broker execution or shared-account conditions.'))
    print(json.dumps(results,default=str,indent=2))


if __name__=='__main__':
    main()
