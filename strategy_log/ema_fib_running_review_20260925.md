# EmaFib Running logic and performance review, 25 September 2026

Historical initial review of the frozen original code. Its recommended corrections
are now implemented locally; see the [correction and validation report](ema_fib_running_corrections_20260925.md)
for current results and the latest recommendation.

Status: still included in the local DEMO suite. This review changes no production strategy logic, parameters, membership, or risk. The earlier STRONG walk-forward result is historical evidence from an older code/data/simulator combination. It does not resolve the defects reproduced here.

## Assessment

The trading idea is coherent, but the current implementation does not reliably follow its order lifecycle or documented running-extreme rule. It is worth correcting and retesting before deciding to retire it. Six matched pairs return +33.59R on Dukascopy, +42.41R on verified HistData, and +17.31R on IC Markets over 2020 through 2025. These are current-code results with confirmed defects, not corrected-strategy results.

The broker edge is modest: PF 1.17, a 24.10R closed-trade drawdown, and 23 consecutive losses. It survives the 1-pip spread replay at +17.10R and a separate illustrative $7/lot/day financing debit at +12.99R. However, 2024 and 2025 together lose 14.04R. January through 14 July 2026 adds only about 1.10R from four trades. The older STRONG label overstates what the present evidence establishes.

GBPUSD contributes most profit in the long broker sample. AUDUSD and NZDUSD are profitable but have only eight and six trades respectively over six years. EURUSD is slightly negative and USDJPY loses on all three sources. Pair removal would be a new research decision and should not be selected from this same evaluation sample without validation. About 11% of accepted broker-replay pending orders become closed trades, reflecting frequent cancellation and replacement.

The 12 deterministic audit cases and historical observers identify real defects. On broker data, 20 losing trades invalidate the wrong anchor, 26 closes leave local pending state, and two H1 touches clear orders that remain unfilled. The copied DEMO evidence is also weak: nearly all its profit comes from an order the old bot tried unsuccessfully to cancel. Correct and compare the lifecycle and running-extreme changes separately, then repeat rolling validation before parameter tuning or promotion.

## What the strategy actually does

D1 and H1 EMA 10/20 directions must agree. D1 simple ATR over 14 completed daily bars must be at least 50 pips. The current H1 EMA-separation filter and loss cooldown are disabled. Entries use H1 candle opening-hour labels 09:00 through 19:00 UTC, so new decisions occur after those bars close, roughly 10:00 through 20:00 UTC. Pending management also runs outside entry hours.

A BUY uses a confirmed H1 fractal low, the low of that candle's body, and a running highest close. A SELL mirrors this with a fractal high and running lowest close. With fractal_n=2, confirmation requires two completed bars to the right. The Fibonacci entry uses 0.786 of the body-based range. The stop is at the fractal wick and the target uses a 2.5 extension of the body-based range. A directional three-candle wick gap is required; there is no extra gap-size, middle-candle strength, or gap-retest test.

The name min_swing_pips is misleading here: the configured 30 pips is a minimum entry-to-stop distance, not a minimum body swing range. fib_tp=2.5 is not a fixed 2.5R target. Actual reward/risk depends on the distance from body to wick. For example, body low 1.102, running high 1.115, and wick low 1.100 give entry 1.104782, stop 1.100, target 1.1345, and about 6.21R before costs. The maximum with zero extra wick distance is approximately 10.68R. Risk checks still enforce the minimum 1R rule.

The pending-order update cancels when the newly calculated entry differs by more than one pip, including changes caused by a new fractal anchor. Replacement is considered on a later H1 bar and must pass the entry filters again. It is not an atomic amendment. Filled positions retain their original SL/TP. Swing age is an entry filter, not an expiry timer for existing orders.

## Confirmed implementation defects

1. H1 bid-price touches stand in for execution-confirmed fills. An unfilled BUY whose bid touches the limit while ask remains above it can disappear from local tracking and miss a later cancellation. Gap fills can also disagree with the H1 straddle heuristic.

2. A new proposal can replace the accepted trade's anchor while a position is already open. The portfolio rejects the duplicate order, but the overwritten anchor remains. A later loss can invalidate the wrong fractal. A 30-pip minimum stop does not prevent this portfolio rejection path, contrary to the old strategy-log explanation.

3. Close callbacks clear anchor snapshots but leave local pending entry/direction intact. A trade that fills and stops between H1 decisions can leave phantom pending state. Conversely, cancellation clears local state before broker confirmation. The engine can retry cancellation, but the strategy no longer retains authoritative order ownership.

4. A newly confirmed fractal resets the running extreme to None, then initializes it using only the current confirmation candle. Earlier closes between the fractal and its confirmation are already known but omitted. A reproduced BUY example should start at the known 1.114 high close but instead starts at 1.108; the SELL mirror is also wrong relative to the documented rule. This is an initialization error, not future-data leakage.

5. Signals carry no setup/attempt identity and the strategy has no order-state adoption callback. A valid strategy checkpoint can preserve state, but a cold restart or invalidated checkpoint cannot recover an accepted order's original anchor from the setup ledger. Falling back to the current fractal on a loss can misattribute an inherited trade. The global checkpoint fingerprint changes when suite membership changes, so retirement of Retracement makes this recovery limitation relevant to the next updated run.

The deterministic audit verifies arithmetic and delayed fractal confirmation, and reproduces both BUY and SELL initialization errors plus the lifecycle defects. These findings do not establish how much profit would change after correction. This review measures the current implementation; it does not present its metrics as corrected-strategy performance.

All 150 existing unit tests pass. They do not cover these Running defects. The separate audit cases deliberately assert the observed faulty outcomes to make the findings reproducible; passing those audit assertions is evidence of the defects, not a strategy-correctness certificate.

## Research method

Completed 64 sequential fixed-parameter replays and 2 plain-versus-observed controls. Both controls compare every trade field and ending exposure. The observer records defects without changing decisions. Code and input hashes are in the manifest, and code hashes matched at completion.

The long period is 2020 through 2025, with a separate 1 January through 14 July 2026 comparison. Every run starts fresh with 180 days of warm-up. M5 executes H1/D1 signals. Spread and $7 per lot round-trip commission are included. Variable spreads, extra slippage, swaps, news filtering, and shared account portfolio/daily-loss gates are excluded. Each pair starts at $10,000 with 0.5% risk; tables combine net-R trade histories in closing-time order, not pooled account returns or equity drawdowns.

Verified HistData passes the provenance-enforcing loader. It is not an independent price-feed confirmation: the previous audit found approximately 99.98% identical OHLC at shared M5 timestamps. Missing bars and higher-timeframe aggregation differ. Broker D1 bars follow the broker session rather than UTC midnight. USDCAD broker M5/H1/D1 begin in January 2025, an accepted coverage limit. It is excluded from all long-period source comparisons and included only in periods with adequate warm-up. Data after 14 July 2026 remains excluded.

The newly supplied broker M5 files end at 21:00 UTC on 14 July. Requesting an end date of 15 July does not guarantee coverage through the final UTC midnight. Period-end open/pending exposure is reported below and excluded from closed-trade statistics.

## Seven FX pairs, 2020 through 2025

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy | 156 | 28.85 | +35.38 | 1.31 | 0.227 | 25.37 | 6 / 12 |
| histdata | 156 | 29.49 | +44.21 | 1.39 | 0.283 | 25.37 | 6 / 12 |

## Six matched pairs, 2020 through 2025

EURUSD, GBPUSD, AUDUSD, NZDUSD, USDJPY, and USDCHF. USDCAD is excluded from every source.

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy | 137 | 29.20 | +33.59 | 1.33 | 0.245 | 19.47 | 4 / 12 |
| histdata | 137 | 29.93 | +42.41 | 1.43 | 0.310 | 19.47 | 4 / 12 |
| mt5_icmarkets_utc | 130 | 26.15 | +17.31 | 1.17 | 0.133 | 24.10 | 4 / 23 |

## Seven FX pairs, January through 14 July 2026

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy | 4 | 50.00 | +1.10 | 1.54 | 0.275 | 2.05 | 1 / 2 |
| histdata | 4 | 50.00 | +1.10 | 1.54 | 0.275 | 2.05 | 1 / 2 |
| mt5_icmarkets_utc | 4 | 50.00 | +1.10 | 1.53 | 0.274 | 2.05 | 1 / 2 |

## By pair, 2020 through 2025

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| EURUSD, dukascopy | 18 | 22.22 | -1.68 | 0.88 | -0.093 | 7.13 | 2 / 7 |
| EURUSD, histdata | 18 | 22.22 | -1.68 | 0.88 | -0.093 | 7.13 | 2 / 7 |
| EURUSD, mt5_icmarkets_utc | 17 | 23.53 | -0.72 | 0.95 | -0.042 | 6.10 | 2 / 6 |
| GBPUSD, dukascopy | 41 | 26.83 | +20.35 | 1.64 | 0.496 | 17.62 | 2 / 16 |
| GBPUSD, histdata | 43 | 27.91 | +27.24 | 1.83 | 0.633 | 17.62 | 2 / 16 |
| GBPUSD, mt5_icmarkets_utc | 37 | 21.62 | +11.42 | 1.37 | 0.309 | 16.73 | 2 / 15 |
| AUDUSD, dukascopy | 9 | 33.33 | +6.31 | 2.03 | 0.701 | 3.06 | 2 / 3 |
| AUDUSD, histdata | 9 | 33.33 | +6.31 | 2.03 | 0.701 | 3.06 | 2 / 3 |
| AUDUSD, mt5_icmarkets_utc | 8 | 25.00 | +5.26 | 1.86 | 0.657 | 3.06 | 1 / 3 |
| NZDUSD, dukascopy | 8 | 75.00 | +15.81 | 8.78 | 1.976 | 1.02 | 3 / 1 |
| NZDUSD, histdata | 8 | 75.00 | +15.81 | 8.78 | 1.976 | 1.02 | 3 / 1 |
| NZDUSD, mt5_icmarkets_utc | 6 | 66.67 | +9.80 | 5.82 | 1.634 | 1.02 | 3 / 1 |
| USDJPY, dukascopy | 54 | 24.07 | -7.62 | 0.82 | -0.141 | 20.17 | 1 / 10 |
| USDJPY, histdata | 52 | 25.00 | -5.69 | 0.86 | -0.109 | 18.23 | 1 / 9 |
| USDJPY, mt5_icmarkets_utc | 54 | 22.22 | -11.54 | 0.73 | -0.214 | 19.74 | 2 / 13 |
| USDCAD, dukascopy | 19 | 26.32 | +1.79 | 1.13 | 0.094 | 7.81 | 2 / 6 |
| USDCAD, histdata | 19 | 26.32 | +1.79 | 1.13 | 0.094 | 7.81 | 2 / 6 |
| USDCHF, dukascopy | 7 | 42.86 | +0.42 | 1.10 | 0.059 | 3.07 | 2 / 3 |
| USDCHF, histdata | 7 | 42.86 | +0.42 | 1.10 | 0.059 | 3.07 | 2 / 3 |
| USDCHF, mt5_icmarkets_utc | 8 | 50.00 | +3.08 | 1.76 | 0.385 | 2.51 | 3 / 2 |

## Calendar-year breakdown, six matched pairs

These are closing-year slices of continuous replays, not new walk-forward folds. No parameter search or fresh walk-forward selection was run on the known-defective implementation. The historical STRONG label should be re-evaluated only after the corrections, with train-only selection and explicit cost assumptions.

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy, 2020 | 25 | 20.00 | +3.08 | 1.14 | 0.123 | 18.56 | 4 / 12 |
| dukascopy, 2021 | 2 | 100.00 | +3.16 | n/a | 1.579 | 0.00 | 2 / 0 |
| dukascopy, 2022 | 48 | 37.50 | +26.92 | 1.88 | 0.561 | 6.13 | 3 / 6 |
| dukascopy, 2023 | 15 | 26.67 | +3.05 | 1.27 | 0.203 | 7.92 | 3 / 6 |
| dukascopy, 2024 | 23 | 21.74 | -5.96 | 0.68 | -0.259 | 8.78 | 2 / 8 |
| dukascopy, 2025 | 24 | 25.00 | +3.35 | 1.18 | 0.140 | 8.17 | 3 / 8 |
| histdata, 2020 | 25 | 20.00 | +3.08 | 1.14 | 0.123 | 18.56 | 4 / 12 |
| histdata, 2021 | 2 | 100.00 | +3.16 | n/a | 1.579 | 0.00 | 2 / 0 |
| histdata, 2022 | 48 | 37.50 | +26.92 | 1.88 | 0.561 | 6.13 | 3 / 6 |
| histdata, 2023 | 16 | 31.25 | +10.86 | 1.96 | 0.679 | 4.87 | 3 / 4 |
| histdata, 2024 | 22 | 22.73 | -4.95 | 0.72 | -0.225 | 8.22 | 2 / 8 |
| histdata, 2025 | 24 | 25.00 | +3.35 | 1.18 | 0.140 | 8.17 | 3 / 8 |
| mt5_icmarkets_utc, 2020 | 22 | 22.73 | +5.97 | 1.32 | 0.271 | 15.63 | 4 / 11 |
| mt5_icmarkets_utc, 2021 | 2 | 100.00 | +4.40 | n/a | 2.202 | 0.00 | 2 / 0 |
| mt5_icmarkets_utc, 2022 | 46 | 32.61 | +17.99 | 1.57 | 0.391 | 6.12 | 3 / 6 |
| mt5_icmarkets_utc, 2023 | 14 | 28.57 | +2.98 | 1.29 | 0.213 | 7.96 | 3 / 7 |
| mt5_icmarkets_utc, 2024 | 20 | 20.00 | -5.78 | 0.65 | -0.289 | 8.80 | 1 / 8 |
| mt5_icmarkets_utc, 2025 | 26 | 15.38 | -8.26 | 0.63 | -0.318 | 15.31 | 2 / 15 |

## One-pip spread stress, six matched pairs

Spread is changed to 1 pip for every pair, with the same commission and strategy settings. The entire replay is rerun. A pending order fills at its order price, so a wider spread can leave some trade paths unchanged while causing other orders to miss their fills.

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy, six_2020_2025 | 137 | 29.20 | +33.59 | 1.33 | 0.245 | 19.47 | 4 / 12 |
| dukascopy, six_spread_1pip | 137 | 28.47 | +31.32 | 1.31 | 0.229 | 19.47 | 4 / 12 |
| histdata, six_2020_2025 | 137 | 29.93 | +42.41 | 1.43 | 0.310 | 19.47 | 4 / 12 |
| histdata, six_spread_1pip | 137 | 29.20 | +39.90 | 1.40 | 0.291 | 19.47 | 4 / 12 |
| mt5_icmarkets_utc, six_2020_2025 | 130 | 26.15 | +17.31 | 1.17 | 0.133 | 24.10 | 4 / 23 |
| mt5_icmarkets_utc, six_spread_1pip | 130 | 26.15 | +17.10 | 1.17 | 0.132 | 24.10 | 4 / 23 |

## Illustrative financing debit, six matched pairs

This subtracts $0, $3, or $7 per lot per 24 hours held, prorated by duration, from existing trade paths. It is a sensitivity calculation, not actual broker swap. Directional credits, rollover times, triple-swap days, changed lot sizing, and compounding are not modeled.

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy, $0/lot/day | 137 | 29.20 | +33.59 | 1.33 | 0.245 | 19.47 | 4 / 12 |
| dukascopy, $3/lot/day | 137 | 29.20 | +31.52 | 1.31 | 0.230 | 19.74 | 4 / 12 |
| dukascopy, $7/lot/day | 137 | 29.20 | +28.76 | 1.28 | 0.210 | 20.12 | 4 / 12 |
| histdata, $0/lot/day | 137 | 29.93 | +42.41 | 1.43 | 0.310 | 19.47 | 4 / 12 |
| histdata, $3/lot/day | 137 | 29.93 | +40.29 | 1.40 | 0.294 | 19.74 | 4 / 12 |
| histdata, $7/lot/day | 137 | 29.93 | +37.45 | 1.37 | 0.273 | 20.12 | 4 / 12 |
| mt5_icmarkets_utc, $0/lot/day | 130 | 26.15 | +17.31 | 1.17 | 0.133 | 24.10 | 4 / 23 |
| mt5_icmarkets_utc, $3/lot/day | 130 | 26.15 | +15.46 | 1.15 | 0.119 | 24.32 | 4 / 23 |
| mt5_icmarkets_utc, $7/lot/day | 130 | 26.15 | +12.99 | 1.13 | 0.100 | 24.60 | 4 / 23 |

## USDCAD only, July through December 2025

July starts after the available broker history provides the required warm-up. The same dates are used for every source.

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy | 0 | n/a | +0.00 | n/a | n/a | 0.00 | 0 / 0 |
| histdata | 0 | n/a | +0.00 | n/a | n/a | 0.00 | 0 / 0 |
| mt5_icmarkets_utc | 0 | n/a | +0.00 | n/a | n/a | 0.00 | 0 / 0 |

## Observed lifecycle problems, six matched pairs

| Source | Accepted | Cancelled | Closed | Bid-touch false fills | Occupied-slot proposals | Wrong-anchor losses | Close leaves pending |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy | 1227 | 1090 | 137 | 1 | 119 | 22 | 24 |
| histdata | 1197 | 1060 | 137 | 1 | 119 | 22 | 24 |
| mt5_icmarkets_utc | 1213 | 1083 | 130 | 2 | 110 | 20 | 26 |

Counts refer to current-code 2020 through 2025 runs at the default modeled spread. They are events, not additive numbers of affected trades. Defects can overlap. Accepted and cancellation counts describe orders, while closed counts describe executed trades. Indicator-only extreme-initialization counts and examples are recorded separately in each result and include warm-up bars. These counts cannot be translated directly into a performance correction.

## Copied DEMO evidence

The 18 September export contains 2 closed Running positions, 2 wins, with combined profit after commission and swap of $1,300.76. The earliest entry is 2026.06.15 01:04:54 and latest close is 2026.06.24 10:10:48 in broker report time. With no losses, profit factor has no finite estimate; two wins do not validate a strategy.

The larger winner is especially unsuitable as evidence of the intended strategy. EURUSD ticket 1689274839 was submitted on 5 June. On 7 June at 21:00 UTC, the copied log records cancellation failure with retcode 10018, immediately followed by an incorrect cancellation-success log. The journal also records ORDER_CANCELLED. The broker history shows that the order instead filled on 15 June and closed on 24 June for $1,205.46 net. The remaining USDJPY winner contributes $95.30 net. Thus most copied DEMO profit came from an order the bot intended to cancel. This was an older execution-path failure, before the September fixes; it is not proof that the same execution bug remains. Exact log lines and journal rows are preserved in demo_evidence.json.

The copied journal has {'SIGNAL': 42, 'ORDER_PLACED': 20, 'CANCEL_REQUESTED': 20, 'ORDER_CANCELLED': 28, 'REJECTED': 2, 'CLOSE': 2, 'CLOSE_PENDING_RECONCILIATION': 3}. Rejections: {'portfolio': 2}. Counts cover a partial window and cancellation rows include recoveries, so they are not a complete placement-to-close funnel. The report predates the confirmed September restart and mixes historical code/settings/risk. It cannot establish correct operation of the current implementation.

## Next decision

Do not optimize numeric parameters or treat the historical STRONG label as current validation. Correct accepted-order ownership and restart recovery first, then separately correct the running-extreme initialization to measure each effect. Re-run the same fixed settings on the same source windows before selecting parameters or deciding whether to retain the strategy. The portfolio already prevents duplicate positions; a simple local position flag without acceptance/rejection/recovery handling would repeat the earlier Retracement failure.

This analysis does not remove Running from DEMO or change the trading host. The evidence differs from Retracement: Running has a body-based range, wick stop, different payoff distribution, and a moving pending level. Its retirement decision should use its own corrected broker results rather than inherit the Retracement decision.

## Reproduction

```powershell
.venv\Scripts\python.exe research_ema_fib_running_review.py
.venv\Scripts\python.exe audit_ema_fib_running_logic.py
.venv\Scripts\python.exe audit_ema_fib_running_demo.py
.venv\Scripts\python.exe summarize_ema_fib_running_review.py
```

Trade files, examples, assumptions, hashes, audit cases, and controls are under `output/ema_fib_running_review_20260925/`. All production code and DEMO settings remain unchanged by this review.

## Period-end exposure

All runs ended flat.
