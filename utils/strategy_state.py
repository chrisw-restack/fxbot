"""Atomic JSON checkpoints for trusted strategy data, without executable pickles."""
import hashlib
import inspect
import json
import os
from collections import deque
from dataclasses import asdict
from datetime import datetime, date, time
from pathlib import Path
from zoneinfo import ZoneInfo

from models import BarEvent


def encode(value):
    if isinstance(value, BarEvent):
        return {'type': 'bar', 'value': encode(asdict(value))}
    if isinstance(value, (datetime, date, time)):
        return {'type': type(value).__name__, 'value': value.isoformat()}
    if isinstance(value, ZoneInfo):
        return {'type': 'zone', 'value': value.key}
    if isinstance(value, dict):
        return {'type': 'dict', 'value': [[encode(k), encode(v)] for k, v in value.items()]}
    if isinstance(value, (deque, tuple, set, frozenset)):
        result = {'type': type(value).__name__, 'value': [encode(v) for v in value]}
        if isinstance(value, (set, frozenset)):
            result['value'].sort(key=lambda v: json.dumps(v, sort_keys=True))
        if isinstance(value, deque):
            result['maxlen'] = value.maxlen
        return result
    if isinstance(value, list):
        return [encode(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f'Unsupported checkpoint type: {type(value).__name__}')


def decode(value):
    if isinstance(value, list):
        return [decode(v) for v in value]
    if not isinstance(value, dict):
        return value
    kind, payload = value['type'], value['value']
    if kind == 'dict':
        return {decode(k): decode(v) for k, v in payload}
    if kind == 'bar':
        return BarEvent(**decode(payload))
    if kind in ('datetime', 'Timestamp'):
        return datetime.fromisoformat(payload)
    if kind == 'date':
        return date.fromisoformat(payload)
    if kind == 'time':
        return time.fromisoformat(payload)
    if kind == 'zone':
        return ZoneInfo(payload)
    if kind == 'deque':
        return deque((decode(v) for v in payload), maxlen=value['maxlen'])
    if kind == 'tuple':
        return tuple(decode(v) for v in payload)
    if kind in ('set', 'frozenset'):
        constructor = set if kind == 'set' else frozenset
        return constructor(decode(v) for v in payload)
    raise ValueError(f'Unknown checkpoint type: {kind}')


class StrategyCheckpoint:
    def __init__(self, path, specs, account):
        self.path = Path(path)
        self.strategies = {strategy.NAME: strategy for strategy, _ in specs}
        # Hash initial constructor state and code. Changed code/config cannot
        # silently inherit incompatible historical state.
        payload = encode([account, [(s.NAME, symbols, s.__dict__) for s, symbols in specs]])
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode())
        root = Path(__file__).resolve().parents[1]
        sources = {Path(inspect.getfile(type(s))) for s in self.strategies.values()}
        sources.update(root / name for name in ('config.py', 'live_config.py', 'engine.py', 'models.py',
                                                'risk/risk_manager.py', 'risk/validation.py',
                                                'execution/mt5_execution.py', 'data/mt5_data.py',
                                                'portfolio/portfolio_manager.py',
                                                'utils/live_reconciliation.py',
                                                'main_live.py', 'utils/strategy_state.py'))
        for source in sorted(sources):
            digest.update(source.read_bytes())
        self.fingerprint = digest.hexdigest()

    def load(self):
        if not self.path.exists():
            return None
        payload = json.loads(self.path.read_text(encoding='utf-8'))
        if payload.get('fingerprint') != self.fingerprint:
            return None
        states = decode(payload['states'])
        last_bar_time = decode(payload['last_bar_time'])
        if set(states) != set(self.strategies):
            raise ValueError('Checkpoint strategy names do not match')
        for name, state in states.items():
            if set(state) != set(self.strategies[name].__dict__):
                raise ValueError(f'Checkpoint state fields do not match: {name}')
        for name, state in states.items():
            self.strategies[name].__dict__.update(state)
        return last_bar_time

    def save(self, last_bar_time):
        payload = {'fingerprint': self.fingerprint,
                   'states': encode({name: s.__dict__ for name, s in self.strategies.items()}),
                   'last_bar_time': encode(last_bar_time)}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        with temporary.open('w', encoding='utf-8') as stream:
            json.dump(payload, stream, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)
