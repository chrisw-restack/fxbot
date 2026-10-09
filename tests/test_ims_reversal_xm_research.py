"""Research bounds and statistics must not join exposure across audit gaps."""
from datetime import datetime, timedelta
import unittest

from research_ims_reversal_xm import intersect, segments_for, aggregate, frozen_strategy
from research_ims_reversal import metrics


class ImsXmResearchTests(unittest.TestCase):
    def test_intersection_does_not_bridge_excluded_period(self):
        a, b, c, d = [datetime(2020, 1, n) for n in (1, 2, 3, 4)]
        self.assertEqual(intersect([(a, d)], [(a, b), (c, d)]), [(a, b), (c, d)])

    def test_each_new_interval_requires_its_own_warmup(self):
        start = datetime(2020, 1, 1)
        left = start+timedelta(days=300)
        end = left+timedelta(days=200)
        segments, skipped = segments_for([(start-timedelta(days=200), start+timedelta(days=90)),
                                         (left, end), (end+timedelta(days=1), end+timedelta(days=5))],
                                        start, end+timedelta(days=6))
        self.assertEqual(segments[0]['trade_start'], start)
        self.assertEqual(segments[1]['trade_start'], left+timedelta(days=180))
        self.assertEqual(segments[1]['load_start'], left)
        self.assertEqual(len(skipped), 1)

    def test_reported_drawdown_and_streak_restart_at_segment_boundary(self):
        trades = [dict(net_r=-1., gross_r=-1., pnl=-50., close_time=datetime(2020, 1, 1))]*3
        def run(ts):
            return dict(trades=ts, metrics=metrics(ts), max_equity_dd_pct=1., filled_open=1, pending_open=0)
        result = aggregate([run(trades), run(trades)])
        self.assertEqual(result['total_r'], -6.)
        self.assertEqual(result['max_segment_dd_r'], 3.)
        self.assertEqual(result['max_loss_streak'], 3)
        self.assertEqual(result['concatenated_closed_r_dd_diagnostic'], 6.)
        self.assertEqual(result['ending_filled_positions_across_segments'], 2)

    def test_uses_current_frozen_demo_strategy(self):
        strategy = frozen_strategy()
        self.assertEqual(strategy.TIMEFRAMES, ['H4', 'M15'])
        self.assertEqual(strategy.pending_cancel_hours, 'entry')
        self.assertEqual(strategy.pending_target_reference, 'moving')
        self.assertEqual(strategy.ltf_fractal_n, 2)
        self.assertEqual(strategy.max_losses_per_bias, 1)


if __name__ == '__main__':
    unittest.main()
