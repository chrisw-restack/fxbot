"""Fixed DEMO Candle Confirmation USDJPY audit; sequential CSV replay, no MT5.

Fresh-cross is a separate research hypothesis, never a production change.
"""
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
from analyze_icmarkets_replay import MemoryJournal
from backtest_engine import BacktestEngine
from data.historical_loader import find_csv, load_and_merge, bar_close_time
from data.histdata_provenance import file_hash, metadata_path, write_json
from live_config import create_live_strategy_specs
from research_ema_fib_review import metrics
from strategies.candle_confirmation import CandleConfirmationStrategy

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'output/candle_usdjpy_review_20260930'
START, END = datetime(2016, 7, 1), datetime(2026, 7, 15)
SOURCES = ('dukascopy', 'histdata', 'mt5_icmarkets_utc')


def settings():
    s = next(s for s, _ in create_live_strategy_specs()
             if s.NAME == 'CandleConfirmation_USDJPY_H1_M5')
    aliases = dict(pip_sizes='_pip_sizes', blocked_hours='_blocked', name='NAME')
    p = {k: getattr(s, aliases.get(k, k))
         for k in inspect.signature(CandleConfirmationStrategy).parameters}
    p['blocked_hours'] = sorted(p['blocked_hours'])
    return p


def paths_for(source):
    paths = []
    for tf in ('M5', 'H1', 'D1'):
        found = find_csv('USDJPY', tf, data_source=source)
        assert found, (source, tf)
        assert len(found) == 1, (source, tf, found)
        paths.extend(found)
    return paths


class ObservedCandle(CandleConfirmationStrategy):
    """Observe current behavior, or apply one explicit fresh-cross hypothesis."""
    def __init__(self, fresh_cross=False, **params):
        super().__init__(**params)
        self.fresh_cross = fresh_cross
        self.active = False
        self.audit = Counter()
        self.examples = {}
        self.origins = {}
        self.last_proposal = None
        self.accepted = {}

    def note(self, key, **details):
        if self.active:
            self.audit[key] += 1
            if len(self.examples.setdefault(key, [])) < 5:
                self.examples[key].append(deepcopy(details))

    def _set_bias(self, symbol, direction, bar):
        super()._set_bias(symbol, direction, bar)
        if self._bias[symbol] is not None:
            self.origins[symbol] = dict(time=bar.timestamp, close_time=bar_close_time(bar), direction=direction)
            self.note('biases', **self.origins[symbol])

    def _expire_bias(self, symbol):
        self.note('bias_expired', origin=self.origins.get(symbol))
        super()._expire_bias(symbol)

    def _detect_bullish_mss(self, symbol, bar, bias, bars):
        return self._observe(super()._detect_bullish_mss(symbol, bar, bias, bars), symbol, bar, bias, bars)

    def _detect_bearish_mss(self, symbol, bar, bias, bars):
        return self._observe(super()._detect_bearish_mss(symbol, bar, bias, bars), symbol, bar, bias, bars)

    def _observe(self, signal, symbol, bar, bias, bars):
        if signal is None:
            return None
        buy = signal.direction == 'BUY'
        idxs = (self._swing_high_idxs if buy else self._swing_low_idxs)(
            bars, self.fractal_n, len(bars) - self.fractal_n - 1)
        pivot = max(i for i in idxs if bar.close > bars[i].high) if buy else max(
            i for i in idxs if bar.close < bars[i].low)
        level = bars[pivot].high if buy else bars[pivot].low
        crossed = bars[-2].close <= level if buy else bars[-2].close >= level
        opposite_breached = any(b.low <= bias['engulf_low'] if buy else b.high >= bias['engulf_high'] for b in bars)
        # Only the completed right wing may confirm a swing; no future candles.
        assert pivot + self.fractal_n < len(bars) - 1
        origin = self.origins[symbol]
        assert all(b.timestamp >= origin['close_time'] for b in bars)
        info = dict(origin=deepcopy(origin), signal_time=bar.timestamp, pivot_time=bars[pivot].timestamp,
                    level=level, previous_close=bars[-2].close, fresh_cross=crossed,
                    opposite_engulf_extreme_breached=opposite_breached,
                    trend_still_allows=self._trend_allows(symbol, signal.direction))
        self.note('detected_signals', **info)
        if self.fresh_cross and not crossed:
            self._signal_fired[symbol] = False
            self.note('hypothesis_filtered_stale_break', **info)
            return None
        self.last_proposal = info
        self.note('signals', **info)
        for key in ('fresh_cross', 'opposite_engulf_extreme_breached', 'trend_still_allows'):
            self.note('signal_' + key + '_' + str(info[key]).lower(), **info)
        return signal

    def notify_order_accepted(self, signal, ticket, details=None):
        self.accepted[ticket] = deepcopy(self.last_proposal)
        self.note('accepted_orders', ticket=ticket, context=self.last_proposal)

    def notify_trade_closed(self, trade):
        # Match EventEngine's production fallback exactly, including BE behavior.
        origin = self.accepted.pop(trade['ticket'], None)
        current = self.origins.get(trade['symbol'])
        if origin and origin['origin'] != current:
            self.note('close_updates_other_origin', trade=trade, accepted=origin, current=current)
        if trade['result'] == 'WIN':
            super().notify_win(trade['symbol'])
        elif trade['result'] == 'LOSS':
            super().notify_loss(trade['symbol'])


def replay(bars, params, variant='current', spread=.2, observed=True):
    strategy = (ObservedCandle(fresh_cross=variant == 'fresh_cross', **params)
                if observed else CandleConfirmationStrategy(**params))
    engine = BacktestEngine(spread_pips=spread)
    engine.add_strategy(strategy, ['USDJPY'])
    journal = MemoryJournal()
    engine.event_engine.trade_journal = journal
    engine.execution.configure_timeframes(bars)
    for bar in bars:
        if bar_close_time(bar) <= START:
            engine.event_engine.warmup_bar(bar)
        else:
            if observed:
                strategy.active = True
            engine.process_bar(bar)
    ts = engine.execution.get_closed_trades()
    windows = {'full': (START, END), '2020_2025': (datetime(2020, 1, 1), datetime(2026, 1, 1)),
               '2026_to_july14': (datetime(2026, 1, 1), END)}
    windows.update({str(y): (datetime(y, 1, 1), min(datetime(y + 1, 1, 1), END)) for y in range(2017, 2027)})
    for year in (2020, 2022, 2024):
        windows[f'fold_{year}_train'] = (datetime(year - 4, 7, 1), datetime(year, 7, 1))
        windows[f'fold_{year}_test'] = (datetime(year, 7, 1), datetime(year + 2, 7, 1))
    def subset(a, b):
        return [t for t in ts if a <= t['open_time'] and t['close_time'] < b]
    result = dict(metrics=metrics(ts), windows={k: metrics(subset(a,b)) for k,(a,b) in windows.items()},
                  gross_metrics=metrics([dict(t, net_r=t['gross_r']) for t in ts]),
                  directions={d: metrics([t for t in ts if t['direction'] == d]) for d in ('BUY','SELL')},
                  final_exposure=engine.execution.get_open_positions(),
                  ending_balance=engine.execution.get_account_balance(),
                  max_equity_drawdown_pct=engine.execution.max_equity_drawdown_pct,
                  commission_r=sum(t['gross_r'] - t['net_r'] for t in ts),
                  audit=dict(getattr(strategy, 'audit', {})), examples=getattr(strategy, 'examples', {}),
                  rejection_reasons=dict(Counter(r['reason'] for r in journal.rows if r['event'] == 'REJECTED')),
                  journal_events=dict(Counter(r['event'] for r in journal.rows)),
                  actual_rr_range=[min((abs(t['tp']-t['entry_price']) / abs(t['entry_price']-t['sl']) for t in ts), default=None),
                                   max((abs(t['tp']-t['entry_price']) / abs(t['entry_price']-t['sl']) for t in ts), default=None)])
    return result, ts


def main():
    logging.disable(logging.CRITICAL)
    OUT.mkdir(parents=True, exist_ok=True)
    params = settings()
    files = {src: paths_for(src) for src in SOURCES}
    code = ['research_candle_usdjpy_review.py', 'strategies/candle_confirmation.py', 'engine.py',
            'backtest_engine.py', 'execution/simulated_execution.py', 'risk/risk_manager.py', 'risk/validation.py',
            'portfolio/portfolio_manager.py', 'data/historical_loader.py', 'data/histdata_provenance.py',
            'live_config.py', 'config.py']
    manifest = dict(created_utc=datetime.now(timezone.utc), parameters=params, workers=1,
        revision=subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip(),
        code_hashes={p:file_hash(ROOT/p) for p in code},
        input_hashes={p:file_hash(p) for paths in files.values() for p in paths},
        metadata_hashes={str(metadata_path(p)):file_hash(metadata_path(p)) for paths in files.values()
                        for p in paths if metadata_path(p).exists()},
        assumptions=dict(start=START, end_exclusive=END, warmup_days=180, spread_pips=.2,
            commission_per_lot=7., planned_risk_pct=config.RISK_PCT, initial_balance=10000,
            swaps=False, variable_spread=False, extra_slippage=False, news=False,
            shared_portfolio=False, daily_loss_gate=False, optimization=False),
        note='Current DEMO parameters. Chronological fixed-parameter diagnostics on reused historical data, not untouched OOS.')
    assert not (OUT/'manifest.json').exists(), 'Use a new output directory for another run.'
    write_json(OUT/'manifest.json', manifest)
    controls, results = [], []
    for src, paths in files.items():
        print('Loading ' + src, flush=True)
        bars = load_and_merge(paths, start=START-timedelta(days=180), end=END)
        write_json(OUT/(src+'_coverage.json'), {tf:dict(count=sum(b.timeframe==tf for b in bars),
            first=min(b.timestamp for b in bars if b.timeframe==tf),
            last=max(b.timestamp for b in bars if b.timeframe==tf)) for tf in ('M5','H1','D1')})
        jobs = [('current', .2), ('fresh_cross', .2)]
        if src == 'mt5_icmarkets_utc':
            jobs += [('current', 1.), ('current', 2.)]
        for variant, spread in jobs:
            began = time.monotonic()
            result, ts = replay(bars, params, variant, spread)
            result.update(source=src, variant=variant, spread_pips=spread, seconds=time.monotonic()-began)
            name = f'{src}_{variant}_spread{spread:g}'
            write_json(OUT/(name+'.json'), result)
            write_json(OUT/(name+'_trades.json'), ts)
            results.append(result)
            write_json(OUT/'results.json', results)
            print(json.dumps(dict(job=name, metrics=result['metrics'], seconds=result['seconds'])), flush=True)
            if variant == 'current' and spread == .2:
                plain, plain_ts = replay(bars, params, observed=False)
                assert plain_ts == ts and plain['final_exposure'] == result['final_exposure'], 'Observer altered production behavior.'
                controls.append(dict(source=src, every_trade_field_matches=True, ending_exposure_matches=True))
                write_json(OUT/'controls.json', controls)
                print('Exact production control passed ' + src, flush=True)
        del bars
    assert all(file_hash(ROOT/p) == h for p,h in manifest['code_hashes'].items())
    assert all(file_hash(p) == h for p,h in manifest['input_hashes'].items())
    assert all(file_hash(p) == h for p,h in manifest['metadata_hashes'].items())
    write_json(OUT/'complete.json', dict(replays=len(results), controls=len(controls), hashes_match=True))
    print('Candle USDJPY review complete.', flush=True)


if __name__ == '__main__':
    main()
