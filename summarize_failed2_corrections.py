"""Build the correction report from saved, reproducible replay artifacts."""
import json

from research_failed2_corrections import OUT, BASE, ROOT, SOURCES
from summarize_ema_fib_tracking import table


def read(path):
    return json.loads(path.read_text())


def main():
    rows=read(OUT/'results.json')
    complete=read(OUT/'complete.json')
    folds=read(OUT/'folds.json')
    restart=read(OUT/'restart_validation.json')['variants']
    old=read(BASE/'results.json')
    idx={(r['source'],r['variant'],r['label']):r for r in rows}
    oldidx={(r['source'],r['variant'],r['label']):r for r in old}
    sections=['# Failed2 market corrections, 28 September 2026',
        'The user authorized the startup-history and setup-tracking recommendations. They are implemented locally. Failed2 remains in the DEMO suite on USTEC at unchanged numeric settings and global 0.5% risk. EmaFibRunning remains excluded from new runs. No MT5 connection, deployment, or real-money promotion occurred.',
        '## Assessment',
        'The corrections preserve the historical case for continued DEMO evaluation. Broker results remain +53.29R for 2020 through 2025, with PF 1.48 and 10.14R closed-trade drawdown. The latest 2024 through 2025 broker test remains +17.28R with 71.6% expectancy retention. The longer histories each add two losing trades after the tracking correction, leaving +103.00R on Dukascopy and +99.68R on HistData. Their latest historical tests remain positive but retain only about 29–31% of training expectancy, which is WEAK under project standards.',
        'At the current settings, extending the initial D1 warm-up makes no further difference to full-period 2020 through 2025 metrics on these sources. It still corrects an operational mismatch: the actual July restart with 50 daily bars permitted a signal that the complete range window blocks. No numeric optimization is justified by this correction exercise. Collect fresh DEMO evidence from the corrected version before treating the historical edge as confirmed.',
        '## What changed',
        'The startup runner now collects each strategy\'s history requirements per symbol and timeframe. Failed2 requests at least 61 daily candles for its 60-prior-day range comparison, and five times the longer EMA period for EMA initialization. Current settings therefore request 250 completed USTEC D1 bars. Other timeframes retain their existing defaults. A shared symbol/timeframe uses the largest requirement, so other strategies subscribed to USTEC D1 also receive that history. Startup refuses insufficient history. The range filter independently refuses entries until the full comparison window exists.',
        'Market proposals now carry stable identities based on strategy, symbol, direction, and H1 setup time in UTC. A proposal does not consume the setup. Acceptance does, and later closure does not release it. Rejections while another trade occupies the slot leave the unsubmitted setup available. If the simulator rejects a queued market fill at its next executable price, only that identified unfilled attempt releases consumption.',
        'The existing account-bound setup ledger persists the identity before a broker submission and attributes confirmed orders and outcomes to it. Open-order and closed-trade recovery restore consumption without needing a strategy checkpoint. Checkpoints preserve the same state and invalidate when the history policy changes. Historical orders without setup identities remain unattributed; the code does not invent their H1 origins. Preserve logs/setup_ledger.json on the trading host.',
        'The market structure condition, stop anchor, H4 refresh, 4R target, session, symbols, and risk are unchanged. No fresh-cross filter, time exit, or parameter optimization was introduced. FVG retains its legacy order-tracking path; it is not validated by these market-mode runs.',
        '## Before and after, 2020 through 2025',
        table([(f'{src}, {variant}',idx[src,variant,'2020_2025']['metrics'])
               for src in SOURCES for variant in ('baseline','tracking','corrected')]),
        'Baseline is the immutable reviewed strategy from commit 2d58c1b24424a235d3337627850b15fc778e6040. Tracking applies the lifecycle and full-range-readiness corrections with the original 180-calendar-day warm-up. Corrected also changes the D1 warm-up to the most recent 250 completed bars when available. All other warm-up streams remain at 180 calendar days for comparison with the original continuous research replay. These are continuous backtests, not simulated daily restarts.',
        '## January through 14 July 2026',
        table([(f'{src}, {variant}',(oldidx[src,'current','2026_to_july14'] if variant=='baseline' else idx[src,'corrected','2026_to_july14'])['metrics'])
               for src in SOURCES for variant in ('baseline','corrected')]),
        '## Historical rolling validation',
        'Four-year training and two-year test periods retain fixed numeric settings. These periods were already used in development and are not fresh unseen evidence. The first 2016 training fold has no earlier history; readiness guards hold entries until the necessary observations exist. Later folds seed from prior data. Broker validation uses the final fold.',
        table([(f"{r['source']}, test {r['test_year']}, {part}",r[part]) for r in folds for part in ('train','test')])]
    lines=['| Source | Test starts | Expectancy retention | Verdict |','|---|---:|---:|---|']
    for row in folds:
        value='undefined' if row['retention'] is None else f"{row['retention']*100:.1f}%"
        lines.append(f"| {row['source']} | {row['test_year']} | {value} | {row['verdict']} |")
    sections.extend(['\n'.join(lines),
        'Retention is test R/trade divided by training R/trade. The project thresholds are 70% for STRONG and 40% for MODERATE. A losing test fails regardless of retention.',
        '## Spread stress',
        table([(f'{src}, {label}',idx[src,'corrected',label]['metrics']) for src in SOURCES for label in ('2020_2025','spread_2','spread_5')]),
        'Spread is one, two, or five index points. These are full replays, not deductions from a fixed trade list.',
        '## Reproduced restart',
        'The 14 July 2026 cold-start reconstruction uses the actual 14:48:58 UTC restart time and stored broker bars. The frozen old code with 50 D1 bars reproduces the logged 15:05 BUY proposal at 29,649.4, SL 29,360.8, and TP 30,803.8. Corrected code emits no entry with either insufficient history or a complete range window.',
        '| Variant | Daily bars | Range rank | Entry filter passes | Signals |\n|---|---:|---:|---|---:|\n'+
        '\n'.join(f"| {r['label']} | {r['daily_bars']} | {r['rank']:.4f} | {r['filter_passes']} | {len(r['signals'])} |" for r in restart),
        f"At the actual startup, EMA50 is {restart[3]['ema_slow']:.6f} with the new history policy versus {restart[4]['ema_slow']:.6f} using all {restart[4]['daily_bars']} available reference bars. Finite warm-up reduces seed dependence; it does not mathematically equal unlimited history. The full-history range rank is 0.70 and blocks this entry. This reconstruction matches the historical signal, not exact broker fills or the entire shared account.",
        '## Validation and limits',
        f"Completed {complete['replays']} sequential replays, including {complete['controls']} frozen-baseline controls. Each control exactly matches every stored trade field and ending exposure from the original review. Source hashes match the prior review, HistData is loaded through its provenance checks, and code hashes stayed unchanged during the runs. No price bars after 14 July 2026 enter the analysis.",
        'All 186 unit tests pass, including 14 new Failed2 cases. These cover occupied-slot rejection, acceptance, late rejection, failed market fills, open and closed ledger recovery, UTC identity, checkpoints, broker submission persistence, and full daily-range requirements. The broker test uses a fake adapter and makes no MT5 connection.',
        'Assumptions match the original review: isolated strategy, $10,000 starting balance, 0.5% risk, M5 execution, bid OHLC, one-point default spread, and zero index commission. Actual financing, variable spread, extra slippage, news, shared-account position limits, and daily-loss gates are excluded. R drawdown uses closed trades, not floating equity. Dukascopy and HistData have near-identical shared M5 candles and are not independent confirmation. Weekend gap risk from the DEMO review remains relevant.',
        'Open exposure at period boundaries is excluded from closed-trade totals and is not liquidated using future prices:\n\n'+
        ('\n'.join(f"- {r['source']} {r['variant']} {r['label']}: {len(r['open_exposure'])} open/pending" for r in rows if r['open_exposure']) or 'All replays ended flat.'),
        '## Trading-host update',
        'Transfer the tested code, stop the old bot process, run the unit suite, and start one bot instance. Preserve logs/setup_ledger.json. The changed code invalidates the old strategy checkpoint and triggers fresh history initialization. MT5 must supply 250 completed USTEC D1 bars at current settings. Existing broker stops and targets remain in place. The corrected strategy cannot recover setup identities for trades created by the old version.',
        '## Reproduction',
        '```powershell\npython -m unittest discover -s tests -v\npython research_failed2_corrections.py\npython validate_failed2_restart.py\npython summarize_failed2_corrections.py\n```',
        'Run with the project backtest environment and one worker. Detailed results, trades, control checks, code and input hashes, and the restart reproduction are in output/failed2_corrections_20260928/. The earlier failed2_review_20260928.md is the pre-correction snapshot; use this report and these commands for current code.'])
    report=ROOT/'strategy_log/failed2_corrections_20260928.md'
    report.write_text('\n\n'.join(sections)+'\n',encoding='utf-8')
    print(report)


if __name__=='__main__':
    main()
