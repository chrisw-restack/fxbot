"""Running lifecycle regressions through the normal event/execution pipeline."""
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backtest_engine import BacktestEngine
from models import BarEvent
from strategies.ema_fib_running import EmaFibRunningStrategy
from utils.setup_ledger import SetupLedger
from utils.strategy_state import StrategyCheckpoint

SYMBOL = 'EURUSD'


def bar(hour,low=1.110,high=1.115,close=1.114,timeframe='H1',minute=0,open_=None):
    return BarEvent(SYMBOL,timeframe,datetime(2024,1,8,hour,minute),
                    close if open_ is None else open_,high,low,close,1)


def strategy(**kwargs):
    return EmaFibRunningStrategy(fib_entry=.786,fib_tp=2.5,fractal_n=2,min_swing_pips=30,
        ema_sep_pct=0.,cooldown_bars=kwargs.pop('cooldown_bars',0),
        blocked_hours=(*range(20,24),*range(0,9)),**kwargs)


def prepared(**kwargs):
    s=strategy(**kwargs)
    s._init_symbol(SYMBOL)
    for tf in ('d1','h1'):
        getattr(s,f'_{tf}_ema_fast')[SYMBOL]=1.114
        getattr(s,f'_{tf}_ema_slow')[SYMBOL]=1.110
        getattr(s,f'_{tf}_bar_count')[SYMBOL]=30
    s._h1_counter[SYMBOL]=30
    s._d1_atr[SYMBOL]=.010
    s._fractal_low[SYMBOL],s._fractal_low_body[SYMBOL]=1.100,1.102
    s._fractal_high[SYMBOL],s._fractal_high_body[SYMBOL]=1.120,1.118
    s._fractal_low_bar[SYMBOL],s._fractal_high_bar[SYMBOL]=26,28
    s._fractal_low_time[SYMBOL],s._fractal_high_time[SYMBOL]=datetime(2024,1,8,4),datetime(2024,1,8,6)
    s._running_high[SYMBOL],s._running_low[SYMBOL]=1.115,1.105
    s._fvg_since_fractal_low[SYMBOL]=s._fvg_since_fractal_high[SYMBOL]=True
    e=BacktestEngine()
    e.add_strategy(s,[SYMBOL])
    e.execution.configure_timeframes([bar(9,timeframe='M5')])
    e.process_bar(bar(9,timeframe='M5',minute=55))
    return s,e


class RunningTrackingTests(unittest.TestCase):
    def test_bid_touch_does_not_consume_unfilled_buy_or_prevent_cancel(self):
        s,e=prepared()
        e.process_bar(bar(9))
        order=e.execution.get_open_positions()[0]
        low=order['entry_price']-.000005
        e.process_bar(bar(10,low=low,timeframe='M5'))
        e.process_bar(bar(10,low=low))
        self.assertIn(order['ticket'],e.execution._pending)
        self.assertEqual(s._pending_entry[SYMBOL],order['entry_price'])
        s._d1_ema_fast[SYMBOL]=1.100
        e.process_bar(bar(20))
        self.assertFalse(e.execution.get_open_positions())
        self.assertFalse(s._orders)

    def test_open_trade_cannot_replace_origin_and_loss_retires_original(self):
        s,e=prepared()
        e.process_bar(bar(9))
        order=e.execution.get_open_positions()[0]
        e.process_bar(bar(10,low=order['entry_price']-.00005,timeframe='M5'))
        e.process_bar(bar(10,low=order['entry_price']-.00005))
        s._fractal_low[SYMBOL],s._fractal_low_body[SYMBOL],s._running_high[SYMBOL]=1.102,1.104,1.120
        e.process_bar(bar(11))
        self.assertFalse(s._proposals)
        self.assertEqual(next(iter(s._orders.values()))['anchor'],1.100)
        e.process_bar(bar(12,low=1.0999,close=1.100,timeframe='M5'))
        self.assertEqual(s._used_fractal_low[SYMBOL],1.100)
        self.assertIsNone(s._used_fractal_high[SYMBOL])
        self.assertFalse(s._orders)

    def test_fill_and_stop_before_h1_clears_pending(self):
        s,e=prepared()
        e.process_bar(bar(9))
        closed=e.process_bar(bar(10,low=1.0999,close=1.100,timeframe='M5'))
        self.assertEqual(len(closed),1)
        self.assertFalse(s._orders)
        self.assertIsNone(s._pending_entry[SYMBOL])

    def test_gap_fill_is_open_without_h1_straddle(self):
        s,e=prepared()
        e.process_bar(bar(9))
        e.process_bar(bar(10,low=1.102,high=1.104,close=1.103,timeframe='M5'))
        self.assertEqual(next(iter(s._orders.values()))['state'],'OPEN')
        self.assertIsNone(s._pending_entry[SYMBOL])

    def test_rejected_proposal_releases_only_its_proposal(self):
        s,e=prepared()
        with patch.object(e.risk,'process',return_value=None):
            e.process_bar(bar(9))
        self.assertFalse(s._orders)
        self.assertFalse(s._proposals)
        e.process_bar(bar(10))
        before=deepcopy(s._orders)
        e.event_engine.reject_signal(SimpleNamespace(symbol=SYMBOL,strategy_name=s.NAME,attempt_id='other'))
        self.assertEqual(s._orders,before)

    def test_failed_reprice_retains_order_until_confirmed_then_new_attempt(self):
        s,e=prepared()
        e.process_bar(bar(9))
        first=dict(e.execution.get_open_positions()[0])
        with patch.object(e.execution,'cancel_pending_order',return_value=False):
            e.process_bar(bar(10,high=1.119,close=1.118))
        self.assertEqual(s._pending_entry[SYMBOL],first['entry_price'])
        self.assertEqual(len(s._orders),1)
        e.event_engine.retry_pending_cancellations(now_monotonic=float('inf'))
        self.assertFalse(s._orders)
        e.process_bar(bar(11,high=1.119,close=1.118))
        second=e.execution.get_open_positions()[0]
        self.assertNotEqual(first['attempt_id'],second['attempt_id'])
        self.assertGreater(second['entry_price'],first['entry_price']+.0001)

    def test_fill_before_cancel_retry_keeps_filled_position(self):
        s,e=prepared()
        e.process_bar(bar(9))
        s._d1_ema_fast[SYMBOL]=1.100
        with patch.object(e.execution,'cancel_pending_order',return_value=False):
            e.process_bar(bar(10))
        e.process_bar(bar(11,low=1.103,close=1.110,timeframe='M5'))
        e.event_engine.retry_pending_cancellations(now_monotonic=float('inf'))
        self.assertEqual(next(iter(s._orders.values()))['state'],'OPEN')
        self.assertEqual(len(e.execution.get_open_positions()),1)

    def test_partial_close_and_remainder_cancel_do_not_release_filled_slot(self):
        for pending_first in (True,False):
            with self.subTest(pending_first=pending_first):
                s,e=prepared()
                e.process_bar(bar(9))
                order=dict(e.execution.get_open_positions()[0])
                position=dict(order,ticket=501,position_id=501,state='OPEN',open_time=datetime(2024,1,8,10))
                snapshot=[order,position] if pending_first else [position,order]
                e.event_engine.sync_order_states(snapshot)
                self.assertEqual(len(s._orders),1)
                self.assertTrue(next(iter(s._orders.values()))['has_pending'])
                s.notify_trade_closed(dict(position,result='LOSS',is_final=False))
                s.notify_order_cancelled(order)
                record=next(iter(s._orders.values()))
                self.assertEqual(record['state'],'OPEN')
                self.assertFalse(record['has_pending'])
                self.assertIsNone(s._used_fractal_low[SYMBOL])
                s.notify_trade_closed(dict(position,result='LOSS',is_final=True))
                self.assertFalse(s._orders)
                self.assertEqual(s._used_fractal_low[SYMBOL],1.100)

    def test_win_and_break_even_clear_without_invalidation(self):
        for result in ('WIN','BE'):
            with self.subTest(result=result):
                s,e=prepared()
                e.process_bar(bar(9))
                s.notify_trade_closed(dict(e.execution.get_open_positions()[0],result=result))
                self.assertFalse(s._orders)
                self.assertIsNone(s._pending_entry[SYMBOL])
                self.assertIsNone(s._used_fractal_low[SYMBOL])

    def test_duplicate_close_and_stale_snapshot_cannot_change_state(self):
        s,e=prepared(cooldown_bars=10)
        e.process_bar(bar(9))
        trade=dict(e.execution.get_open_positions()[0],result='LOSS',close_time=datetime(2024,1,8,10))
        s.notify_trade_closed(trade)
        cooldown=s._cooldown_until[SYMBOL]
        s._h1_counter[SYMBOL]+=5
        legacy={k:v for k,v in trade.items() if k not in ('setup_id','attempt_id')}
        s.notify_trade_closed(legacy)
        s.sync_order_state(legacy)
        self.assertEqual(s._cooldown_until[SYMBOL],cooldown)
        self.assertFalse(s._orders)

    def test_cancelled_snapshot_cannot_resurrect_with_different_attribution(self):
        s,e=prepared()
        e.process_bar(bar(9))
        order=dict(e.execution.get_open_positions()[0])
        s.notify_order_cancelled(order)
        s.sync_order_state({k:v for k,v in order.items() if k not in ('setup_id','attempt_id')})
        self.assertFalse(s._orders)

    def test_partial_fill_discovered_after_remainder_cancel_is_adopted(self):
        s,e=prepared()
        e.process_bar(bar(9))
        order=dict(e.execution.get_open_positions()[0])
        # A fill can occur between the last snapshot and broker removal of its remainder.
        s.notify_order_cancelled(order)
        position=dict(order,ticket=501,position_id=501,state='OPEN',open_time=datetime(2024,1,8,10))
        e.event_engine.sync_order_states([position])
        self.assertEqual(len(s._orders),1)
        self.assertEqual(next(iter(s._orders.values()))['anchor'],1.100)
        self.assertEqual(next(iter(s._orders.values()))['state'],'OPEN')
        self.assertIsNone(s.generate_signal(bar(11)))
        s.notify_trade_closed(dict(position,result='LOSS',is_final=True))
        s.sync_order_state(position)
        self.assertFalse(s._orders)
        self.assertEqual(s._used_fractal_low[SYMBOL],1.100)

    def test_ledger_recovers_anchor_and_late_attribution_upgrades_legacy_record(self):
        s,e=prepared()
        e.process_bar(bar(9))
        order=dict(e.execution.get_open_positions()[0])
        with TemporaryDirectory() as folder:
            path=Path(folder)/'ledger.json'
            ledger=SetupLedger(path,{'login':1})
            ledger.accept(order['ticket'],**{k:order[k] for k in
                ('symbol','strategy_name','direction','setup_id','attempt_id','submitted_tp')})
            context=SetupLedger(path,{'login':1}).context(order)
        restored=strategy()
        restored.sync_order_state({k:v for k,v in order.items() if k not in ('setup_id','attempt_id')})
        self.assertIsNone(next(iter(restored._orders.values()))['anchor'])
        restored.sync_order_state(dict(order,**context))
        self.assertEqual(set(restored._orders),{order['attempt_id']})
        self.assertEqual(next(iter(restored._orders.values()))['anchor'],1.100)
        restored.notify_trade_closed(dict(order,result='LOSS'))
        self.assertEqual(restored._used_fractal_low[SYMBOL],1.100)

    def test_checkpoint_roundtrip_preserves_order_and_terminal_identity(self):
        s,e=prepared()
        with TemporaryDirectory() as folder:
            path=Path(folder)/'state.json'
            fresh=strategy()
            writer=StrategyCheckpoint(path,[(fresh,[SYMBOL])],{'login':1})
            e.process_bar(bar(9))
            fresh.__dict__.update(deepcopy(s.__dict__))
            writer.save({(SYMBOL,'H1'):datetime(2024,1,8,9)})
            restored=strategy()
            reader=StrategyCheckpoint(path,[(restored,[SYMBOL])],{'login':1})
            self.assertIsNotNone(reader.load())
            self.assertEqual(restored._orders,s._orders)
            trade=dict(e.execution.get_open_positions()[0],result='LOSS',close_time=datetime(2024,1,8,10))
            fresh.notify_trade_closed(trade)
            writer.save({(SYMBOL,'H1'):datetime(2024,1,8,9)})
            closed_state=strategy()
            closed_reader=StrategyCheckpoint(path,[(closed_state,[SYMBOL])],{'login':1})
            self.assertIsNotNone(closed_reader.load())
            self.assertEqual(closed_state._processed_closes,fresh._processed_closes)
            self.assertEqual(closed_state._last_loss_time,fresh._last_loss_time)
            before=deepcopy(closed_state.__dict__)
            closed_state.notify_trade_closed(trade)
            self.assertEqual(closed_state.__dict__,before)

    def test_legacy_order_can_cancel_but_loss_never_guesses_current_anchor(self):
        s,e=prepared()
        order=dict(ticket=123,symbol=SYMBOL,strategy_name=s.NAME,direction='BUY',open_price=1.104782,
                   state='PENDING',open_time=None)
        e.event_engine.sync_order_states([order])
        self.assertEqual(len(s._orders),1)
        s._d1_ema_fast[SYMBOL]=1.100
        self.assertEqual(s.generate_signal(bar(20)).direction,'CANCEL')
        s.notify_trade_closed(dict(order,result='LOSS'))
        self.assertIsNone(s._used_fractal_low[SYMBOL])
        self.assertIsNone(s._used_fractal_high[SYMBOL])
        self.assertFalse(s._orders)

    def test_stale_loss_does_not_restart_cooldown_or_clear_new_order(self):
        s,e=prepared(cooldown_bars=10)
        e.process_bar(bar(9))
        old=dict(e.execution.get_open_positions()[0],ticket=999,origin_order_ticket=999,attempt_id='old',
                 result='LOSS',close_time=datetime(2024,1,1))
        s._h1_close_times[SYMBOL].extend(datetime(2024,1,8)+timedelta(hours=i) for i in range(11))
        before=deepcopy(s._orders)
        s.notify_trade_closed(old)
        self.assertEqual(s._orders,before)
        self.assertLessEqual(s._cooldown_until[SYMBOL],s._h1_counter[SYMBOL])

    def test_sell_loss_invalidates_only_accepted_high_anchor(self):
        s,e=prepared()
        for tf in ('d1','h1'):
            getattr(s,f'_{tf}_ema_fast')[SYMBOL]=1.108
            getattr(s,f'_{tf}_ema_slow')[SYMBOL]=1.112
        e.process_bar(bar(9,low=1.105,high=1.112,close=1.108))
        order=e.execution.get_open_positions()[0]
        s._fractal_high[SYMBOL]=1.125
        s.notify_trade_closed(dict(order,result='LOSS'))
        self.assertEqual(s._used_fractal_high[SYMBOL],1.120)
        self.assertIsNone(s._used_fractal_low[SYMBOL])


if __name__=='__main__':
    unittest.main()
