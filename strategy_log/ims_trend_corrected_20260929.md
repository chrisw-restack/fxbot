# IMS trend corrections and validation, 2026-09-29

Implemented the authorized setup-tracking recommendations for `IMS_H4_M15`. DEMO membership, eight symbols, risk, 2.5R target, and entry hours remain unchanged. No trading-host deployment was performed.

The corrections weaken the evidence for IMS. Over 2020-2025, the current eight-symbol Dukascopy result falls from +27.11R to +22.70R and HistData from +22.91R to +12.44R. For the same four broker pairs, net R falls from -4.86R to -24.56R, with profit factor 0.78 and 31.65R closed-trade drawdown. The recent five-pair broker window falls from +10.64R to +1.20R across 30 trades. Complete the missing broker coverage before treating the corrected suite as validated or selecting replacement parameters.

## What changed

- Each H4 origin has a stable setup identity. Each proposal has a separate attempt identity that travels through risk, execution, the existing durable order ledger, cancellations, and trade closes.
- H4 candidate validation walks forward from the first confirmed break/FVG. An origin breach, later invalid depth, or later FVG disrespect cannot be forgotten on the next scan. Historical depth uses the range known at each candle, not the final range applied backward. Retired origins cannot silently reactivate.
- Proposals and accepted orders have separate records. Failed cancellations retain the accepted order and retry intent. Filled positions block new proposals and cannot be cancelled as pending orders. Partial fills keep their filled exposure when the unfilled remainder is cancelled.
- Wins and losses update only their originating setup. A win retires that origin; a loss preserves the original retry/cooldown policy when the origin is still current. Late duplicate cancellation and close events are idempotent.
- Pending target checks use the submitted target. The default remains entry-hours cancellation. The optional `pending_cancel_hours="all"` and `fresh_break_required=True` are research alternatives only. Sell target touches remain structural bid-price touches, not a claim that ask reached an executable take-profit.
- Cold startup now requests 300 H4 and 4,800 M15 bars with current settings, so lower-timeframe invalidations can be reconstructed across the H4 history. The new helper participates in checkpoint fingerprints. Changed code invalidates the old checkpoint and triggers a fresh warmup; the existing setup ledger remains independent.

Legacy broker orders without setup identity remain tracked and block duplicate entries. Their closes do not guess an originating setup or reset the current one. Legacy pending orders cannot receive origin-based cancellation until attributed; inspect these on the host when upgrading. This does not close or remove them automatically.

## Validation

All 206 tests pass, including 20 new IMS regression tests. They cover both-direction origin invalidation, historical depth and FVG checks, bid/ask pending behavior, cancellation failure, a fill racing with cancellation, partial fills, stale snapshots, late outcomes, cold ledger recovery, checkpoint recovery, legacy orders, and both optional policies. A frozen pre-correction EURUSD control reproduces all 36 saved trades exactly.

21 corrected sequential baseline cases and 12 separate broker policy cases completed, plus the frozen control. Source/data hashes, trades, final exposure, rejections, and policy selection are saved in `output/ims_trend_corrected_20260929/`. The initial interrupted run is retained separately and is excluded.

The baseline comparisons use the same data, date bounds, and cost model as [the original review](ims_trend_review_20260929.md): M5 fills, configured spreads, $7/lot FX commission, 0.5% planned risk, no swaps, and independent symbol accounts. They are R sums, not shared-account returns. Drawdown is closed-trade R. Shared daily-loss/news/portfolio gates are not represented. Proxy spread assumptions for crosses remain uncalibrated. HistData/Dukascopy are not independent feeds. Broker H4 candle boundaries differ from proxy H4 boundaries.

## Current eight symbols, 2020-2025

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy before | 246 | 33.74 | +27.11 | 1.16 | 0.110 | 17.16 | 3 / 10 |
| dukascopy corrected | 244 | 33.20 | +22.70 | 1.13 | 0.093 | 19.68 | 5 / 16 |
| histdata before | 231 | 33.33 | +22.91 | 1.14 | 0.099 | 19.61 | 3 / 11 |
| histdata corrected | 225 | 32.00 | +12.44 | 1.08 | 0.055 | 18.57 | 4 / 16 |

## Matched four-symbol long-history comparison, 2020-2025

USDJPY, AUDUSD, EURUSD, GBPUSD.

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy before | 134 | 35.82 | +25.21 | 1.28 | 0.188 | 17.40 | 3 / 13 |
| dukascopy corrected | 132 | 34.85 | +20.74 | 1.23 | 0.157 | 14.06 | 3 / 10 |
| histdata before | 126 | 34.92 | +19.62 | 1.22 | 0.156 | 19.61 | 3 / 13 |
| histdata corrected | 121 | 33.06 | +11.43 | 1.13 | 0.094 | 15.93 | 3 / 10 |
| mt5_icmarkets_utc before | 137 | 29.93 | -4.86 | 0.95 | -0.035 | 17.74 | 4 / 8 |
| mt5_icmarkets_utc corrected | 137 | 25.55 | -24.56 | 0.78 | -0.179 | 31.65 | 2 / 9 |

## Recent five-symbol comparison

The same four plus USDCAD. April 1, 2025 through July 14, 2026. USDCAD broker warmup uses its available January-March 2025 history.

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy before | 30 | 40.00 | -2.45 | 0.92 | -0.082 | 15.98 | 3 / 4 |
| dukascopy corrected | 32 | 34.38 | -7.36 | 0.78 | -0.230 | 15.94 | 3 / 5 |
| histdata before | 30 | 40.00 | -2.45 | 0.92 | -0.082 | 15.98 | 3 / 4 |
| histdata corrected | 32 | 34.38 | -7.36 | 0.78 | -0.230 | 15.94 | 3 / 5 |
| mt5_icmarkets_utc before | 30 | 40.00 | +10.64 | 1.57 | 0.355 | 6.22 | 4 / 5 |
| mt5_icmarkets_utc corrected | 30 | 30.00 | +1.20 | 1.06 | 0.040 | 5.33 | 2 / 5 |

## Corrected per-symbol results, 2020-2025

### dukascopy

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| USDJPY | 34 | 17.65 | -15.32 | 0.49 | -0.450 | 20.47 | 1 / 9 |
| EURAUD | 32 | 37.50 | +7.92 | 1.37 | 0.248 | 8.00 | 5 / 6 |
| CADJPY | 27 | 29.63 | -1.15 | 0.94 | -0.042 | 7.05 | 3 / 5 |
| USDCAD | 25 | 20.00 | -9.96 | 0.55 | -0.398 | 12.48 | 1 / 7 |
| AUDUSD | 22 | 27.27 | -2.71 | 0.84 | -0.123 | 12.69 | 3 / 8 |
| EURUSD | 44 | 45.45 | +23.28 | 1.91 | 0.529 | 4.29 | 4 / 4 |
| GBPCAD | 28 | 35.71 | +5.14 | 1.27 | 0.184 | 4.99 | 4 / 4 |
| GBPUSD | 32 | 43.75 | +15.48 | 1.82 | 0.484 | 4.18 | 3 / 4 |

### histdata

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| USDJPY | 30 | 16.67 | -14.53 | 0.45 | -0.484 | 19.68 | 1 / 8 |
| EURAUD | 28 | 39.29 | +8.73 | 1.48 | 0.312 | 6.90 | 5 / 5 |
| CADJPY | 25 | 24.00 | -5.94 | 0.71 | -0.238 | 10.78 | 2 / 10 |
| USDCAD | 25 | 20.00 | -9.06 | 0.57 | -0.362 | 11.58 | 1 / 7 |
| AUDUSD | 20 | 20.00 | -7.57 | 0.56 | -0.378 | 15.09 | 2 / 14 |
| EURUSD | 39 | 43.59 | +18.04 | 1.77 | 0.463 | 4.29 | 4 / 4 |
| GBPCAD | 26 | 38.46 | +7.27 | 1.43 | 0.280 | 4.99 | 4 / 4 |
| GBPUSD | 32 | 43.75 | +15.49 | 1.82 | 0.484 | 4.18 | 3 / 4 |

### mt5_icmarkets_utc

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| USDJPY | 35 | 22.86 | -10.41 | 0.65 | -0.297 | 18.18 | 3 / 13 |
| AUDUSD | 29 | 20.69 | -9.85 | 0.60 | -0.340 | 10.62 | 2 / 8 |
| EURUSD | 39 | 33.33 | +3.84 | 1.14 | 0.098 | 13.60 | 3 / 10 |
| GBPUSD | 34 | 23.53 | -8.14 | 0.71 | -0.239 | 9.33 | 1 / 4 |

## Rolling historical policy comparison

Three predeclared policies, tested one change at a time on the four broker pairs. `current` retains entry-hours target cancellation and the existing structure-break definition. `all_hours` only extends target cancellation beyond entry hours. `fresh_break` only requires the previous M15 close to be on the unbroken side of the selected fractal.

Each policy runs continuously from July 1, 2016 with earlier warmup. Rolling selection uses four years of training results and two subsequent years for evaluation. Rank eligible policies by training total R; eligibility requires at least 20 training trades and PF above 1. Ties favor current settings. If none qualifies, current settings are retained only as a comparison, not declared validated. Only trades opened and closed inside each window count. No test result enters its fold selection.

This is a rolling comparison of continuously maintained strategy states, not a simulated switch between live accounts. Pre-boundary positions can occupy a slot until they close even though their P/L is excluded from the next window. The historical dates have already appeared in prior research, so these are not untouched out-of-sample data. Full deployment validation still requires common broker coverage and a shared-account replay.

### Train 2016-07-01 to 2020-07-01; test to 2022-07-01

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| current training | 71 | 35.21 | +10.02 | 1.20 | 0.141 | 9.13 | 4 / 6 |
| all_hours training | 67 | 35.82 | +10.69 | 1.22 | 0.160 | 8.10 | 5 / 6 |
| fresh_break training | 62 | 35.48 | +12.01 | 1.27 | 0.194 | 9.54 | 3 / 7 |
| current test | 35 | 25.71 | -5.87 | 0.79 | -0.168 | 8.63 | 2 / 8 |
| all_hours test | 32 | 28.12 | -2.69 | 0.89 | -0.084 | 7.38 | 2 / 7 |
| fresh_break test | 29 | 31.03 | +0.71 | 1.03 | 0.024 | 7.48 | 3 / 7 |

Selected from training: `fresh_break`. Expectancy retention: 12.6%. Fallback because none qualified: False.

### Train 2018-07-01 to 2022-07-01; test to 2024-07-01

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| current training | 68 | 29.41 | -4.45 | 0.92 | -0.065 | 15.95 | 3 / 8 |
| all_hours training | 63 | 31.75 | +0.81 | 1.02 | 0.013 | 11.75 | 3 / 7 |
| fresh_break training | 56 | 33.93 | +5.00 | 1.12 | 0.089 | 13.33 | 3 / 7 |
| current test | 45 | 20.00 | -16.40 | 0.57 | -0.364 | 20.19 | 2 / 9 |
| all_hours test | 41 | 21.95 | -12.11 | 0.64 | -0.295 | 15.89 | 2 / 8 |
| fresh_break test | 38 | 13.16 | -22.96 | 0.35 | -0.604 | 25.09 | 1 / 19 |

Selected from training: `fresh_break`. Expectancy retention: -676.2%. Fallback because none qualified: False.

### Train 2020-07-01 to 2024-07-01; test to 2026-07-01

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| current training | 80 | 22.50 | -22.27 | 0.66 | -0.278 | 24.33 | 2 / 9 |
| all_hours training | 73 | 24.66 | -14.80 | 0.75 | -0.203 | 18.79 | 2 / 8 |
| fresh_break training | 67 | 20.90 | -22.25 | 0.61 | -0.332 | 25.09 | 3 / 19 |
| current test | 50 | 32.00 | +4.38 | 1.13 | 0.088 | 4.49 | 2 / 4 |
| all_hours test | 44 | 29.55 | -0.78 | 0.98 | -0.018 | 7.21 | 1 / 4 |
| fresh_break test | 40 | 35.00 | +7.26 | 1.27 | 0.182 | 4.76 | 2 / 4 |

Selected from training: `current`. Expectancy retention: n/a. Fallback because none qualified: True.

Combined non-overlapping test windows, July 2020 through June 2026.

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| Always current | 130 | 26.15 | -17.89 | 0.82 | -0.138 | 24.33 | 2 / 9 |
| Always all hours | 117 | 26.50 | -15.58 | 0.83 | -0.133 | 20.16 | 2 / 8 |
| Always fresh break | 107 | 26.17 | -14.99 | 0.82 | -0.140 | 25.09 | 3 / 19 |
| Training-selected policy | 117 | 25.64 | -17.87 | 0.80 | -0.153 | 25.09 | 3 / 19 |

All three fixed policies lose money across the combined broker test windows. Current settings return -17.89R, all-hours cancellation -15.58R, and the fresh-break requirement -14.99R. Training-selected policies return -17.87R. Neither alternative establishes a profitable replacement, so both remain disabled. The corrected strategy has no demonstrated broker edge across these four pairs. The full eight-symbol suite still needs the missing broker data before a keep-or-retire decision.

## Remaining broker data and host steps

A full eight-symbol broker comparison still needs M5 exports for EURAUD, CADJPY, and GBPCAD. This workstation cannot fetch them from MT5. On the trading host:

```bat
cd /d C:\fxbot
python fetch_data_mt5_icmarkets.py --symbols EURAUD CADJPY GBPCAD --timeframes M5 --start 2016-01-01 --end 2026-07-15
```

Keep the actual available dates and copy the resulting CSVs and companion metadata into `data/historical/mt5_icmarkets_utc/` here. Existing verified HistData does not need downloading again.

The changes are local and uncommitted. After reviewing the results and committing/pushing the chosen code, stop the existing bot with Ctrl+C, pull the update on the host, run the tests, and start one bot instance. Preserve `logs/setup_ledger.json`, `logs/trade_journal.csv`, and the checkpoint files. The changed checkpoint fingerprint handles the cold restart; do not delete the ledger to force startup.

```bat
git pull --ff-only
python -m unittest discover -s tests -v
python main_live.py
```

Confirm warmup completes and the startup position/order reconciliation matches MT5. Missing required history must be resolved before startup. This review does not authorize real-money trading.
