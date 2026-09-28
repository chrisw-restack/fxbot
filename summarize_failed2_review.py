"""Render the fixed-parameter Failed2 market review from saved artifacts."""
from copy import deepcopy
from datetime import datetime
import json
from statistics import median

from data.histdata_provenance import write_json
from research_failed2_review import OUT, ROOT, SOURCES
from research_ema_fib_review import metrics
from summarize_ema_fib_tracking import table


def read(name):
    return json.loads((OUT/name).read_text())


def main():
    complete=read('complete.json')
    rows=read('results.json')
    indexed={(r['source'],r['variant'],r['label']):r for r in rows}
    folds=read('folds.json')
    demo=read('demo_evidence.json')
    data=read('data_audit.json')
    sections=['# Failed2 H4/H1/M5 market review, 28 September 2026',
        'Scope: the configured Failed2_H4_H1_M5_market strategy on USTEC. Production Failed2 logic, parameters, risk, and DEMO membership are unchanged. EmaFibRunning was separately removed from default startup at the user\'s explicit request. No interaction with MT5 or deployment occurred.',
        '## Assessment and recommended order of work',
        'The historical evidence supports further work on Failed2 rather than retirement. At current settings, the 2020–2025 broker replay earns +53.29R with PF 1.48 and 10.14R closed-trade drawdown. Its 2024–2025 historical test remains profitable at +17.28R and retains 71.6% of training expectancy. However, the same final test retains only 31–32% on the two long-history sources: profitable, but WEAK by the project standard. The older blanket STRONG label therefore overstates current evidence.',
        'Verified HistData produces comparable results to Dukascopy, but their near-identical M5 prices do not establish independent confirmation. The copied DEMO record is weak: eight trades, one winner, and a net loss of $778.31. It mixes earlier versions and operational conditions, so it neither validates current code nor isolates the cause of the loss.',
        'First correct startup history requirements and test consistent daily-filter initialization. Then distinguish proposed from accepted setups and recover consumed setup identities across cold restarts. Compare those corrections against this frozen baseline before optimizing numeric parameters. The fresh-cross diagnostic has mixed results and worse long-period drawdown on every source; it does not justify changing the entry rule. Keep H4 refresh and stop-anchor alternatives as separate research questions. No Failed2 production correction or parameter promotion is made in this review.',
        '## Current rules',
        'H4 candles select BUY or SELL using the previous candle\'s body and wick extremes. The labels 2, 3, and failed2 describe this custom body-based implementation. For example, a bullish 2 can close above the prior body high while remaining inside its wick range; the labels do not enforce strict wick-based candle categories.',
        'Every qualifying H4 candle refreshes the bias and clears the H1 setup and accumulated M5 bars, including a same-direction H4 candle. A candle that produces no new bias leaves the existing bias active by default. The older statement that only an opposite bias replaces the setup was incomplete.',
        'An H1 candle must close strictly after the bias candle. BUY confirmation sweeps the previous H1 low and closes back above it; SELL is mirrored. An outside candle can qualify because there is no requirement to avoid sweeping the opposite side. A later qualifying H1 candle replaces the current H1 setup.',
        'M5 entry must close strictly after H1 confirmation. A swing needs four completed bars on each side for the structure level. BUY requires a close above a confirmed swing high; SELL requires a close below a confirmed swing low. The stop uses a two-bar fractal on the opposite side whose pivot occurs BEFORE the selected broken pivot. It is not necessarily the most recent opposite pivot before entry. One accepted-or-consumed setup flag normally suppresses further signals for the same H1 confirmation.',
        'D1 EMA 20/50 must align with entry direction. The last completed D1 range is compared with the preceding 60 daily ranges. A rank of at least 0.70 blocks entries, meaning the top 30% is blocked. Signal bars have UTC opening-hour labels 13, 14, or 15; the last allowed M5 signal closes at 16:00 UTC. This fixed UTC window shifts relative to New York local time with daylight saving.',
        'The strategy sets TP at four times the distance from signal close to SL. Actual execution occurs at the next M5 open in backtests and at the executable quote on the host. Spread and gaps change the realized entry R:R. The execution layer rechecks the minimum 1R requirement and sizes against the executable entry, while retaining the strategy\'s locked target. Four is a target based on the signal price, not a guarantee of four net R per winning trade.',
        '## Current parameters, 2020 through 2025',
        table([(src,indexed[(src,'current','2020_2025')]['metrics']) for src in SOURCES]),
        'These are isolated strategy results at the current settings, after the shared simulator and data-provenance repairs. They are not a controlled before/after comparison with May tables that used older windows, data, costs, and execution assumptions.',
        '## January through 14 July 2026',
        table([(src,indexed[(src,'current','2026_to_july14')]['metrics']) for src in SOURCES]),
        '## Historical rolling validation',
        'Four-year training windows and two-year test windows use the same fixed parameters. No search occurs within these runs. The periods were used in earlier strategy development, so these are historical revalidation checks, not fresh unseen evidence. The first training run starts in January 2016 without earlier warm-up. Later runs use 180 days. Broker validation uses the final 2020 through 2023 training window and 2024 through 2025 test.',
        table([(f"{r['source']}, test {r['test_year']}, {part}",r[part]) for r in folds for part in ('train','test')])]
    lines=['| Source | Test starts | Expectancy retention | Verdict |','|---|---:|---:|---|']
    for r in folds:
        pct='undefined' if r['retention'] is None else f"{r['retention']*100:.1f}%"
        lines.append(f"| {r['source']} | {r['test_year']} | {pct} | {r['verdict']} |")
    sections.extend(['\n'.join(lines),
        'Retention divides test expectancy by training expectancy. It is undefined for nonpositive training expectancy; a losing test fails regardless of the ratio.',
        '## Logic and lifecycle findings',
        '1. **The entry need not be a new structure break.** The code checks whether the current close is beyond a swing. It does not require the preceding close to be on the other side or require the first break to occur after H1 confirmation. The deterministic BUY example enters at 112 above a 110 swing after the preceding candle already closed at 111 before H1 confirmation. SELL has the same behavior. This is a rule ambiguity with material trade impact, not future-data leakage.',
        '2. **Cold startup underfills the range filter.** main_live.py supplies 50 D1 bars, while the configured range comparison needs 60 prior bars plus the evaluated day. The audit reproduces a full-history rank of 70%, which blocks trading, versus 63.27% with 50 bars, which allows it. At least 61 completed D1 bars are needed for that comparison. A consistent warm-up policy should also be tested for EMA initialization.',
        'The actual 14 July restart provides a concrete example. Reconstructing the 14:48:58 UTC startup with stored broker candles and 50 D1 bars reproduces the 15:05 BUY signal at 29,649.4, SL 29,360.8, and TP 30,803.8. These match the supplied log and journal for ticket 1807793687. With 61 D1 bars, the range rank reaches the blocking threshold of 0.70 and no signal occurs; the EMA trend stays BUY in both cases. The actual position later lost $152.18 net. This is an isolated current-code reconstruction of the signal, not a replay of the entire account or its exact broker fills. Evidence is saved in `restart_reproduction.json`.',
        '3. **A rejected setup can be consumed while another position is open.** Failed2 sets its traded-setup flag when it emits a proposal. With a free slot, the rejection hook releases it. With an occupied strategy slot, the engine\'s legacy rejection path skips that hook, so the unsubmitted H1 setup stays consumed. This can suppress entry after the existing trade closes. It does not overwrite an accepted stop or target.',
        '4. **Cold recovery cannot restore setup consumption.** A matching checkpoint preserves the current state, but signals carry no setup/attempt identity and the strategy has no order-adoption callback. A reconstructed strategy can propose a previously traded H1 setup after that position has closed. Broker portfolio reconciliation prevents concurrent duplicates, but it does not provide durable one-trade-per-setup history.',
        '5. **Stop selection and H4 refresh need explicit documentation.** The audit confirms that a newer opposite pivot after the broken swing is ignored for the stop, and same-direction H4 refresh clears an H1 confirmation. These are coherent possible rule choices, but changing either is a new strategy hypothesis that needs its own comparison.',
        'The ten deterministic audit cases also confirm delayed fractal availability, strict H4/H1/M5 timing, BUY/SELL symmetry, and next-bar market execution with the locked target. They intentionally reproduce limitations as well as correct behavior. Passing this audit is not a certificate that all strategy choices are sound.',
        'The pending-order bid-touch issue discussed for EmaFib is not active in this market-entry configuration. Failed2 market mode no longer emits CANCEL signals. FVG mode and unused alternative filters are outside this review.',
        '## Observed events in the long replay'])
    lines=['| Source | Signals | Accepted | Occupied-slot signals | Accepted without fresh cross | Signals with break before H1 |',
           '|---|---:|---:|---:|---:|---:|']
    for src in SOURCES:
        a=indexed[(src,'current','2020_2025')]['audit']
        lines.append('| '+src+' | '+' | '.join(str(a.get(k,0)) for k in ('signals','accepted','signal_while_occupied','accepted_without_fresh_cross','selected_swing_broken_before_h1_confirmation'))+' |')
    sections.extend(['\n'.join(lines),
        'Counts can overlap. Accepted orders can remain open at a period boundary; closed-trade statistics exclude that exposure.',
        '## Diagnostic fresh-cross comparison',
        'This research-only variant adds one condition: the previous close must not already be beyond the selected swing. It holds all numeric parameters and other rules fixed. It is not an optimized configuration or a production change. It permits a later re-cross of an older swing; it does not enforce a first-ever break after H1.',
        table([(f'{src}, {v}',indexed[(src,v,'2020_2025')]['metrics']) for src in SOURCES for v in ('current','fresh_cross')]),
        table([(f'{src}, {v}, 2026',indexed[(src,v,'2026_to_july14')]['metrics']) for src in SOURCES for v in ('current','fresh_cross')]),
        '## Spread stress',
        'Full replays use 1, 2, and 5 index points of spread. Index commission remains zero, matching the supplied broker history. Spread stress does not model every form of slippage or financing.',
        table([(f'{src}, {label}',indexed[(src,'current',label)]['metrics']) for src in SOURCES for label in ('2020_2025','spread_2','spread_5')]),
        '## Calendar years and direction',
        table([(f'{src}, {y}',m) for src in SOURCES for y,m in indexed[(src,'current','2020_2025')]['years'].items()]),
        table([(f'{src}, {d}',m) for src in SOURCES for d,m in indexed[(src,'current','2020_2025')]['directions'].items()])])
    holding=[]
    financing=[]
    for src in SOURCES:
        ts=read(f'{src}_current_2020_2025_trades.json')
        holding.append(dict(source=src,median_hold_hours=median(t['duration_hours'] for t in ts),
            max_hold_hours=max(t['duration_hours'] for t in ts),
            median_fill_rr=median(abs(t['tp']-t['entry_price'])/abs(t['entry_price']-t['sl']) for t in ts)))
        for rate in (0,3,7):
            adjusted=deepcopy(ts)
            for t in adjusted:
                t['net_r']-=rate*t['lot_size']*t['duration_hours']/24/t['initial_risk']
            financing.append(dict(source=src,debit_usd_per_lot_day=rate,metrics=metrics(adjusted)))
    write_json(OUT/'holding.json',holding)
    write_json(OUT/'financing_sensitivity.json',financing)
    sections.extend(['## Holding duration',
        'Typical holds are short, but the tails are substantial. Broker median holding time is 3.05 hours and its longest trade lasts 701.8 hours (29.2 days). Dukascopy and HistData medians are about four hours, with maximum holds of 1,565.5 hours (65.2 days). Median entry reward/risk is about 3.92 rather than the signal-price target of 4. Long holds make financing and weekend gaps relevant even though many trades close the same day.',
        '## Illustrative financing sensitivity',
        'This subtracts a hypothetical $0, $3, or $7 per lot per 24 hours held from existing paths. It is not a reconstruction of actual broker swap, and does not model credits, triple-swap days, changed sizing, or changed trade paths.',
        table([(f"{r['source']}, ${r['debit_usd_per_lot_day']}/lot/day",r['metrics']) for r in financing]),
        '## Copied DEMO history',
        f"The supplied 18 September broker export contains {demo['trades']} closed Failed2 positions, {demo['wins']} win, and ${demo['net_pnl']:,.2f} net P&L. Monetary PF is {demo['profit_factor_money']:.2f}. Swap totals ${demo['total_swap']:,.2f}; commission is zero. All eight tickets match market-order journal records despite truncated broker comments. Seven losses follow the first winner. This is a small, weak forward sample, not current-code validation.",
        'Ticket 1927396897 opened on Friday 11 September at 29,461.9, with reported SL 29,342.7 and 1.1 lots. It closed early Monday at 29,070.5. Net loss was $452.70 including $22.16 swap, about 3.45 times the $131.12 risk implied by the reported SL. The price gap therefore matters more than ordinary spread for this example. The strategy has no time-based exit, and its positions can remain open over weekends.',
        f"The copied journal records {demo['event_counts']}. Rejections: {demo['rejection_reasons']}. Its 106 cancellation requests belong to earlier market-mode code; the current implementation suppresses those signals. The journal is partial and mixes historical versions, settings, risk, restarts, and portfolio conditions. It cannot reconcile one-for-one with the isolated current-parameter replay.",
        '## Data and method',
        f"Completed {complete['replays']} sequential replays and {complete['controls']} plain-versus-observed controls. Every control matches all trade fields and ending exposure. Source and code hashes are saved; code hashes stayed unchanged during the run. All 172 existing unit tests pass, and ten separate deterministic audit cases reproduce the findings.",
        'All sources use M5 execution and completed H1/H4/D1 bars, a $10,000 initial balance, 0.5% risk, one open position for this strategy, a one-point default spread, and zero index commission. The same DEMO parameters are applied to USA100 aliases and USTEC with one-point pip size and $1 per point per lot. HistData passes the provenance-enforcing loader. The newer full broker H4 export is selected explicitly rather than merged with the superseded shorter export.',
        'The main period is 2020 through 2025; recent performance ends on 14 July 2026. No price bars after that cutoff enter research decisions. News, shared-account position limits and daily-loss gates, variable spreads, extra slippage, and actual swap are excluded. MT5 operation was not tested on this PC. R drawdown is closed-trade drawdown, not floating account-equity drawdown.',
        f"Across 2020 through 14 July 2026, {data['comparison'][0]['identical_pct']:.2f}% of shared Dukascopy/HistData M5 candles have identical OHLC. HistData lacks {data['comparison'][0]['duka_times_missing_other']:,} M5 timestamps found in Dukascopy. It is useful comparable data, but does not establish an independent feed. Broker prices differ, and its H4/D1 session boundaries have no exact opening-time matches with UTC-aligned Dukascopy bars. Those comparisons include both price-feed and candle-boundary differences.",
        '## Period-end exposure',
        '\n'.join(f"- {r['source']} {r['variant']} {r['label']}: {len(r['open_exposure'])} open/pending" for r in rows if r['open_exposure']) or 'All replays ended flat.',
        'Positions are not force-closed with future data; their eventual outcomes do not enter the reported closed-trade totals.',
        '## Reproduction',
        '```powershell\n.venv\\Scripts\\python.exe research_failed2_review.py\n.venv\\Scripts\\python.exe audit_failed2_logic.py\n.venv\\Scripts\\python.exe audit_failed2_demo.py\n.venv\\Scripts\\python.exe audit_failed2_data.py\n.venv\\Scripts\\python.exe audit_failed2_restart.py\n.venv\\Scripts\\python.exe summarize_failed2_review.py\n```',
        'Detailed trades, examples, fold results, source coverage, hashes, and copied DEMO evidence are under `output/failed2_review_20260928/`.'])
    path=ROOT/'strategy_log/failed2_review_20260928.md'
    path.write_text('\n\n'.join(sections)+'\n',encoding='utf-8')
    print(path)


if __name__=='__main__':
    main()
