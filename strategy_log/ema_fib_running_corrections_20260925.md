# EmaFib Running corrections and validation, 25 September 2026

Status: local strategy corrections completed at the user's request. Numeric parameters, seven-pair DEMO membership, and risk are unchanged. This work does not deploy or restart the trading host, and it does not authorize real-money trading. The earlier review describes the frozen original implementation; use this report for corrected results.

## Assessment and recommendation

The tracking defects are real, but they do not explain away Running's historical profit. Tracking-only results barely change for the six matched pairs; the seven-pair Dukascopy/HistData runs add one USDCAD loss. Correcting the running extreme reduces six-pair net R from +33.59 to +27.03 on Dukascopy, +42.41 to +35.40 on verified HistData, and +17.31 to +13.26 on IC Markets. Keep both correctness fixes rather than selecting the flawed implementation for its higher return.

The corrected broker result is a weak basis for continued use: 128 trades over six years, PF 1.13, expectancy +0.104R/trade, maximum closed-trade drawdown 22.73R, and 22 consecutive losses. The most recent historical test, 2024 through 2025, loses 15.10R with PF 0.59. That test also loses on Dukascopy and HistData. Earlier tests are WEAK for 2020 through 2021 and STRONG for 2022 through 2023 on the long-history sources. The strategy no longer deserves a blanket STRONG validation label.

January through 14 July 2026 produces only four trades and about +1.10R on each source. That sample cannot overturn the recent failed test. The one-pip broker spread replay remains positive at +13.02R, so the result is not solely an artifact of the default narrow spread; actual financing and execution remain unmodeled.

I recommend pausing new Running entries in the default DEMO suite and retaining the corrected strategy for research. Membership has not been changed by this work. A new parameter search should be a separate, small, train-only experiment with untouched evaluation periods and broker confirmation. Selecting winning pairs or the best parameter combination from these same completed tests would overstate the evidence. No numeric optimization was performed here.

## What changed

Order proposals now become tracked exposure only after acceptance. Fills, cancellations, and final closes come from execution callbacks. A bid-price touch no longer clears a pending BUY before the ask actually reaches its entry. Failed cancellations retain ownership, and a filled position keeps its originating anchor even when later fractals form. Duplicate closes and stale snapshots cannot reopen finished orders. Partial closes and cancellation of an unfilled remainder preserve the filled position.

New signals carry setup and attempt identities. The existing setup ledger can recover the originating anchor after a cold restart; checkpoints preserve the complete state when their configuration fingerprint matches. Inherited orders without recorded origin remain managed, but a loss does not guess an anchor from current market state. Preserve logs/setup_ledger.json when updating the host. The correction cannot reconstruct missing metadata for old orders.

The running extreme now starts with every completed close from the actual fractal anchor through its confirmation candle. Previously it started with the confirmation close alone. A BUY example with a known 1.114 close before confirmation and a 1.108 confirmation close now starts at 1.114. SELL uses the mirrored lowest close. This uses only completed information. EMA, ATR, FVG, minimum stop, entry hours, Fibonacci parameters, repricing threshold, and the rule allowing filled positions to run to SL/TP are unchanged.

The research control called tracking applies only the lifecycle correction and deliberately retains the old extreme initialization. Corrected applies both fixes. Original is loaded from the reviewed Git revision, not reconstructed by undoing selected lines. These controls measure the effects separately; the production strategy contains both corrections.

## Six matched pairs, 2020 through 2025

EURUSD, GBPUSD, AUDUSD, NZDUSD, USDJPY, and USDCHF. USDCAD is excluded from all three sources because broker history starts in January 2025.

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy, original | 137 | 29.20 | +33.59 | 1.33 | 0.245 | 19.47 | 4 / 12 |
| dukascopy, tracking | 137 | 29.20 | +33.59 | 1.33 | 0.245 | 19.47 | 4 / 12 |
| dukascopy, corrected | 134 | 28.36 | +27.03 | 1.27 | 0.202 | 21.34 | 4 / 14 |
| histdata, original | 137 | 29.93 | +42.41 | 1.43 | 0.310 | 19.47 | 4 / 12 |
| histdata, tracking | 137 | 29.93 | +42.41 | 1.43 | 0.310 | 19.47 | 4 / 12 |
| histdata, corrected | 132 | 28.79 | +35.40 | 1.36 | 0.268 | 21.34 | 4 / 14 |
| mt5_icmarkets_utc, original | 130 | 26.15 | +17.31 | 1.17 | 0.133 | 24.10 | 4 / 23 |
| mt5_icmarkets_utc, tracking | 130 | 26.15 | +17.31 | 1.17 | 0.133 | 24.10 | 4 / 23 |
| mt5_icmarkets_utc, corrected | 128 | 25.78 | +13.26 | 1.13 | 0.104 | 22.73 | 4 / 22 |

![Cumulative closed-trade net R by source and correction](../output/ema_fib_running_corrections_20260925/correction_comparison.png)

## Seven pairs on long-history sources

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy, original | 156 | 28.85 | +35.38 | 1.31 | 0.227 | 25.37 | 6 / 12 |
| dukascopy, tracking | 157 | 28.66 | +34.36 | 1.30 | 0.219 | 26.39 | 6 / 12 |
| dukascopy, corrected | 155 | 27.74 | +26.78 | 1.23 | 0.173 | 28.27 | 6 / 12 |
| histdata, original | 156 | 29.49 | +44.21 | 1.39 | 0.283 | 25.37 | 6 / 12 |
| histdata, tracking | 157 | 29.30 | +43.19 | 1.38 | 0.275 | 26.39 | 6 / 12 |
| histdata, corrected | 153 | 28.10 | +35.14 | 1.31 | 0.230 | 28.27 | 6 / 12 |

## Seven pairs, January through 14 July 2026

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy, original | 4 | 50.00 | +1.10 | 1.54 | 0.275 | 2.05 | 1 / 2 |
| dukascopy, tracking | 4 | 50.00 | +1.10 | 1.54 | 0.275 | 2.05 | 1 / 2 |
| dukascopy, corrected | 4 | 50.00 | +1.10 | 1.54 | 0.275 | 2.05 | 1 / 2 |
| histdata, original | 4 | 50.00 | +1.10 | 1.54 | 0.275 | 2.05 | 1 / 2 |
| histdata, tracking | 4 | 50.00 | +1.10 | 1.54 | 0.275 | 2.05 | 1 / 2 |
| histdata, corrected | 4 | 50.00 | +1.10 | 1.54 | 0.275 | 2.05 | 1 / 2 |
| mt5_icmarkets_utc, original | 4 | 50.00 | +1.10 | 1.53 | 0.274 | 2.05 | 1 / 2 |
| mt5_icmarkets_utc, tracking | 4 | 50.00 | +1.10 | 1.53 | 0.274 | 2.05 | 1 / 2 |
| mt5_icmarkets_utc, corrected | 4 | 50.00 | +1.10 | 1.53 | 0.274 | 2.05 | 1 / 2 |

## Corrected results by pair, 2020 through 2025

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy, EURUSD | 17 | 17.65 | -6.16 | 0.57 | -0.362 | 7.13 | 1 / 7 |
| histdata, EURUSD | 17 | 17.65 | -6.16 | 0.57 | -0.362 | 7.13 | 1 / 7 |
| mt5_icmarkets_utc, EURUSD | 16 | 18.75 | -5.21 | 0.61 | -0.326 | 6.10 | 1 / 6 |
| dukascopy, GBPUSD | 41 | 24.39 | +17.24 | 1.52 | 0.420 | 18.64 | 2 / 17 |
| histdata, GBPUSD | 42 | 26.19 | +25.15 | 1.76 | 0.599 | 18.64 | 2 / 17 |
| mt5_icmarkets_utc, GBPUSD | 36 | 22.22 | +12.44 | 1.42 | 0.346 | 16.72 | 2 / 15 |
| dukascopy, AUDUSD | 8 | 37.50 | +7.33 | 2.44 | 0.916 | 3.06 | 2 / 3 |
| histdata, AUDUSD | 8 | 37.50 | +7.33 | 2.44 | 0.916 | 3.06 | 2 / 3 |
| mt5_icmarkets_utc, AUDUSD | 8 | 25.00 | +5.26 | 1.86 | 0.657 | 3.06 | 1 / 3 |
| dukascopy, NZDUSD | 9 | 66.67 | +14.97 | 5.90 | 1.663 | 1.02 | 3 / 1 |
| histdata, NZDUSD | 9 | 66.67 | +14.97 | 5.90 | 1.663 | 1.02 | 3 / 1 |
| mt5_icmarkets_utc, NZDUSD | 7 | 57.14 | +8.78 | 3.87 | 1.254 | 1.02 | 2 / 1 |
| dukascopy, USDJPY | 52 | 25.00 | -6.92 | 0.83 | -0.133 | 16.64 | 2 / 9 |
| histdata, USDJPY | 49 | 24.49 | -6.47 | 0.83 | -0.132 | 16.19 | 2 / 9 |
| mt5_icmarkets_utc, USDJPY | 52 | 23.08 | -10.34 | 0.75 | -0.199 | 20.21 | 2 / 18 |
| dukascopy, USDCAD | 21 | 23.81 | -0.26 | 0.98 | -0.012 | 9.86 | 2 / 7 |
| histdata, USDCAD | 21 | 23.81 | -0.26 | 0.98 | -0.012 | 9.86 | 2 / 7 |
| dukascopy, USDCHF | 7 | 42.86 | +0.58 | 1.14 | 0.083 | 3.06 | 2 / 3 |
| histdata, USDCHF | 7 | 42.86 | +0.58 | 1.14 | 0.083 | 3.06 | 2 / 3 |
| mt5_icmarkets_utc, USDCHF | 9 | 44.44 | +2.34 | 1.46 | 0.259 | 3.53 | 3 / 3 |

## Corrected calendar years, six matched pairs

Closing-year slices of the continuous 2020 through 2025 replays.

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy, 2020 | 26 | 19.23 | +2.06 | 1.09 | 0.079 | 20.61 | 4 / 14 |
| dukascopy, 2021 | 2 | 100.00 | +3.32 | n/a | 1.662 | 0.00 | 2 / 0 |
| dukascopy, 2022 | 45 | 35.56 | +20.62 | 1.70 | 0.458 | 6.13 | 3 / 6 |
| dukascopy, 2023 | 16 | 31.25 | +4.71 | 1.42 | 0.294 | 6.26 | 3 / 4 |
| dukascopy, 2024 | 21 | 19.05 | -7.03 | 0.60 | -0.335 | 8.78 | 2 / 8 |
| dukascopy, 2025 | 24 | 25.00 | +3.35 | 1.18 | 0.140 | 8.17 | 3 / 8 |
| histdata, 2020 | 26 | 19.23 | +2.06 | 1.09 | 0.079 | 20.61 | 4 / 14 |
| histdata, 2021 | 2 | 100.00 | +3.32 | n/a | 1.662 | 0.00 | 2 / 0 |
| histdata, 2022 | 45 | 35.56 | +20.62 | 1.70 | 0.458 | 6.13 | 3 / 6 |
| histdata, 2023 | 15 | 33.33 | +12.06 | 2.17 | 0.804 | 4.07 | 3 / 4 |
| histdata, 2024 | 20 | 20.00 | -6.02 | 0.63 | -0.301 | 8.22 | 2 / 8 |
| histdata, 2025 | 24 | 25.00 | +3.35 | 1.18 | 0.140 | 8.17 | 3 / 8 |
| mt5_icmarkets_utc, 2020 | 22 | 22.73 | +5.97 | 1.32 | 0.271 | 16.65 | 4 / 12 |
| mt5_icmarkets_utc, 2021 | 2 | 100.00 | +4.68 | n/a | 2.341 | 0.00 | 2 / 0 |
| mt5_icmarkets_utc, 2022 | 47 | 31.91 | +14.14 | 1.43 | 0.301 | 6.13 | 3 / 6 |
| mt5_icmarkets_utc, 2023 | 14 | 28.57 | +3.56 | 1.35 | 0.254 | 7.38 | 3 / 7 |
| mt5_icmarkets_utc, 2024 | 19 | 21.05 | -4.75 | 0.69 | -0.250 | 8.22 | 1 / 8 |
| mt5_icmarkets_utc, 2025 | 24 | 12.50 | -10.34 | 0.52 | -0.431 | 14.52 | 2 / 14 |

## Historical rolling validation

Four-year training and two-year test windows use the same fixed parameters throughout. Training windows are 2016 through 2019, 2018 through 2021, and 2020 through 2023. Tests are 2020 through 2021, 2022 through 2023, and 2024 through 2025. Each side starts fresh. The first training period has no pre-2016 warm-up because the files start in January 2016. Later runs have 180 days of warm-up. Broker validation uses only the final fold and six matched pairs; Dukascopy and HistData use all seven pairs.

These periods were used in earlier strategy development. This is historical revalidation, not fresh unseen out-of-sample evidence. No parameter, source, or symbol selection occurs in these folds. Expectancy retention is test R/trade divided by training R/trade; it is undefined when training expectancy is nonpositive. A losing test fails regardless of retention.

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy, test 2020, train | 64 | 28.12 | +25.09 | 1.54 | 0.392 | 11.80 | 3 / 7 |
| dukascopy, test 2020, test | 41 | 24.39 | +5.11 | 1.16 | 0.125 | 26.50 | 6 / 12 |
| dukascopy, test 2022, train | 62 | 27.42 | +21.76 | 1.46 | 0.351 | 26.50 | 6 / 12 |
| dukascopy, test 2022, test | 65 | 33.85 | +25.48 | 1.58 | 0.392 | 8.18 | 3 / 8 |
| dukascopy, test 2024, train | 106 | 30.19 | +30.59 | 1.40 | 0.289 | 28.27 | 6 / 12 |
| dukascopy, test 2024, test | 49 | 22.45 | -3.81 | 0.90 | -0.078 | 16.93 | 3 / 11 |
| histdata, test 2020, train | 63 | 26.98 | +23.53 | 1.50 | 0.374 | 11.76 | 3 / 9 |
| histdata, test 2020, test | 41 | 24.39 | +5.11 | 1.16 | 0.125 | 26.50 | 6 / 12 |
| histdata, test 2022, train | 59 | 27.12 | +18.79 | 1.42 | 0.318 | 26.50 | 6 / 12 |
| histdata, test 2022, test | 64 | 34.38 | +32.83 | 1.76 | 0.513 | 8.18 | 3 / 8 |
| histdata, test 2024, train | 105 | 30.48 | +37.94 | 1.50 | 0.361 | 28.27 | 6 / 12 |
| histdata, test 2024, test | 48 | 22.92 | -2.80 | 0.93 | -0.058 | 16.38 | 3 / 11 |
| mt5_icmarkets_utc, test 2024, train | 85 | 30.59 | +28.35 | 1.46 | 0.334 | 16.65 | 4 / 12 |
| mt5_icmarkets_utc, test 2024, test | 43 | 16.28 | -15.10 | 0.59 | -0.351 | 22.73 | 2 / 22 |

| Source | Test starts | Expectancy retention | Verdict |
|---|---|---:|---|
| dukascopy | 2020 | 31.8% | WEAK |
| dukascopy | 2022 | 111.7% | STRONG |
| dukascopy | 2024 | -27.0% | FAIL |
| histdata | 2020 | 33.4% | WEAK |
| histdata | 2022 | 161.1% | STRONG |
| histdata | 2024 | -16.2% | FAIL |
| mt5_icmarkets_utc | 2024 | -105.2% | FAIL |

## One-pip spread stress, corrected six-pair strategy

Full replays use one pip spread on every pair, retaining commission. This can change which pending orders fill.

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy, six_2020_2025 | 134 | 28.36 | +27.03 | 1.27 | 0.202 | 21.34 | 4 / 14 |
| dukascopy, six_spread_1pip | 133 | 28.57 | +28.60 | 1.29 | 0.215 | 21.34 | 4 / 14 |
| histdata, six_2020_2025 | 132 | 28.79 | +35.40 | 1.36 | 0.268 | 21.34 | 4 / 14 |
| histdata, six_spread_1pip | 131 | 29.01 | +36.16 | 1.38 | 0.276 | 21.34 | 4 / 14 |
| mt5_icmarkets_utc, six_2020_2025 | 128 | 25.78 | +13.26 | 1.13 | 0.104 | 22.73 | 4 / 22 |
| mt5_icmarkets_utc, six_spread_1pip | 128 | 25.78 | +13.02 | 1.13 | 0.102 | 22.73 | 4 / 22 |

## Illustrative financing debit, corrected six-pair strategy

A fixed-path sensitivity subtracts $0, $3, or $7 per lot per 24 hours held. It is not actual broker swap. Credits, rollover timing, triple-swap days, changed sizing, and compounding are excluded.

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy, $0/lot/day | 134 | 28.36 | +27.03 | 1.27 | 0.202 | 21.34 | 4 / 14 |
| dukascopy, $3/lot/day | 134 | 28.36 | +24.99 | 1.25 | 0.187 | 21.63 | 4 / 14 |
| dukascopy, $7/lot/day | 134 | 28.36 | +22.27 | 1.22 | 0.166 | 22.01 | 4 / 14 |
| histdata, $0/lot/day | 132 | 28.79 | +35.40 | 1.36 | 0.268 | 21.34 | 4 / 14 |
| histdata, $3/lot/day | 132 | 28.79 | +33.35 | 1.34 | 0.253 | 21.63 | 4 / 14 |
| histdata, $7/lot/day | 132 | 28.79 | +30.63 | 1.31 | 0.232 | 22.01 | 4 / 14 |
| mt5_icmarkets_utc, $0/lot/day | 128 | 25.78 | +13.26 | 1.13 | 0.104 | 22.73 | 4 / 22 |
| mt5_icmarkets_utc, $3/lot/day | 128 | 25.78 | +11.38 | 1.11 | 0.089 | 23.01 | 4 / 22 |
| mt5_icmarkets_utc, $7/lot/day | 128 | 25.78 | +8.89 | 1.09 | 0.069 | 23.37 | 4 / 22 |

## USDCAD, July through December 2025

The common window has sufficient warm-up on the available broker history.

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy, original | 0 | n/a | +0.00 | n/a | n/a | 0.00 | 0 / 0 |
| dukascopy, tracking | 0 | n/a | +0.00 | n/a | n/a | 0.00 | 0 / 0 |
| dukascopy, corrected | 0 | n/a | +0.00 | n/a | n/a | 0.00 | 0 / 0 |
| histdata, original | 0 | n/a | +0.00 | n/a | n/a | 0.00 | 0 / 0 |
| histdata, tracking | 0 | n/a | +0.00 | n/a | n/a | 0.00 | 0 / 0 |
| histdata, corrected | 0 | n/a | +0.00 | n/a | n/a | 0.00 | 0 / 0 |
| mt5_icmarkets_utc, original | 0 | n/a | +0.00 | n/a | n/a | 0.00 | 0 / 0 |
| mt5_icmarkets_utc, tracking | 0 | n/a | +0.00 | n/a | n/a | 0.00 | 0 / 0 |
| mt5_icmarkets_utc, corrected | 0 | n/a | +0.00 | n/a | n/a | 0.00 | 0 / 0 |

## Reproducibility and limits

Completed 204 sequential corrected/control replays and 2 original-code controls. Original controls match every prior trade field and ending exposure. Input, provenance sidecar, parameter, and shared-pipeline hashes match the prior baseline. Code and price-data hashes remained unchanged throughout the run. Each corrected replay checks that accepted-order ownership matches ending simulated exposure and that no unresolved proposal remains.

After those replays, an additional broker cancellation race was corrected: a partial fill discovered after cancellation of its remainder must still be adopted as OPEN. Final closes still block stale snapshots. The preceding strategy source is archived with its original hash. Six further full 2020 through 2025 broker replays on the final code match every earlier trade field and ending exposure. No CSV replay enters the changed partial-fill branch because the simulator has no partial fills. Final source hashes and control results are recorded in final_code_validation.json. The race itself has a deterministic regression test.

All 172 unit tests pass, including 22 new Running tests for lifecycle and extreme initialization. Execution failure messages in the tests are intentional fixtures. Broker connectivity and real MT5 order submission are not tested on this PC.

M5 executes H1/D1 signals. Each pair starts with $10,000 and 0.5% risk per trade. Default spread and $7/lot round-trip commission are modeled. Tables combine independent pair net-R histories by close time. Profit factor uses positive net R divided by absolute negative net R. Drawdown is the maximum decline of cumulative closed-trade R, not floating account-equity drawdown. Shared account exposure limits, daily-loss gates, news, variable spreads, extra slippage, and actual swaps are excluded.

Verified HistData passes the provenance-enforcing loader. The earlier source audit found approximately 99.98% identical OHLC on shared M5 timestamps with Dukascopy, so the two are not independent price confirmations. Missing bars and daily aggregation differ. Broker daily bars follow broker sessions rather than UTC midnight. Data after 14 July 2026 is excluded; some supplied broker files end at 21:00 UTC that day.

The copied DEMO export remains only two historical wins totaling $1,300.76 net. The $1,205.46 EURUSD winner followed an unsuccessful cancellation that the older engine wrongly logged as successful. That history does not validate the intended strategy or these new corrections.

## Period-end exposure

- dukascopy GBPUSD corrected fold_2020_train: 1 open/pending
- histdata GBPUSD corrected fold_2020_train: 1 open/pending

Open exposure, where present, is excluded from closed-trade statistics and is never liquidated using future bars.

## Reproduction

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe research_ema_fib_running_corrections.py
.venv\Scripts\python.exe summarize_ema_fib_running_corrections.py
```

The main research script now reruns all cases on the final strategy. validate_ema_fib_running_final.py preserves the supplemental check against the archived pre-race-fix artifacts from this run; it deliberately refuses a different preceding source hash.

Frozen original strategy revision: `2d58c1b24424a235d3337627850b15fc778e6040`. Research artifacts and hashes are under `output/ema_fib_running_corrections_20260925/`. The separate initial review remains under `strategy_log/ema_fib_running_review_20260925.md`.
