"""Validate GBP research artifacts and write a reproducible review."""
import json
from pathlib import Path
from data.histdata_provenance import file_hash,write_json

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/candle_gbpusd_review_20260930'
FEEDS={'dukascopy':'Dukascopy','histdata':'HistData','mt5_icmarkets_utc':'IC Markets'}
VERSIONS={'original':'before fill guard','current':'current corrected','fresh_cross':'fresh crossing only',
          'opposite_extreme':'expire opposite extreme'}


def read(name):
    return json.loads((OUT/name).read_text())


def metric_row(label,m):
    return (f"| {label} | {m['trades']} | {m['win_rate']:.2f} | {m['total_r']:+.2f} | "
            f"{m['profit_factor']:.3f} | {m['expectancy']:+.4f} | {m['max_dd_r']:.2f} | "
            f"{m['max_win_streak']}/{m['max_loss_streak']} |")


def table(title):
    return ['',title,'',
        '| Case | Trades | Win % | Net R | PF | R/trade | Closed DD R | Win/loss streak |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']


def main():
    manifest,results=read('manifest.json'),read('results.json')
    complete=read('complete.json')
    assert complete==dict(research_replays=21,controls=6,hashes_match=True)
    assert len(read('controls.json'))==6 and all(c['all_fields_match'] for c in read('controls.json'))
    assert all(file_hash(ROOT/p)==h for p,h in manifest['code_hashes'].items())
    assert all(file_hash(p)==h for p,h in manifest['input_hashes'].items())
    assert all(file_hash(p)==h for p,h in manifest['metadata_hashes'].items())
    demo,feed,detail=read('demo_evidence.json'),read('feed_audit.json'),read('trade_details.json')
    assert all(file_hash(p)==h for p,h in demo['input_hashes'].items())
    assert not demo['unmatched_report'] and not demo['unmatched_journal']
    assert len(demo['matches'])==demo['summary']['trades']==5
    assert all(abs(x['difference'])<.011 for x in demo['matches'])
    def get(source='mt5_icmarkets_utc',variant='current',spread=.2):
        return next(r for r in results if r['source']==source and r['variant']==variant and r['spread_pips']==spread)
    for r in results:
        name=f"{r['source']}_{r['variant']}_spread{r['spread_pips']:g}"
        ts,contexts=read(name+'_trades.json'),read(name+'_contexts.json')
        assert len(ts)==r['metrics']['trades']
        assert len(ts)+sum(r['rejected'].values())+len(r['final_exposure'])==len(contexts)
        if r['variant'] not in ('original','tracking_only'):
            by_attempt={x['attempt_id']:x for x in contexts}
            assert len(by_attempt)==len(contexts)
            for t in ts:
                assert by_attempt[t['attempt_id']]['setup_id']==t['setup_id']
                assert abs(t['entry_price']-t['sl'])/.0001+1e-8>=8
                assert abs(t['tp']-t['entry_price'])/abs(t['entry_price']-t['sl'])+1e-8>=1
    b=get()
    lines=['# Candle Confirmation GBPUSD review, 2026-09-30','',
        'The shared strategy now tracks orders and validates executable stops correctly. '
        'Its GBPUSD rules are reproducible and use completed bars, but the current broker edge '
        'is too thin to treat as robust. I recommend pausing new GBPUSD DEMO entries and keeping '
        'this implementation for further research. This review makes no membership or parameter change.','',
        '## Current candidate and meaning','',
        '- H1 establishes directional bias when its close breaks the preceding candle body.',
        '- M5 waits for a 50% retracement, a confirmed swing with three bars on each side, '
        'and a three-candle price gap somewhere in the selected leg.',
        '- Daily EMA20/50 must agree with direction and be separated by at least 0.1%. '
        'H1 range must be at least eight pips, and body at least 60% of its full range.',
        '- TP is at 150% of the H1 range from its opposite extreme. Symmetric SL is derived '
        'from the target distance for 2:1 proposed R:R. It is not necessarily beyond a structural swing.',
        '- Minimum proposed and executable stop is eight pips. All UTC entry hours are allowed. '
        'Engulf candle color is not required. Global planned account risk is 0.5%.','',
        'The name does not imply a textbook full-body engulf. A close beyond the previous body is '
        'enough even if the new open does not wrap the body, and color can differ after a gap. '
        'A BUY setup expires when price touches its H1 high before entry; SELL expires at its low. '
        'It can survive crossing the opposite extreme. In practice this often makes it a trend-following '
        'recovery pattern after a sweep through the range, rather than an entry contained within that range.','',
        'The code may enter on a later close beyond an already-broken swing if the earlier crossing '
        'did not satisfy the gap requirement. This is consistent with the present rule, but differs '
        'from requiring a new crossing on the entry candle. Both interpretations were tested separately.','',
        '## Correctness checks','',
        'The confirmed fractal uses completed right-wing bars before the entry candle. Higher '
        'timeframe candles are dispatched at their close, and market fills occur at the next M5 '
        'open using bid/ask conventions. Reproductions and accepted-context checks found no future-bar use. '
        'Filled trades retain their originating H1 setup and attempt ID. Old closures, partial fills, '
        'rejected fills, and restart recovery use the shared lifecycle corrections from the USDJPY work.','',
        'Warmup requests 250 D1, 100 H1, and 1,200 M5 completed bars. Each reviewed feed has '
        'at least these counts before January 2017. Every corrected filled trade has at least an '
        'eight-pip stop and 1:1 filled R:R. Tracking alone matches every economic field of the '
        'frozen pre-tracking class on all three feeds. The observation wrapper exactly matches '
        'plain production trades and end exposure on all three feeds.','',
        'The final MT5 quote is checked before submission. A reported fill is checked after '
        'acknowledgement; slippage can still violate the minimum after the order is real. Those '
        'positions remain tracked and violations are logged. Missing actual fill prices are unknown. '
        'No MT5 connection was attempted in this review.','',
        '## Matched current performance','',
        'January 1, 2017 through July 14, 2026, after the same completed 2016 warmup. '
        'The period matches the corrected USDJPY baseline. Prices after the research cutoff '
        'are excluded from replay and parameter decisions. This is standalone replay, with a '
        '0.2-pip spread, configured round-trip commission, and 0.5% planned risk. '
        'No news filter, competing strategies, or daily-loss cap is applied. '
        'Swap and actual tick slippage are not modeled. Open exposure is never forcibly closed.']
    lines+=table('Current corrected settings across feeds')
    for src in FEEDS:
        lines.append(metric_row(FEEDS[src],get(src)['metrics']))
    lines+=['','| Feed | Planned-budget R | Account growth | Equity DD | Minimum filled stop |',
        '|---|---:|---:|---:|---:|']
    for src in FEEDS:
        r=get(src)
        lines.append(f"| {FEEDS[src]} | {r['budget_metrics']['total_r']:+.2f} | {r['growth_pct']:+.2f}% | "
                     f"{r['equity_dd_pct']:.2f}% | {r['minimum_filled_stop_pips']:.2f} pips |")
    lines+=['','Net R uses actual filled entry-to-stop risk, including spread and commission. '
        'Planned-budget R uses 0.5% of standalone balance for that trade and reconciles to ending '
        'balance. Closed R drawdown and marked-to-market percentage drawdown use different units. '
        'The broker return is small compared with its drawdown, despite the positive final total.']
    lines+=table('Effect of the executable stop guard')
    for src in FEEDS:
        for variant in ('original','current'):
            lines.append(metric_row(FEEDS[src]+' / '+VERSIONS[variant],get(src,variant)['metrics']))
    lines+=['','The guard rejects one undersized fill on Dukascopy and three on HistData. '
        'Later decisions can change after a rejection, so the corrected result is a full replay. '
        'No current-baseline broker fill breaches eight pips; its results are unchanged by the guard. '
        'These controls use today\'s shared simulator with frozen earlier signal logic. They do not '
        'reproduce every simulator version used by the May or August reports.']
    lines+=table('Isolated rule experiments, 0.2-pip spread')
    for src in FEEDS:
        for variant in ('current','fresh_cross','opposite_extreme'):
            lines.append(metric_row(FEEDS[src]+' / '+VERSIONS[variant],get(src,variant)['metrics']))
    lines+=['','Fresh crossing reduces the full-period total on all three feeds and makes the broker '
        'result negative. Expiring at the opposite engulf extreme removes much of the positive '
        'recovery contribution and also fails. Neither experiment is a validated replacement. '
        'The rules were tested individually, never combined or promoted to production.']
    lines+=table('Broker spread stress, full history')
    for spread in (.2,1.,2.):
        for variant in ('current','fresh_cross','opposite_extreme'):
            lines.append(metric_row(f'{spread:g} pips / '+VERSIONS[variant],get(variant=variant,spread=spread)['metrics']))
    lines+=['','These are constant-spread stress scenarios, not measured historical spreads. '
        'They replay fills, stop/target hits, and subsequent decisions at the wider spread. '
        'At one pip, current settings lose -20.53R; at two pips, -41.10R. '
        'All three rule interpretations fail the wider-spread scenarios.']
    lines+=table('Broker chronological checks with current settings')
    for y in (2020,2022,2024):
        lines.append(metric_row(f'July {y}-June {y+2}',b['windows'][f'fold_{y}_test']))
    lines.append(metric_row('Combined July 2020-June 2026',b['later_tests']))
    lines.append(metric_row('Calendar 2020-2025',b['windows']['2020_2025']))
    lines.append(metric_row('January-July 14, 2026',b['windows']['2026_to_july14']))
    lines+=['','These are later historical windows from continuous replay, not a new optimized '
        'walk-forward study or untouched holdout. No parameter selection occurs in this review. '
        'Training subdivisions start in January 2017 for the first window and span four years '
        'thereafter. Earlier training totals are negative, so a simple retention ratio is not '
        'a useful validation grade. The old MODERATE label and +41.4R fixed-candidate OOS figure '
        'refer to earlier evidence and do not establish robustness under today\'s broker/cost model.']
    lines+=table('Broker direction comparison, current settings')
    for direction,m in b['directions'].items():
        lines.append(metric_row(direction,m))
    groups=detail['details']['mt5_icmarkets_utc_current_spread0.2']['groups']
    lines+=table('Descriptive broker setup groups, current settings')
    for key in ('fresh_cross_true','fresh_cross_false','opposite_extreme_breached_true','opposite_extreme_breached_false'):
        lines.append(metric_row(key.replace('_',' '),groups[key]))
    lines+=['','Broker signals include 60 later crossings out of 397 and 181 setups whose opposite '
        'extreme had been breached. The recovery group contributes +28.61R, while the group '
        'without that breach contributes -23.66R. This is a useful research lead, not an '
        'already-tested recovery-only strategy. Selecting a subgroup changes later setup '
        'opportunities; deleting other trades is not a substitute for replay. BUY-only also '
        'remains a descriptive split, not an optimized or validated direction filter.','',
        '## Data and deployment limitations','',
        'Verified HistData sidecars and source/input hashes passed the loader and completion checks. '
        'HistData is positive here, with 399 trades and +16.84R, but weaker than Dukascopy\'s +27.82R. '
        'Prices on matching M5 timestamps are more than 99.94% identical in every year from '
        '2019 onward. It is not independent feed confirmation. Earlier 2017-2018 prices differ.','',
        'HistData has provider gaps from February through July 2023. April contains 3,924 M5 '
        'bars versus 5,796 Dukascopy and 5,778 broker. Only five resampled M5 candles are '
        'excluded by the known-conflict policy across the entire converted file, which cannot '
        'explain those large gaps. No prices, clocks, or missing rows were changed for this review.','',
        'Daily candle boundaries differ. Dukascopy/HistData are aligned to UTC midnight; '
        'broker D1 sessions start at 21:00 or 22:00 UTC. The loader preserves genuine broker '
        'Sunday-stamped Monday sessions. Thus the D1 trend gate can differ even when M5 prices '
        'are similar. A common-session D1 comparison would be a separate controlled experiment.','',
        'The broker baseline has 112 trades spanning a UTC date change and a maximum holding '
        'time of 130 hours. This is an overnight proxy rather than a precise count of swap '
        'charges. Historical swap can materially change a result this close to break-even. '
        'Full-suite limits, correlated USD exposure, and varying spread/slippage also remain '
        'outside the standalone result.','',
        '## Copied DEMO evidence','',
        'Five closed GBPUSD trades from July 28 through September 17, 2026 show one win, '
        'net -$354.15 after commission/swap, money PF 0.408, closed money drawdown $354.15, '
        'and a longest loss streak of two. All five tickets and net profits match the journal. '
        'Broker report times remain wall time rather than being guessed into UTC.','',
        'The journal records 11 signals, five submitted orders, and six execution rejections '
        'from May-July. Two journal diagnostics and two corresponding log entries explicitly '
        'show invalid broker-comment arguments; the remaining two failures have incomplete '
        'diagnostics. Current MT5 code already uses shortened comments and durable submission '
        'identities. These older failures are not new defects introduced by tracking.','',
        'The copied history precedes the September 18 restart and the present local corrections. '
        'It mixes older versions and sizing and contains too few trades to establish or refute '
        'the corrected edge. It is forward evidence after the historical research cutoff and '
        'was not used to choose the tested hypotheses.','',
        '## Recommendation','',
        'Retain the shared tracking, warmup, and executable-stop corrections. They make this '
        'strategy suitable for controlled research, but its existing GBPUSD settings have '
        'too little broker margin to justify calling the edge robust. I recommend pausing '
        'new GBPUSD DEMO entries while investigating a more specific hypothesis. No production '
        'membership, risk, symbols, parameters, or host state changed in this analysis.','',
        'The strongest lead is an explicit recovery after the opposite engulf extreme is '
        'crossed. Test that as one predeclared logic change, compare it with the current '
        'control, and select any parameters using training data only. Require stability in '
        'later periods and broker costs, rather than optimizing the full-period subgroup. '
        'Do not enable the fresh-cross or opposite-extreme-expiry variants from this review.','',
        'Before a further DEMO decision, gather current GBPUSD spreads during the actual entry '
        'hours, including rollover, and review new fill/stop diagnostics and broker swap. '
        'On the Windows trading host, the existing read-only monitor can be run in several '
        'sessions with `python measure_spreads.py --symbols GBPUSD --duration 300 --interval 0.5`. '
        'A five-minute snapshot alone is not a historical spread model.','',
        '## Verification and artifacts','',
        'All 228 repository tests pass. Completed 21 sequential research cases plus three '
        'additional plain-production replays. Six exact comparisons verify original versus '
        'tracking and production versus observer across all three feeds. Source/CSV/sidecar '
        'hashes, accepted/closed/rejected counts, attribution, fractal chronology, actual stop '
        'distance, and filled R:R are audited.','',
        'Frozen inputs, settings, results by year/window/direction, contexts, trade lists, '
        'feed audits, synthetic rule reproductions, and copied DEMO reconciliation are under '
        '`output/candle_gbpusd_review_20260930/`. Main scripts are '
        '`research_candle_gbpusd_review.py`, `audit_candle_gbpusd_review.py`, and '
        '`summarize_candle_gbpusd_review.py`. The research runner refuses to overwrite an '
        'existing manifest. No MT5 terminal access is required for these replays.','']
    report=ROOT/'strategy_log/candle_gbpusd_review_20260930.md'
    report.write_text('\n'.join(lines),encoding='utf-8')
    write_json(OUT/'audit_complete.json',dict(research_cases=21,comparisons=6,hashes_verified=True,
        attribution_and_stop_checks=True,report_sha256=file_hash(report),
        analysis_code_hashes={p:file_hash(ROOT/p) for p in ('audit_candle_gbpusd_review.py','summarize_candle_gbpusd_review.py')}))
    print(str(report))


if __name__=='__main__':
    main()
