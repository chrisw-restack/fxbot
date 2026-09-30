"""Candle setup ownership, restart recovery, and executable stop regressions."""
from copy import deepcopy
import csv
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backtest_engine import BacktestEngine
from models import BarEvent
from risk.risk_manager import RiskManager
from risk.validation import valid_stop_distance
from strategies.candle_confirmation import CandleConfirmationStrategy
from utils.setup_ledger import SetupLedger
from utils.strategy_state import StrategyCheckpoint
from utils.trade_journal import TradeJournal
from utils.warmup import warmup_counts, warmup_days
from test_review_regressions import fake_broker, place, signal, bar
from execution.simulated_execution import SimulatedExecution

T = datetime(2024, 1, 8)
S = 'USDJPY'


def candle(minutes, o, h, l, c, tf='M5'):
    return BarEvent(S, tf, T + timedelta(minutes=minutes), o, h, l, c, 1)


def prepared():
    s = CandleConfirmationStrategy(fractal_n=1, min_sl_pips=8,
                                  tp_range_pct=1.25, sl_rr_ratio=1.5)
    e = BacktestEngine(spread_pips=.2)
    e.add_strategy(s, [S])
    e.process_bar(candle(0, 155, 156, 154, 154.5, 'H1'))
    e.process_bar(candle(60, 154.5, 156, 154, 155.1, 'H1'))
    for i, (h,l,c) in enumerate([(155,154.4,154.5),(155.6,154.8,155.1),
                                 (155.4,155,155.2),(155.5,155,155.3)]):
        e.process_bar(candle(120+5*i,c,h,l,c))
    return s,e


def submit(s,e,minute=140):
    e.process_bar(candle(minute,155.3,155.9,155.6,155.8))
    return dict(e.execution.get_open_positions()[0])


class CandleTrackingTests(unittest.TestCase):
    def test_pipeline_origin_attempt_and_fill_rejection_release_only_own_attempt(self):
        s,e = prepared()
        with TemporaryDirectory() as tmp:
            path = Path(tmp)/'journal.csv'
            e.event_engine.trade_journal = TradeJournal(str(path))
            order = submit(s,e)
            self.assertEqual(order['setup_id'], s._setup_id(S))
            self.assertIn('2024-01-08T02:20:00', order['attempt_id'])
            self.assertEqual(order['min_stop_distance'], .08)
            e.process_bar(candle(145,155.35,155.5,155.34,155.4))
            self.assertFalse(s._orders)
            self.assertFalse(s._signal_fired[S])
            self.assertFalse(e.execution.get_open_positions())
            self.assertEqual(e.execution.get_account_balance(), 10000)
            self.assertFalse(e.portfolio.get_open_positions())
            s.sync_order_state(order)
            self.assertFalse(s._orders)
            with path.open() as stream:
                rows = list(csv.DictReader(stream))
            rejected = next(r for r in rows if r['reason']=='minimum_stop_distance_at_fill')
            context = json.loads(rejected['context_json'])
            self.assertEqual(context['attempt_id'],order['attempt_id'])
            self.assertEqual(context['min_stop_distance'],.08)
            accepted = next(r for r in rows if r['event']=='ORDER_PLACED')
            accepted_context = json.loads(accepted['context_json'])
            self.assertEqual(accepted_context['pivot_level'],155.6)
            self.assertEqual(accepted_context['engulf_time_utc'],'2024-01-08T01:00:00')
            self.assertTrue(accepted_context['fresh_cross'])
            new_order = submit(s,e,150)
            # A later close beyond the pivot may propose again under existing rules.
            self.assertEqual(new_order['setup_id'], order['setup_id'])

    def test_proposal_rejection_does_not_remove_accepted_exposure(self):
        s,e = prepared()
        with patch.object(e.risk,'process',return_value=None):
            e.process_bar(candle(140,155.3,155.9,155.6,155.8))
        self.assertFalse(s._proposals)
        self.assertFalse(s._signal_fired[S])
        order = submit(s,e,145)
        before = deepcopy(s._orders)
        e.event_engine.reject_signal(SimpleNamespace(symbol=S,strategy_name=s.NAME,attempt_id='other'))
        self.assertEqual(before,s._orders)
        s.sync_order_state(dict(order,state='OPEN'))
        s.notify_proposal_rejected(SimpleNamespace(**order))
        self.assertEqual(len(s._orders),1)

    def test_old_outcome_cannot_clear_new_origin_and_duplicate_is_idempotent(self):
        for result in ('WIN','LOSS','BE'):
            s,e = prepared()
            order = submit(s,e)
            s._signal_fired[S] = False
            s._set_bias(S,'BUY',candle(180,154.5,156,154,155.2,'H1'))
            before = deepcopy(s._bias)
            s.notify_trade_closed(dict(order,result=result,is_final=True))
            self.assertEqual(s._bias,before)
            self.assertIn(order['setup_id'],s._finished_setups)
            self.assertFalse(s._orders)
            s.notify_trade_closed(dict(order,result=result,is_final=True))
            s.sync_order_state(dict(order,state='OPEN'))
            self.assertEqual(s._bias,before)
            self.assertFalse(s._orders)

    def test_final_close_expires_own_origin_for_win_loss_and_break_even(self):
        for result in ('WIN','LOSS','BE'):
            s,e = prepared()
            order = submit(s,e)
            s.notify_trade_closed(dict(order,result=result,is_final=True))
            self.assertIsNone(s._bias[S])
            s._set_bias(S,'BUY',candle(60,154.5,156,154,155.1,'H1'))
            self.assertIsNone(s._bias[S])

    def test_partial_fill_close_and_cancel_remainder_preserve_exposure(self):
        for reverse in (False,True):
            s,e = prepared()
            order = submit(s,e)
            position = dict(order,ticket=501,position_id=501,state='OPEN',open_time=T)
            snapshot = [order,position]
            e.event_engine.sync_order_states(snapshot[::-1] if reverse else snapshot)
            s.notify_trade_closed(dict(position,result='LOSS',is_final=False))
            s.notify_trade_closed(dict(position,result='LOSS',remaining_volume=.1))
            s.notify_order_cancelled(order)
            record = next(iter(s._orders.values()))
            self.assertEqual(record['state'],'OPEN')
            self.assertFalse(record['has_pending'])
            self.assertIsNone(s.generate_signal(candle(150,155.5,155.9,155.6,155.8)))

    def test_cancelled_pending_snapshot_ignored_but_racing_fill_adopted(self):
        s,e = prepared()
        order = submit(s,e)
        s.notify_order_cancelled(order)
        s.sync_order_state(order)
        self.assertFalse(s._orders)
        s.sync_order_state(dict(order,state='OPEN'))
        self.assertEqual(next(iter(s._orders.values()))['state'],'OPEN')

    def test_legacy_recovery_blocks_entries_without_guessing_origin(self):
        s,e = prepared()
        s.sync_order_state(dict(symbol=S,ticket=888,direction='BUY',state='OPEN'))
        before = deepcopy(s._bias)
        self.assertIsNone(s.generate_signal(candle(140,155.3,155.9,155.6,155.8)))
        s.notify_trade_closed(dict(symbol=S,ticket=888,result='LOSS'))
        self.assertEqual(s._bias,before)
        self.assertFalse(s._orders)

    def test_foreign_strategy_and_malformed_origin_are_not_adopted_as_own_setup(self):
        s,e = prepared()
        order = submit(s,e)
        restored,_ = prepared()
        restored.sync_order_state(dict(order,strategy_name='Other'))
        self.assertFalse(restored._orders)
        restored.sync_order_state(dict(order,setup_id=s.NAME+'|v1|not-json'))
        self.assertNotIn('setup_id',next(iter(restored._orders.values())))
        restored.notify_trade_closed(dict(order,setup_id='bad'))
        self.assertIsNotNone(restored._bias[S])

    def test_utc_setup_identity_and_reset(self):
        s,e = prepared()
        origin = s._setup_id(S)
        s._bias[S]['timestamp'] = datetime(2024,1,8,3,tzinfo=timezone(timedelta(hours=2)))
        self.assertEqual(origin,s._setup_id(S))
        submit(s,e)
        s.reset()
        self.assertFalse(s._orders)
        self.assertFalse(s._bias)
        self.assertFalse(s._entry_bars)
        self.assertFalse(s._finished_setups)

    def test_checkpoint_preserves_open_and_terminal_ownership(self):
        s,e = prepared()
        order = submit(s,e)
        with TemporaryDirectory() as tmp:
            a,b = CandleConfirmationStrategy(),CandleConfirmationStrategy()
            ca = StrategyCheckpoint(Path(tmp)/'state.json',[(a,[S])],{'login':1})
            cb = StrategyCheckpoint(Path(tmp)/'state.json',[(b,[S])],{'login':1})
            a.__dict__.update(deepcopy(s.__dict__))
            ca.save({(S,'M5'):T})
            self.assertEqual(cb.load(),{(S,'M5'):T})
            self.assertEqual(a._orders,b._orders)
            b.notify_trade_closed(dict(order,result='WIN'))
            cb.save({})
            ca.load()
            self.assertEqual(a._finished_setups,b._finished_setups)

    def test_ledger_recovers_attributed_close_without_checkpoint(self):
        s,e = prepared()
        order = submit(s,e)
        with TemporaryDirectory() as tmp:
            path = Path(tmp)/'ledger.json'
            ledger = SetupLedger(path,{'login':1})
            ledger.accept(order['ticket'],**{k:order[k] for k in
                ('symbol','direction','strategy_name','setup_id','attempt_id')})
            ledger.close(dict(order,result='LOSS',is_final=True))
            restored,_ = prepared()
            for trade in SetupLedger(path,{'login':1}).closed_trades():
                restored.notify_trade_closed(trade)
            self.assertIsNone(restored._bias[S])
            self.assertIn(order['setup_id'],restored._finished_setups)

    def test_warmup_requests_cover_ema_and_entry_history(self):
        s = CandleConfirmationStrategy(tf_trend='D1',ema_slow=50)
        counts = warmup_counts([(s,[S])])
        self.assertEqual(counts[S,'D1'],250)
        self.assertEqual(counts[S,'H1'],100)
        self.assertEqual(counts[S,'M5'],1200)
        self.assertGreaterEqual(warmup_days([(s,[S])]),385)
        s.ema_slow = 100
        self.assertEqual(s.warmup_requirements()['D1'],500)

    def test_csv_runner_loads_enough_calendar_history_for_declared_bars(self):
        s = CandleConfirmationStrategy(tf_trend='D1')
        e = BacktestEngine()
        e.add_strategy(s,[S])
        with patch('backtest_engine.load_csv',return_value=[]) as loader, \
             patch.object(e.trade_logger,'plot_equity_curve'), \
             patch.object(e.trade_logger,'print_summary'), \
             patch.object(e.trade_logger,'print_trade_log'):
            e.run('data.csv',start_date=T)
        self.assertGreaterEqual((T-loader.call_args.kwargs['start']).days,385)

    def test_oos_runner_loads_declared_warmup_without_training_orders(self):
        import walk_forward
        s = CandleConfirmationStrategy(tf_trend='D1')
        with patch.object(walk_forward,'build_strategy',return_value=(s,1.5)), \
             patch.object(walk_forward,'filter_bars',return_value=[]) as filtered, \
             patch.object(walk_forward,'run_backtest',return_value={}):
            walk_forward.test_oos([],T,T+timedelta(days=100),CandleConfirmationStrategy,{}, {},[S])
        self.assertGreaterEqual((T-filtered.call_args.kwargs['start']).days,385)


class ExecutableStopTests(unittest.TestCase):
    def test_distance_rejects_invalid_values_and_accepts_boundary(self):
        self.assertTrue(valid_stop_distance(1.1,1.099,.001))
        for minimum in (-1,float('nan'),float('inf'),'bad'):
            self.assertFalse(valid_stop_distance(1.1,1.099,minimum))
        self.assertTrue(valid_stop_distance(1.1,1.099,None))

    def test_risk_rechecks_quote_and_propagates_opt_in(self):
        s = signal(min_stop_distance=.002)
        self.assertIsNone(RiskManager(lambda:10000).process(s))
        r = RiskManager(lambda:10000,entry_price_fn=lambda s:1.101)
        out = r.process(signal(stop_loss=1.099,take_profit=1.105,min_stop_distance=.002))
        self.assertEqual(out.min_stop_distance,.002)
        self.assertIsNone(RiskManager(lambda:10000).process(signal()).min_stop_distance)

    def test_simulator_both_directions_reject_next_open_and_opt_out_is_unchanged(self):
        for direction in ('BUY','SELL'):
            ex = SimulatedExecution(10000,spread_pips=0)
            sl,tp = (1.099,1.102) if direction=='BUY' else (1.101,1.098)
            ticket = place(ex,direction=direction,sl=sl,tp=tp,min_stop_distance=.001)
            o = 1.0995 if direction=='BUY' else 1.1005
            ex.check_fills(bar(o=o,h=o+.0001,l=o-.0001,c=o))
            self.assertFalse(ex.get_open_positions())
            self.assertEqual(ex.take_rejected_orders()[0]['ticket'],ticket)
            self.assertEqual(ex.get_account_balance(),10000)
            ex = SimulatedExecution(10000,spread_pips=0)
            place(ex,direction=direction,sl=sl,tp=tp)
            ex.check_fills(bar(o=o,h=o+.0001,l=o-.0001,c=o))
            self.assertEqual(len(ex.get_open_positions()),1)

    def test_final_broker_quote_rejects_before_preflight_and_send(self):
        with fake_broker() as (fake, cls, _):
            ex = cls()
            self.assertEqual(place(ex,min_stop_distance=.002),0)
            fake.order_check.assert_not_called()
            fake.order_send.assert_not_called()
            self.assertEqual(ex.get_last_order_error()['stage'],'risk_validation')

    def test_broker_price_rounding_cannot_hide_short_stop(self):
        with fake_broker() as (fake, cls, _):
            fake.symbol_info_tick.return_value.ask = 1.100104
            ex = cls()
            # Raw distance is .001104, rounded request distance is .00110.
            self.assertEqual(place(ex,min_stop_distance=.001102),0)
            fake.order_send.assert_not_called()

    def test_acknowledged_slippage_is_logged_and_retains_real_ticket(self):
        with fake_broker() as (fake, cls, _):
            fake.order_send.side_effect = lambda req:SimpleNamespace(retcode=10009,order=123,price=1.0995,deal=456)
            ex = cls()
            self.assertEqual(place(ex,min_stop_distance=.001,setup_id='origin',attempt_id='attempt'),123)
            self.assertFalse(ex.get_last_order_details()['fill_stop_distance_valid'])
            self.assertEqual(ex.get_last_order_details()['fill_price_source'],'broker')
            self.assertIn('123',ex.setup_ledger.orders)
            self.assertEqual(fake.order_send.call_count,1)

    def test_broker_reported_boundary_fill_is_accepted(self):
        with fake_broker() as (fake, cls, _):
            ex = cls()
            self.assertEqual(place(ex,min_stop_distance=.0011),123)
            self.assertTrue(ex.get_last_order_details()['fill_stop_distance_valid'])

    def test_missing_broker_fill_price_is_unknown_and_exposure_is_retained(self):
        with fake_broker() as (fake, cls, _):
            fake.order_send.side_effect = lambda req:SimpleNamespace(retcode=10009,order=123,price=0,deal=456)
            ex = cls()
            self.assertEqual(place(ex,min_stop_distance=.001),123)
            self.assertIsNone(ex.get_last_order_details()['fill_stop_distance_valid'])
            self.assertEqual(ex.get_last_order_details()['fill_price_source'],'request')


if __name__ == '__main__':
    unittest.main()
