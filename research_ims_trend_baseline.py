"""Frozen pre-correction IMS for reproducible historical controls only."""
import hashlib
import subprocess
from pathlib import Path

REVISION = 'fcecee82022a1601a869bde0795737cbedb17392'
SOURCE = subprocess.check_output(['git', 'show', f'{REVISION}:strategies/ims.py'],
                                 cwd=Path(__file__).resolve().parent).decode('utf-8')
SOURCE_SHA256 = hashlib.sha256(SOURCE.encode()).hexdigest()
_namespace = {'__name__': 'frozen_ims_trend'}
exec(compile(SOURCE, f'{REVISION}:strategies/ims.py', 'exec'), _namespace)
ImsStrategy = _namespace['ImsStrategy']
