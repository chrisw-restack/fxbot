"""Create the Running correction report from completed local research results."""
from copy import deepcopy
from datetime import datetime
import json

from data.histdata_provenance import file_hash, write_json
from research_ema_fib_review import metrics
from research_ema_fib_running_corrections import OUT, PREVIOUS, ROOT, SOURCES
from summarize_ema_fib_tracking import table


def read(name):
    return json.loads((OUT/name).read_text())


def trades(source,variant,label,six=False):
    folder=PREVIOUS if variant=='original' else OUT
    pattern=f'{source}_*_{label}_trades.json' if variant=='original' else f'{source}_*_{variant}_{label}_trades.json'
    return [t for p in sorted(folder.glob(pattern)) for t in json.loads(p.read_text())
            if not six or t['symbol']!='USDCAD']


def main():
    complete=read('complete.json')
    manifest=read('manifest.json')
    strategy_hash=file_hash(ROOT/'strategies/ema_fib_running.py')
    validation_note='The completed replay manifest matches the final strategy source hash.'
    if manifest['code_hashes']['strategies/ema_fib_running.py']!=strategy_hash:
        final_validation=read('final_code_validation.json')
        assert len(final_validation['controls'])==6
        assert final_validation['strategy_sha256']==strategy_hash
        assert final_validation['preceding_strategy_sha256']==manifest['code_hashes']['strategies/ema_fib_running.py']
        validation_note=('After those replays, an additional broker cancellation race was corrected: a partial fill '
            'discovered after cancellation of its remainder must still be adopted as OPEN. Final closes still block '
            'stale snapshots. The preceding strategy source is archived with its original hash. Six further full '
            '2020 through 2025 broker replays on the final code match every earlier trade field and ending exposure. '
            'No CSV replay enters the changed partial-fill branch because the simulator has no partial fills. '
            'Final source hashes and control results are recorded in final_code_validation.json. '
            'The race itself has a deterministic regression test.')
    rows=read('results.json')
    aggregate={(r['source'],r['variant'],r['label']):r for r in read('aggregate.json')}
    original={(r['source'],'original',r['label']):r for r in json.loads((PREVIOUS/'aggregate.json').read_text())}
    aggregate.update(original)
    variants=('original','tracking','corrected')
    comparison=[(f'{src}, {v}',aggregate[(src,v,'six_2020_2025')]['metrics']) for src in SOURCES for v in variants]
    changes=[]
    for src in SOURCES:
        for before,after in zip(variants,variants[1:]):
            def key(t):
                return (t['symbol'],t['direction'],t['open_time'],t['close_time'],
                        round(t['entry_price'],10),round(t['sl'],10),round(t['tp'],10))
            old={key(t):t for t in trades(src,before,'2020_2025',six=True)}
            new={key(t):t for t in trades(src,after,'2020_2025',six=True)}
            removed=[old[k] for k in old.keys()-new.keys()]
            added=[new[k] for k in new.keys()-old.keys()]
            changes.append(dict(source=src,before=before,after=after,unchanged_paths=len(old.keys()&new.keys()),
                removed=sorted(removed,key=lambda t:t['open_time']),added=sorted(added,key=lambda t:t['open_time']),
                removed_metrics=metrics(removed),added_metrics=metrics(added)))
    write_json(OUT/'changed_trade_paths.json',changes)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(3,1,figsize=(11,10),sharex=True,layout='constrained')
    names={'dukascopy':'Dukascopy','histdata':'Verified HistData','mt5_icmarkets_utc':'IC Markets'}
    colors={'original':'#7b8794','tracking':'#dc8423','corrected':'#1764a0'}
    for ax,src in zip(axes,SOURCES):
        for variant in variants:
            ts=sorted(trades(src,variant,'2020_2025',six=True),key=lambda t:(t['close_time'],t['symbol'],t['ticket']))
            dates=[datetime(2020,1,1)]
            cumulative=[0.0]
            for t in ts:
                dates.append(datetime.fromisoformat(t['close_time']))
                cumulative.append(cumulative[-1]+t['net_r'])
            ax.step(dates,cumulative,where='post',label=variant,color=colors[variant],linewidth=1.7)
        ax.axhline(0,color='#263340',linewidth=.6)
        ax.set_title(names[src],loc='left',fontsize=12)
        ax.set_ylabel('Cumulative net R')
        ax.grid(alpha=.15)
        ax.legend(loc='upper left',ncol=3,frameon=False,fontsize=9)
    fig.suptitle('EmaFib Running: effect of the two corrections\nSix matched pairs, fixed parameters, closed trades only',fontsize=14)
    axes[-1].set_xlim(datetime(2020,1,1),datetime(2026,1,1))
    fig.savefig(OUT/'correction_comparison.png',dpi=160)
    plt.close(fig)
    sections=['# EmaFib Running corrections and validation, 25 September 2026',
        'Status: local strategy corrections completed at the user\'s request. Numeric parameters, seven-pair DEMO membership, and risk are unchanged. This work does not deploy or restart the trading host, and it does not authorize real-money trading. The earlier review describes the frozen original implementation; use this report for corrected results.',
        '## Assessment and recommendation',
        'The tracking defects are real, but they do not explain away Running\'s historical profit. Tracking-only results barely change for the six matched pairs; the seven-pair Dukascopy/HistData runs add one USDCAD loss. Correcting the running extreme reduces six-pair net R from +33.59 to +27.03 on Dukascopy, +42.41 to +35.40 on verified HistData, and +17.31 to +13.26 on IC Markets. Keep both correctness fixes rather than selecting the flawed implementation for its higher return.',
        'The corrected broker result is a weak basis for continued use: 128 trades over six years, PF 1.13, expectancy +0.104R/trade, maximum closed-trade drawdown 22.73R, and 22 consecutive losses. The most recent historical test, 2024 through 2025, loses 15.10R with PF 0.59. That test also loses on Dukascopy and HistData. Earlier tests are WEAK for 2020 through 2021 and STRONG for 2022 through 2023 on the long-history sources. The strategy no longer deserves a blanket STRONG validation label.',
        'January through 14 July 2026 produces only four trades and about +1.10R on each source. That sample cannot overturn the recent failed test. The one-pip broker spread replay remains positive at +13.02R, so the result is not solely an artifact of the default narrow spread; actual financing and execution remain unmodeled.',
        'I recommend pausing new Running entries in the default DEMO suite and retaining the corrected strategy for research. Membership has not been changed by this work. A new parameter search should be a separate, small, train-only experiment with untouched evaluation periods and broker confirmation. Selecting winning pairs or the best parameter combination from these same completed tests would overstate the evidence. No numeric optimization was performed here.',
        '## What changed',
        'Order proposals now become tracked exposure only after acceptance. Fills, cancellations, and final closes come from execution callbacks. A bid-price touch no longer clears a pending BUY before the ask actually reaches its entry. Failed cancellations retain ownership, and a filled position keeps its originating anchor even when later fractals form. Duplicate closes and stale snapshots cannot reopen finished orders. Partial closes and cancellation of an unfilled remainder preserve the filled position.',
        'New signals carry setup and attempt identities. The existing setup ledger can recover the originating anchor after a cold restart; checkpoints preserve the complete state when their configuration fingerprint matches. Inherited orders without recorded origin remain managed, but a loss does not guess an anchor from current market state. Preserve logs/setup_ledger.json when updating the host. The correction cannot reconstruct missing metadata for old orders.',
        'The running extreme now starts with every completed close from the actual fractal anchor through its confirmation candle. Previously it started with the confirmation close alone. A BUY example with a known 1.114 close before confirmation and a 1.108 confirmation close now starts at 1.114. SELL uses the mirrored lowest close. This uses only completed information. EMA, ATR, FVG, minimum stop, entry hours, Fibonacci parameters, repricing threshold, and the rule allowing filled positions to run to SL/TP are unchanged.',
        'The research control called tracking applies only the lifecycle correction and deliberately retains the old extreme initialization. Corrected applies both fixes. Original is loaded from the reviewed Git revision, not reconstructed by undoing selected lines. These controls measure the effects separately; the production strategy contains both corrections.',
        '## Six matched pairs, 2020 through 2025',
        'EURUSD, GBPUSD, AUDUSD, NZDUSD, USDJPY, and USDCHF. USDCAD is excluded from all three sources because broker history starts in January 2025.',
        table(comparison),
        '![Cumulative closed-trade net R by source and correction](../output/ema_fib_running_corrections_20260925/correction_comparison.png)',
        '## Seven pairs on long-history sources',
        table([(f'{src}, {v}',aggregate[(src,v,'2020_2025')]['metrics']) for src in SOURCES[:2] for v in variants]),
        '## Seven pairs, January through 14 July 2026',
        table([(f'{src}, {v}',aggregate[(src,v,'2026_to_july14')]['metrics']) for src in SOURCES for v in variants]),
        '## Corrected results by pair, 2020 through 2025',
        table([(f"{r['source']}, {r['symbol']}",r['metrics']) for r in rows if r['variant']=='corrected' and r['label']=='2020_2025']),
        '## Corrected calendar years, six matched pairs',
        'Closing-year slices of the continuous 2020 through 2025 replays.',
        table([(f'{src}, {y}',m) for src in SOURCES for y,m in aggregate[(src,'corrected','six_2020_2025')]['years'].items()]),
        '## Historical rolling validation',
        'Four-year training and two-year test windows use the same fixed parameters throughout. Training windows are 2016 through 2019, 2018 through 2021, and 2020 through 2023. Tests are 2020 through 2021, 2022 through 2023, and 2024 through 2025. Each side starts fresh. The first training period has no pre-2016 warm-up because the files start in January 2016. Later runs have 180 days of warm-up. Broker validation uses only the final fold and six matched pairs; Dukascopy and HistData use all seven pairs.',
        'These periods were used in earlier strategy development. This is historical revalidation, not fresh unseen out-of-sample evidence. No parameter, source, or symbol selection occurs in these folds. Expectancy retention is test R/trade divided by training R/trade; it is undefined when training expectancy is nonpositive. A losing test fails regardless of retention.',
        table([(f"{r['source']}, test {str(r['test_start'])[:4]}, {part}",r[part]) for r in read('folds.json') for part in ('train','test')])]
    lines=['| Source | Test starts | Expectancy retention | Verdict |','|---|---|---:|---|']
    for r in read('folds.json'):
        retention='undefined' if r['retention'] is None else f"{100*r['retention']:.1f}%"
        lines.append(f"| {r['source']} | {str(r['test_start'])[:4]} | {retention} | {r['verdict']} |")
    sections.extend(['\n'.join(lines),'## One-pip spread stress, corrected six-pair strategy',
        'Full replays use one pip spread on every pair, retaining commission. This can change which pending orders fill.',
        table([(f'{src}, {label}',aggregate[(src,'corrected',label)]['metrics']) for src in SOURCES for label in ('six_2020_2025','six_spread_1pip')])])
    financing=[]
    for src in SOURCES:
        ts=trades(src,'corrected','2020_2025',six=True)
        for rate in (0,3,7):
            adjusted=deepcopy(ts)
            for t in adjusted:
                t['net_r']-=rate*t['lot_size']*t['duration_hours']/24/t['initial_risk']
            financing.append(dict(source=src,debit_usd_per_lot_day=rate,metrics=metrics(adjusted)))
    write_json(OUT/'financing_sensitivity.json',financing)
    sections.extend(['## Illustrative financing debit, corrected six-pair strategy',
        'A fixed-path sensitivity subtracts $0, $3, or $7 per lot per 24 hours held. It is not actual broker swap. Credits, rollover timing, triple-swap days, changed sizing, and compounding are excluded.',
        table([(f"{r['source']}, ${r['debit_usd_per_lot_day']}/lot/day",r['metrics']) for r in financing]),
        '## USDCAD, July through December 2025',
        'The common window has sufficient warm-up on the available broker history.',
        table([(f'{src}, {v}',aggregate[(src,v,'2025_h2')]['metrics']) for src in SOURCES for v in variants]),
        '## Reproducibility and limits',
        f"Completed {complete['replays']} sequential corrected/control replays and {complete['baseline_controls']} original-code controls. Original controls match every prior trade field and ending exposure. Input, provenance sidecar, parameter, and shared-pipeline hashes match the prior baseline. Code and price-data hashes remained unchanged throughout the run. Each corrected replay checks that accepted-order ownership matches ending simulated exposure and that no unresolved proposal remains.",
        validation_note,
        'All 172 unit tests pass, including 22 new Running tests for lifecycle and extreme initialization. Execution failure messages in the tests are intentional fixtures. Broker connectivity and real MT5 order submission are not tested on this PC.',
        'M5 executes H1/D1 signals. Each pair starts with $10,000 and 0.5% risk per trade. Default spread and $7/lot round-trip commission are modeled. Tables combine independent pair net-R histories by close time. Profit factor uses positive net R divided by absolute negative net R. Drawdown is the maximum decline of cumulative closed-trade R, not floating account-equity drawdown. Shared account exposure limits, daily-loss gates, news, variable spreads, extra slippage, and actual swaps are excluded.',
        'Verified HistData passes the provenance-enforcing loader. The earlier source audit found approximately 99.98% identical OHLC on shared M5 timestamps with Dukascopy, so the two are not independent price confirmations. Missing bars and daily aggregation differ. Broker daily bars follow broker sessions rather than UTC midnight. Data after 14 July 2026 is excluded; some supplied broker files end at 21:00 UTC that day.',
        'The copied DEMO export remains only two historical wins totaling $1,300.76 net. The $1,205.46 EURUSD winner followed an unsuccessful cancellation that the older engine wrongly logged as successful. That history does not validate the intended strategy or these new corrections.',
        '## Period-end exposure',
        '\n'.join(f"- {r['source']} {r['symbol']} {r['variant']} {r['label']}: {len(r['open_exposure'])} open/pending" for r in rows if r['open_exposure']) or 'Every replay ended flat.',
        'Open exposure, where present, is excluded from closed-trade statistics and is never liquidated using future bars.',
        '## Reproduction',
        '```powershell\n.venv\\Scripts\\python.exe -m unittest discover -s tests -v\n.venv\\Scripts\\python.exe research_ema_fib_running_corrections.py\n.venv\\Scripts\\python.exe summarize_ema_fib_running_corrections.py\n```',
        'The main research script now reruns all cases on the final strategy. validate_ema_fib_running_final.py preserves the supplemental check against the archived pre-race-fix artifacts from this run; it deliberately refuses a different preceding source hash.',
        f"Frozen original strategy revision: `{manifest['frozen_revision']}`. Research artifacts and hashes are under `output/ema_fib_running_corrections_20260925/`. The separate initial review remains under `strategy_log/ema_fib_running_review_20260925.md`."])
    path=ROOT/'strategy_log/ema_fib_running_corrections_20260925.md'
    path.write_text('\n\n'.join(sections)+'\n',encoding='utf-8')
    print(path)


if __name__=='__main__':
    main()
