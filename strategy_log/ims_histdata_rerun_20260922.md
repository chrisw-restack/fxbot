# IMS Reversal performance rerun on repaired HistData, 22 September 2026

The repaired data changes the frozen original strategy's continuous 2020-2025 result from +60.15R to +57.43R, a change of -2.71R. With the completed setup-tracking correction and existing entry-hours/moving-target policy, the result is +59.13R.

## Scope and method

EURUSD IMS Reversal, matching the earlier study and current DEMO symbol. This is not the separate trend-following IMS strategy. The 15 earlier HistData cases were rerun with their original strategy code and fixed parameter choices. Nine additional runs use the completed tracking correction. An unchanged-Dukascopy control reproduced all 112 original trades exactly, including every saved trade field. This separates the repaired-data effect from strategy changes.

The original strategy is loaded from local Git revision 4cdc9eb7bc0bcd758d04af9e83f035faaa9bce09. Current tracking uses the local working tree captured in the manifest. No parameter search, DEMO configuration change, commit, push, or MT5 connection occurred. All 25 replays ran sequentially.

All runs use H4/M15 signals and M5 bid-candle execution, completed bars, up to 180 days of warm-up without orders, 0.5% risk, $10,000 starting balance, a constant 0.1-pip spread, and $7 round-trip commission per lot. The spread stress uses 1.0 pip. PF divides positive net R by absolute negative net R. Drawdown in the tables is cumulative closed-trade net R, not account equity drawdown. Full-suite competition, daily-loss limits, swaps, variable spreads, and tick-level ordering are not modeled. Open exposure is not forcibly closed at a window boundary.

All replay bars close no later than 15 July 2026 at 00:00 UTC. The forward-demo period remains protected. The historical windows were previously inspected, so these are retrospective checks, not a fresh untouched holdout.

## Continuous 2020-2025

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | W/L streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| Old HistData, frozen original code | 102 | 31.4 | +60.15 | 1.82 | +0.590 | 14.10 | 2/13 |
| Repaired HistData, frozen original code | 104 | 30.8 | +57.43 | 1.76 | +0.552 | 14.10 | 2/13 |
| Repaired HistData, current tracking/default policy | 105 | 31.4 | +59.13 | 1.78 | +0.563 | 14.10 | 2/13 |

The data repair reduces the frozen-code result by 2.71R. The completed tracking correction then adds 1.70R on the repaired data, with the same 14.10R closed-trade drawdown and 13-loss maximum streak. The accounting correction has a small profit effect in this test; its correctness does not depend on increasing historical profit.

At modeled 0.5% risk, the current default takes $10,000 to $13,282.69. Its maximum marked-to-market equity drawdown is 7.19%, and it has 0 open positions/orders at the end. This is a standalone simulated account, not a measured broker return.

The current default's three largest winners contribute 34.60R. Removing those trades leaves +24.53R. This describes concentration; it is not a forecast or a new filter.

![Closed-trade R and drawdown](../output/ims_histdata_rerun_20260922/performance.png)

## Previously selected parameters, unchanged

The frozen selections remain M15 fractal 1 in 2020-2021 and 2022-2023, then EMA separation 0.20% in 2024-2025. They were selected earlier on Dukascopy training windows and were not selected again on repaired HistData. The rows below concatenate three separate test runs with state reset at each window. Their dollar PnL is not one continuous account.

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | W/L streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| old HistData, baseline | 102 | 31.4 | +60.15 | 1.82 | +0.590 | 14.10 | 2/13 |
| old HistData, selected | 95 | 30.5 | +17.47 | 1.25 | +0.184 | 19.66 | 3/7 |
| new HistData, baseline | 104 | 30.8 | +57.43 | 1.76 | +0.552 | 14.10 | 2/13 |
| new HistData, selected | 98 | 29.6 | +14.31 | 1.20 | +0.146 | 19.66 | 3/7 |

The earlier selected parameter changes still underperform the baseline: +14.31R versus +57.43R. This rerun provides no performance case for replacing the baseline with that selected schedule.

## Separate two-year windows

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | W/L streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2020-2021, baseline, old | 36 | 22.2 | +2.38 | 1.08 | +0.066 | 14.10 | 1/13 |
| 2020-2021, baseline, repaired | 38 | 21.1 | -0.07 | 1.00 | -0.002 | 14.10 | 1/13 |
| 2020-2021, ltf_fractal_1, old | 37 | 32.4 | +13.32 | 1.49 | +0.360 | 9.61 | 3/5 |
| 2020-2021, ltf_fractal_1, repaired | 40 | 30.0 | +10.16 | 1.34 | +0.254 | 9.61 | 2/5 |
| 2020-2021, current default, repaired | 39 | 23.1 | +1.59 | 1.05 | +0.041 | 14.10 | 1/13 |
| 2022-2023, baseline, old | 34 | 32.4 | +41.91 | 2.86 | +1.233 | 6.34 | 2/6 |
| 2022-2023, baseline, repaired | 34 | 32.4 | +41.64 | 2.85 | +1.225 | 6.34 | 2/6 |
| 2022-2023, ltf_fractal_1, old | 33 | 18.2 | -12.65 | 0.53 | -0.383 | 13.63 | 1/7 |
| 2022-2023, ltf_fractal_1, repaired | 33 | 18.2 | -12.65 | 0.53 | -0.383 | 13.63 | 1/7 |
| 2022-2023, current default, repaired | 33 | 33.3 | +42.74 | 2.99 | +1.295 | 6.34 | 2/6 |
| 2024-2025, baseline, old | 32 | 40.6 | +15.86 | 1.77 | +0.496 | 7.41 | 2/7 |
| 2024-2025, baseline, repaired | 32 | 40.6 | +15.86 | 1.77 | +0.496 | 7.41 | 2/7 |
| 2024-2025, ema_sep_020pct, old | 25 | 44.0 | +16.81 | 2.12 | +0.672 | 6.37 | 3/6 |
| 2024-2025, ema_sep_020pct, repaired | 25 | 44.0 | +16.81 | 2.12 | +0.672 | 6.37 | 3/6 |
| 2024-2025, current default, repaired | 33 | 39.4 | +14.80 | 1.69 | +0.449 | 7.41 | 2/7 |

## Current setup-tracking policies, continuous 2020-2025

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | W/L streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| entry / moving | 105 | 31.4 | +59.13 | 1.78 | +0.563 | 14.10 | 2/13 |
| entry / submitted | 105 | 31.4 | +59.13 | 1.78 | +0.563 | 14.10 | 2/13 |
| all / moving | 99 | 31.3 | +58.63 | 1.83 | +0.592 | 14.10 | 2/13 |
| all / submitted | 101 | 31.7 | +60.22 | 1.83 | +0.596 | 14.10 | 2/13 |

Entry/all refers to target-touch cancellation during entry hours or all hours. Moving/submitted refers to the moving H4 target or the originally submitted target. Accepted trade TPs are never moved by these policies. The numeric entry parameters are identical.

Complete moving/submitted trade paths match under entry hours: True. They match under all hours: False.

All-hours cancellation with the submitted target produces the highest HistData total, +60.22R, only 1.09R above the existing default across six years, with unchanged maximum drawdown. The earlier IC Markets comparison favored entry-hours cancellation, +37.52R versus +27.28R, and found identical moving/submitted paths on that dataset. This small proxy-data advantage does not overturn that broker result or select a new default. No policy was changed.

## Previously viewed stress period, January to 14 July 2026

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | W/L streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline, old | 8 | 12.5 | -3.51 | 0.54 | -0.439 | 4.34 | 1/4 |
| baseline, repaired | 9 | 22.2 | +2.43 | 1.32 | +0.270 | 4.34 | 2/4 |
| ema_sep_020pct, old | 6 | 16.7 | -1.33 | 0.76 | -0.222 | 3.33 | 1/3 |
| ema_sep_020pct, repaired | 6 | 16.7 | -1.33 | 0.76 | -0.222 | 3.33 | 1/3 |
| Current tracking/default policy, repaired | 9 | 22.2 | +2.43 | 1.32 | +0.270 | 4.34 | 2/4 |

The frozen-code baseline retains the eight earlier trade entry/exit signatures and adds one SELL opened on 24 March 2026 and closed on 26 March. That trade contributes +5.95R, changing the small recent sample from a loss to a gain. This falls within the US/European DST disagreement weeks and shows why the old conversion could change the conclusion. Nine trades still provide little evidence about durability.

## Earlier incomplete lifecycle experiments

These reproduce the September 18 research subclasses for comparability. They are distinct from the completed setup-tracking implementation above and are not deployment candidates.

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | W/L streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| research_retire_loss, old | 94 | 34.0 | +68.75 | 2.06 | +0.731 | 13.06 | 2/12 |
| research_retire_loss, repaired | 96 | 33.3 | +66.03 | 1.99 | +0.688 | 13.06 | 2/12 |
| research_pending_lifecycle, old | 98 | 31.6 | +61.23 | 1.87 | +0.625 | 14.10 | 2/13 |
| research_pending_lifecycle, repaired | 100 | 31.0 | +58.52 | 1.81 | +0.585 | 14.10 | 2/13 |
| research_both, old | 90 | 34.4 | +69.84 | 2.13 | +0.776 | 13.06 | 2/12 |
| research_both, repaired | 92 | 33.7 | +67.12 | 2.05 | +0.730 | 13.06 | 2/12 |

## Constant 1.0-pip spread stress, continuous 2020-2025

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | W/L streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline, old | 102 | 30.4 | +44.22 | 1.59 | +0.434 | 14.10 | 2/13 |
| baseline, repaired | 104 | 29.8 | +41.51 | 1.54 | +0.399 | 14.10 | 2/13 |
| ema_sep_020pct, old | 81 | 30.9 | +39.30 | 1.67 | +0.485 | 9.71 | 3/9 |
| ema_sep_020pct, repaired | 82 | 30.5 | +37.61 | 1.63 | +0.459 | 9.71 | 3/9 |
| Current tracking/default policy, repaired | 105 | 30.5 | +43.21 | 1.56 | +0.411 | 14.10 | 2/13 |

## Broker-clock H4 grouping sensitivity, frozen original code

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | W/L streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| Old HistData | 112 | 29.5 | +46.95 | 1.56 | +0.419 | 8.31 | 3/7 |
| Repaired HistData | 111 | 29.7 | +48.69 | 1.59 | +0.439 | 8.31 | 3/7 |

This reproduces the earlier grouping of HistData M5 prices using UTC+3 in US DST and UTC+2 otherwise. It is a candle-boundary sensitivity check, not actual IC Markets price history or a new broker-clock verification.

## Data limits and verification

Across 2020 to 14 July 2026, 99.978% of the 478,274 common M5 candles have identical OHLC at five decimal places. HistData lacks 10,524 M5 candles present in the Dukascopy reference, including 9,799 in 2023. The near-identical observed prices and substantial missing intervals prevent treating the stronger HistData result as independent confirmation. This audit does not establish that the reference itself is complete.

The input CSVs and sidecars pass the repaired HistData provenance checks. Missing provider data and quarantined conflicting minutes remain gaps. HistData should not be treated as independent from Dukascopy. Actual broker validation and the protected forward DEMO evidence still matter; higher proxy-data R alone does not justify deployment.

All 25 saved runs passed checks on trade counts, net-R totals, PnL/risk identities, drawdown, chronological closes, and date bounds. Input, sidecar, code, and previous-result hashes remained unchanged during the run. The old result files were preserved.

Reproduce the replays with `python research_ims_histdata_rerun.py`. Results, complete trades, frozen parameter choices, input/code hashes, comparisons, and validation evidence are in `output/ims_histdata_rerun_20260922/`. The retained local `summarize.py` generates this report and its chart.

See [the data repair report](histdata_provenance_20260921.md) and [the broker setup-tracking comparison](ims_setup_tracking_20260919.md).
