"""Build the Candle Confirmation USDJPY review from saved, verified replays."""
from datetime import datetime
import json

from data.histdata_provenance import file_hash, write_json
from research_candle_usdjpy_review import ROOT, OUT, SOURCES
from research_ema_fib_review import metrics
from summarize_ema_fib_tracking import table


def read(name):
    return json.loads((OUT/name).read_text())


def main():
    manifest=read('manifest.json')
    assert all(file_hash(ROOT/p)==h for p,h in manifest['code_hashes'].items())
    assert read('complete.json') == dict(replays=8, controls=3, hashes_match=True)
    assert read('followup_complete.json') == dict(replays=4, hashes_match=True)
    initial, followups=read('results.json'),read('followup_results.json')
    indexed={(r['source'],r['variant'],r['spread_pips']):r for r in initial+followups}
    evidence=read('denominator_and_feed_audit.json')
    demo=read('demo_evidence.json')
    rows=[(f'{source} {variant}',indexed[source,variant,.2]['metrics'])
          for source in SOURCES for variant in ('current','fresh_cross')]
    chronological={}
    for source in SOURCES:
        for variant in ('current','fresh_cross'):
            ts=read(f'{source}_{variant}_spread0.2_trades.json')
            selected=[t for t in ts if any(f'{y}-07-01'<=t['open_time'] and t['close_time']<f'{y+2}-07-01'
                for y in (2020,2022,2024))]
            chronological[f'{source} {variant}']=metrics(selected)
    write_json(OUT/'summary.json',dict(chronological=chronological,
        decision='Recommend pause CandleConfirmation_USDJPY_H1_M5 from DEMO. No config change made.',
        observed_controls=read('controls.json'), scenarios=12,controls=3))
    lines=['# Candle Confirmation USDJPY review, 2026-09-30','',
        'Recommend pausing `CandleConfirmation_USDJPY_H1_M5` from new DEMO runs. The setup idea is coherent, '
        'but current costs and broker evidence do not establish a dependable edge. A fresh-break requirement improves '
        'the full-history figures without establishing a robust replacement. GBPUSD was not reviewed here. '
        'No production code, DEMO membership, parameters, risk, or trading-host state was changed.','',
        '## Current executable rules','',
        'Daily EMA20 must be above EMA50 for BUY, below it for SELL, with separation of at least 0.05%. '
        'A completed H1 candle must close outside the previous H1 body, have a range of at least 8 pips, '
        'and have a body covering at least half its own range. This is a close-through-body rule; it does not '
        'require the current body to engulf the entire previous body or require matching candle color.','',
        'The strategy waits for M5 price to touch the H1 midpoint, then requires a close beyond a confirmed '
        'five-candle fractal and an FVG somewhere in the selected breaking leg. The BUY target is the H1 low '
        'plus 1.25 times its range, or one-quarter of the range beyond the H1 high. SELL mirrors this. '
        'The stop is calculated from the signal close to produce 1.5R, rather than anchored to structure. '
        'The minimum proposed stop is 8 pips. Filled trades run to their fixed SL/TP. All UTC hours are allowed.','',
        'The pre-entry expiration rule is intentional in the existing code: BUY expires when the engulf high '
        'is reached, SELL when the engulf low is reached. It prevents chasing after the original range edge '
        'has already traded. It does not invalidate BUY below the engulf low or SELL above the engulf high. '
        'Adding opposite-extreme invalidation would be a separate strategy change requiring its own validation.','',
        '## Performance with current execution','',
        'Common requested period July 1, 2016 through July 14, 2026. Each source retains its real coverage. '
        'Net R includes a fixed 0.2-pip spread and $7/lot round-trip commission. Each replay is a standalone '
        '$10,000 USD account with planned risk of 0.5% per trade. Market entries fill at the next M5 open; '
        'BUY pays ask and SELL stops/targets use ask. OHLC ambiguity is stop-first. No swaps, variable spreads, '
        'extra slippage, news gate, shared portfolio capacity, or daily-loss gate are modeled. No forced final '
        'liquidation occurs; all these completed cases end without open exposure.','',table(rows),'',
        'Fresh-cross changes only the entry rule: the immediately previous M5 close must remain on the unbroken '
        'side of the chosen fractal. It keeps all current parameters. It is a research hypothesis, not enabled code.','',
        '### 2020-2025 and January-July 2026','']
    for window in ('2020_2025','2026_to_july14'):
        lines += [window.replace('_',' '),'',table([(f'{source} {variant}',indexed[source,variant,.2]['windows'][window])
            for source in SOURCES for variant in ('current','fresh_cross')]),'']
    lines += ['## R denominator and account growth','',
        'Production net R divides P/L by the risk at the actual filled stop distance. A favorable entry gap can '
        'shrink this denominator even though the position was sized against a much larger intended risk. '
        'Therefore summed filled-stop R can overstate the relationship to account growth.','',
        'Dukascopy has a SELL on April 3, 2023 at 21:00 UTC with entry 132.439 and SL 132.446333. '
        'Its filled stop is only 0.73 pip, despite the 8-pip proposal minimum. The previous M5 close was 132.360. '
        'The $116.02 profit becomes +27.21 net R when divided by $4.26 actual stop risk. Relative to the original '
        'planned 0.5% account budget, it is about +2.29R. The same trade appears in the fresh-cross case. '
        'This is a denominator/entry-gap issue; it is not evidence of a 27-fold return on planned account risk.','',
        '| Case | Filled-stop net R | Planned-budget R | Closed account growth | Marked-to-market DD % |',
        '|---|---:|---:|---:|---:|']
    for source in SOURCES:
        for variant in ('current','fresh_cross'):
            r=indexed[source,variant,.2]
            b=evidence['planned_risk'][f'{source}_{variant}_spread0.2']
            lines += [f"| {source} {variant} | {r['metrics']['total_r']:+.2f} | {b['total_planned_r']:+.2f} | "
                      f"{b['closed_growth_pct']:+.2f}% | {r['max_equity_drawdown_pct']:.2f}% |"]
    lines += ['',
        'The planned-budget denominator is 0.5% of account balance before order acceptance. Positions do not '
        'overlap, and no realized P/L changes that balance between acceptance and fill. These are standalone '
        'compounded simulations, not the actual multi-strategy demo account.','',
        'A separate full replay rejects market fills whose actual SL distance falls below 8 pips, releases the '
        'proposal through the normal engine callback, and continues trading. This avoids deleting a selected '
        'winner after the fact. It reduces current Dukascopy to +7.98R, PF 1.02, versus +32.60R without that '
        'fill guard. Broker remains negative at -5.89R. The minimum fill distance is a validation recommendation, '
        'not an optimized filter or a production change.','',
        table([(f'{source} minimum fill SL 8 pips',indexed[source,'min_fill_sl8',.2]['metrics'])
               for source in ('dukascopy','mt5_icmarkets_utc')]),'',
        '## Costs and execution sensitivity','',
        'At 0.2-pip spread, current broker price R before commission is +36.84R. Commission consumes 46.44R, '
        'leaving -9.59R. The fresh-cross version retains only +4.42R, PF 1.01, over 583 trades. '
        'Uniform 1- and 2-pip spreads are stress cases, not estimates of the actual historical average. '
        'They matter because entries are allowed during quiet hours and rollover.','',
        table([(f'Broker {variant}, spread {spread:g} pip',indexed['mt5_icmarkets_utc',variant,spread]['metrics'])
            for variant in ('current','fresh_cross') for spread in (.2,1.,2.)]),'',
        'Both variants fail with a 1-pip modeled spread. There is too little retained broker edge to absorb '
        'unmodeled swaps, spread spikes, or worse execution.','',
        '## Chronological diagnostics','',
        'Four-year training windows followed by two-year test windows, advancing two years. Strategies run '
        'continuously with fixed settings, not fresh-start optimization at each fold. Only trades opened and '
        'closed inside a window count; boundary-crossing exposure can still occupy a slot. Historical dates '
        'were already used in earlier research, so these are chronological diagnostics rather than untouched '
        'out-of-sample evidence. No parameters were selected from these test scores.','',
        '| Feed and rule | Jul 2020-Jun 2022 R | Jul 2022-Jun 2024 R | Jul 2024-Jun 2026 R |',
        '|---|---:|---:|---:|']
    for source in SOURCES:
        for variant in ('current','fresh_cross'):
            r=indexed[source,variant,.2]
            lines += [f'| {source} {variant} | ' + ' | '.join(f"{r['windows'][f'fold_{y}_test']['total_r']:+.2f}"
                for y in (2020,2022,2024)) + ' |']
    lines += ['', 'Combined non-overlapping test windows.','',table(list(chronological.items())),'',
        'The current broker test windows total -15.33R; fresh-cross totals -5.64R. The 2022-2024 broker '
        'window is negative for both, and current settings also lose in 2024-2026. These findings do not '
        'support carrying forward the older MODERATE label as validation of current executable behavior.','',
        'Detailed training/test metrics and expectancy retention:','',
        '| Feed and rule | Split | Train R | Test R | Expectancy retention | Verdict |',
        '|---|---:|---:|---:|---:|---|']
    for source in SOURCES:
        for variant in ('current','fresh_cross'):
            r=indexed[source,variant,.2]
            for y in (2020,2022,2024):
                train,test=r['windows'][f'fold_{y}_train'],r['windows'][f'fold_{y}_test']
                retention=100*test['expectancy']/train['expectancy'] if train['expectancy']>0 else None
                verdict='FAIL' if test['total_r']<=0 else 'UNDEFINED' if retention is None else (
                    'STRONG' if retention>=70 else 'MODERATE' if retention>=40 else 'WEAK')
                text='n/a' if retention is None else f'{retention:.1f}%'
                lines += [f"| {source} {variant} | {y} | {train['total_r']:+.2f} | {test['total_r']:+.2f} | {text} | {verdict} |"]
    lines += ['', '## Signal logic and tracking audit','',
        'Completed bars drive the strategy in chronological close-time order. All signal fractals have their '
        'right wing confirmed before the signal candle. Recorded M5 context begins after H1 confirmation. '
        'I found no future-bar use in the active signal path. The proposed symmetric SL/TP has 1.5R; '
        'risk and execution enforce the global minimum 1.0R at submission and modeled fill.','',
        '- The structure-break test checks whether the current close is beyond a confirmed pivot. It does not '
        'require a fresh cross. On broker data, 140 of 641 current signals have a previous close already beyond '
        'the selected pivot. A reproduced example waits until a later FVG appears after the initial break. '
        'This differs from a strict "enter on the break" interpretation, but the fresh-cross alternative fails '
        'to establish a robust edge.',
        '- Broker data produces 283 of 641 proposals after the opposite H1 extreme has been breached. '
        'The current code allows this intentionally; structural stops are not used. This rule should be '
        'made explicit before considering an opposite-extreme filter. That filter was not tested here.',
        '- Ordinary accepted trades freeze H1 bias changes through `_signal_fired`. No close-to-different-origin '
        'event occurred in the uninterrupted replays. Rejected unsubmitted proposals correctly release that '
        'flag. However, the strategy has no setup/attempt identity or broker synchronization callback. '
        'A recovered earlier trade close can clear a newer warmed-up bias by symbol; the synthetic reproduction '
        'confirms it. Durable attribution should be added before any future reactivation.',
        '- Cold startup, including the current full suite, requests only 50 D1, 100 H1, and 250 M5 bars for '
        'USDJPY. EMA50 begins from its seed with no settling history; the M5 history covers about 21 hours '
        'against 100 H1 hours. Specify longer D1 settling history and enough M5 history to reconstruct the '
        'same H1 span. This review uses 180 calendar days of warmup and does not validate cold-start equivalence.',
        '- The 8-pip minimum applies to the proposal, while a gap can reduce the actual filled distance below it. '
        'Apply the chosen minimum to the final executable quote and to deferred simulated market fills before '
        'relying on the same policy in both paths. Keep price/filled-risk R, planned-budget R, and account growth '
        'separate in performance reports.','',
        '## Data limits','',
        'All three USDJPY M5/H1/D1 streams are available locally. Broker D1 session boundaries differ from '
        'UTC-midnight proxy D1 bars, so daily trend signals need not match. HistData inputs pass the existing '
        'hash-bound UTC provenance validation; no clocks or prices were changed for this review.','',
        'Dukascopy and HistData have almost identical OHLC at more than 99.9% of matching M5 timestamps from '
        '2019 onward. They should not be called independent confirmation. HistData has substantially fewer '
        'M5 bars during February-July 2023. For example, April has 3,948 HistData bars versus 5,792 Dukascopy '
        'and 5,778 broker bars. The HistData sidecar excludes only eight M5 candles for known conflicts, '
        'so those exclusions do not explain the larger provider gaps. Do not invent candles or treat the '
        'full-sample feeds as identical coverage. The saved monthly coverage table records this limitation. '
        'Investigating or reacquiring those months may improve the comparison, but does not repair the '
        'independent broker failure found here.','',
        'The older May walk-forward and August broker replay used earlier execution revisions and different '
        'date bounds. Their published +54.0R fixed OOS and +0.05R broker net totals are historical records, '
        'not exact controls for this run. The current review freezes code/data hashes and verifies its own '
        'instrumented runs against uninstrumented production.','',
        '## Copied DEMO results','',
        'The MT5 position export contains 12 USDJPY Candle Confirmation trades, August 3 through September 15, '
        '2026: six wins, +$136.89 net including commission/swap, money profit factor 1.22, closed-money drawdown '
        '$319.48, and maximum winning/losing streaks of three. All 12 tickets match journal closes, and their '
        'journal P/L reconciles to broker net P/L within rounding. Actual target R:R ranges from 1.44 to 1.53. '
        'The sample is positive but too small to establish the strategy edge.','',
        'The journal also contains five execution failures. Two have explicit invalid-comment errors, and '
        'older log lines document the same issue. Current execution already has comment sanitization; this '
        'review does not label those older failures as current strategy defects. Report comments are shortened '
        'and are attributed by symbol plus exact journal ticket matches. The copied files predate the '
        'September 18 restart and represent older runtime versions. No trading-host access occurred.','',
        '## Decision and verification','',
        'Pause this USDJPY variant from new DEMO runs. Preserve it as research code. Before reconsidering it, '
        'correct durable setup/order attribution, warmup reconstruction, final-fill stop-distance validation, '
        'and the performance denominator. Then rerun fixed settings before further parameter searches. '
        'Keep the fresh-cross option as a research hypothesis; its broker PF of 1.01 and negative combined '
        'later windows are not enough to enable it. GBPUSD needs its own review.','',
        'Completed 12 sequential research scenarios and three exact production controls. Every saved trade '
        'field and ending exposure match in all three controls. The existing core-design suite passes all '
        '40 tests, including five Candle Confirmation tests. Synthetic reproductions cover stale breaks, '
        'opposite-extreme behavior, rejection release, and recovered-close attribution. Code, inputs, and '
        'HistData metadata hashes match their recorded manifests. Scripts and detailed evidence are under '
        '`output/candle_usdjpy_review_20260930/`. Recommendations are not implemented in production.','']
    report=ROOT/'strategy_log/candle_usdjpy_review_20260930.md'
    report.write_text('\n'.join(lines),encoding='utf-8')
    write_json(OUT/'review_complete.json',dict(scenarios=12,exact_controls=3,core_tests=40,
        report_sha256=file_hash(report),analysis_code_hashes={p:file_hash(ROOT/p) for p in (
            'audit_candle_usdjpy_review.py','inspect_candle_usdjpy_evidence.py',
            'research_candle_usdjpy_followups.py','summarize_candle_usdjpy_review.py')}))
    print(json.dumps(chronological,indent=2))


if __name__=='__main__':
    main()
