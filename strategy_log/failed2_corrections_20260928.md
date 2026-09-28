# Failed2 market corrections, 28 September 2026

The user authorized the startup-history and setup-tracking recommendations. They are implemented locally. Failed2 remains in the DEMO suite on USTEC at unchanged numeric settings and global 0.5% risk. EmaFibRunning remains excluded from new runs. No MT5 connection, deployment, or real-money promotion occurred.

## Assessment

The corrections preserve the historical case for continued DEMO evaluation. Broker results remain +53.29R for 2020 through 2025, with PF 1.48 and 10.14R closed-trade drawdown. The latest 2024 through 2025 broker test remains +17.28R with 71.6% expectancy retention. The longer histories each add two losing trades after the tracking correction, leaving +103.00R on Dukascopy and +99.68R on HistData. Their latest historical tests remain positive but retain only about 29–31% of training expectancy, which is WEAK under project standards.

At the current settings, extending the initial D1 warm-up makes no further difference to full-period 2020 through 2025 metrics on these sources. It still corrects an operational mismatch: the actual July restart with 50 daily bars permitted a signal that the complete range window blocks. No numeric optimization is justified by this correction exercise. Collect fresh DEMO evidence from the corrected version before treating the historical edge as confirmed.

## What changed

The startup runner now collects each strategy's history requirements per symbol and timeframe. Failed2 requests at least 61 daily candles for its 60-prior-day range comparison, and five times the longer EMA period for EMA initialization. Current settings therefore request 250 completed USTEC D1 bars. Other timeframes retain their existing defaults. A shared symbol/timeframe uses the largest requirement, so other strategies subscribed to USTEC D1 also receive that history. Startup refuses insufficient history. The range filter independently refuses entries until the full comparison window exists.

Market proposals now carry stable identities based on strategy, symbol, direction, and H1 setup time in UTC. A proposal does not consume the setup. Acceptance does, and later closure does not release it. Rejections while another trade occupies the slot leave the unsubmitted setup available. If the simulator rejects a queued market fill at its next executable price, only that identified unfilled attempt releases consumption.

The existing account-bound setup ledger persists the identity before a broker submission and attributes confirmed orders and outcomes to it. Open-order and closed-trade recovery restore consumption without needing a strategy checkpoint. Checkpoints preserve the same state and invalidate when the history policy changes. Historical orders without setup identities remain unattributed; the code does not invent their H1 origins. Preserve logs/setup_ledger.json on the trading host.

The market structure condition, stop anchor, H4 refresh, 4R target, session, symbols, and risk are unchanged. No fresh-cross filter, time exit, or parameter optimization was introduced. FVG retains its legacy order-tracking path; it is not validated by these market-mode runs.

## Before and after, 2020 through 2025

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy, baseline | 223 | 30.04 | +105.00 | 1.67 | 0.471 | 12.04 | 8 / 10 |
| dukascopy, tracking | 225 | 29.78 | +103.00 | 1.65 | 0.458 | 13.04 | 8 / 11 |
| dukascopy, corrected | 225 | 29.78 | +103.00 | 1.65 | 0.458 | 13.04 | 8 / 11 |
| histdata, baseline | 212 | 30.19 | +101.68 | 1.68 | 0.480 | 12.04 | 8 / 10 |
| histdata, tracking | 214 | 29.91 | +99.68 | 1.66 | 0.466 | 13.04 | 8 / 11 |
| histdata, corrected | 214 | 29.91 | +99.68 | 1.66 | 0.466 | 13.04 | 8 / 11 |
| mt5_icmarkets_utc, baseline | 152 | 27.63 | +53.29 | 1.48 | 0.351 | 10.14 | 3 / 8 |
| mt5_icmarkets_utc, tracking | 152 | 27.63 | +53.29 | 1.48 | 0.351 | 10.14 | 3 / 8 |
| mt5_icmarkets_utc, corrected | 152 | 27.63 | +53.29 | 1.48 | 0.351 | 10.14 | 3 / 8 |

Baseline is the immutable reviewed strategy from commit 2d58c1b24424a235d3337627850b15fc778e6040. Tracking applies the lifecycle and full-range-readiness corrections with the original 180-calendar-day warm-up. Corrected also changes the D1 warm-up to the most recent 250 completed bars when available. All other warm-up streams remain at 180 calendar days for comparison with the original continuous research replay. These are continuous backtests, not simulated daily restarts.

## January through 14 July 2026

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy, baseline | 28 | 21.43 | +0.85 | 1.04 | 0.031 | 6.13 | 1 / 5 |
| dukascopy, corrected | 28 | 21.43 | +0.85 | 1.04 | 0.031 | 6.13 | 1 / 5 |
| histdata, baseline | 26 | 23.08 | +2.85 | 1.14 | 0.110 | 6.13 | 1 / 5 |
| histdata, corrected | 26 | 23.08 | +2.85 | 1.14 | 0.110 | 6.13 | 1 / 5 |
| mt5_icmarkets_utc, baseline | 18 | 38.89 | +16.41 | 2.49 | 0.912 | 3.00 | 3 / 3 |
| mt5_icmarkets_utc, corrected | 18 | 38.89 | +16.41 | 2.49 | 0.912 | 3.00 | 3 / 3 |

## Historical rolling validation

Four-year training and two-year test periods retain fixed numeric settings. These periods were already used in development and are not fresh unseen evidence. The first 2016 training fold has no earlier history; readiness guards hold entries until the necessary observations exist. Later folds seed from prior data. Broker validation uses the final fold.

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy, test 2020, train | 140 | 27.86 | +44.49 | 1.44 | 0.318 | 16.51 | 3 / 15 |
| dukascopy, test 2020, test | 78 | 37.18 | +62.84 | 2.28 | 0.806 | 10.00 | 8 / 10 |
| dukascopy, test 2022, train | 147 | 34.01 | +95.10 | 1.98 | 0.647 | 16.51 | 8 / 13 |
| dukascopy, test 2022, test | 62 | 27.42 | +21.88 | 1.49 | 0.353 | 10.00 | 2 / 10 |
| dukascopy, test 2024, train | 140 | 32.86 | +84.72 | 1.90 | 0.605 | 10.00 | 8 / 10 |
| dukascopy, test 2024, test | 87 | 24.14 | +16.07 | 1.24 | 0.185 | 13.04 | 2 / 11 |
| histdata, test 2020, train | 139 | 28.06 | +44.94 | 1.45 | 0.323 | 15.51 | 3 / 13 |
| histdata, test 2020, test | 78 | 37.18 | +62.84 | 2.28 | 0.806 | 10.00 | 8 / 10 |
| histdata, test 2022, train | 146 | 33.56 | +91.82 | 1.95 | 0.629 | 15.51 | 8 / 13 |
| histdata, test 2022, test | 51 | 27.45 | +18.56 | 1.50 | 0.364 | 10.00 | 2 / 10 |
| histdata, test 2024, train | 129 | 33.33 | +81.40 | 1.95 | 0.631 | 10.00 | 8 / 10 |
| histdata, test 2024, test | 87 | 24.14 | +16.07 | 1.24 | 0.185 | 13.04 | 2 / 11 |
| mt5_icmarkets_utc, test 2024, train | 91 | 28.57 | +36.01 | 1.55 | 0.396 | 10.14 | 3 / 8 |
| mt5_icmarkets_utc, test 2024, test | 61 | 26.23 | +17.28 | 1.38 | 0.283 | 7.09 | 2 / 6 |

| Source | Test starts | Expectancy retention | Verdict |
|---|---:|---:|---|
| dukascopy | 2020 | 253.5% | STRONG |
| dukascopy | 2022 | 54.5% | MODERATE |
| dukascopy | 2024 | 30.5% | WEAK |
| histdata | 2020 | 249.2% | STRONG |
| histdata | 2022 | 57.9% | MODERATE |
| histdata | 2024 | 29.3% | WEAK |
| mt5_icmarkets_utc | 2024 | 71.6% | STRONG |

Retention is test R/trade divided by training R/trade. The project thresholds are 70% for STRONG and 40% for MODERATE. A losing test fails regardless of retention.

## Spread stress

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy, 2020_2025 | 225 | 29.78 | +103.00 | 1.65 | 0.458 | 13.04 | 8 / 11 |
| dukascopy, spread_2 | 225 | 29.78 | +97.08 | 1.61 | 0.431 | 13.04 | 8 / 11 |
| dukascopy, spread_5 | 225 | 29.33 | +76.47 | 1.48 | 0.340 | 13.04 | 8 / 11 |
| histdata, 2020_2025 | 214 | 29.91 | +99.68 | 1.66 | 0.466 | 13.04 | 8 / 11 |
| histdata, spread_2 | 214 | 29.91 | +94.25 | 1.63 | 0.440 | 13.04 | 8 / 11 |
| histdata, spread_5 | 214 | 29.44 | +74.90 | 1.49 | 0.350 | 13.04 | 8 / 11 |
| mt5_icmarkets_utc, 2020_2025 | 152 | 27.63 | +53.29 | 1.48 | 0.351 | 10.14 | 3 / 8 |
| mt5_icmarkets_utc, spread_2 | 152 | 27.63 | +49.61 | 1.45 | 0.326 | 10.25 | 3 / 8 |
| mt5_icmarkets_utc, spread_5 | 153 | 27.45 | +38.89 | 1.35 | 0.254 | 10.57 | 3 / 8 |

Spread is one, two, or five index points. These are full replays, not deductions from a fixed trade list.

## Reproduced restart

The 14 July 2026 cold-start reconstruction uses the actual 14:48:58 UTC restart time and stored broker bars. The frozen old code with 50 D1 bars reproduces the logged 15:05 BUY proposal at 29,649.4, SL 29,360.8, and TP 30,803.8. Corrected code emits no entry with either insufficient history or a complete range window.

| Variant | Daily bars | Range rank | Entry filter passes | Signals |
|---|---:|---:|---|---:|
| baseline_50 | 50 | 0.6327 | True | 1 |
| corrected_50 | 50 | 0.6327 | False | 0 |
| corrected_61 | 61 | 0.7000 | False | 0 |
| corrected_startup | 250 | 0.7000 | False | 0 |
| corrected_reference | 388 | 0.7000 | False | 0 |

At the actual startup, EMA50 is 29092.600096 with the new history policy versus 29092.601548 using all 388 available reference bars. Finite warm-up reduces seed dependence; it does not mathematically equal unlimited history. The full-history range rank is 0.70 and blocks this entry. This reconstruction matches the historical signal, not exact broker fills or the entire shared account.

## Validation and limits

Completed 32 sequential replays, including 3 frozen-baseline controls. Each control exactly matches every stored trade field and ending exposure from the original review. Source hashes match the prior review, HistData is loaded through its provenance checks, and code hashes stayed unchanged during the runs. No price bars after 14 July 2026 enter the analysis.

All 186 unit tests pass, including 14 new Failed2 cases. These cover occupied-slot rejection, acceptance, late rejection, failed market fills, open and closed ledger recovery, UTC identity, checkpoints, broker submission persistence, and full daily-range requirements. The broker test uses a fake adapter and makes no MT5 connection.

Assumptions match the original review: isolated strategy, $10,000 starting balance, 0.5% risk, M5 execution, bid OHLC, one-point default spread, and zero index commission. Actual financing, variable spread, extra slippage, news, shared-account position limits, and daily-loss gates are excluded. R drawdown uses closed trades, not floating equity. Dukascopy and HistData have near-identical shared M5 candles and are not independent confirmation. Weekend gap risk from the DEMO review remains relevant.

Open exposure at period boundaries is excluded from closed-trade totals and is not liquidated using future prices:

- dukascopy corrected fold_2020_train: 1 open/pending
- dukascopy corrected fold_2022_test: 1 open/pending
- dukascopy corrected fold_2024_train: 1 open/pending
- histdata corrected fold_2020_train: 1 open/pending
- histdata corrected fold_2022_test: 1 open/pending
- histdata corrected fold_2024_train: 1 open/pending

## Trading-host update

Transfer the tested code, stop the old bot process, run the unit suite, and start one bot instance. Preserve logs/setup_ledger.json. The changed code invalidates the old strategy checkpoint and triggers fresh history initialization. MT5 must supply 250 completed USTEC D1 bars at current settings. Existing broker stops and targets remain in place. The corrected strategy cannot recover setup identities for trades created by the old version.

## Reproduction

```powershell
python -m unittest discover -s tests -v
python research_failed2_corrections.py
python validate_failed2_restart.py
python summarize_failed2_corrections.py
```

Run with the project backtest environment and one worker. Detailed results, trades, control checks, code and input hashes, and the restart reproduction are in output/failed2_corrections_20260928/. The earlier failed2_review_20260928.md is the pre-correction snapshot; use this report and these commands for current code.
