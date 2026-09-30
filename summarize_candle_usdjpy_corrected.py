"""Verify the completed fixed-parameter replay and write its research baseline."""
import json
from pathlib import Path
from data.histdata_provenance import file_hash, write_json

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'output/candle_usdjpy_corrected_20260930'


def read(name):
    return json.loads((OUT/name).read_text())


def main():
    manifest,results = read('manifest.json'),read('results.json')
    assert read('complete.json')==dict(replays=9,controls=3,hashes_match=True)
    formatting = read('postrun_formatting.json')
    for p,h in manifest['code_hashes'].items():
        if p==formatting['path'].replace('\\','/'):
            assert h==formatting['before_sha256'] and formatting['syntax_tree_identical']
            assert file_hash(ROOT/p)==formatting['after_sha256']
        else:
            assert file_hash(ROOT/p)==h
    assert all(file_hash(p)==h for p,h in manifest['input_hashes'].items())
    assert all(file_hash(p)==h for p,h in manifest['metadata_hashes'].items())
    assert all(c['all_economic_trade_fields_match'] for c in read('controls.json'))
    names = {'dukascopy':'Dukascopy','histdata':'HistData','mt5_icmarkets_utc':'IC Markets'}
    lines = ['# Candle Confirmation USDJPY tracking baseline, 2026-09-30','',
        'Implemented the requested attribution, warmup, and executable stop checks locally. '
        'The fixed parameters still do not show a consistent edge across the available feeds. '
        'This is a baseline for future research, not a parameter promotion or host deployment.','',
        '## What changed','',
        '- A setup is identified by strategy, symbol, direction, and the originating H1 candle in UTC. '
        'Each proposed entry has its own timestamped attempt ID.',
        '- Accepted orders retain ownership until a confirmed cancellation or final close. '
        'An old close cannot clear a newer setup. Rejected fills release their own attempt. '
        'Partial closes and cancelled remainders preserve filled exposure.',
        '- All final outcomes, including break-even, consume their own originating setup. '
        'Duplicate callbacks are harmless. Legacy positions block entries conservatively; '
        'their unknown origin is never inferred from the latest bias.',
        '- The existing account-bound durable ledger and code/config-bound checkpoint preserve attribution '
        'across restarts. Changed source invalidates old checkpoints; it does not discard the ledger.',
        '- Current D1 EMA20/50 settings request 250 D1, 100 H1, and 1,200 M5 completed bars. '
        'The demo runner already enforces the requested counts and chronological replay. '
        'CSV backtests and OOS warmup now allow more calendar history when the strategy requires it. '
        'Calendar allowance alone cannot guarantee enough bars in a source with gaps.',
        '- The strategy minimum is passed as a price distance through risk and execution. '
        'For USDJPY this is 0.08, or eight pips. Simulated market orders check the next-open '
        'bid/ask fill before creating exposure. MT5 checks the final rounded request quote before submission, '
        'then checks the reported broker fill after acknowledgement.',
        '- Broker slippage can still violate the minimum after submission. Such a real position retains '
        'its ticket and is logged as a violation; it is not treated as a rejected order or automatically closed. '
        'A missing broker fill price is marked unknown rather than reported as a confirmed pass.',
        '- Signal and order journal context now includes origin/attempt IDs, engulf range and retracement, '
        'pivot time and level, previous close, fresh-cross status, opposite-extreme breach, and trend alignment. '
        'These are observations. They do not enable new entry filters. MT5 execution context records the '
        'fill, stop validation, and price source.',
        '- The shared Candle Confirmation class also gives GBPUSD these lifecycle and minimum-stop checks. '
        'GBPUSD performance was not reassessed here. Entry rules, parameters, risk, and DEMO membership remain unchanged.','',
        '## Matched comparison','',
        'USDJPY only, January 1, 2017 through July 14, 2026. All variants use the same '
        'completed 2016 warmup history and unchanged DEMO parameters. Trading starts in 2017 '
        'so each feed has at least 250 completed D1 bars. This differs from the preceding '
        'July 2016-start review and its totals must not be mixed with these figures. '
        'Replay is sequential, with a 0.2-pip spread, configured commission, and 0.5% planned '
        'account risk. It has no other strategies, news filter, portfolio competition, or forced end liquidation.','',
        '| Feed | Version | Trades | Win % | Net R | PF | R/trade | Closed DD R | Win/loss streak |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in results:
        if r['variant']=='tracking_only':
            continue
        m=r['metrics']
        lines.append(f"| {names[r['source']]} | {r['variant']} | {m['trades']} | {m['win_rate']:.2f} | "
            f"{m['total_r']:+.2f} | {m['profit_factor']:.3f} | {m['expectancy']:+.4f} | "
            f"{m['max_dd_r']:.2f} | {m['max_win_streak']}/{m['max_loss_streak']} |")
    lines += ['', 'Tracking-only runs match every economic trade field of the frozen original class '
        'on all three feeds. The corrected version adds the executable stop guard. '
        'Each feed rejects four undersized fills; subsequent setup decisions can change, '
        'so the effect cannot be estimated by deleting those trades from an old trade list. '
        'All nine replays end with no open exposure.','',
        'Net R uses actual filled entry-to-stop risk after costs. The old Dukascopy result includes '
        'the +27.21R trade with a 0.73-pip filled stop. Removing this distortion lowers the R total '
        'substantially, while account growth changes very little.','',
        '| Feed | Version | Planned-budget R | Account growth | Equity DD | Minimum filled stop |',
        '|---|---|---:|---:|---:|---:|']
    for r in results:
        if r['variant']=='tracking_only':
            continue
        lines.append(f"| {names[r['source']]} | {r['variant']} | {r['budget_metrics']['total_r']:+.2f} | "
            f"{r['account_growth_pct']:+.2f}% | {r['max_equity_drawdown_pct']:.2f}% | "
            f"{r['minimum_actual_stop_pips']:.2f} pips |")
    lines += ['', 'Planned-budget R divides net profit by 0.5% of the account balance for that trade. '
        'It is reconstructed here from the sequential single-position balance and reconciles exactly '
        'to ending balance. It measures deployment impact more directly than a tiny actual-stop denominator.','',
        '## Later periods with corrected execution','',
        '| Feed | Period | Trades | Win % | Net R | PF | R/trade | Closed DD R | Win/loss streak |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in results:
        if r['variant']!='corrected':
            continue
        ts = read(f"{r['source']}_corrected_trades.json")
        contexts = {x['attempt_id']:x for x in read(f"{r['source']}_corrected_contexts.json")}
        assert len(contexts)==r['events']['ORDER_PLACED']
        assert len(ts)+sum(r['rejected'].values())==len(contexts)
        for t in ts:
            c=contexts[t['attempt_id']]
            assert c['setup_id']==t['setup_id']
            assert abs(t['entry_price']-t['sl'])/.01+1e-8>=8
            assert abs(t['tp']-t['entry_price'])/abs(t['entry_price']-t['sl'])+1e-8>=1
        for key in ('2020_2025','2026_to_july14'):
            m=r['windows'][key]
            lines.append(f"| {names[r['source']]} | {key.replace('_',' ')} | {m['trades']} | {m['win_rate']:.2f} | "
                f"{m['total_r']:+.2f} | {m['profit_factor']:.3f} | {m['expectancy']:+.4f} | "
                f"{m['max_dd_r']:.2f} | {m['max_win_streak']}/{m['max_loss_streak']} |")
    lines += ['', 'These are descriptive historical subdivisions, not new untouched OOS validation. '
        'No parameters were selected on them. HistData retains documented 2023 provider gaps, '
        'and its recent matching prices are nearly identical to Dukascopy. It is not an independent '
        'feed confirmation. No forward DEMO results after the research cutoff enter these figures.','',
        '## Next research steps','',
        'Use the corrected class and these outputs as the control. Change one rule or parameter at '
        'a time, declare the training and later test windows first, and retain setup/attempt IDs '
        'when comparing trade lists. The existing fresh-cross observation lets us identify trades '
        'affected by that proposed rule without changing production behavior. Compare account growth, '
        'planned-budget R, costs, and drawdown alongside filled-risk R. Recheck broker spread sensitivity '
        'and chronological walk-forward performance before considering a material DEMO parameter change.','',
        '## Verification and host update','',
        'All 228 tests pass, including 22 focused lifecycle/execution tests. Completed nine sequential '
        'replays and three exact tracking-only controls. The audit checks accepted/closed/rejected counts, '
        'origin attribution, minimum filled stops, minimum filled R:R, input hashes, and HistData sidecars. '
        'A redundant EOF blank line was removed after replay with an identical syntax tree; '
        '`postrun_formatting.json` records both source hashes.','',
        'Results, accepted setup context, trade lists, manifest, controls, and completion marker are '
        'under `output/candle_usdjpy_corrected_20260930/`. The replay script refuses to overwrite an '
        'existing manifest; use a new output directory for a future experiment. Earlier review '
        'outputs remain historical evidence for earlier code, not the corrected control.','',
        'The changes are local and uncommitted. No MT5 connection or host deployment occurred. '
        'After committing/pushing the reviewed change, stop the existing bot process on the trading '
        'host, pull with `git pull --ff-only`, run `python -m unittest discover -s tests -v`, and '
        'restart with `python main_live.py`. Preserve existing ledger and journal files. '
        'Expect a cold warmup because the code fingerprint changed, followed by broker reconciliation. '
        'Positions created before setup IDs existed remain legacy exposure until confirmed closure.','']
    report=ROOT/'strategy_log/candle_usdjpy_corrected_20260930.md'
    report.write_text('\n'.join(lines),encoding='utf-8')
    write_json(OUT/'audit_complete.json',dict(replays=9,controls=3,
        attribution_and_stops_verified=True,hashes_verified=True,report_sha256=file_hash(report)))
    print(str(report))


if __name__=='__main__':
    main()
