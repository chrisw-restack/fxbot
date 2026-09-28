"""Reproduce Running logic observations without changing production behavior."""
from datetime import datetime
from unittest.mock import patch
import logging

from backtest_engine import BacktestEngine
from data.histdata_provenance import write_json
from models import BarEvent
from research_ema_fib_running_review import OUT, settings
from research_ema_fib_running_baseline import EmaFibRunningStrategy

SYMBOL = 'EURUSD'


def bar(hour,low=1.110,high=1.115,close=1.114,timeframe='H1',minute=0,open_=None):
    return BarEvent(SYMBOL,timeframe,datetime(2024,1,8,hour,minute),
                    close if open_ is None else open_,high,low,close,1)


def prepared():
    params,_ = settings()
    s = EmaFibRunningStrategy(**params)
    s._init_symbol(SYMBOL)
    for tf in ('d1','h1'):
        getattr(s,f'_{tf}_ema_fast')[SYMBOL]=1.114
        getattr(s,f'_{tf}_ema_slow')[SYMBOL]=1.110
        getattr(s,f'_{tf}_bar_count')[SYMBOL]=30
    s._h1_counter[SYMBOL]=30
    s._d1_atr[SYMBOL]=.010
    s._fractal_low[SYMBOL],s._fractal_low_body[SYMBOL]=1.100,1.102
    s._fractal_high[SYMBOL],s._fractal_high_body[SYMBOL]=1.120,1.118
    s._fractal_low_bar[SYMBOL],s._fractal_high_bar[SYMBOL]=26,28
    s._running_high[SYMBOL],s._running_low[SYMBOL]=1.115,1.105
    s._fvg_since_fractal_low[SYMBOL]=s._fvg_since_fractal_high[SYMBOL]=True
    e=BacktestEngine()
    e.add_strategy(s,[SYMBOL])
    e.execution.configure_timeframes([bar(9,timeframe='M5')])
    e.process_bar(bar(9,timeframe='M5',minute=55))
    return s,e


def main():
    logging.disable(logging.CRITICAL)
    cases=[]
    s,e=prepared()
    buy=s._calc_entry(SYMBOL,'BUY')
    sell=s._calc_entry(SYMBOL,'SELL')
    assert all(abs(a-b)<1e-10 for a,b in zip(buy,(1.104782,1.100,1.1345)))
    assert all(abs(a-b)<1e-10 for a,b in zip(sell,(1.115218,1.120,1.0855)))
    cases.append(dict(case='Body Fibonacci entry/target and wick stop mirror correctly',verdict='PASS',
                      buy=buy,sell=sell,buy_rr=(buy[2]-buy[0])/(buy[0]-buy[1])))
    e.process_bar(bar(9))
    order=e.execution.get_open_positions()[0]
    e.process_bar(bar(10,low=order['entry_price']-.00005,timeframe='M5'))
    e.process_bar(bar(10,low=order['entry_price']-.00005))
    s._fractal_low[SYMBOL],s._fractal_low_body[SYMBOL],s._running_high[SYMBOL]=1.102,1.104,1.120
    e.process_bar(bar(11))
    assert len(e.execution.get_open_positions())==1 and s._pending_anchor_low[SYMBOL]==1.102
    closed=e.process_bar(bar(12,low=1.0999,close=1.100,timeframe='M5'))
    assert len(closed)==1 and s._used_fractal_low[SYMBOL]==1.102
    cases.append(dict(case='Rejected proposal overwrites accepted anchor before loss',verdict='DEFECT CONFIRMED',
                      accepted_anchor=1.100,invalidated_anchor=s._used_fractal_low[SYMBOL]))

    s,e=prepared()
    e.process_bar(bar(9))
    order=e.execution.get_open_positions()[0]
    low=order['entry_price']-.000005
    e.process_bar(bar(10,low=low,timeframe='M5'))
    e.process_bar(bar(10,low=low))
    assert order['ticket'] in e.execution._pending and s._pending_entry[SYMBOL] is None
    s._d1_ema_fast[SYMBOL]=1.100
    e.process_bar(bar(20))
    assert order['ticket'] in e.execution._pending
    cases.append(dict(case='Bid touch consumes unfilled BUY and prevents later bias cancellation',verdict='DEFECT CONFIRMED'))

    s,e=prepared()
    e.process_bar(bar(9))
    closed=e.process_bar(bar(10,low=1.0999,close=1.100,timeframe='M5'))
    assert len(closed)==1 and not e.execution.get_open_positions() and s._pending_entry[SYMBOL] is not None
    cases.append(dict(case='Fill and stop before next H1 leaves phantom pending state',verdict='DEFECT CONFIRMED'))

    s,e=prepared()
    e.process_bar(bar(9))
    s._d1_ema_fast[SYMBOL]=1.100
    with patch.object(e.execution,'cancel_pending_order',return_value=False):
        e.process_bar(bar(20))
    assert e.execution._pending and s._pending_entry[SYMBOL] is None
    cases.append(dict(case='Cancellation failure loses local pending/anchor before confirmation',verdict='DEFECT CONFIRMED',
                      engine_retry_still_available=True))

    s=EmaFibRunningStrategy(fractal_n=2)
    events=[bar(i,low=lo,high=hi,close=cl,open_=op) for i,(lo,hi,cl,op) in enumerate([
        (1.103,1.110,1.105,1.106),(1.102,1.109,1.104,1.105),
        (1.100,1.107,1.103,1.102),(1.101,1.115,1.114,1.103),
        (1.102,1.113,1.108,1.110)])]
    for event in events[:4]:
        s.generate_signal(event)
        assert s._fractal_low[SYMBOL] is None
    s.generate_signal(events[4])
    assert s._fractal_low[SYMBOL]==1.100
    assert s._running_high[SYMBOL]==1.108
    cases.append(dict(case='Fractal waits for two completed right-hand bars',verdict='PASS'))
    cases.append(dict(case='Confirmed anchor drops already-known highest close in right wing',verdict='DEFECT CONFIRMED',
                      actual_running_high=s._running_high[SYMBOL],highest_close_since_anchor=1.114))
    # Mirror all OHLC values around 1.1 to verify the SELL-side omission too.
    s=EmaFibRunningStrategy(fractal_n=2)
    for ev in events:
        s.generate_signal(bar(ev.timestamp.hour,low=2.2-ev.high,high=2.2-ev.low,
                              close=2.2-ev.close,open_=2.2-ev.open))
    assert abs(s._running_low[SYMBOL]-1.092)<1e-10
    cases.append(dict(case='Confirmed high drops already-known lowest close in right wing',verdict='DEFECT CONFIRMED',
                      actual_running_low=s._running_low[SYMBOL],lowest_close_since_anchor=1.086))

    s,e=prepared()
    e.process_bar(bar(9))
    order=e.execution.get_open_positions()[0]
    assert not order.get('setup_id') and not order.get('attempt_id')
    fresh=EmaFibRunningStrategy(**settings()[0])
    assert not hasattr(fresh,'sync_order_state')
    cases.append(dict(case='No ledger setup identity or order-state adoption without checkpoint',verdict='RECOVERY LIMIT CONFIRMED'))

    s,e=prepared()
    s._fvg_since_fractal_low[SYMBOL]=False
    e.process_bar(bar(9))
    assert not e.execution.get_open_positions()
    s._fvg_since_fractal_low[SYMBOL]=True
    e.process_bar(bar(10))
    assert e.execution.get_open_positions()
    cases.append(dict(case='Directional FVG is required before entry',verdict='PASS'))

    s,e=prepared()
    e.process_bar(bar(20))
    assert not e.execution.get_open_positions()
    cases.append(dict(case='Blocked H1 opening hour prevents new entry',verdict='PASS'))

    s,e=prepared()
    e.process_bar(bar(9))
    first=e.execution.get_open_positions()[0]
    e.process_bar(bar(10,low=1.110,high=1.119,close=1.118))
    assert not e.execution.get_open_positions()
    e.process_bar(bar(11,low=1.110,high=1.119,close=1.118))
    second=e.execution.get_open_positions()[0]
    assert second['entry_price']>first['entry_price']+.0001
    cases.append(dict(case='Moving extreme cancels pending and replaces on a later H1 decision',verdict='PASS',
                      first_entry=first['entry_price'],replacement_entry=second['entry_price']))
    write_json(OUT/'logic_cases.json',cases)
    for row in cases:
        print(row['verdict']+': '+row['case'])


if __name__=='__main__':
    main()
