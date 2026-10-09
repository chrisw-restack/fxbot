"""Frozen EURUSD IMS Reversal comparison on audited XM replay intervals.

One worker, no MT5 connection, no tuning, and no bars after 14 July 2026.
All sources use the same segment starts, warmups, and cost scenarios.
"""
from collections import Counter
from datetime import datetime, timedelta, timezone
import inspect
import json
import logging
from pathlib import Path
import time

import config
from backtest_engine import BacktestEngine
from data.historical_loader import load_and_merge, bar_close_time, find_csv
from data.histdata_provenance import file_hash
from live_config import create_live_strategy_specs
from research_ims_reversal import metrics
from strategies.ims_reversal import ImsReversalStrategy
from utils.warmup import warmup_counts

ROOT = Path(__file__).resolve().parent
XM = ROOT/'output/xm_processed_20261001/history'
OUT = ROOT/'output/ims_reversal_xm_20261002'
TFS = ('M5', 'M15', 'H4')
START, HISTORY_END, CUTOFF = datetime(2020, 1, 1), datetime(2026, 1, 1), datetime(2026, 7, 15)
WARMUP = timedelta(days=180)
COSTS = {
    'raw_costs': dict(spread_pips=.1, commission_per_lot=7.),
    'xm_costs': dict(spread_pips=1.1, commission_per_lot=0.),
    'xm_wider': dict(spread_pips=1.6, commission_per_lot=0.),
}


def write(path, value):
    path.write_text(json.dumps(value, indent=2, default=str, allow_nan=False), encoding='utf-8')


def frozen_strategy():
    return next(s for s, symbols in create_live_strategy_specs()
                if isinstance(s, ImsReversalStrategy) and symbols == ['EURUSD'])


def intersect(left, right):
    return sorted({(max(a, c), min(b, d)) for a, b in left for c, d in right
                   if max(a, c) < min(b, d)})


def xm_intervals(files):
    shared = [(datetime.min, CUTOFF)]
    for path in files:
        meta = json.loads(Path(str(path)+'.meta.json').read_text())
        own = [(datetime.fromisoformat(i['start']), datetime.fromisoformat(i['end']))
               for i in meta['replay_intervals']]
        shared = intersect(shared, own)
    return shared


def segments_for(intervals, start, end):
    segments, skipped = [], []
    for left, right in intervals:
        right = min(right, end)
        if right <= start:
            continue
        trading = max(start, left+WARMUP)
        if trading >= right:
            skipped.append(dict(interval_start=left, interval_end=right,
                                reason='Insufficient interval length for 180-day warmup'))
            continue
        segments.append(dict(load_start=trading-WARMUP, trade_start=trading, end=right))
    return segments, skipped


def inputs():
    result = {'xm': [next(XM.glob(f'EURUSD_{tf}_*.csv')) for tf in TFS]}
    for source in ('dukascopy', 'histdata', 'mt5_icmarkets_utc'):
        result[source] = []
        for tf in TFS:
            paths = [Path(p) for p in find_csv('EURUSD', tf, data_source=source)]
            if not paths:
                raise ValueError(f'Missing {source} EURUSD {tf}')
            # A single latest complete snapshot, without mixing overlapping exports.
            result[source].append(max(paths, key=lambda p: p.stat().st_mtime_ns))
    return result


def replay(bars, segment, cost):
    strategy = frozen_strategy()
    engine = BacktestEngine(initial_balance=10000, rr_ratio=strategy.rr_ratio,
                           spread_pips=cost['spread_pips'])
    # Local simulator scenario only; the production config is never mutated.
    engine.execution._commission_per_lot = cost['commission_per_lot']
    engine.add_strategy(strategy, ['EURUSD'])
    start, end = segment['trade_start'], segment['end']
    assert end <= CUTOFF
    warm_counts = Counter(b.timeframe for b in bars if bar_close_time(b) <= start)
    required = warmup_counts([(strategy, ['EURUSD'])])
    assert all(warm_counts[tf] >= n for (_, tf), n in required.items()), warm_counts
    began = time.monotonic()
    trades = engine.replay(bars, start_date=start, end_date=end)
    assert all(start <= t['open_time'] <= t['close_time'] <= end for t in trades)
    assert all(abs(t['commission']-round(t['lot_size']*cost['commission_per_lot'], 2)) < .011
               for t in trades)
    assert all(t.get('setup_id') and t.get('attempt_id') for t in trades)
    exposure = engine.execution.get_open_positions()
    return dict(segment=segment, cost=cost, metrics=metrics(trades), trades=trades,
                ending_exposure=exposure, filled_open=len(engine.execution._positions),
                pending_open=len(engine.execution._pending),
                ending_balance=engine.execution.get_account_balance(),
                ending_equity=engine.execution.get_equity(),
                max_equity_dd_pct=engine.execution.max_equity_drawdown_pct,
                warmup_bars=dict(warm_counts), replay_bars=dict(Counter(b.timeframe for b in bars)),
                h4_opening_hours=dict(Counter(b.timestamp.hour for b in bars if b.timeframe == 'H4')),
                setup_attempts=list(strategy._setup_attempts.values()),
                seconds=time.monotonic()-began)


def aggregate(runs):
    trades = [t for r in runs for t in r['trades']]
    result = metrics(trades)
    # Do not silently join independent account histories across exclusions.
    result['concatenated_closed_r_dd_diagnostic'] = result.pop('max_dd_r')
    result['concatenated_win_streak_diagnostic'] = result.pop('max_win_streak')
    result['concatenated_loss_streak_diagnostic'] = result.pop('max_loss_streak')
    result['max_segment_dd_r'] = max((r['metrics']['max_dd_r'] for r in runs), default=0.)
    result['max_win_streak'] = max((r['metrics']['max_win_streak'] for r in runs), default=0)
    result['max_loss_streak'] = max((r['metrics']['max_loss_streak'] for r in runs), default=0)
    result['max_segment_equity_dd_pct'] = max((r['max_equity_dd_pct'] for r in runs), default=0.)
    result['ending_filled_positions_across_segments'] = sum(r['filled_open'] for r in runs)
    result['ending_pending_orders_across_segments'] = sum(r['pending_open'] for r in runs)
    result['segment_count'] = len(runs)
    top = sorted((t['net_r'] for t in trades), reverse=True)[:3]
    result['largest_three_trade_r'] = sum(top)
    result['net_r_without_largest_three'] = result['total_r']-sum(top)
    result['yearly'] = {str(y): metrics([t for t in trades if t['close_time'].year == y])
                        for y in sorted({t['close_time'].year for t in trades})}
    return result


def main():
    logging.disable(logging.CRITICAL)
    OUT.mkdir(parents=True, exist_ok=True)
    sources = inputs()
    shared = xm_intervals(sources['xm'])
    historical, skipped = segments_for(shared, START, HISTORY_END)
    recent, recent_skipped = segments_for(shared, HISTORY_END, CUTOFF)
    jobs = {'2020_2025': historical, '2026_viewed': recent}
    assert config.RISK_PCT == .005 and historical and recent
    strategy = frozen_strategy()
    params = {k: getattr(strategy, '_pip_sizes' if k == 'pip_sizes' else k)
              for k in inspect.signature(ImsReversalStrategy).parameters}
    code = ['research_ims_reversal_xm.py', 'strategies/ims_reversal.py', 'strategies/ims_setup_tracking.py',
            'live_config.py', 'config.py', 'backtest_engine.py', 'engine.py', 'risk/risk_manager.py',
            'risk/validation.py', 'execution/simulated_execution.py', 'portfolio/portfolio_manager.py',
            'data/historical_loader.py', 'data/xm_provenance.py', 'research_ims_reversal.py']
    manifest = dict(created_at_utc=datetime.now(timezone.utc), symbol='EURUSD', parameters=params,
        workers=1, cutoff=CUTOFF, costs=COSTS, segments=jobs, skipped=skipped+recent_skipped,
        shared_xm_intervals=shared,
        inputs={source: [dict(path=str(p), sha256=file_hash(p),
                     metadata_sha256=file_hash(str(p)+'.meta.json') if Path(str(p)+'.meta.json').exists() else None)
                     for p in paths] for source, paths in sources.items()},
        code_hashes={p:file_hash(ROOT/p) for p in code},
        xm_audit_hash=file_hash(XM.parent/'audit.json'),
        assumptions=dict(risk_pct=config.RISK_PCT, initial_balance=10000, warmup_days=180,
            daily_loss_gate=False, standalone_strategy=True, swaps=False, variable_spread=False,
            slippage=False, force_close=False, execution_timeframe='M5',
            notes='Independent accounts/state per segment; 2026 is a previously viewed stress period.'))
    write(OUT/'manifest.json', manifest)
    all_runs, summaries = [], []
    total = sum(len(s) for s in jobs.values())*9
    index = 0
    for source, files in sources.items():
        for period, segments in jobs.items():
            grouped = {cost:[] for cost in COSTS if source == 'xm' or cost != 'xm_wider'}
            for segment_id, segment in enumerate(segments, 1):
                print(f'Loading {source} {period} segment {segment_id}: {segment}', flush=True)
                bars = load_and_merge([str(p) for p in files], start=segment['load_start'], end=segment['end'])
                bars = [b for b in bars if bar_close_time(b) <= segment['end']]
                for cost_id in grouped:
                    index += 1
                    print(f'Replay {index}/{total}: {source} {period} {segment_id} {cost_id}', flush=True)
                    result = replay(bars, segment, COSTS[cost_id])
                    result.update(source=source, period=period, segment_id=segment_id, cost_id=cost_id)
                    name = f'{source}_{period}_segment{segment_id}_{cost_id}'
                    write(OUT/(name+'.json'), result)
                    grouped[cost_id].append(result)
                    all_runs.append(result)
                    print(json.dumps(dict(source=source, cost=cost_id, metrics=result['metrics']), default=str), flush=True)
                del bars
            for cost_id, runs in grouped.items():
                summaries.append(dict(source=source, period=period, cost_id=cost_id, metrics=aggregate(runs)))
            write(OUT/'summary.json', summaries)
    write(OUT/'verification.json', dict(completed=True, runs=len(all_runs), expected_runs=total,
        parameter_search=False, protected_cutoff_passed=True, trade_dates_passed=True,
        warmup_counts_passed=True, commissions_passed=True, all_closes_have_originating_setup=True,
        input_hashes_unchanged=all(file_hash(i['path']) == i['sha256']
            for items in manifest['inputs'].values() for i in items)))
    assert len(all_runs) == total
    print('Completed frozen comparison; see summary.json and per-segment results.', flush=True)


if __name__ == '__main__':
    main()
