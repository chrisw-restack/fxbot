import unittest
from datetime import datetime
from types import SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import pandas as pd

from inspect_ifx_mt5 import TERMINAL, SYMBOLS, completed_frame, verify_terminal
from audit_ifx_history import gap_details
from data.historical_loader import load_csv


class IfxCollectionTests(unittest.TestCase):
    def api(self, **changes):
        account = dict(login=12, server='IFXBrokers-Real', company='IFX Brokers', trade_mode=0)
        account.update(changes)
        return SimpleNamespace(ACCOUNT_TRADE_MODE_DEMO=0,
            terminal_info=lambda: SimpleNamespace(path=str(__import__('pathlib').Path(TERMINAL).parent), connected=True),
            account_info=lambda: SimpleNamespace(**account))

    def test_real_named_server_with_demo_flag_is_accepted(self):
        verify_terminal(self.api(), TERMINAL, 12, 'IFXBrokers-Real')

    def test_real_account_or_changed_identity_is_rejected(self):
        for changes in ({'trade_mode': 2}, {'login': 99}, {'company': 'Other Broker'}):
            with self.assertRaises(RuntimeError):
                verify_terminal(self.api(**changes), TERMINAL, 12, 'IFXBrokers-Real')

    def test_cutoff_excludes_incomplete_bar_without_clock_conversion(self):
        rates = [dict(time=300,open=2,high=3,low=1,close=2,tick_volume=4),
                 dict(time=600,open=2,high=3,low=1,close=2,tick_volume=5)]
        frame = completed_frame(rates,'M5',datetime(1970,1,1),datetime(1970,1,1,0,12))
        self.assertEqual(len(frame), 1)
        self.assertEqual(str(frame.iloc[0]['time']), '1970-01-01 00:05:00')
        self.assertEqual(frame.iloc[0]['volume'], 4)

    def test_duplicate_and_bad_ohlc_are_rejected(self):
        row = dict(time=300,open=2,high=3,low=1,close=2,tick_volume=4)
        for rows in ([row,row], [dict(row,high=1)]):
            with self.assertRaises(RuntimeError):
                completed_frame(rows,'M5',datetime(1970,1,1),datetime(1970,1,2))

    def test_cash_nasdaq_mapping(self):
        self.assertEqual(SYMBOLS['USTEC'], 'T100.ifx_m')

    def test_weekend_is_distinct_from_intraday_hole(self):
        frame = pd.DataFrame({'close':[1,1,1]},index=pd.to_datetime([
            '2024-08-02 15:55','2024-08-02 16:55','2024-08-05 00:00']))
        gaps=gap_details(frame,'M5')
        self.assertEqual(gaps['grid_gap_events'],2)
        self.assertEqual(gaps['same_day_weekday_gaps_at_least_60_minutes'],1)
        self.assertEqual(gaps['largest_same_day_weekday_gaps'][0]['missing_grid_slots'],11)

    def test_empty_weekday_is_retained_for_review(self):
        frame = pd.DataFrame({'close':[1,1]},index=pd.to_datetime([
            '2024-08-01 23:55','2024-08-05 00:00']))
        self.assertEqual(gap_details(frame,'M5')['full_empty_weekdays'],['2024-08-02'])

    def test_raw_ifx_cannot_enter_backtest(self):
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'EURUSD_M5_20220101-20220102.csv'
            Path(str(path)+'.meta.json').write_text(json.dumps(dict(provider='IFX',
                time_basis='ifx_server_unreviewed',research_status='raw_unreviewed')))
            with self.assertRaisesRegex(ValueError,'resolution audit'):
                load_csv(str(path),time_basis='utc')


if __name__ == '__main__':
    unittest.main()
