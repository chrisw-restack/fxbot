import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from backtest_engine import BacktestEngine
from models import BarEvent, Signal
from risk.risk_manager import RiskManager
from strategies.ims_reversal import ImsReversalStrategy
from utils.setup_ledger import SetupLedger
from utils.strategy_state import StrategyCheckpoint
from utils.trade_journal import TradeJournal
from utils.live_reconciliation import recover_offline_journal_orders, apply_trade_updates
from test_review_regressions import fake_broker, place

T = datetime(2020, 1, 6, 12)


def bar(t=T, tf='M15', low=1.114, high=1.117, close=1.116):
    return BarEvent('EURUSD', tf, t, close, high, low, close, 0)


def seeded(**kwargs):
    s = ImsReversalStrategy(**kwargs)
    s.generate_signal(bar(tf='H4'))
    s._htf_bias['EURUSD'] = dict(direction='BUY', swing_low=1.10, swing_high=1.12,
        dealing_50=1.11, fvg_level=1.102, _swing_ts=T-timedelta(days=1))
    return s


def order(s, ticket=1, setup=None, state='PENDING'):
    setup = setup or s._setup_id('EURUSD')
    return dict(ticket=ticket, origin_order_ticket=ticket, setup_id=setup,
                attempt_id=setup+'|attempt'+str(ticket), symbol='EURUSD', strategy_name=s.NAME,
                direction='SELL', submitted_tp=1.11, state=state)


def loss(s, ticket=1, setup=None):
    return dict(order(s, ticket, setup), result='LOSS', pnl=-50, close_time=T, is_final=True)


class SetupIdentityTests(unittest.TestCase):
    def test_range_extension_keeps_identity_new_origin_changes_it(self):
        s=seeded(); original=s._setup_id('EURUSD')
        s._htf_bias['EURUSD']['swing_high']=1.13
        self.assertEqual(s._setup_id('EURUSD'), original)
        s._htf_bias['EURUSD']['_swing_ts']+=timedelta(hours=4)
        self.assertNotEqual(s._setup_id('EURUSD'), original)

    def test_old_trade_retires_its_setup_without_resetting_new_setup(self):
        s=seeded(); close=loss(s)
        s._htf_bias['EURUSD']['_swing_ts']+=timedelta(hours=4)
        newer=s._setup_id('EURUSD');s._ltf_signal_fired['EURUSD']=True
        s.notify_trade_closed(close)
        self.assertIn(close['setup_id'],s._retired_setups)
        self.assertEqual(s._setup_id('EURUSD'),newer)
        self.assertTrue(s._ltf_signal_fired['EURUSD'])
        self.assertNotIn(newer,s._setup_losses)

    def test_real_scanner_does_not_revive_losing_origin(self):
        s=ImsReversalStrategy(max_losses_per_bias=1)
        levels=[(1.099,1.101,1.100),(1.100,1.108,1.104),(1.097,1.103,1.098),
                (1.090,1.097,1.093),(1.096,1.106,1.105),(1.108,1.114,1.113)]
        for i,(lo,hi,cl) in enumerate(levels):
            s.generate_signal(bar(T+timedelta(hours=4*i), 'H4', lo,hi,cl))
        setup=s._setup_id('EURUSD');self.assertIsNotNone(setup)
        s.notify_trade_closed(loss(s))
        s.generate_signal(bar(T+timedelta(hours=24),'H4',1.110,1.115,1.114))
        self.assertNotEqual(s._setup_id('EURUSD'),setup)

    def test_duplicate_close_and_partial_close_do_not_consume_extra_losses(self):
        s=seeded(max_losses_per_bias=2);trade=loss(s)
        s.notify_trade_closed(dict(trade,is_final=False))
        s.notify_trade_closed(dict(trade,remaining_volume=.1))
        self.assertEqual(s._setup_losses,{})
        s.notify_trade_closed(trade);s.notify_trade_closed(trade)
        self.assertEqual(s._setup_losses[trade['setup_id']],1)
        self.assertNotIn(trade['setup_id'],s._retired_setups)
        s.notify_trade_closed(dict(trade,ticket=2,origin_order_ticket=2))
        self.assertIn(trade['setup_id'],s._retired_setups)

    def test_unknown_legacy_close_never_charges_active_setup(self):
        s=seeded();setup=s._setup_id('EURUSD');trade=loss(s);trade.pop('setup_id')
        with self.assertLogs('strategies.ims_setup_tracking',level='WARNING'):
            s.notify_trade_closed(trade)
        self.assertEqual(s._setup_id('EURUSD'),setup)
        self.assertEqual(s._setup_losses,{})

    def test_checkpoint_preserves_retired_identity_and_applied_close_ids(self):
        with tempfile.TemporaryDirectory() as folder:
            s=ImsReversalStrategy();spec=[(s,['EURUSD'])]
            checkpoint=StrategyCheckpoint(Path(folder)/'state.json',spec,{'login':1})
            s.generate_signal(bar(tf='H4'))
            s._htf_bias['EURUSD']=seeded()._htf_bias['EURUSD'].copy()
            trade=loss(s);s.notify_trade_closed(trade);checkpoint.save({('EURUSD','M15'):T})
            restored=ImsReversalStrategy()
            self.assertIsNotNone(StrategyCheckpoint(Path(folder)/'state.json',[(restored,['EURUSD'])],{'login':1}).load())
            restored.notify_trade_closed(trade)
            self.assertEqual(restored._setup_losses[trade['setup_id']],1)
            self.assertIn(trade['setup_id'],restored._retired_setups)

    def test_proposal_rejection_releases_only_that_attempt(self):
        s=seeded();o=order(s);s.sync_order_state(o)
        newer=s._htf_bias['EURUSD'].copy();newer['_swing_ts']+=timedelta(hours=4)
        s._htf_bias['EURUSD']=newer
        proposal=order(s,2,state='PROPOSED');s.sync_order_state(proposal)
        s._ltf_signal_fired['EURUSD']=True
        s.notify_proposal_rejected(SimpleNamespace(**proposal))
        self.assertFalse(s._ltf_signal_fired['EURUSD'])
        self.assertEqual(s._setup_attempts[o['attempt_id']]['state'],'PENDING')
        self.assertEqual(s._setup_losses,{})

    def test_pipeline_carries_identity_through_risk_fill_and_close(self):
        s=seeded(entry_mode='market');setup=s._setup_id('EURUSD')
        proposal=Signal('EURUSD','SELL','MARKET',1.118,1.119,s.NAME,T,take_profit=1.11)
        with patch.object(s,'_generate_signal',return_value=proposal):
            signal=s.generate_signal(bar())
        enriched=RiskManager(lambda:10000).process(signal)
        self.assertEqual(enriched.setup_id,setup)
        engine=BacktestEngine(spread_pips=0);engine.add_strategy(s,['EURUSD'])
        with patch.object(s,'generate_signal',return_value=signal):
            engine.event_engine.process_bar(bar())
        engine.process_bar(bar(T+timedelta(minutes=15),'M15',1.118,1.120,1.118))
        trade=engine.execution.get_closed_trades()[0]
        self.assertEqual(trade['setup_id'],setup)
        self.assertEqual(trade['attempt_id'],signal.attempt_id)
        self.assertIn(setup,s._retired_setups)


class CancellationPolicyTests(unittest.TestCase):
    def test_old_cancellation_replay_does_not_release_new_attempt_on_same_setup(self):
        s=seeded();old=order(s);new=order(s,ticket=2,state='OPEN')
        s.sync_order_state(old);s.sync_order_state(new)
        s.notify_order_cancelled(old)
        self.assertTrue(s._ltf_signal_fired['EURUSD'])
        self.assertEqual(s._setup_attempts[new['attempt_id']]['state'],'OPEN')

    def test_partial_remainder_cancellation_does_not_free_portfolio_slot(self):
        s=seeded();engine=BacktestEngine();engine.add_strategy(s,['EURUSD'])
        pending=order(s);filled=dict(pending,ticket=9,state='OPEN')
        engine.event_engine.sync_order_states([pending,filled])
        engine.portfolio.sync_existing([pending,filled])
        with patch.object(engine.execution,'get_open_positions',return_value=[filled]):
            engine.event_engine._record_cancelled(pending,'test')
        self.assertIn(('EURUSD',s.NAME),engine.portfolio.get_open_positions())
        self.assertEqual(engine.portfolio._open_ticket_count,1)

    def test_partial_fill_remainder_cancel_keeps_position_and_final_close_clears_it(self):
        s=seeded();engine=BacktestEngine();engine.add_strategy(s,['EURUSD'])
        pending=order(s);filled=dict(pending,ticket=9,state='OPEN')
        engine.event_engine.sync_order_states([filled,pending])
        record=s._setup_attempts[pending['attempt_id']]
        self.assertEqual(record['state'],'OPEN');self.assertTrue(record['has_pending'])
        engine.event_engine.notify_order_cancelled(pending)
        self.assertEqual(record['state'],'OPEN');self.assertFalse(record['has_pending'])
        self.assertTrue(s._ltf_signal_fired['EURUSD'])
        s.notify_trade_closed(loss(s))
        self.assertEqual(record['state'],'CLOSED');self.assertFalse(record['has_pending'])

    def test_each_session_target_combination_both_directions(self):
        for direction in ['SELL','BUY']:
            for hours in ['entry','all']:
                for reference in ['submitted','moving']:
                    with self.subTest(direction=direction,hours=hours,reference=reference):
                        s=seeded(pending_cancel_hours=hours,pending_target_reference=reference,
                                 blocked_hours=(*range(12),*range(17,24)))
                        if direction=='BUY':
                            s._htf_bias['EURUSD'].update(direction='SELL',fvg_level=1.118)
                        o=order(s);o['direction']=direction;s.sync_order_state(o)
                        # Both targets touched; below/above the structural-expiry close thresholds.
                        candle=bar(T.replace(hour=18),low=1.109,high=1.112,close=1.111)
                        signal=s.generate_signal(candle)
                        self.assertEqual(signal.direction if signal else None,'CANCEL' if hours=='all' else None)
                        if signal:self.assertEqual(signal.setup_id,o['setup_id'])

    def test_moving_target_and_original_target_are_distinct(self):
        for reference,expected in [('submitted',None),('moving','CANCEL')]:
            s=seeded(pending_target_reference=reference);o=order(s);s.sync_order_state(o)
            s._htf_bias['EURUSD'].update(swing_high=1.13,dealing_50=1.115)
            signal=s.generate_signal(bar())
            self.assertEqual(signal.direction if signal else None,expected)

    def test_filled_position_is_not_treated_as_pending(self):
        s=seeded(pending_cancel_hours='all',pending_target_reference='submitted')
        s.sync_order_state(order(s,state='OPEN'))
        signal=s.generate_signal(bar(low=1.109,high=1.115,close=1.112))
        self.assertIsNone(signal)
        self.assertIsNotNone(s._htf_bias['EURUSD'])

    def test_cancel_old_setup_does_not_cancel_new_setup_order(self):
        s=seeded();engine=BacktestEngine();engine.add_strategy(s,['EURUSD'])
        ex=engine.execution
        for ticket,setup in [(1,'A'),(2,'B')]:
            ex.place_order('EURUSD','SELL','PENDING',1.118,.1,1.119,1.11,s.NAME,setup_id=setup,attempt_id=setup)
        cancel=Signal('EURUSD','CANCEL','PENDING',0,0,s.NAME,T,setup_id='A')
        engine.event_engine._handle_cancel(cancel)
        self.assertEqual([p['setup_id'] for p in ex.get_open_positions()],['B'])


class LedgerRecoveryTests(unittest.TestCase):
    def test_offline_cancellation_clears_restored_pending_attempt(self):
        s=seeded();o=order(s);s.sync_order_state(o)
        ex=SimpleNamespace(get_recent_closed_trade=Mock(return_value=None),
                           get_historical_order_state=Mock(return_value='CANCELLED'))
        journal=SimpleNamespace(get_unresolved_orders=Mock(return_value=[o]),log_order_cancelled=Mock())
        result=recover_offline_journal_orders(ex,journal,Mock(),[],logging.getLogger(),
                                              on_cancel=s.notify_order_cancelled)
        self.assertEqual(result[1],1)
        self.assertFalse(s._ltf_signal_fired['EURUSD'])
        self.assertEqual(s._setup_attempts[o['attempt_id']]['state'],'CANCELLED')

    def test_cancelling_partial_remainder_keeps_ledger_position_recoverable(self):
        s=seeded();o=order(s);ledger=SetupLedger()
        ledger.accept(1,**{k:v for k,v in o.items() if k not in ('ticket','origin_order_ticket')})
        ledger.bind(1,900);ledger.cancel(o)
        self.assertEqual(ledger.unresolved_orders()[0]['state'],'OPEN')
        ledger.close(dict(loss(s),remaining_volume=.1))
        self.assertEqual(ledger.outcomes,{})

    def test_account_binding_atomic_failure_and_restart_outcome(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'ledger.json';s=seeded();o=order(s)
            ledger=SetupLedger(path,{'login':1,'server':'Demo'})
            ledger.accept(1,**{k:v for k,v in o.items() if k not in ('ticket','origin_order_ticket')})
            with patch('utils.setup_ledger.os.replace',side_effect=OSError('disk error')):
                with self.assertRaises(OSError):ledger.close(loss(s))
            self.assertEqual(ledger.outcomes,{})
            ledger.close(loss(s));restored=SetupLedger(path,{'login':1,'server':'Demo'})
            restored.close(loss(s));self.assertEqual(len(restored.closed_trades()),1)
            with self.assertRaises(ValueError):SetupLedger(path,{'login':2,'server':'Demo'})

    def test_old_checkpoint_replays_durable_outcome_once(self):
        s=seeded();ledger=SetupLedger();o=order(s)
        ledger.accept(1,**{k:v for k,v in o.items() if k not in ('ticket','origin_order_ticket')})
        ledger.close(loss(s));engine=BacktestEngine();engine.add_strategy(s,['EURUSD'])
        self.assertEqual(apply_trade_updates(engine.event_engine,ledger.closed_trades(),T-timedelta(seconds=1)),ledger.closed_trades())
        apply_trade_updates(engine.event_engine,ledger.closed_trades(),T)
        apply_trade_updates(engine.event_engine,ledger.closed_trades(),T)
        self.assertEqual(s._setup_losses[o['setup_id']],1)

    def test_journal_keeps_metadata_with_broker_details_without_schema_change(self):
        with tempfile.TemporaryDirectory() as folder:
            journal=TradeJournal(Path(folder)/'journal.csv');s=seeded()
            sig=Signal('EURUSD','SELL','PENDING',1.118,1.119,s.NAME,T,take_profit=1.11,setup_id='A',attempt_id='a1')
            enriched=RiskManager(lambda:10000).process(sig)
            journal.log_order_placed(enriched,12,execution_details={'tp':1.11,'fill_price':1.118})
            record=journal.get_unresolved_orders()[0]
            self.assertEqual(record['setup_id'],'A');self.assertEqual(record['attempt_id'],'a1')

    def test_offline_old_close_is_not_hidden_by_new_position_in_same_slot(self):
        s=seeded();old=order(s);current=order(s,ticket=2,setup='new',state='OPEN')
        ex=SimpleNamespace(get_recent_closed_trade=Mock(return_value=loss(s)),get_historical_order_state=Mock())
        journal=SimpleNamespace(get_unresolved_orders=Mock(return_value=[old]),log_close=Mock())
        cb=Mock()
        result=recover_offline_journal_orders(ex,journal,Mock(),[current],logging.getLogger(),on_close=cb)
        self.assertEqual(result[0],1);cb.assert_called_once()


class BrokerIdentityTests(unittest.TestCase):
    def test_legacy_pending_fill_maps_by_deal_without_inventing_setup(self):
        with fake_broker() as (mt5,Execution,_):
            ex=Execution({'Test':1001})
            mt5.history_deals_get.return_value=[SimpleNamespace(entry=0,order=123,position_id=900)]
            current=ex._attach_setup_context(dict(ticket=999,position_id=900,symbol='EURUSD',
                                    strategy_name='Test',direction='BUY',state='OPEN'))
            self.assertEqual(current['origin_order_ticket'],123)
            self.assertNotIn('setup_id',current)
            from utils.live_reconciliation import same_broker_position
            old=dict(ticket=123,symbol='EURUSD',strategy_name='Test',direction='BUY',state='PENDING')
            self.assertTrue(same_broker_position(old,current))
            self.assertFalse(same_broker_position(dict(old,ticket=124),current))

    def test_submission_intent_persists_and_maps_changed_position_ticket(self):
        with fake_broker() as (mt5,Execution,_):
            ledger=SetupLedger();ex=Execution({'Test':1001},setup_ledger=ledger)
            ticket=place(ex,setup_id='A',attempt_id='a1')
            token=mt5.order_send.call_args.args[0]['comment']
            self.assertLessEqual(len(token),20)
            self.assertEqual(ledger.context(dict(ticket=ticket))['setup_id'],'A')
            mt5.history_deals_get.return_value=[SimpleNamespace(entry=0,order=ticket,position_id=900)]
            pos=ex._attach_setup_context(dict(ticket=999,position_id=900,symbol='EURUSD',strategy_name='Test',direction='BUY',state='OPEN'))
            self.assertEqual(pos['origin_order_ticket'],ticket)
            self.assertEqual(pos['setup_id'],'A')
            with self.assertRaises(RuntimeError):place(ex,setup_id='A',attempt_id='a1')
            self.assertEqual(mt5.order_send.call_count,1)

    def test_crash_before_ack_record_recovers_by_exact_broker_comment(self):
        with fake_broker() as (mt5,Execution,_):
            ledger=SetupLedger()
            token=ledger.prepare(setup_id='A',attempt_id='a1',symbol='EURUSD',strategy_name='Test',direction='BUY',state='PENDING',submitted_tp=1.102)
            mt5.history_orders_get=Mock(return_value=[SimpleNamespace(ticket=123,position_id=900,comment=token,symbol='EURUSD',magic=1001,type=2)])
            ex=Execution({'Test':1001},setup_ledger=ledger);ex.recover_setup_intents()
            self.assertEqual(ledger.context(dict(ticket=999,position_id=900))['setup_id'],'A')
            mt5.order_send.assert_not_called()

    def test_partial_exit_is_not_final_and_full_history_counts_once(self):
        with fake_broker() as (mt5,Execution,_):
            ledger=SetupLedger();ex=Execution({'Test':1001},setup_ledger=ledger)
            ledger.accept(123,setup_id='A',attempt_id='a1',symbol='EURUSD',strategy_name='Test',direction='BUY',state='OPEN',submitted_tp=1.102)
            def deal(ticket,entry,volume,pnl):
                return SimpleNamespace(ticket=ticket,order=123 if entry==0 else ticket,position_id=900,
                    entry=entry,volume=volume,profit=pnl,commission=-1,swap=0,fee=0,time=1600000000+ticket,
                    price=1.1 if entry==0 else 1.099,comment='',symbol='EURUSD')
            deals=[deal(1,0,1,0),deal(2,1,.4,-40)]
            mt5.history_deals_get.return_value=deals
            pos=dict(ticket=123,position_id=900,symbol='EURUSD',strategy_name='Test',direction='BUY',sl=1.099,tp=1.102,open_price=1.1)
            mt5.positions_get.return_value=[SimpleNamespace(ticket=901,identifier=900)]
            self.assertIsNone(ex.get_recent_closed_trade(pos))
            mt5.positions_get.return_value=[]
            self.assertIsNone(ex.get_recent_closed_trade(pos))
            deals.append(deal(3,1,.6,-60))
            mt5.orders_get.return_value=[SimpleNamespace(ticket=123)]
            self.assertIsNone(ex.get_recent_closed_trade(pos))
            self.assertEqual(ledger.outcomes,{})
            mt5.orders_get.return_value=[]
            trade=ex.get_recent_closed_trade(pos);self.assertEqual(trade['pnl'],-103)
            self.assertEqual(trade['setup_id'],'A');ex.get_recent_closed_trade(pos)
            self.assertEqual(len(ledger.outcomes),1)


if __name__=='__main__':unittest.main()
