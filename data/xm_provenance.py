"""UTC XM file integrity and bounds for independent, warmed replay segments."""
from pathlib import Path
import json

import pandas as pd

from data.histdata_provenance import file_hash


def validate_xm_output(path, metadata, start=None, end=None, time_basis=None):
    required_hashes = ('csv_sha256','source_sha256','source_manifest_sha256',
                       'processor_sha256','evidence_clock_reference_sha256')
    if (metadata.get('provider')!='XM' or metadata.get('processing_schema_version')!=1
            or metadata.get('research_status')!='approved_native_resolution'
            or metadata.get('time_basis')!='utc' or metadata.get('session_origin')!='xm'
            or any(len(metadata.get(k,''))!=64 for k in required_hashes)
            or file_hash(path)!=metadata['csv_sha256']):
        raise ValueError('Unverified or changed XM CSV; run the XM preparation audit first')
    parts = Path(path).stem.split('_')
    if len(parts)<3 or parts[:2]!=[metadata.get('symbol'),metadata.get('timeframe')]:
        raise ValueError('XM symbol/timeframe filename differs from audited metadata')
    dataset_path = Path(path).parent/'xm_dataset.json'
    if dataset_path.exists():
        contract = json.loads(dataset_path.read_text(encoding='utf-8')).get('files',{}).get(Path(path).name,{})
        sidecar = Path(str(path)+'.meta.json')
        if (not sidecar.exists() or contract.get('csv_sha256')!=metadata['csv_sha256']
                or contract.get('metadata_sha256')!=file_hash(sidecar)):
            raise ValueError('XM metadata/intervals differ from the completed dataset manifest')
    elif any(p.lower().startswith('xm_processed') for p in Path(path).parts[:-1]):
        raise ValueError('XM prepared dataset manifest is missing; processing is incomplete')
    if time_basis not in (None,'utc'):
        raise ValueError('Prepared XM candles are UTC; a second conversion is not permitted')
    first,end_of_data = pd.Timestamp(metadata['coverage_start']),pd.Timestamp(metadata['coverage_end'])
    left,right = pd.Timestamp(start) if start is not None else first,pd.Timestamp(end) if end is not None else end_of_data
    if any(t.tzinfo is not None for t in (first,end_of_data,left,right)):
        raise ValueError('XM replay bounds must use naive UTC timestamps')
    if left>=right or left<first or right>end_of_data:
        raise ValueError(f'XM replay lies outside verified coverage [{first}, {end_of_data})')
    intervals = metadata.get('replay_intervals',[])
    if not any(left>=pd.Timestamp(i['start']) and right<=pd.Timestamp(i['end']) for i in intervals):
        raise ValueError('XM replay crosses a quarantined interval or unexplained long gap. '
                         'Choose a shared audited interval and restart/warm up independently.')
