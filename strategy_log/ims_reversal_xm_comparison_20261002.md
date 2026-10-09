# IMS Reversal on audited XM data, 2 October 2026

The frozen EURUSD strategy has a small positive historical result on XM, but this
comparison does not establish a convincing transferable edge. At the modeled
1.1-pip spread and zero commission, the comparable 2020-2025 segments produce
+11.55R across 97 trades, PF 1.16, and a
14-trade losing streak. The previously viewed 2026 period
loses all 9 closed trades, totaling -9.00R.
Summing those independent runs leaves +2.55R
across 106 trades. This is a sum of closed R, not a
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
| 2020-01-01 00:00:00 | 2019-07-05 00:00:00 | 2021-10-31 18:00:00 |
| 2022-04-29 22:00:00 | 2021-10-31 22:00:00 | 2024-12-23 22:00:00 |
| 2025-06-29 22:00:00 | 2024-12-31 22:00:00 | 2026-01-01 00:00:00 |
| 2026-01-01 00:00:00 | 2025-07-05 00:00:00 | 2026-07-14 21:00:00 |

The historical comparison contains 1,823.83 calendar days within
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

| Data | Trades | Win % | Net R | PF | R/trade | Max segment DD R | W/L streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| XM | 97 | 25.8 | +14.89 | 1.19 | +0.154 | 18.16 | 3/14 |
| Dukascopy | 92 | 26.1 | +8.99 | 1.12 | +0.098 | 16.51 | 2/13 |
| Repaired HistData | 84 | 31.0 | +34.62 | 1.57 | +0.412 | 14.10 | 2/13 |
| IC Markets | 93 | 26.9 | +27.60 | 1.38 | +0.297 | 25.78 | 3/20 |

Max segment DD is the largest cumulative closed-R drawdown within any one replay.
Win/loss streaks reset at segment boundaries. These values are not a continuous
six-year account drawdown; each raw result also records marked-to-market equity
drawdown and ending exposure.

## Same XM cost scenario on all four datasets

Comparable 2020-2025 segments, 1.1-pip spread and zero commission on every feed.
This isolates price and native candle differences with the same modeled costs.
It does not claim that IC Markets or Dukascopy accounts charge these costs.

| Data | Trades | Win % | Net R | PF | R/trade | Max segment DD R | W/L streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| XM | 97 | 23.7 | +11.55 | 1.16 | +0.119 | 16.26 | 3/14 |
| Dukascopy | 92 | 26.1 | +15.74 | 1.23 | +0.171 | 14.74 | 2/13 |
| Repaired HistData | 84 | 31.0 | +40.64 | 1.72 | +0.484 | 13.00 | 2/13 |
| IC Markets | 93 | 25.8 | +30.59 | 1.44 | +0.329 | 23.90 | 3/20 |

Annual net R below uses these same costs and matched date windows. Some years
are partial because of the exclusions and warmups listed above.

| Year | XM | Dukascopy | Repaired HistData | IC Markets |
|---|---:|---:|---:|---:|
| 2020 | +12.51 | +14.65 | +14.65 | +23.24 |
| 2021 | -4.61 | -7.16 | -7.16 | +2.81 |
| 2022 | -7.43 | +0.07 | +0.07 | -4.89 |
| 2023 | +5.23 | -5.87 | +19.03 | -0.87 |
| 2024 | +4.71 | +9.02 | +9.02 | +6.80 |
| 2025 | +1.14 | +5.03 | +5.03 | +3.49 |

XM alone at a wider 1.6-pip spread and zero commission produces
+11.48R, PF 1.16, and
16.33R maximum segment drawdown. The near-identical
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

| Data | Trades | Win % | Net R | PF | R/trade | Max segment DD R | W/L streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| XM | 9 | 0.0 | -9.75 | 0.00 | -1.083 | 9.75 | 0/9 |
| Dukascopy | 9 | 22.2 | +2.43 | 1.32 | +0.270 | 4.34 | 2/4 |
| Repaired HistData | 9 | 22.2 | +2.43 | 1.32 | +0.270 | 4.34 | 2/4 |
| IC Markets | 8 | 0.0 | -8.67 | 0.00 | -1.084 | 8.67 | 0/8 |

Same XM cost scenario:

| Data | Trades | Win % | Net R | PF | R/trade | Max segment DD R | W/L streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| XM | 9 | 0.0 | -9.00 | 0.00 | -1.000 | 9.00 | 0/9 |
| Dukascopy | 9 | 22.2 | +3.23 | 1.46 | +0.359 | 4.00 | 2/4 |
| Repaired HistData | 9 | 22.2 | +3.23 | 1.46 | +0.359 | 4.00 | 2/4 |
| IC Markets | 8 | 0.0 | -8.05 | 0.00 | -1.007 | 8.05 | 0/8 |

## Concentration, missing prices, and candle boundaries

Removing the three largest historical trades is a descriptive concentration
check, not a new trading filter or a forecast. All calculations below use the
common 1.1-pip, zero-commission scenario.

| Data | Net R | Three largest trades R | R without those trades |
|---|---:|---:|---:|
| XM | +11.55 | +23.83 | -12.27 |
| Dukascopy | +15.74 | +23.24 | -7.49 |
| Repaired HistData | +40.64 | +26.30 | +14.34 |
| IC Markets | +30.59 | +27.65 | +2.95 |

HistData matches Dukascopy OHLC to five decimal places on 99.979% of their
common M5 candles in these precise trading windows. HistData is missing
10,375 Dukascopy M5 timestamps. Their outcomes
must not be counted as two independent confirmations. The differing missing bars
can change higher-timeframe swings, pending orders, and later trades even when
the common prices match. Missing prices were not filled or patched from another
feed. Other-source gaps remain in their audited exports; matching date bounds
does not imply matching quote coverage.

The HistData advantage over Dukascopy is concentrated in 2023, when HistData
returns +19.03R and Dukascopy -5.87R under the common XM cost scenario. HistData
lacks 9,799 reference M5 candles
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
