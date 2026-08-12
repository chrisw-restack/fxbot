import tempfile
import unittest
from pathlib import Path

import pandas as pd

from data.historical_loader import load_csv


def _write_d1_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            'time': ['2026-08-09 21:00:00', '2026-08-10 21:00:00'],
            'open': [1.0, 1.1],
            'high': [1.2, 1.3],
            'low': [0.9, 1.0],
            'close': [1.1, 1.2],
            'volume': [100, 110],
        }
    ).to_csv(path, index=False)


class HistoricalLoaderTests(unittest.TestCase):
    def test_utc_normalized_mt5_keeps_sunday_d1_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = (
                Path(tmp)
                / 'mt5_icmarkets_utc'
                / 'EURUSD_D1_20260809-20260810.csv'
            )
            _write_d1_csv(path)

            bars = load_csv(str(path))

        self.assertEqual(len(bars), 2)
        self.assertEqual(bars[0].timestamp, pd.Timestamp('2026-08-09 21:00:00'))

    def test_non_mt5_data_still_drops_weekend_d1_bar(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'EURUSD_D1_20260809-20260810.csv'
            _write_d1_csv(path)

            bars = load_csv(str(path))

        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0].timestamp, pd.Timestamp('2026-08-10 21:00:00'))

    def test_load_csv_applies_date_bounds_before_returning_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = (
                Path(tmp)
                / 'mt5_icmarkets_utc'
                / 'EURUSD_D1_20260809-20260810.csv'
            )
            _write_d1_csv(path)

            bars = load_csv(
                str(path),
                start=pd.Timestamp('2026-08-10 00:00:00'),
                end=pd.Timestamp('2026-08-11 00:00:00'),
            )

        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0].timestamp, pd.Timestamp('2026-08-10 21:00:00'))


if __name__ == '__main__':
    unittest.main()
