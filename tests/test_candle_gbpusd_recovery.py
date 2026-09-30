"""Research gates retain completed-bar detection and production proposal tracking."""
from datetime import datetime, timedelta
import unittest

from models import BarEvent
from research_candle_gbpusd_recovery import RecoveryCandle
from research_candle_gbpusd_review import settings


def fixture(policy, touched=False, outside=False, sell=False):
    params = settings()
    params.update(tf_trend=None, min_engulf_range_pips=0, min_engulf_body_pct=0)
    strategy = RecoveryCandle(recovery=policy, **params)
    def bar(tf, minute, high, low, close, opening=None):
        opening = close if opening is None else opening
        if sell:
            opening, high, low, close = 2.2-opening, 2.2-low, 2.2-high, 2.2-close
        return BarEvent('GBPUSD', tf, datetime(2024, 1, 1)+timedelta(minutes=minute),
                        opening, high, low, close, 1)
    strategy.generate_signal(bar('H1', 0, 1.102, 1.098, 1.099, 1.10))
    if outside:
        low = 1.1003 if outside == 'boundary' else 1.101
        strategy.generate_signal(bar('H1', 60, 1.103, low, 1.102, 1.1015))
    else:
        strategy.generate_signal(bar('H1', 60, 1.103, 1.095, 1.101, 1.099))
    first_low = 1.095 if touched == 'equal' else 1.0945 if touched else 1.097
    sequence = [(1.0984, first_low, 1.0978),
                (1.099,1.0974,1.0984), (1.0994,1.0978,1.0989),
                (1.1000,1.098,1.0993), (1.0995,1.0984,1.0990),
                (1.0996,1.0987,1.0992), (1.0997,1.099,1.0994),
                (1.1004,1.0991,1.1001), (1.1005,1.0999,1.1003)]
    signals = [strategy.generate_signal(bar('M5', 120+5*i, *prices))
               for i, prices in enumerate(sequence)]
    return strategy, signals


class RecoveryGateTests(unittest.TestCase):
    def test_touch_required_without_consuming_filtered_setup(self):
        for sell in (False, True):
            control, signals = fixture('off', sell=sell)
            self.assertTrue(all(x is None for x in signals[:-1]))
            self.assertIsNotNone(signals[-1])
            for policy in ('touch', 'inside'):
                strategy, signals = fixture(policy, sell=sell)
                self.assertTrue(all(x is None for x in signals))
                self.assertFalse(strategy._proposals)
                self.assertFalse(strategy._signal_fired['GBPUSD'])
                self.assertIsNotNone(strategy._bias['GBPUSD'])

    def test_recovered_signal_uses_production_ownership_and_stop_guard(self):
        for sell in (False, True):
            for policy in ('touch', 'inside'):
                strategy, signals = fixture(policy, touched=True, sell=sell)
                self.assertTrue(all(x is None for x in signals[:-1]))
                signal = signals[-1]
                self.assertIsNotNone(signal)
                self.assertEqual(signal.direction, 'SELL' if sell else 'BUY')
                self.assertEqual(signal.min_stop_distance, .0008)
                self.assertEqual(len(strategy._proposals), 1)
                self.assertEqual(signal.setup_id, strategy._setup_id('GBPUSD'))
                strategy.notify_proposal_rejected(signal)
                self.assertFalse(strategy._proposals)
                self.assertFalse(strategy._signal_fired['GBPUSD'])

    def test_return_inside_is_an_additional_rule_in_both_directions(self):
        for sell in (False, True):
            touch, signals = fixture('touch', outside=True, sell=sell)
            self.assertIsNotNone(signals[-1])
            self.assertFalse(touch.get_last_signal_context('GBPUSD')['close_back_inside_range'])
            inside, signals = fixture('inside', outside=True, sell=sell)
            self.assertTrue(all(x is None for x in signals))
            self.assertFalse(inside._proposals)
            self.assertIsNotNone(inside._bias['GBPUSD'])

    def test_unknown_policy_rejected(self):
        with self.assertRaises(ValueError):
            RecoveryCandle(recovery='unknown')

    def test_exact_touch_qualifies_but_close_on_boundary_is_not_inside(self):
        for sell in (False, True):
            touched, signals = fixture('touch', touched='equal', sell=sell)
            self.assertIsNotNone(signals[-1])
            self.assertTrue(touched.get_last_signal_context('GBPUSD')['opposite_extreme_breached'])
            for policy in ('touch', 'inside'):
                strategy, signals = fixture(policy, outside='boundary', sell=sell)
                self.assertEqual(signals[-1] is not None, policy == 'touch')


if __name__ == '__main__':
    unittest.main()
