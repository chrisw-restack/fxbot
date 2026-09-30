"""Summarize the completed, unchanged-parameter IMS audit."""
from collections import Counter
import json
from pathlib import Path

import pandas as pd
from data.histdata_provenance import write_json
from data.historical_loader import find_csv
from research_ims_trend_review import OUT, ROOT, settings
from research_ema_fib_review import metrics
from summarize_ema_fib_tracking import table


def read(path):
    return json.loads(path.read_text())


def prices(symbols):
    rows = []
    for symbol in symbols:
        frames = {}
        for source in ('dukascopy','histdata'):
            df = pd.concat([pd.read_csv(p, usecols=['time','open','high','low','close'])
                            for p in find_csv(symbol,'M5',data_source=source)])
            df = df[(df.time >= '2020-01-01') & (df.time < '2026-07-15')].set_index('time')
            assert df.index.is_unique
            frames[source] = df
        d, h = frames['dukascopy'], frames['histdata']
        shared = d.index.intersection(h.index)
        equal = (d.loc[shared].round(8) == h.loc[shared].round(8)).all(axis=1)
        rows.append(dict(symbol=symbol, common_bars=len(shared), identical_ohlc_pct=100*equal.mean(),
            dukascopy_only=len(d.index.difference(h.index)), histdata_only=len(h.index.difference(d.index))))
    write_json(OUT/'price_comparison.json',rows)
    return rows


def main():
    _, symbols = settings()
    results = {}
    all_trades = {}
    for source in ('dukascopy','histdata','mt5_icmarkets_utc'):
        for symbol in symbols:
            path = OUT/f'{source}_{symbol}.json'
            if path.exists():
                results[source,symbol] = read(path)
                all_trades[source,symbol] = read(OUT/f'{source}_{symbol}_trades.json')
    assert len(results) == 21, f'Incomplete study: {len(results)}/21'
    def selected(source, cohort, start, end):
        return [t for sym in cohort for t in all_trades[source,sym]
                if start <= t['close_time'] < end]
    def comparison(cohort, start, end, sources):
        return table([(source, metrics(selected(source,cohort,start,end))) for source in sources])
    sources = ['dukascopy','histdata','mt5_icmarkets_utc']
    four = ['USDJPY','AUDUSD','EURUSD','GBPUSD']
    five = four+['USDCAD']
    price_rows = read(OUT/'price_comparison.json') if (OUT/'price_comparison.json').exists() else prices(symbols)
    demo = read(OUT/'demo_evidence.json')
    audit = {s: dict(sum((Counter(r['audit']) for (src,_),r in results.items() if src==s),Counter()))
             for s in sources}
    summary = dict(audit=audit, runs=len(results), production_control=results['dukascopy','EURUSD']['control'],
        all_eight_2020_2025={s:metrics(selected(s,symbols,'2020','2026')) for s in sources[:2]},
        four_2020_2025={s:metrics(selected(s,four,'2020','2026')) for s in sources},
        five_common={s:metrics(selected(s,five,'2025-04-01','2026-07-15')) for s in sources},
        final_exposure={f'{s}_{sym}':r['final_exposure'] for (s,sym),r in results.items() if r['final_exposure']})
    summary['worst_trades'] = {s: min((t for (src,_),ts in all_trades.items() if src==s for t in ts),
                                    key=lambda t:t['net_r']) for s in sources}
    summary['order_accounting'] = {}
    for source in sources:
        accepted = audit[source].get('accepted_orders',0)
        cancelled = audit[source].get('confirmed_cancellations',0)
        closed = sum(len(ts) for (src,_),ts in all_trades.items() if src==source)
        exposure = [p for (src,_),r in results.items() if src==source for p in r['final_exposure']]
        filled_open = sum(bool(p.get('open_time')) for p in exposure)
        # All orders in this strategy are pending and there are no partial simulated closes.
        assert accepted == cancelled + closed + len(exposure)
        summary['order_accounting'][source] = dict(accepted=accepted,cancelled=cancelled,
            closed=closed,filled_open=filled_open,pending=len(exposure)-filled_open,
            filled_percent=100*(closed+filled_open)/accepted)
    write_json(OUT/'summary.json',summary)
    lines = ['# IMS trend strategy review, 2026-09-29', '',
        'Scope: `ImsStrategy`, DEMO name `IMS_H4_M15`. This is not IMS Reversal. Production logic, parameters, symbols, and risk were left unchanged.', '',
        '## Assessment', '',
        'Across the current eight symbols, 2020-2025 remains positive at +27.11R on Dukascopy and +22.91R on corrected HistData, '
        'with profit factors 1.16 and 1.14. The data repair has not erased the historical edge, but the margin is modest.', '',
        'On the same four symbols with long broker M5 history, however, 2020-2025 returns +25.21R on Dukascopy, '
        '+19.62R on HistData, and -4.86R on broker data. The recent five-symbol broker window returns +10.64R across only 30 trades. '
        'This is mixed evidence, not a reliable broker-confirmed edge across the full suite.', '',
        'The trend-following idea is coherent, but the current implementation has setup lifecycle defects. '
        'Its old MODERATE label belongs to the earlier nine-symbol study and does not validate today\'s eight-symbol configuration with the current simulator. '
        'Repair and revalidate setup tracking before searching parameters or increasing exposure. This review does not establish a validated replacement configuration.', '',
        '## Rules actually executed', '',
        'H4 finds a confirmed fractal origin, a later wick break of the preceding opposite swing, and a three-candle imbalance anywhere in that leg. '
        'The range extends with new extremes. EMA 20/50 direction and at least 0.1% separation filter entries. '
        'M15 must touch the 60% level for buys or 40% for sells, then close beyond a confirmed opposite fractal. '
        'The entry leg must contain an imbalance, and its origin must lie in the appropriate half of the H4 range. '
        'A pending order is proposed at the leg midpoint, with the stop at its origin and a 2.5R target supplied by the runner.', '',
        'The session checks M15 candle opening hours 12 through 16 UTC, so completed-candle decisions normally occur from 12:15 through 17:00. '
        'H4 depth expiry uses a wick below 30% or above 70%; M15 depth expiry uses the close. '
        'Origin breaches also expire on M15 wicks. The top strategy docstring still says a strict 50% zone touch, while executable entry activation uses 60%/40%.', '',
        'Confirmed fractals use completed right-hand bars. The shared replay dispatches higher-timeframe bars only after their close, '
        'and orders cannot fill on the signal candle. No direct future-candle read was found in this path. '
        'Those safeguards do not solve the state and execution issues below.', '',
        '## Logic findings', '',
        '1. **Expired setups can return without passing their own invalidation rules.** '
        'The scanner has no retired-origin memory and checks the historical break/FVG without rejecting a subsequently breached origin. '
        'The audit constructs an H4 origin at 90, a high of 112, an expiry candle with low 92, '
        'then a candle with low 89. The same origin at 90 is recreated on that last candle even though it is already broken. '
        'A later M15 check may expire it again, but the scanner is not returning a consistently valid setup.', '',
        '2. **Trade closure is not tied to the originating setup.** A win clears the current H4 bias by symbol. '
        'A loss resets the current M15 state by symbol. If the bias changed while a position was open, the old result updates the newer setup. '
        'The observer records actual occurrences and delegates to unchanged production callbacks.', '',
        '3. **Proposal, pending order, and filled position share one flag.** The strategy has no order-accepted, order-sync, '
        'proposal-specific rejection, or attributed-close interface. It resets state when issuing a cancellation, before the broker confirms removal. '
        'The engine does retry failed cancellations and protects filled positions, so this is a strategy tracking problem, not evidence that cancellation closes filled trades. '
        'An occupied-slot rejection can retain state for a proposal that was never accepted.', '',
        '4. **Target-touch cancellation only runs during entry hours.** A pending order remains locally active after an otherwise identical target-touch candle at 18:00, '
        'while the 12:00 candle emits CANCEL. Structural expiry does run outside entry hours. '
        'Whether target cancellation should run all hours is a policy choice to compare after fixing identity and confirmation tracking. '
        'Sell target checks also use bid lows rather than the executable ask.', '',
        '5. **Some pattern definitions are broader than their names suggest.** The H4 break is a wick break; '
        'M15 only needs to remain beyond an old fractal, with no fresh-cross requirement. '
        'The FVG can precede the final break and need not remain unfilled. These are design choices, not automatic coding errors. '
        'Make the intended rules explicit before testing stricter alternatives.', '',
        '## Reproduction and assumptions', '',
        '21 sequential fixed-parameter replays. Eight symbols on Dukascopy and verified HistData; five on broker data. '
        'Continuous runs start January 2020 with 180 days of preceding warmup, and stop before July 15, 2026. '
        'Broker USDCAD starts April 2025 with its available January-March history for warmup. '
        'Tables partition trades by close time; open exposure is not forcibly liquidated. Later slices retain earlier strategy state and positions, '
        'so these are chronological diagnostics, not newly selected out-of-sample tests or a fresh walk-forward validation.', '',
        'M5 execution, bid/ask spread handling, configured spreads, $7 per lot round-trip FX commission, and 0.5% risk. '
        'Swaps and variable spread spikes are excluded. Cross-pair spreads remain uncalibrated placeholders in config. '
        'Crosses receive same-source historical USD conversion quotes. Each symbol has its own $10,000 account; '
        'merged results are a chronological sum of trade R, not a shared-account return. Shared portfolio limits, news gates, '
        'and the 2% daily-loss gate are not modeled in these standalone runs. Drawdown is closed-trade R, not floating account equity.', '',
        'The EURUSD Dukascopy observer control reproduces every closed trade and final open exposure of the plain production strategy. '
        'The six deterministic audit findings pass. The existing 186 unit tests also pass. '
        'Input and code hashes, HistData metadata hashes, individual trades, rejection counts, and examples are saved in '
        '`output/ims_trend_review_20260929/`. Passing tests do not certify profitability.', '',
        'The generic `run_backtest.py ims_h4_m15` command loads only the strategy timeframes and uses its fallback global symbol list. '
        'It therefore does not reproduce this explicitly configured eight-symbol M5 audit. '
        'Use `research_ims_trend_review.py` for these results. The generic runner and DEMO runner both supply 2.5R correctly.', '',
        '## Eight current symbols, January 2020 through December 2025', '',
        comparison(symbols,'2020','2026',sources[:2]), '',
        '## Same four symbols with long broker M5 history', '',
        'USDJPY, AUDUSD, EURUSD, GBPUSD. January 2020 through December 2025.', '',
        comparison(four,'2020','2026',sources), '',
        'January 2026 through July 14, the same four symbols.', '',
        comparison(four,'2026','2026-07-15',sources), '',
        '## Same five symbols in the available recent broker window', '',
        'The four above plus USDCAD. April 1, 2025 through July 14, 2026.', '',
        comparison(five,'2025-04-01','2026-07-15',sources), '',
        '## Per-symbol results, January 2020 through December 2025', '']
    for source in sources:
        cohort = symbols if source != 'mt5_icmarkets_utc' else four
        lines += [f'### {source}', '', table([(sym,metrics(selected(source,[sym],'2020','2026'))) for sym in cohort]), '']
    lines += ['## Annual four-symbol comparison', '',
              table([(f'{year} {source}',metrics(selected(source,four,str(year),str(year+1))))
                     for year in range(2020,2027) for source in sources]), '',
              '2026 contains only data through July 14.', '',
              '## Gap losses', '',
              'Stops are filled at the next available opening price when the market gaps through them. '
              'A 0.5% planned stop risk does not cap the realized loss at 0.5%. '
              'The worst observed trade on each source follows; these losses are included in every applicable table.', '',
              '| Source | Symbol | Entry time | Close time | Net R |',
              '|---|---|---|---|---:|']
    for s,t in summary['worst_trades'].items():
        lines.append(f"| {s} | {t['symbol']} | {t['open_time']} | {t['close_time']} | {t['net_r']:.2f} |")
    lines += ['',
              '## Data comparability', '',
              'HistData provenance was verified by the loader before replay. It must not be described as an independent price feed. '
              'The common M5 bars below are compared at matching UTC timestamps, rounded to eight decimals. '
              'Broker H4 candles follow broker session boundaries after UTC conversion; proxy H4 candles use UTC buckets. '
              'A broker/proxy performance difference therefore mixes candle construction, prices, and coverage. This review does not isolate those causes.', '',
              '| Symbol | Common M5 bars | Identical OHLC % | Only Dukascopy | Only HistData |',
              '|---|---:|---:|---:|---:|']
    for r in price_rows:
        lines.append(f"| {r['symbol']} | {r['common_bars']} | {r['identical_ohlc_pct']:.2f} | {r['dukascopy_only']} | {r['histdata_only']} |")
    lines += ['', '## Tracking observations', '',
              'Counts include warmup. Reactivation counts include repeated invalidation of the same origin; '
              'they are not counts of trades or proof that every reactivation should be forbidden. '
              'The explicit origin-breach reproduction establishes the invalid-candidate defect separately.', '',
              '| Source | Expired-origin reactivations | Proposals from expired origins | Closes updating a different current origin | Proposals while occupied |',
              '|---|---:|---:|---:|---:|']
    for s,a in audit.items():
        lines.append(f"| {s} | {a.get('expired_origin_reactivated',0)} | {a.get('proposal_from_previously_expired_origin',0)} | {a.get('close_updates_different_current_origin',0)} | {a.get('proposal_while_slot_occupied',0)} |")
    lines += ['', 'An example is Dukascopy USDJPY ticket 59, closed July 30, 2024. '
              'The accepted order came from a July 24 SELL origin, but its loss reset M15 state for the newer July 26 BUY origin.', '',
              'Full-run simulated order accounting, including the partial 2026 period. Broker totals cover five symbols with shorter USDCAD coverage.', '',
              '| Source | Accepted | Cancelled | Closed | Still filled | Still pending | Filled % |',
              '|---|---:|---:|---:|---:|---:|---:|']
    for s,a in summary['order_accounting'].items():
        lines.append(f"| {s} | {a['accepted']} | {a['cancelled']} | {a['closed']} | {a['filled_open']} | {a['pending']} | {a['filled_percent']:.1f} |")
    active = demo['current_eight_symbols']
    lines += ['', '## Copied DEMO evidence', '',
        f"The export contains {active['trades']} closed IMS trades on the current eight symbols, {active['wins']} winners, "
        f"net P/L ${active['net_pnl']:.2f}, money profit factor {active['profit_factor_money']:.2f}, "
        f"closed-P/L drawdown ${active['max_closed_money_drawdown']:.2f}, and a {active['max_loss_streak']}-loss maximum streak. "
        'Two additional gold trades lost $286.46; gold is already excluded. No closed GBPUSD trade appears in this export.', '',
        'These are mixed old versions and sizing, from April through September 2026, before the confirmed September 18 restart. '
        'They are not forward validation of the reviewed current code. Reported R is not normalized here because original risk and fills '
        'are not consistently reconstructable from this export; broker money includes commission and swap.', '',
        'The partial journal has 24 distinct placed tickets, 21 cancellation rows, 12 close rows, six risk rejections, and three portfolio rejections. '
        'Ten of the 24 placed tickets match closed positions in the export. That is a 41.7% lower bound on fills within this placed cohort, '
        'not a complete fill-rate estimate. Cancellation and close records cannot be treated as mutually exclusive without ticket reconciliation. '
        'The three portfolio rejections match the eight-open-trade cap in copied logs on June 19, 22, and 23. '
        'No daily-loss-limit line was found in the copied trading logs. The sample is too small to establish correlated USD loss behavior. '
        'Shared USD exposure and cross-strategy capacity still matter and are not represented by independent-symbol R totals.', '',
        '## Recommended next work', '',
        '1. Give each H4 setup and each submission attempt a stable identity. Validate a candidate against all candles since its origin. '
        'Separate invalidation memory from the policy on legitimately recovered ranges.',
        '2. Track proposals, accepted pending orders, fills, confirmed cancellations, and closes separately. '
        'Keep the accepted setup attached to its ticket across restarts; an old close must not alter a new setup. '
        'Retain the existing engine protection against cancelling filled positions.',
        '3. Rerun the unchanged parameters after those corrections, then compare entry-hours versus all-hours target cancellation '
        'and any fresh-break requirement one at a time. Do not select replacements from these diagnostic results.',
        '4. Collect the three missing broker M5 series, then validate all eight symbols on common periods. '
        'Use a new chronological walk-forward comparison and a shared-account replay before changing DEMO settings.', '',
        'On the MT5 Windows host, run:', '', '```bat',
        'cd /d C:\\fxbot',
        'python fetch_data_mt5_icmarkets.py --symbols EURAUD CADJPY GBPCAD --timeframes M5 --start 2016-01-01 --end 2026-07-15',
        '```', '',
        'Copy the resulting CSV files and any companion metadata into this repository\'s '
        '`data/historical/mt5_icmarkets_utc/` directory. Keep the actual available dates if the broker only supplies recent history. '
        'USDCAD already starts in 2025; do not invent earlier broker data. No redownload of verified HistData is required.', '',
        'No strategy was removed, promoted, or changed on the trading host by this review.', '']
    report = ROOT/'strategy_log/ims_trend_review_20260929.md'
    report.write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(summary,indent=2))
    print(report)


if __name__ == '__main__':
    main()
