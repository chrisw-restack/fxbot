"""Trusted frozen Running implementation from the 25 September review."""
import subprocess

REVISION = '2d58c1b24424a235d3337627850b15fc778e6040'
SOURCE = subprocess.check_output(
    ['git','show',f'{REVISION}:strategies/ema_fib_running.py'],text=True,encoding='utf-8')
_namespace = {'__name__': __name__}
exec(compile(SOURCE,'<frozen Running review baseline>','exec'),_namespace)
EmaFibRunningStrategy = _namespace['EmaFibRunningStrategy']
