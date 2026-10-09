# XM demo connection and history inspection, 1 October 2026

Connected to `C:\Program Files\XM Global MT5\terminal64.exe`, demo account 318785505 on `XMGlobal-MT5 7`. USD virtual balance $10,000, account leverage 1:1000, retail hedging mode. FX instruments are in the Standard Ultra Low groups and have a `#` suffix. `US100Cash#` is the Nasdaq cash CFD mapped to the project research name `USTEC`. No credentials were read from `.env`, and no orders, preflights, cancellations, account changes, or bot deployment changes were made.

## Collection and terminal limit

Collected 55 raw M5/M15/H1/H4/D1 CSVs for eleven instruments, 16,212,221 rows. Requested 2008-01-01 through 2026-07-15 in broker wall-clock time, retaining completed bars only. With the measured positive UTC offsets, this excludes post-July-14 UTC prices and conservatively omits the last few hours of July 14. The 2008 start is a requested boundary, not evidence that the broker has no earlier history.

Initially the saved and reported chart setting was 100,000,000 bars, but existing timeframe caches remained limited to about 100,000 recent bars. Even after older minute-history cache files downloaded, a EURUSD M5 request for January 4-9, 2010 returned no rows. After verifying the XM account had zero positions and orders, only the XM terminal was closed gracefully and restarted. The identical request then returned 1,368 five-minute records. The final collection uses the restarted terminal; preliminary snapshots are retained separately and must not be used as coverage conclusions.

All final raw CSV hashes match the manifest. The current account and terminal identity were checked throughout collection. API failures while history loaded were retried and are recorded per request.

## Coverage and resolution

| Instrument | Returned M5 first, server clock | M5 bars | First dense M5 window | IC Markets local M5 first, UTC | Exness first dense M5 window |
|---|---|---:|---|---|---|
| EURUSD | 2008-01-02 | 1,376,039 | 2008-01-02 00:00:00 | 2016-01-03 | 2021-07-12 00:00:00 |
| GBPUSD | 2008-01-01 | 1,348,711 | 2008-01-02 00:00:00 | 2016-01-03 | 2021-07-12 00:00:00 |
| USDJPY | 2008-01-01 | 1,347,604 | 2008-01-02 00:00:00 | 2016-01-03 | 2021-07-12 00:00:00 |
| AUDUSD | 2008-01-01 | 585,753 | 2018-09-28 00:00:00 | 2016-01-03 | 2021-07-12 00:00:00 |
| NZDUSD | 2008-01-01 | 585,559 | 2018-09-28 00:00:00 | 2016-01-03 | 2021-07-13 00:00:00 |
| USDCAD | 2008-01-01 | 1,363,796 | 2008-01-02 00:00:00 | 2025-01-01 | 2021-07-12 00:00:00 |
| USDCHF | 2008-01-01 | 1,349,403 | 2008-01-02 00:00:00 | 2016-01-03 | 2021-07-12 00:00:00 |
| EURAUD | 2008-01-01 | 585,502 | 2018-09-28 00:00:00 | No single local M5 export | 2021-07-12 00:00:00 |
| CADJPY | 2008-01-01 | 1,373,302 | 2008-01-02 00:00:00 | No single local M5 export | 2021-07-13 00:00:00 |
| GBPCAD | 2008-01-01 | 585,480 | 2018-09-28 00:00:00 | No single local M5 export | 2021-07-13 00:00:00 |
| USTEC | 2011-09-19 | 683,798 | 2016-10-27 00:00:00 | 2016-01-03 | 2021-07-13 00:00:00 |

The dense-window diagnostic requires five consecutive observed weekdays with at least 150 M5 bars per day. It is not a guarantee that later history is gap-free. OHLC and tick-volume equality against higher timeframes also detects coarse records inside the archive, not only at its beginning.

| Instrument | Timeframe | Months flagged for substantial coarse records and low weekday density |
|---|---|---|
| GBPUSD | M5 | 2018-05 through 2018-09 |
| GBPUSD | M15 | 2018-05 through 2018-09 |
| USDJPY | M5 | 2018-05 through 2018-09 |
| USDJPY | M15 | 2018-05 through 2018-09 |
| AUDUSD | M5 | 2008-01 through 2018-09 |
| AUDUSD | M15 | 2008-01 through 2018-09 |
| AUDUSD | H1 | 2008-01 through 2018-03 |
| AUDUSD | H4 | 2008-01 through 2018-03 |
| NZDUSD | M5 | 2008-01 through 2018-09 |
| NZDUSD | M15 | 2008-01 through 2018-09 |
| NZDUSD | H1 | 2008-01 through 2018-03 |
| NZDUSD | H4 | 2008-01 through 2018-03 |
| USDCAD | M5 | 2018-08 through 2018-09 |
| USDCAD | M15 | 2018-08 through 2018-09 |
| USDCHF | M5 | 2018-05 through 2018-09 |
| USDCHF | M15 | 2018-05 through 2018-09 |
| EURAUD | M5 | 2008-01 through 2018-09 |
| EURAUD | M15 | 2008-01 through 2018-09 |
| EURAUD | H1 | 2008-01 through 2018-03 |
| EURAUD | H4 | 2008-01 through 2018-03 |
| GBPCAD | M5 | 2008-01 through 2018-09 |
| GBPCAD | M15 | 2008-01 through 2018-09 |
| GBPCAD | H1 | 2008-01 through 2018-03 |
| GBPCAD | H4 | 2008-01 through 2018-03 |
| USTEC | M5 | 2011-09 through 2016-10 |
| USTEC | M15 | 2011-09 through 2016-10 |
| USTEC | H1 | 2011-09 through 2016-04 |
| USTEC | H4 | 2011-09 through 2016-05 |

These are investigation flags, not an automatic approval or complete list of bad intervals. A low-count partial month or holiday can differ from a genuine hole. Native D1 weekend/short-session records also need review. Replay preparation must audit required timeframes together, split around unusable intervals, and re-establish warmup state. Do not fill holes with another broker or replay hourly bars as M5 candles.

## Historical clock evidence

The current tick epoch is approximately three hours ahead of UTC. Each available M5 reference comparison tests shifts of zero, two, and three hours using consecutive return rank correlation, split by month and European/US DST disagreement periods. Thresholds are at least 50 matched returns, correlation at least 0.8, and a 0.3 margin over the next offset. References and raw inputs are bound to their SHA256 hashes.

| Instrument | Compatible rules in verified windows | Verified windows | Overlapping windows failing thresholds |
|---|---|---:|---:|
| EURUSD | european_dst | 164 | 0 |
| GBPUSD | european_dst | 161 | 0 |
| USDJPY | european_dst | 161 | 0 |
| AUDUSD | european_dst | 122 | 0 |
| NZDUSD | european_dst | 122 | 0 |
| USDCAD | european_dst | 164 | 0 |
| USDCHF | european_dst | 161 | 0 |
| EURAUD | european_dst | 122 | 0 |
| CADJPY | european_dst | 164 | 0 |
| GBPCAD | european_dst | 122 | 0 |
| USTEC | european_dst | 153 | 0 |

Native UTC Dukascopy is the primary reference. Independent checks of EURUSD/GBPUSD/USDJPY in March and October-November 2016, March and October-November 2017, and March 2026 identify the European rule for XM. An initial comparison against the existing IC Markets UTC exports appeared to suggest a changing XM rule. The second reference corrected that interpretation: the IC Markets export appears one hour early in the March/October-November 2016 and March 2017 disagreement weeks. `independent_clock_check.json` records the native-UTC cross-check. `icmarkets_utc_reference_check.json` separately measures the IC Markets export against native UTC and records the required one-hour correction in those older weeks. The IC Markets historical conversion needs a separate provenance audit before old broker-specific session results are treated as settled. No IC Markets file or strategy result was changed in this task.

The current IC Markets US-DST conversion must not be reused for XM. Earlier years without a UTC reference and failed overlapping windows remain unverified. No raw timestamp has been silently converted to UTC.

## Quotes and contract constraints

Two quote samples were taken after history collection. The first, 2026-10-01T12:29:18.695984+00:00 through 2026-10-01T12:30:17.821228+00:00, includes widening around 12:30 UTC. A later minute was collected separately, 2026-10-01T12:38:24.374566+00:00 through 2026-10-01T12:39:23.497677+00:00. The table uses the later sample; both raw sets and their hashes are retained. These are short demo quote observations, not proof of NY-open, news, rollover, or realized execution costs. An earlier sample was interrupted by history loading and is excluded from conclusions. FX spreads use project pips; USTEC uses index price points.

| Instrument | Mean spread | P95 spread | Fresh samples / distinct ticks | Minimum lot / lot step | Swap mode |
|---|---:|---:|---|---|---:|
| EURUSD | 1.068 | 1.200 | 60 / 44 | 0.01 / 0.01 | 0 |
| GBPUSD | 1.157 | 1.300 | 60 / 56 | 0.01 / 0.01 | 0 |
| USDJPY | 1.048 | 1.400 | 60 / 59 | 0.01 / 0.01 | 0 |
| AUDUSD | 1.393 | 1.500 | 60 / 43 | 0.01 / 0.01 | 0 |
| NZDUSD | 1.998 | 2.100 | 60 / 44 | 0.01 / 0.01 | 0 |
| USDCAD | 2.243 | 2.300 | 60 / 47 | 0.01 / 0.01 | 0 |
| USDCHF | 1.667 | 1.800 | 60 / 51 | 0.01 / 0.01 | 0 |
| EURAUD | 3.492 | 3.705 | 60 / 57 | 0.01 / 0.01 | 0 |
| CADJPY | 3.108 | 3.200 | 60 / 59 | 0.01 / 0.01 | 0 |
| GBPCAD | 3.755 | 3.905 | 60 / 59 | 0.01 / 0.01 | 0 |
| USTEC | 1.950 | 1.950 | 60 / 60 | 0.1 / 0.1 | 3 |

FX contracts use 100,000 base-currency units per standard lot. Nasdaq cash uses a contract size of 1, USD profit currency, and a 0.1 minimum lot and lot step. A 100-point entry-to-stop distance at the minimum lot implies $10 of gross price risk. Nasdaq cash uses a different minimum lot/step from Exness. Minimum lot and risk-rounding effects must be checked at the same research balance. High account leverage does not reduce the cash loss at the stop.

The snapshot reports swap mode 0 for FX, despite nonzero swap-long/short fields. [MetaQuotes documents disabled swap mode](https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants); those unused values must not be treated as charged overnight financing. Nasdaq cash reports enabled swap mode 3 in USD margin currency, displayed long debit $5.00 and short credit $0.74 per lot for ordinary rollover, and triple rollover on Friday. Account eligibility and actual charges have not been measured with trades.

XM publishes spread-only pricing in its [trading-conditions help](https://www.xm.com/help-center/trading-conditions/faq-why-are-rollover-rates-tripled). Our IC Markets FX backtests include $7 round-trip commission per standard lot. Compare total cost, not raw spreads alone. The source spread column is in MT5 integer points and is not necessarily the average spread at an entry. Historical fill-cost scenarios must be calibrated independently.

## Research decision

Keep the raw snapshot in `output/xm_inspection_20261001_final/history`, outside approved datasets. The loader refuses XM exports without a review status; the raw files also declare an unsupported unreviewed clock basis. No strategy replay, parameter optimization, broker migration, or real-money promotion was performed.

Next, audit the existing IC Markets timestamp discrepancy and prepare provenance-bound UTC datasets with explicit valid intervals and native session handling, then compare frozen strategy parameters on matched broker windows with each broker’s full cost model. Extra early history may provide additional evidence, but another broker is not by itself an untouched strategy validation sample.

Validation: all 249 unit tests pass; raw file hashes, terminal/account identity, old-window probes before/after restart, resolution diagnostics, native-UTC clock comparisons, and both post-download quote samples were checked.
