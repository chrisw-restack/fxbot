"""Verify late ledger attribution hardening against the completed study."""
from datetime import timedelta
import json
import logging

from data.historical_loader import load_and_merge
from data.histdata_provenance import file_hash, write_json
from research_ema_fib_review import current_settings, paths_for, PERIODS
from research_ema_fib_tracking import OUT, ROOT, run


def main():
    logging.disable(logging.CRITICAL)
    manifest = json.loads((OUT/'manifest.json').read_text())
    study_hash = file_hash(OUT/'study_strategy.py')
    assert study_hash == manifest['code_hashes']['strategies/ema_fib_retracement.py']
    params, _ = current_settings()
    _, start, end = PERIODS[0]
    controls = []
    for symbol in ('EURUSD', 'AUDUSD'):
        bars = load_and_merge(paths_for('dukascopy', symbol), start=start-timedelta(days=180), end=end)
        result, trades = run(bars, 'dukascopy', symbol, 'recovery_control', start, end, params)
        old = json.loads((OUT/f'dukascopy_{symbol}_2020_2025.json').read_text())
        old_trades = json.loads((OUT/f'dukascopy_{symbol}_2020_2025_trades.json').read_text())
        assert json.loads(json.dumps(trades, default=str)) == old_trades
        assert json.loads(json.dumps(result['open_exposure'], default=str)) == old['open_exposure']
        controls.append(dict(symbol=symbol, all_trade_fields_match=True, ending_exposure_matches=True))
        del bars
    write_json(OUT/'recovery_hardening_verification.json', dict(
        study_strategy_sha256=study_hash,
        final_strategy_sha256=file_hash(ROOT/'strategies/ema_fib_retracement.py'),
        explanation='Late ledger attribution upgrades an initially unknown legacy order. '
                    'Fresh research orders already have attribution at acceptance. '
                    'The original study manifest is preserved with its tested strategy snapshot.',
        controls=controls,
        final_code_hashes={p:file_hash(ROOT/p) for p in manifest['code_hashes']}))


if __name__ == '__main__':
    main()
