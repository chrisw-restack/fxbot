"""Cost and fill-distance hypotheses after the fixed Candle USDJPY audit."""
from collections import Counter
from datetime import timedelta, datetime, timezone
import json
import logging
import time

from analyze_icmarkets_replay import MemoryJournal
from backtest_engine import BacktestEngine
from data.historical_loader import load_and_merge, bar_close_time
from data.histdata_provenance import file_hash, write_json
from research_candle_usdjpy_review import OUT, ROOT, START, END, settings, paths_for, replay
from research_ema_fib_review import metrics
from strategies.candle_confirmation import CandleConfirmationStrategy


def guarded_replay(bars, params):
    """Reject a future market fill below 8 pips before it enters the simulator.

    The normal rejection callback releases the proposal and subsequent bars replay
    normally. This is a research execution guard, not deletion of selected trades.
    """
    s = CandleConfirmationStrategy(**params)
    e = BacktestEngine(spread_pips=.2)
    e.add_strategy(s, ['USDJPY'])
    journal = MemoryJournal()
    e.event_engine.trade_journal = journal
    e.execution.configure_timeframes(bars)
    check = e.execution.check_fills
    rejected = []
    def guarded_check(bar):
        if bar.timeframe == 'M5':
            for ticket,pos in list(e.execution._pending.items()):
                available = pos.get('submitted_time')
                if pos['order_type'] == 'MARKET' and (available is None or bar.timestamp >= available):
                    fill = e.execution._entry_price(bar.open, bar.symbol, pos['direction'])
                    if abs(fill-pos['sl'])/.01 < 8-1e-9:
                        rejected.append(dict(ticket=ticket, time=bar.timestamp, fill=fill, sl=pos['sl']))
                        e.execution._rejected_orders.append(e.execution._pending.pop(ticket))
        return check(bar)
    e.execution.check_fills = guarded_check
    ts = e.replay(bars, start_date=START, end_date=END)
    result = dict(metrics=metrics(ts), final_exposure=e.execution.get_open_positions(),
        ending_balance=e.execution.get_account_balance(), max_equity_drawdown_pct=e.execution.max_equity_drawdown_pct,
        guarded_fill_rejections=rejected, rejection_reasons=dict(Counter(
            r['reason'] for r in journal.rows if r['event']=='REJECTED')),
        windows={f'fold_{y}_test':metrics([t for t in ts if datetime(y,7,1)<=t['open_time']
            and t['close_time']<datetime(y+2,7,1)]) for y in (2020,2022,2024)})
    return result,ts


def main():
    logging.disable(logging.CRITICAL)
    initial = json.loads((OUT/'manifest.json').read_text())
    assert all(file_hash(ROOT/p)==h for p,h in initial['code_hashes'].items())
    manifest = dict(created_utc=datetime.now(timezone.utc), workers=1,
        source_manifest_sha256=file_hash(OUT/'manifest.json'),
        script_sha256=file_hash(ROOT/'research_candle_usdjpy_followups.py'),
        hypotheses=['Fresh-cross broker costs at 1 and 2 pips', 'Current settings with minimum actual-fill SL distance 8 pips'],
        note='Unpromoted follow-up hypotheses. No policy search or parameter changes in production.')
    assert not (OUT/'followup_manifest.json').exists()
    write_json(OUT/'followup_manifest.json',manifest)
    params=settings()
    results=[]
    for src in ('dukascopy','mt5_icmarkets_utc'):
        bars=load_and_merge(paths_for(src),start=START-timedelta(days=180),end=END)
        jobs=[('min_fill_sl8',.2)]
        if src=='mt5_icmarkets_utc':
            jobs += [('fresh_cross',1.),('fresh_cross',2.)]
        for variant,spread in jobs:
            began=time.monotonic()
            result,ts=guarded_replay(bars,params) if variant=='min_fill_sl8' else replay(bars,params,variant,spread)
            result.update(source=src,variant=variant,spread_pips=spread,seconds=time.monotonic()-began)
            name=f'{src}_{variant}_spread{spread:g}'
            write_json(OUT/(name+'.json'),result)
            write_json(OUT/(name+'_trades.json'),ts)
            results.append(result)
            write_json(OUT/'followup_results.json',results)
            print(json.dumps(dict(job=name,metrics=result['metrics'],seconds=result['seconds'])),flush=True)
        del bars
    assert all(file_hash(ROOT/p)==h for p,h in initial['code_hashes'].items())
    assert all(file_hash(p)==h for p,h in initial['input_hashes'].items())
    assert all(file_hash(p)==h for p,h in initial['metadata_hashes'].items())
    write_json(OUT/'followup_complete.json',dict(replays=4,hashes_match=True))


if __name__=='__main__':
    main()
