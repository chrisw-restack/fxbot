"""Final broker-history controls after the partial-fill cancellation race fix."""
from datetime import datetime, timezone
import json
import logging

from data.historical_loader import load_and_merge
from data.histdata_provenance import file_hash, write_json
import research_ema_fib_running_corrections as research
from strategies.ema_fib_running import EmaFibRunningStrategy


class CheckedRunning(EmaFibRunningStrategy):
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.late_partial_fills=0

    def sync_order_state(self,order):
        key,_=self._find_order(order)
        state=order.get('state') or ('OPEN' if order.get('open_time') is not None else 'PENDING')
        if state=='OPEN' and (key in self._finished_orders or self._identities(order)&self._cancelled_order_ids):
            self.late_partial_fills+=1
        return super().sync_order_state(order)


def main():
    logging.disable(logging.CRITICAL)
    out=research.OUT
    manifest=json.loads((out/'manifest.json').read_text())
    strategy_path='strategies/ema_fib_running.py'
    assert file_hash(out/'strategy_before_partial_race_fix.py')==manifest['code_hashes'][strategy_path]
    assert all(file_hash(research.ROOT/p)==sha for p,sha in manifest['code_hashes'].items() if p!=strategy_path)
    final_hash=file_hash(research.ROOT/strategy_path)
    params,symbols=research.settings()
    assert params==manifest['parameters']
    research.CLASSES['corrected']=CheckedRunning
    controls=[]
    for symbol in symbols:
        if symbol=='USDCAD':
            continue
        paths=research.paths_for('mt5_icmarkets_utc',symbol)
        assert all(file_hash(p)==manifest['input_hashes'][p] for p in paths)
        bars=load_and_merge(paths,start=datetime(2019,7,1),end=datetime(2026,1,1))
        # Capture the inspected instance without changing the replay's event flow.
        instances=[]
        def factory(**kwargs):
            strategy=CheckedRunning(**kwargs)
            instances.append(strategy)
            return strategy
        research.CLASSES['corrected']=factory
        result,trades=research.replay(bars,'mt5_icmarkets_utc',symbol,'corrected','final_code_control',
            datetime(2020,1,1),datetime(2026,1,1),params)
        previous=out/f'mt5_icmarkets_utc_{symbol}_corrected_2020_2025_trades.json'
        assert json.loads(json.dumps(trades,default=str))==json.loads(previous.read_text())
        assert result['open_exposure']==json.loads((out/f'mt5_icmarkets_utc_{symbol}_corrected_2020_2025.json').read_text())['open_exposure']
        assert instances[0].late_partial_fills==0
        controls.append(dict(symbol=symbol,all_trade_fields_match=True,ending_exposure_matches=True,
            late_partial_fills=0,prior_trades_sha256=file_hash(previous)))
        del bars
    assert final_hash==file_hash(research.ROOT/strategy_path)
    write_json(out/'final_code_validation.json',dict(created_utc=datetime.now(timezone.utc),controls=controls,
        strategy_sha256=final_hash,validation_script_sha256=file_hash(__file__),
        preceding_strategy_sha256=manifest['code_hashes'][strategy_path],
        explanation='The final change permits a confirmed OPEN snapshot after remainder cancellation. '
                    'The CSV simulator has no partial fills. All six matched broker-history replays match '
                    'every previous trade field and ending exposure; no replay enters the changed branch. '
                    'The broker cancellation race is covered by a new deterministic regression test.'))
    print('All six final-code broker controls match.',flush=True)


if __name__=='__main__':
    main()
