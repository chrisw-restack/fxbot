import os
import tempfile
import unittest
from datetime import datetime

from data.historical_loader import load_and_merge
from execution.simulated_execution import SimulatedExecution
from models import BarEvent, Signal
from portfolio.portfolio_manager import PortfolioManager
from risk.risk_manager import RiskManager


class PortfolioManagerTests(unittest.TestCase):
    def test_sync_existing_replaces_slots_from_broker_state(self):
        portfolio = PortfolioManager(max_open_trades=3, max_daily_loss_pct=None)
        portfolio.sync_existing([
            {'ticket': 101, 'symbol': 'EURUSD', 'strategy_name': 'A'},
            {'ticket': 202, 'symbol': 'EURUSD', 'strategy_name': 'B'},
        ])

        self.assertFalse(portfolio.approve(_enriched_signal('EURUSD', 'A')))
        self.assertFalse(portfolio.approve(_enriched_signal('EURUSD', 'B')))
        self.assertTrue(portfolio.approve(_enriched_signal('GBPUSD', 'A')))


class RiskManagerTests(unittest.TestCase):
    def test_rejects_rr_below_minimum_when_strategy_sets_tp(self):
        risk = RiskManager(account_balance_fn=lambda: 10_000.0)
        signal = Signal(
            symbol='EURUSD',
            direction='BUY',
            order_type='MARKET',
            entry_price=1.1000,
            stop_loss=1.0990,
            take_profit=1.1005,
            strategy_name='Test',
            timestamp=datetime(2024, 1, 1),
        )

        self.assertIsNone(risk.process(signal))


class SimulatedExecutionTests(unittest.TestCase):
    def test_market_order_fills_on_next_matching_timeframe_bar(self):
        execution = SimulatedExecution(10_000, spread_pips=0.0, rr_ratio=2.0)
        ticket = execution.place_order(
            symbol='EURUSD',
            direction='BUY',
            order_type='MARKET',
            entry_price=1.1000,
            lot_size=0.1,
            sl=1.0990,
            tp=1.1020,
            strategy_name='Test',
            entry_timeframe='H1',
            signal_time=datetime(2024, 1, 1, 9),
        )

        execution.check_fills(_bar('EURUSD', 'M15', datetime(2024, 1, 1, 9, 15), 1.1010))
        self.assertEqual(execution.get_open_positions()[0]['ticket'], ticket)
        self.assertEqual(execution.get_open_positions()[0]['order_type'], 'MARKET')

        execution.check_fills(_bar('EURUSD', 'H1', datetime(2024, 1, 1, 10), 1.1005))
        self.assertEqual(execution.get_open_positions()[0]['open_time'], datetime(2024, 1, 1, 10))


class HistoricalLoaderTests(unittest.TestCase):
    def test_load_and_merge_processes_lower_timeframe_first_at_same_close_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            h4 = os.path.join(tmp, 'EURUSD_H4_20240101-20240102.csv')
            m15 = os.path.join(tmp, 'EURUSD_M15_20240101-20240102.csv')
            _write_csv(h4, '2024-01-01 08:00:00')
            _write_csv(m15, '2024-01-01 11:45:00')

            bars = load_and_merge([h4, m15])

        self.assertEqual([b.timeframe for b in bars], ['M15', 'H4'])


def _enriched_signal(symbol, strategy_name):
    from models import EnrichedSignal

    return EnrichedSignal(
        symbol=symbol,
        direction='BUY',
        order_type='MARKET',
        entry_price=1.1,
        stop_loss=1.09,
        take_profit=1.12,
        lot_size=0.1,
        strategy_name=strategy_name,
        timestamp=datetime(2024, 1, 1),
    )


def _bar(symbol, timeframe, timestamp, open_price):
    return BarEvent(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        open=open_price,
        high=open_price + 0.0005,
        low=open_price - 0.0005,
        close=open_price,
        volume=1,
    )


def _write_csv(path, timestamp):
    with open(path, 'w', encoding='utf-8') as f:
        f.write('time,open,high,low,close,volume\n')
        f.write(f'{timestamp},1.1000,1.1010,1.0990,1.1005,1\n')


if __name__ == '__main__':
    unittest.main()
