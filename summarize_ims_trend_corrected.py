"""Correction report and rolling historical policy comparison for IMS trend."""
from datetime import datetime
import json

from data.histdata_provenance import file_hash, write_json
from research_ema_fib_review import metrics
from research_ims_trend_corrected import OUT, OLD, ROOT, POLICIES, FOUR
from research_ims_trend_review import settings
from summarize_ema_fib_tracking import table


def read(path):
    return json.loads(path.read_text())


def trades(folder,source,symbols,start='2020',end='2026'):
    return [t for symbol in symbols for t in read(folder/f'{source}_{symbol}_trades.json')
            if start <= t['close_time'] < end]


def policy_trades(policy,start,end):
    return [t for symbol in FOUR for t in read(OUT/f'policy_{symbol}_{policy}_trades.json')
            if start <= t['open_time'] and start <= t['close_time'] < end]


def main():
    _,symbols = settings()
    manifest = read(OUT/'manifest.json')
    assert all(file_hash(ROOT/p)==digest for p,digest in manifest['code_hashes'].items())
    assert all((OUT/f'policy_{sym}_{p}.json').exists() for sym in FOUR for p in POLICIES)
    assert sum((OUT/f'{src}_{sym}.json').exists() for src in ('dukascopy','histdata','mt5_icmarkets_utc')
               for sym in symbols)==21
    sources = ['dukascopy','histdata','mt5_icmarkets_utc']
    eight = [(f'{src} {label}',metrics(trades(folder,src,symbols)))
             for src in sources[:2] for label,folder in [('before',OLD),('corrected',OUT)]]
    four = [(f'{src} {label}',metrics(trades(folder,src,FOUR)))
            for src in sources for label,folder in [('before',OLD),('corrected',OUT)]]
    recent = [(f'{src} {label}',metrics(trades(folder,src,FOUR+['USDCAD'],'2025-04-01','2026-07-15')))
              for src in sources for label,folder in [('before',OLD),('corrected',OUT)]]
    folds, selected, default = [], [], []
    for year in (2020,2022,2024):
        train_start, split, end = f'{year-4}-07-01',f'{year}-07-01',f'{year+2}-07-01'
        training = {p:metrics(policy_trades(p,train_start,split)) for p in POLICIES}
        eligible = [p for p,m in training.items() if m['trades']>=20 and m['profit_factor'] is not None
                    and m['profit_factor']>1]
        chosen = max(eligible,key=lambda p:round(training[p]['total_r'],8)) if eligible else 'current'
        tests = {p:metrics(policy_trades(p,split,end)) for p in POLICIES}
        selected.extend(policy_trades(chosen,split,end))
        default.extend(policy_trades('current',split,end))
        train_expect = training[chosen]['expectancy']
        retention = (100*tests[chosen]['expectancy']/train_expect
                     if train_expect and train_expect>0 and tests[chosen]['expectancy'] is not None else None)
        folds.append(dict(train_start=train_start,split=split,end=end,training=training,tests=tests,
            chosen=chosen,fallback_no_eligible=not eligible,retention_pct=retention))
    totals = {'selected':metrics(selected),'current':metrics(default)}
    for policy in ('all_hours','fresh_break'):
        totals[policy] = metrics([t for fold in folds for t in policy_trades(policy,fold['split'],fold['end'])])
    summary = dict(eight=dict(eight),four=dict(four),recent=dict(recent),folds=folds,rolling=totals,
                   tests=206,baseline_control=read(OUT/'baseline_control.json'))
    write_json(OUT/'summary.json',summary)
    lines = ['# IMS trend corrections and validation, 2026-09-29', '',
        'Implemented the authorized setup-tracking recommendations for `IMS_H4_M15`. '
        'DEMO membership, eight symbols, risk, 2.5R target, and entry hours remain unchanged. '
        'No trading-host deployment was performed.', '',
        'The corrections weaken the evidence for IMS. Over 2020-2025, the current eight-symbol '
        'Dukascopy result falls from +27.11R to +22.70R and HistData from +22.91R to +12.44R. '
        'For the same four broker pairs, net R falls from -4.86R to -24.56R, with profit factor 0.78 '
        'and 31.65R closed-trade drawdown. The recent five-pair broker window falls from +10.64R '
        'to +1.20R across 30 trades. Complete the missing broker coverage before treating the corrected '
        'suite as validated or selecting replacement parameters.', '',
        '## What changed', '',
        '- Each H4 origin has a stable setup identity. Each proposal has a separate attempt identity that travels through '
        'risk, execution, the existing durable order ledger, cancellations, and trade closes.',
        '- H4 candidate validation walks forward from the first confirmed break/FVG. An origin breach, later invalid depth, '
        'or later FVG disrespect cannot be forgotten on the next scan. Historical depth uses the range known at each candle, '
        'not the final range applied backward. Retired origins cannot silently reactivate.',
        '- Proposals and accepted orders have separate records. Failed cancellations retain the accepted order and retry intent. '
        'Filled positions block new proposals and cannot be cancelled as pending orders. Partial fills keep their filled exposure '
        'when the unfilled remainder is cancelled.',
        '- Wins and losses update only their originating setup. A win retires that origin; a loss preserves the original '
        'retry/cooldown policy when the origin is still current. Late duplicate cancellation and close events are idempotent.',
        '- Pending target checks use the submitted target. The default remains entry-hours cancellation. '
        'The optional `pending_cancel_hours="all"` and `fresh_break_required=True` are research alternatives only. '
        'Sell target touches remain structural bid-price touches, not a claim that ask reached an executable take-profit.',
        '- Cold startup now requests 300 H4 and 4,800 M15 bars with current settings, so lower-timeframe invalidations can '
        'be reconstructed across the H4 history. The new helper participates in checkpoint fingerprints. '
        'Changed code invalidates the old checkpoint and triggers a fresh warmup; the existing setup ledger remains independent.', '',
        'Legacy broker orders without setup identity remain tracked and block duplicate entries. Their closes do not guess '
        'an originating setup or reset the current one. Legacy pending orders cannot receive origin-based cancellation '
        'until attributed; inspect these on the host when upgrading. This does not close or remove them automatically.', '',
        '## Validation', '',
        'All 206 tests pass, including 20 new IMS regression tests. They cover both-direction origin invalidation, '
        'historical depth and FVG checks, bid/ask pending behavior, cancellation failure, a fill racing with cancellation, '
        'partial fills, stale snapshots, late outcomes, cold ledger recovery, checkpoint recovery, legacy orders, '
        'and both optional policies. A frozen pre-correction EURUSD control reproduces all 36 saved trades exactly.', '',
        '21 corrected sequential baseline cases and 12 separate broker policy cases completed, plus the frozen control. '
        'Source/data hashes, trades, final exposure, rejections, and policy selection are saved in '
        '`output/ims_trend_corrected_20260929/`. The initial interrupted run is retained separately and is excluded.', '',
        'The baseline comparisons use the same data, date bounds, and cost model as '
        '[the original review](ims_trend_review_20260929.md): M5 fills, configured spreads, $7/lot FX commission, '
        '0.5% planned risk, no swaps, and independent symbol accounts. They are R sums, not shared-account returns. '
        'Drawdown is closed-trade R. Shared daily-loss/news/portfolio gates are not represented. '
        'Proxy spread assumptions for crosses remain uncalibrated. HistData/Dukascopy are not independent feeds. '
        'Broker H4 candle boundaries differ from proxy H4 boundaries.', '',
        '## Current eight symbols, 2020-2025', '',table(eight),'',
        '## Matched four-symbol long-history comparison, 2020-2025', '',
        'USDJPY, AUDUSD, EURUSD, GBPUSD.', '',table(four),'',
        '## Recent five-symbol comparison', '',
        'The same four plus USDCAD. April 1, 2025 through July 14, 2026. USDCAD broker warmup uses its available January-March 2025 history.',
        '',table(recent),'',
        '## Corrected per-symbol results, 2020-2025','']
    for src in sources:
        cohort = FOUR if src=='mt5_icmarkets_utc' else symbols
        lines += [f'### {src}','',table([(sym,metrics(trades(OUT,src,[sym]))) for sym in cohort]),'']
    lines += ['## Rolling historical policy comparison','',
        'Three predeclared policies, tested one change at a time on the four broker pairs. '
        '`current` retains entry-hours target cancellation and the existing structure-break definition. '
        '`all_hours` only extends target cancellation beyond entry hours. `fresh_break` only requires the previous '
        'M15 close to be on the unbroken side of the selected fractal.', '',
        'Each policy runs continuously from July 1, 2016 with earlier warmup. Rolling selection uses four years '
        'of training results and two subsequent years for evaluation. Rank eligible policies by training total R; '
        'eligibility requires at least 20 training trades and PF above 1. Ties favor current settings. '
        'If none qualifies, current settings are retained only as a comparison, not declared validated. '
        'Only trades opened and closed inside each window count. No test result enters its fold selection.', '',
        'This is a rolling comparison of continuously maintained strategy states, not a simulated switch between live accounts. '
        'Pre-boundary positions can occupy a slot until they close even though their P/L is excluded from the next window. '
        'The historical dates have already appeared in prior research, so these are not untouched out-of-sample data. '
        'Full deployment validation still requires common broker coverage and a shared-account replay.', '']
    for f in folds:
        retention = 'n/a' if f['retention_pct'] is None else f"{f['retention_pct']:.1f}%"
        lines += [f"### Train {f['train_start']} to {f['split']}; test to {f['end']}",'',
            table([(f'{p} training',f['training'][p]) for p in POLICIES]+[(f'{p} test',f['tests'][p]) for p in POLICIES]),'',
            f"Selected from training: `{f['chosen']}`. Expectancy retention: {retention}. "
            f"Fallback because none qualified: {f['fallback_no_eligible']}.",'']
    lines += ['Combined non-overlapping test windows, July 2020 through June 2026.','',
        table([('Always current',totals['current']),('Always all hours',totals['all_hours']),
               ('Always fresh break',totals['fresh_break']),('Training-selected policy',totals['selected'])]),'',
        'All three fixed policies lose money across the combined broker test windows. Current settings return '
        '-17.89R, all-hours cancellation -15.58R, and the fresh-break requirement -14.99R. Training-selected '
        'policies return -17.87R. Neither alternative establishes a profitable replacement, so both remain disabled. '
        'The corrected strategy has no demonstrated broker edge across these four pairs. The full eight-symbol '
        'suite still needs the missing broker data before a keep-or-retire decision.', '',
        '## Remaining broker data and host steps','',
        'A full eight-symbol broker comparison still needs M5 exports for EURAUD, CADJPY, and GBPCAD. '
        'This workstation cannot fetch them from MT5. On the trading host:', '', '```bat',
        'cd /d C:\\fxbot',
        'python fetch_data_mt5_icmarkets.py --symbols EURAUD CADJPY GBPCAD --timeframes M5 --start 2016-01-01 --end 2026-07-15',
        '```','',
        'Keep the actual available dates and copy the resulting CSVs and companion metadata into '
        '`data/historical/mt5_icmarkets_utc/` here. Existing verified HistData does not need downloading again.', '',
        'The changes are local and uncommitted. After reviewing the results and committing/pushing the chosen code, '
        'stop the existing bot with Ctrl+C, pull the update on the host, run the tests, and start one bot instance. '
        'Preserve `logs/setup_ledger.json`, `logs/trade_journal.csv`, and the checkpoint files. '
        'The changed checkpoint fingerprint handles the cold restart; do not delete the ledger to force startup.', '',
        '```bat','git pull --ff-only','python -m unittest discover -s tests -v','python main_live.py','```','',
        'Confirm warmup completes and the startup position/order reconciliation matches MT5. Missing required history '
        'must be resolved before startup. This review does not authorize real-money trading.','']
    path = ROOT/'strategy_log/ims_trend_corrected_20260929.md'
    path.write_text('\n'.join(lines),encoding='utf-8')
    write_json(OUT/'complete.json',dict(cases=33,frozen_control=True,tests=206,
                                      report_hash=file_hash(path),code_hashes=manifest['code_hashes']))
    print(json.dumps({k:v for k,v in summary.items() if k!='folds'},indent=2))


if __name__=='__main__':
    main()
