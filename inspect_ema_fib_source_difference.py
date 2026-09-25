"""Trace the missing March 2026 AUDUSD winner without changing decisions."""
from datetime import datetime, timedelta
from copy import deepcopy
import logging

from backtest_engine import BacktestEngine
from data.historical_loader import load_and_merge
from data.histdata_provenance import write_json
from research_ema_fib_review import OUT, current_settings, paths_for, ObservedEmaFib, metrics


class Trace(ObservedEmaFib):
    def __init__(self, **params):
        super().__init__(**params)
        self.trace = []

    def generate_signal(self, event):
        signal = super().generate_signal(event)
        if datetime(2026,3,20) <= event.timestamp < datetime(2026,3,26):
            sym = event.symbol
            self.trace.append(dict(time=event.timestamp, timeframe=event.timeframe,
                close=event.close, signal=signal.__dict__ if signal else None,
                d1_fast=self._d1_ema_fast.get(sym), d1_slow=self._d1_ema_slow.get(sym),
                h1_fast=self._h1_ema_fast.get(sym), h1_slow=self._h1_ema_slow.get(sym),
                pending_entry=self._pending_entry.get(sym),
                status=self.get_status(sym), actual=deepcopy(self.execution.get_open_positions())))
        return signal


def main():
    logging.disable(logging.CRITICAL)
    params, _ = current_settings()
    start, end = datetime(2026,1,1), datetime(2026,4,1)
    results = []
    for source, omit_hour in [('dukascopy',False), ('histdata',False), ('histdata',True)]:
        name = source + ('_omit_one_h1_control' if omit_hour else '')
        strategy = Trace(**params)
        engine = BacktestEngine()
        strategy.execution = engine.execution
        engine.add_strategy(strategy, ['AUDUSD'])
        bars = load_and_merge(paths_for(source,'AUDUSD'), start=start-timedelta(days=180), end=end)
        if omit_hour:
            before = len(bars)
            bars = [b for b in bars if not (b.timeframe == 'H1' and b.timestamp == datetime(2026,3,23,19))]
            assert len(bars) == before-1
        trades = engine.replay(bars, start_date=start, end_date=end)
        write_json(OUT/f'{name}_audusd_march_trace.json', strategy.trace)
        results.append(dict(source=name, metrics=metrics(trades), trades=trades,
                            note='Omission control is diagnostic only. Source files are unchanged.'))
        print(name)
        for row in strategy.trace:
            if row['signal']:
                print(row['time'], row['signal']['direction'], row['signal']['entry_price'],
                      row['d1_fast'], row['d1_slow'], row['status']['blocker'])
    write_json(OUT/'audusd_march_difference.json', results)


if __name__ == '__main__':
    main()
