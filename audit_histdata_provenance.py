"""Verify HistData archives against fresh official downloads and UTC references.

Sequential and resumable. No trading or strategy evaluation. Old inputs remain
untouched until a separately requested rebuild has passed validation.
"""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import ssl
import time
import shutil

import certifi
import pandas as pd

from fetch_data_histdata import download_zip, HISTDATA_SYMBOLS, read_histdata_zip, save_timeframe
from data.histdata_provenance import (read_raw_archive, infer_clock, validate_frame,
                                    verified_archive_metadata, validate_output_metadata, metadata_path)

ROOT = Path(__file__).resolve().parent
OLD_RAW = ROOT / 'data/raw/histdata'
VERIFIED_RAW = ROOT / 'data/raw/histdata_verified_20260921'
OUT = ROOT / 'output/histdata_provenance_20260921'


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.part')
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding='utf-8')
    tmp.replace(path)


def refresh_archives():
    context = ssl.create_default_context(cafile=certifi.where())
    files = sorted(OLD_RAW.glob('DAT_ASCII_*_M1_*.zip'))
    records = []
    for index, old in enumerate(files, 1):
        _, _, symbol, _, period = old.stem.split('_')
        year = int(period[:4])
        month = int(period[4:]) if len(period) == 6 else None
        path = VERIFIED_RAW / old.name
        receipt = Path(str(path) + '.meta.json')
        if receipt.exists() and path.exists():
            record = json.loads(receipt.read_text(encoding='utf-8'))
            if record.get('sha256') != sha256(path):
                raise ValueError(f'Previously downloaded archive changed: {path}')
        else:
            print(f'[{index}/{len(files)}] Downloading {symbol} {period}', flush=True)
            for attempt in range(3):
                try:
                    path = download_zip(symbol, year, month, VERIFIED_RAW, context)
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    time.sleep(5 * (attempt + 1))
            source_url = f'https://www.histdata.com/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes/{symbol.lower()}/{year}'
            if month is not None:
                source_url += f'/{month}'
            record = dict(schema_version=1, provider='HistData', source_url=source_url,
                          download_url='https://www.histdata.com/get.php',
                          downloaded_at_utc=datetime.now(timezone.utc).isoformat(),
                          tls_verified=True, sha256=sha256(path), size_bytes=path.stat().st_size,
                          source_symbol=symbol, period=period)
            write_json(receipt, record)
            time.sleep(1)
        record = dict(record, old_path=str(old.relative_to(ROOT)), old_sha256=sha256(old))
        record['identical_to_old'] = record['old_sha256'] == record['sha256']
        records.append(record)
        write_json(OUT / 'downloads.json', records)
        print(f'[{index}/{len(files)}] Verified {old.name}; identical={record["identical_to_old"]}', flush=True)


def reference_for(symbol):
    project = next((p for p, source in HISTDATA_SYMBOLS.items() if source == symbol), symbol)
    # Early broker-export transition weeks disagree with direct UTC references.
    # Use the explicitly UTC Dukascopy export for the source-clock decision and
    # retain broker disagreements as a separate audit finding, not a time shift.
    matches = sorted((ROOT / 'data/historical').glob(f'{project}_M5_*.csv'))
    if len(matches) != 1:
        raise ValueError(f'Need one unambiguous UTC M5 reference for {project}: {matches}')
    path, provider = matches[0], 'Dukascopy UTC export; feed independence not assumed'
    df = pd.read_csv(path, usecols=['time', 'close'], parse_dates=['time'])
    if df.time.duplicated().any() or not df.time.is_monotonic_increasing:
        raise ValueError(f'Invalid reference timestamps: {path}')
    return df, dict(path=str(path.relative_to(ROOT)), sha256=sha256(path), provider=provider,
                    time_basis='utc')


def verify_clocks(raw_dir=OLD_RAW, resume=False, quarantine_conflicts=False):
    records, failures = {}, []
    prior = {}
    if resume and (OUT / 'clock_audit.json').exists():
        prior = json.loads((OUT / 'clock_audit.json').read_text(encoding='utf-8'))['archives']
    reference_symbol = None
    files = sorted(raw_dir.glob('DAT_ASCII_*_M1_*.zip'))
    for index, path in enumerate(files, 1):
        symbol = path.stem.split('_')[2]
        if symbol != reference_symbol:
            reference, reference_info = reference_for(symbol)
            reference_symbol = symbol
        digest = sha256(path)
        try:
            cached = prior.get(digest)
            if (cached and cached['clock_verification'].get('reference') == reference_info
                    and all('eu_shift' in w for w in cached['clock_verification']['windows'])):
                records[digest] = dict(cached, path=str(path.relative_to(ROOT)))
                proof = cached['clock_verification']
            else:
                raw = read_raw_archive(path, quarantine_conflicts=quarantine_conflicts)
                bounds = (reference.time >= raw.time.min()+pd.Timedelta(hours=3)) & (reference.time <= raw.time.max()+pd.Timedelta(hours=6))
                proof = infer_clock(raw, reference.loc[bounds])
                proof['reference'] = reference_info
                proof['raw_cleanup'] = raw.attrs.get('raw_cleanup', {})
                records[digest] = dict(path=str(path.relative_to(ROOT)), sha256=digest,
                                       clock_verification=proof, rows=len(raw),
                                       first_local=str(raw.time.iloc[0]), last_local=str(raw.time.iloc[-1]))
            receipt_path = Path(str(path) + '.meta.json')
            if receipt_path.exists():
                receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
                if receipt.get('sha256') == digest and receipt.get('tls_verified') is True:
                    receipt['clock_verification'] = proof
                    write_json(receipt_path, receipt)
            print(f'[{index}/{len(files)}] {path.name}: {proof["source_clock"]}', flush=True)
        except ValueError as error:
            failure = dict(path=str(path), error=str(error))
            failures.append(failure)
            print(f'[{index}/{len(files)}] FAILED: {failure}', flush=True)
        write_json(OUT / 'clock_audit.json', dict(archives=records, failures=failures))
    if failures:
        raise RuntimeError(f'{len(failures)} source-clock checks failed; no unverified conversion is permitted')


def rebuild_existing():
    """Stage and validate every existing timeframe before publishing any replacement."""
    if (OUT / 'published.json').exists():
        raise ValueError('This dated migration is already published; use the normal converter for future downloads')
    old_zips = sorted(OLD_RAW.glob('DAT_ASCII_*_M1_*.zip'))
    for path in old_zips:
        verified_archive_metadata(VERIFIED_RAW / path.name)
    active = ROOT / 'data/historical/histdata'
    existing = sorted(active.glob('*.csv'))
    symbols = sorted({p.name.split('_')[0] for p in existing})
    plan = []
    for symbol in symbols:
        old_files = [p for p in existing if p.name.startswith(symbol+'_')]
        cutoff = max(pd.Timestamp(p.stem.split('_')[-1].split('-')[-1]) for p in old_files) + pd.Timedelta(days=1)
        source_symbol = HISTDATA_SYMBOLS[symbol]
        sources, chunks = [], []
        for old in old_zips:
            if old.stem.split('_')[2] != source_symbol:
                continue
            chunk = read_histdata_zip(VERIFIED_RAW / old.name)
            sources.append(chunk.attrs.pop('histdata_source'))
            chunks.append(chunk)
        frame = pd.concat(chunks, ignore_index=True).sort_values('time').reset_index(drop=True)
        validate_frame(frame, symbol)
        frame = frame[frame.time < cutoff]
        print(f'{symbol}: rebuilding {len(old_files)} timeframes from {len(frame):,} verified M1 rows', flush=True)
        staging = OUT / 'rebuilt' / symbol
        for old in old_files:
            timeframe = old.name.split('_')[1]
            save_timeframe(frame, symbol, timeframe, staging, sources)
            matches = list(staging.glob(f'{symbol}_{timeframe}_*.csv'))
            if len(matches) != 1:
                raise ValueError(f'Ambiguous staged output: {matches}')
            new = matches[0]
            meta = json.loads(metadata_path(new).read_text(encoding='utf-8'))
            validate_output_metadata(new, meta)
            before = pd.read_csv(old, parse_dates=['time']).set_index('time')
            after = pd.read_csv(new, parse_dates=['time']).set_index('time')
            common = before.index.intersection(after.index)
            changed = (before.loc[common].round(10) != after.loc[common].round(10)).any(axis=1)
            plan.append(dict(old=str(old.relative_to(ROOT)), staged=str(new.relative_to(ROOT)),
                old_sha256=sha256(old), new_sha256=sha256(new), rows_before=len(before), rows_after=len(after),
                common_rows_changed=int(changed.sum()), timestamps_added=len(after.index.difference(before.index)),
                timestamps_removed=len(before.index.difference(after.index)), cutoff_exclusive=str(cutoff)))
            write_json(OUT / 'rebuild_plan.json', plan)
        del frame, chunks
    if len(plan) != len(existing):
        raise RuntimeError('Incomplete rebuild; refusing publication')
    publish_staged(plan)


def check_output_name(old, new, meta):
    if old.name == new.name:
        return
    old_symbol, old_tf, old_dates = old.stem.split('_')
    new_symbol, new_tf, new_dates = new.stem.split('_')
    old_start, old_end = old_dates.split('-')
    new_start, new_end = new_dates.split('-')
    # Removing a conflicted final day legitimately shortens three D1 files.
    # Every missing trailing date must be explained by the recorded quarantine.
    if (old_symbol != new_symbol or old_tf != new_tf or old_tf != 'D1'
            or old_start != new_start or new_end >= old_end):
        raise ValueError('Unexpected coverage/filename change')
    missing_days = pd.date_range(pd.Timestamp(new_end)+pd.Timedelta(days=1), pd.Timestamp(old_end))
    excluded_days = pd.DatetimeIndex(meta.get('data_quality', {}).get('conflicting_utc_minutes', [])).floor('D')
    if not missing_days.isin(excluded_days).all():
        raise ValueError('Shortened coverage is not explained by quarantined final days')


def publish_staged(plan):
    if (OUT / 'published.json').exists():
        raise ValueError('This dated migration is already published')
    active = ROOT / 'data/historical/histdata'
    existing = sorted(active.glob('*.csv'))
    old_zips = sorted(OLD_RAW.glob('DAT_ASCII_*_M1_*.zip'))
    if {str(p.relative_to(ROOT)) for p in existing} != {item['old'] for item in plan}:
        raise ValueError('Staged plan does not match the complete active CSV set')
    for old in old_zips:
        verified_archive_metadata(VERIFIED_RAW / old.name)
    for item in plan:
        old, new = ROOT/item['old'], ROOT/item['staged']
        if old.resolve().parent != active.resolve() or not new.resolve().is_relative_to((OUT/'rebuilt').resolve()):
            raise ValueError('Staged publication path escapes its expected directory')
        meta = json.loads(metadata_path(new).read_text(encoding='utf-8'))
        validate_output_metadata(new, meta)
        check_output_name(old, new, meta)
        if sha256(new) != item['new_sha256']:
            raise ValueError(f'Staged file changed: {new}')
        if sha256(old) != item['old_sha256']:
            raise ValueError(f'Active file changed during rebuild: {old}')
        item['published'] = str((active/new.name).relative_to(ROOT))
    # Every destination is resolved and constrained to this repository before mutation.
    archive_dir = ROOT / 'data/historical/_quarantine_histdata_20260921'
    raw_archive_dir = ROOT / 'data/raw/histdata_unverified_20260921'
    for directory in (archive_dir, raw_archive_dir, active, OLD_RAW):
        if not directory.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError(f'Archive/publish directory is outside the repository: {directory}')
        directory.mkdir(parents=True, exist_ok=True)
    # Check every backup before publishing the first file.
    for item in plan:
        backup = archive_dir / Path(item['old']).name
        if backup.exists() and sha256(backup) != item['old_sha256']:
            raise ValueError(f'Would replace a different legacy backup: {backup}')
    for old in old_zips:
        backup = raw_archive_dir / old.name
        if sha256(old) != sha256(VERIFIED_RAW / old.name) and backup.exists() and sha256(backup) != sha256(old):
            raise ValueError(f'Would replace a different raw backup: {backup}')
    for item in plan:
        old, new = ROOT/item['old'], ROOT/item['staged']
        if sha256(old) != item['old_sha256']:
            raise ValueError(f'Active file changed during rebuild: {old}')
        backup = archive_dir / old.name
        if backup.exists() and sha256(backup) != item['old_sha256']:
            raise ValueError(f'Would replace a different legacy backup: {backup}')
        shutil.copy2(old, backup)
        write_json(metadata_path(backup), dict(provider='HistData', provenance_status='quarantined_legacy',
            sha256=item['old_sha256'], reason='Prior unverified timezone conversion; historical comparisons only'))
        target = active / new.name
        temporary = target.with_suffix('.csv.part')
        shutil.copy2(new, temporary)
        temporary.replace(target)
        shutil.copy2(metadata_path(new), metadata_path(target))
        if target != old:
            # Keep the old bytes in the checked backup, but remove their old name
            # from discovery so the same timeframe is not loaded twice.
            old.replace(backup)
            if metadata_path(old).exists():
                metadata_path(old).replace(Path(str(backup)+'.original.meta.json'))
    for old in old_zips:
        new = VERIFIED_RAW / old.name
        if sha256(old) != sha256(new):
            backup = raw_archive_dir / old.name
            if backup.exists() and sha256(backup) != sha256(old):
                raise ValueError(f'Would replace a different raw backup: {backup}')
            shutil.copy2(old, backup)
            temporary = old.with_suffix('.zip.part')
            shutil.copy2(new, temporary)
            temporary.replace(old)
        shutil.copy2(metadata_path(new), metadata_path(old))
    write_json(OUT / 'published.json', dict(published_at_utc=datetime.now(timezone.utc).isoformat(),
        csv_count=len(plan), raw_archive_count=len(old_zips), backup_dir=str(archive_dir.relative_to(ROOT)),
        plan=plan))
    print(f'Published {len(plan)} verified CSVs; all previous CSVs retained in {archive_dir}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download', action='store_true')
    parser.add_argument('--verify-clocks', action='store_true')
    parser.add_argument('--raw-dir', type=Path, default=OLD_RAW)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--quarantine-conflicts', action='store_true',
        help='Record and exclude every conflicting minute and its containing resampled candles.')
    parser.add_argument('--rebuild', action='store_true')
    parser.add_argument('--publish-staged', action='store_true', help='Recheck and publish this migration\'s completed staged plan.')
    args = parser.parse_args()
    if args.download:
        refresh_archives()
    if args.verify_clocks:
        verify_clocks(args.raw_dir.resolve(), args.resume, args.quarantine_conflicts)
    if args.rebuild:
        rebuild_existing()
    elif args.publish_staged:
        publish_staged(json.loads((OUT/'rebuild_plan.json').read_text(encoding='utf-8')))
