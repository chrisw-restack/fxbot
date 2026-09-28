"""Deterministic audit of current Failed2 behavior, including reproduced defects.

These assertions describe observed behavior, not approval of every rule.
"""
from collections import deque
from copy import deepcopy
from datetime import datetime, timedelta
import unittest

from backtest_engine import BacktestEngine
from data.histdata_provenance import write_json
from models import BarEvent
from research_failed2_review import OUT, settings, FreshCrossFailed2
from strategies.failed2 import Failed2Strategy


def bars():
    highs=[104,103,101,105,107,108,109,110,109,109,109,109,112,113]
    lows=[98,97,95,98,100,103,105,106,104,105,106,106,107,108]
    closes=[101,100,98,102,104,106,107,108,107,107,108,108,111,112]
    return [BarEvent('USTEC','M5',datetime(2024,1,8,11,55)+timedelta(minutes=5*i),c,h,l,c,1)
            for i,(h,l,c) in enumerate(zip(highs,lows,closes))]


def prepared(cls=Failed2Strategy):
    s=cls(**settings())
    s._init_symbol('USTEC')
    s._bias['USTEC']=dict(direction='BUY',kind='2',high=120,low=90,
        timestamp=datetime(2024,1,8,4),close_time=datetime(2024,1,8,8))
    s._itf_setup['USTEC']=dict(id=(datetime(2024,1,8,12),'BUY'),direction='BUY',
        timestamp=datetime(2024,1,8,12),close_time=datetime(2024,1,8,13))
    s._d1_ema_fast['USTEC'],s._d1_ema_slow['USTEC']=105,100
    s._entry_bars['USTEC'].extend(bars()[:-1])
    return s


class Failed2LogicAudit(unittest.TestCase):
    def test_old_break_is_accepted_after_new_h1_confirmation(self):
        s=prepared()
        signal=s.generate_signal(bars()[-1])
        self.assertIsNotNone(signal)
        self.assertEqual(signal.entry_price,112)
        self.assertEqual(signal.stop_loss,95)
        self.assertEqual(signal.take_profit,180)
        self.assertGreater(bars()[-2].close,110)
        self.assertIsNone(prepared(FreshCrossFailed2).generate_signal(bars()[-1]))

    def test_sell_mirror_also_accepts_old_break(self):
        s=prepared()
        s._bias['USTEC']['direction']='SELL'
        s._itf_setup['USTEC']['direction']='SELL'
        s._itf_setup['USTEC']['id']=(datetime(2024,1,8,12),'SELL')
        s._d1_ema_fast['USTEC'],s._d1_ema_slow['USTEC']=100,105
        mirrored=[BarEvent(b.symbol,b.timeframe,b.timestamp,220-b.open,220-b.low,220-b.high,220-b.close,1) for b in bars()]
        s._entry_bars['USTEC']=deque(mirrored[:-1],maxlen=s._entry_bars_len)
        signal=s.generate_signal(mirrored[-1])
        self.assertEqual(signal.direction,'SELL')
        self.assertEqual(signal.stop_loss,125)
        self.assertEqual(signal.entry_price,108)

    def test_equal_confirmation_close_cannot_enter(self):
        s=prepared()
        s._entry_bars['USTEC'].pop()
        self.assertIsNone(s.generate_signal(bars()[-2]))
        self.assertIsNotNone(s.generate_signal(bars()[-1]))

    def test_fractal_needs_four_completed_right_bars(self):
        self.assertNotIn(7,Failed2Strategy._swing_high_idxs(bars()[:11],4,10))
        self.assertIn(7,Failed2Strategy._swing_high_idxs(bars()[:12],4,11))

    def test_stop_uses_pivot_before_broken_high_not_latest_low(self):
        s=prepared()
        signal=s.generate_signal(bars()[-1])
        low_idxs=s._swing_low_idxs(bars(),2,len(bars())-1)
        self.assertIn(8,low_idxs)
        self.assertEqual(bars()[8].low,104)
        self.assertEqual(signal.stop_loss,95)

    def test_same_direction_h4_refresh_discards_h1_setup(self):
        s=prepared()
        s._prev_bias_bar['USTEC']=BarEvent('USTEC','H4',datetime(2024,1,8,4),100,110,95,105,1)
        s.generate_signal(BarEvent('USTEC','H4',datetime(2024,1,8,8),105,111,96,110,1))
        self.assertEqual(s._bias['USTEC']['direction'],'BUY')
        self.assertIsNone(s._itf_setup['USTEC'])
        self.assertFalse(s._entry_bars['USTEC'])

    def test_50_daily_bars_can_disagree_with_full_range_filter(self):
        ranges=[1]*42+[100]*18+[2]
        daily=[BarEvent('USTEC','D1',datetime(2023,1,1)+timedelta(days=i),100,100+r/2,100-r/2,100,1)
               for i,r in enumerate(ranges)]
        full=Failed2Strategy(**settings())
        short=Failed2Strategy(**settings())
        for b in daily:
            full.generate_signal(b)
        for b in daily[-50:]:
            short.generate_signal(b)
        self.assertAlmostEqual(full._d1_range_percentile['USTEC'],.7)
        self.assertAlmostEqual(short._d1_range_percentile['USTEC'],31/49)
        self.assertTrue(full._d1_range_blocked['USTEC'])
        self.assertFalse(short._d1_range_blocked['USTEC'])

    def test_rejection_releases_proposal_only_when_slot_is_empty(self):
        for occupied in (False,True):
            s=prepared()
            e=BacktestEngine()
            e.add_strategy(s,['USTEC'])
            signal=s.generate_signal(bars()[-1])
            if occupied:
                e.portfolio.record_existing('USTEC',s.NAME,999)
            e.event_engine.reject_signal(signal)
            self.assertEqual(s._traded_setup_id['USTEC'] is not None,occupied)

    def test_cold_reconstruction_cannot_restore_consumed_setup(self):
        s=prepared()
        signal=s.generate_signal(bars()[-1])
        s.notify_win('USTEC')
        self.assertIsNone(s.generate_signal(bars()[-1]))
        cold=prepared()
        self.assertIsNotNone(cold.generate_signal(bars()[-1]))
        self.assertIsNone(signal.setup_id)
        self.assertFalse(hasattr(cold,'sync_order_state'))

    def test_market_fills_next_bar_with_executable_rr_not_exactly_four(self):
        s=prepared()
        e=BacktestEngine(spread_pips=1.)
        e.add_strategy(s,['USTEC'])
        e.process_bar(bars()[-1])
        self.assertEqual(len(e.execution._pending),1)
        self.assertFalse(e.execution._positions)
        b=BarEvent('USTEC','M5',datetime(2024,1,8,13,5),112,115,111,113,1)
        e.process_bar(b)
        p=e.execution.get_open_positions()[0]
        self.assertEqual(p['entry_price'],113)
        self.assertAlmostEqual((p['tp']-p['entry_price'])/(p['entry_price']-p['sl']),67/18)


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(Failed2LogicAudit)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    write_json(OUT/'logic_audit.json',dict(cases=result.testsRun,failures=len(result.failures),errors=len(result.errors),
        note='Assertions reproduce current behavior, including limitations; not a correctness certificate.'))
    raise SystemExit(not result.wasSuccessful())
