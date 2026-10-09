"""Explicit terminal identity and UTC/native-session export contracts."""
from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

import pandas as pd

from data.historical_loader import load_csv
from audit_exness_history import examine
from inspect_exness_mt5 import completed_frame, verify_terminal


class ExnessCollectionTests(unittest.TestCase):
    def test_lone_distinct_old_bar_does_not_establish_dense_resolution(self):
        days = pd.bdate_range('2021-01-04','2021-01-15')
        daily = pd.DataFrame(dict(time=days, open=1., high=1.4, low=.8, close=1.1, volume=50)).set_index('time')
        rows = daily.loc[:'2021-01-08'].reset_index().to_dict('records')
        rows.append(dict(time=pd.Timestamp('2021-01-05 16:40:00'), open=1., high=1.2, low=.9, close=1.1, volume=3))
        for day in days[days>=pd.Timestamp('2021-01-11')]:
            rows.extend(dict(time=stamp, open=1., high=1.2, low=.9, close=1.1, volume=3)
                        for stamp in pd.date_range(day,periods=200,freq='5min'))
        frame = pd.DataFrame(rows).set_index('time').sort_index()
        result = examine({'M5':frame,'D1':daily},'M5')
        self.assertEqual(result['native_first'],'2021-01-05 16:40:00')
        self.assertEqual(result['first_dense_weekday_window'],'2021-01-11 00:00:00')

    def test_completed_bars_are_utc_without_icmarkets_shift(self):
        start = datetime(2026, 7, 13, tzinfo=timezone.utc)
        end = datetime(2026, 7, 15, tzinfo=timezone.utc)
        rows = [dict(time=int(t.timestamp()), open=1., high=2., low=.5, close=1.5, tick_volume=5)
                for t in (start, end)]
        frame = completed_frame(rows, 'D1', start, end)
        self.assertEqual(len(frame), 1)
        self.assertEqual(frame['time'].iloc[0], pd.Timestamp('2026-07-13 00:00:00'))
        self.assertIsNone(frame['time'].dt.tz)

    def test_duplicate_or_invalid_source_bars_are_not_silently_accepted(self):
        start = datetime(2026, 7, 13, tzinfo=timezone.utc)
        end = datetime(2026, 7, 15, tzinfo=timezone.utc)
        row = dict(time=int(start.timestamp()), open=1., high=2., low=.5, close=1.5)
        for rows in ([row, row], [dict(row, high=.8)]):
            with self.assertRaises(RuntimeError):
                completed_frame(rows, 'M5', start, end)

    def test_exness_native_sunday_candle_is_preserved_by_loader(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp)/'EURUSD_D1_20260927-20260928.csv'
            pd.DataFrame(dict(time=['2026-09-27 00:00:00', '2026-09-28 00:00:00'],
                open=[1., 1.], high=[2., 2.], low=[.5, .5], close=[1.5, 1.5])).to_csv(path, index=False)
            Path(str(path)+'.meta.json').write_text(json.dumps(dict(provider='Exness',
                time_basis='utc', session_origin='exness', research_status='approved_native_resolution')))
            bars = load_csv(str(path))
            self.assertEqual(len(bars), 2)
            self.assertEqual(bars[0].timestamp, pd.Timestamp('2026-09-27 00:00:00'))

    def test_changed_account_or_terminal_or_real_account_is_rejected(self):
        with TemporaryDirectory() as tmp:
            path = str(Path(tmp)/'terminal64.exe')
            terminal = SimpleNamespace(path=tmp, connected=True)
            account = SimpleNamespace(login=123, server='Exness-Trial', company='Exness', trade_mode=0)
            mt5 = SimpleNamespace(terminal_info=lambda:terminal, account_info=lambda:account,
                                  ACCOUNT_TRADE_MODE_DEMO=0)
            verify_terminal(mt5, path, 123, 'Exness-Trial')
            for field, value in [('login',124), ('server','Other'), ('trade_mode',2), ('company','Other')]:
                old = getattr(account, field)
                setattr(account, field, value)
                with self.assertRaises(RuntimeError):
                    verify_terminal(mt5, path, 123, 'Exness-Trial')
                setattr(account, field, old)
            with self.assertRaises(RuntimeError):
                verify_terminal(mt5, str(Path(tmp)/'other'/'terminal64.exe'), 123, 'Exness-Trial')

    def test_unreviewed_broker_export_is_blocked_from_replay(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp)/'EURUSD_M5_20190101-20190102.csv'
            Path(str(path)+'.meta.json').write_text(json.dumps(dict(research_status='raw_unreviewed')))
            with self.assertRaisesRegex(ValueError, 'timeframe-resolution'):
                load_csv(str(path))


if __name__ == '__main__':
    unittest.main()
