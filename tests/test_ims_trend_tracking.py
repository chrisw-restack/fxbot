"""IMS trend lifecycle regressions through the shared event/execution pipeline."""
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from models import BarEvent
from backtest_engine import BacktestEngine
from strategies.ims import ImsStrategy
from utils.strategy_state import StrategyCheckpoint
from utils.setup_ledger import SetupLedger
from utils.warmup import warmup_counts

SYMBOL = 'EURUSD'


def bar(hour=14, minute=0, low=1.113, high=1.116, close=1.115, tf='M15'):
    return BarEvent(SYMBOL,tf,datetime(2024,1,8,hour,minute),close,high,low,close,1)


def prepared(**options):
    s = ImsStrategy(tf_htf='H4',tf_ltf='M15',fractal_n=1,ltf_fractal_n=1,
                    ema_fast=0,ema_slow=0,tp_mode='rr',rr_ratio=2.5,
                    blocked_hours=(*range(0,12),*range(17,24)),**options)
    s.generate_signal(bar(11))
    s._htf_bias[SYMBOL] = dict(direction='BUY',swing_low=1.10,swing_high=1.12,
        dealing_50=1.11,fvg_level=1.102,_swing_ts=datetime(2024,1,7,8))
    e = BacktestEngine(rr_ratio=2.5)
    e.add_strategy(s,[SYMBOL])
    e.execution.configure_timeframes([bar(tf='M5')])
    e.process_bar(bar(11,55,tf='M5'))
    lows = [1.107,1.104,1.106,1.1085,1.110,1.109]
    highs = [1.109,1.108,1.110,1.112,1.114,1.112]
    closes = [1.108,1.107,1.109,1.111,1.113,1.111]
    for i,(lo,hi,c) in enumerate(zip(lows,highs,closes)):
        e.process_bar(bar(12+i//4,15*(i%4),lo,hi,c))
    return s,e


def submit(s,e):
    e.process_bar(bar(13,30,low=1.110))
    return dict(e.execution.get_open_positions()[0])


class ImsTrendTrackingTests(unittest.TestCase):
    def test_signal_has_stable_origin_and_attempt_and_rejection_releases_it(self):
        s,e = prepared()
        with patch.object(e.risk,'process',return_value=None):
            e.process_bar(bar(13,30,low=1.110))
        self.assertFalse(s._proposals)
        self.assertFalse(s._ltf_signal_fired[SYMBOL])
        e.process_bar(bar(13,45,low=1.113,high=1.117,close=1.116))
        order = e.execution.get_open_positions()[0]
        self.assertEqual(order['setup_id'],s._setup_id(SYMBOL))
        self.assertIn('2024-01-08T13:45:00',order['attempt_id'])
        before = deepcopy(s._orders)
        e.event_engine.reject_signal(SimpleNamespace(symbol=SYMBOL,strategy_name=s.NAME,attempt_id='other'))
        self.assertEqual(s._orders,before)

    def test_bid_touch_leaves_buy_pending_and_target_cancels_confirmed_order(self):
        s,e = prepared()
        order = submit(s,e)
        e.process_bar(bar(13,45,low=order['entry_price'],tf='M5'))
        self.assertIn(order['ticket'],e.execution._pending)
        e.process_bar(bar(14,low=1.114,high=1.123,close=1.120))
        self.assertFalse(s._orders)
        self.assertFalse(e.execution.get_open_positions())
        self.assertIn(order['setup_id'],s._retired_setups)

    def test_failed_cancel_keeps_accepted_order_and_blocks_new_entry(self):
        s,e = prepared()
        order = submit(s,e)
        with patch.object(e.execution,'cancel_pending_order',return_value=False):
            e.process_bar(bar(14,low=1.101,close=1.105))
        self.assertIsNone(s._htf_bias[SYMBOL])
        self.assertEqual(len(s._orders),1)
        self.assertTrue(next(iter(s._orders.values()))['cancel_requested'])
        self.assertEqual(next(iter(s._orders.values()))['setup_id'],order['setup_id'])
        e.event_engine.retry_pending_cancellations(now_monotonic=float('inf'))
        self.assertFalse(s._orders)

    def test_fill_before_cancel_retry_never_closes_position(self):
        s,e = prepared()
        submit(s,e)
        with patch.object(e.execution,'cancel_pending_order',return_value=False):
            e.process_bar(bar(14,low=1.101,close=1.105))
        e.process_bar(bar(14,15,low=1.108,tf='M5'))
        e.event_engine.retry_pending_cancellations(now_monotonic=float('inf'))
        self.assertEqual(len(e.execution._positions),1)
        self.assertEqual(next(iter(s._orders.values()))['state'],'OPEN')
        self.assertIsNone(s.generate_signal(bar(14,30)))

    def test_old_win_or_loss_does_not_reset_new_bias(self):
        for result in ('WIN','LOSS'):
            with self.subTest(result=result):
                s,e = prepared()
                order = submit(s,e)
                s._htf_bias[SYMBOL]['_swing_ts'] = datetime(2024,1,8,8)
                s._reset_ltf(SYMBOL)
                s._ltf_in_zone[SYMBOL] = True
                before = deepcopy(s._htf_bias)
                s.notify_trade_closed(dict(order,result=result,is_final=True))
                self.assertEqual(s._htf_bias,before)
                self.assertTrue(s._ltf_in_zone[SYMBOL])
                self.assertFalse(s._orders)
                s.notify_trade_closed(dict(order,result=result,is_final=True))
                self.assertEqual(s._htf_bias,before)

    def test_attributed_win_retires_origin_and_attributed_loss_preserves_it(self):
        for result in ('WIN','LOSS'):
            s,e = prepared()
            order = submit(s,e)
            s.notify_trade_closed(dict(order,result=result))
            self.assertEqual(order['setup_id'] in s._retired_setups,result=='WIN')
            self.assertEqual(s._htf_bias[SYMBOL] is None,result=='WIN')
            self.assertFalse(s._ltf_signal_fired[SYMBOL])

    def test_partial_fill_and_cancel_remainder_preserve_open_exposure(self):
        for reverse in (False,True):
            s,e = prepared()
            order = submit(s,e)
            position = dict(order,ticket=501,position_id=501,state='OPEN',open_time=datetime(2024,1,8,14))
            snapshot = [order,position]
            e.event_engine.sync_order_states(snapshot[::-1] if reverse else snapshot)
            s.notify_trade_closed(dict(position,result='LOSS',is_final=False))
            s.notify_order_cancelled(order)
            self.assertEqual(len(s._orders),1)
            self.assertEqual(next(iter(s._orders.values()))['state'],'OPEN')
            self.assertFalse(next(iter(s._orders.values()))['has_pending'])

    def test_stale_pending_after_cancel_is_ignored_but_racing_fill_is_adopted(self):
        s,e = prepared()
        order = submit(s,e)
        s.notify_order_cancelled(order)
        s.sync_order_state(order)
        self.assertFalse(s._orders)
        s.sync_order_state(dict(order,state='OPEN',open_time=datetime(2024,1,8,14)))
        self.assertEqual(next(iter(s._orders.values()))['state'],'OPEN')
        s.notify_trade_closed(dict(order,result='LOSS'))
        s.sync_order_state(dict(order,state='OPEN'))
        self.assertFalse(s._orders)

    def test_late_cancel_after_final_loss_does_not_retire_surviving_bias(self):
        s,e = prepared()
        order = submit(s,e)
        s.notify_trade_closed(dict(order,result='LOSS'))
        before = deepcopy(s._htf_bias)
        s.notify_order_cancelled(order)
        self.assertEqual(s._htf_bias,before)
        self.assertNotIn(order['setup_id'],s._retired_setups)

    def test_restored_obsolete_pending_cancels_without_touching_new_bias(self):
        s,e = prepared()
        order = submit(s,e)
        restored,_ = prepared()
        restored._htf_bias[SYMBOL]['_swing_ts'] = datetime(2024,1,8,8)
        restored.sync_order_state(order)
        cancel = restored.generate_signal(bar())
        self.assertEqual(cancel.direction,'CANCEL')
        self.assertEqual(cancel.attempt_id,order['attempt_id'])
        before = deepcopy(restored._htf_bias)
        restored.notify_order_cancelled(order)
        self.assertEqual(restored._htf_bias,before)

    def test_legacy_order_blocks_entry_and_close_does_not_guess_origin(self):
        s,e = prepared()
        s.sync_order_state(dict(symbol=SYMBOL,ticket=123,direction='BUY',state='OPEN'))
        before = deepcopy(s._htf_bias)
        e.process_bar(bar(13,30,low=1.110))
        self.assertFalse(e.execution.get_open_positions())
        s.notify_trade_closed(dict(symbol=SYMBOL,ticket=123,result='WIN'))
        self.assertEqual(s._htf_bias,before)
        self.assertFalse(s._orders)

    def test_pending_hours_policy_and_submitted_target(self):
        for policy in ('entry','all'):
            s,e = prepared(pending_cancel_hours=policy)
            order = submit(s,e)
            s._htf_bias[SYMBOL]['swing_high'] = 1.13
            e.process_bar(bar(18,low=1.117,high=order['tp']+.0001,close=1.119))
            self.assertEqual(bool(s._orders),policy=='entry')

    def test_open_position_never_uses_pending_target_cancellation(self):
        s,e = prepared(pending_cancel_hours='all')
        order = submit(s,e)
        e.process_bar(bar(13,45,low=1.108,tf='M5'))
        self.assertIsNone(s.generate_signal(bar(18,low=1.115,high=order['tp']+.0001,close=1.12)))
        self.assertEqual(len(s._orders),1)

    def test_checkpoint_preserves_cancel_intent_and_terminal_identities(self):
        s,e = prepared()
        order = submit(s,e)
        with patch.object(e.execution,'cancel_pending_order',return_value=False):
            e.process_bar(bar(14,low=1.101,close=1.105))
        with TemporaryDirectory() as tmp:
            # Fingerprints use initial state, so create both before assigning test state.
            initial = ImsStrategy()
            other = ImsStrategy()
            a = StrategyCheckpoint(Path(tmp)/'state.json',[(initial,[SYMBOL])],{'login':1})
            b = StrategyCheckpoint(Path(tmp)/'state.json',[(other,[SYMBOL])],{'login':1})
            initial.__dict__.update(deepcopy(s.__dict__))
            a.save({})
            self.assertEqual(b.load(),{})
            self.assertTrue(next(iter(other._orders.values()))['cancel_requested'])
            self.assertIn(order['setup_id'],other._retired_setups)

    def test_ledger_recovers_win_retirement_without_a_checkpoint(self):
        s,e = prepared()
        order = submit(s,e)
        with TemporaryDirectory() as tmp:
            path = Path(tmp)/'ledger.json'
            ledger = SetupLedger(path,{'login':1})
            ledger.accept(order['ticket'],**{k:order[k] for k in
                ('setup_id','attempt_id','symbol','direction','strategy_name')},state='PENDING')
            ledger.close(dict(order,result='WIN',close_time=datetime(2024,1,8,15)))
            restored,_ = prepared()
            for trade in SetupLedger(path,{'login':1}).closed_trades():
                restored.notify_trade_closed(trade)
            self.assertIn(order['setup_id'],restored._retired_setups)

    def test_expired_or_breached_origin_cannot_reactivate_for_either_direction(self):
        for mirror in (False,True):
            s = ImsStrategy(tf_htf='H4',tf_ltf='M15')
            lows = [100,101,99,90,93,96,99,92,89]
            highs = [105,110,104,95,99,108,112,106,100]
            candles = []
            for i,(lo,hi) in enumerate(zip(lows,highs)):
                if mirror:
                    lo,hi = 220-hi,220-lo
                candles.append(BarEvent(SYMBOL,'H4',datetime(2024,1,1)+timedelta(hours=4*i),
                                       (lo+hi)/2,hi,lo,(lo+hi)/2,1))
            for candle in candles[:7]:
                s.generate_signal(candle)
            origin = s._setup_id(SYMBOL)
            self.assertIsNotNone(origin)
            s.generate_signal(candles[7])
            self.assertIn(origin,s._retired_setups)
            s.generate_signal(candles[8])
            self.assertNotEqual(s._setup_id(SYMBOL),origin)
            # Also reject from a fresh scan with no retired-set memory.
            s._retired_setups.clear()
            self.assertIsNone(s._validated_candidate(candles,3,110,'SELL' if mirror else 'BUY'))

    def test_candidate_depth_uses_range_known_then_not_final_extended_range(self):
        s = ImsStrategy()
        candles = [BarEvent(SYMBOL,'H4',datetime(2024,1,1)+timedelta(hours=4*i),c,h,l,c,1)
                   for i,(l,h,c) in enumerate([(90,95,94),(95,105,104),(96,112,111),(98,115,114),(110,140,139)])]
        self.assertIsNotNone(s._validated_candidate(candles,0,110,'BUY'))
        candles[3].low = 95
        self.assertIsNone(s._validated_candidate(candles,0,110,'BUY'))

    def test_candidate_rejects_disrespected_formation_fvg(self):
        s = ImsStrategy()
        candles = [BarEvent(SYMBOL,'H4',datetime(2024,1,1)+timedelta(hours=4*i),c,h,l,c,1)
                   for i,(l,h,c) in enumerate([(90,105,104),(100,110,109),(106,112,111),(100,113,103)])]
        self.assertIsNotNone(s._validated_candidate(candles[:3],0,110,'BUY'))
        self.assertIsNone(s._validated_candidate(candles,0,110,'BUY'))

    def test_fresh_break_option_blocks_repeated_close_beyond_same_pivot(self):
        for fresh in (False,True):
            s,e = prepared(fresh_break_required=fresh)
            first = s.generate_signal(bar(13,30,low=1.110))
            self.assertIsNotNone(first)
            s.notify_proposal_rejected(first)
            second = s.generate_signal(bar(13,45,low=1.113,high=1.117,close=1.116))
            self.assertEqual(second is None,fresh)

    def test_reset_and_warmup_cover_ltf_invalidation_history(self):
        s,e = prepared()
        submit(s,e)
        counts = warmup_counts([(s,[SYMBOL])])
        self.assertEqual(counts[SYMBOL,'M15'],16*counts[SYMBOL,'H4'])
        s.reset()
        self.assertFalse(s._orders)
        self.assertFalse(s._retired_setups)


if __name__ == '__main__':
    unittest.main()
