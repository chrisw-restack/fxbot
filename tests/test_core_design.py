import os
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone

from data.historical_loader import load_and_merge
from engine import EventEngine
from execution.simulated_execution import SimulatedExecution
from models import BarEvent, Signal
from portfolio.portfolio_manager import PortfolioManager
from risk.risk_manager import RiskManager
from strategies.candle_confirmation import CandleConfirmationStrategy
from strategies.ema_fib_retracement import EmaFibRetracementStrategy
from strategies.ema_fib_running import EmaFibRunningStrategy
from strategies.ny_index_opening_drive import NyIndexOpeningDriveStrategy
from strategies.three_line_strike import ThreeLineStrikeStrategy
from utils.telegram_notifier import TelegramNotifier
import config


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

    def test_sync_existing_counts_duplicate_broker_slots_toward_global_limit(self):
        portfolio = PortfolioManager(max_open_trades=3, max_daily_loss_pct=None)
        portfolio.sync_existing([
            {'ticket': 101, 'symbol': 'EURUSD', 'strategy_name': 'A'},
            {'ticket': 102, 'symbol': 'EURUSD', 'strategy_name': 'A'},
            {'ticket': 202, 'symbol': 'USDJPY', 'strategy_name': 'B'},
        ])

        self.assertFalse(portfolio.approve(_enriched_signal('GBPUSD', 'C')))


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


class StrategyPipDefaultsTests(unittest.TestCase):
    def test_strategy_defaults_match_gold_pip_size(self):
        self.assertEqual(ThreeLineStrikeStrategy()._pip_size('XAUUSD'), config.PIP_SIZE['XAUUSD'])
        self.assertEqual(EmaFibRetracementStrategy()._pip_size('XAUUSD'), config.PIP_SIZE['XAUUSD'])
        self.assertEqual(EmaFibRunningStrategy()._pip_size('XAUUSD'), config.PIP_SIZE['XAUUSD'])


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


class MT5ExecutionTests(unittest.TestCase):
    def test_order_failure_captures_broker_request_diagnostics(self):
        old_mt5 = sys.modules.get('MetaTrader5')
        old_module = sys.modules.pop('execution.mt5_execution', None)
        info = types.SimpleNamespace(
            visible=True,
            volume_step=0.01,
            volume_min=0.01,
            volume_max=100.0,
            trade_tick_size=0.00001,
            point=0.00001,
            digits=5,
            trade_stops_level=10,
            trade_freeze_level=0,
            filling_mode=1,
        )
        tick = types.SimpleNamespace(bid=1.1000, ask=1.1001)
        failure = types.SimpleNamespace(retcode=10016, comment='invalid stops')
        fake_mt5 = types.SimpleNamespace(
            TIMEFRAME_M5=1,
            TIMEFRAME_M15=2,
            TIMEFRAME_H1=3,
            TIMEFRAME_H4=4,
            TIMEFRAME_D1=5,
            TRADE_ACTION_DEAL=1,
            TRADE_ACTION_PENDING=5,
            TRADE_RETCODE_DONE=10009,
            TRADE_RETCODE_PLACED=10008,
            TRADE_RETCODE_INVALID_FILL=10030,
            ORDER_TYPE_BUY=0,
            ORDER_TYPE_SELL=1,
            ORDER_TYPE_BUY_LIMIT=2,
            ORDER_TYPE_SELL_LIMIT=3,
            ORDER_TYPE_BUY_STOP=4,
            ORDER_TYPE_SELL_STOP=5,
            ORDER_TIME_GTC=0,
            ORDER_FILLING_FOK=0,
            ORDER_FILLING_IOC=1,
            ORDER_FILLING_RETURN=2,
            symbol_info=lambda symbol: info,
            symbol_info_tick=lambda symbol: tick,
            order_check=lambda request: failure,
            order_send=lambda request: failure,
            last_error=lambda: (1, 'test error'),
        )
        sys.modules['MetaTrader5'] = fake_mt5

        def cleanup():
            sys.modules.pop('execution.mt5_execution', None)
            if old_module is not None:
                sys.modules['execution.mt5_execution'] = old_module
            if old_mt5 is not None:
                sys.modules['MetaTrader5'] = old_mt5
            else:
                sys.modules.pop('MetaTrader5', None)

        self.addCleanup(cleanup)

        from execution.mt5_execution import MT5Execution

        execution = MT5Execution(magic_numbers={'TestStrategy': 1001})
        ticket = execution.place_order(
            symbol='EURUSD',
            direction='BUY',
            order_type='MARKET',
            entry_price=1.1001,
            lot_size=0.1,
            sl=1.0990,
            tp=1.1020,
            strategy_name='TestStrategy',
        )
        error = execution.get_last_order_error()

        self.assertEqual(ticket, 0)
        self.assertEqual(error['retcode'], 10016)
        self.assertEqual(error['broker_comment'], 'invalid stops')
        self.assertEqual(error['request']['magic'], 1001)
        self.assertEqual(error['trade_stops_level'], 10)
        self.assertEqual(error['bid'], 1.1000)
        self.assertEqual(error['ask'], 1.1001)

    def test_pending_cancellation_requires_broker_removal_confirmation(self):
        old_mt5 = sys.modules.get('MetaTrader5')
        old_module = sys.modules.pop('execution.mt5_execution', None)
        calls = {'orders_get': 0}

        def orders_get(ticket):
            calls['orders_get'] += 1
            if calls['orders_get'] == 1:
                return [types.SimpleNamespace(ticket=ticket)]
            return ()

        fake_mt5 = types.SimpleNamespace(
            TIMEFRAME_M5=1,
            TIMEFRAME_M15=2,
            TIMEFRAME_H1=3,
            TIMEFRAME_H4=4,
            TIMEFRAME_D1=5,
            TRADE_ACTION_REMOVE=8,
            TRADE_RETCODE_DONE=10009,
            orders_get=orders_get,
            order_send=lambda request: types.SimpleNamespace(
                retcode=10009,
                comment='done',
            ),
            last_error=lambda: (0, ''),
        )
        sys.modules['MetaTrader5'] = fake_mt5

        def cleanup():
            sys.modules.pop('execution.mt5_execution', None)
            if old_module is not None:
                sys.modules['execution.mt5_execution'] = old_module
            if old_mt5 is not None:
                sys.modules['MetaTrader5'] = old_mt5
            else:
                sys.modules.pop('MetaTrader5', None)

        self.addCleanup(cleanup)

        from execution.mt5_execution import MT5Execution

        execution = MT5Execution(magic_numbers={'TestStrategy': 1001})

        self.assertTrue(execution.close_order(123))
        self.assertEqual(calls['orders_get'], 2)

    def test_open_orders_resolve_canonical_strategy_from_magic(self):
        old_mt5 = sys.modules.get('MetaTrader5')
        old_module = sys.modules.pop('execution.mt5_execution', None)

        fake_mt5 = types.SimpleNamespace(
            TIMEFRAME_M5=1,
            TIMEFRAME_M15=2,
            TIMEFRAME_H1=3,
            TIMEFRAME_H4=4,
            TIMEFRAME_D1=5,
            ORDER_TYPE_BUY_LIMIT=2,
            ORDER_TYPE_BUY_STOP=4,
            positions_get=lambda: (),
            orders_get=lambda: [
                types.SimpleNamespace(
                    ticket=123,
                    symbol='EURUSD',
                    type=2,
                    volume_current=1.0,
                    price_open=1.1,
                    sl=1.09,
                    tp=1.2,
                    magic=1001,
                    comment='EmaFibRetracemen',
                    position_id=0,
                ),
            ],
        )
        sys.modules['MetaTrader5'] = fake_mt5

        def cleanup():
            sys.modules.pop('execution.mt5_execution', None)
            if old_module is not None:
                sys.modules['execution.mt5_execution'] = old_module
            if old_mt5 is not None:
                sys.modules['MetaTrader5'] = old_mt5
            else:
                sys.modules.pop('MetaTrader5', None)

        self.addCleanup(cleanup)

        from execution.mt5_execution import MT5Execution

        execution = MT5Execution(magic_numbers={'EmaFibRetracement': 1001})
        order = execution.get_open_positions()[0]

        self.assertEqual(order['strategy_name'], 'EmaFibRetracement')
        self.assertEqual(order['broker_comment'], 'EmaFibRetracemen')

    def test_duplicate_magic_numbers_are_rejected(self):
        old_mt5 = sys.modules.get('MetaTrader5')
        old_module = sys.modules.pop('execution.mt5_execution', None)
        fake_mt5 = types.SimpleNamespace(
            TIMEFRAME_M5=1,
            TIMEFRAME_M15=2,
            TIMEFRAME_H1=3,
            TIMEFRAME_H4=4,
            TIMEFRAME_D1=5,
        )
        sys.modules['MetaTrader5'] = fake_mt5

        def cleanup():
            sys.modules.pop('execution.mt5_execution', None)
            if old_module is not None:
                sys.modules['execution.mt5_execution'] = old_module
            if old_mt5 is not None:
                sys.modules['MetaTrader5'] = old_mt5
            else:
                sys.modules.pop('MetaTrader5', None)

        self.addCleanup(cleanup)

        from execution.mt5_execution import MT5Execution

        with self.assertRaises(ValueError):
            MT5Execution(magic_numbers={'A': 1001, 'B': 1001})

    def test_closed_trade_lookup_matches_exit_deal_with_sl_comment(self):
        old_mt5 = sys.modules.get('MetaTrader5')
        old_module = sys.modules.pop('execution.mt5_execution', None)

        fake_mt5 = types.SimpleNamespace(
            TIMEFRAME_M5=1,
            TIMEFRAME_M15=2,
            TIMEFRAME_H1=3,
            TIMEFRAME_H4=4,
            TIMEFRAME_D1=5,
            TRADE_RETCODE_DONE=10009,
            TRADE_RETCODE_PLACED=10008,
            DEAL_ENTRY_OUT=1,
            DEAL_ENTRY_OUT_BY=3,
            last_error=lambda: (0, ''),
        )
        sys.modules['MetaTrader5'] = fake_mt5

        def cleanup():
            sys.modules.pop('execution.mt5_execution', None)
            if old_module is not None:
                sys.modules['execution.mt5_execution'] = old_module
            if old_mt5 is not None:
                sys.modules['MetaTrader5'] = old_mt5
            else:
                sys.modules.pop('MetaTrader5', None)

        self.addCleanup(cleanup)

        from execution.mt5_execution import MT5Execution

        close_ts = int(datetime(2026, 6, 9, 12, tzinfo=timezone.utc).timestamp())
        fake_mt5.history_deals_get = lambda start, end: [
            types.SimpleNamespace(
                position_id=12345,
                order=12345,
                ticket=1,
                symbol='EURUSD',
                entry=0,
                comment='TestStrategy',
                profit=0.0,
                commission=-3.5,
                swap=0.0,
                fee=0.0,
                price=1.1000,
                time=close_ts - 60,
            ),
            types.SimpleNamespace(
                position_id=12345,
                order=54321,
                ticket=2,
                symbol='EURUSD',
                entry=fake_mt5.DEAL_ENTRY_OUT,
                comment='[sl 1.0990]',
                profit=-100.0,
                commission=-3.5,
                swap=0.0,
                fee=0.0,
                price=1.0990,
                time=close_ts,
            ),
        ]

        execution = MT5Execution(magic_numbers={'TestStrategy': 1001})
        closed = execution.get_recent_closed_trade({
            'ticket': 12345,
            'position_id': 12345,
            'symbol': 'EURUSD',
            'direction': 'BUY',
            'strategy_name': 'TestStrategy',
            'open_price': 1.1000,
            'sl': 1.0990,
            'tp': 1.1020,
            'volume': 1.0,
        })

        self.assertIsNotNone(closed)
        self.assertEqual(closed['strategy_name'], 'TestStrategy')
        self.assertEqual(closed['result'], 'LOSS')
        self.assertEqual(closed['close_reason'], '[sl 1.0990]')
        self.assertAlmostEqual(closed['pnl'], -107.0)
        self.assertAlmostEqual(closed['r_multiple'], -1.0)

    def test_closed_trade_uses_sl_exit_for_r_when_tracked_sl_missing(self):
        old_mt5 = sys.modules.get('MetaTrader5')
        old_module = sys.modules.pop('execution.mt5_execution', None)

        fake_mt5 = types.SimpleNamespace(
            TIMEFRAME_M5=1,
            TIMEFRAME_M15=2,
            TIMEFRAME_H1=3,
            TIMEFRAME_H4=4,
            TIMEFRAME_D1=5,
            TRADE_RETCODE_DONE=10009,
            TRADE_RETCODE_PLACED=10008,
            DEAL_ENTRY_OUT=1,
            DEAL_ENTRY_OUT_BY=3,
            last_error=lambda: (0, ''),
        )
        sys.modules['MetaTrader5'] = fake_mt5

        def cleanup():
            sys.modules.pop('execution.mt5_execution', None)
            if old_module is not None:
                sys.modules['execution.mt5_execution'] = old_module
            if old_mt5 is not None:
                sys.modules['MetaTrader5'] = old_mt5
            else:
                sys.modules.pop('MetaTrader5', None)

        self.addCleanup(cleanup)

        from execution.mt5_execution import MT5Execution

        close_ts = int(datetime(2026, 6, 9, 12, tzinfo=timezone.utc).timestamp())
        fake_mt5.history_deals_get = lambda start, end: [
            types.SimpleNamespace(
                position_id=12345,
                order=12345,
                ticket=1,
                symbol='EURUSD',
                entry=0,
                comment='TestStrategy',
                profit=0.0,
                commission=-3.5,
                swap=0.0,
                fee=0.0,
                price=1.1000,
                time=close_ts - 60,
            ),
            types.SimpleNamespace(
                position_id=12345,
                order=54321,
                ticket=2,
                symbol='EURUSD',
                entry=fake_mt5.DEAL_ENTRY_OUT,
                comment='[sl 1.0990]',
                profit=-100.0,
                commission=-3.5,
                swap=0.0,
                fee=0.0,
                price=1.0990,
                time=close_ts,
            ),
        ]

        execution = MT5Execution(magic_numbers={'TestStrategy': 1001})
        closed = execution.get_recent_closed_trade({
            'ticket': 12345,
            'position_id': 12345,
            'symbol': 'EURUSD',
            'direction': 'BUY',
            'strategy_name': 'TestStrategy',
            'open_price': 1.1000,
            'sl': 0.0,
            'tp': 1.1020,
            'volume': 1.0,
        })

        self.assertIsNotNone(closed)
        self.assertEqual(closed['result'], 'LOSS')
        self.assertAlmostEqual(closed['r_multiple'], -1.0)
        self.assertAlmostEqual(closed['sl'], 1.0990)

    def test_closed_trade_recovers_entry_and_sl_from_position_history(self):
        old_mt5 = sys.modules.get('MetaTrader5')
        old_module = sys.modules.pop('execution.mt5_execution', None)
        deal_queries = []
        order_queries = []

        close_ts = int(datetime(2026, 6, 24, 12, tzinfo=timezone.utc).timestamp())
        deals = [
            types.SimpleNamespace(
                position_id=12345,
                order=12345,
                ticket=1,
                symbol='EURUSD',
                entry=0,
                comment='TestStrategy',
                profit=0.0,
                commission=-3.5,
                swap=0.0,
                fee=0.0,
                price=1.1000,
                volume=1.0,
                time=close_ts - 3600,
            ),
            types.SimpleNamespace(
                position_id=12345,
                order=54321,
                ticket=2,
                symbol='EURUSD',
                entry=1,
                comment='[tp 1.1020]',
                profit=200.0,
                commission=-3.5,
                swap=0.0,
                fee=0.0,
                price=1.1020,
                volume=1.0,
                time=close_ts,
            ),
        ]

        def history_deals_get(*args, **kwargs):
            deal_queries.append((args, kwargs))
            return deals if kwargs.get('position') == 12345 else ()

        def history_orders_get(**kwargs):
            order_queries.append(kwargs)
            if kwargs.get('position') != 12345:
                return ()
            return [
                types.SimpleNamespace(
                    ticket=12345,
                    position_id=12345,
                    symbol='EURUSD',
                    sl=1.0990,
                    tp=1.1020,
                    time_setup=close_ts - 3660,
                ),
            ]

        fake_mt5 = types.SimpleNamespace(
            TIMEFRAME_M5=1,
            TIMEFRAME_M15=2,
            TIMEFRAME_H1=3,
            TIMEFRAME_H4=4,
            TIMEFRAME_D1=5,
            TRADE_RETCODE_DONE=10009,
            TRADE_RETCODE_PLACED=10008,
            DEAL_ENTRY_IN=0,
            DEAL_ENTRY_OUT=1,
            DEAL_ENTRY_INOUT=2,
            DEAL_ENTRY_OUT_BY=3,
            history_deals_get=history_deals_get,
            history_orders_get=history_orders_get,
            last_error=lambda: (0, ''),
        )
        sys.modules['MetaTrader5'] = fake_mt5

        def cleanup():
            sys.modules.pop('execution.mt5_execution', None)
            if old_module is not None:
                sys.modules['execution.mt5_execution'] = old_module
            if old_mt5 is not None:
                sys.modules['MetaTrader5'] = old_mt5
            else:
                sys.modules.pop('MetaTrader5', None)

        self.addCleanup(cleanup)

        from execution.mt5_execution import MT5Execution

        execution = MT5Execution(magic_numbers={'TestStrategy': 1001})
        closed = execution.get_recent_closed_trade({
            'ticket': 12345,
            'position_id': 12345,
            'symbol': 'EURUSD',
            'direction': 'BUY',
            'strategy_name': 'TestStrategy',
            'open_price': 0.0,
            'sl': 0.0,
            'tp': 0.0,
            'volume': 1.0,
        })

        self.assertIsNotNone(closed)
        self.assertEqual(deal_queries[0][1], {'position': 12345})
        self.assertEqual(order_queries[0], {'position': 12345})
        self.assertEqual(closed['result'], 'WIN')
        self.assertAlmostEqual(closed['entry_price'], 1.1000)
        self.assertAlmostEqual(closed['sl'], 1.0990)
        self.assertAlmostEqual(closed['tp'], 1.1020)
        self.assertAlmostEqual(closed['r_multiple'], 2.0)
        self.assertEqual(closed['r_source'], 'order_history')

    def test_closed_pending_order_follows_position_id_to_exit_deal(self):
        old_mt5 = sys.modules.get('MetaTrader5')
        old_module = sys.modules.pop('execution.mt5_execution', None)

        close_ts = int(datetime(2026, 6, 24, 12, tzinfo=timezone.utc).timestamp())
        deals = [
            types.SimpleNamespace(
                position_id=12345,
                order=777,
                ticket=1,
                symbol='EURUSD',
                entry=0,
                comment='TestStrategy',
                profit=0.0,
                commission=-3.5,
                swap=0.0,
                fee=0.0,
                price=1.1000,
                volume=1.0,
                time=close_ts - 30,
            ),
            types.SimpleNamespace(
                position_id=12345,
                order=888,
                ticket=2,
                symbol='EURUSD',
                entry=1,
                comment='[sl 1.0990]',
                profit=-100.0,
                commission=-3.5,
                swap=0.0,
                fee=0.0,
                price=1.0990,
                volume=1.0,
                time=close_ts,
            ),
        ]

        def history_deals_get(*args, **kwargs):
            if kwargs:
                return ()
            return deals

        fake_mt5 = types.SimpleNamespace(
            TIMEFRAME_M5=1,
            TIMEFRAME_M15=2,
            TIMEFRAME_H1=3,
            TIMEFRAME_H4=4,
            TIMEFRAME_D1=5,
            TRADE_RETCODE_DONE=10009,
            TRADE_RETCODE_PLACED=10008,
            DEAL_ENTRY_IN=0,
            DEAL_ENTRY_OUT=1,
            DEAL_ENTRY_INOUT=2,
            DEAL_ENTRY_OUT_BY=3,
            history_deals_get=history_deals_get,
            history_orders_get=lambda **kwargs: (),
            last_error=lambda: (0, ''),
        )
        sys.modules['MetaTrader5'] = fake_mt5

        def cleanup():
            sys.modules.pop('execution.mt5_execution', None)
            if old_module is not None:
                sys.modules['execution.mt5_execution'] = old_module
            if old_mt5 is not None:
                sys.modules['MetaTrader5'] = old_mt5
            else:
                sys.modules.pop('MetaTrader5', None)

        self.addCleanup(cleanup)

        from execution.mt5_execution import MT5Execution

        execution = MT5Execution(magic_numbers={'TestStrategy': 1001})
        closed = execution.get_recent_closed_trade({
            'ticket': 777,
            'position_id': 0,
            'symbol': 'EURUSD',
            'direction': 'BUY',
            'strategy_name': 'TestStrategy',
            'open_price': 1.1000,
            'sl': 1.0990,
            'tp': 1.1020,
            'volume': 1.0,
            'state': 'PENDING',
        })

        self.assertIsNotNone(closed)
        self.assertEqual(closed['result'], 'LOSS')
        self.assertAlmostEqual(closed['pnl'], -107.0)
        self.assertAlmostEqual(closed['r_multiple'], -1.0)


class EventEngineCancellationTests(unittest.TestCase):
    def test_cancel_removes_all_matching_orders_and_only_logs_confirmed_success(self):
        positions = [
            {
                'ticket': 1, 'symbol': 'EURUSD',
                'strategy_name': 'EmaFibRetracement', 'open_time': None,
            },
            {
                'ticket': 2, 'symbol': 'EURUSD',
                'strategy_name': 'EmaFibRetracement', 'open_time': None,
            },
        ]

        class Execution:
            def get_open_positions(self):
                return positions

            def close_order(self, ticket):
                return ticket == 1

            def get_last_cancel_error(self):
                return {'retcode': 10030}

        class Journal:
            def __init__(self):
                self.cancelled = []
                self.failed = []

            def log_order_cancelled(self, pos, reason=''):
                self.cancelled.append((pos['ticket'], reason))

            def log_cancel_failed(self, pos, reason, details=None):
                self.failed.append((pos['ticket'], reason, details))

        class Notifier:
            def __init__(self):
                self.alerts = []

            def notify_operational_alert(self, message):
                self.alerts.append(message)

        portfolio = PortfolioManager(max_daily_loss_pct=None)
        portfolio.sync_existing(positions)
        journal = Journal()
        notifier = Notifier()
        engine = EventEngine(
            risk_manager=None,
            portfolio_manager=portfolio,
            execution=Execution(),
            trade_logger=None,
            notifier=notifier,
            trade_journal=journal,
        )
        signal = types.SimpleNamespace(
            symbol='EURUSD',
            strategy_name='EmaFibRetracement',
        )

        engine._handle_cancel(signal)

        self.assertEqual(journal.cancelled, [(1, 'strategy_cancel')])
        self.assertEqual(journal.failed, [(2, 'broker_cancel_failed', {'retcode': 10030})])
        self.assertEqual(len(notifier.alerts), 1)


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


class NyIndexOpeningDriveStrategyTests(unittest.TestCase):
    def test_enters_after_opening_drive_pullback_and_structure_break(self):
        strategy = NyIndexOpeningDriveStrategy(
            min_drive_pips=40,
            max_drive_pips=250,
            min_drive_body_pct=0.4,
            trend_filter='off',
            d1_range_filter='off',
            fractal_n=1,
            rr_ratio=3.0,
            sl_buffer_pips=5.0,
            pip_sizes={'USA100': 1.0},
        )

        bars = [
            _idx_bar(13, 30, 10000, 10030, 9995, 10025),
            _idx_bar(13, 35, 10025, 10050, 10020, 10045),
            _idx_bar(13, 40, 10045, 10070, 10040, 10065),
            _idx_bar(13, 45, 10065, 10090, 10060, 10085),
            _idx_bar(13, 50, 10085, 10100, 10080, 10095),
            _idx_bar(13, 55, 10095, 10098, 10085, 10090),
            _idx_bar(14, 0, 10090, 10080, 10050, 10060),
        ]
        for bar in bars:
            self.assertIsNone(strategy.generate_signal(bar))

        signal = strategy.generate_signal(_idx_bar(14, 5, 10060, 10110, 10055, 10105))

        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, 'BUY')
        self.assertAlmostEqual(signal.stop_loss, 10045)
        self.assertAlmostEqual(signal.take_profit, 10285)


class TelegramNotifierTests(unittest.TestCase):
    def test_unknown_r_multiple_is_reported_as_not_available(self):
        notifier = TelegramNotifier(bot_token='', chat_id='')
        sent = []
        notifier._send = lambda text: sent.append(text)

        notifier.notify_order_closed(
            symbol='USDCAD',
            direction='BUY',
            result='LOSS',
            r_multiple=None,
            pnl=-89.33,
            strategy='IMS_H4_M15',
        )

        self.assertEqual(len(sent), 1)
        self.assertIn('R: n/a', sent[0])
        self.assertNotIn('R: +0.00', sent[0])


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


def _idx_bar(hour, minute, open_price, high, low, close):
    return BarEvent(
        symbol='USA100',
        timeframe='M5',
        timestamp=datetime(2024, 6, 3, hour, minute),
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
