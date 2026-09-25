"""Deterministic EmaFib audit cases, including confirmed unfixed defects.

Assertions verify the observations in the report, not correctness of defects.
Production strategy and DEMO configuration are intentionally unchanged.
"""
from datetime import datetime
import logging

from backtest_engine import BacktestEngine
from data.histdata_provenance import write_json
from models import BarEvent
from research_ema_fib_review import OUT, current_settings
from research_ema_fib_baseline import EmaFibRetracementStrategy


SYMBOL = 'EURUSD'


def bar(hour, low, high, close, timeframe='H1', minute=0):
    return BarEvent(SYMBOL, timeframe, datetime(2024, 1, 8, hour, minute), close, high, low, close, 1)


def prepared():
    params, _ = current_settings()
    strategy = EmaFibRetracementStrategy(**params)
    strategy._init_symbol(SYMBOL)
    for tf in ('d1', 'h1'):
        getattr(strategy, f'_{tf}_ema_fast')[SYMBOL] = 1.104
        getattr(strategy, f'_{tf}_ema_slow')[SYMBOL] = 1.102
        getattr(strategy, f'_{tf}_bar_count')[SYMBOL] = 30
    strategy._h1_counter[SYMBOL] = 30
    strategy._d1_atr[SYMBOL] = .010
    strategy._swing_high[SYMBOL] = 1.105
    strategy._swing_low[SYMBOL] = 1.100
    strategy._swing_high_bar[SYMBOL] = 28
    strategy._swing_low_bar[SYMBOL] = 26
    engine = BacktestEngine()
    engine.add_strategy(strategy, [SYMBOL])
    engine.execution.configure_timeframes([bar(9, 1.103, 1.104, 1.104, 'M5')])
    engine.process_bar(bar(9, 1.103, 1.104, 1.104, 'M5', 55))
    return strategy, engine


def main():
    logging.disable(logging.CRITICAL)
    cases = []
    strategy, engine = prepared()
    engine.process_bar(bar(9, 1.103, 1.104, 1.104))
    original = engine.execution.get_open_positions()[0]
    entry = original['entry_price']
    assert abs(entry-1.10107) < 1e-10
    assert original['sl'] == 1.100 and abs(original['tp']-1.115) < 1e-10
    cases.append(dict(case='Fibonacci price arithmetic', verdict='PASS',
                      entry=entry, stop=original['sl'], target=original['tp'],
                      gross_rr=original['requested_rr']))

    # A genuine fill, followed by a later rejected proposal on a newer swing.
    engine.process_bar(bar(10, entry-.00005, 1.104, 1.104, 'M5'))
    assert original['ticket'] in engine.execution._positions
    engine.process_bar(bar(10, entry-.00005, 1.104, 1.104))
    strategy._swing_high[SYMBOL], strategy._swing_low[SYMBOL] = 1.108, 1.102
    engine.process_bar(bar(11, 1.104, 1.106, 1.105))
    assert len(engine.execution.get_open_positions()) == 1
    assert strategy._pending_swing_high[SYMBOL] == 1.108
    closed = engine.process_bar(bar(12, 1.0999, 1.104, 1.100, 'M5'))
    assert len(closed) == 1 and closed[0]['result'] == 'LOSS'
    used = [strategy._used_swing_high[SYMBOL], strategy._used_swing_low[SYMBOL]]
    assert used == [1.108, 1.102]
    cases.append(dict(case='Rejected proposal overwrites accepted swing', verdict='DEFECT CONFIRMED',
                      original_swing=[1.105, 1.100], swing_invalidated_after_loss=used,
                      duplicate_order_blocked=True))

    strategy, engine = prepared()
    engine.process_bar(bar(9, 1.103, 1.104, 1.104))
    order = engine.execution.get_open_positions()[0]
    entry = order['entry_price']
    # Bid touches BUY limit, but ask is still 0.05 pip above it.
    low = entry-.000005
    engine.process_bar(bar(10, low, 1.104, 1.104, 'M5'))
    assert order['ticket'] in engine.execution._pending
    engine.process_bar(bar(10, low, 1.104, 1.104))
    assert strategy._pending_entry[SYMBOL] is None
    assert order['ticket'] in engine.execution._pending
    cases.append(dict(case='Bid-touch heuristic clears an unfilled BUY', verdict='DEFECT CONFIRMED',
                      broker_state='PENDING', strategy_pending=None, bid_low=low,
                      ask_low=low+.00001, entry=entry))

    strategy, engine = prepared()
    engine.process_bar(bar(9, 1.103, 1.104, 1.104))
    closed = engine.process_bar(bar(10, 1.0999, 1.104, 1.100, 'M5'))
    assert len(closed) == 1 and not engine.execution.get_open_positions()
    assert strategy._pending_entry[SYMBOL] is not None
    cases.append(dict(case='Trade fills and stops before next H1 decision', verdict='DEFECT CONFIRMED',
                      broker_open_orders=0, local_pending_entry=strategy._pending_entry[SYMBOL]))

    strategy, engine = prepared()
    for tf in ('d1', 'h1'):
        getattr(strategy, f'_{tf}_ema_fast')[SYMBOL] = 1.101
        getattr(strategy, f'_{tf}_ema_slow')[SYMBOL] = 1.104
    signal = strategy.generate_signal(bar(9, 1.100, 1.102, 1.101))
    assert signal.direction == 'SELL' and abs(signal.entry_price-1.10393) < 1e-10
    assert signal.stop_loss == 1.105 and abs(signal.take_profit-1.090) < 1e-10
    cases.append(dict(case='SELL mirrors BUY Fibonacci levels', verdict='PASS'))

    strategy, engine = prepared()
    engine.process_bar(bar(9, 1.103, 1.104, 1.104))
    strategy._d1_ema_fast[SYMBOL] = 1.100
    strategy._d1_ema_slow[SYMBOL] = 1.105
    engine.process_bar(bar(20, 1.103, 1.104, 1.104))
    assert not engine.execution.get_open_positions() and strategy._pending_entry[SYMBOL] is None
    cases.append(dict(case='D1 disagreement cancels untouched pending even in blocked entry hours', verdict='PASS'))

    strategy, engine = prepared()
    strategy._swing_high[SYMBOL] = 1.102
    engine.process_bar(bar(9, 1.103, 1.104, 1.104))
    assert not engine.execution.get_open_positions() and strategy._pending_entry[SYMBOL] is None
    cases.append(dict(case='Rejected short-stop proposal clears state when no order exists', verdict='PASS'))

    # A seven-bar fractal becomes available only after three right-hand bars.
    strategy = EmaFibRetracementStrategy(fractal_n=3)
    events = [bar(i, 1.09, high, 1.10) for i, high in enumerate([1.11,1.12,1.13,1.15,1.13,1.12,1.11])]
    for event in events[:6]:
        strategy.generate_signal(event)
        assert strategy._swing_high[SYMBOL] is None
    strategy.generate_signal(events[6])
    assert strategy._swing_high[SYMBOL] == 1.15
    cases.append(dict(case='Fractal waits for three completed right-hand bars', verdict='PASS'))

    write_json(OUT/'logic_cases.json', cases)
    for case in cases:
        print(f"{case['verdict']}: {case['case']}")


if __name__ == '__main__':
    main()
