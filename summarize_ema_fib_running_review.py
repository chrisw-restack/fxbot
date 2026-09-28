"""Render the Running review from completed, hashed local research artifacts."""
from collections import Counter
from copy import deepcopy
import json
from statistics import median

from data.histdata_provenance import write_json
from research_ema_fib_running_review import OUT, ROOT, SOURCES
from research_ema_fib_review import metrics
from summarize_ema_fib_tracking import table


def read(name):
    return json.loads((OUT/name).read_text())


def trades(source,label,symbols=None):
    result=[]
    for p in sorted(OUT.glob(f'{source}_*_{label}_trades.json')):
        result.extend(t for t in json.loads(p.read_text()) if symbols is None or t['symbol'] in symbols)
    return result


def main():
    complete=read('complete.json')
    manifest=read('manifest.json')
    rows=read('results.json')
    aggregate={(r['source'],r['label']):r for r in read('aggregate.json')}
    demo=read('demo_evidence.json')
    sections=['# EmaFib Running logic and performance review, 25 September 2026',
        'Historical initial review of the frozen original code. Its recommended corrections are now implemented locally; see the [correction and validation report](ema_fib_running_corrections_20260925.md) for current results and the latest recommendation.',
        'Status: still included in the local DEMO suite. This review changes no production strategy logic, parameters, membership, or risk. The earlier STRONG walk-forward result is historical evidence from an older code/data/simulator combination. It does not resolve the defects reproduced here.',
        '## Assessment',
        'The trading idea is coherent, but the current implementation does not reliably follow its order lifecycle or documented running-extreme rule. It is worth correcting and retesting before deciding to retire it. Six matched pairs return +33.59R on Dukascopy, +42.41R on verified HistData, and +17.31R on IC Markets over 2020 through 2025. These are current-code results with confirmed defects, not corrected-strategy results.',
        'The broker edge is modest: PF 1.17, a 24.10R closed-trade drawdown, and 23 consecutive losses. It survives the 1-pip spread replay at +17.10R and a separate illustrative $7/lot/day financing debit at +12.99R. However, 2024 and 2025 together lose 14.04R. January through 14 July 2026 adds only about 1.10R from four trades. The older STRONG label overstates what the present evidence establishes.',
        'GBPUSD contributes most profit in the long broker sample. AUDUSD and NZDUSD are profitable but have only eight and six trades respectively over six years. EURUSD is slightly negative and USDJPY loses on all three sources. Pair removal would be a new research decision and should not be selected from this same evaluation sample without validation. About 11% of accepted broker-replay pending orders become closed trades, reflecting frequent cancellation and replacement.',
        'The 12 deterministic audit cases and historical observers identify real defects. On broker data, 20 losing trades invalidate the wrong anchor, 26 closes leave local pending state, and two H1 touches clear orders that remain unfilled. The copied DEMO evidence is also weak: nearly all its profit comes from an order the old bot tried unsuccessfully to cancel. Correct and compare the lifecycle and running-extreme changes separately, then repeat rolling validation before parameter tuning or promotion.',
        '## What the strategy actually does',
        'D1 and H1 EMA 10/20 directions must agree. D1 simple ATR over 14 completed daily bars must be at least 50 pips. The current H1 EMA-separation filter and loss cooldown are disabled. Entries use H1 candle opening-hour labels 09:00 through 19:00 UTC, so new decisions occur after those bars close, roughly 10:00 through 20:00 UTC. Pending management also runs outside entry hours.',
        'A BUY uses a confirmed H1 fractal low, the low of that candle\'s body, and a running highest close. A SELL mirrors this with a fractal high and running lowest close. With fractal_n=2, confirmation requires two completed bars to the right. The Fibonacci entry uses 0.786 of the body-based range. The stop is at the fractal wick and the target uses a 2.5 extension of the body-based range. A directional three-candle wick gap is required; there is no extra gap-size, middle-candle strength, or gap-retest test.',
        'The name min_swing_pips is misleading here: the configured 30 pips is a minimum entry-to-stop distance, not a minimum body swing range. fib_tp=2.5 is not a fixed 2.5R target. Actual reward/risk depends on the distance from body to wick. For example, body low 1.102, running high 1.115, and wick low 1.100 give entry 1.104782, stop 1.100, target 1.1345, and about 6.21R before costs. The maximum with zero extra wick distance is approximately 10.68R. Risk checks still enforce the minimum 1R rule.',
        'The pending-order update cancels when the newly calculated entry differs by more than one pip, including changes caused by a new fractal anchor. Replacement is considered on a later H1 bar and must pass the entry filters again. It is not an atomic amendment. Filled positions retain their original SL/TP. Swing age is an entry filter, not an expiry timer for existing orders.',
        '## Confirmed implementation defects',
        '1. H1 bid-price touches stand in for execution-confirmed fills. An unfilled BUY whose bid touches the limit while ask remains above it can disappear from local tracking and miss a later cancellation. Gap fills can also disagree with the H1 straddle heuristic.',
        '2. A new proposal can replace the accepted trade\'s anchor while a position is already open. The portfolio rejects the duplicate order, but the overwritten anchor remains. A later loss can invalidate the wrong fractal. A 30-pip minimum stop does not prevent this portfolio rejection path, contrary to the old strategy-log explanation.',
        '3. Close callbacks clear anchor snapshots but leave local pending entry/direction intact. A trade that fills and stops between H1 decisions can leave phantom pending state. Conversely, cancellation clears local state before broker confirmation. The engine can retry cancellation, but the strategy no longer retains authoritative order ownership.',
        '4. A newly confirmed fractal resets the running extreme to None, then initializes it using only the current confirmation candle. Earlier closes between the fractal and its confirmation are already known but omitted. A reproduced BUY example should start at the known 1.114 high close but instead starts at 1.108; the SELL mirror is also wrong relative to the documented rule. This is an initialization error, not future-data leakage.',
        '5. Signals carry no setup/attempt identity and the strategy has no order-state adoption callback. A valid strategy checkpoint can preserve state, but a cold restart or invalidated checkpoint cannot recover an accepted order\'s original anchor from the setup ledger. Falling back to the current fractal on a loss can misattribute an inherited trade. The global checkpoint fingerprint changes when suite membership changes, so retirement of Retracement makes this recovery limitation relevant to the next updated run.',
        'The deterministic audit verifies arithmetic and delayed fractal confirmation, and reproduces both BUY and SELL initialization errors plus the lifecycle defects. These findings do not establish how much profit would change after correction. This review measures the current implementation; it does not present its metrics as corrected-strategy performance.',
        'All 150 existing unit tests pass. They do not cover these Running defects. The separate audit cases deliberately assert the observed faulty outcomes to make the findings reproducible; passing those audit assertions is evidence of the defects, not a strategy-correctness certificate.',
        '## Research method',
        f"Completed {complete['replays']} sequential fixed-parameter replays and {complete['observer_controls']} plain-versus-observed controls. Both controls compare every trade field and ending exposure. The observer records defects without changing decisions. Code and input hashes are in the manifest, and code hashes matched at completion.",
        'The long period is 2020 through 2025, with a separate 1 January through 14 July 2026 comparison. Every run starts fresh with 180 days of warm-up. M5 executes H1/D1 signals. Spread and $7 per lot round-trip commission are included. Variable spreads, extra slippage, swaps, news filtering, and shared account portfolio/daily-loss gates are excluded. Each pair starts at $10,000 with 0.5% risk; tables combine net-R trade histories in closing-time order, not pooled account returns or equity drawdowns.',
        'Verified HistData passes the provenance-enforcing loader. It is not an independent price-feed confirmation: the previous audit found approximately 99.98% identical OHLC at shared M5 timestamps. Missing bars and higher-timeframe aggregation differ. Broker D1 bars follow the broker session rather than UTC midnight. USDCAD broker M5/H1/D1 begin in January 2025, an accepted coverage limit. It is excluded from all long-period source comparisons and included only in periods with adequate warm-up. Data after 14 July 2026 remains excluded.',
        'The newly supplied broker M5 files end at 21:00 UTC on 14 July. Requesting an end date of 15 July does not guarantee coverage through the final UTC midnight. Period-end open/pending exposure is reported below and excluded from closed-trade statistics.',
        '## Seven FX pairs, 2020 through 2025',
        table([(src,aggregate[(src,'2020_2025')]['metrics']) for src in SOURCES[:2]]),
        '## Six matched pairs, 2020 through 2025',
        'EURUSD, GBPUSD, AUDUSD, NZDUSD, USDJPY, and USDCHF. USDCAD is excluded from every source.',
        table([(src,aggregate[(src,'six_2020_2025')]['metrics']) for src in SOURCES]),
        '## Seven FX pairs, January through 14 July 2026',
        table([(src,aggregate[(src,'2026_to_july14')]['metrics']) for src in SOURCES]),
        '## By pair, 2020 through 2025',
        table([(f"{r['symbol']}, {r['source']}",r['metrics']) for r in rows if r['label']=='2020_2025']),
        '## Calendar-year breakdown, six matched pairs',
        'These are closing-year slices of continuous replays, not new walk-forward folds. No parameter search or fresh walk-forward selection was run on the known-defective implementation. The historical STRONG label should be re-evaluated only after the corrections, with train-only selection and explicit cost assumptions.',
        table([(f'{src}, {y}',m) for src in SOURCES for y,m in aggregate[(src,'six_2020_2025')]['years'].items()]),
        '## One-pip spread stress, six matched pairs',
        'Spread is changed to 1 pip for every pair, with the same commission and strategy settings. The entire replay is rerun. A pending order fills at its order price, so a wider spread can leave some trade paths unchanged while causing other orders to miss their fills.',
        table([(f'{src}, {label}',aggregate[(src,label)]['metrics']) for src in SOURCES for label in ('six_2020_2025','six_spread_1pip')])]
    financing=[]
    for src in SOURCES:
        ts=trades(src,'2020_2025',[s for s in manifest['symbols'] if s!='USDCAD'])
        for rate in (0,3,7):
            adjusted=deepcopy(ts)
            for t in adjusted:
                t['net_r']-=rate*t['lot_size']*t['duration_hours']/24/t['initial_risk']
            financing.append(dict(source=src,debit_usd_per_lot_day=rate,metrics=metrics(adjusted)))
    write_json(OUT/'financing_sensitivity.json',financing)
    sections.extend(['## Illustrative financing debit, six matched pairs',
        'This subtracts $0, $3, or $7 per lot per 24 hours held, prorated by duration, from existing trade paths. It is a sensitivity calculation, not actual broker swap. Directional credits, rollover times, triple-swap days, changed lot sizing, and compounding are not modeled.',
        table([(f"{r['source']}, ${r['debit_usd_per_lot_day']}/lot/day",r['metrics']) for r in financing]),
        '## USDCAD only, July through December 2025',
        'July starts after the available broker history provides the required warm-up. The same dates are used for every source.',
        table([(r['source'],r['metrics']) for r in rows if r['label']=='2025_h2'])])
    audits=[]
    for src in SOURCES:
        subset=[r for r in rows if r['source']==src and r['label']=='2020_2025' and r['symbol']!='USDCAD']
        counts=Counter()
        for r in subset:
            counts.update(r['audit'])
        audits.append(dict(source=src,counts=dict(counts),closed=sum(r['metrics']['trades'] for r in subset),
                           ending_open=sum(sum(bool(p.get('open_time')) for p in r['open_exposure']) for r in subset)))
    write_json(OUT/'audit_totals.json',audits)
    lines=['| Source | Accepted | Cancelled | Closed | Bid-touch false fills | Occupied-slot proposals | Wrong-anchor losses | Close leaves pending |',
           '|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in audits:
        c=r['counts']
        lines.append('| '+r['source']+' | '+' | '.join(str(v) for v in [c.get('accepted_orders',0),c.get('confirmed_cancellations',0),r['closed'],
            c.get('heuristic_consumed_unfilled_order',0),c.get('proposal_while_slot_occupied',0),
            c.get('loss_invalidated_wrong_anchor',0),c.get('close_left_local_pending',0)])+' |')
    sections.extend(['## Observed lifecycle problems, six matched pairs', '\n'.join(lines),
        'Counts refer to current-code 2020 through 2025 runs at the default modeled spread. They are events, not additive numbers of affected trades. Defects can overlap. Accepted and cancellation counts describe orders, while closed counts describe executed trades. Indicator-only extreme-initialization counts and examples are recorded separately in each result and include warm-up bars. These counts cannot be translated directly into a performance correction.'])
    details=[]
    for src in SOURCES:
        ts=trades(src,'2020_2025',[s for s in manifest['symbols'] if s!='USDCAD'])
        details.append(dict(source=src,median_duration_hours=median(t['duration_hours'] for t in ts),
                            max_duration_hours=max(t['duration_hours'] for t in ts),
                            median_level_rr=median(abs(t['tp']-t['entry_price'])/abs(t['entry_price']-t['sl']) for t in ts)))
    write_json(OUT/'holding_and_rr.json',details)
    sections.extend(['## Copied DEMO evidence',
        f"The 18 September export contains {demo['trades']} closed Running positions, {demo['wins']} wins, with combined profit after commission and swap of ${demo['net_pnl']:,.2f}. The earliest entry is {demo['first_entry']} and latest close is {demo['last_close']} in broker report time. With no losses, profit factor has no finite estimate; two wins do not validate a strategy.",
        'The larger winner is especially unsuitable as evidence of the intended strategy. EURUSD ticket 1689274839 was submitted on 5 June. On 7 June at 21:00 UTC, the copied log records cancellation failure with retcode 10018, immediately followed by an incorrect cancellation-success log. The journal also records ORDER_CANCELLED. The broker history shows that the order instead filled on 15 June and closed on 24 June for $1,205.46 net. The remaining USDJPY winner contributes $95.30 net. Thus most copied DEMO profit came from an order the bot intended to cancel. This was an older execution-path failure, before the September fixes; it is not proof that the same execution bug remains. Exact log lines and journal rows are preserved in demo_evidence.json.',
        'The copied journal has '+str(demo['event_counts'])+'. Rejections: '+str(demo['rejection_reasons'])+'. Counts cover a partial window and cancellation rows include recoveries, so they are not a complete placement-to-close funnel. The report predates the confirmed September restart and mixes historical code/settings/risk. It cannot establish correct operation of the current implementation.',
        '## Next decision',
        'Do not optimize numeric parameters or treat the historical STRONG label as current validation. Correct accepted-order ownership and restart recovery first, then separately correct the running-extreme initialization to measure each effect. Re-run the same fixed settings on the same source windows before selecting parameters or deciding whether to retain the strategy. The portfolio already prevents duplicate positions; a simple local position flag without acceptance/rejection/recovery handling would repeat the earlier Retracement failure.',
        'This analysis does not remove Running from DEMO or change the trading host. The evidence differs from Retracement: Running has a body-based range, wick stop, different payoff distribution, and a moving pending level. Its retirement decision should use its own corrected broker results rather than inherit the Retracement decision.',
        '## Reproduction',
        '```powershell\n.venv\\Scripts\\python.exe research_ema_fib_running_review.py\n.venv\\Scripts\\python.exe audit_ema_fib_running_logic.py\n.venv\\Scripts\\python.exe audit_ema_fib_running_demo.py\n.venv\\Scripts\\python.exe summarize_ema_fib_running_review.py\n```',
        'Trade files, examples, assumptions, hashes, audit cases, and controls are under `output/ema_fib_running_review_20260925/`. All production code and DEMO settings remain unchanged by this review.',
        '## Period-end exposure',
        '\n'.join(f"- {r['source']} {r['symbol']} {r['label']}: {len(r['open_exposure'])}" for r in rows if r['open_exposure']) or 'All runs ended flat.'])
    path=ROOT/'strategy_log/ema_fib_running_review_20260925.md'
    path.write_text('\n\n'.join(sections)+'\n',encoding='utf-8')
    print(path)


if __name__=='__main__':
    main()
