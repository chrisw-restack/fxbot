# IMS trend strategy review, 2026-09-29

Scope: `ImsStrategy`, DEMO name `IMS_H4_M15`. This is not IMS Reversal. Production logic, parameters, symbols, and risk were left unchanged.

## Assessment

Across the current eight symbols, 2020-2025 remains positive at +27.11R on Dukascopy and +22.91R on corrected HistData, with profit factors 1.16 and 1.14. The data repair has not erased the historical edge, but the margin is modest.

On the same four symbols with long broker M5 history, however, 2020-2025 returns +25.21R on Dukascopy, +19.62R on HistData, and -4.86R on broker data. The recent five-symbol broker window returns +10.64R across only 30 trades. This is mixed evidence, not a reliable broker-confirmed edge across the full suite.

The trend-following idea is coherent, but the current implementation has setup lifecycle defects. Its old MODERATE label belongs to the earlier nine-symbol study and does not validate today's eight-symbol configuration with the current simulator. Repair and revalidate setup tracking before searching parameters or increasing exposure. This review does not establish a validated replacement configuration.

## Rules actually executed

H4 finds a confirmed fractal origin, a later wick break of the preceding opposite swing, and a three-candle imbalance anywhere in that leg. The range extends with new extremes. EMA 20/50 direction and at least 0.1% separation filter entries. M15 must touch the 60% level for buys or 40% for sells, then close beyond a confirmed opposite fractal. The entry leg must contain an imbalance, and its origin must lie in the appropriate half of the H4 range. A pending order is proposed at the leg midpoint, with the stop at its origin and a 2.5R target supplied by the runner.

The session checks M15 candle opening hours 12 through 16 UTC, so completed-candle decisions normally occur from 12:15 through 17:00. H4 depth expiry uses a wick below 30% or above 70%; M15 depth expiry uses the close. Origin breaches also expire on M15 wicks. The top strategy docstring still says a strict 50% zone touch, while executable entry activation uses 60%/40%.

Confirmed fractals use completed right-hand bars. The shared replay dispatches higher-timeframe bars only after their close, and orders cannot fill on the signal candle. No direct future-candle read was found in this path. Those safeguards do not solve the state and execution issues below.

## Logic findings

1. **Expired setups can return without passing their own invalidation rules.** The scanner has no retired-origin memory and checks the historical break/FVG without rejecting a subsequently breached origin. The audit constructs an H4 origin at 90, a high of 112, an expiry candle with low 92, then a candle with low 89. The same origin at 90 is recreated on that last candle even though it is already broken. A later M15 check may expire it again, but the scanner is not returning a consistently valid setup.

2. **Trade closure is not tied to the originating setup.** A win clears the current H4 bias by symbol. A loss resets the current M15 state by symbol. If the bias changed while a position was open, the old result updates the newer setup. The observer records actual occurrences and delegates to unchanged production callbacks.

3. **Proposal, pending order, and filled position share one flag.** The strategy has no order-accepted, order-sync, proposal-specific rejection, or attributed-close interface. It resets state when issuing a cancellation, before the broker confirms removal. The engine does retry failed cancellations and protects filled positions, so this is a strategy tracking problem, not evidence that cancellation closes filled trades. An occupied-slot rejection can retain state for a proposal that was never accepted.

4. **Target-touch cancellation only runs during entry hours.** A pending order remains locally active after an otherwise identical target-touch candle at 18:00, while the 12:00 candle emits CANCEL. Structural expiry does run outside entry hours. Whether target cancellation should run all hours is a policy choice to compare after fixing identity and confirmation tracking. Sell target checks also use bid lows rather than the executable ask.

5. **Some pattern definitions are broader than their names suggest.** The H4 break is a wick break; M15 only needs to remain beyond an old fractal, with no fresh-cross requirement. The FVG can precede the final break and need not remain unfilled. These are design choices, not automatic coding errors. Make the intended rules explicit before testing stricter alternatives.

## Reproduction and assumptions

21 sequential fixed-parameter replays. Eight symbols on Dukascopy and verified HistData; five on broker data. Continuous runs start January 2020 with 180 days of preceding warmup, and stop before July 15, 2026. Broker USDCAD starts April 2025 with its available January-March history for warmup. Tables partition trades by close time; open exposure is not forcibly liquidated. Later slices retain earlier strategy state and positions, so these are chronological diagnostics, not newly selected out-of-sample tests or a fresh walk-forward validation.

M5 execution, bid/ask spread handling, configured spreads, $7 per lot round-trip FX commission, and 0.5% risk. Swaps and variable spread spikes are excluded. Cross-pair spreads remain uncalibrated placeholders in config. Crosses receive same-source historical USD conversion quotes. Each symbol has its own $10,000 account; merged results are a chronological sum of trade R, not a shared-account return. Shared portfolio limits, news gates, and the 2% daily-loss gate are not modeled in these standalone runs. Drawdown is closed-trade R, not floating account equity.

The EURUSD Dukascopy observer control reproduces every closed trade and final open exposure of the plain production strategy. The six deterministic audit findings pass. The existing 186 unit tests also pass. Input and code hashes, HistData metadata hashes, individual trades, rejection counts, and examples are saved in `output/ims_trend_review_20260929/`. Passing tests do not certify profitability.

The generic `run_backtest.py ims_h4_m15` command loads only the strategy timeframes and uses its fallback global symbol list. It therefore does not reproduce this explicitly configured eight-symbol M5 audit. Use `research_ims_trend_review.py` for these results. The generic runner and DEMO runner both supply 2.5R correctly.

## Eight current symbols, January 2020 through December 2025

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy | 246 | 33.74 | +27.11 | 1.16 | 0.110 | 17.16 | 3 / 10 |
| histdata | 231 | 33.33 | +22.91 | 1.14 | 0.099 | 19.61 | 3 / 11 |

## Same four symbols with long broker M5 history

USDJPY, AUDUSD, EURUSD, GBPUSD. January 2020 through December 2025.

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy | 134 | 35.82 | +25.21 | 1.28 | 0.188 | 17.40 | 3 / 13 |
| histdata | 126 | 34.92 | +19.62 | 1.22 | 0.156 | 19.61 | 3 / 13 |
| mt5_icmarkets_utc | 137 | 29.93 | -4.86 | 0.95 | -0.035 | 17.74 | 4 / 8 |

January 2026 through July 14, the same four symbols.

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy | 5 | 20.00 | -13.66 | 0.15 | -2.733 | 13.66 | 1 / 2 |
| histdata | 5 | 20.00 | -13.66 | 0.15 | -2.733 | 13.66 | 1 / 2 |
| mt5_icmarkets_utc | 10 | 30.00 | +0.63 | 1.10 | 0.063 | 3.35 | 1 / 4 |

## Same five symbols in the available recent broker window

The four above plus USDCAD. April 1, 2025 through July 14, 2026.

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy | 30 | 40.00 | -2.45 | 0.92 | -0.082 | 15.98 | 3 / 4 |
| histdata | 30 | 40.00 | -2.45 | 0.92 | -0.082 | 15.98 | 3 / 4 |
| mt5_icmarkets_utc | 30 | 40.00 | +10.64 | 1.57 | 0.355 | 6.22 | 4 / 5 |

## Per-symbol results, January 2020 through December 2025

### dukascopy

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| USDJPY | 40 | 25.00 | -7.85 | 0.75 | -0.196 | 20.51 | 2 / 9 |
| EURAUD | 27 | 33.33 | +2.35 | 1.12 | 0.087 | 7.95 | 2 / 7 |
| CADJPY | 33 | 30.30 | -0.78 | 0.97 | -0.024 | 10.56 | 5 / 7 |
| USDCAD | 24 | 20.83 | -8.50 | 0.59 | -0.354 | 11.02 | 1 / 9 |
| AUDUSD | 25 | 28.00 | -2.37 | 0.88 | -0.095 | 14.74 | 4 / 9 |
| EURUSD | 36 | 44.44 | +17.65 | 1.83 | 0.490 | 4.76 | 4 / 4 |
| GBPCAD | 28 | 39.29 | +8.83 | 1.49 | 0.315 | 5.21 | 4 / 5 |
| GBPUSD | 33 | 45.45 | +17.78 | 1.94 | 0.539 | 4.22 | 4 / 4 |

### histdata

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| USDJPY | 37 | 24.32 | -8.15 | 0.73 | -0.220 | 20.82 | 2 / 9 |
| EURAUD | 24 | 37.50 | +5.51 | 1.34 | 0.230 | 6.85 | 2 / 6 |
| CADJPY | 30 | 23.33 | -8.01 | 0.68 | -0.267 | 15.15 | 4 / 14 |
| USDCAD | 26 | 23.08 | -6.21 | 0.70 | -0.239 | 10.06 | 1 / 9 |
| AUDUSD | 24 | 20.83 | -8.35 | 0.59 | -0.348 | 18.26 | 3 / 17 |
| EURUSD | 32 | 46.88 | +18.33 | 2.01 | 0.573 | 4.14 | 4 / 4 |
| GBPCAD | 25 | 44.00 | +12.00 | 1.81 | 0.480 | 5.21 | 4 / 5 |
| GBPUSD | 33 | 45.45 | +17.79 | 1.94 | 0.539 | 4.22 | 4 / 4 |

### mt5_icmarkets_utc

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| USDJPY | 36 | 25.00 | -8.97 | 0.71 | -0.249 | 16.83 | 3 / 12 |
| AUDUSD | 31 | 25.81 | -5.40 | 0.78 | -0.174 | 7.03 | 1 / 5 |
| EURUSD | 38 | 36.84 | +8.52 | 1.33 | 0.224 | 8.60 | 4 / 8 |
| GBPUSD | 32 | 31.25 | +0.98 | 1.04 | 0.031 | 5.47 | 2 / 5 |

## Annual four-symbol comparison

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2020 dukascopy | 25 | 44.00 | +12.09 | 1.82 | 0.484 | 5.37 | 2 / 5 |
| 2020 histdata | 24 | 41.67 | +9.64 | 1.65 | 0.401 | 5.37 | 2 / 5 |
| 2020 mt5_icmarkets_utc | 25 | 20.00 | -11.24 | 0.52 | -0.450 | 15.00 | 2 / 7 |
| 2021 dukascopy | 13 | 30.77 | -0.15 | 0.98 | -0.011 | 5.42 | 1 / 5 |
| 2021 histdata | 13 | 30.77 | -0.15 | 0.98 | -0.011 | 5.42 | 1 / 5 |
| 2021 mt5_icmarkets_utc | 16 | 31.25 | +0.31 | 1.03 | 0.019 | 5.42 | 1 / 5 |
| 2022 dukascopy | 25 | 16.00 | -12.41 | 0.44 | -0.496 | 16.21 | 1 / 13 |
| 2022 histdata | 25 | 16.00 | -12.41 | 0.44 | -0.496 | 16.21 | 1 / 13 |
| 2022 mt5_icmarkets_utc | 23 | 30.43 | +0.39 | 1.02 | 0.017 | 7.28 | 2 / 7 |
| 2023 dukascopy | 20 | 35.00 | +3.21 | 1.23 | 0.161 | 4.21 | 3 / 4 |
| 2023 histdata | 13 | 30.77 | +0.08 | 1.01 | 0.006 | 3.22 | 1 / 3 |
| 2023 mt5_icmarkets_utc | 20 | 25.00 | -3.82 | 0.76 | -0.191 | 8.60 | 2 / 8 |
| 2024 dukascopy | 27 | 33.33 | +2.77 | 1.14 | 0.103 | 7.44 | 2 / 7 |
| 2024 histdata | 27 | 33.33 | +2.77 | 1.14 | 0.103 | 7.44 | 2 / 7 |
| 2024 mt5_icmarkets_utc | 29 | 31.03 | +0.22 | 1.01 | 0.008 | 5.09 | 2 / 4 |
| 2025 dukascopy | 24 | 54.17 | +19.69 | 2.66 | 0.820 | 3.21 | 3 / 3 |
| 2025 histdata | 24 | 54.17 | +19.69 | 2.66 | 0.820 | 3.21 | 3 / 3 |
| 2025 mt5_icmarkets_utc | 24 | 41.67 | +9.28 | 1.62 | 0.387 | 4.35 | 4 / 4 |
| 2026 dukascopy | 5 | 20.00 | -13.66 | 0.15 | -2.733 | 13.66 | 1 / 2 |
| 2026 histdata | 5 | 20.00 | -13.66 | 0.15 | -2.733 | 13.66 | 1 / 2 |
| 2026 mt5_icmarkets_utc | 10 | 30.00 | +0.63 | 1.10 | 0.063 | 3.35 | 1 / 4 |

2026 contains only data through July 14.

## Gap losses

Stops are filled at the next available opening price when the market gaps through them. A 0.5% planned stop risk does not cap the realized loss at 0.5%. The worst observed trade on each source follows; these losses are included in every applicable table.

| Source | Symbol | Entry time | Close time | Net R |
|---|---|---|---|---:|
| dukascopy | AUDUSD | 2026-04-10 21:00:00 | 2026-04-12 21:05:00 | -11.71 |
| histdata | AUDUSD | 2026-04-10 21:00:00 | 2026-04-12 21:05:00 | -11.71 |
| mt5_icmarkets_utc | USDJPY | 2020-02-21 19:55:00 | 2020-02-23 22:05:00 | -3.13 |

## Data comparability

HistData provenance was verified by the loader before replay. It must not be described as an independent price feed. The common M5 bars below are compared at matching UTC timestamps, rounded to eight decimals. Broker H4 candles follow broker session boundaries after UTC conversion; proxy H4 candles use UTC buckets. A broker/proxy performance difference therefore mixes candle construction, prices, and coverage. This review does not isolate those causes.

| Symbol | Common M5 bars | Identical OHLC % | Only Dukascopy | Only HistData |
|---|---:|---:|---:|---:|
| USDJPY | 478014 | 99.97 | 10777 | 24 |
| EURAUD | 477283 | 99.98 | 10809 | 24 |
| CADJPY | 478052 | 99.98 | 10598 | 24 |
| USDCAD | 477996 | 99.98 | 10562 | 24 |
| AUDUSD | 477971 | 99.98 | 10707 | 24 |
| EURUSD | 478274 | 99.98 | 10524 | 4 |
| GBPCAD | 476458 | 99.98 | 10768 | 36 |
| GBPUSD | 477923 | 99.98 | 10738 | 24 |

## Tracking observations

Counts include warmup. Reactivation counts include repeated invalidation of the same origin; they are not counts of trades or proof that every reactivation should be forbidden. The explicit origin-breach reproduction establishes the invalid-candidate defect separately.

| Source | Expired-origin reactivations | Proposals from expired origins | Closes updating a different current origin | Proposals while occupied |
|---|---:|---:|---:|---:|
| dukascopy | 15035 | 279 | 13 | 0 |
| histdata | 14905 | 275 | 13 | 0 |
| mt5_icmarkets_utc | 7268 | 115 | 8 | 1 |

An example is Dukascopy USDJPY ticket 59, closed July 30, 2024. The accepted order came from a July 24 SELL origin, but its loss reset M15 state for the newer July 26 BUY origin.

Full-run simulated order accounting, including the partial 2026 period. Broker totals cover five symbols with shorter USDCAD coverage.

| Source | Accepted | Cancelled | Closed | Still filled | Still pending | Filled % |
|---|---:|---:|---:|---:|---:|---:|
| dukascopy | 640 | 377 | 262 | 0 | 1 | 40.9 |
| histdata | 620 | 372 | 247 | 0 | 1 | 39.8 |
| mt5_icmarkets_utc | 340 | 188 | 152 | 0 | 0 | 44.7 |

## Copied DEMO evidence

The export contains 11 closed IMS trades on the current eight symbols, 3 winners, net P/L $-401.82, money profit factor 0.65, closed-P/L drawdown $1061.81, and a 5-loss maximum streak. Two additional gold trades lost $286.46; gold is already excluded. No closed GBPUSD trade appears in this export.

These are mixed old versions and sizing, from April through September 2026, before the confirmed September 18 restart. They are not forward validation of the reviewed current code. Reported R is not normalized here because original risk and fills are not consistently reconstructable from this export; broker money includes commission and swap.

The partial journal has 24 distinct placed tickets, 21 cancellation rows, 12 close rows, six risk rejections, and three portfolio rejections. Ten of the 24 placed tickets match closed positions in the export. That is a 41.7% lower bound on fills within this placed cohort, not a complete fill-rate estimate. Cancellation and close records cannot be treated as mutually exclusive without ticket reconciliation. The three portfolio rejections match the eight-open-trade cap in copied logs on June 19, 22, and 23. No daily-loss-limit line was found in the copied trading logs. The sample is too small to establish correlated USD loss behavior. Shared USD exposure and cross-strategy capacity still matter and are not represented by independent-symbol R totals.

## Recommended next work

1. Give each H4 setup and each submission attempt a stable identity. Validate a candidate against all candles since its origin. Separate invalidation memory from the policy on legitimately recovered ranges.
2. Track proposals, accepted pending orders, fills, confirmed cancellations, and closes separately. Keep the accepted setup attached to its ticket across restarts; an old close must not alter a new setup. Retain the existing engine protection against cancelling filled positions.
3. Rerun the unchanged parameters after those corrections, then compare entry-hours versus all-hours target cancellation and any fresh-break requirement one at a time. Do not select replacements from these diagnostic results.
4. Collect the three missing broker M5 series, then validate all eight symbols on common periods. Use a new chronological walk-forward comparison and a shared-account replay before changing DEMO settings.

On the MT5 Windows host, run:

```bat
cd /d C:\fxbot
python fetch_data_mt5_icmarkets.py --symbols EURAUD CADJPY GBPCAD --timeframes M5 --start 2016-01-01 --end 2026-07-15
```

Copy the resulting CSV files and any companion metadata into this repository's `data/historical/mt5_icmarkets_utc/` directory. Keep the actual available dates if the broker only supplies recent history. USDCAD already starts in 2025; do not invent earlier broker data. No redownload of verified HistData is required.

No strategy was removed, promoted, or changed on the trading host by this review.
