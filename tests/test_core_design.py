import os
import tempfile
import unittest
from datetime import datetime

from data.historical_loader import load_and_merge
from execution.simulated_execution import SimulatedExecution
from models import BarEvent, Signal
from portfolio.portfolio_manager import PortfolioManager
from risk.risk_manager import RiskManager
from strategies.candle_confirmation import CandleConfirmationStrategy


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

    def test_buy_round_trip_pays_spread_at_entry_only_with_bid_bars(self):
        execution = SimulatedExecution(10_000, spread_pips=2.0, commission_per_lot=0.0)
        execution.place_order(
            symbol='EURUSD',
            direction='BUY',
            order_type='MARKET',
            entry_price=1.1000,
            lot_size=1.0,
            sl=1.0990,
            tp=1.1020,
            strategy_name='Test',
            entry_timeframe='H1',
            tp_locked=True,
        )

        execution.check_fills(_bar('EURUSD', 'H1', datetime(2024, 1, 1, 10), 1.1000))
        closed = execution.check_fills(_bar('EURUSD', 'H1', datetime(2024, 1, 1, 11), 1.1020))

        self.assertEqual(len(closed), 1)
        self.assertAlmostEqual(closed[0]['entry_price'], 1.1002)
        self.assertAlmostEqual(closed[0]['exit_price'], 1.1020)
        self.assertAlmostEqual(closed[0]['pnl'], 180.0)

    def test_sell_round_trip_pays_spread_at_exit_with_bid_bars(self):
        execution = SimulatedExecution(10_000, spread_pips=2.0, commission_per_lot=0.0)
        execution.place_order(
            symbol='EURUSD',
            direction='SELL',
            order_type='MARKET',
            entry_price=1.1000,
            lot_size=1.0,
            sl=1.1010,
            tp=1.0980,
            strategy_name='Test',
            entry_timeframe='H1',
            tp_locked=True,
        )

        execution.check_fills(_bar('EURUSD', 'H1', datetime(2024, 1, 1, 10), 1.1000))
        closed = execution.check_fills(_bar('EURUSD', 'H1', datetime(2024, 1, 1, 11), 1.0980))

        self.assertEqual(len(closed), 1)
        self.assertAlmostEqual(closed[0]['entry_price'], 1.1000)
        self.assertAlmostEqual(closed[0]['exit_price'], 1.0982)
        self.assertAlmostEqual(closed[0]['pnl'], 180.0)

    def test_sell_tp_is_not_hit_until_ask_reaches_target(self):
        execution = SimulatedExecution(10_000, spread_pips=2.0, commission_per_lot=0.0)
        execution.place_order(
            symbol='EURUSD',
            direction='SELL',
            order_type='MARKET',
            entry_price=1.1000,
            lot_size=1.0,
            sl=1.1010,
            tp=1.0980,
            strategy_name='Test',
            entry_timeframe='H1',
            tp_locked=True,
        )

        execution.check_fills(_bar('EURUSD', 'H1', datetime(2024, 1, 1, 10), 1.1000))
        not_closed = execution.check_fills(BarEvent(
            symbol='EURUSD',
            timeframe='H1',
            timestamp=datetime(2024, 1, 1, 11),
            open=1.0983,
            high=1.0985,
            low=1.0979,
            close=1.0982,
            volume=1,
        ))
        closed = execution.check_fills(BarEvent(
            symbol='EURUSD',
            timeframe='H1',
            timestamp=datetime(2024, 1, 1, 12),
            open=1.0982,
            high=1.0984,
            low=1.0978,
            close=1.0981,
            volume=1,
        ))

        self.assertEqual(not_closed, [])
        self.assertEqual(len(closed), 1)


class HistoricalLoaderTests(unittest.TestCase):
    def test_load_and_merge_processes_lower_timeframe_first_at_same_close_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            h4 = os.path.join(tmp, 'EURUSD_H4_20240101-20240102.csv')
            m15 = os.path.join(tmp, 'EURUSD_M15_20240101-20240102.csv')
            _write_csv(h4, '2024-01-01 08:00:00')
            _write_csv(m15, '2024-01-01 11:45:00')

            bars = load_and_merge([h4, m15])

        self.assertEqual([b.timeframe for b in bars], ['M15', 'H4'])


class CandleConfirmationStrategyTests(unittest.TestCase):
    def test_bullish_entry_requires_retrace_swing_break_and_fvg(self):
        strategy = CandleConfirmationStrategy(fractal_n=1)
        strategy.generate_signal(_cc_bar('H1', 0, 1.1050, 1.1060, 1.1010, 1.1020))
        strategy.generate_signal(_cc_bar('H1', 60, 1.1020, 1.1100, 1.1000, 1.1051))

        sequence = [
            _cc_bar('M5', 65, 1.1050, 1.1050, 1.1040, 1.1045),
            _cc_bar('M5', 70, 1.1045, 1.1060, 1.1048, 1.1055),
            _cc_bar('M5', 75, 1.1055, 1.1055, 1.1052, 1.1053),
            _cc_bar('M5', 80, 1.1053, 1.1057, 1.1051, 1.1056),
        ]
        for bar in sequence:
            self.assertIsNone(strategy.generate_signal(bar))

        signal = strategy.generate_signal(_cc_bar('M5', 85, 1.1056, 1.1064, 1.1054, 1.1062))

        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, 'BUY')
        self.assertAlmostEqual(signal.take_profit, 1.1100)
        self.assertAlmostEqual(signal.stop_loss, 1.1024)

    def test_no_entry_before_retrace_level_is_touched(self):
        strategy = CandleConfirmationStrategy(fractal_n=1)
        strategy.generate_signal(_cc_bar('H1', 0, 1.1050, 1.1060, 1.1010, 1.1020))
        strategy.generate_signal(_cc_bar('H1', 60, 1.1020, 1.1100, 1.1000, 1.1051))

        bars = [
            _cc_bar('M5', 65, 1.1060, 1.1062, 1.1056, 1.1058),
            _cc_bar('M5', 70, 1.1058, 1.1070, 1.1057, 1.1065),
            _cc_bar('M5', 75, 1.1065, 1.1066, 1.1058, 1.1061),
            _cc_bar('M5', 80, 1.1061, 1.1067, 1.1059, 1.1064),
            _cc_bar('M5', 85, 1.1064, 1.1074, 1.1062, 1.1072),
        ]

        for bar in bars:
            self.assertIsNone(strategy.generate_signal(bar))

    def test_fvg_is_required_in_breaking_leg(self):
        strategy = CandleConfirmationStrategy(fractal_n=1)
        strategy.generate_signal(_cc_bar('H1', 0, 1.1050, 1.1060, 1.1010, 1.1020))
        strategy.generate_signal(_cc_bar('H1', 60, 1.1020, 1.1100, 1.1000, 1.1051))

        bars = [
            _cc_bar('M5', 65, 1.1050, 1.1050, 1.1040, 1.1045),
            _cc_bar('M5', 70, 1.1045, 1.1060, 1.1048, 1.1055),
            _cc_bar('M5', 75, 1.1055, 1.1055, 1.1049, 1.1053),
            _cc_bar('M5', 80, 1.1053, 1.1057, 1.1051, 1.1056),
            _cc_bar('M5', 85, 1.1056, 1.1064, 1.1054, 1.1062),
        ]

        for bar in bars:
            self.assertIsNone(strategy.generate_signal(bar))

    def test_touching_engulf_extreme_before_entry_invalidates_bias(self):
        strategy = CandleConfirmationStrategy(fractal_n=1)
        strategy.generate_signal(_cc_bar('H1', 0, 1.1050, 1.1060, 1.1010, 1.1020))
        strategy.generate_signal(_cc_bar('H1', 60, 1.1020, 1.1100, 1.1000, 1.1051))

        self.assertIsNone(strategy.generate_signal(
            _cc_bar('M5', 65, 1.1060, 1.1100, 1.1050, 1.1065)
        ))

        self.assertIsNone(strategy._bias['EURUSD'])

    def test_opposing_engulf_replaces_bias_before_entry_but_not_after_signal(self):
        strategy = CandleConfirmationStrategy(fractal_n=1)
        strategy.generate_signal(_cc_bar('H1', 0, 1.1050, 1.1060, 1.1010, 1.1020))
        strategy.generate_signal(_cc_bar('H1', 60, 1.1020, 1.1100, 1.1000, 1.1051))

        strategy.generate_signal(_cc_bar('H1', 120, 1.1051, 1.1060, 1.0980, 1.1010))
        self.assertEqual(strategy._bias['EURUSD']['direction'], 'SELL')

        strategy._signal_fired['EURUSD'] = True
        strategy.generate_signal(_cc_bar('H1', 180, 1.1010, 1.1120, 1.1000, 1.1065))
        self.assertEqual(strategy._bias['EURUSD']['direction'], 'SELL')


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


def _cc_bar(timeframe, minute, open_price, high, low, close):
    return BarEvent(
        symbol='EURUSD',
        timeframe=timeframe,
        timestamp=datetime(2024, 1, 1, minute // 60, minute % 60),
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=1,
    )


def _write_csv(path, timestamp):
    with open(path, 'w', encoding='utf-8') as f:
        f.write('time,open,high,low,close,volume\n')
        f.write(f'{timestamp},1.1000,1.1010,1.0990,1.1005,1\n')


if __name__ == '__main__':
    unittest.main()
