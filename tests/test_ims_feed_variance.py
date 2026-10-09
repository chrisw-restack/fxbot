"""A boundary diagnostic must not leak prices across H4 buckets or gaps."""
from datetime import datetime, timedelta
import unittest

from diagnose_ims_reversal_feed_variance import anchored_h4
from models import BarEvent


class FeedVarianceTests(unittest.TestCase):
    def test_next_bucket_prices_cannot_change_prior_h4(self):
        start = datetime(2026, 1, 5, 2)
        bars = [BarEvent('EURUSD','M5',start,1.,2.,.5,1.5,10.),
                BarEvent('EURUSD','M5',start+timedelta(hours=4),10.,20.,5.,15.,20.)]
        result, _ = anchored_h4(bars, [start,start+timedelta(hours=4)])
        self.assertEqual((result[0].high,result[0].low,result[0].volume), (2.,.5,10.))
        self.assertEqual((result[1].high,result[1].low,result[1].volume), (20.,5.,20.))

    def test_missing_h4_anchor_does_not_extend_an_earlier_bucket(self):
        start = datetime(2026, 1, 5, 2)
        bars = [BarEvent('EURUSD','M5',start,1.,2.,.5,1.5,10.),
                BarEvent('EURUSD','M5',start+timedelta(hours=5),10.,20.,5.,15.,20.)]
        result, audit = anchored_h4(bars,[start])
        self.assertEqual(len(result),1)
        self.assertEqual(result[0].high,2.)
        self.assertEqual(audit['partial_buckets'],1)


if __name__ == '__main__':
    unittest.main()
