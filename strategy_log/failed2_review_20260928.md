# Failed2 H4/H1/M5 market review, 28 September 2026

This is the review before corrections. The user subsequently authorized the
startup-history and setup-tracking fixes. Use the
[correction report](failed2_corrections_20260928.md) for current code, results,
and reproduction commands; the commands below describe the original review.

Scope: the configured Failed2_H4_H1_M5_market strategy on USTEC. Production Failed2 logic, parameters, risk, and DEMO membership are unchanged. EmaFibRunning was separately removed from default startup at the user's explicit request. No interaction with MT5 or deployment occurred.

## Assessment and recommended order of work

The historical evidence supports further work on Failed2 rather than retirement. At current settings, the 2020–2025 broker replay earns +53.29R with PF 1.48 and 10.14R closed-trade drawdown. Its 2024–2025 historical test remains profitable at +17.28R and retains 71.6% of training expectancy. However, the same final test retains only 31–32% on the two long-history sources: profitable, but WEAK by the project standard. The older blanket STRONG label therefore overstates current evidence.

Verified HistData produces comparable results to Dukascopy, but their near-identical M5 prices do not establish independent confirmation. The copied DEMO record is weak: eight trades, one winner, and a net loss of $778.31. It mixes earlier versions and operational conditions, so it neither validates current code nor isolates the cause of the loss.

First correct startup history requirements and test consistent daily-filter initialization. Then distinguish proposed from accepted setups and recover consumed setup identities across cold restarts. Compare those corrections against this frozen baseline before optimizing numeric parameters. The fresh-cross diagnostic has mixed results and worse long-period drawdown on every source; it does not justify changing the entry rule. Keep H4 refresh and stop-anchor alternatives as separate research questions. No Failed2 production correction or parameter promotion is made in this review.

## Current rules

H4 candles select BUY or SELL using the previous candle's body and wick extremes. The labels 2, 3, and failed2 describe this custom body-based implementation. For example, a bullish 2 can close above the prior body high while remaining inside its wick range; the labels do not enforce strict wick-based candle categories.

Every qualifying H4 candle refreshes the bias and clears the H1 setup and accumulated M5 bars, including a same-direction H4 candle. A candle that produces no new bias leaves the existing bias active by default. The older statement that only an opposite bias replaces the setup was incomplete.

An H1 candle must close strictly after the bias candle. BUY confirmation sweeps the previous H1 low and closes back above it; SELL is mirrored. An outside candle can qualify because there is no requirement to avoid sweeping the opposite side. A later qualifying H1 candle replaces the current H1 setup.

M5 entry must close strictly after H1 confirmation. A swing needs four completed bars on each side for the structure level. BUY requires a close above a confirmed swing high; SELL requires a close below a confirmed swing low. The stop uses a two-bar fractal on the opposite side whose pivot occurs BEFORE the selected broken pivot. It is not necessarily the most recent opposite pivot before entry. One accepted-or-consumed setup flag normally suppresses further signals for the same H1 confirmation.

D1 EMA 20/50 must align with entry direction. The last completed D1 range is compared with the preceding 60 daily ranges. A rank of at least 0.70 blocks entries, meaning the top 30% is blocked. Signal bars have UTC opening-hour labels 13, 14, or 15; the last allowed M5 signal closes at 16:00 UTC. This fixed UTC window shifts relative to New York local time with daylight saving.

The strategy sets TP at four times the distance from signal close to SL. Actual execution occurs at the next M5 open in backtests and at the executable quote on the host. Spread and gaps change the realized entry R:R. The execution layer rechecks the minimum 1R requirement and sizes against the executable entry, while retaining the strategy's locked target. Four is a target based on the signal price, not a guarantee of four net R per winning trade.

## Current parameters, 2020 through 2025

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy | 223 | 30.04 | +105.00 | 1.67 | 0.471 | 12.04 | 8 / 10 |
| histdata | 212 | 30.19 | +101.68 | 1.68 | 0.480 | 12.04 | 8 / 10 |
| mt5_icmarkets_utc | 152 | 27.63 | +53.29 | 1.48 | 0.351 | 10.14 | 3 / 8 |

These are isolated strategy results at the current settings, after the shared simulator and data-provenance repairs. They are not a controlled before/after comparison with May tables that used older windows, data, costs, and execution assumptions.

## January through 14 July 2026

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy | 28 | 21.43 | +0.85 | 1.04 | 0.031 | 6.13 | 1 / 5 |
| histdata | 26 | 23.08 | +2.85 | 1.14 | 0.110 | 6.13 | 1 / 5 |
| mt5_icmarkets_utc | 18 | 38.89 | +16.41 | 2.49 | 0.912 | 3.00 | 3 / 3 |

## Historical rolling validation

Four-year training windows and two-year test windows use the same fixed parameters. No search occurs within these runs. The periods were used in earlier strategy development, so these are historical revalidation checks, not fresh unseen evidence. The first training run starts in January 2016 without earlier warm-up. Later runs use 180 days. Broker validation uses the final 2020 through 2023 training window and 2024 through 2025 test.

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy, test 2020, train | 141 | 27.66 | +42.76 | 1.42 | 0.303 | 15.51 | 3 / 15 |
| dukascopy, test 2020, test | 77 | 37.66 | +63.84 | 2.33 | 0.829 | 10.00 | 8 / 10 |
| dukascopy, test 2022, train | 144 | 34.03 | +92.75 | 1.98 | 0.644 | 15.51 | 8 / 13 |
| dukascopy, test 2022, test | 62 | 27.42 | +21.88 | 1.49 | 0.353 | 10.00 | 2 / 10 |
| dukascopy, test 2024, train | 139 | 33.09 | +85.72 | 1.92 | 0.617 | 10.00 | 8 / 10 |
| dukascopy, test 2024, test | 86 | 24.42 | +17.07 | 1.26 | 0.198 | 12.04 | 2 / 10 |
| histdata, test 2020, train | 141 | 27.66 | +42.54 | 1.42 | 0.302 | 14.51 | 3 / 13 |
| histdata, test 2020, test | 77 | 37.66 | +63.84 | 2.33 | 0.829 | 10.00 | 8 / 10 |
| histdata, test 2022, train | 144 | 33.33 | +88.93 | 1.93 | 0.618 | 14.51 | 8 / 13 |
| histdata, test 2022, test | 51 | 27.45 | +18.56 | 1.50 | 0.364 | 10.00 | 2 / 10 |
| histdata, test 2024, train | 128 | 33.59 | +82.40 | 1.97 | 0.644 | 10.00 | 8 / 10 |
| histdata, test 2024, test | 86 | 24.42 | +17.07 | 1.26 | 0.198 | 12.04 | 2 / 10 |
| mt5_icmarkets_utc, test 2024, train | 91 | 28.57 | +36.01 | 1.55 | 0.396 | 10.14 | 3 / 8 |
| mt5_icmarkets_utc, test 2024, test | 61 | 26.23 | +17.28 | 1.38 | 0.283 | 7.09 | 2 / 6 |

| Source | Test starts | Expectancy retention | Verdict |
|---|---:|---:|---|
| dukascopy | 2020 | 273.4% | STRONG |
| dukascopy | 2022 | 54.8% | MODERATE |
| dukascopy | 2024 | 32.2% | WEAK |
| histdata | 2020 | 274.8% | STRONG |
| histdata | 2022 | 58.9% | MODERATE |
| histdata | 2024 | 30.8% | WEAK |
| mt5_icmarkets_utc | 2024 | 71.6% | STRONG |

Retention divides test expectancy by training expectancy. It is undefined for nonpositive training expectancy; a losing test fails regardless of the ratio.

## Logic and lifecycle findings

1. **The entry need not be a new structure break.** The code checks whether the current close is beyond a swing. It does not require the preceding close to be on the other side or require the first break to occur after H1 confirmation. The deterministic BUY example enters at 112 above a 110 swing after the preceding candle already closed at 111 before H1 confirmation. SELL has the same behavior. This is a rule ambiguity with material trade impact, not future-data leakage.

2. **Cold startup underfills the range filter.** main_live.py supplies 50 D1 bars, while the configured range comparison needs 60 prior bars plus the evaluated day. The audit reproduces a full-history rank of 70%, which blocks trading, versus 63.27% with 50 bars, which allows it. At least 61 completed D1 bars are needed for that comparison. A consistent warm-up policy should also be tested for EMA initialization.

The actual 14 July restart provides a concrete example. Reconstructing the 14:48:58 UTC startup with stored broker candles and 50 D1 bars reproduces the 15:05 BUY signal at 29,649.4, SL 29,360.8, and TP 30,803.8. These match the supplied log and journal for ticket 1807793687. With 61 D1 bars, the range rank reaches the blocking threshold of 0.70 and no signal occurs; the EMA trend stays BUY in both cases. The actual position later lost $152.18 net. This is an isolated current-code reconstruction of the signal, not a replay of the entire account or its exact broker fills. Evidence is saved in `restart_reproduction.json`.

3. **A rejected setup can be consumed while another position is open.** Failed2 sets its traded-setup flag when it emits a proposal. With a free slot, the rejection hook releases it. With an occupied strategy slot, the engine's legacy rejection path skips that hook, so the unsubmitted H1 setup stays consumed. This can suppress entry after the existing trade closes. It does not overwrite an accepted stop or target.

4. **Cold recovery cannot restore setup consumption.** A matching checkpoint preserves the current state, but signals carry no setup/attempt identity and the strategy has no order-adoption callback. A reconstructed strategy can propose a previously traded H1 setup after that position has closed. Broker portfolio reconciliation prevents concurrent duplicates, but it does not provide durable one-trade-per-setup history.

5. **Stop selection and H4 refresh need explicit documentation.** The audit confirms that a newer opposite pivot after the broken swing is ignored for the stop, and same-direction H4 refresh clears an H1 confirmation. These are coherent possible rule choices, but changing either is a new strategy hypothesis that needs its own comparison.

The ten deterministic audit cases also confirm delayed fractal availability, strict H4/H1/M5 timing, BUY/SELL symmetry, and next-bar market execution with the locked target. They intentionally reproduce limitations as well as correct behavior. Passing this audit is not a certificate that all strategy choices are sound.

The pending-order bid-touch issue discussed for EmaFib is not active in this market-entry configuration. Failed2 market mode no longer emits CANCEL signals. FVG mode and unused alternative filters are outside this review.

## Observed events in the long replay

| Source | Signals | Accepted | Occupied-slot signals | Accepted without fresh cross | Signals with break before H1 |
|---|---:|---:|---:|---:|---:|
| dukascopy | 294 | 223 | 71 | 50 | 112 |
| histdata | 276 | 212 | 64 | 49 | 109 |
| mt5_icmarkets_utc | 174 | 152 | 22 | 25 | 28 |

Counts can overlap. Accepted orders can remain open at a period boundary; closed-trade statistics exclude that exposure.

## Diagnostic fresh-cross comparison

This research-only variant adds one condition: the previous close must not already be beyond the selected swing. It holds all numeric parameters and other rules fixed. It is not an optimized configuration or a production change. It permits a later re-cross of an older swing; it does not enforce a first-ever break after H1.

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy, current | 223 | 30.04 | +105.00 | 1.67 | 0.471 | 12.04 | 8 / 10 |
| dukascopy, fresh_cross | 212 | 28.77 | +86.48 | 1.57 | 0.408 | 19.31 | 4 / 17 |
| histdata, current | 212 | 30.19 | +101.68 | 1.68 | 0.480 | 12.04 | 8 / 10 |
| histdata, fresh_cross | 201 | 28.86 | +82.95 | 1.58 | 0.413 | 18.01 | 4 / 17 |
| mt5_icmarkets_utc, current | 152 | 27.63 | +53.29 | 1.48 | 0.351 | 10.14 | 3 / 8 |
| mt5_icmarkets_utc, fresh_cross | 147 | 28.57 | +58.65 | 1.56 | 0.399 | 13.00 | 3 / 13 |

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy, current, 2026 | 28 | 21.43 | +0.85 | 1.04 | 0.031 | 6.13 | 1 / 5 |
| dukascopy, fresh_cross, 2026 | 26 | 23.08 | +2.85 | 1.14 | 0.110 | 5.13 | 2 / 5 |
| histdata, current, 2026 | 26 | 23.08 | +2.85 | 1.14 | 0.110 | 6.13 | 1 / 5 |
| histdata, fresh_cross, 2026 | 24 | 25.00 | +4.85 | 1.26 | 0.202 | 5.13 | 2 / 5 |
| mt5_icmarkets_utc, current, 2026 | 18 | 38.89 | +16.41 | 2.49 | 0.912 | 3.00 | 3 / 3 |
| mt5_icmarkets_utc, fresh_cross, 2026 | 18 | 33.33 | +10.93 | 1.91 | 0.607 | 4.00 | 2 / 4 |

## Spread stress

Full replays use 1, 2, and 5 index points of spread. Index commission remains zero, matching the supplied broker history. Spread stress does not model every form of slippage or financing.

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy, 2020_2025 | 223 | 30.04 | +105.00 | 1.67 | 0.471 | 12.04 | 8 / 10 |
| dukascopy, spread_2 | 223 | 30.04 | +99.08 | 1.63 | 0.444 | 12.04 | 8 / 10 |
| dukascopy, spread_5 | 223 | 29.60 | +78.47 | 1.50 | 0.352 | 12.04 | 8 / 10 |
| histdata, 2020_2025 | 212 | 30.19 | +101.68 | 1.68 | 0.480 | 12.04 | 8 / 10 |
| histdata, spread_2 | 212 | 30.19 | +96.25 | 1.65 | 0.454 | 12.04 | 8 / 10 |
| histdata, spread_5 | 212 | 29.72 | +76.90 | 1.51 | 0.363 | 12.04 | 8 / 10 |
| mt5_icmarkets_utc, 2020_2025 | 152 | 27.63 | +53.29 | 1.48 | 0.351 | 10.14 | 3 / 8 |
| mt5_icmarkets_utc, spread_2 | 152 | 27.63 | +49.61 | 1.45 | 0.326 | 10.25 | 3 / 8 |
| mt5_icmarkets_utc, spread_5 | 153 | 27.45 | +38.89 | 1.35 | 0.254 | 10.57 | 3 / 8 |

## Calendar years and direction

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy, 2020 | 34 | 38.24 | +29.68 | 2.41 | 0.873 | 10.00 | 6 / 10 |
| dukascopy, 2021 | 43 | 37.21 | +34.17 | 2.27 | 0.795 | 7.00 | 2 / 7 |
| dukascopy, 2022 | 34 | 23.53 | +5.89 | 1.23 | 0.173 | 9.00 | 2 / 9 |
| dukascopy, 2023 | 28 | 32.14 | +15.99 | 1.84 | 0.571 | 7.00 | 2 / 7 |
| dukascopy, 2024 | 41 | 26.83 | +13.22 | 1.44 | 0.322 | 5.19 | 2 / 5 |
| dukascopy, 2025 | 43 | 23.26 | +6.06 | 1.18 | 0.141 | 8.04 | 2 / 8 |
| histdata, 2020 | 34 | 38.24 | +29.68 | 2.41 | 0.873 | 10.00 | 6 / 10 |
| histdata, 2021 | 43 | 37.21 | +34.17 | 2.27 | 0.795 | 7.00 | 2 / 7 |
| histdata, 2022 | 34 | 23.53 | +5.89 | 1.23 | 0.173 | 9.00 | 2 / 9 |
| histdata, 2023 | 17 | 35.29 | +12.67 | 2.15 | 0.745 | 7.00 | 2 / 7 |
| histdata, 2024 | 41 | 26.83 | +13.22 | 1.44 | 0.322 | 5.19 | 2 / 5 |
| histdata, 2025 | 43 | 23.26 | +6.06 | 1.18 | 0.141 | 8.04 | 2 / 8 |
| mt5_icmarkets_utc, 2020 | 25 | 32.00 | +14.57 | 1.86 | 0.583 | 5.00 | 2 / 5 |
| mt5_icmarkets_utc, 2021 | 26 | 30.77 | +12.52 | 1.70 | 0.482 | 10.14 | 2 / 8 |
| mt5_icmarkets_utc, 2022 | 24 | 16.67 | -4.22 | 0.79 | -0.176 | 7.94 | 1 / 6 |
| mt5_icmarkets_utc, 2023 | 16 | 37.50 | +13.13 | 2.31 | 0.821 | 4.00 | 3 / 4 |
| mt5_icmarkets_utc, 2024 | 30 | 26.67 | +9.19 | 1.42 | 0.306 | 7.09 | 2 / 6 |
| mt5_icmarkets_utc, 2025 | 31 | 25.81 | +8.09 | 1.34 | 0.261 | 6.00 | 2 / 6 |

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy, BUY | 177 | 29.94 | +81.18 | 1.65 | 0.459 | 12.00 | 8 / 12 |
| dukascopy, SELL | 46 | 30.43 | +23.82 | 1.74 | 0.518 | 10.00 | 3 / 10 |
| histdata, BUY | 166 | 30.12 | +77.86 | 1.67 | 0.469 | 12.00 | 8 / 12 |
| histdata, SELL | 46 | 30.43 | +23.82 | 1.74 | 0.518 | 10.00 | 3 / 10 |
| mt5_icmarkets_utc, BUY | 122 | 28.69 | +48.34 | 1.55 | 0.396 | 9.09 | 3 / 8 |
| mt5_icmarkets_utc, SELL | 30 | 23.33 | +4.95 | 1.22 | 0.165 | 11.00 | 2 / 11 |

## Holding duration

Typical holds are short, but the tails are substantial. Broker median holding time is 3.05 hours and its longest trade lasts 701.8 hours (29.2 days). Dukascopy and HistData medians are about four hours, with maximum holds of 1,565.5 hours (65.2 days). Median entry reward/risk is about 3.92 rather than the signal-price target of 4. Long holds make financing and weekend gaps relevant even though many trades close the same day.

## Illustrative financing sensitivity

This subtracts a hypothetical $0, $3, or $7 per lot per 24 hours held from existing paths. It is not a reconstruction of actual broker swap, and does not model credits, triple-swap days, changed sizing, or changed trade paths.

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy, $0/lot/day | 223 | 30.04 | +105.00 | 1.67 | 0.471 | 12.04 | 8 / 10 |
| dukascopy, $3/lot/day | 223 | 30.04 | +93.50 | 1.58 | 0.419 | 12.31 | 8 / 10 |
| dukascopy, $7/lot/day | 223 | 30.04 | +78.16 | 1.47 | 0.350 | 12.67 | 8 / 10 |
| histdata, $0/lot/day | 212 | 30.19 | +101.68 | 1.68 | 0.480 | 12.04 | 8 / 10 |
| histdata, $3/lot/day | 212 | 30.19 | +90.93 | 1.60 | 0.429 | 12.31 | 8 / 10 |
| histdata, $7/lot/day | 212 | 30.19 | +76.60 | 1.49 | 0.361 | 12.67 | 8 / 10 |
| mt5_icmarkets_utc, $0/lot/day | 152 | 27.63 | +53.29 | 1.48 | 0.351 | 10.14 | 3 / 8 |
| mt5_icmarkets_utc, $3/lot/day | 152 | 27.63 | +46.03 | 1.41 | 0.303 | 11.16 | 3 / 8 |
| mt5_icmarkets_utc, $7/lot/day | 152 | 27.63 | +36.34 | 1.31 | 0.239 | 12.51 | 3 / 8 |

## Copied DEMO history

The supplied 18 September broker export contains 8 closed Failed2 positions, 1 win, and $-778.31 net P&L. Monetary PF is 0.39. Swap totals $-76.16; commission is zero. All eight tickets match market-order journal records despite truncated broker comments. Seven losses follow the first winner. This is a small, weak forward sample, not current-code validation.

Ticket 1927396897 opened on Friday 11 September at 29,461.9, with reported SL 29,342.7 and 1.1 lots. It closed early Monday at 29,070.5. Net loss was $452.70 including $22.16 swap, about 3.45 times the $131.12 risk implied by the reported SL. The price gap therefore matters more than ordinary spread for this example. The strategy has no time-based exit, and its positions can remain open over weekends.

The copied journal records {'SIGNAL': 115, 'CANCEL_REQUESTED': 106, 'ORDER_PLACED': 8, 'CLOSE': 7, 'REJECTED': 1}. Rejections: {'portfolio': 1}. Its 106 cancellation requests belong to earlier market-mode code; the current implementation suppresses those signals. The journal is partial and mixes historical versions, settings, risk, restarts, and portfolio conditions. It cannot reconcile one-for-one with the isolated current-parameter replay.

## Data and method

Completed 32 sequential replays and 3 plain-versus-observed controls. Every control matches all trade fields and ending exposure. Source and code hashes are saved; code hashes stayed unchanged during the run. All 172 existing unit tests pass, and ten separate deterministic audit cases reproduce the findings.

All sources use M5 execution and completed H1/H4/D1 bars, a $10,000 initial balance, 0.5% risk, one open position for this strategy, a one-point default spread, and zero index commission. The same DEMO parameters are applied to USA100 aliases and USTEC with one-point pip size and $1 per point per lot. HistData passes the provenance-enforcing loader. The newer full broker H4 export is selected explicitly rather than merged with the superseded shorter export.

The main period is 2020 through 2025; recent performance ends on 14 July 2026. No price bars after that cutoff enter research decisions. News, shared-account position limits and daily-loss gates, variable spreads, extra slippage, and actual swap are excluded. MT5 operation was not tested on this PC. R drawdown is closed-trade drawdown, not floating account-equity drawdown.

Across 2020 through 14 July 2026, 99.95% of shared Dukascopy/HistData M5 candles have identical OHLC. HistData lacks 9,187 M5 timestamps found in Dukascopy. It is useful comparable data, but does not establish an independent feed. Broker prices differ, and its H4/D1 session boundaries have no exact opening-time matches with UTC-aligned Dukascopy bars. Those comparisons include both price-feed and candle-boundary differences.

## Period-end exposure

- dukascopy current fold_2020_train: 1 open/pending
- dukascopy current fold_2022_test: 1 open/pending
- dukascopy current fold_2024_train: 1 open/pending
- histdata current fold_2020_train: 1 open/pending
- histdata current fold_2022_test: 1 open/pending
- histdata current fold_2024_train: 1 open/pending

Positions are not force-closed with future data; their eventual outcomes do not enter the reported closed-trade totals.

## Reproduction

```powershell
.venv\Scripts\python.exe research_failed2_review.py
.venv\Scripts\python.exe audit_failed2_logic.py
.venv\Scripts\python.exe audit_failed2_demo.py
.venv\Scripts\python.exe audit_failed2_data.py
.venv\Scripts\python.exe audit_failed2_restart.py
.venv\Scripts\python.exe summarize_failed2_review.py
```

Detailed trades, examples, fold results, source coverage, hashes, and copied DEMO evidence are under `output/failed2_review_20260928/`.
