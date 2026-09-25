"""Explain a changed AUDUSD winner using unchanged before/after replay flows."""
from copy import deepcopy
from datetime import datetime, timedelta
import logging

from backtest_engine import BacktestEngine
from data.historical_loader import load_and_merge
from data.histdata_provenance import write_json
from research_ema_fib_baseline import EmaFibRetracementStrategy as Baseline
from research_ema_fib_review import current_settings, paths_for
from research_ema_fib_tracking import OUT
from strategies.ema_fib_retracement import EmaFibRetracementStrategy


class TraceEngine(BacktestEngine):
    def state(self):
        s = self.strategy
        return dict(orders=deepcopy(self.execution.get_open_positions()),
            pending=s._pending_entry.get('AUDUSD'),pending_direction=s._pending_direction.get('AUDUSD'),
            used=(s._used_swing_high.get('AUDUSD'),s._used_swing_low.get('AUDUSD')),
            swing=(s._swing_high.get('AUDUSD'),s._swing_low.get('AUDUSD')),
            status=s.get_status('AUDUSD'))

    def process_bar(self, bar):
        active = datetime(2020,4,20) <= bar.timestamp < datetime(2020,4,25)
        before = self.state() if active else None
        closed = super().process_bar(bar)
        if active:
            after = self.state()
            if bar.timeframe == 'H1' or before != after:
                self.trace.append(dict(time=bar.timestamp,timeframe=bar.timeframe,before=before,after=after,closed=closed))
        return closed


def main():
    logging.disable(logging.CRITICAL)
    params,_ = current_settings()
    start,end = datetime(2020,1,1),datetime(2020,5,1)
    bars = load_and_merge(paths_for('dukascopy','AUDUSD'),start=start-timedelta(days=180),end=end)
    for name,cls in [('original',Baseline),('corrected',EmaFibRetracementStrategy)]:
        engine = TraceEngine()
        engine.strategy = cls(**params)
        engine.trace = []
        engine.add_strategy(engine.strategy,['AUDUSD'])
        trades = engine.replay(bars,start_date=start,end_date=end)
        write_json(OUT/f'audusd_april2020_{name}_trace.json',engine.trace)
        write_json(OUT/f'audusd_april2020_{name}_trades.json',trades)
        for r in engine.trace:
            before = {o['ticket'] for o in r['before']['orders']}
            after = {o['ticket'] for o in r['after']['orders']}
            if before != after:
                print(name,r['time'],r['timeframe'],'tickets',sorted(before),'->',sorted(after),r['after']['status'])


if __name__ == '__main__':
    main()
