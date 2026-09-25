"""Regression coverage for EmaFib order identity, fills, closes, and recovery."""
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backtest_engine import BacktestEngine
from models import BarEvent
from strategies.ema_fib_retracement import EmaFibRetracementStrategy
from utils.setup_ledger import SetupLedger
from utils.strategy_state import StrategyCheckpoint


SYMBOL = 'EURUSD'


def bar(hour, low=1.103, high=1.104, close=1.104, timeframe='H1', minute=0):
    return BarEvent(SYMBOL, timeframe, datetime(2024,1,8,hour,minute), close, high, low, close, 1)


def strategy():
    return EmaFibRetracementStrategy(fib_entry=.786, fib_tp=3., min_swing_pips=10,
        ema_sep_pct=.001, blocked_hours=(*range(20,24), *range(0,9)))


def prepared():
    s = strategy()
    s._init_symbol(SYMBOL)
    for tf in ('d1','h1'):
        getattr(s, f'_{tf}_ema_fast')[SYMBOL] = 1.104
        getattr(s, f'_{tf}_ema_slow')[SYMBOL] = 1.102
        getattr(s, f'_{tf}_bar_count')[SYMBOL] = 30
    s._h1_counter[SYMBOL] = 30
    s._d1_atr[SYMBOL] = .010
    s._swing_high[SYMBOL], s._swing_low[SYMBOL] = 1.105, 1.100
    s._swing_high_bar[SYMBOL], s._swing_low_bar[SYMBOL] = 28, 26
    s._swing_high_time[SYMBOL], s._swing_low_time[SYMBOL] = datetime(2024,1,8,6), datetime(2024,1,8,4)
    e = BacktestEngine()
    e.add_strategy(s, [SYMBOL])
    e.execution.configure_timeframes([bar(9,timeframe='M5')])
    e.process_bar(bar(9,timeframe='M5',minute=55))
    return s, e


class EmaFibTrackingTests(unittest.TestCase):
    def test_bid_touch_does_not_consume_unfilled_buy(self):
        s,e = prepared()
        e.process_bar(bar(9))
        order = e.execution.get_open_positions()[0]
        low = order['entry_price']-.000005
        e.process_bar(bar(10, low=low, timeframe='M5'))
        e.process_bar(bar(10, low=low))
        self.assertIn(order['ticket'], e.execution._pending)
        self.assertEqual(s._pending_entry[SYMBOL], order['entry_price'])
        s._d1_ema_fast[SYMBOL] = 1.100
        e.process_bar(bar(11))
        self.assertFalse(e.execution.get_open_positions())
        self.assertFalse(s._orders)

    def test_open_trade_cannot_overwrite_origin_and_loss_retires_original(self):
        s,e = prepared()
        e.process_bar(bar(9))
        order = e.execution.get_open_positions()[0]
        entry = order['entry_price']
        e.process_bar(bar(10, low=entry-.00005, timeframe='M5'))
        e.process_bar(bar(10, low=entry-.00005))
        s._swing_high[SYMBOL], s._swing_low[SYMBOL] = 1.108, 1.102
        e.process_bar(bar(11,low=1.104,high=1.106,close=1.105))
        self.assertFalse(s._proposals)
        self.assertEqual(len(e.execution.get_open_positions()), 1)
        self.assertEqual(next(iter(s._orders.values()))['swing'], (1.105,1.100))
        e.process_bar(bar(12,low=1.0999,close=1.100,timeframe='M5'))
        self.assertEqual((s._used_swing_high[SYMBOL],s._used_swing_low[SYMBOL]), (1.105,1.100))
        self.assertFalse(s._orders)
        self.assertIsNone(s._pending_entry[SYMBOL])

    def test_fill_and_stop_before_h1_clears_all_order_state(self):
        s,e = prepared()
        e.process_bar(bar(9))
        closed = e.process_bar(bar(10,low=1.0999,close=1.100,timeframe='M5'))
        self.assertEqual(len(closed),1)
        self.assertFalse(s._orders)
        self.assertFalse(s._proposals)
        self.assertIsNone(s._pending_entry[SYMBOL])
        self.assertIsNone(s._pending_direction[SYMBOL])

    def test_gap_fill_is_open_without_waiting_for_h1_straddle(self):
        s,e = prepared()
        e.process_bar(bar(9))
        e.process_bar(bar(10,low=1.1006,high=1.1009,close=1.1008,timeframe='M5'))
        self.assertEqual(next(iter(s._orders.values()))['state'],'OPEN')
        self.assertIsNone(s._pending_entry[SYMBOL])

    def test_rejected_proposal_does_not_own_slot(self):
        s,e = prepared()
        s._swing_high[SYMBOL] = 1.102
        e.process_bar(bar(9))
        self.assertFalse(s._orders)
        self.assertFalse(s._proposals)
        s._swing_high[SYMBOL] = 1.105
        e.process_bar(bar(10))
        self.assertEqual(len(s._orders),1)

    def test_rejecting_unrelated_proposal_preserves_accepted_order(self):
        s,e = prepared()
        e.process_bar(bar(9))
        before = deepcopy(s._orders)
        e.event_engine.reject_signal(SimpleNamespace(symbol=SYMBOL,strategy_name=s.NAME,attempt_id='unsubmitted'))
        self.assertEqual(s._orders,before)

    def test_cancellation_failure_keeps_identity_until_confirmed(self):
        s,e = prepared()
        e.process_bar(bar(9))
        s._d1_ema_fast[SYMBOL] = 1.100
        with patch.object(e.execution,'cancel_pending_order',return_value=False):
            e.process_bar(bar(20))
        self.assertEqual(len(s._orders),1)
        self.assertIsNotNone(s._pending_entry[SYMBOL])
        e.event_engine.retry_pending_cancellations(now_monotonic=float('inf'))
        self.assertFalse(s._orders)
        self.assertIsNone(s._pending_entry[SYMBOL])

    def test_fill_before_cancel_retry_is_kept_open(self):
        s,e = prepared()
        e.process_bar(bar(9))
        s._d1_ema_fast[SYMBOL] = 1.100
        with patch.object(e.execution,'cancel_pending_order',return_value=False):
            e.process_bar(bar(10))
        e.process_bar(bar(11,low=1.101,high=1.104,timeframe='M5'))
        e.event_engine.retry_pending_cancellations(now_monotonic=float('inf'))
        self.assertEqual(next(iter(s._orders.values()))['state'],'OPEN')
        self.assertEqual(len(e.execution.get_open_positions()),1)

    def test_partial_close_and_cancelled_remainder_keep_open_position(self):
        s,e = prepared()
        e.process_bar(bar(9))
        order = dict(e.execution.get_open_positions()[0])
        s.sync_order_state(dict(order,state='OPEN',has_pending=True))
        s.notify_trade_closed(dict(order,result='LOSS',is_final=False))
        s.notify_order_cancelled(order)
        self.assertEqual(next(iter(s._orders.values()))['state'],'OPEN')
        self.assertFalse(next(iter(s._orders.values()))['has_pending'])

    def test_win_and_break_even_clear_without_retiring_swing(self):
        for result in ('WIN','BE'):
            with self.subTest(result=result):
                s,e = prepared()
                e.process_bar(bar(9))
                s.notify_trade_closed(dict(e.execution.get_open_positions()[0],result=result,close_time=datetime(2024,1,8,10)))
                self.assertFalse(s._orders)
                self.assertIsNone(s._pending_entry[SYMBOL])
                self.assertIsNone(s._used_swing_high[SYMBOL])

    def test_duplicate_close_with_and_without_attribution_is_idempotent(self):
        s,e = prepared()
        e.process_bar(bar(9))
        trade = dict(e.execution.get_open_positions()[0],result='LOSS',close_time=datetime(2024,1,8,10))
        s.notify_trade_closed(trade)
        before = s._cooldown_until[SYMBOL]
        s._h1_counter[SYMBOL] += 4
        s.notify_trade_closed({k:v for k,v in trade.items() if k not in ('attempt_id','setup_id')})
        self.assertEqual(s._cooldown_until[SYMBOL],before)
        s.sync_order_state(trade)
        self.assertFalse(s._orders)

    def test_ledger_recovers_original_swing_without_checkpoint(self):
        s,e = prepared()
        e.process_bar(bar(9))
        order = dict(e.execution.get_open_positions()[0])
        with TemporaryDirectory() as folder:
            path = Path(folder)/'ledger.json'
            ledger = SetupLedger(path, {'login':1})
            ledger.accept(order['ticket'],**{k:order[k] for k in
                ('symbol','strategy_name','direction','setup_id','attempt_id','submitted_tp')})
            context = SetupLedger(path,{'login':1}).context(order)
        restored = strategy()
        restored.sync_order_state(dict(order,**context))
        self.assertEqual(next(iter(restored._orders.values()))['swing'], (1.105,1.100))
        restored.notify_trade_closed(dict(order,result='LOSS',close_time=datetime(2024,1,8,10)))
        self.assertEqual(restored._used_swing_high[SYMBOL],1.105)

    def test_checkpoint_roundtrip_retains_active_origin(self):
        s,e = prepared()
        with TemporaryDirectory() as folder:
            path = Path(folder)/'state.json'
            # Fingerprints use constructor state, before warming or accepting.
            fresh = strategy()
            writer = StrategyCheckpoint(path,[(fresh,[SYMBOL])],{'login':1})
            e.process_bar(bar(9))
            fresh.__dict__.update(deepcopy(s.__dict__))
            writer.save({(SYMBOL,'H1'):datetime(2024,1,8,9)})
            restored = strategy()
            reader = StrategyCheckpoint(path,[(restored,[SYMBOL])],{'login':1})
            self.assertIsNotNone(reader.load())
            self.assertEqual(restored._orders,s._orders)

    def test_late_ledger_attribution_recovers_previously_unknown_origin(self):
        s,e = prepared()
        e.process_bar(bar(9))
        order = dict(e.execution.get_open_positions()[0])
        restored = strategy()
        restored.sync_order_state({k:v for k,v in order.items() if k not in
                                   ('setup_id','attempt_id','origin_order_ticket')})
        self.assertIsNone(next(iter(restored._orders.values()))['swing'])
        restored.sync_order_state(order)
        self.assertEqual(len(restored._orders),1)
        self.assertEqual(set(restored._orders), {order['attempt_id']})
        self.assertEqual(next(iter(restored._orders.values()))['swing'],(1.105,1.100))

    def test_legacy_pending_recovers_cancellation_without_inventing_swing(self):
        s,e = prepared()
        order = dict(ticket=123,symbol=SYMBOL,strategy_name=s.NAME,direction='BUY',open_price=1.101,
                     state='PENDING',open_time=None)
        e.event_engine.sync_order_states([order])
        self.assertEqual(len(s._orders),1)
        self.assertIsNone(next(iter(s._orders.values()))['swing'])
        s._d1_ema_fast[SYMBOL] = 1.100
        signal = s.generate_signal(bar(20))
        self.assertEqual(signal.direction,'CANCEL')
        s.notify_trade_closed(dict(order,result='LOSS',close_time=datetime(2024,1,8,21)))
        self.assertIsNone(s._used_swing_high[SYMBOL])
        self.assertFalse(s._orders)

    def test_stale_recovered_close_does_not_start_new_cooldown_or_clear_new_order(self):
        s,e = prepared()
        e.process_bar(bar(9))
        old = dict(e.execution.get_open_positions()[0],ticket=999,origin_order_ticket=999,attempt_id='old',
                   result='LOSS',close_time=datetime(2024,1,1))
        s._h1_close_times[SYMBOL].extend(datetime(2024,1,8)+timedelta(hours=i) for i in range(11))
        before = deepcopy(s._orders)
        s.notify_trade_closed(old)
        self.assertEqual(s._orders,before)
        self.assertLessEqual(s._cooldown_until[SYMBOL],s._h1_counter[SYMBOL])

    def test_older_out_of_order_loss_does_not_replace_latest_used_swing(self):
        s,e = prepared()
        e.process_bar(bar(9))
        trade = dict(e.execution.get_open_positions()[0],result='LOSS',close_time=datetime(2024,1,8,10))
        s.notify_trade_closed(trade)
        s.notify_trade_closed(dict(trade,ticket=999,origin_order_ticket=999,attempt_id='older',
                                   close_time=datetime(2024,1,1),setup_id=None))
        self.assertEqual(s._used_swing_high[SYMBOL],1.105)


if __name__ == '__main__':
    unittest.main()
