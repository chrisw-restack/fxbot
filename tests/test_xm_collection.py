"""XM collection identity, raw clock, and clock-regime validation."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import json
import unittest

import numpy as np
import pandas as pd

from inspect_xm_mt5 import raw_completed_frame, verify_terminal
from audit_xm_history import clock_windows, resolution_details
from data.historical_loader import load_csv
from data.histdata_provenance import file_hash


class XmCollectionTests(unittest.TestCase):
    def test_raw_timestamps_are_preserved_and_cutoff_excludes_incomplete_bars(self):
        start, end = pd.Timestamp('2026-07-14'), pd.Timestamp('2026-07-15')
        rows = [dict(time=int(t.timestamp()), open=1., high=2., low=.5, close=1.5)
            for t in (start, end-pd.Timedelta(minutes=2), end)]
        frame = raw_completed_frame(rows,'M5',start,end)
        self.assertEqual(list(frame.time), [start])

    def test_account_change_real_account_and_wrong_terminal_are_rejected(self):
        with TemporaryDirectory() as tmp:
            terminal = SimpleNamespace(path=tmp,connected=True)
            account = SimpleNamespace(login=42,server='XMGlobal-MT5 7',company='XM Global',trade_mode=0)
            m = SimpleNamespace(terminal_info=lambda:terminal,account_info=lambda:account,ACCOUNT_TRADE_MODE_DEMO=0)
            path = str(Path(tmp)/'terminal64.exe')
            verify_terminal(m,path,42,account.server)
            for field,value in [('login',43),('server','Exness'),('company','Other'),('trade_mode',2)]:
                old = getattr(account,field)
                setattr(account,field,value)
                with self.assertRaises(RuntimeError):
                    verify_terminal(m,path,42,'XMGlobal-MT5 7')
                setattr(account,field,old)
            with self.assertRaises(RuntimeError):
                verify_terminal(m,str(Path(tmp)/'other'/'terminal64.exe'),42,account.server)

    def test_xm_without_review_status_is_blocked_even_with_explicit_utc_override(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp)/'EURUSD_M5_20260101-20260102.csv'
            Path(str(path)+'.meta.json').write_text(json.dumps(dict(provider='XM',time_basis='utc')))
            with self.assertRaisesRegex(ValueError,'timeframe-resolution'):
                load_csv(str(path), time_basis='utc')

    def test_reviewed_utc_xm_data_preserves_native_sunday_session(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp)/'EURUSD_D1_20260927-20260928.csv'
            pd.DataFrame(dict(time=['2026-09-27 21:00:00','2026-09-28 21:00:00'],
                open=1.,high=1.1,low=.9,close=1.,volume=10)).to_csv(path,index=False)
            Path(str(path)+'.meta.json').write_text(json.dumps(dict(provider='XM',
                time_basis='utc',session_origin='xm',research_status='approved_native_resolution',
                processing_schema_version=1,csv_sha256=file_hash(path),source_sha256='a'*64,
                source_manifest_sha256='b'*64,processor_sha256='c'*64,evidence_clock_reference_sha256='d'*64,
                symbol='EURUSD',timeframe='D1',coverage_start='2026-09-27 21:00:00',coverage_end='2026-09-29 21:00:00',
                replay_intervals=[dict(start='2026-09-27 21:00:00',end='2026-09-29 21:00:00')])))
            bars = load_csv(str(path))
            self.assertEqual(len(bars),2)
            self.assertEqual(bars[0].timestamp,pd.Timestamp('2026-09-27 21:00:00'))

    def test_clock_audit_distinguishes_european_and_us_transition_weeks(self):
        # March 16 is already US DST, but Europe changes March 29 in 2026.
        index = pd.date_range('2026-03-16',periods=288*3,freq='5min')
        rng = np.random.default_rng(23)
        prices = 1.2+np.cumsum(rng.normal(0,.0001,len(index)))
        reference = pd.DataFrame(dict(time=index,close=prices))
        for shift,expected in [(2,'european_dst'),(3,'us_dst')]:
            raw = reference.copy()
            raw.time += pd.Timedelta(hours=shift)
            result = clock_windows(raw,reference)
            self.assertEqual(result['compatible_rules'],[expected])
            self.assertTrue(all(w['verified'] for w in result['windows']))

    def test_unrelated_prices_do_not_verify_a_clock(self):
        index = pd.date_range('2026-03-16',periods=288*3,freq='5min')
        rng = np.random.default_rng(78)
        raw = pd.DataFrame(dict(time=index,close=1.2+np.cumsum(rng.normal(0,.001,len(index)))))
        ref = pd.DataFrame(dict(time=index,close=1.2+np.cumsum(rng.normal(0,.001,len(index)))))
        result = clock_windows(raw,ref)
        self.assertEqual(result['compatible_rules'],[])
        self.assertFalse(any(w['verified'] for w in result['windows']))

    def test_coarse_section_inside_history_is_flagged(self):
        index = pd.date_range('2026-03-01','2026-03-31 23:00',freq='h')
        hourly = pd.DataFrame(dict(open=1.,high=1.1,low=.9,close=1.,volume=10),index=index)
        full_index = pd.date_range('2026-02-01','2026-02-28 23:55',freq='5min')
        detailed = pd.DataFrame(dict(open=1.,high=1.05,low=.95,close=1.01,volume=3),index=full_index)
        low = pd.concat([detailed,hourly])
        result = resolution_details({'M5':low,'H1':hourly},'M5')
        self.assertEqual(result['suspect_coarse_months'],['2026-03-01'])

    def test_daily_prefix_is_flagged_despite_fewer_than_fifty_monthly_rows(self):
        index = pd.bdate_range('2026-03-01','2026-03-31')
        daily = pd.DataFrame(dict(open=1.,high=1.1,low=.9,close=1.,volume=10),index=index)
        result = resolution_details({'M5':daily,'D1':daily},'M5')
        self.assertEqual(result['suspect_coarse_months'],['2026-03-01'])
        self.assertIsNone(result['native_first'])

    def test_mixed_historical_clock_does_not_claim_one_universal_rule(self):
        rng = np.random.default_rng(21)
        raw, refs = [], []
        for year,offset in [(2016,3),(2026,2)]:
            index = pd.date_range(f'{year}-03-16',periods=288*3,freq='5min')
            prices = 1.2+np.cumsum(rng.normal(0,.0001,len(index)))
            refs.append(pd.DataFrame(dict(time=index,close=prices)))
            raw.append(pd.DataFrame(dict(time=index+pd.Timedelta(hours=offset),close=prices)))
        result = clock_windows(pd.concat(raw),pd.concat(refs))
        self.assertEqual(result['compatible_rules'],[])
        self.assertEqual(result['compatible_rules_by_year'],{'2016':['us_dst'],'2026':['european_dst']})


if __name__ == '__main__':
    unittest.main()
