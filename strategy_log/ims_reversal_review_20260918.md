# IMS Reversal review, 18 September 2026

22 September update: the [repaired-HistData rerun](ims_histdata_rerun_20260922.md)
now supersedes the HistData performance tables below. Original results remain
here for comparison; the rerun also distinguishes the completed tracking code
from the earlier research-only experiments.

21 September data update: [the HistData provenance repair](histdata_provenance_20260921.md)
established archive-specific clock rules and replaces the old conversion. Every
HistData performance table below refers to the old inputs and must be rerun
before use. The repair does not establish an independent price feed.

Update: newly collected broker candles have now been tested. See the
[IC Markets follow-up](ims_reversal_broker_review_20260918.md). Its results
supersede the deployment implications of the proxy-only experiments below.

The strategy has a plausible pullback hypothesis, but the implementation has setup-lifecycle inconsistencies and the edge is sensitive to price feed and candle boundaries. The parameter study below is research only. Production strategy code and the frozen EURUSD demo configuration were not changed.

## Decision

Keep the current numeric parameters frozen. This bounded search did not identify a robust improvement: the rolling selections underperformed the baseline in the combined Dukascopy tests. The isolated lifecycle correction is a more promising development direction, but it needs proper order-to-setup attribution, checkpoint/reconciliation support, and broker-data validation before deployment. The stored HistData results are diagnostic only because their provenance/timezone contract remains unresolved. No parameter or strategy is approved for real-money trading by this review.

## What it actually trades

For a SELL, the code finds an H4 upward structure break with a bullish fair-value gap. The H4 EMA20 must be above EMA50 with the configured separation. Price must reach the premium half of the H4 range. It then waits for an M15 close below a confirmed swing low, with a bearish gap in the earlier downswing, and places a SELL pending order halfway through that earlier M15 leg. With the current zero buffer, the stop is at the leg's swing high and the target is the H4 midpoint. BUY is the mirror image.

This deliberately trades against the H4 trend. The bet is a pullback toward the range midpoint after an M15 reversal, not that the H4 trend has permanently reversed. A midpoint is a price-range definition, not evidence of economic fair value. Large target-to-stop ratios can support low win rates, but only if those targets are reached often enough after execution costs.

Example: an H4 range of 1.1000 to 1.1200 has a 1.1100 midpoint. A confirmed M15 downswing from 1.1190 to 1.1170 can propose a SELL at 1.1180, SL 1.1190, TP 1.1100. That is 8R before costs, but the trade is fading a still-bullish H4 trend.

## Logic audit

1. The documented one-loss-per-bias rule is not persistent. `notify_loss()` clears the active bias, but the H4 scanner can immediately reconstruct the same direction and origin timestamp from its history. A deterministic synthetic example reproduces this on the next H4 bar. The initial four-year baseline audit counted 59 reactivations of loss-retired active bias identities and nine entry proposals on such identities. These are state/proposal counts, not nine proven executed retries.

2. The session block returns before the pending-target cancellation check. In a synthetic test, the same target touch cancels an unfilled order at 16:00 UTC but not at 18:00 UTC. Other structural-expiry checks still operate outside the session. Restricting new entries should not silently disable the stated target-consumed cancellation rule.

3. Cancellation compares against the current H4 midpoint, while the broker order retains its submitted target. If the range extends, the strategy can cancel even though the original target has not been reached. A synthetic submitted SELL TP of 1.1100 is incorrectly treated as reached when the midpoint moves to 1.1150 and price only falls to 1.1140, if submitted-target semantics are intended. A moving-midpoint cancellation policy would instead need to be explicitly documented and validated.

4. Close callbacks carry symbol and result, not the originating bias identity. If a trade from an older bias closes after the active bias has changed, its loss can retire the new bias. The isolated retirement experiment does not repair this attribution problem. A production correction needs a stable setup identity from order submission through reconciliation and restart.

5. H4 breaks use wick extremes rather than requiring a close beyond structure. M15 requires a close beyond a swing, but does not require the previous close to have been on the other side. The FVG check examines the earlier origin-to-swing segment and excludes the current breaking candle. These are looser definitions than a fresh, displacement-confirmed reversal. They are design choices to clarify, not justification for adding several new filters at once.

No obvious future-candle access was found in the strategy review: pivots use only bars already supplied to the strategy, and the corrected engine dispatches completed bars. This is a code review conclusion, not a formal proof of every runtime path.

The isolated research subclass fixes the three demonstrated lifecycle scenarios and passes all four synthetic checks. It is not registered for demo use and is not a complete deployment patch, particularly for setup attribution and checkpoint persistence.

## Research method

EURUSD is the active demo candidate, so the parameter tests focus on EURUSD rather than selecting a new symbol basket. Thirteen settings, including baseline, change one parameter at a time. Each rolling fold trains on four calendar years, selects the greatest net R among cases with at least 30 trades and PF >=1.10, and then tests the next two years. No later test results enter an earlier selection. The same chosen settings are tested on the stored HistData files without retuning; the later data audit prevents treating those results as independent validation.

Training: 2016-2019, 2018-2021, and 2020-2023. Validation: 2020-2021, 2022-2023, and 2024-2025. Each run has fresh strategy state and up to 180 prior calendar days of warm-up. Ending exposure remains open and is excluded from closed-trade metrics. Aggregated fold R sequences concatenate the separate test runs; their dollar balances are not one continuous account simulation.

Both feeds use M5 execution, completed H4/M15 signals, a constant 0.1-pip EURUSD spread, $7 round-trip commission per standard lot, and the corrected gap/entry-candle simulator. The runs are standalone, with the global daily-loss gate disabled and the one-position-per-strategy rule retained. Swaps, variable spreads, tick-level ordering, and broker execution anomalies are not modeled. PF is gross positive net R divided by absolute negative net R. R includes modeled commission and spread.

All parameter selection and performance evaluation stop no later than 14 July 2026. The existing forward trial is protected. Earlier research already inspected portions of these historical years, so these are retrospective rolling tests, not a newly untouched holdout. January to 14 July 2026 is explicitly a previously viewed stress period.

## Rolling test results

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | W/L streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy baseline | 112 | 26.8 | +31.80 | 1.36 | +0.284 | 16.51 | 2/13 |
| dukascopy selected | 104 | 29.8 | +13.23 | 1.17 | +0.127 | 20.75 | 3/6 |
| histdata baseline | 102 | 31.4 | +60.15 | 1.82 | +0.590 | 14.10 | 2/13 |
| histdata selected | 95 | 30.5 | +17.47 | 1.25 | +0.184 | 19.66 | 3/7 |

The three largest baseline wins were 14.67R, 10.70R, 9.22R. Removing those three trades changes the six-year net result from +31.80R to -2.80R. This is a concentration diagnostic, not a forecast or an alternative parameter selection. The winners held for roughly 62-140 hours with initial stops of about 6-8 pips. Their execution, overnight spread exposure, and omitted swaps deserve particular broker-data checks.

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | W/L streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy 2020-2021 baseline | 38 | 21.1 | -0.07 | 1.00 | -0.002 | 14.10 | 1/13 |
| dukascopy 2020-2021 M15 fractal 1 | 40 | 30.0 | +10.16 | 1.34 | +0.254 | 9.61 | 2/5 |
| dukascopy 2022-2023 baseline | 42 | 21.4 | +16.01 | 1.45 | +0.381 | 16.51 | 2/10 |
| dukascopy 2022-2023 M15 fractal 1 | 39 | 20.5 | -13.74 | 0.57 | -0.352 | 14.71 | 1/5 |
| dukascopy 2024-2025 baseline | 32 | 40.6 | +15.86 | 1.77 | +0.496 | 7.41 | 2/7 |
| dukascopy 2024-2025 EMA separation 0.20% | 25 | 44.0 | +16.81 | 2.12 | +0.672 | 6.37 | 3/6 |
| histdata 2020-2021 baseline | 36 | 22.2 | +2.38 | 1.08 | +0.066 | 14.10 | 1/13 |
| histdata 2020-2021 M15 fractal 1 | 37 | 32.4 | +13.32 | 1.49 | +0.360 | 9.61 | 3/5 |
| histdata 2022-2023 baseline | 34 | 32.4 | +41.91 | 2.86 | +1.233 | 6.34 | 2/6 |
| histdata 2022-2023 M15 fractal 1 | 33 | 18.2 | -12.65 | 0.53 | -0.383 | 13.63 | 1/7 |
| histdata 2024-2025 baseline | 32 | 40.6 | +15.86 | 1.77 | +0.496 | 7.41 | 2/7 |
| histdata 2024-2025 EMA separation 0.20% | 25 | 44.0 | +16.81 | 2.12 | +0.672 | 6.37 | 3/6 |

Selected parameters and training expectancy retention:

- 2020-2021: M15 fractal 1; training +22.25R, test +10.16R, expectancy retention 83.4%.

- 2022-2023: M15 fractal 1; training +39.98R, test -13.74R, expectancy retention -66.1%.

- 2024-2025: EMA separation 0.20%; training +21.34R, test +16.81R, expectancy retention 195.3%.

## Recent stress period, January to 14 July 2026

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | W/L streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy Frozen baseline | 9 | 22.2 | +2.43 | 1.32 | +0.270 | 4.34 | 2/4 |
| dukascopy EMA separation 0.20% | 6 | 16.7 | -1.33 | 0.76 | -0.222 | 3.33 | 1/3 |
| histdata Frozen baseline | 8 | 12.5 | -3.51 | 0.54 | -0.439 | 4.34 | 1/4 |
| histdata EMA separation 0.20% | 6 | 16.7 | -1.33 | 0.76 | -0.222 | 3.33 | 1/3 |

## Lifecycle changes tested separately, continuous 2020-2025 replay

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | W/L streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy Frozen baseline | 112 | 26.8 | +31.80 | 1.36 | +0.284 | 16.51 | 2/13 |
| dukascopy Retire losing bias | 102 | 29.4 | +42.58 | 1.55 | +0.417 | 13.29 | 2/12 |
| dukascopy Pending lifecycle correction | 108 | 26.9 | +32.88 | 1.39 | +0.304 | 15.46 | 2/13 |
| dukascopy Both lifecycle corrections | 98 | 29.6 | +43.67 | 1.59 | +0.446 | 13.06 | 2/12 |
| histdata Frozen baseline | 102 | 31.4 | +60.15 | 1.82 | +0.590 | 14.10 | 2/13 |
| histdata Retire losing bias | 94 | 34.0 | +68.75 | 2.06 | +0.731 | 13.06 | 2/12 |
| histdata Pending lifecycle correction | 98 | 31.6 | +61.23 | 1.87 | +0.625 | 14.10 | 2/13 |
| histdata Both lifecycle corrections | 90 | 34.4 | +69.84 | 2.13 | +0.776 | 13.06 | 2/12 |

These runs keep the baseline numeric parameters and are not part of parameter selection. Their continuous state differs from the reset-at-each-fold table above. Correctness changes can reduce historical profit; profit alone is not a reason to keep a documented-rule violation.

## Spread stress, constant 1.0 pip, continuous 2020-2025 replay

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | W/L streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy Frozen baseline | 112 | 25.9 | +16.01 | 1.18 | +0.143 | 16.51 | 2/13 |
| dukascopy EMA separation 0.20% | 87 | 26.4 | +22.36 | 1.33 | +0.257 | 16.18 | 3/13 |
| histdata Frozen baseline | 102 | 30.4 | +44.22 | 1.59 | +0.434 | 14.10 | 2/13 |
| histdata EMA separation 0.20% | 81 | 30.9 | +39.30 | 1.67 | +0.485 | 9.71 | 3/9 |

This is a sensitivity test, not a calibrated IC Markets spread distribution.

## H4 session sensitivity, unchanged baseline parameters

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | W/L streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy original UTC H4 | 112 | 26.8 | +31.80 | 1.36 | +0.284 | 16.51 | 2/13 |
| dukascopy resampled broker-clock H4 | 116 | 25.9 | +24.29 | 1.26 | +0.209 | 18.41 | 3/15 |
| histdata original UTC H4 | 102 | 31.4 | +60.15 | 1.82 | +0.590 | 14.10 | 2/13 |
| histdata resampled broker-clock H4 | 112 | 29.5 | +46.95 | 1.56 | +0.419 | 8.31 | 3/7 |

This resamples each proxy M5 price series into H4 candles aligned with the broker clock: UTC+3 in US daylight time and UTC+2 otherwise. M15 signals and M5 execution are unchanged. It isolates sensitivity to candle grouping, without adding actual IC Markets prices or selecting parameters on the new grouping. These are proxy prices, not broker performance estimates.

## Initial training-window sensitivity, 2016-2019

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | W/L streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| M15 fractal 1 | 73 | 28.8 | +22.25 | 1.40 | +0.305 | 19.47 | 2/17 |
| 60% range target | 88 | 23.9 | +19.74 | 1.27 | +0.224 | 23.48 | 3/19 |
| Fixed 3R target | 76 | 31.6 | +14.66 | 1.26 | +0.193 | 10.55 | 3/10 |
| Fixed 2R target | 55 | 40.0 | +7.43 | 1.21 | +0.135 | 5.41 | 3/4 |
| Frozen baseline | 75 | 25.3 | +4.70 | 1.08 | +0.063 | 18.22 | 4/15 |
| 40% range target | 57 | 28.1 | +4.40 | 1.10 | +0.077 | 11.95 | 3/7 |
| stop_buffer_1pip | 82 | 26.8 | +2.97 | 1.05 | +0.036 | 20.61 | 5/15 |
| EMA separation 0.20% | 49 | 26.5 | +2.37 | 1.06 | +0.048 | 20.88 | 4/13 |
| zone_65 | 75 | 24.0 | +0.95 | 1.02 | +0.013 | 20.43 | 4/16 |
| zone_75 | 71 | 21.1 | -4.89 | 0.92 | -0.069 | 25.74 | 4/22 |
| EMA separation 0.05% | 87 | 23.0 | -5.25 | 0.93 | -0.060 | 22.10 | 2/17 |
| ltf_fractal_3 | 71 | 22.5 | -8.42 | 0.86 | -0.119 | 20.50 | 2/11 |
| stop_buffer_2pips | 84 | 25.0 | -8.90 | 0.87 | -0.106 | 21.54 | 5/15 |

The largest in-sample result is not automatically the best deployable setting. Settings must transfer to later periods and the execution venue.

## Data limitations and broker check

All six EURUSD input files were checked through the cutoff: no duplicate timestamps, missing OHLC, inverted candles, or unsorted timestamps were found. This structural check does not establish tick completeness. Both feeds' H4 bars open at 00/04/08/12/16/20 UTC. IC Markets runtime logs show summer H4 opens at 01/05/09/13/17/21 UTC. This changes swing and FVG structure, even before price-feed differences. A second UTC-aligned feed is not a substitute for broker-session validation.

The stored feeds are strongly dependent: 66.84% of common M5 candles and 64.73% of common H4 candles have exactly identical OHLC. HistData also lacks 9,826 M5 timestamps present in Dukascopy during 2023. Price differences and missing intervals can both change signals and fills; the higher HistData result is not stronger proof of an edge.

There is an unresolved source-contract mismatch. The [HistData source FAQ](https://www.histdata.com/f-a-q/) specifies fixed EST without daylight-saving adjustments, whereas `fetch_data_histdata.py` applies America/New_York daylight-saving rules. However, the stored raw ZIP sample for 1 July 2024 08:00 matches both local datasets exactly after adding four hours, not the documented five. This sample does not establish the correct interpretation of the complete archive. Do not blindly shift the existing files: establish their provenance and verify the raw source clock first. All HistData tables in this report are quarantined diagnostics, not clean independent validation.

The prior July broker review found a much weaker portfolio edge on IC Markets than Dukascopy and retained only EURUSD for a frozen forward trial. Those older numerical tables used earlier engine behavior. Fresh IC Markets M5, M15, and H4 candles are absent from this checkout, so this review cannot approve any optimized parameter for the broker.

On the Windows host, existing EURUSD exports can be copied back. If they are absent, the existing exporter can fetch them without placing trades:

```bat
python fetch_data_mt5_icmarkets.py --symbols EURUSD --timeframes M5 M15 H4 --start 2016-01-01 --end 2026-07-15
```

Copy the three EURUSD CSVs from `data/historical/mt5_icmarkets_utc` into the matching local folder. Keep their UTC-normalized names. Missing older M5 coverage must be reported rather than silently substituting coarse execution candles.

## Reproduction

```bat
python audit_ims_reversal_logic.py
python research_ims_reversal.py --workflow
python research_ims_reversal.py --workflow --source histdata
python research_ims_reversal.py --start 2020-01-01 --end 2026-01-01 --variants baseline research_retire_loss research_pending_lifecycle research_both
python research_ims_reversal.py --source histdata --start 2020-01-01 --end 2026-01-01 --variants baseline research_retire_loss research_pending_lifecycle research_both
```

Validation: all 89 existing unit tests pass. The separate synthetic audit reproduces three lifecycle-rule discrepancies in production code and passes all four scenarios in the isolated research variant. Its successful exit means the observations matched the assertions; it does not mean production passed the three disputed rules.

Sources: `strategies/ims_reversal.py`, `live_config.py`, `engine.py`, `strategy_log/ims_reversal.md`, `strategy_log/live_demo_audit.md`, the six local EURUSD files, and copied broker logs. Input hashes, individual run metrics, signal diagnostics, closed-trade lists, and supplementary research scripts are saved in `output/ims_reversal_review_20260918`. No strategy or demo configuration was changed.
