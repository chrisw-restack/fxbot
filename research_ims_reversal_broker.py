"""Validate frozen IMS Reversal research choices on exported broker candles.

Runs sequentially. No MT5 connection, new parameter selection, or demo changes.
The protected forward period never enters a replay.
"""
from collections import Counter
from datetime import datetime, timedelta
import hashlib
import json
import logging
from pathlib import Path

from data.historical_loader import load_and_merge, bar_close_time
from research_ims_reversal import CUTOFF, OUT, run


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    folder = Path('data/historical/mt5_icmarkets_utc')
    files = []
    for tf in ['M5', 'M15', 'H4']:
        candidates = list(folder.glob(f'EURUSD_{tf}_*.csv'))
        if not candidates:
            raise ValueError(f'Missing broker EURUSD {tf}')
        # One fresh complete export per timeframe, never a mixture of snapshots.
        files.append(str(max(candidates, key=lambda p: p.stat().st_mtime_ns)))
    # Frozen in the preceding proxy study, before viewing broker outcomes.
    choices = [dict(year=2020, variant='ltf_fractal_1'),
               dict(year=2022, variant='ltf_fractal_1'),
               dict(year=2024, variant='ema_sep_020pct')]
    print('Loading broker EURUSD M5/M15/H4; one worker; cutoff 2026-07-15', flush=True)
    bars = load_and_merge(files, start=datetime(2019, 7, 1), end=CUTOFF)
    bars = [b for b in bars if bar_close_time(b) <= CUTOFF]
    coverage = {}
    for tf in ['M5', 'M15', 'H4']:
        times = [b.timestamp for b in bars if b.timeframe == tf]
        if not times or min(times) > datetime(2019, 7, 8) or max(times) < CUTOFF-timedelta(days=1):
            raise ValueError(f'Insufficient {tf} history for the fixed validation windows')
        coverage[tf] = dict(first=min(times), last=max(times), bars=len(times))
    manifest = dict(files=[dict(path=p, sha256=hashlib.sha256(Path(p).read_bytes()).hexdigest()) for p in files],
                    coverage=coverage, cutoff=CUTOFF, selections=choices,
                    notes='Frozen selections from Dukascopy; no broker fitting; standalone EURUSD; one worker')
    (OUT/'broker_validation_manifest.json').write_text(json.dumps(manifest, indent=2, default=str))
    print('Loaded '+str(dict(Counter(b.timeframe for b in bars))), flush=True)
    source = 'mt5_icmarkets_utc'

    def replay(variant, start, end, spread=None):
        window = [b for b in bars if start-timedelta(days=180) <= b.timestamp and bar_close_time(b) <= end]
        return run(window, source, 'EURUSD', variant, start, end, spread)

    results = []
    for c in choices:
        start = datetime(c['year'], 1, 1)
        end = datetime(c['year']+2, 1, 1)
        for variant in ['baseline', c['variant'], 'research_both']:
            results.append(replay(variant, start, end))
    for variant in ['baseline', 'research_retire_loss', 'research_pending_lifecycle', 'research_both']:
        results.append(replay(variant, datetime(2020, 1, 1), datetime(2026, 1, 1)))
    for variant in ['baseline', 'ema_sep_020pct', 'research_both']:
        results.append(replay(variant, datetime(2026, 1, 1), CUTOFF))
    for variant in ['baseline', 'research_both']:
        results.append(replay(variant, datetime(2020, 1, 1), datetime(2026, 1, 1), spread=1.0))
    (OUT/'broker_validation_runs.json').write_text(json.dumps(results, indent=2, default=str))


if __name__ == '__main__':
    logging.disable(logging.CRITICAL)
    main()
