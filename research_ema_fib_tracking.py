"""Sequential before/after, broker replay, and fixed-parameter rolling validation.

No parameter search or DEMO changes. Run from the repository root. Historical
test windows were already seen during past development; these are revalidation,
not a new untouched holdout. The period after 14 July 2026 remains excluded.
"""
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
from pathlib import Path
import subprocess
import time

from backtest_engine import BacktestEngine
from data.historical_loader import load_and_merge, bar_close_time, find_csv
from data.histdata_provenance import file_hash, metadata_path, write_json
from research_ema_fib_baseline import EmaFibRetracementStrategy as Baseline, SOURCE, REVISION
from research_ema_fib_review import current_settings, paths_for, metrics, PERIODS
from strategies.ema_fib_retracement import EmaFibRetracementStrategy
import config

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'output/ema_fib_tracking_20260925'
PREVIOUS = ROOT/'output/ema_fib_review_20260923'
SOURCES = ('dukascopy', 'histdata', 'mt5_icmarkets_utc')
CUTOFF = datetime(2026,7,15)
FOLDS = [(datetime(y-4,1,1), datetime(y,1,1), datetime(y+2,1,1)) for y in (2020,2022,2024)]


def run(bars, source, symbol, label, start, end, params, baseline=False, spread=None):
    assert end <= CUTOFF
    selected = [b for b in bars if b.timestamp >= start-timedelta(days=180) and bar_close_time(b) <= end]
    strategy = (Baseline if baseline else EmaFibRetracementStrategy)(**params)
    engine = BacktestEngine(spread_pips=config.BACKTEST_SPREAD_PIPS if spread is None else spread)
    engine.add_strategy(strategy,[symbol])
    began = time.monotonic()
    trades = engine.replay(selected,start_date=start,end_date=end)
    exposure = engine.execution.get_open_positions()
    if not baseline:
        assert set(strategy._orders) == {o['attempt_id'] for o in exposure}, 'Strategy/execution state mismatch'
        assert not strategy._proposals, 'Unresolved proposal at end of replay'
    result = dict(source=source,symbol=symbol,label=label,start=start,end=end,
        metrics=metrics(trades),ending_balance=engine.execution.get_account_balance(),
        max_equity_dd_pct=engine.execution.max_equity_drawdown_pct,open_exposure=exposure,
        seconds=time.monotonic()-began,baseline=baseline,spread=spread,
        bars=dict(Counter(b.timeframe for b in selected)))
    name = f'{source}_{symbol}_{label}'
    write_json(OUT/(name+'.json'),result)
    write_json(OUT/(name+'_trades.json'),trades)
    print(json.dumps(dict(job=name,metrics=result['metrics'],seconds=result['seconds'])),flush=True)
    return result,trades


def main():
    logging.disable(logging.CRITICAL)
    OUT.mkdir(parents=True,exist_ok=True)
    params,symbols = current_settings()
    broker_symbols = [s for s in symbols if all(find_csv(s,tf,data_source='mt5_icmarkets_utc') for tf in ('M5','H1','D1'))]
    paths = {sym:{src:paths_for(src,sym) for src in SOURCES
                  if src != 'mt5_icmarkets_utc' or sym in broker_symbols} for sym in symbols}
    code = ['research_ema_fib_tracking.py','research_ema_fib_baseline.py','research_ema_fib_review.py',
        'strategies/ema_fib_retracement.py','engine.py','backtest_engine.py','execution/simulated_execution.py',
        'execution/mt5_execution.py','risk/risk_manager.py','portfolio/portfolio_manager.py',
        'utils/setup_ledger.py','utils/strategy_state.py','data/historical_loader.py',
        'data/histdata_provenance.py','config.py','live_config.py']
    manifest = dict(created_at_utc=datetime.now(timezone.utc),workers=1,parameters=params,symbols=symbols,
        revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        frozen_revision=REVISION,frozen_sha256=hashlib.sha256(SOURCE.encode()).hexdigest(),
        code_hashes={p:file_hash(ROOT/p) for p in code},
        input_hashes={p:file_hash(p) for sources in paths.values() for files in sources.values() for p in files},
        sidecar_hashes={str(metadata_path(p)):file_hash(metadata_path(p))
            for sources in paths.values() for files in sources.values() for p in files if metadata_path(p).exists()},
        previous_result_hashes={p.name:file_hash(p) for p in PREVIOUS.glob('*_trades.json')},
        periods=PERIODS,folds=FOLDS,cutoff=CUTOFF,broker_symbols=broker_symbols,
        missing_broker_symbols=[s for s in symbols if s not in broker_symbols],
        assumptions=dict(initial_balance=10000,risk_pct=config.RISK_PCT,commission_per_lot=config.COMMISSION_PER_LOT,
            spreads={s:config.BACKTEST_SPREAD_PIPS[s] for s in symbols},swaps=False,news=False,daily_loss_gate=False,
            workers=1,execution='M5',warmup_days=180,aggregate='Independent symbol net-R series, not account equity',
            optimization=False,walk_forward='Four-year training/two-year test, fixed parameters, no fresh holdout'))
    write_json(OUT/'manifest.json',manifest)
    results, grouped, comparisons = [], {}, []
    for symbol in symbols:
        for source in paths[symbol]:
            print(f'Loading {source} {symbol}',flush=True)
            # Historical data starts in Jan 2016; earlier warm-up is unavailable.
            start = datetime(2016,1,1) if source != 'mt5_icmarkets_utc' else datetime(2019,7,1)
            bars = load_and_merge(paths[symbol][source],start=start,end=CUTOFF)
            if source == 'dukascopy' and symbol in ('EURUSD','AUDUSD'):
                _,control = run(bars,source,symbol,'frozen_control',PERIODS[0][1],PERIODS[0][2],params,baseline=True)
                old = json.loads((PREVIOUS/f'{source}_{symbol}_2020_2025_trades.json').read_text())
                assert json.loads(json.dumps(control,default=str)) == old, 'Unchanged-data baseline drift'
            for label,start,end in PERIODS:
                result,trades = run(bars,source,symbol,label,start,end,params)
                results.append(result)
                grouped.setdefault((source,label),[]).extend(trades)
                if symbol in broker_symbols and source != 'mt5_icmarkets_utc':
                    grouped.setdefault((source,'broker_matched_'+label),[]).extend(trades)
                if source != 'mt5_icmarkets_utc':
                    old = json.loads((PREVIOUS/f'{source}_{symbol}_{label}.json').read_text())
                    comparisons.append(dict(source=source,symbol=symbol,period=label,
                        before=old['metrics'],after=result['metrics']))
            if source != 'mt5_icmarkets_utc':
                for start,split,end in FOLDS:
                    for kind,a,b in [('train',start,split),('test',split,end)]:
                        label = f'fold_{split.year}_{kind}'
                        result,trades = run(bars,source,symbol,label,a,b,params)
                        results.append(result)
                        grouped.setdefault((source,label),[]).extend(trades)
                result,trades = run(bars,source,symbol,'spread_1pip',PERIODS[0][1],PERIODS[0][2],params,spread=1.0)
                results.append(result)
                grouped.setdefault((source,'spread_1pip'),[]).extend(trades)
            write_json(OUT/'results.json',results)
            write_json(OUT/'comparison.json',comparisons)
            write_json(OUT/'aggregate.json',[dict(source=s,label=l,metrics=metrics(t)) for (s,l),t in grouped.items()])
            del bars
    folds = []
    for source in ('dukascopy','histdata'):
        for _,split,_ in FOLDS:
            train = metrics(grouped[(source,f'fold_{split.year}_train')])
            test = metrics(grouped[(source,f'fold_{split.year}_test')])
            retention = test['expectancy']/train['expectancy'] if train['expectancy'] > 0 else None
            verdict = ('FAIL' if test['total_r'] <= 0 else 'UNDEFINED' if retention is None
                       else 'STRONG' if retention >= .7 else 'MODERATE' if retention >= .4 else 'WEAK')
            folds.append(dict(source=source,test_start=split,train=train,test=test,retention=retention,verdict=verdict))
    write_json(OUT/'folds.json',folds)
    # Catch accidental changes during a long run before treating it as reproducible.
    assert all(file_hash(ROOT/p)==sha for p,sha in manifest['code_hashes'].items()), 'Code changed during research'
    write_json(OUT/'complete.json',dict(results=len(results),baseline_controls=2,code_hashes_match=True))
    print('Completed corrected comparisons, spread stress, broker replay, and rolling validation.',flush=True)


if __name__ == '__main__':
    main()
