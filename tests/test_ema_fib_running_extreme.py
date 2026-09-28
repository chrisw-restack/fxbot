"""The confirmed anchor includes known right-wing closes without looking ahead."""
import unittest
from models import BarEvent
from test_ema_fib_running_tracking import strategy, bar, SYMBOL


def sequence(mirror=False):
    prices = [(1.103,1.110,1.105,1.106),(1.102,1.109,1.104,1.105),
              (1.100,1.107,1.103,1.102),(1.101,1.115,1.114,1.103),
              (1.102,1.113,1.108,1.110)]
    bars = [bar(9+i,low=lo,high=hi,close=c,open_=o) for i,(lo,hi,c,o) in enumerate(prices)]
    if mirror:
        bars = [BarEvent(b.symbol,b.timeframe,b.timestamp,2.2-b.open,2.2-b.low,
                         2.2-b.high,2.2-b.close,b.volume) for b in bars]
    return bars


class RunningExtremeTests(unittest.TestCase):
    def test_buy_includes_known_close_after_anchor_only_when_confirmed(self):
        s=strategy()
        bars=sequence()
        for b in bars[:-1]:
            s.generate_signal(b)
            self.assertIsNone(s._fractal_low[SYMBOL])
        s.generate_signal(bars[-1])
        self.assertAlmostEqual(s._running_high[SYMBOL],1.114)
        self.assertEqual(s._fractal_low_time[SYMBOL],bars[2].timestamp)
        self.assertFalse(s._fvg_since_fractal_low[SYMBOL])
        s.generate_signal(bar(14,low=1.105,high=1.117,close=1.116))
        self.assertAlmostEqual(s._running_high[SYMBOL],1.116)

    def test_sell_includes_known_close_after_anchor(self):
        s=strategy()
        for b in sequence(mirror=True):
            s.generate_signal(b)
        self.assertAlmostEqual(s._running_low[SYMBOL],1.086)
        self.assertFalse(s._fvg_since_fractal_high[SYMBOL])

    def test_existing_three_bar_gap_rule_is_preserved(self):
        s=strategy()
        bars=sequence()
        bars[-1]=bar(13,low=1.108,high=1.113,close=1.109,open_=1.110)
        for b in bars:
            s.generate_signal(b)
        self.assertTrue(s._fvg_since_fractal_low[SYMBOL])
        self.assertAlmostEqual(s._running_high[SYMBOL],1.114)

    def test_closes_before_anchor_are_excluded(self):
        s=strategy()
        bars=sequence()
        bars[0]=bar(9,low=1.103,high=1.130,close=1.129)
        for b in bars:
            s.generate_signal(b)
        self.assertAlmostEqual(s._running_high[SYMBOL],1.114)

    def test_new_anchor_resets_prior_extreme_and_other_symbol_is_isolated(self):
        s=strategy()
        s._init_symbol(SYMBOL)
        s._running_high[SYMBOL]=1.300
        s._init_symbol('GBPUSD')
        s._running_high['GBPUSD']=1.400
        for b in sequence():
            s.generate_signal(b)
        self.assertAlmostEqual(s._running_high[SYMBOL],1.114)
        self.assertEqual(s._running_high['GBPUSD'],1.400)
        s.reset()
        self.assertFalse(s._orders)
        self.assertFalse(s._running_high)


if __name__ == '__main__':
    unittest.main()
