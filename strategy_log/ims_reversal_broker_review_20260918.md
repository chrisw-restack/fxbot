# IMS Reversal broker-data follow-up, 18 September 2026

This follows the initial [logic and parameter review](ims_reversal_review_20260918.md). The newly supplied IC Markets EURUSD exports now permit direct broker-candle validation. The numerical choices and lifecycle experiment were fixed before these replays. Production strategy code, demo membership, and risk were not changed.

## Decision

Retain the frozen EURUSD forward-demo trial and its current numeric parameters. The current baseline is historically positive on broker candles, but the much deeper drawdown and long loss streak weaken the case for a robust edge. The previously selected parameter changes do not improve the combined broker validation. The lifecycle experiment also loses its profit advantage over the baseline on this feed, so the earlier proxy improvement does not justify deployment. Correctness issues still need explicit semantics and proper setup attribution; they should not be accepted or rejected solely for their historical profit.

## Method and scope

The same rolling choices from Dukascopy were carried across without broker fitting: M15 fractal 1 for 2020-2021 and 2022-2023, then EMA separation 0.20% for 2024-2025. Baseline and the isolated lifecycle experiment were also tested in each window. Additional continuous runs separate loss-bias retirement from pending-target handling. January to 14 July 2026 remains a previously viewed stress period, not a pristine holdout.

All tests use completed native broker H4/M15 bars and M5 execution, 180 calendar days of warm-up, 0.5% risk, 0.1-pip constant spread, and $7 round-trip commission per standard lot. The full demo suite, daily-loss gate, swaps, variable spreads, and tick-level ordering are not modeled. The wider-spread check uses 1.0 pip. PF uses positive versus negative net R; drawdown uses cumulative closed-trade net R. A positive historical result is not a measured demo-account return.

The lifecycle experiment remains incomplete: it retires the active bias reported by the existing callback, not a proven originating order/setup identity. Pending cancellation is moved outside entry-hour blocking and checked against the submitted target. Setup attribution and persistence through restart still need a complete production implementation. These corrections were not tuned on broker outcomes.

## Same-period proxy and broker comparison, continuous 2020-2025

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Max W/L streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy Current parameters | 112 | 26.8 | +31.80 | 1.36 | +0.284 | 16.51 | 2/13 |
| dukascopy Both lifecycle changes | 98 | 29.6 | +43.67 | 1.59 | +0.446 | 13.06 | 2/12 |
| mt5_icmarkets_utc Current parameters | 114 | 26.3 | +32.54 | 1.36 | +0.285 | 28.98 | 3/23 |
| mt5_icmarkets_utc Both lifecycle changes | 97 | 27.8 | +25.41 | 1.34 | +0.262 | 25.80 | 3/21 |

## Rolling test aggregate, 2020-2025

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Max W/L streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| Current parameters | 114 | 26.3 | +32.54 | 1.36 | +0.285 | 28.98 | 3/23 |
| Rolling parameter selection | 114 | 26.3 | +14.10 | 1.16 | +0.124 | 30.35 | 3/10 |
| Both lifecycle changes | 97 | 27.8 | +25.41 | 1.34 | +0.262 | 25.80 | 3/21 |

Each two-year window starts with fresh strategy state and account balance. Aggregated R concatenates the closed trades; it is not a single compounded account. Open exposure is not forcibly closed at a window boundary.

## Individual windows

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Max W/L streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2020-2021 Current parameters | 33 | 30.3 | +19.54 | 1.79 | +0.592 | 6.62 | 2/6 |
| 2020-2021 M15 fractal 1 | 39 | 30.8 | +20.37 | 1.70 | +0.522 | 13.15 | 2/6 |
| 2020-2021 Both lifecycle changes | 27 | 29.6 | +11.39 | 1.56 | +0.422 | 5.58 | 2/5 |
| 2022-2023 Current parameters | 47 | 14.9 | -3.15 | 0.93 | -0.067 | 28.98 | 1/23 |
| 2022-2023 M15 fractal 1 | 49 | 12.2 | -27.51 | 0.39 | -0.561 | 27.51 | 1/10 |
| 2022-2023 Both lifecycle changes | 39 | 15.4 | -5.37 | 0.85 | -0.138 | 25.80 | 1/21 |
| 2024-2025 Current parameters | 34 | 38.2 | +16.15 | 1.71 | +0.475 | 6.40 | 3/6 |
| 2024-2025 EMA separation 0.20% | 26 | 46.2 | +21.24 | 2.41 | +0.817 | 5.32 | 3/5 |
| 2024-2025 Both lifecycle changes | 31 | 41.9 | +19.40 | 1.99 | +0.626 | 4.22 | 3/4 |

## Lifecycle components, continuous 2020-2025

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Max W/L streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| Current parameters | 114 | 26.3 | +32.54 | 1.36 | +0.285 | 28.98 | 3/23 |
| Retire losing bias | 101 | 28.7 | +35.65 | 1.46 | +0.353 | 25.80 | 3/21 |
| Pending lifecycle only | 110 | 25.5 | +22.31 | 1.25 | +0.203 | 28.98 | 3/23 |
| Both lifecycle changes | 97 | 27.8 | +25.41 | 1.34 | +0.262 | 25.80 | 3/21 |

Retiring a losing bias alone improves broker net R modestly, from +32.54R to +35.65R, and lowers drawdown from 28.98R to 25.80R. The pending-handling experiment reduces profit; combining the changes produces +25.41R. This identifies which experimental component lost the proxy advantage, but does not make either incomplete implementation ready for deployment.

## Previously viewed stress period, January to 14 July 2026

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Max W/L streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| Current parameters | 8 | 0.0 | -8.67 | 0.00 | -1.084 | 8.67 | 0/8 |
| EMA separation 0.20% | 6 | 0.0 | -6.44 | 0.00 | -1.073 | 6.44 | 0/6 |
| Both lifecycle changes | 8 | 0.0 | -8.67 | 0.00 | -1.084 | 8.67 | 0/8 |

The baseline and combined lifecycle experiment each lose all eight closed trades in this recent period. The stronger EMA filter loses all six of its trades. These are small samples, but they do not support promoting an alternative setting.

## Constant 1.0-pip spread sensitivity, continuous 2020-2025

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Max W/L streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| Current parameters | 113 | 25.7 | +29.58 | 1.33 | +0.262 | 28.97 | 3/23 |
| Both lifecycle changes | 96 | 27.1 | +22.45 | 1.30 | +0.234 | 25.79 | 3/21 |

## Concentration and data quality

At the modeled 0.5% risk, the continuous baseline grows its initial $10,000 to $11,683.98 over six years, with 15.06% maximum marked-to-market equity drawdown in the simulator. This excludes swaps and the full demo suite interactions.

The longest baseline losing sequence contains 23 trades from 2022-11-04 12:35:00 to 2023-09-26 14:50:00, totaling -24.78R.

The three largest broker-baseline wins contribute 30.32R. Removing them changes the continuous baseline from +32.54R to +2.22R. This is a concentration diagnostic, not a forecast or a new selection rule.

The fresh files start on 3 January 2016 and include later forward-demo data, which was excluded. Before 15 July 2026 they contain 786,033 M5, 262,050 M15, and 16,391 H4 rows. All timestamps are ordered; no duplicate timestamps, missing OHLC, or malformed OHLC were found. The final H4 candle crossing the cutoff is also excluded from replay. H4 UTC opening hours alternate between 01/05/09/13/17/21 in summer and 02/06/10/14/18/22 in winter.

The new H4 and M15 files match all common OHLC rows in the older July export exactly. Each run uses only the fresh file for each timeframe, avoiding a mixture of overlapping snapshots. The audit records filenames, hashes, coverage, and gaps.

There are historical gaps, including 2 December 2021 from the end of the 08:20 M5 candle to 14:35 UTC. 0 baseline closed-trade positions overlap that interval. Missing bars can also affect setup state and pending orders, so this check does not establish complete tick history. The largest gaps, including holidays, are listed in the raw audit and were not filled with invented prices.

## Reproduction and artifacts

```bat
python research_ims_reversal_broker.py
```

This runs sequentially and never connects to MT5. The previous study's selected settings are frozen in the script; it does not run another parameter search. Raw results, trades, signal diagnostics, input audit, and the comparison chart are saved in `output/ims_reversal_review_20260918`. Eighteen broker replays passed saved trade-count, net-R, and date-bound checks. The forward-demo period remains excluded.
