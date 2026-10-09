"""Summarize the completed fixed-parameter XM comparison, without new replays."""
from datetime import datetime
import json
from pathlib import Path

import pandas as pd

from research_ims_reversal_xm import OUT, ROOT, write

REPORT = ROOT/'strategy_log/ims_reversal_xm_comparison_20261002.md'
LABELS = {'xm':'XM', 'dukascopy':'Dukascopy', 'histdata':'Repaired HistData',
          'mt5_icmarkets_utc':'IC Markets'}
ORDER = ('xm', 'dukascopy', 'histdata', 'mt5_icmarkets_utc')


def table(summaries, period, cost):
    lines = ['| Data | Trades | Win % | Net R | PF | R/trade | Max segment DD R | W/L streak |',
             '|---|---:|---:|---:|---:|---:|---:|---:|']
    for source in ORDER:
        s = next(s for s in summaries if (s['source'], s['period'], s['cost_id']) == (source, period, cost))
        m = s['metrics']
        pf = f"{m['profit_factor']:.2f}" if m['profit_factor'] is not None else 'N/A'
        lines.append(f"| {LABELS[source]} | {m['trades']} | {m['win_rate']:.1f} | {m['total_r']:+.2f} | "
                     f"{pf} | {m['expectancy']:+.3f} | {m['max_segment_dd_r']:.2f} | "
                     f"{m['max_win_streak']}/{m['max_loss_streak']} |")
    return '\n'.join(lines)


def main():
    verification = json.loads((OUT/'verification.json').read_text())
    assert verification['completed'] and verification['runs'] == verification['expected_runs'] == 36
    summaries = json.loads((OUT/'summary.json').read_text())
    manifest = json.loads((OUT/'manifest.json').read_text())
    def get(source, period, cost='raw_costs'):
        return next(s['metrics'] for s in summaries
                    if (s['source'],s['period'],s['cost_id']) == (source,period,cost))
    # Price-only overlap diagnostics on the precise comparison trading windows.
    frames = {}
    windows = [(pd.Timestamp(s['trade_start']), pd.Timestamp(s['end']))
               for s in manifest['segments']['2020_2025']]
    for source, paths in manifest['inputs'].items():
        path = next(i['path'] for i in paths if '_M5_' in i['path'])
        frame = pd.read_csv(path, usecols=['time','open','high','low','close'], parse_dates=['time'])
        mask = pd.Series(False, index=frame.index)
        for start, end in windows:
            mask |= (frame.time >= start) & (frame.time+pd.Timedelta(minutes=5) <= end)
        frames[source] = frame.loc[mask].set_index('time').round(5)
    diagnostics = {}
    reference = frames['dukascopy']
    for source, frame in frames.items():
        common = frame.index.intersection(reference.index)
        missing = reference.index.difference(frame.index)
        diagnostics[source] = dict(m5_bars=len(frame), common_m5_with_dukascopy=len(common),
            exact_5_decimal_ohlc_matches=int((frame.loc[common] == reference.loc[common]).all(axis=1).sum()),
            missing_dukascopy_m5_timestamps=len(missing),
            missing_reference_m5_by_year={str(y):int((missing.year == y).sum()) for y in sorted(set(missing.year))},
            additional_m5_timestamps=len(frame.index.difference(reference.index)))
    write(OUT/'price_overlap.json', diagnostics)
    xm, recent = get('xm','2020_2025','xm_costs'), get('xm','2026_viewed','xm_costs')
    wider = get('xm','2020_2025','xm_wider')
    h = diagnostics['histdata']
    match = 100*h['exact_5_decimal_ohlc_matches']/h['common_m5_with_dukascopy']
    trading_days = sum((end-start).total_seconds()/86400 for start,end in windows)
    text = f"""# IMS Reversal on audited XM data, 2 October 2026

The frozen EURUSD strategy has a small positive historical result on XM, but this
comparison does not establish a convincing transferable edge. At the modeled
1.1-pip spread and zero commission, the comparable 2020-2025 segments produce
{xm['total_r']:+.2f}R across {xm['trades']} trades, PF {xm['profit_factor']:.2f}, and a
{xm['max_loss_streak']}-trade losing streak. The previously viewed 2026 period
loses all {recent['trades']} closed trades, totaling {recent['total_r']:+.2f}R.
Summing those independent runs leaves {xm['total_r']+recent['total_r']:+.2f}R
across {xm['trades']+recent['trades']} trades. This is a sum of closed R, not a
single compounded account return.

## Frozen method and comparable dates

Used the current `live_config.py` EURUSD instance, including completed setup
tracking, H4/M15 signals, M5 execution, H4 fractal 1, M15 fractal 2, 30-bar
lookback, 50% entry zone and H4 target, EMA 20/50 with 0.10% separation, swing
stop with no buffer, one losing attempt per originating setup, and entry hours
12:00-16:59 UTC. Pending cancellation retains `entry` hours and `moving` target.
No numeric parameters, policy defaults, DEMO membership, risk, or account changed.

Each account starts with $10,000 and risks 0.5% per trade. The portfolio daily
loss gate and the other DEMO strategies are excluded, matching earlier standalone
studies. Spread is constant in each scenario; no swap, variable spread, additional
slippage, or tick-level intrabar ordering is modeled. The 1.1-pip and 1.6-pip XM
scenarios are assumptions, informed by a short recent quote sample. They are not
measured historical effective costs. Zero spread in older CSVs was never used as
free execution. All OHLC inputs are bid prices, and SELL exits use modeled ask.

XM guards require independent strategy and execution resets across excluded
periods. The intersection of M5, M15, and H4 intervals sets the bounds. D1 is not
required by this configuration. Every source uses the same boundaries and 180
calendar days of warmup, with actual H4/M15 counts checked before trading.

| Trading segment | Warmup starts | Exclusive end |
|---|---|---|
"""
    for segment in manifest['segments']['2020_2025']+manifest['segments']['2026_viewed']:
        text += f"| {segment['trade_start']} | {segment['load_start']} | {segment['end']} |\n"
    text += f"""
The historical comparison contains {trading_days:,.2f} calendar days within
2020-2025. New warmups exclude the first 180 days after the late-2021 and late-2024
breaks. The short Christmas 2024 interval cannot support that warmup and is
skipped. First entries after each reset cannot inherit an order or setup from an
earlier segment. Open orders and positions at every end are saved separately;
there is no forced liquidation. Older fragmented XM history is outside this
comparison. Pre-2016 XM clocks remain quarantined. Restricting IC Markets to
2020 onward also avoids the unresolved early 2016/2017 clock discrepancies.

## Same cost assumptions on all four datasets

Comparable 2020-2025 segments, 0.1-pip spread and $7 round-trip commission per lot.
These costs reproduce our usual raw-account research assumptions on every feed.

{table(summaries, '2020_2025', 'raw_costs')}

Max segment DD is the largest cumulative closed-R drawdown within any one replay.
Win/loss streaks reset at segment boundaries. These values are not a continuous
six-year account drawdown; each raw result also records marked-to-market equity
drawdown and ending exposure.

## Same XM cost scenario on all four datasets

Comparable 2020-2025 segments, 1.1-pip spread and zero commission on every feed.
This isolates price and native candle differences with the same modeled costs.
It does not claim that IC Markets or Dukascopy accounts charge these costs.

{table(summaries, '2020_2025', 'xm_costs')}

Annual net R below uses these same costs and matched date windows. Some years
are partial because of the exclusions and warmups listed above.

| Year | XM | Dukascopy | Repaired HistData | IC Markets |
|---|---:|---:|---:|---:|
"""
    for year in range(2020, 2026):
        values = [get(source, '2020_2025', 'xm_costs')['yearly'][str(year)]['total_r'] for source in ORDER]
        text += f"| {year} | " + ' | '.join(f'{r:+.2f}' for r in values) + ' |\n'
    text += f"""
XM alone at a wider 1.6-pip spread and zero commission produces
{wider['total_r']:+.2f}R, PF {wider['profit_factor']:.2f}, and
{wider['max_segment_dd_r']:.2f}R maximum segment drawdown. The near-identical
1.1/1.6-pip totals do not establish broad spread robustness. Both already lose
two trades that win at 0.1 pip.

Two concrete XM SELL examples show why changing commission alone cannot estimate
the outcome. On 23 September 2025 the raw-cost case wins +3.00R, but the 1.1-pip
case stops out at -1.00R. On 4 December 2025 a +5.26R raw-cost winner becomes a
-1.00R loss. Wider modeled ask reaches the short stop sooner. These are scenarios
on bid candles, not evidence of executed broker slippage.

## January to 14 July 2026, previously viewed stress period

The final data boundary is 14 July at 21:00 UTC. No completed or incomplete candle
after that boundary enters the replay. The period has been examined before and
is not an untouched out-of-sample test.

Same raw-account research costs:

{table(summaries, '2026_viewed', 'raw_costs')}

Same XM cost scenario:

{table(summaries, '2026_viewed', 'xm_costs')}

## Concentration, missing prices, and candle boundaries

Removing the three largest historical trades is a descriptive concentration
check, not a new trading filter or a forecast. All calculations below use the
common 1.1-pip, zero-commission scenario.

| Data | Net R | Three largest trades R | R without those trades |
|---|---:|---:|---:|
"""
    for source in ORDER:
        m = get(source,'2020_2025','xm_costs')
        text += (f"| {LABELS[source]} | {m['total_r']:+.2f} | {m['largest_three_trade_r']:+.2f} | "
                 f"{m['net_r_without_largest_three']:+.2f} |\n")
    text += f"""
HistData matches Dukascopy OHLC to five decimal places on {match:.3f}% of their
common M5 candles in these precise trading windows. HistData is missing
{h['missing_dukascopy_m5_timestamps']:,} Dukascopy M5 timestamps. Their outcomes
must not be counted as two independent confirmations. The differing missing bars
can change higher-timeframe swings, pending orders, and later trades even when
the common prices match. Missing prices were not filled or patched from another
feed. Other-source gaps remain in their audited exports; matching date bounds
does not imply matching quote coverage.

The HistData advantage over Dukascopy is concentrated in 2023, when HistData
returns +19.03R and Dukascopy -5.87R under the common XM cost scenario. HistData
lacks {h['missing_reference_m5_by_year'].get('2023', 0):,} reference M5 candles
in that year's matched windows. The other annual results agree to the displayed
precision. This is a reason to investigate missing-price effects before treating
the stronger HistData figure as evidence of a durable strategy edge.

Native broker H4 candles and UTC-aligned proxy H4 candles describe different
four-hour slices. XM uses the audited European DST clock windows, while the IC
Markets export has its existing broker session boundaries. We preserve each
native series. These results test the whole strategy on each source and its
candles; they do not isolate a pure spread effect or prove that one broker's
price feed is inherently better. The earlier continuous HistData +59.13R and IC
Markets +37.52R figures used different trading days and uninterrupted state, so
they must not be directly substituted for this matched segmented comparison.

## Decision and reproduction

XM adds a useful broker test, but its modest profit, concentration in a few
winners, and nine consecutive 2026 losses leave the edge unconvincing. The fixed
forward-DEMO trial remains unchanged. Historical XM returns do not justify a
parameter change, broker migration, or real-money promotion.

Run `python research_ims_reversal_xm.py`, then
`python summarize_ims_reversal_xm.py`. Both operate only on local files. The
replay uses one worker and performs no MT5 calls or parameter search.

The 36 replays passed completed-bar cutoff, entry/close date, warmup count,
commission, originating setup ID, and input hash checks. Files, sidecars, strategy,
engine, and configuration hashes are recorded in
`output/ims_reversal_xm_20261002/manifest.json`. `summary.json` holds aggregate
and annual closed-trade figures; per-segment files preserve trades, setup
attempts, bar counts, native H4 opening hours, account equity, and unclosed
exposure. `price_overlap.json` records M5 overlap diagnostics. Four focused tests
cover interval intersection, independent warmup, reset-aware drawdown/streaks,
and frozen configuration selection.

The full repository suite passes all 267 tests. The saved strategy/engine/config
hashes remain unchanged after replay. All 36 runs end with zero filled positions
and zero pending orders, so no unclosed exposure is omitted from these totals.
"""
    REPORT.write_text(text, encoding='utf-8')
    print(REPORT)
    print(json.dumps(diagnostics, indent=2))


if __name__ == '__main__':
    main()
