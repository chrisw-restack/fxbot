"""XM exclusions, session gaps, clock limits, and guarded UTC replay inputs."""
from datetime import datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd
import numpy as np

from data.historical_loader import load_csv
from data.histdata_provenance import file_hash
from data.xm_provenance import validate_xm_output
from prepare_xm_history import (coarser_matches, mask_intervals, allowed_intervals,
                                gap_inventory, aggregation_audit, xm_utc, clock_keys)
from audit_xm_early_clocks import daily_offsets
from summarize_xm_preparation import restrict_price_hazards


def candles(index, volume=1):
    return pd.DataFrame(dict(open=1.,high=1.2,low=.9,close=1.1,volume=volume,spread=10),index=index)


class XmPreparationTests(unittest.TestCase):
    def test_parent_price_difference_blocks_finer_replay_for_entire_parent_day(self):
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'EURUSD_M5_20260105-20260107.csv'
            candles(pd.DatetimeIndex(['2026-01-05 12:00','2026-01-06 12:00','2026-01-07 12:00'])).to_csv(path,index_label='time')
            interval=dict(start='2026-01-05 00:00',end='2026-01-08 00:00')
            meta=dict(provider='XM',session_origin='xm',time_basis='utc',research_status='approved_native_resolution',
                processing_schema_version=1,csv_sha256=file_hash(path),source_sha256='a'*64,source_manifest_sha256='b'*64,
                processor_sha256='c'*64,evidence_clock_reference_sha256='d'*64,symbol='EURUSD',timeframe='M5',
                coverage_start=interval['start'],coverage_end=interval['end'],replay_intervals=[interval])
            sidecar=Path(str(path)+'.meta.json')
            sidecar.write_text(json.dumps(meta))
            info=dict(timeframes={'M5':dict(file=str(path),replay_intervals=[interval])},joint_all_timeframe_intervals=[dict(**interval,days=3)])
            restrict_price_hazards(info,{'D1':dict(difference_server_times=['2026-01-06 00:00:00'])})
            with self.assertRaisesRegex(ValueError,'crosses'):
                load_csv(str(path),start=datetime(2026,1,6,11),end=datetime(2026,1,6,13))
            bars=load_csv(str(path),start=datetime(2026,1,7,11),end=datetime(2026,1,7,13))
            self.assertEqual(len(bars),1)
            self.assertEqual(info['partial_price_hazard_intervals'][0]['start'],'2026-01-05 22:00:00')

    def test_raw_snapshot_with_lost_sidecar_cannot_default_to_utc(self):
        with TemporaryDirectory(prefix='xm_inspection_') as tmp:
            path=Path(tmp)/'EURUSD_M5_20260105-20260106.csv'
            candles(pd.date_range('2026-01-05',periods=2,freq='5min')).to_csv(path,index_label='time')
            with self.assertRaisesRegex(ValueError,'Unverified'):
                load_csv(str(path),time_basis='utc')

    def test_day_audit_detects_mixed_offsets_inside_one_month(self):
        rng = np.random.default_rng(39)
        index = pd.date_range('2013-06-03',periods=288*2,freq='5min')
        reference = pd.DataFrame(dict(time=index,close=1.+np.cumsum(rng.normal(0,.0001,len(index)))))
        raw = reference.copy()
        raw.loc[:287,'time'] += pd.Timedelta(hours=2)
        raw.loc[288:,'time'] += pd.Timedelta(hours=3)
        audit = daily_offsets(raw,reference)
        full = [d for d in audit if d['scores']['2']['pairs']>200 and d['scores']['3']['pairs']>200]
        self.assertEqual([(d['observed_offset'],d['verified']) for d in full],[(2,True),(3,True)])

    def test_exact_nonflat_parent_copy_is_flagged_but_flat_one_quote_is_not(self):
        index = pd.date_range('2026-01-05',periods=2,freq='h')
        parent = candles(index)
        parent.loc[index[1],['open','high','low','close']] = 1.
        matches = coarser_matches({'M5':parent.copy(),'M15':parent.copy(),'H1':parent.copy(),'H4':parent.iloc[:0],'D1':parent.iloc[:0]},'M5')
        self.assertEqual(matches.iloc[0],'H1')
        self.assertEqual(matches.iloc[1],'')

    def test_short_session_parent_equality_is_retained_when_own_m5_proves_prices(self):
        index = pd.date_range('2026-01-09 23:00',periods=3,freq='5min')
        fine = candles(index)
        parent = candles(index[:1],volume=3)
        frames = {'M5':fine,'M15':parent.copy(),'H1':parent.copy(),'H4':parent.iloc[:0],'D1':parent.iloc[:0]}
        self.assertEqual(coarser_matches(frames,'M15').iloc[0],'H1')
        self.assertEqual(coarser_matches(frames,'M15',fine).iloc[0],'')
        # An H1 proxy with a later extreme fails the requested M15 comparison.
        frames['M15'].high=1.5
        frames['H1'].high=1.5
        self.assertEqual(coarser_matches(frames,'M15',fine).iloc[0],'H1')

    def test_good_friday_index_gap_has_calendar_and_reference_closure_evidence(self):
        index = pd.DatetimeIndex(['2026-04-02 20:00','2026-04-06 00:00'])
        reference = pd.DatetimeIndex(['2026-04-02 16:00','2026-04-05 22:00'])
        gaps,blocked=gap_inventory(index,'H4','USTEC',reference)
        self.assertEqual(gaps.iloc[0].kind,'holiday_closure_candidate')
        self.assertEqual(blocked,[])
        # Quotes during the supposed closure prevent that holiday exemption.
        with_quotes=reference.union(pd.DatetimeIndex(['2026-04-03 14:00']))
        gaps,blocked=gap_inventory(index,'H4','USTEC',with_quotes)
        self.assertEqual(gaps.iloc[0].kind,'unexplained_long_gap')
        self.assertTrue(blocked)

    def test_excluded_source_run_and_complement_do_not_bridge_a_hole(self):
        index = pd.date_range('2026-01-05',periods=8,freq='5min')
        holes = mask_intervals(index,[False,True,True,False,False,True,False,False],5)
        valid = allowed_intervals(index[0],index[-1]+pd.Timedelta(minutes=5),holes)
        self.assertEqual(valid,[(index[0],index[1]),(index[3],index[5]),(index[6],index[-1]+pd.Timedelta(minutes=5))])

    def test_weekend_is_reported_without_an_outage_boundary(self):
        index = pd.DatetimeIndex(['2026-01-09 23:55','2026-01-12 00:00'])
        gaps,blocked = gap_inventory(index,'M5','EURUSD')
        self.assertEqual(gaps.iloc[0].kind,'weekend_closure_candidate')
        self.assertEqual(blocked,[])

    def test_intraday_hour_of_missing_quotes_requires_replay_boundary(self):
        index = pd.DatetimeIndex(['2026-01-05 10:00','2026-01-05 11:05'])
        reference = pd.date_range('2026-01-05 08:00','2026-01-05 09:05',freq='5min')
        gaps,blocked = gap_inventory(index,'M5','EURUSD',reference)
        self.assertEqual(gaps.iloc[0].kind,'unexplained_long_gap')
        self.assertEqual(gaps.iloc[0].reference_m5_records,12)
        self.assertEqual(blocked,[(pd.Timestamp('2026-01-05 10:05'),pd.Timestamp('2026-01-05 11:05'))])

    def test_recurring_index_overnight_break_is_recognized_on_hourly_grid(self):
        index = pd.DatetimeIndex([t for day in pd.bdate_range('2026-01-05',periods=35)
            for t in (day+pd.Timedelta(hours=1),day+pd.Timedelta(hours=23))])
        gaps,_ = gap_inventory(index,'H1','USTEC')
        overnight = gaps.loc[(pd.to_datetime(gaps.previous_server).dt.hour==23)
                             & (pd.to_datetime(gaps.next_server).dt.hour==1)
                             & (gaps.missing_minutes==60)]
        self.assertTrue(len(overnight)>=20)
        self.assertTrue((overnight.kind=='recurring_overnight_break_candidate').all())

    def test_partial_parent_is_not_compared_as_a_complete_candle(self):
        index = pd.date_range('2026-01-05',periods=3,freq='5min')
        m5 = candles(index)
        parent = candles(index[:1],volume=3)
        self.assertEqual(aggregation_audit(m5,parent,'M15',.00001)['ohlc_mismatches'],0)
        parent.high = 1.5
        self.assertEqual(aggregation_audit(m5,parent,'M15',.00001)['ohlc_mismatches'],1)
        self.assertEqual(aggregation_audit(m5.iloc[:2],parent,'M15',.00001)['complete_bars_compared'],0)

    def test_european_clock_and_non_nominal_dst_candle_are_visible(self):
        index = pd.DatetimeIndex(['2026-03-16','2026-03-30','2026-10-25'])
        utc = xm_utc(index)
        self.assertEqual(utc[0],pd.Timestamp('2026-03-15 22:00'))
        self.assertEqual(utc[1],pd.Timestamp('2026-03-29 21:00'))
        self.assertEqual(xm_utc(index+pd.Timedelta(days=1))[2]-utc[2],pd.Timedelta(hours=25))
        keys = clock_keys(index)
        self.assertEqual(keys[0],('2026-03',2,3))

    def test_changed_file_missing_sidecar_and_cross_gap_replay_are_blocked(self):
        with TemporaryDirectory(prefix='mt5_xm_') as tmp:
            path = Path(tmp)/'EURUSD_M5_20260105-20260106.csv'
            candles(pd.DatetimeIndex(['2026-01-05 10:00','2026-01-05 11:05'])).to_csv(path,index_label='time')
            meta = dict(provider='XM',session_origin='xm',time_basis='utc',
                research_status='approved_native_resolution',processing_schema_version=1,
                csv_sha256=file_hash(path),source_sha256='a'*64,source_manifest_sha256='b'*64,
                processor_sha256='c'*64,evidence_clock_reference_sha256='d'*64,
                symbol='EURUSD',timeframe='M5',coverage_start='2026-01-05 10:00',coverage_end='2026-01-05 11:10',
                replay_intervals=[dict(start='2026-01-05 10:00',end='2026-01-05 10:05'),dict(start='2026-01-05 11:05',end='2026-01-05 11:10')])
            sidecar = Path(str(path)+'.meta.json')
            sidecar.write_text(json.dumps(meta))
            with self.assertRaisesRegex(ValueError,'crosses'):
                load_csv(str(path))
            bars = load_csv(str(path),start=datetime(2026,1,5,11,5),end=datetime(2026,1,5,11,10))
            self.assertEqual(len(bars),1)
            original_sidecar = sidecar.read_bytes()
            (path.parent/'xm_dataset.json').write_text(json.dumps(dict(files={path.name:dict(
                csv_sha256=meta['csv_sha256'],metadata_sha256=file_hash(sidecar))})))
            modified = dict(meta,replay_intervals=[dict(start=meta['coverage_start'],end=meta['coverage_end'])])
            sidecar.write_text(json.dumps(modified))
            with self.assertRaisesRegex(ValueError,'metadata/intervals'):
                load_csv(str(path))
            sidecar.write_bytes(original_sidecar)
            with self.assertRaisesRegex(ValueError,'second conversion'):
                validate_xm_output(path,meta,time_basis='icmarkets')
            path.write_text(path.read_text()+'\n')
            with self.assertRaisesRegex(ValueError,'changed'):
                load_csv(str(path))
            sidecar.unlink()
            with self.assertRaisesRegex(ValueError,'Unverified'):
                load_csv(str(path))

    def test_requested_bounds_cannot_include_unverified_prefix_or_missing_tail(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp)/'EURUSD_M5_20260105-20260106.csv'
            path.write_text('test')
            meta = dict(provider='XM',session_origin='xm',time_basis='utc',research_status='approved_native_resolution',
                processing_schema_version=1,csv_sha256=file_hash(path),source_sha256='a'*64,source_manifest_sha256='b'*64,
                processor_sha256='c'*64,evidence_clock_reference_sha256='d'*64,symbol='EURUSD',timeframe='M5',
                coverage_start='2026-01-05',coverage_end='2026-01-06',
                replay_intervals=[dict(start='2026-01-05',end='2026-01-06')])
            with self.assertRaisesRegex(ValueError,'outside'):
                validate_xm_output(path,meta,start=datetime(2026,1,4))
            with self.assertRaisesRegex(ValueError,'outside'):
                validate_xm_output(path,meta,end=datetime(2026,1,7))


if __name__ == '__main__':
    unittest.main()
