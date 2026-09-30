"""Verify complete sequential recovery replays and publish comparison tables."""
import json
from pathlib import Path

from data.histdata_provenance import file_hash, write_json
from research_ema_fib_review import metrics

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'output/candle_gbpusd_recovery_20260930'
LABELS = {'off': 'Current', 'touch': 'Recovery touch', 'inside': 'Recovery + inside close'}
FEEDS = {'dukascopy': 'Dukascopy', 'histdata': 'HistData', 'mt5_icmarkets_utc': 'IC Markets'}


def read(name):
    return json.loads((OUT/name).read_text())


def name(row):
    return f"{row['source']}_{row['policy']}_spread{row['spread_pips']:g}_{row['window']}"


def table(title):
    return ['', title, '',
        '| Case | Trades | Win % | Net R | PF | R/trade | Closed DD R | Win/loss streak |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']


def metric_row(label, m):
    return (f"| {label} | {m['trades']} | {m['win_rate']:.2f} | {m['total_r']:+.2f} | "
            f"{m['profit_factor']:.3f} | {m['expectancy']:+.4f} | {m['max_dd_r']:.2f} | "
            f"{m['max_win_streak']}/{m['max_loss_streak']} |")


def main():
    manifest, results, complete = read('manifest.json'), read('results.json'), read('complete.json')
    assert complete == dict(research_replays=24, baseline_controls=3, hashes_match=True)
    controls = read('controls.json')
    assert len(controls) == 3 and all(c['previous_trade_fields_match'] and c['plain_production_matches'] for c in controls)
    assert all(file_hash(ROOT/p) == h for p, h in manifest['code_hashes'].items())
    assert all(file_hash(p) == h for p, h in manifest['input_hashes'].items())
    assert all(file_hash(p) == h for p, h in manifest['metadata_hashes'].items())
    assert len(results) == 24
    def get(policy='off', source='mt5_icmarkets_utc', spread=.2, window='full'):
        return next(r for r in results if r['policy']==policy and r['source']==source
                    and r['spread_pips']==spread and r['window']==window)
    trade_sets = {}
    for r in results:
        ts, contexts = read(name(r)+'_trades.json'), read(name(r)+'_contexts.json')
        trade_sets[name(r)] = ts
        assert metrics(ts) == r['metrics']
        assert len(contexts) == len(ts)+sum(r['rejected'].values())+len(r['final_exposure'])
        by_attempt = {c['attempt_id']: c for c in contexts}
        assert len(by_attempt) == len(contexts)
        for t in ts:
            c = by_attempt[t['attempt_id']]
            assert c['setup_id'] == t['setup_id']
            assert abs(t['entry_price']-t['sl'])/.0001+1e-8 >= 8
            assert abs(t['tp']-t['entry_price'])/abs(t['entry_price']-t['sl'])+1e-8 >= 1
            if r['policy'] != 'off':
                assert c['context']['opposite_extreme_breached']
            if r['policy'] == 'inside':
                assert c['context']['close_back_inside_range']
    cold = {}
    for policy in LABELS:
        rows = [get(policy, window=f'cold_{y}') for y in (2020, 2022, 2024)]
        cold[policy] = dict(metrics=metrics([t for r in rows for t in trade_sets[name(r)]]),
            folds=[dict(window=r['window'], growth_pct=r['growth_pct'],
                        final_exposure=len(r['final_exposure']), warmup_bars=r['warmup_bars']) for r in rows])
    current = trade_sets[name(get())]
    recovery = trade_sets[name(get('touch'))]
    key = lambda t: (t['setup_id'], t['attempt_id'], t['open_time'], t['close_time'],
                     t['direction'], t['entry_price'], t['sl'], t['tp'])
    a, b = {key(t):t for t in current}, {key(t):t for t in recovery}
    overlap = dict(common=metrics([b[k] for k in a.keys() & b.keys()]),
                   current_only=metrics([a[k] for k in a.keys()-b.keys()]),
                   recovery_only=metrics([b[k] for k in b.keys()-a.keys()]))
    write_json(OUT/'summary.json', dict(cold=cold, broker_trade_overlap=overlap,
        controls=controls, replays=len(results), inputs_and_code_hashes_match=True))
    lines = ['# Candle Confirmation GBPUSD recovery study, 2026-09-30', '',
        'USDJPY Candle Confirmation is removed from new DEMO runs at the user’s request. '
        'GBPUSD remains enabled with the same parameters and 0.5% planned risk. '
        'Recovery-only remains an experiment. The simpler touch rule improves broker '
        'performance and drawdown, but fails wider-spread robustness and does not '
        'improve total R across all feeds. Returning inside the range makes results worse.', '',
        '## Rules tested', '',
        'Current is the existing corrected GBPUSD strategy. Recovery touch adds one gate: '
        'BUY needs a completed M5 low at or below the originating H1 low; SELL needs a '
        'completed M5 high at or above its H1 high. The touch can be on the signal bar. '
        'The usual confirmed swing break, FVG, daily trend, stop and target rules still apply. '
        'Recovery + inside close adds a second gate: the signal close must be strictly '
        'between the originating H1 low and high. Equality counts as a touch but not an inside close.', '',
        'The gate scans the same setup-specific entry buffer as the existing diagnostics '
        '(maximum 1,000 M5 bars). It is a recovery of local M5 structure after the touch; '
        'the touch-only version can signal while still outside the H1 range. It does not '
        'require a fresh crossing or change expiry at the target-side H1 extreme. '
        'Filtered detections leave the setup eligible and do not create or consume a proposal. '
        'Full sequential replays allow later opportunities and changed setup histories; '
        'these results are not obtained by deleting trades from the current trade list.', '',
        'Shared tracking, 250 D1 / 100 H1 / 1,200 M5 warmup requirements, next-open bid/ask '
        'market fills, eight-pip executable minimum stops, and at least 1:1 filled R:R remain active. '
        'GBP parameters remain fn=3, retracement=50%, target=150% of H1 range, symmetric '
        'proposed R:R=2, daily EMA20/50 separation=0.1%, H1 minimum range=8 pips, body=60%.', '',
        '## Full matched replays', '',
        'January 1, 2017 through July 14, 2026. Completed 2016 bars warm each feed; '
        'data after the cutoff is excluded. Standalone 0.5% planned risk, constant 0.2-pip '
        'spread and configured commission. No news filter, other strategies, daily-loss cap, '
        'swap or actual tick slippage. Open positions at the end are not forcibly closed.']
    for source, label in FEEDS.items():
        lines += table(label)
        for policy in LABELS:
            lines.append(metric_row(LABELS[policy], get(policy, source)['metrics']))
    lines += ['', '| Feed / rule | Budget R | Account growth | Equity DD | End exposure |',
              '|---|---:|---:|---:|---:|']
    for source, label in FEEDS.items():
        for policy in LABELS:
            r = get(policy, source)
            lines.append(f"| {label} / {LABELS[policy]} | {r['budget_metrics']['total_r']:+.2f} | "
                         f"{r['growth_pct']:+.2f}% | {r['equity_dd_pct']:.2f}% | {len(r['final_exposure'])} |")
    lines += ['', 'Net R uses simulated net P&L divided by modeled risk at the actual fill. '
        'Budget R uses net P&L divided by the planned 0.5% balance budget; lot rounding and '
        'fill differences mean account growth is not exactly net R × 0.5%. '
        'Closed drawdown in R and marked-to-market account drawdown are separate measures.']
    lines += table('IC Markets spread sensitivity, full period')
    for spread in (.2, 1., 2.):
        for policy in LABELS:
            lines.append(metric_row(f'{LABELS[policy]}, {spread:g} pip', get(policy, spread=spread)['metrics']))
    lines += ['', 'The touch rule nearly breaks even at one pip and loses at two pips. '
        'This is a stress test, not a measurement of historical broker spreads. '
        'The inside-close alternative is negative even at the base spread.', '',
        '## Separate later-period checks', '',
        'Each two-year broker window starts with a new strategy and $10,000 account. '
        'At least the declared warmup counts are verified using preceding history '
        '(386 calendar days). No positions or setup state are inherited from a previous '
        'test window. Setup state reconstructed during warmup is retained at its start. '
        'Trades and floating positions at each boundary are recorded separately. '
        'These are retrospective checks: the recovery idea arose from an already-seen '
        'full-period subgroup, so the later windows are not untouched out-of-sample evidence. '
        'No parameters were optimized or selected within these windows.']
    for year in (2020, 2022, 2024):
        lines += table(f'July {year} through June {year+2}')
        for policy in LABELS:
            lines.append(metric_row(LABELS[policy], get(policy, window=f'cold_{year}')['metrics']))
    lines += table('Combined closed trades from the three separate windows')
    for policy in LABELS:
        lines.append(metric_row(LABELS[policy], cold[policy]['metrics']))
    lines += ['', 'Combined R and streaks concatenate closed outcomes in chronological order. '
        'Account balances reset for each fold; the individual growth percentages are not '
        'added or claimed as continuous portfolio growth.', '',
        '| Window | Rule | Account growth | Equity DD | End exposure |',
        '|---|---|---:|---:|---:|']
    for year in (2020, 2022, 2024):
        for policy in LABELS:
            r = get(policy, window=f'cold_{year}')
            lines.append(f"| {year}–{year+2} | {LABELS[policy]} | {r['growth_pct']:+.2f}% | "
                         f"{r['equity_dd_pct']:.2f}% | {len(r['final_exposure'])} |")
    lines += table('Broker continuous replay by entry/close period')
    for window in ('2017_2019', '2020_2025', '2026_to_july14'):
        for policy in LABELS:
            lines.append(metric_row(f"{window} / {LABELS[policy]}", get(policy)['windows'][window]))
    lines += ['', 'A trade enters these period totals only when both its entry and close are '
        'within that period. Cross-boundary trades remain in the full replay and need not '
        'sum into these subdivisions. This continuous replay differs from resetting each cold window.']
    lines += table('Broker BUY/SELL, full base-spread replay')
    for policy in LABELS:
        for direction in ('BUY', 'SELL'):
            lines.append(metric_row(f'{LABELS[policy]} / {direction}', get(policy)['directions'][direction]))
    lines += ['', '## Why the original subgroup was too optimistic', '',
        'The preceding review found 181 touched-extreme trades contributing +28.61R '
        'within the current broker trade list. Actual recovery-only replay yields '
        f"{len(recovery)} trades and {get('touch')['metrics']['total_r']:+.2f}R. "
        'Skipping other entries changes exposure, subsequent H1 biases and future opportunities. '
        'For the following comparison, matching requires the same originating setup, attempt, '
        'entry/close times, direction and entry/SL/TP prices; volume and tickets can differ '
        'after account paths diverge.']
    lines += table('Current versus recovery-touch economic opportunity overlap')
    for label, key_name in [('Common opportunities (recovery sizing)', 'common'),
                            ('Only in current', 'current_only'), ('Only in recovery', 'recovery_only')]:
        lines.append(metric_row(label, overlap[key_name]))
    lines += ['', '## Validation and limitations', '',
        'Completed 24 sequential research cases plus three extra plain-production controls. '
        'All three unchanged baselines match every trade field from the preceding review '
        'and all three observation baselines match plain production trades and ending exposure. '
        'Code, CSV and HistData metadata hashes match at completion. Every accepted order '
        'reconciles to a close, executable rejection or ending exposure; all closed recovery '
        'trades are attributed to qualifying contexts and retain the stop/R:R guards. '
        'Five focused recovery tests cover both directions, equality boundaries, no premature '
        'entry before fractal/FVG confirmation, filtered setup eligibility, proposal rejection '
        'and minimum-stop preservation. The complete 234-test suite passes.', '',
        'HistData retains the previously documented 2023 provider gaps. Recent matching '
        'prices are nearly identical to Dukascopy and do not constitute an independent feed. '
        'Broker D1 session boundaries differ from UTC-midnight source bars. Swap, tick-level '
        'spread/slippage and portfolio competition can materially change these thin edges. '
        'The copied DEMO evidence predates the current corrections and was not used to tune '
        'these rules. No new MT5 connection was made.', '',
        '## Decision', '',
        'Keep GBPUSD DEMO unchanged as requested. Keep USDJPY Candle Confirmation retired '
        'from new runs, with magic number 1009 retained for existing-position reconciliation. '
        'USDJPY remains available to other strategies. Existing broker positions are not '
        'automatically closed by this configuration change.', '',
        'Retain the touch-only rule for further research; do not promote the inside-close '
        'alternative on these results. Before changing GBPUSD DEMO logic, predefine one '
        'further hypothesis, validate it on later evidence not used in selecting it, and '
        'measure actual execution costs. The current study does not establish a robust '
        'replacement or justify higher risk.', '',
        'The remote trading process still uses its loaded configuration until the updated '
        'code is committed/pushed, pulled on the host and the process is restarted. '
        'This task changes local code only; it performs no commit, push or host deployment.', '',
        '## Reproduce', '',
        'Use `.venv\\Scripts\\python.exe research_candle_gbpusd_recovery.py` in a fresh output '
        'directory (the runner refuses to overwrite an existing manifest), then '
        '`.venv\\Scripts\\python.exe summarize_candle_gbpusd_recovery.py`. Fixed definitions '
        'and original source hashes are recorded in '
        '`output/candle_gbpusd_recovery_20260930/manifest.json`; all per-case trades, '
        'contexts, controls, completion record and summary are retained there.']
    path = ROOT/'strategy_log/candle_gbpusd_recovery_20260930.md'
    path.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps(dict(report=str(path), cold=cold, broker_trade_overlap=overlap), indent=2))


if __name__ == '__main__':
    main()
