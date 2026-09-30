"""Frozen Candle Confirmation signal logic before tracking corrections."""
import hashlib
from pathlib import Path
import subprocess

REVISION = 'fcecee82022a1601a869bde0795737cbedb17392'
SOURCE = subprocess.check_output(['git', 'show', f'{REVISION}:strategies/candle_confirmation.py'],
                                 cwd=Path(__file__).resolve().parent).decode('utf-8')
SOURCE_SHA256 = hashlib.sha256(SOURCE.encode()).hexdigest()
_namespace = {'__name__': 'frozen_candle_confirmation'}
exec(compile(SOURCE, f'{REVISION}:strategies/candle_confirmation.py', 'exec'), _namespace)
CandleConfirmationStrategy = _namespace['CandleConfirmationStrategy']
