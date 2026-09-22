"""Hash-bound HistData source-clock evidence and converted-file contracts.

HistData's FAQ says fixed EST. The archives must be measured rather than silently
assuming that claim or New York DST. References are UTC bid M5 candles; this is a
timestamp alignment check, not proof that two price feeds are independent.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd

SCHEMA_VERSION = 1
TIMEZONES = {'fixed_est': 'Etc/GMT+5', 'new_york': 'America/New_York',
             'european_dst': 'Europe/Helsinki'}
FAQ_URL = 'https://www.histdata.com/f-a-q/'


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def metadata_path(path):
    return Path(str(path) + '.meta.json')


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.part')
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding='utf-8')
    tmp.replace(path)


def read_raw_archive(path, *, quarantine_conflicts=False):
    """Read the price member, never the companion gap-status TXT report."""
    path = Path(path)
    expected = path.stem + '.csv'
    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if Path(n).name.upper() == expected.upper()]
        if len(names) != 1:
            raise ValueError(f'Expected exactly one price member {expected} in {path}')
        with archive.open(names[0]) as stream:
            df = pd.read_csv(stream, sep=';', header=None,
                             names=['time', 'open', 'high', 'low', 'close', 'volume'])
    df['time'] = pd.to_datetime(df['time'], format='%Y%m%d %H%M%S', errors='raise')
    duplicates = int(df.duplicated().sum())
    backwards = int((df.time.diff() < pd.Timedelta(0)).sum())
    df = df.drop_duplicates().sort_values('time').reset_index(drop=True)
    conflicts = df.time.duplicated(keep=False)
    conflict_times = sorted(df.loc[conflicts, 'time'].unique())
    if conflict_times and not quarantine_conflicts:
        raise ValueError(f'Conflicting prices for the same raw timestamp: {path}')
    df = df.loc[~conflicts].reset_index(drop=True)
    validate_frame(df, str(path))
    df.attrs['raw_cleanup'] = dict(exact_duplicate_rows_removed=duplicates, backward_steps_sorted=backwards)
    if conflict_times:
        df.attrs['raw_cleanup'].update(conflict_policy='exclude_all_versions_and_intersecting_candles',
            conflicting_rows_excluded=int(conflicts.sum()),
            conflicting_local_minutes=[str(pd.Timestamp(t)) for t in conflict_times])
    return df


def validate_frame(df, label):
    if df.empty or df.isna().any().any():
        raise ValueError(f'Empty or incomplete data: {label}')
    values = df[['open', 'high', 'low', 'close', 'volume']].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values[:, :4] <= 0).any() or (values[:, 4] < 0).any():
        raise ValueError(f'Invalid numeric values: {label}')
    if ((df.high < df[['open', 'close', 'low']].max(axis=1)) |
            (df.low > df[['open', 'close', 'high']].min(axis=1))).any():
        raise ValueError(f'Invalid OHLC: {label}')
    if not df.time.is_monotonic_increasing or df.time.duplicated().any():
        raise ValueError(f'Unsorted or duplicate timestamps: {label}')
    if ((df.time.dt.second != 0) | (df.time.dt.microsecond != 0)).any():
        raise ValueError(f'Non-minute timestamps: {label}')


def to_utc(local_time, clock):
    if clock not in TIMEZONES:
        raise ValueError(f'Unsupported source clock: {clock}')
    # Some archive years use UTC-5/-4 with European DST transitions. This is
    # Helsinki wall time minus seven hours, not America/New_York time.
    wall = local_time + pd.Timedelta(hours=7) if clock == 'european_dst' else local_time
    return (wall.dt.tz_localize(TIMEZONES[clock], ambiguous='raise', nonexistent='raise')
            .dt.tz_convert('UTC').dt.tz_localize(None))


def infer_clock(raw, reference, min_pairs=50, min_correlation=.8, min_margin=.3):
    """Resolve +4 versus +5 hours in each month and DST regime; reject weak evidence."""
    m5 = raw.set_index('time')['close'].resample('5min').last().dropna()
    conflicts = raw.attrs.get('raw_cleanup', {}).get('conflicting_local_minutes', [])
    if conflicts:
        m5 = m5.drop(pd.DatetimeIndex(conflicts).floor('5min').unique(), errors='ignore')
    ref = reference.set_index('time')['close']
    if not ref.index.is_unique or ref.index.tz is not None:
        raise ValueError('Reference must have unique, naive UTC timestamps')
    local = pd.Series(m5.index)
    shifts = ((to_utc(local, 'new_york') - local).dt.total_seconds() / 3600).astype(int)
    eu_shifts = ((to_utc(local, 'european_dst') - local).dt.total_seconds() / 3600).astype(int)
    groups = pd.DataFrame({'month': m5.index.strftime('%Y-%m'), 'ny_shift': shifts.to_numpy(),
                           'eu_shift': eu_shifts.to_numpy()}, index=m5.index)
    evidence = []
    for (month, ny_shift, eu_shift), group in groups.groupby(['month', 'ny_shift', 'eu_shift']):
        sample = m5.loc[group.index]
        scores = {}
        for offset in (4, 5):
            shifted = sample.copy()
            shifted.index += pd.Timedelta(hours=offset)
            joined = pd.concat([shifted.rename('raw'), ref.rename('reference')], axis=1, join='inner').dropna()
            consecutive = joined.index.to_series().diff() == pd.Timedelta(minutes=5)
            changes = joined.pct_change(fill_method=None).loc[consecutive].dropna()
            # Rank correlation prevents one provider-specific spike from deciding
            # an entire month's clock. Preserve Pearson as a diagnostic as well.
            corr = changes['raw'].rank().corr(changes['reference'].rank()) if len(changes) >= min_pairs else float('nan')
            pearson = changes['raw'].corr(changes['reference']) if len(changes) >= min_pairs else float('nan')
            scores[str(offset)] = dict(pairs=len(changes), correlation=float(corr) if np.isfinite(corr) else None,
                                      pearson_correlation=float(pearson) if np.isfinite(pearson) else None)
        ranked = sorted((s['correlation'], int(offset)) for offset, s in scores.items() if s['correlation'] is not None)
        if len(ranked) != 2 or ranked[-1][0] < min_correlation or ranked[-1][0]-ranked[-2][0] < min_margin:
            raise ValueError(f'Insufficient clock evidence for {month}, NY offset {ny_shift}: {scores}')
        best = ranked[-1][1]
        evidence.append(dict(month=month, ny_shift=int(ny_shift), eu_shift=int(eu_shift), observed_shift=best, scores=scores))
    candidates = [clock for clock in TIMEZONES if all(
        e['observed_shift'] == (5 if clock == 'fixed_est' else e['ny_shift'] if clock == 'new_york' else e['eu_shift']) for e in evidence)]
    if not candidates:
        raise ValueError('Archive has inconsistent offsets; neither supported clock fits every period')
    # Winter-only files cannot distinguish the conventions, but both convert identically.
    clock = candidates[0]
    return dict(status='verified', source_clock=clock, compatible_clocks=candidates,
                clock_rules_indistinguishable=len(candidates) > 1, windows=evidence,
                method='M5 consecutive close-return rank correlation, offsets +4 and +5 per month/US/EU DST regime',
                thresholds=dict(min_pairs=min_pairs, min_correlation=min_correlation, min_margin=min_margin),
                verified_at_utc=datetime.now(timezone.utc).isoformat())


def verified_archive_metadata(path):
    meta_file = metadata_path(path)
    if not meta_file.exists():
        raise ValueError(f'HistData archive lacks provenance: {path}. Verify its official download and source clock first.')
    meta = json.loads(meta_file.read_text(encoding='utf-8'))
    if (meta.get('provider') != 'HistData' or meta.get('schema_version') != SCHEMA_VERSION
            or meta.get('tls_verified') is not True or meta.get('sha256') != file_hash(path)
            or meta.get('clock_verification', {}).get('status') != 'verified'):
        raise ValueError(f'HistData archive provenance/hash/clock is unverified: {path}')
    if meta['clock_verification'].get('source_clock') not in TIMEZONES:
        raise ValueError(f'Unsupported verified HistData clock: {path}')
    return meta


def validate_output_metadata(path, meta):
    if (meta.get('provider') != 'HistData' or meta.get('provenance_status') != 'verified'
            or meta.get('schema_version') != SCHEMA_VERSION or meta.get('time_basis') != 'utc'
            or not meta.get('sources') or meta.get('sha256') != file_hash(path)):
        raise ValueError(f'Unverified or changed HistData CSV: {path}. Run the provenance audit/rebuild before backtesting.')
    for source in meta['sources']:
        if (not source.get('sha256') or not source.get('source_url') or source.get('tls_verified') is not True
                or source.get('clock_verification', {}).get('status') != 'verified'
                or source['clock_verification'].get('source_clock') not in TIMEZONES):
            raise ValueError(f'HistData CSV has an unverified source archive: {path}')
