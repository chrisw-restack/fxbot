"""Fixed-parameter, sequential EURUSD setup-policy comparison; no MT5 calls.

All variants/periods are specified before replay. These historical comparisons
are retrospective diagnostics, not a new untouched out-of-sample evaluation.
The forward-demo period starting 2026-07-15 is excluded, including crossing bars.
"""
from datetime import datetime, timedelta
import hashlib
import json
import logging
from pathlib import Path
import time
import sys

import config
from backtest_engine import BacktestEngine
from data.historical_loader import load_and_merge, bar_close_time
from research_ims_baseline import ImsReversalStrategy as LegacyIMS, SOURCE, REVISION
from research_ims_reversal import BASE, CUTOFF, metrics
from strategies.ims_reversal import ImsReversalStrategy

OUT = Path('output/ims_setup_tracking_20260919')
POLICIES = {'legacy': {}, **{
    hours + '_' + target: dict(pending_cancel_hours=hours, pending_target_reference=target)
    for hours in ('entry', 'all') for target in ('moving', 'submitted')}}


def main():
    verify_only = '--verify-final' in sys.argv
    OUT.mkdir(parents=True, exist_ok=True)
    files = [Path('data/historical/mt5_icmarkets_utc') / f'EURUSD_{tf}_20160103-20260918.csv'
             for tf in ('M5', 'M15', 'H4')]
    source_files = ['engine.py', 'backtest_engine.py', 'models.py', 'risk/risk_manager.py',
                    'strategies/ims_reversal.py', 'strategies/ims_setup_tracking.py',
                    'execution/simulated_execution.py', 'research_ims_setup_policies.py']
    manifest = dict(cutoff=CUTOFF, legacy_revision=REVISION,
        legacy_sha256=hashlib.sha256(SOURCE.encode()).hexdigest(), parameters=BASE,
        policies=POLICIES, workers=1, selection='Retrospective; no automated demo selection',
        execution=dict(risk_pct=config.RISK_PCT, spread=config.BACKTEST_SPREAD_PIPS,
                       commission=config.COMMISSION_PER_LOT, swaps=False, daily_loss_gate=False),
        hashes={str(p): hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in [*files, *source_files]})
    (OUT/('verification_manifest.json' if verify_only else 'manifest.json')).write_text(json.dumps(manifest, indent=2, default=str))
    print('Loading bounded broker candles; one worker; no forward-demo data.', flush=True)
    bars = load_and_merge([str(p) for p in files], start=datetime(2019, 7, 1), end=CUTOFF)
    bars = [b for b in bars if bar_close_time(b) <= CUTOFF]
    results = []
    def replay(policy, start, end, spread=None):
        assert end <= CUTOFF
        selected = [b for b in bars if b.timestamp >= start-timedelta(days=180) and bar_close_time(b) <= end]
        strategy = (LegacyIMS if policy == 'legacy' else ImsReversalStrategy)(**BASE, **POLICIES[policy])
        engine = BacktestEngine(initial_balance=10000, rr_ratio=2.5,
            spread_pips=config.BACKTEST_SPREAD_PIPS if spread is None else spread)
        engine.add_strategy(strategy, ['EURUSD'])
        began = time.monotonic()
        trades = engine.replay(selected, start_date=start, end_date=end)
        assert all(start <= t['close_time'] <= end for t in trades)
        result = dict(policy=policy, start=start, end=end, spread=spread, metrics=metrics(trades),
            ending_balance=engine.execution.get_account_balance(),
            max_equity_dd_pct=engine.execution.max_equity_drawdown_pct,
            open_exposure=len(engine.execution.get_open_positions()), seconds=time.monotonic()-began)
        name = f'{policy}_{start:%Y%m%d}_{end:%Y%m%d}' + (f'_spread{spread}' if spread else '')
        if verify_only:
            expected = json.loads((OUT/(name+'_trades.json')).read_text())
            assert json.loads(json.dumps(trades, default=str)) == expected, name
            result['complete_trade_path_unchanged'] = True
        else:
            (OUT/(name+'_trades.json')).write_text(json.dumps(trades, indent=2, default=str))
        results.append(result)
        (OUT/('verification_results.json' if verify_only else 'results.json')).write_text(json.dumps(results, indent=2, default=str))
        print(json.dumps(result, default=str), flush=True)
        return result
    if verify_only:
        for policy in POLICIES:
            if policy != 'legacy':
                replay(policy, datetime(2020, 1, 1), datetime(2026, 1, 1))
        return
    # Exact original baseline is the comparability check, before policy tests.
    original = replay('legacy', datetime(2020, 1, 1), datetime(2026, 1, 1))
    assert original['metrics']['trades'] == 114 and abs(original['metrics']['total_r']-32.54473) < .001
    for policy in POLICIES:
        if policy != 'legacy':
            replay(policy, datetime(2020, 1, 1), datetime(2026, 1, 1))
        for year in (2020, 2022, 2024):
            replay(policy, datetime(year, 1, 1), datetime(year+2, 1, 1))
        replay(policy, datetime(2026, 1, 1), CUTOFF)
        replay(policy, datetime(2020, 1, 1), datetime(2026, 1, 1), 1.0)


if __name__ == '__main__':
    logging.disable(logging.CRITICAL)
    main()
