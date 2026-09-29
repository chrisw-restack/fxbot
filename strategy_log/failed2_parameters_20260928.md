# Failed2 parameter study, completed 29 September 2026

Completed 128 serial replays across 19 configurations, including 16 exact controls against the corrected review. The search changes one parameter at a time. No DEMO settings, risk, production logic, or MT5 account state changed.

## Recommendation

Keep the current parameters. This bounded search did not establish a convincing improvement. Retain the 4R signal-price target, structure fractal 4, stop fractal 2, 60-day range lookback with a 0.70 blocking threshold, D1 EMA20/50 direction filter, and 13:00–16:00 UTC session. This is a comparison of the tested choices, not proof that the current settings are globally optimal.

Extending the session to 17:00 looked better in broker training, but the following 2024–2025 test fell from +17.28R to +4.28R, with drawdown increasing from 7.09R to 10.53R. Its January–14 July 2026 broker result also fell, from +16.41R to +9.55R. Reject this extension from the current evidence.

A 90-day range lookback is almost identical to 60 days over the full broker history, +53.26R versus +53.29R, and improves the recent broker slice by just 1R over 17 trades. It reduces returns on the longer feeds. That small recent gain is insufficient reason to change the configuration. The 40-day lookback also gives lower full-period and recent broker returns, despite retaining a STRONG training/test ratio. Retention alone does not establish improvement over the current strategy.

The rolling search selected 5R for its first two tests and current settings for the last. Combining those independent test folds gives +98.40R and 16R drawdown, versus +100.79R and 13.04R drawdown with current settings throughout. The selected parameters therefore do not improve this historical comparison.

The 4.5R target led eligible broker training returns, +43.14R versus +36.01R, but its Dukascopy training drawdown was 16R against the predeclared 15R cap. It was screened out before finalist testing. This report does not claim to have disproved untested validation performance for that setting. Removing the trend filter was also screened out; broker training drawdown reached 26.14R with a 25-loss streak.

All finalists remain profitable in the full broker replay with five-point spread and in a separate illustrative financing-debit scenario. The current settings still give the strongest returns in those comparisons. Keep collecting DEMO evidence from the corrected implementation; these reused historical periods do not resolve its weak recent long-feed retention or the earlier weak DEMO sample.

## Tested choices

- Current: target 4R; MSS 4; stop fractal 2; daily range threshold 0.70 over 60 days; 13:00–16:00 UTC; D1 EMA20/50.
- Target 2.5R instead of 4R.
- Target 3R instead of 4R.
- Target 3.5R instead of 4R.
- Target 4.5R instead of 4R.
- Target 5R instead of 4R.
- Structure fractal 2 instead of 4.
- Structure fractal 3 instead of 4.
- Structure fractal 5 instead of 4.
- Stop fractal 1 instead of 2.
- Stop fractal 3 instead of 2.
- Daily range blocking percentile 0.60 instead of 0.70.
- Daily range blocking percentile 0.80 instead of 0.70.
- Daily range blocking percentile 0.90 instead of 0.70.
- Daily range lookback 40 instead of 60.
- Daily range lookback 90 instead of 60.
- Session 12:00–16:00 UTC instead of 13:00–16:00.
- Session 13:00–17:00 UTC instead of 13:00–16:00.
- Disable the D1 EMA direction filter; retain the range filter.

Session bounds refer to M5 bar-opening labels; the last permitted signal bar closes at the stated ending time. Every alternative changes only the listed parameter. No combinations of winning parameters were constructed after seeing results.

## Selection protocol

The protocol and all options were written and hash-bound before the runs. Training eligibility requires at least 40 closed trades, positive total R, profit factor of at least 1.10, and maximum closed-trade R drawdown no more than 1.5 times current settings in that training period. Eligible choices are ranked by total R, then lower drawdown and option name. These are research screening limits, not account-risk guarantees.

The Dukascopy rolling search selects separately on 2016–2019, 2018–2021, and 2020–2023, then tests the selected choice on the following two years. Broker screening uses 2020–2023. Its top three non-current choices that also pass the Dukascopy 2020–2023 training limits are frozen before finalist evaluation. HistData is used to compare those frozen finalists, not to choose them. Recent evaluation ends on 14 July 2026.

These historical periods were used in earlier development. Training/test separation prevents this sweep from choosing on its test results, but does not make the periods untouched or erase prior selection bias. Dukascopy and HistData have near-identical shared M5 prices, so agreement between them is not independent-feed confirmation.

## Training results, 2020 through 2023

mt5_icmarkets_utc

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| session_12_16 [excluded] | 178 | 26.97 | +54.41 | 1.42 | 0.306 | 15.62 | 3 / 11 |
| rr_5 [excluded] | 88 | 26.14 | +46.72 | 1.72 | 0.531 | 17.34 | 2 / 13 |
| rr_4.5 [eligible] | 91 | 27.47 | +43.14 | 1.65 | 0.474 | 13.00 | 3 / 13 |
| session_13_17 [eligible] | 124 | 27.42 | +42.81 | 1.48 | 0.345 | 12.14 | 3 / 9 |
| trend_off [excluded] | 184 | 24.46 | +37.01 | 1.27 | 0.201 | 26.14 | 3 / 25 |
| current [eligible] | 91 | 28.57 | +36.01 | 1.55 | 0.396 | 10.14 | 3 / 8 |
| lookback_90 [eligible] | 91 | 28.57 | +36.01 | 1.55 | 0.396 | 10.14 | 3 / 8 |
| lookback_40 [eligible] | 90 | 27.78 | +32.23 | 1.50 | 0.358 | 11.45 | 3 / 8 |
| range_0.6 [eligible] | 77 | 28.57 | +30.61 | 1.56 | 0.397 | 10.45 | 3 / 7 |
| range_0.8 [eligible] | 102 | 26.47 | +29.73 | 1.40 | 0.291 | 11.14 | 3 / 9 |
| mss_3 [eligible] | 103 | 26.21 | +28.26 | 1.37 | 0.274 | 13.22 | 3 / 8 |
| stop_1 [eligible] | 95 | 26.32 | +27.34 | 1.39 | 0.288 | 10.14 | 2 / 9 |
| range_0.9 [eligible] | 118 | 25.42 | +27.01 | 1.30 | 0.229 | 14.40 | 4 / 10 |
| stop_3 [excluded] | 88 | 26.14 | +24.57 | 1.38 | 0.279 | 16.18 | 3 / 16 |
| rr_3.5 [eligible] | 96 | 28.12 | +22.29 | 1.32 | 0.232 | 11.07 | 3 / 8 |
| rr_2.5 [eligible] | 98 | 35.71 | +21.55 | 1.34 | 0.220 | 7.14 | 3 / 7 |
| mss_5 [eligible] | 71 | 25.35 | +16.97 | 1.32 | 0.239 | 8.33 | 3 / 7 |
| rr_3 [eligible] | 97 | 29.90 | +16.05 | 1.24 | 0.165 | 10.33 | 3 / 8 |
| mss_2 [excluded] | 139 | 20.86 | +0.56 | 1.01 | 0.004 | 17.90 | 3 / 11 |

dukascopy

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| trend_off [excluded] | 275 | 28.36 | +109.31 | 1.55 | 0.397 | 19.28 | 4 / 10 |
| current [eligible] | 140 | 32.86 | +84.72 | 1.90 | 0.605 | 10.00 | 8 / 10 |
| session_13_17 [eligible] | 140 | 32.86 | +84.72 | 1.90 | 0.605 | 10.00 | 8 / 10 |
| rr_3.5 [eligible] | 149 | 35.57 | +84.39 | 1.88 | 0.566 | 10.00 | 6 / 10 |
| session_12_16 [eligible] | 146 | 32.19 | +83.97 | 1.85 | 0.575 | 10.00 | 6 / 10 |
| rr_5 [excluded] | 135 | 27.41 | +82.34 | 1.84 | 0.610 | 16.00 | 5 / 16 |
| mss_2 [eligible] | 185 | 30.27 | +82.11 | 1.61 | 0.444 | 12.00 | 3 / 12 |
| range_0.8 [eligible] | 163 | 30.67 | +81.51 | 1.72 | 0.500 | 12.01 | 8 / 11 |
| lookback_90 [eligible] | 139 | 32.37 | +80.65 | 1.86 | 0.580 | 12.00 | 8 / 12 |
| rr_3 [eligible] | 155 | 38.71 | +79.49 | 1.84 | 0.513 | 10.00 | 6 / 10 |
| rr_4.5 [excluded] | 138 | 28.99 | +77.40 | 1.79 | 0.561 | 16.00 | 6 / 16 |
| mss_3 [eligible] | 166 | 30.72 | +76.84 | 1.64 | 0.463 | 12.00 | 3 / 12 |
| lookback_40 [eligible] | 142 | 30.99 | +73.23 | 1.75 | 0.516 | 11.18 | 7 / 10 |
| range_0.9 [excluded] | 182 | 28.57 | +71.86 | 1.55 | 0.395 | 16.04 | 4 / 13 |
| stop_3 [eligible] | 129 | 31.78 | +71.86 | 1.82 | 0.557 | 14.00 | 7 / 11 |
| range_0.6 [eligible] | 120 | 31.67 | +65.51 | 1.80 | 0.546 | 9.25 | 8 / 9 |
| rr_2.5 [eligible] | 157 | 41.40 | +65.46 | 1.71 | 0.417 | 8.56 | 6 / 8 |
| stop_1 [eligible] | 152 | 28.29 | +57.82 | 1.53 | 0.380 | 14.57 | 6 / 11 |
| mss_5 [eligible] | 121 | 28.93 | +50.23 | 1.58 | 0.415 | 11.00 | 3 / 11 |

## Frozen finalists

- Session 13:00–17:00 UTC instead of 13:00–16:00.
- Daily range lookback 90 instead of 60.
- Daily range lookback 40 instead of 60.

The finalist order is the broker training ranking. It is not a ranking chosen after examining validation.

## Later historical test, 2024 through 2025

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| mt5_icmarkets_utc, current | 61 | 26.23 | +17.28 | 1.38 | 0.283 | 7.09 | 2 / 6 |
| mt5_icmarkets_utc, session_13_17 | 79 | 21.52 | +4.28 | 1.07 | 0.054 | 10.53 | 2 / 9 |
| mt5_icmarkets_utc, lookback_90 | 61 | 26.23 | +17.26 | 1.38 | 0.283 | 7.09 | 2 / 7 |
| mt5_icmarkets_utc, lookback_40 | 58 | 25.86 | +15.27 | 1.35 | 0.263 | 6.54 | 2 / 6 |
| dukascopy, current | 87 | 24.14 | +16.07 | 1.24 | 0.185 | 13.04 | 2 / 11 |
| dukascopy, session_13_17 | 87 | 24.14 | +16.07 | 1.24 | 0.185 | 13.04 | 2 / 11 |
| dukascopy, lookback_90 | 90 | 23.33 | +13.07 | 1.19 | 0.145 | 12.04 | 2 / 11 |
| dukascopy, lookback_40 | 90 | 23.33 | +13.08 | 1.19 | 0.145 | 14.04 | 3 / 12 |
| histdata, current | 87 | 24.14 | +16.07 | 1.24 | 0.185 | 13.04 | 2 / 11 |
| histdata, session_13_17 | 87 | 24.14 | +16.07 | 1.24 | 0.185 | 13.04 | 2 / 11 |
| histdata, lookback_90 | 90 | 23.33 | +13.07 | 1.19 | 0.145 | 12.04 | 2 / 11 |
| histdata, lookback_40 | 90 | 23.33 | +13.08 | 1.19 | 0.145 | 14.04 | 3 / 12 |

| Source | Option | Expectancy retention | Verdict |
|---|---|---:|---|
| dukascopy | current | 30.5% | WEAK |
| dukascopy | session_13_17 | 30.5% | WEAK |
| dukascopy | lookback_90 | 25.0% | WEAK |
| dukascopy | lookback_40 | 28.2% | WEAK |
| histdata | current | 29.3% | WEAK |
| histdata | session_13_17 | 29.3% | WEAK |
| histdata | lookback_90 | 24.0% | WEAK |
| histdata | lookback_40 | 27.2% | WEAK |
| mt5_icmarkets_utc | current | 71.6% | STRONG |
| mt5_icmarkets_utc | session_13_17 | 15.7% | WEAK |
| mt5_icmarkets_utc | lookback_90 | 71.5% | STRONG |
| mt5_icmarkets_utc | lookback_40 | 73.5% | STRONG |

Retention is test R/trade divided by training R/trade. STRONG starts at 70%; MODERATE at 40%; below 40% is WEAK. A losing test fails regardless of retention.

## January through 14 July 2026

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| mt5_icmarkets_utc, current | 18 | 38.89 | +16.41 | 2.49 | 0.912 | 3.00 | 3 / 3 |
| mt5_icmarkets_utc, session_13_17 | 20 | 30.00 | +9.55 | 1.68 | 0.478 | 6.00 | 2 / 6 |
| mt5_icmarkets_utc, lookback_90 | 17 | 41.18 | +17.41 | 2.74 | 1.024 | 3.00 | 3 / 3 |
| mt5_icmarkets_utc, lookback_40 | 15 | 33.33 | +9.58 | 1.96 | 0.638 | 3.00 | 1 / 3 |
| dukascopy, current | 28 | 21.43 | +0.85 | 1.04 | 0.031 | 6.13 | 1 / 5 |
| dukascopy, session_13_17 | 28 | 21.43 | +0.85 | 1.04 | 0.031 | 6.13 | 1 / 5 |
| dukascopy, lookback_90 | 26 | 23.08 | +2.85 | 1.14 | 0.110 | 6.13 | 1 / 6 |
| dukascopy, lookback_40 | 26 | 19.23 | -2.39 | 0.89 | -0.092 | 8.00 | 1 / 8 |
| histdata, current | 26 | 23.08 | +2.85 | 1.14 | 0.110 | 6.13 | 1 / 5 |
| histdata, session_13_17 | 26 | 23.08 | +2.85 | 1.14 | 0.110 | 6.13 | 1 / 5 |
| histdata, lookback_90 | 24 | 25.00 | +4.85 | 1.26 | 0.202 | 6.13 | 1 / 6 |
| histdata, lookback_40 | 24 | 20.83 | -0.39 | 0.98 | -0.016 | 8.00 | 1 / 8 |

## Full period, 2020 through 2025

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| mt5_icmarkets_utc, current | 152 | 27.63 | +53.29 | 1.48 | 0.351 | 10.14 | 3 / 8 |
| mt5_icmarkets_utc, session_13_17 | 203 | 25.12 | +47.08 | 1.31 | 0.232 | 12.14 | 3 / 9 |
| mt5_icmarkets_utc, lookback_90 | 152 | 27.63 | +53.26 | 1.48 | 0.350 | 10.14 | 3 / 8 |
| mt5_icmarkets_utc, lookback_40 | 148 | 27.03 | +47.50 | 1.44 | 0.321 | 11.45 | 3 / 8 |
| dukascopy, current | 225 | 29.78 | +103.00 | 1.65 | 0.458 | 13.04 | 8 / 11 |
| dukascopy, session_13_17 | 225 | 29.78 | +103.00 | 1.65 | 0.458 | 13.04 | 8 / 11 |
| dukascopy, lookback_90 | 227 | 29.07 | +95.93 | 1.59 | 0.423 | 12.04 | 8 / 12 |
| dukascopy, lookback_40 | 230 | 28.26 | +88.53 | 1.54 | 0.385 | 14.04 | 7 / 12 |
| histdata, current | 214 | 29.91 | +99.68 | 1.66 | 0.466 | 13.04 | 8 / 11 |
| histdata, session_13_17 | 214 | 29.91 | +99.68 | 1.66 | 0.466 | 13.04 | 8 / 11 |
| histdata, lookback_90 | 216 | 29.17 | +92.61 | 1.60 | 0.429 | 12.04 | 8 / 12 |
| histdata, lookback_40 | 219 | 28.31 | +85.21 | 1.54 | 0.389 | 14.04 | 7 / 12 |

This full-period comparison includes training observations. Do not treat it as independent validation.

## Rolling parameter selection on Dukascopy

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| test 2020, current | 78 | 37.18 | +62.84 | 2.28 | 0.806 | 10.00 | 8 / 10 |
| test 2020, rr_5 | 75 | 30.67 | +59.51 | 2.14 | 0.793 | 16.00 | 5 / 16 |
| test 2022, current | 62 | 27.42 | +21.88 | 1.49 | 0.353 | 10.00 | 2 / 10 |
| test 2022, rr_5 | 60 | 23.33 | +22.82 | 1.50 | 0.380 | 15.01 | 2 / 15 |
| test 2024, current | 87 | 24.14 | +16.07 | 1.24 | 0.185 | 13.04 | 2 / 11 |

- Test 2020: selected rr_5 from training only; retention 137.2%, STRONG.
- Test 2022: selected rr_5 from training only; retention 48.3%, MODERATE.
- Test 2024: selected current from training only; retention 30.5%, WEAK.

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| current | 227 | 29.52 | +100.79 | 1.63 | 0.444 | 13.04 | 8 / 11 |
| selected | 222 | 26.13 | +98.40 | 1.60 | 0.443 | 16.00 | 5 / 16 |

The stitched table combines closed trades from independent test folds with fresh starting state and balance. Boundary positions remain unclosed and are excluded. It is a historical comparison of the selection rule, not continuous account equity or a deployable rule validated on unseen data.

## Broker spread stress, 2020 through 2025

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| current, 1 points | 152 | 27.63 | +53.29 | 1.48 | 0.351 | 10.14 | 3 / 8 |
| current, 2 points | 152 | 27.63 | +49.61 | 1.45 | 0.326 | 10.25 | 3 / 8 |
| current, 5 points | 153 | 27.45 | +38.89 | 1.35 | 0.254 | 10.57 | 3 / 8 |
| session_13_17, 1 points | 203 | 25.12 | +47.08 | 1.31 | 0.232 | 12.14 | 3 / 9 |
| session_13_17, 2 points | 203 | 25.12 | +43.18 | 1.28 | 0.213 | 12.25 | 3 / 9 |
| session_13_17, 5 points | 204 | 25.00 | +31.69 | 1.21 | 0.155 | 12.97 | 3 / 9 |
| lookback_90, 1 points | 152 | 27.63 | +53.26 | 1.48 | 0.350 | 10.14 | 3 / 8 |
| lookback_90, 2 points | 152 | 27.63 | +49.58 | 1.45 | 0.326 | 10.25 | 3 / 8 |
| lookback_90, 5 points | 153 | 27.45 | +38.82 | 1.35 | 0.254 | 11.57 | 3 / 8 |
| lookback_40, 1 points | 148 | 27.03 | +47.50 | 1.44 | 0.321 | 11.45 | 3 / 8 |
| lookback_40, 2 points | 148 | 27.03 | +44.06 | 1.41 | 0.298 | 11.82 | 3 / 8 |
| lookback_40, 5 points | 149 | 26.85 | +33.99 | 1.31 | 0.228 | 12.76 | 3 / 8 |

## Illustrative broker financing sensitivity

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| current, $0/lot/day | 152 | 27.63 | +53.29 | 1.48 | 0.351 | 10.14 | 3 / 8 |
| current, $3/lot/day | 152 | 27.63 | +46.03 | 1.41 | 0.303 | 11.16 | 3 / 8 |
| current, $7/lot/day | 152 | 27.63 | +36.34 | 1.31 | 0.239 | 12.51 | 3 / 8 |
| session_13_17, $0/lot/day | 203 | 25.12 | +47.08 | 1.31 | 0.232 | 12.14 | 3 / 9 |
| session_13_17, $3/lot/day | 203 | 25.12 | +37.06 | 1.24 | 0.183 | 13.76 | 3 / 9 |
| session_13_17, $7/lot/day | 203 | 25.12 | +23.70 | 1.15 | 0.117 | 15.92 | 3 / 9 |
| lookback_90, $0/lot/day | 152 | 27.63 | +53.26 | 1.48 | 0.350 | 10.14 | 3 / 8 |
| lookback_90, $3/lot/day | 152 | 27.63 | +45.99 | 1.41 | 0.303 | 11.16 | 3 / 8 |
| lookback_90, $7/lot/day | 152 | 27.63 | +36.30 | 1.31 | 0.239 | 12.53 | 3 / 8 |
| lookback_40, $0/lot/day | 148 | 27.03 | +47.50 | 1.44 | 0.321 | 11.45 | 3 / 8 |
| lookback_40, $3/lot/day | 148 | 27.03 | +40.27 | 1.36 | 0.272 | 12.59 | 3 / 8 |
| lookback_40, $7/lot/day | 148 | 27.03 | +30.64 | 1.26 | 0.207 | 14.12 | 3 / 8 |

These are hypothetical uniform debits on the existing trade paths. They do not reconstruct actual swap, credits, triple-swap days, changed sizing, or changed trade paths. Spread stress and this financing sensitivity are separate scenarios, not combined costs.

| Option | Median holding hours | Longest holding hours |
|---|---:|---:|
| current | 3.05 | 701.80 |
| session_13_17 | 3.20 | 701.80 |
| lookback_90 | 3.15 | 701.80 |
| lookback_40 | 2.80 | 701.80 |

The strategy has no time exit. Long holds and weekend gap losses remain possible; a nominal 1R stop is not a guaranteed loss limit.

## Data, controls, and limits

All sources use corrected Failed2 market logic, M5 execution, completed H1/H4/D1 inputs, $10,000 starting balance, 0.5% risk, and zero index commission. Default spread is one index point. USA100 and USTEC use the same one-point pip size and $1 per point per lot assumptions. Broker H4 uses the full newer export. HistData passes provenance checks. The manifest records every input, sidecar, and relevant code hash.

D1 warm-up uses up to 250 completed bars; other streams use 180 calendar days, as in the corrected comparison. The first 2016 training window has no earlier history and waits for indicator readiness. Each later replay starts fresh from prior history. No price bars after 14 July 2026 enter the study.

Actual financing, variable spread, extra slippage, news filters, shared-account position limits, and daily-loss gates are excluded from the main tables. Profit factor divides positive net R by absolute negative net R; it can differ from a dollar-based profit factor under changing lot sizes. Drawdown is based on closed-trade R, not floating equity. Broker candle boundaries differ from the UTC-aligned long-history feeds, so source comparisons include session construction as well as price differences.

All 16 controls exactly match every trade field and ending exposure saved in the corrected review. Code and metadata hashes remained unchanged during the runs. No strategy implementation was modified for this sweep.

## Period-end exposure

- dukascopy current fold_2020_train spread 1: 1 open/pending.
- dukascopy rr_3.5 fold_2020_train spread 1: 1 open/pending.
- dukascopy rr_4.5 fold_2020_train spread 1: 1 open/pending.
- dukascopy rr_5 fold_2020_train spread 1: 1 open/pending.
- dukascopy mss_2 fold_2020_train spread 1: 1 open/pending.
- dukascopy mss_3 fold_2020_train spread 1: 1 open/pending.
- dukascopy mss_5 fold_2020_train spread 1: 1 open/pending.
- dukascopy stop_1 fold_2020_train spread 1: 1 open/pending.
- dukascopy stop_3 fold_2020_train spread 1: 1 open/pending.
- dukascopy range_0.6 fold_2020_train spread 1: 1 open/pending.
- dukascopy range_0.8 fold_2020_train spread 1: 1 open/pending.
- dukascopy range_0.9 fold_2020_train spread 1: 1 open/pending.
- dukascopy lookback_40 fold_2020_train spread 1: 1 open/pending.
- dukascopy lookback_90 fold_2020_train spread 1: 1 open/pending.
- dukascopy session_12_16 fold_2020_train spread 1: 1 open/pending.
- dukascopy session_13_17 fold_2020_train spread 1: 1 open/pending.
- dukascopy trend_off fold_2020_train spread 1: 1 open/pending.
- dukascopy current fold_2022_test spread 1: 1 open/pending.
- dukascopy rr_5 fold_2022_test spread 1: 1 open/pending.
- dukascopy current fold_2024_train spread 1: 1 open/pending.
- dukascopy rr_4.5 fold_2024_train spread 1: 1 open/pending.
- dukascopy rr_5 fold_2024_train spread 1: 1 open/pending.
- dukascopy mss_5 fold_2024_train spread 1: 1 open/pending.
- dukascopy stop_1 fold_2024_train spread 1: 1 open/pending.
- dukascopy stop_3 fold_2024_train spread 1: 1 open/pending.
- dukascopy range_0.6 fold_2024_train spread 1: 1 open/pending.
- dukascopy range_0.8 fold_2024_train spread 1: 1 open/pending.
- dukascopy range_0.9 fold_2024_train spread 1: 1 open/pending.
- dukascopy lookback_40 fold_2024_train spread 1: 1 open/pending.
- dukascopy lookback_90 fold_2024_train spread 1: 1 open/pending.
- dukascopy session_12_16 fold_2024_train spread 1: 1 open/pending.
- dukascopy session_13_17 fold_2024_train spread 1: 1 open/pending.
- dukascopy trend_off fold_2024_train spread 1: 1 open/pending.
- mt5_icmarkets_utc lookback_40 2026_to_july14 spread 1: 1 open/pending.
- histdata current fold_2024_train spread 1: 1 open/pending.
- histdata session_13_17 fold_2024_train spread 1: 1 open/pending.
- histdata lookback_90 fold_2024_train spread 1: 1 open/pending.
- histdata lookback_40 fold_2024_train spread 1: 1 open/pending.

No future prices are used to close these positions. Different settings can leave different exposure at a cutoff, so closed-trade results are not a complete mark-to-market comparison.

## Reproduction

```powershell
python research_failed2_parameters.py
python summarize_failed2_parameters.py
```

Use the project backtest environment and one worker. The study resumes cached jobs only when its manifest is identical. Results, all trades, frozen selections, rankings, checks, and sensitivity tables are under output/failed2_parameters_20260928/. DEMO configuration is unchanged.
