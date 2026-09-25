"""Build the dated EmaFib validation report from completed research artifacts."""
from copy import deepcopy
from pathlib import Path
import json

from data.histdata_provenance import write_json
from research_ema_fib_review import metrics
from research_ema_fib_tracking import OUT, PREVIOUS, ROOT


def read(name):
    return json.loads((OUT/name).read_text())


def table(rows):
    lines = ['| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |',
             '|---|---:|---:|---:|---:|---:|---:|---:|']
    for label,m in rows:
        f = lambda value,n=2: 'n/a' if value is None else f'{value:.{n}f}'
        lines.append(f"| {label} | {m['trades']} | {f(m['win_rate'])} | {m['total_r']:+.2f} | {f(m['profit_factor'])} | {f(m['expectancy'],3)} | {m['max_dd_r']:.2f} | {m['max_win_streak']} / {m['max_loss_streak']} |")
    return '\n'.join(lines)


def trades(source, label):
    result = []
    for p in sorted(OUT.glob(f'{source}_*_{label}_trades.json')):
        result.extend(json.loads(p.read_text()))
    return result


def main():
    complete = read('complete.json')
    manifest = read('manifest.json')
    results = read('results.json')
    aggregate = {(r['source'],r['label']):r['metrics'] for r in read('aggregate.json')}
    previous = {(r['source'],r['period']):r['metrics'] for r in json.loads((PREVIOUS/'aggregate.json').read_text())}
    folds = read('folds.json')
    sections = ['# EmaFib accepted-order tracking and revalidation, 25 September 2026',
        'The tracking corrections are implemented locally. DEMO membership, numeric parameters, and 0.5% risk are unchanged. This report does not authorize deployment or real-money trading. The last confirmed trading-server revision remains `4cdc9eb` from 18 September.',
        '## Assessment',
        'The order lifecycle now passes the regression checks, but the current seven-pair strategy has a weak, cost-sensitive historical edge. Corrected 2020 through 2025 results fall from +39.26R to +20.98R on Dukascopy and from +70.72R to +51.34R on verified HistData. Maximum closed-trade drawdowns remain 66.82R and 49.39R. These are sums of independent pair results, not account return percentages.',
        'Both sources produce WEAK retention in the first rolling test and a losing second test. The final test is profitable, but Dukascopy has a negative training baseline and HistData has a near-zero one. HistData\'s 1796% retention therefore does not establish reliable performance across periods. The former MODERATE label should not be carried forward as the corrected strategy\'s current verdict.',
        'A 1-pip spread changes the six-year totals to -25.21R and +4.27R. The four available broker pairs return only +11.05R, with a 60.36R drawdown and 47 consecutive losses. These results do not support increasing risk or promoting the strategy. GBPUSD and USDCAD lose on both long-history sources, while AUDUSD is approximately flat. Removing pairs improves the same historical sample, but is not yet a validated selection rule.',
        'Keep the numeric settings fixed while completing the missing broker comparison and reviewing fresh DEMO outcomes. Do not start a broad parameter search to recover the old profit figure. A later search should use a small declared grid, train-only selection in each fold, cost stress, and an untouched evaluation period. Break-even stops and pending-age filters remain unsupported by the existing evidence.',
        '## What changed',
        'Proposed signals and accepted orders now have separate state. Each accepted attempt carries a recoverable original-swing identity through the existing order ledger. New fractals and rejected proposals cannot replace that origin. Broker or simulator snapshots determine whether an order is pending or filled. An H1 price touch no longer changes order state.',
        'Cancellation requests retain their state until confirmed, and target the originating attempt. A filled position remains protected during cancellation retries or cancellation of a partially filled remainder. Final closes clear the matching order, and losses invalidate its original swing. Repeated outcomes are idempotent. Older recovered losses do not reset a current cooldown or replace a newer loss attribution.',
        'Valid checkpoints preserve full strategy state. If a checkpoint is unavailable, ledger-attributed orders recover their original swing from their setup identity. Legacy orders without that identity are still tracked and receive bias-flip cancellation checks. Their eventual losses apply a cooldown without guessing which current swing to invalidate. Pending-age settings remain disabled; the age of an inherited order without a checkpoint is not inferred.',
        'All 150 tests pass, including 17 new regression tests. The new tests cover the three audited defects, gap fills, rejection, cancellation failure and retry, partial outcomes, duplicate closes, ledger recovery including late attribution, checkpoints, legacy orders, and stale recovered losses. Research asserts that strategy and simulator ending exposure agree in every corrected run.',
        '## Research method',
        f"Completed {complete['results']} corrected replays plus {complete['baseline_controls']} frozen-code controls, one worker at a time. The frozen EURUSD and AUDUSD controls reproduce all original trade fields from the 23 September review. The original implementation is loaded from `{manifest['frozen_revision']}`. Old result files are retained.",
        'The main comparisons use 2020 through 2025 and a separate 1 January through 14 July 2026 period. Each replay starts fresh with up to 180 days of warm-up. H1/D1 generate decisions and M5 executes orders. Spread and $7 per lot round-trip commission are included. Gaps are modeled, but variable spreads, additional slippage, swap, news blocking, and the shared DEMO daily-loss/portfolio gates are absent. Trade sizes use 0.5% of each independent symbol account, initially $10,000.',
        'Tables combine independent symbol net-R trade histories in closing-time order. Profit factor is positive net R divided by absolute negative net R. These are not pooled account returns or equity drawdowns. Open exposure at each period end is left open and listed in the raw results. It is excluded from closed-trade metrics.',
        'All HistData files pass the provenance-enforcing loader. Numeric parameters are held fixed throughout. No search or symbol selection occurs inside the rolling folds. Because these historical periods were previously used in development, this is historical revalidation, not fresh unseen evidence. Data after 14 July 2026 remains excluded.',
        'The prior source audit found identical OHLC at approximately 99.98% of common M5 timestamps. HistData also omits about 10,500 to 10,800 M5 bars per pair present in Dukascopy. Provenance verification does not establish completeness or an independent price feed. The repaired HistData files are comparable evidence with different coverage, not independent confirmation.',
        '## Before and after, 2020 through 2025',
        table([(f'{s}, {version}', (previous if version=='original' else aggregate)[(s,'2020_2025')])
               for s in ('dukascopy','histdata') for version in ('original','corrected')]),
        '### A removed winner explained',
        'On 22 April 2020, AUDUSD had a pending BUY at 0.6292371. The 23:00 UTC H1 candle had a bid low of 0.62922. With the modeled 0.2-pip spread, the ask low was 0.62924, just above the entry, so the order was still unfilled. The old strategy treated the bid touch as a fill and skipped its bias-flip cancellation. At that candle\'s midnight close, the corrected strategy sees the real pending state and cancels because H1 bias has turned bearish. The old order instead filled at 00:20 on 23 April and later won +12.98R. Keeping that winner would retain the tracking defect. Separate trace files preserve both event paths.',
        '## Before and after, 2026 through 14 July',
        table([(f'{s}, {version}', (previous if version=='original' else aggregate)[(s,'2026_to_july14')])
               for s in ('dukascopy','histdata') for version in ('original','corrected')]),
        '## Corrected results by pair, 2020 through 2025',
        table([(f"{r['symbol']}, {r['source']}",r['metrics']) for r in results
               if r['label']=='2020_2025' and r['source']!='mt5_icmarkets_utc']),
        '## Rolling train/test checks',
        'Training uses 2016–2019, 2018–2021, and 2020–2023. The corresponding tests are 2020–2021, 2022–2023, and 2024–2025. Each side starts fresh. The first training window has no pre-2016 warm-up because the files start in January 2016. Training and test metrics use the same fixed parameters; no parameter is chosen using a test window. Retention is test expectancy divided by training expectancy. It is undefined when training expectancy is nonpositive. A losing test receives FAIL regardless of the ratio.',
        table([(f"{r['source']} {str(r['test_start'])[:4]} {part}",r[part]) for r in folds for part in ('train','test')])]
    lines = ['| Source | Test starts | Expectancy retention | Verdict |','|---|---|---:|---|']
    for row in folds:
        retention = 'undefined' if row['retention'] is None else f"{row['retention']*100:.1f}%"
        lines.append(f"| {row['source']} | {str(row['test_start'])[:4]} | {retention} | {row['verdict']} |")
    sections.append('\n'.join(lines))
    oos = {s:sum([trades(s,f'fold_{y}_test') for y in (2020,2022,2024)],[]) for s in ('dukascopy','histdata')}
    sections.extend(['Combined non-overlapping test windows, with fresh state at each fold boundary:',
                     table([(s,metrics(t)) for s,t in oos.items()])])
    stress_rows = [(f'{s}, {label}',aggregate[(s,label)]) for s in ('dukascopy','histdata') for label in ('2020_2025','spread_1pip')]
    sections.extend(['## Wider-spread stress',
        'This changes only spread to 1.0 pip on every pair, with the same commission and parameters. It reruns execution, so fill changes can alter later setups; the result need not worsen monotonically for every individual pair.',table(stress_rows)])
    financing = []
    for source in ('dukascopy','histdata'):
        original = trades(source,'2020_2025')
        for rate in (0,3,7):
            adjusted = deepcopy(original)
            for t in adjusted:
                t['net_r'] -= rate*t['lot_size']*t['duration_hours']/24/t['initial_risk']
            financing.append(dict(source=source,debit_usd_per_lot_per_24h=rate,metrics=metrics(adjusted)))
    write_json(OUT/'financing_sensitivity.json',financing)
    sections.extend(['## Illustrative financing debit',
        'Historical broker swap schedules are unavailable. This is a post-processing sensitivity, not a broker swap backtest: subtract $0, $3, or $7 per lot for each 24 hours held, prorated by duration. It keeps original fills, lot sizes, and trade paths fixed. It does not model directional credits, rollover times, triple-swap days, or changed compounding.',
        table([(f"{r['source']}, ${r['debit_usd_per_lot_per_24h']}/lot/day",r['metrics']) for r in financing])])
    subset = []
    for source in ('dukascopy','histdata'):
        original = trades(source,'2020_2025')
        for removed in ([],['GBPUSD'],['USDCAD'],['GBPUSD','USDCAD']):
            subset.append(dict(source=source,removed=removed,metrics=metrics([t for t in original if t['symbol'] not in removed])))
    write_json(OUT/'symbol_exclusion_diagnostic.json',subset)
    sections.extend(['## Symbol exclusions, diagnostic only',
        'Each single-symbol exclusion is shown separately, followed by both. These are recombinations of independent pair results, without shared account interaction. GBPUSD and USDCAD were identified using the same historical evaluation years, so these comparisons are post-hoc and do not validate a new five-pair deployment.',
        table([(f"{r['source']}, omit {', '.join(r['removed']) or 'none'}",r['metrics']) for r in subset])])
    broker = manifest['broker_symbols']
    sections.extend(['## Matched broker-data comparison',
        f"Complete M5/H1/D1 broker files exist for {', '.join(broker)}. The following tables compare exactly those pairs on each source. Broker D1 bars retain the IC Markets session boundaries, including Sunday UTC starts, while the other sources use UTC-day bars. These candle differences are part of the deployment check."])
    for period in ('2020_2025','2026_to_july14'):
        sections.extend([period,table([(s,aggregate[(s,period if s=='mt5_icmarkets_utc' else 'broker_matched_'+period)]) for s in ('dukascopy','histdata','mt5_icmarkets_utc')])])
    sections.extend(['The broker subset is incomplete. NZDUSD, USDCAD, and USDCHF lack M5 exports here. Run this read-only data export on the MT5 Windows host, then copy the resulting three CSVs into this checkout\'s `data/historical/mt5_icmarkets_utc/` directory:',
        '```cmd\ncd /d C:\\fxbot\npython fetch_data_mt5_icmarkets.py --symbols NZDUSD USDCAD USDCHF --timeframes M5 --start 2016-01-01 --end 2026-07-15\n```',
        'The H1/D1 files for those pairs are already present. This command does not deploy the code changes or start another bot process. Completing the seven-pair broker comparison depends on receiving the missing exports.'])
    coverage = read('coverage.json')['results']
    lines = ['| Source | Pair | TF | Missing higher bars with complete M5 coverage | Different common OHLC |',
             '|---|---|---|---:|---:|']
    for row in coverage:
        lines.append(f"| {row['source']} | {row['symbol']} | {row['timeframe']} | {row['missing_despite_complete_m5']} | {row['common_ohlc_differ']} |")
    sections.extend(['## Coverage audit',
        'Dukascopy has two or three missing H1 bars per pair despite complete M5 coverage, plus a few inconsistent higher-timeframe OHLC values. HistData\'s H1/D1 bars agree with its own M5 aggregation in this check. The known missing Dukascopy AUDUSD H1 candle at 23 March 2026 19:00 UTC explains the approximately 12.96R recent-period source difference documented in the prior review. The remaining coverage findings limit claims of agreement; do not delete valid HistData bars to force its results to match.',
        'Checks compare H1 and weekday D1 availability/OHLC against aggregation of the available M5 candles, from 2020 through 14 July 2026. A complete H1 bucket contains 12 M5 candles; a complete D1 bucket contains 288. These are coverage checks, not proof that every market tick exists. CSV files were not filled, deleted, or rebuilt.', '\n'.join(lines)])
    exposure = [(r['source'],r['symbol'],r['label'],len(r['open_exposure'])) for r in results if r['open_exposure']]
    sections.extend(['## Period-end exposure',
        'Open/pending counts by source, symbol, and run are recorded below. These trades are not forcibly liquidated and are excluded from the closed results.',
        '\n'.join(f'- {s}, {sym}, {label}: {n}' for s,sym,label,n in exposure) if exposure else 'All corrected runs ended flat.',
        '## Reproduction and deployment boundary',
        'The 134-run study finished with matching code hashes. A subsequent recovery-only correction lets authoritative ledger attribution replace an initially unknown legacy origin. The tested strategy snapshot remains in `study_strategy.py`, with the original manifest unchanged. Two additional full-period EURUSD/AUDUSD controls match every corrected trade field and ending exposure. `recovery_hardening_verification.json` records the final source hashes and those checks. This late-attribution branch is not exercised by fresh backtest orders, which receive their origin at acceptance.',
        '```powershell\n.venv\\Scripts\\python.exe -m unittest discover -s tests -v\n.venv\\Scripts\\python.exe research_ema_fib_tracking.py\n.venv\\Scripts\\python.exe audit_ema_fib_coverage.py\n.venv\\Scripts\\python.exe summarize_ema_fib_tracking.py\n```',
        'Detailed trades, assumptions, input and code hashes, fold results, and controls are saved in `output/ema_fib_tracking_20260925/`. The previous review remains in `output/ema_fib_review_20260923/`. No MT5 terminal connection, deployment, risk increase, or real-money promotion was performed. Any eventual rollout must preserve `logs/setup_ledger.json` and stop the old bot before starting a new instance. Legacy inherited orders remain explicitly unattributed rather than assigned to a guessed swing.'])
    path = ROOT/'strategy_log/ema_fib_tracking_20260925.md'
    path.write_text('\n\n'.join(sections)+'\n',encoding='utf-8')
    print(path)


if __name__ == '__main__':
    main()
