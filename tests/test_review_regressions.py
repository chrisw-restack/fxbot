import importlib
import json
import sys
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd

from backtest_engine import BacktestEngine
from data.historical_loader import load_csv
from data.news_filter import NewsFilter
from engine import EventEngine
from execution.simulated_execution import SimulatedExecution
from models import BarEvent, Signal
from portfolio.portfolio_manager import PortfolioManager
from risk.risk_manager import RiskManager

T = datetime(2026, 9, 7, 10)


def bar(t=T, tf='M5', o=1.1, h=1.1001, l=1.0999, c=1.1, symbol='EURUSD'):
    return BarEvent(symbol, tf, t, o, h, l, c, 1)


def signal(**kwargs):
    return Signal(**dict(dict(symbol='EURUSD', direction='BUY', order_type='MARKET',
                              entry_price=1.1, stop_loss=1.099, take_profit=1.102,
                              strategy_name='Test', timestamp=T), **kwargs))


def place(ex, **kwargs):
    return ex.place_order(**dict(dict(symbol='EURUSD', direction='BUY', order_type='MARKET',
                                     entry_price=1.1, sl=1.099, tp=1.102, lot_size=1.0,
                                     strategy_name='Test', entry_timeframe='M5', tp_locked=True), **kwargs))


@contextmanager
def fake_broker():
    info = SimpleNamespace(visible=True, volume_step=.01, volume_min=.01, volume_max=100.,
                           trade_tick_size=.00001, point=.00001, digits=5)
    fake = SimpleNamespace(
        TIMEFRAME_M5=5, TIMEFRAME_M15=15, TIMEFRAME_H1=60, TIMEFRAME_H4=240, TIMEFRAME_D1=1440,
        ORDER_TYPE_BUY=0, ORDER_TYPE_SELL=1, ORDER_TYPE_BUY_LIMIT=2, ORDER_TYPE_SELL_LIMIT=3,
        ORDER_TYPE_BUY_STOP=4, ORDER_TYPE_SELL_STOP=5, TRADE_ACTION_DEAL=1, TRADE_ACTION_PENDING=5,
        TRADE_RETCODE_DONE=10009, TRADE_RETCODE_PLACED=10008, TRADE_RETCODE_INVALID_FILL=10030,
        ORDER_TIME_GTC=0, ORDER_FILLING_IOC=1, ORDER_FILLING_FOK=0, ORDER_FILLING_RETURN=2,
        ACCOUNT_TRADE_MODE_DEMO=0, ACCOUNT_MARGIN_MODE_RETAIL_HEDGING=2,
        positions_get=Mock(return_value=()), orders_get=Mock(return_value=()),
        account_info=Mock(return_value=SimpleNamespace(balance=10000., login=123, server='Demo', trade_mode=0, margin_mode=2)),
        symbol_info=Mock(return_value=info),
        symbol_info_tick=Mock(return_value=SimpleNamespace(bid=1.1, ask=1.1001)),
        order_calc_profit=Mock(side_effect=lambda direction, symbol, volume, entry, sl: -abs(entry-sl)*100000*volume),
        order_send=Mock(side_effect=lambda request: SimpleNamespace(retcode=10009, order=123, price=request['price'], deal=456)),
        order_check=Mock(return_value=SimpleNamespace(retcode=0, comment='ok')),
        initialize=Mock(return_value=True), shutdown=Mock(), last_error=Mock(return_value=(-1, 'unavailable')),
        history_deals_get=Mock(return_value=()),
    )
    names = ('execution.mt5_execution', 'data.mt5_data')
    saved = {name: sys.modules.pop(name, None) for name in names}
    try:
        with patch.dict(sys.modules, {'MetaTrader5': fake}):
            execution = importlib.import_module('execution.mt5_execution')
            data = importlib.import_module('data.mt5_data')
            yield fake, execution.MT5Execution, data
    finally:
        for name in names:
            sys.modules.pop(name, None)
            if saved[name] is not None:
                sys.modules[name] = saved[name]


class RiskRegressionTests(unittest.TestCase):
    def test_rejects_wrong_sides_and_nonfinite_values(self):
        risk = RiskManager(lambda: 10000)
        for changes in ({'stop_loss': 1.101}, {'take_profit': 1.098},
                        {'entry_price': float('nan')}, {'stop_loss': float('inf')},
                        {'stop_loss': None}, {'direction': 'OTHER'}, {'order_type': 'OTHER'}):
            with self.subTest(changes=changes):
                self.assertIsNone(risk.process(signal(**changes)))

    def test_rejects_minimum_volume_above_budget(self):
        self.assertIsNone(RiskManager(lambda: 100).process(signal(stop_loss=1.09, take_profit=1.12)))

    def test_rounds_down_and_preserves_budget(self):
        result = RiskManager(lambda: 10000).process(signal(stop_loss=1.0989, take_profit=1.1022))
        self.assertEqual(result.lot_size, .45)
        self.assertEqual(result.risk_budget, 50)

    def test_rechecks_locked_target_at_executable_price(self):
        risk = RiskManager(lambda: 10000, entry_price_fn=lambda s: 1.1008)
        self.assertIsNone(risk.process(signal(take_profit=1.101)))

    def test_uses_broker_contract_loss(self):
        risk = RiskManager(lambda: 10000, loss_per_lot_fn=lambda *a: 2000,
                           volume_limits_fn=lambda s: dict(step=.01, minimum=.01, maximum=100))
        self.assertEqual(risk.process(signal()).lot_size, .02)


class DailyLimitRegressionTests(unittest.TestCase):
    def test_older_day_cannot_clear_losses(self):
        p = PortfolioManager()
        p.set_current_date(T.date())
        p.record_close('EURUSD', -250, 'Test')
        p.set_current_date((T-timedelta(days=1)).date())
        self.assertTrue(p.is_daily_loss_exceeded(10000))

    def test_old_close_does_not_charge_today(self):
        p = PortfolioManager()
        p.set_current_date(T.date())
        p.record_close('EURUSD', -250, 'Test', close_time=T-timedelta(days=1))
        self.assertFalse(p.is_daily_loss_exceeded(10000))

    def test_restore_is_idempotent(self):
        p = PortfolioManager()
        for _ in range(2):
            p.restore_daily_loss(T.date(), 250)
        self.assertEqual(p._daily_loss, 250)
        p.set_current_date((T+timedelta(days=1)).date())
        self.assertEqual(p._daily_loss, 0)

    def test_limit_preserves_updates_and_cancellations(self):
        p = PortfolioManager()
        p.restore_daily_loss(T.date(), 250)
        ex = SimulatedExecution(10000)
        strategy = SimpleNamespace(NAME='Test', TIMEFRAMES=['M5'], generate_signal=Mock(
            return_value=signal(direction='CANCEL', entry_price=0, stop_loss=0)))
        engine = EventEngine(RiskManager(lambda: 10000), p, ex, Mock())
        engine.register(strategy, ['EURUSD'])
        engine._handle_cancel = Mock()
        engine.process_bar(bar())
        strategy.generate_signal.assert_called_once()
        engine._handle_cancel.assert_called_once()

    def test_first_close_on_new_day_is_not_cleared(self):
        engine = BacktestEngine(max_daily_loss_pct=.02, spread_pips=0)
        engine.portfolio.set_current_date((T-timedelta(days=1)).date())
        place(engine.execution, lot_size=3)
        engine.process_bar(bar(l=1.098))
        self.assertTrue(engine.portfolio.is_daily_loss_exceeded(engine.execution.get_account_balance()))


class BrokerRegressionTests(unittest.TestCase):
    def test_account_switch_blocks_submission(self):
        with fake_broker() as (mt5, cls, _):
            ex = cls(expected_account={'expected_login':123, 'expected_server':'Demo'})
            mt5.account_info.return_value.login = 456
            with self.assertRaises(RuntimeError):
                place(ex)
            mt5.order_send.assert_not_called()

    def test_partial_fill_is_recorded_as_a_real_order(self):
        with fake_broker() as (mt5, cls, _):
            mt5.TRADE_RETCODE_DONE_PARTIAL = 10010
            mt5.order_send.side_effect = None
            mt5.order_send.return_value = SimpleNamespace(retcode=10010, order=123, price=1.1001, volume=.03)
            ex = cls()
            self.assertEqual(place(ex), 123)
            self.assertEqual(ex.get_last_order_details()['volume'], .03)

    def test_unknown_preflight_does_not_submit(self):
        with fake_broker() as (mt5, cls, _):
            mt5.order_check.return_value = None
            with self.assertRaises(RuntimeError):
                place(cls())
            mt5.order_send.assert_not_called()

    def test_query_failures_raise_instead_of_empty_snapshot(self):
        with fake_broker() as (mt5, cls, _):
            for method in ('positions_get', 'orders_get'):
                fn = getattr(mt5, method)
                fn.return_value = None
                with self.assertRaises(RuntimeError):
                    cls().get_open_positions()
                fn.return_value = ()

    def test_balance_failure_raises(self):
        with fake_broker() as (mt5, cls, _):
            mt5.account_info.return_value = None
            with self.assertRaises(RuntimeError):
                cls().get_account_balance()

    def test_final_volume_does_not_exceed_budget(self):
        with fake_broker() as (mt5, cls, _):
            place(cls(), risk_budget=5)
            request = mt5.order_send.call_args.args[0]
            self.assertEqual(request['volume'], .04)
            self.assertLessEqual(abs(request['price']-request['sl'])*100000*request['volume'], 5)

    def test_broker_minimum_cannot_increase_risk(self):
        with fake_broker() as (mt5, cls, _):
            mt5.symbol_info.return_value.volume_min = .1
            self.assertEqual(place(cls(), risk_budget=5), 0)
            mt5.order_send.assert_not_called()

    def test_final_quote_rejects_subminimum_rr(self):
        with fake_broker() as (mt5, cls, _):
            mt5.symbol_info_tick.return_value.ask = 1.1008
            self.assertEqual(place(cls(), tp=1.101), 0)
            mt5.order_send.assert_not_called()

    def test_failed_preflight_does_not_submit_order(self):
        with fake_broker() as (mt5, cls, _):
            mt5.order_check.return_value = SimpleNamespace(retcode=10016, comment='invalid stops')
            self.assertEqual(place(cls()), 0)
            mt5.order_send.assert_not_called()

    def test_real_or_netting_account_cannot_connect(self):
        with fake_broker() as (mt5, _, data):
            for field, value in [('trade_mode', 2), ('margin_mode', 0), ('login', 999)]:
                info = mt5.account_info.return_value
                original = getattr(info, field)
                setattr(info, field, value)
                with self.assertRaises(RuntimeError):
                    data.connect(123, 'test-password', 'Demo')
                setattr(info, field, original)
            self.assertTrue(data.connect(123, 'test-password', 'Demo'))

    def test_daily_loss_groups_partial_deals_and_filters_utc_day(self):
        with fake_broker() as (mt5, cls, _):
            ex = cls({'Test': 1001})
            now = T.replace(tzinfo=timezone.utc)
            def deal(ticket, pnl, position=1, magic=1001, timestamp=now):
                return SimpleNamespace(ticket=ticket, magic=magic, type=0, position_id=position,
                                       time=timestamp.timestamp(), profit=pnl, swap=0, commission=-1, fee=0)
            mt5.history_deals_get.return_value = [deal(1, -100), deal(2, 20), deal(3, -500, magic=0),
                                                deal(4, -500, timestamp=now-timedelta(days=1))]
            with patch.object(ex, '_mt5_timestamp_utc', side_effect=lambda ts: datetime.fromtimestamp(ts, timezone.utc)):
                self.assertEqual(ex.get_daily_loss(now), 82)
                self.assertEqual(ex.get_daily_loss(now), 82)
            mt5.history_deals_get.return_value = None
            with self.assertRaises(RuntimeError):
                ex.get_daily_loss(now)


class SimulatorRegressionTests(unittest.TestCase):
    def test_market_entry_bar_stop_is_applied(self):
        ex = SimulatedExecution(10000, spread_pips=0, commission_per_lot=0)
        place(ex)
        closed = ex.check_fills(bar(l=1.098))
        self.assertEqual(len(closed), 1)
        self.assertAlmostEqual(closed[0]['pnl'], -100)

    def test_market_entry_bar_target_is_applied(self):
        ex = SimulatedExecution(10000, spread_pips=0, commission_per_lot=0)
        place(ex)
        self.assertEqual(ex.check_fills(bar(h=1.103))[0]['exit_reason'], 'WIN')

    def test_both_levels_intrabar_assume_stop_first(self):
        ex = SimulatedExecution(10000, spread_pips=0, commission_per_lot=0)
        place(ex)
        self.assertEqual(ex.check_fills(bar(h=1.103, l=1.098))[0]['exit_reason'], 'LOSS')

    def test_stop_gap_fills_at_open(self):
        ex = SimulatedExecution(10000, spread_pips=0, commission_per_lot=0)
        place(ex)
        ex.check_fills(bar())
        trade = ex.check_fills(bar(T+timedelta(minutes=5), o=1.097, h=1.098, l=1.096, c=1.097))[0]
        self.assertAlmostEqual(trade['exit_price'], 1.097)
        self.assertAlmostEqual(trade['net_r'], -3)

    def test_tp_at_open_precedes_later_stop(self):
        ex = SimulatedExecution(10000, spread_pips=0, commission_per_lot=0)
        place(ex)
        ex.check_fills(bar())
        self.assertEqual(ex.check_fills(bar(T+timedelta(minutes=5), o=1.103, h=1.104, l=1.098))[0]['exit_reason'], 'WIN')

    def test_pending_limit_does_not_use_preentry_high_for_tp(self):
        ex = SimulatedExecution(10000, spread_pips=0, commission_per_lot=0)
        ex.check_fills(bar(o=1.101, h=1.101, l=1.101, c=1.101))
        place(ex, order_type='PENDING')
        closed = ex.check_fills(bar(T+timedelta(minutes=5), o=1.101, h=1.103, l=1.0995, c=1.1005))
        self.assertEqual(closed, [])
        self.assertEqual(len(ex._positions), 1)

    def test_pending_stop_gap_uses_worse_open(self):
        ex = SimulatedExecution(10000, spread_pips=0, commission_per_lot=0)
        ex.check_fills(bar(o=1.0995, h=1.0995, l=1.0995, c=1.0995))
        place(ex, order_type='PENDING')
        ex.check_fills(bar(T+timedelta(minutes=5), o=1.1005, h=1.1006, l=1.1004, c=1.1005))
        self.assertEqual(next(iter(ex._positions.values()))['entry_price'], 1.1005)

    def test_finer_stream_executes_h1_order_without_overlap(self):
        ex = SimulatedExecution(10000, spread_pips=0, commission_per_lot=0)
        fine = bar()
        coarse = bar(T-timedelta(hours=1), tf='H1', h=1.103, l=1.098)
        ex.configure_timeframes([fine, coarse])
        place(ex, entry_timeframe='H1', signal_time=T-timedelta(hours=1))
        self.assertEqual(ex.check_fills(bar(T-timedelta(minutes=5))), [])
        self.assertEqual(ex._positions, {})
        ex.check_fills(fine)
        self.assertEqual(len(ex._positions), 1)
        self.assertEqual(ex.check_fills(coarse), [])
        self.assertEqual(len(ex._positions), 1)

    def test_net_r_and_equity_include_costs(self):
        ex = SimulatedExecution(10000, spread_pips=0, commission_per_lot=7)
        place(ex)
        ex.check_fills(bar(c=1.0995))
        self.assertAlmostEqual(ex.get_equity(), 9943)
        trade = ex.check_fills(bar(T+timedelta(minutes=5), h=1.103))[0]
        self.assertAlmostEqual(trade['gross_r'], 2)
        self.assertAlmostEqual(trade['net_r'], 1.93)
        self.assertEqual(trade['r_multiple'], trade['net_r'])

    def test_usdjpy_risk_uses_historical_conversion(self):
        ex = SimulatedExecution(10000)
        self.assertAlmostEqual(ex.loss_per_lot('USDJPY', 'BUY', 150, 149), 100000/149)

    def test_rejected_market_fill_releases_portfolio_slot(self):
        engine = BacktestEngine(spread_pips=0)
        enriched = RiskManager(lambda: 10000).process(signal(take_profit=1.101))
        ticket = place(engine.execution, tp=1.101, risk_budget=50)
        engine.portfolio.record_open(enriched, ticket)
        engine.process_bar(bar(o=1.1008, h=1.1009, l=1.1007, c=1.1008))
        self.assertEqual(engine.portfolio.get_open_positions(), {})
        self.assertEqual(engine.execution.get_closed_trades(), [])


class DataAndValidationRegressionTests(unittest.TestCase):
    def test_recovered_closes_are_applied_at_the_right_bar_boundary(self):
        from utils.live_reconciliation import apply_trade_updates
        engine = SimpleNamespace(notify_trade_closed=Mock())
        trades = [dict(close_time=T+timedelta(minutes=10), ticket=2), dict(close_time=T, ticket=1)]
        remaining = apply_trade_updates(engine, trades, T+timedelta(minutes=5))
        self.assertEqual([t['ticket'] for t in remaining], [2])
        self.assertEqual(engine.notify_trade_closed.call_args.args[0]['ticket'], 1)
        self.assertEqual(apply_trade_updates(engine, remaining, T+timedelta(minutes=15)), [])

    def test_checkpoint_round_trip_preserves_strategy_state(self):
        from live_config import create_live_strategy_specs
        from utils.strategy_state import StrategyCheckpoint, encode
        with tempfile.TemporaryDirectory() as tmp:
            specs = create_live_strategy_specs()
            checkpoint = StrategyCheckpoint(Path(tmp)/'state.json', specs, {'login': 123})
            for strategy, symbols in specs:
                for symbol in symbols:
                    for tf in strategy.TIMEFRAMES:
                        strategy.generate_signal(bar(symbol=symbol, tf=tf))
            before = encode({s.NAME: s.__dict__ for s, _ in specs})
            cursor = {('EURUSD', 'M5'): T}
            checkpoint.save(cursor)
            restored_specs = create_live_strategy_specs()
            restored = StrategyCheckpoint(Path(tmp)/'state.json', restored_specs, {'login': 123})
            self.assertEqual(restored.load(), cursor)
            self.assertEqual(encode({s.NAME: s.__dict__ for s, _ in restored_specs}), before)
            wrong_account = StrategyCheckpoint(Path(tmp)/'state.json', create_live_strategy_specs(), {'login': 456})
            self.assertIsNone(wrong_account.load())

    def test_rejected_signal_releases_day_but_not_existing_order(self):
        from strategies.ny_index_opening_drive import NyIndexOpeningDriveStrategy
        strategy = NyIndexOpeningDriveStrategy()
        engine = BacktestEngine()
        engine.add_strategy(strategy, ['USTEC'])
        strategy._traded_day['USTEC'] = True
        proposal = signal(symbol='USTEC', strategy_name=strategy.NAME)
        engine.event_engine.reject_signal(proposal)
        self.assertFalse(strategy._traded_day['USTEC'])
        enriched = RiskManager(lambda: 10000).process(signal())
        enriched.symbol = 'USTEC'
        enriched.strategy_name = strategy.NAME
        engine.portfolio.record_open(enriched, 12)
        strategy._traded_day['USTEC'] = True
        engine.event_engine.reject_signal(proposal)
        self.assertTrue(strategy._traded_day['USTEC'])

    def test_partial_dispatch_retry_does_not_repeat_prior_strategy(self):
        engine = BacktestEngine()
        first = SimpleNamespace(NAME='First', TIMEFRAMES=['M5'], generate_signal=Mock(return_value=None))
        second = SimpleNamespace(NAME='Second', TIMEFRAMES=['M5'], generate_signal=Mock(side_effect=RuntimeError('test failure')))
        engine.add_strategy(first, ['EURUSD'])
        engine.add_strategy(second, ['EURUSD'])
        with self.assertRaises(RuntimeError):
            engine.event_engine.process_bar(bar())
        engine.event_engine.process_bar(bar())
        self.assertEqual(first.generate_signal.call_count, 1)
        self.assertEqual(second.generate_signal.call_count, 1)

    def test_unavailable_risk_data_releases_unsubmitted_proposal(self):
        engine = BacktestEngine()
        strategy = SimpleNamespace(NAME='Test', TIMEFRAMES=['M5'],
                                   generate_signal=Mock(return_value=signal()),
                                   notify_signal_rejected=Mock())
        engine.add_strategy(strategy, ['EURUSD'])
        with patch.object(engine.risk, 'process', side_effect=RuntimeError('quote unavailable')):
            with self.assertRaises(RuntimeError):
                engine.event_engine.process_bar(bar())
        strategy.notify_signal_rejected.assert_called_once_with('EURUSD')
        self.assertEqual(engine.execution.get_open_positions(), [])

    def test_outage_recovery_returns_all_missed_bars(self):
        with fake_broker() as (_, _, data):
            latest = bar(T+timedelta(minutes=15))
            recent = [bar(T+timedelta(minutes=i)) for i in (0, 5, 10, 15)]
            with patch.object(data, 'get_latest_completed_bar', return_value=latest), patch.object(data, 'get_recent_bars', return_value=recent):
                self.assertEqual([b.timestamp for b in data.get_completed_bars_since('EURUSD', 'M5', T)],
                                 [T+timedelta(minutes=i) for i in (5, 10, 15)])

    def test_outage_recovery_refuses_incomplete_history(self):
        with fake_broker() as (_, _, data):
            latest = bar(T+timedelta(minutes=15))
            with patch.object(data, 'get_latest_completed_bar', return_value=latest), patch.object(data, 'get_recent_bars', return_value=[latest]):
                with self.assertRaises(RuntimeError):
                    data.get_completed_bars_since('EURUSD', 'M5', T)

    def test_weekday_utc_is_not_shifted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'EURUSD_M5_20260907-20260908.csv'
            pd.DataFrame([dict(time=T, open=1.1, high=1.101, low=1.099, close=1.1)]).to_csv(path, index=False)
            self.assertEqual(load_csv(str(path))[0].timestamp, T)
            self.assertEqual(load_csv(str(path), time_basis='icmarkets')[0].timestamp, T-timedelta(hours=3))
            Path(str(path)+'.meta.json').write_text(json.dumps({'time_basis': 'icmarkets'}))
            self.assertEqual(load_csv(str(path))[0].timestamp, T-timedelta(hours=3))

    def test_asymmetric_news_window_and_cross_currency_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'news.csv'
            pd.DataFrame([dict(datetime_utc=T+timedelta(hours=4), currency='CHF', event='Test', impact='HIGH')]).to_csv(path,index=False)
            news = NewsFilter(str(path), block_hours_before=4, block_hours_after=1)
            self.assertTrue(news.is_blocked('USDCHF', T+timedelta(hours=1)))
            self.assertTrue(news.is_blocked('EURCHF', T+timedelta(hours=5)))
            self.assertFalse(news.is_blocked('USDCHF', T+timedelta(hours=7)))
            self.assertEqual(len(news.get_nearby_events('USDCHF', T+timedelta(hours=1))), 1)

    def test_walk_forward_passes_rr_to_ims(self):
        from walk_forward import build_strategy
        from strategies.ims import ImsStrategy
        strategy, rr = build_strategy(ImsStrategy, {'rr_ratio': 2.5})
        self.assertEqual(rr, 2.5)
        self.assertEqual(strategy.rr_ratio, 2.5)

    def test_walk_forward_no_losses_is_not_zero_profit_factor(self):
        from walk_forward import compute_metrics
        self.assertEqual(compute_metrics([{'r_multiple': 1.93, 'result': 'WIN'}])['pf'], float('inf'))

    def test_failed_combination_is_reported_as_error(self):
        from walk_forward import optimize
        class Broken:
            def __init__(self):
                raise ValueError('broken configuration')
        best, _, results = optimize([], T, T+timedelta(days=1), Broken, {}, {}, ['EURUSD'], 'expectancy')
        self.assertIsNone(best)
        self.assertEqual(results[0]['error'], 'broken configuration')

    def test_oos_warmup_cannot_place_training_orders(self):
        engine = BacktestEngine(spread_pips=0)
        strategy = SimpleNamespace(NAME='Test', TIMEFRAMES=['M5'], generate_signal=Mock(return_value=signal()))
        engine.add_strategy(strategy, ['EURUSD'])
        engine.replay([bar(T-timedelta(minutes=10)), bar(T-timedelta(minutes=5))], start_date=T)
        self.assertEqual(strategy.generate_signal.call_count, 2)
        self.assertEqual(engine.execution.get_open_positions(), [])

    def test_training_excludes_candles_closing_after_fold_end(self):
        from walk_forward import optimize
        completed = bar(T, tf='M5')
        incomplete = bar(T, tf='H4')
        strategy = SimpleNamespace(NAME='Test')
        with patch('walk_forward.build_strategy', return_value=(strategy, 2.5)), \
                patch('walk_forward.run_backtest', return_value={'trades': 0}) as run:
            optimize([completed, incomplete], T, T+timedelta(hours=1),
                     object, {}, {}, ['EURUSD'], 'expectancy')
        self.assertEqual(run.call_args.args[0], [completed])


if __name__ == '__main__':
    unittest.main()
