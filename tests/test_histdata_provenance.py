import json
import io
import ssl
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import numpy as np
import pandas as pd

from data.histdata_provenance import (read_raw_archive, infer_clock, to_utc, file_hash,
    metadata_path, write_json, validate_output_metadata)
from data.historical_loader import load_csv
from fetch_data_histdata import read_histdata_zip, find_zip, save_timeframe, download_zip, has_verified_download


def sample(clock):
    rng = np.random.default_rng(72)
    frames = []
    for start in ['2024-01-08', '2024-03-20', '2024-07-01', '2024-10-28']:
        times = pd.date_range(start, periods=1440, freq='min')
        prices = 1.1 + rng.normal(0, .0001, len(times)).cumsum()
        frames.append(pd.DataFrame(dict(time=times, open=prices, high=prices+.0001,
                                       low=prices-.0001, close=prices, volume=0)))
    raw = pd.concat(frames, ignore_index=True)
    reference = raw[['time', 'close']].copy()
    reference.time = to_utc(reference.time, clock)
    reference = reference.set_index('time').resample('5min').last().dropna().reset_index()
    return raw, reference


def receipt(path, clock='new_york'):
    return dict(schema_version=1, provider='HistData', sha256=file_hash(path), tls_verified=True,
                source_url='https://www.histdata.com/download-free-forex-historical-data/',
                clock_verification=dict(status='verified', source_clock=clock,
                    raw_cleanup=read_raw_archive(path, quarantine_conflicts=True).attrs['raw_cleanup']))


def archive(folder, rows, extra_first=True):
    path=Path(folder)/'DAT_ASCII_EURUSD_M1_2024.zip'
    with zipfile.ZipFile(path,'w') as z:
        if extra_first:z.writestr('DAT_ASCII_EURUSD_M1_2024.txt','Gap status, not price data')
        z.writestr(path.stem+'.csv',rows)
    return path


class HistDataClockTests(unittest.TestCase):
    def test_fixed_est_and_new_york_differ_in_summer(self):
        local=pd.Series(pd.to_datetime(['2024-01-08 08:30','2024-07-01 08:30']))
        self.assertEqual(to_utc(local,'fixed_est').dt.hour.tolist(),[13,13])
        self.assertEqual(to_utc(local,'new_york').dt.hour.tolist(),[13,12])

    def test_european_transition_weeks_are_distinct_from_new_york(self):
        local=pd.Series(pd.to_datetime(['2024-03-20 13:00','2024-10-28 07:30']))
        self.assertEqual(to_utc(local,'european_dst').dt.hour.tolist(),[18,12])
        self.assertEqual(to_utc(local,'new_york').dt.hour.tolist(),[17,11])

    def test_clock_selection_uses_transition_windows_not_a_summer_sample(self):
        for clock in ['fixed_est','new_york','european_dst']:
            with self.subTest(clock=clock):
                raw,ref=sample(clock)
                self.assertEqual(infer_clock(raw,ref)['source_clock'],clock)

    def test_unrelated_or_insufficient_reference_is_rejected(self):
        raw,ref=sample('new_york')
        with self.assertRaisesRegex(ValueError,'Insufficient'):infer_clock(raw,ref.iloc[:10])
        ref.close=np.random.default_rng(4).uniform(1,2,len(ref))
        with self.assertRaisesRegex(ValueError,'Insufficient'):infer_clock(raw,ref)

    def test_dst_ambiguous_or_nonexistent_rows_are_not_silently_shifted(self):
        for stamp in ['2024-03-10 02:15','2024-11-03 01:15']:
            with self.subTest(stamp=stamp),self.assertRaises(Exception):
                to_utc(pd.Series(pd.to_datetime([stamp])),'new_york')


class HistDataArchiveTests(unittest.TestCase):
    def test_cached_archive_needs_matching_authenticated_download_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            path=archive(folder,'20240701 080000;1.1;1.2;1.0;1.15;0\n')
            self.assertFalse(has_verified_download(path))
            meta=receipt(path)
            write_json(metadata_path(path),meta)
            self.assertTrue(has_verified_download(path))
            write_json(metadata_path(path),dict(meta,tls_verified=False))
            self.assertFalse(has_verified_download(path))
            write_json(metadata_path(path),dict(meta,sha256='wrong'))
            self.assertFalse(has_verified_download(path))

    def test_official_download_writes_hash_receipt_but_requires_clock_audit(self):
        with tempfile.TemporaryDirectory() as folder:
            content=io.BytesIO()
            with zipfile.ZipFile(content,'w') as z:
                z.writestr('DAT_ASCII_EURUSD_M1_2024.csv','20240701 080000;1.1;1.2;1.0;1.15;0\n')
            response=io.BytesIO(content.getvalue())
            response.geturl=lambda:'https://www.histdata.com/get.php'
            fields=dict(tk='test',date='2024',datemonth='2024',platform='ASCII',timeframe='M1',fxpair='EURUSD')
            with patch('fetch_data_histdata.fetch_html',return_value=''), patch('fetch_data_histdata.parse_hidden_form',return_value=fields), patch('urllib.request.urlopen',return_value=response):
                path=download_zip('EURUSD',2024,None,Path(folder),ssl.create_default_context())
            meta=json.loads(metadata_path(path).read_text())
            self.assertEqual(meta['sha256'],file_hash(path))
            self.assertTrue(meta['tls_verified'])
            self.assertEqual(meta['period'],'2024')
            with self.assertRaisesRegex(ValueError,'unverified'):read_histdata_zip(path)

    def test_wrong_download_form_cannot_publish_an_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            fields=dict(date='2024',datemonth='2024',platform='ASCII',timeframe='M1',fxpair='GBPUSD')
            with patch('fetch_data_histdata.fetch_html',return_value=''), patch('fetch_data_histdata.parse_hidden_form',return_value=fields), patch('urllib.request.urlopen') as request:
                with self.assertRaisesRegex(ValueError,'does not match'):
                    download_zip('EURUSD',2024,None,Path(folder),ssl.create_default_context())
                request.assert_not_called()
            self.assertFalse(list(Path(folder).iterdir()))

    def test_selects_price_csv_even_when_gap_report_comes_first(self):
        with tempfile.TemporaryDirectory() as folder:
            path=archive(folder,'20240701 080000;1.1;1.2;1.0;1.15;0\n')
            self.assertEqual(len(read_raw_archive(path)),1)

    def test_only_exact_duplicate_rows_can_be_removed(self):
        with tempfile.TemporaryDirectory() as folder:
            line='20240701 080000;1.1;1.2;1.0;1.15;0\n'
            path=archive(folder,line+line)
            df=read_raw_archive(path)
            self.assertEqual(len(df),1)
            self.assertEqual(df.attrs['raw_cleanup']['exact_duplicate_rows_removed'],1)
            path=archive(folder,line+'20240701 080000;1.1;1.2;1.0;1.16;0\n')
            with self.assertRaisesRegex(ValueError,'Conflicting'):read_raw_archive(path)

    def test_wrong_member_and_invalid_ohlc_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=archive(folder,'20240701 080000;1.1;1.0;1.2;1.15;0\n')
            with self.assertRaisesRegex(ValueError,'OHLC'):read_raw_archive(path)
            with zipfile.ZipFile(path,'w') as z:z.writestr('wrong.csv','text')
            with self.assertRaisesRegex(ValueError,'price member'):read_raw_archive(path)

    def test_missing_receipt_or_modified_archive_cannot_convert(self):
        with tempfile.TemporaryDirectory() as folder:
            path=archive(folder,'20240701 080000;1.1;1.2;1.0;1.15;0\n')
            with self.assertRaisesRegex(ValueError,'lacks provenance'):read_histdata_zip(path)
            write_json(metadata_path(path),receipt(path))
            self.assertEqual(read_histdata_zip(path).time.iloc[0],pd.Timestamp('2024-07-01 12:00'))
            with zipfile.ZipFile(path,'a') as z:z.writestr('changed.txt','x')
            with self.assertRaisesRegex(ValueError,'unverified'):read_histdata_zip(path)

    def test_unverified_tls_or_clock_cannot_convert(self):
        with tempfile.TemporaryDirectory() as folder:
            path=archive(folder,'20240701 080000;1.1;1.2;1.0;1.15;0\n')
            for update in [dict(tls_verified=False),dict(clock_verification={})]:
                write_json(metadata_path(path),dict(receipt(path),**update))
                with self.assertRaises(ValueError):read_histdata_zip(path)

    def test_annual_lookup_does_not_accidentally_select_a_monthly_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'DAT_ASCII_EURUSD_M1_202401.zip').touch()
            self.assertIsNone(find_zip(Path(folder),'EURUSD',2024,None))


class HistDataOutputTests(unittest.TestCase):
    def test_shortened_migration_filename_requires_every_missing_day_quarantined(self):
        from audit_histdata_provenance import check_output_name
        old=Path('EURUSD_D1_20160103-20260724.csv')
        new=Path('EURUSD_D1_20160103-20260722.csv')
        meta=dict(data_quality=dict(conflicting_utc_minutes=['2026-07-23 10:00','2026-07-24 11:00']))
        check_output_name(old,new,meta)
        meta['data_quality']['conflicting_utc_minutes'].pop()
        with self.assertRaisesRegex(ValueError,'not explained'):check_output_name(old,new,meta)
        with self.assertRaisesRegex(ValueError,'Unexpected'):
            check_output_name(old,Path('EURUSD_D1_20160103-20260725.csv'),meta)

    def test_conflicts_exclude_all_versions_and_every_containing_candle(self):
        with tempfile.TemporaryDirectory() as folder:
            path=archive(folder,
                '20240701 080000;1.1;1.2;1.0;1.15;0\n'
                '20240701 080100;1.1;1.2;1.0;1.15;0\n'
                '20240701 080100;1.1;1.2;1.0;1.16;0\n'
                '20240702 080000;1.1;1.2;1.0;1.15;0\n')
            source=receipt(path)
            write_json(metadata_path(path),source)
            raw=read_histdata_zip(path)
            self.assertEqual(len(raw),2)
            self.assertEqual(source['clock_verification']['raw_cleanup']['conflicting_rows_excluded'],2)
            for timeframe in ['M1','M5','M15','H1','H4','D1']:
                with self.subTest(timeframe=timeframe):
                    out=Path(folder)/'histdata'/timeframe
                    save_timeframe(raw,'EURUSD',timeframe,out,[source])
                    csv=next(out.glob('*.csv'))
                    data=pd.read_csv(csv,parse_dates=['time'])
                    self.assertEqual(len(data),2 if timeframe=='M1' else 1)
                    self.assertTrue(load_csv(str(csv)))
                    meta=json.loads(metadata_path(csv).read_text())
                    self.assertEqual(meta['data_quality']['conflicting_utc_minutes'],['2024-07-01 12:01:00'])
            source['clock_verification']['raw_cleanup']['conflicting_local_minutes']=[]
            write_json(metadata_path(path),source)
            with self.assertRaisesRegex(ValueError,'cleanup differs'):read_histdata_zip(path)

    def test_verified_resample_load_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as folder:
            raw,ref=sample('new_york')
            path=archive(folder,'20240701 080000;1.1;1.2;1.0;1.15;0\n')
            source=receipt(path)
            out=Path(folder)/'histdata'
            raw.time=to_utc(raw.time,'new_york')
            save_timeframe(raw,'EURUSD','H4',out,[source])
            csv=next(out.glob('*.csv'))
            self.assertTrue(load_csv(str(csv)))
            with self.assertRaisesRegex(ValueError,'already UTC'):load_csv(str(csv),time_basis='icmarkets')
            with csv.open('a') as stream:stream.write('\n')
            with self.assertRaisesRegex(ValueError,'Unverified or changed'):load_csv(str(csv))

    def test_legacy_csv_without_contract_is_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'histdata'/'EURUSD_M5_20240101-20240102.csv'
            p.parent.mkdir();p.write_text('time,open,high,low,close\n2024-01-01,1,1,1,1\n')
            with self.assertRaisesRegex(ValueError,'Unverified or changed'):load_csv(str(p))

    def test_unverified_resampling_does_not_publish_a_csv(self):
        with tempfile.TemporaryDirectory() as folder:
            raw,_=sample('new_york')
            with self.assertRaisesRegex(ValueError,'Verified source receipts'):
                save_timeframe(raw,'EURUSD','H4',Path(folder))
            self.assertFalse(list(Path(folder).glob('*.csv')))
