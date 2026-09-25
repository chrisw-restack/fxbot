"""Frozen EmaFib implementation reviewed on 23 September, for research only."""
import subprocess

REVISION = '0a1caec9307d2f80987d61da8a6228807be6a8e2'
SOURCE = subprocess.check_output(
    ['git', 'show', f'{REVISION}:strategies/ema_fib_retracement.py'], text=True, encoding='utf-8')
_namespace = {'__name__': __name__}
exec(compile(SOURCE, '<frozen EmaFib baseline>', 'exec'), _namespace)
EmaFibRetracementStrategy = _namespace['EmaFibRetracementStrategy']
