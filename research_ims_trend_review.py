"""Fixed DEMO IMS audit. Sequential local CSV replay, no MT5 or parameter changes."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import inspect
import json
import logging
from pathlib import Path
import subprocess
import time

import config
from live_config import create_live_strategy_specs
from strategies.ims import ImsStrategy as CurrentImsStrategy
from research_ims_trend_baseline import ImsStrategy, REVISION, SOURCE_SHA256
from backtest_engine import BacktestEngine
from data.historical_loader import find_csv, load_and_merge
from data.histdata_provenance import file_hash, metadata_path, write_json
from research_ema_fib_review import metrics
from analyze_icmarkets_replay import MemoryJournal

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'output/ims_trend_review_20260929'
START, END = datetime(2020, 1, 1), datetime(2026, 7, 15)


def settings():
    strategy, symbols = next((s, syms) for s, syms in create_live_strategy_specs()
                             if type(s) is CurrentImsStrategy)
    params = {k: getattr(strategy, '_pip_sizes' if k == 'pip_sizes' else k)
              for k in inspect.signature(ImsStrategy).parameters}
    params['blocked_hours'] = sorted(params['blocked_hours'])
    return params, symbols


def paths_for(source, symbol):
    paths = []
    for tf in ('M5', 'M15', 'H4'):
        found = find_csv(symbol, tf, data_source=source)
        if not found:
            raise ValueError(f'Missing {source} {symbol} {tf}')
        # Prefer the recent full export over overlapping earlier broker exports.
        if source == 'mt5_icmarkets_utc':
            found = [max(found, key=lambda p: Path(p).name.rsplit('-', 1)[-1])]
        paths.extend(found)
    conversion = {'EURAUD': 'AUDUSD', 'CADJPY': 'USDJPY', 'GBPCAD': 'USDCAD'}.get(symbol)
    if conversion:
        found = find_csv(conversion, 'M5', data_source=source)
        if not found:
            raise ValueError(f'Missing conversion {source} {conversion} M5')
        paths.extend(found)
    return paths


class ObservedIms(ImsStrategy):
    """Observe decisions; callbacks delegate to the same production behavior."""
    def __init__(self, **params):
        super().__init__(**params)
        self.audit = Counter()
        self.examples = {}
        self.retired = set()
        self.accepted = {}
        self.execution = None

    def identity(self, symbol):
        b = self._htf_bias.get(symbol)
        return (symbol, b['direction'], b['_swing_ts']) if b else None

    def note(self, key, **details):
        self.audit[key] += 1
        if len(self.examples.setdefault(key, [])) < 3:
            self.examples[key].append(deepcopy(details))

    def _expire_bias(self, symbol, bar):
        identity = self.identity(symbol)
        if identity:
            self.retired.add(identity)
        return super()._expire_bias(symbol, bar)

    def generate_signal(self, event):
        before = self.identity(event.symbol)
        signal = super().generate_signal(event)
        after = self.identity(event.symbol)
        if after and after != before and after in self.retired:
            self.note('expired_origin_reactivated', time=event.timestamp, identity=after)
        if signal and signal.direction != 'CANCEL':
            self.audit['proposals_including_warmup'] += 1
            if self.execution and any(p['symbol'] == event.symbol for p in self.execution.get_open_positions()):
                self.note('proposal_while_slot_occupied', time=event.timestamp, identity=after)
            if after in self.retired:
                self.note('proposal_from_previously_expired_origin', time=event.timestamp, identity=after)
        return signal

    def notify_order_accepted(self, signal, ticket, details=None):
        self.accepted[ticket] = self.identity(signal.symbol)
        self.audit['accepted_orders'] += 1

    def notify_order_cancelled(self, order):
        self.accepted.pop(order['ticket'], None)
        self.audit['confirmed_cancellations'] += 1

    def notify_trade_closed(self, trade):
        symbol = trade['symbol']
        origin = self.accepted.pop(trade['ticket'], None)
        current = self.identity(symbol)
        if origin and current and origin != current:
            self.note('close_updates_different_current_origin', ticket=trade['ticket'],
                      time=trade['close_time'], result=trade['result'], accepted=origin, current=current)
        if trade['result'] == 'WIN':
            super().notify_win(symbol)
        elif trade['result'] == 'LOSS':
            super().notify_loss(symbol)


def replay(bars, params, symbol, start, observed=True, spread=None):
    strategy = (ObservedIms if observed else ImsStrategy)(**params)
    engine = BacktestEngine(rr_ratio=params['rr_ratio'],
        spread_pips=config.BACKTEST_SPREAD_PIPS if spread is None else spread)
    if observed:
        strategy.execution = engine.execution
    journal = MemoryJournal()
    engine.event_engine.trade_journal = journal
    engine.add_strategy(strategy, [symbol])
    trades = engine.replay(bars, start_date=start, end_date=END)
    return trades, engine, strategy, journal


def main():
    logging.disable(logging.CRITICAL)
    OUT.mkdir(parents=True, exist_ok=True)
    params, symbols = settings()
    jobs, missing = [], []
    for source in ('dukascopy', 'histdata', 'mt5_icmarkets_utc'):
        for symbol in symbols:
            try:
                jobs.append((source, symbol, paths_for(source, symbol)))
            except ValueError as exc:
                missing.append(str(exc))
    files = sorted({p for _, _, paths in jobs for p in paths})
    code = ['research_ims_trend_review.py', 'research_ims_trend_baseline.py', 'engine.py', 'backtest_engine.py',
            'execution/simulated_execution.py', 'risk/risk_manager.py', 'live_config.py', 'config.py',
            'data/historical_loader.py', 'portfolio/portfolio_manager.py']
    manifest = dict(created_at=datetime.now(timezone.utc), revision=subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], text=True).strip(), parameters=params, symbols=symbols,
        start=START, end_exclusive=END, workers=1, missing=missing,
        frozen_strategy_revision=REVISION, frozen_strategy_sha256=SOURCE_SHA256,
        code_hashes={p: file_hash(ROOT/p) for p in code},
        input_hashes={p: file_hash(p) for p in files},
        sidecar_hashes={str(metadata_path(p)): file_hash(metadata_path(p)) for p in files if 'histdata' in p},
        assumptions=dict(rr=2.5, risk_pct=config.RISK_PCT, spread=config.BACKTEST_SPREAD_PIPS,
            commission_per_lot=config.COMMISSION_PER_LOT, swaps=False, daily_loss_gate=False,
            independent_symbol_accounts=True, execution_timeframe='M5',
            conversion='Auxiliary same-source M5 USD quotes for crosses; no conversion proxies',
            broker_usdcad_start='2025-04-01, allowing three months available warmup'))
    if (OUT/'manifest.json').exists():
        previous = json.loads((OUT/'manifest.json').read_text())
        for field in ('parameters', 'input_hashes', 'sidecar_hashes'):
            assert previous[field] == manifest[field], f'Baseline inputs changed: {field}; use a new output directory'
        # Keep the actual original run provenance, rather than relabel cached results.
    else:
        write_json(OUT/'manifest.json', manifest)
    for source, symbol, paths in jobs:
        name = f'{source}_{symbol}'
        path = OUT/f'{name}.json'
        if path.exists():
            print('Existing', name, flush=True)
            continue
        started = time.monotonic()
        start = datetime(2025, 4, 1) if source == 'mt5_icmarkets_utc' and symbol == 'USDCAD' else START
        print('Loading', name, flush=True)
        bars = load_and_merge(paths, start=start-timedelta(days=180), end=END)
        trades, engine, strategy, journal = replay(bars, params, symbol, start)
        control = None
        if symbol == 'EURUSD' and source == 'dukascopy':
            plain, plain_engine, _, _ = replay(bars, params, symbol, start, observed=False)
            assert plain == trades, 'Observer changed trades'
            assert plain_engine.execution.get_open_positions() == engine.execution.get_open_positions()
            control = 'Every closed trade and final exposure match uninstrumented production strategy'
        windows = {'2020_2025': (START, datetime(2026,1,1)),
                   '2026_to_july14': (datetime(2026,1,1), END),
                   'common_2025apr_to_july2026': (datetime(2025,4,1), END)}
        windows.update({str(y): (datetime(y,1,1), min(datetime(y+1,1,1), END)) for y in range(2020,2027)})
        result = dict(source=source, symbol=symbol, start=start, end=END, bars=len(bars),
            metrics=metrics(trades), windows={k: metrics([t for t in trades if a <= t['close_time'] < b])
                for k,(a,b) in windows.items() if a >= start},
            audit=dict(strategy.audit), examples=strategy.examples, control=control,
            journal_events=dict(Counter(r['event'] for r in journal.rows)),
            rejection_reasons=dict(Counter(r['reason'] for r in journal.rows if r['event']=='REJECTED')),
            final_exposure=engine.execution.get_open_positions(), seconds=time.monotonic()-started)
        write_json(OUT/f'{name}_trades.json', trades)
        write_json(path, result)
        print(name, result['metrics'], 'seconds', round(result['seconds']), flush=True)
        del bars, engine, strategy, journal


if __name__ == '__main__':
    main()
