"""Load the immutable Failed2 implementation used by the September review."""
from pathlib import Path
import subprocess

REVISION = '2d58c1b24424a235d3337627850b15fc778e6040'
SOURCE = subprocess.check_output(
    ['git', 'show', REVISION + ':strategies/failed2.py'],
    cwd=Path(__file__).resolve().parent).decode('utf-8')
namespace = {'__name__': 'failed2_review_baseline'}
exec(compile(SOURCE, REVISION + '/strategies/failed2.py', 'exec'), namespace)
BaselineFailed2 = namespace['Failed2Strategy']
