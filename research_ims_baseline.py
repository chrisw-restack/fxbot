"""Frozen strategy for reproducing the September 18 study after tracking fixes.

Uses the local Git object only; never checks out files or contacts a remote.
"""
from pathlib import Path
import subprocess
from types import ModuleType

REVISION = '4cdc9eb7bc0bcd758d04af9e83f035faaa9bce09'
SOURCE = subprocess.check_output(
    ['git', 'show', REVISION + ':strategies/ims_reversal.py'],
    cwd=Path(__file__).resolve().parent, encoding='utf-8')
_module = ModuleType('ims_reversal_frozen_4cdc9eb')
exec(compile(SOURCE, REVISION + ':strategies/ims_reversal.py', 'exec'), _module.__dict__)
ImsReversalStrategy = _module.ImsReversalStrategy
