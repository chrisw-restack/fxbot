# EmaFib Retracement review, 23 September 2026

Update, 25 September: the identified tracking defects are corrected locally. See [the implementation and revalidation report](ema_fib_tracking_20260925.md). This document retains the original findings and results for comparison; the corrected implementation has not been deployed.

The trend-and-retracement idea is coherent, and the entry arithmetic and confirmed-fractal timing work. The implementation does not reliably retain the identity or state of an accepted order. Correct that before optimizing parameters or relying on the old validation figures.

Repaired HistData and Dukascopy both return a profit with the current parameters over 2020 through 2025. The size of the profit differs materially, and both have long losing streaks. HistData supports the direction of the historical result, but does not independently validate the strategy or reproduce its profit closely.

No production logic, parameters, symbols, risk settings, source prices, or deployment were changed in this review. The current executable risk is 0.5% per trade. The previous 0.7% statement in the strategy log was stale.

## Scope and reproducibility

- Reviewed local revision `0a1caec9307d2f80987d61da8a6228807be6a8e2` and the settings returned by `create_live_strategy_specs()`.
- Tested all seven configured pairs: EURUSD, GBPUSD, AUDUSD, NZDUSD, USDJPY, USDCAD, and USDCHF. Gold is excluded.
- Ran 28 fixed-parameter replays, plus an observer control. Each source/pair has a continuous 2020–2025 run and a separate 1 January through 14 July 2026 run. Each starts with 180 calendar days of indicator warm-up. No tuning used the results, and no backtest evaluates the protected period after 14 July.
- Used validated HistData CSVs and their hash-bound provenance sidecars. Ordinary loader validation remained enabled.
- Used H1 and D1 for strategy decisions, and M5 for execution. Bars become available only after closing. Source-specific missing bars remain missing. The normal non-MT5 loader drops Sunday D1 bars for both sources.
- Applied configured spreads of 0.1/0.2/0.2/0.6/0.2/0.3/0.1 pips in the symbol order above, $7 per lot round-trip commission, and 0.5% sizing from a $10,000 starting balance for each symbol. Spread varies by pair, but stays constant through time. Swap and additional slippage are not modeled; stop gaps are modeled.
- These are isolated strategy tests. News blocking, the DEMO daily-loss gate, and competition with other strategies are absent. Aggregate R combines independent symbol trade histories in closing-time order. It is not a pooled account return or percentage drawdown. Profit factor is positive net R divided by absolute negative net R. Simultaneous closes sort by symbol and then ticket for reproducible streaks.
- Every run ended without pending orders or open positions, so the closed-trade figures omit no ending exposure.

The read-only observer records lifecycle discrepancies. An uninstrumented EURUSD 2020–2025 control produced identical trade dictionaries and ending exposure. The existing 133 unit tests pass. Five targeted audit cases confirm expected behavior; three other cases reproduce the unfixed defects below. Passing the existing suite does not cover those defects.

Reproduce from the repository root, using one worker:

```powershell
.venv\Scripts\python.exe research_ema_fib_review.py
.venv\Scripts\python.exe audit_ema_fib_logic.py
.venv\Scripts\python.exe audit_ema_fib_demo_logs.py
.venv\Scripts\python.exe inspect_ema_fib_source_difference.py
```

Results, individual trades, diagnostics, data comparisons, and the input/code hash manifest are in `output/ema_fib_review_20260923/`. The omission experiment in the final command changes only an in-memory replay input and is not a replacement dataset or performance estimate.

## What the strategy actually trades

D1 and H1 EMA 10/20 directions must agree. BUY means the fast EMA is above the slow EMA; SELL means it is below or equal. Price does not have to close above or below both averages. The 0.001 separation threshold applies to H1, not D1. D1 additionally needs a 14-bar simple average true range of at least 50 pips.

H1 swing points use a strict seven-bar fractal. A high or low is known only after three subsequent H1 bars have closed. The audit found no future-bar use in this confirmation. The most recently confirmed high and low are tracked separately, with maximum ages of 100 observed H1 bars. Their chronological order need not describe a single completed impulse. The optional recent-swing-alignment filter remains disabled, as previously validated.

The configured entry is a 78.6% retracement, with the stop at the opposite swing extreme and the target at three times the swing range from its origin. For a BUY swing from 1.10000 to 1.10500, this gives:

| Level | Price |
|---|---:|
| Entry | 1.10107 |
| Stop | 1.10000 |
| Target | 1.11500 |
| Gross reward/risk before execution costs | 13.02 |

SELL calculations mirror BUY correctly. A target setting of `fib_tp=3.0` therefore does **not** mean a 3R trade. This explains the very low win rate and reliance on occasional large winners. The nominal break-even win rate is about 7.13% before costs; costs and gaps raise it. In the Dukascopy run, the average winner made 12.96R and the average loser lost 1.07R.

Although the strategy's minimum swing is 10 pips, the risk manager requires at least a 5-pip stop. At a 78.6% entry, a swing generally needs at least 23.36 pips to meet that requirement. Smaller proposals are correctly rejected and cleared when no order occupies the slot.

The hour filter uses the H1 candle's opening timestamp. Allowed candle labels 09:00 through 19:00 UTC correspond to decisions after approximately 10:00 through 20:00 UTC. Pending orders can fill outside those hours. Indicators and cancellation checks continue during blocked entry hours. Either D1 or H1 disagreement can cancel an untouched pending order, but this is checked on H1 processing, not immediately on a D1 update.

These details are current behavior, not proposed parameter changes. Changing session interpretation or swing pairing would be a separate research variant requiring validation.

## Confirmed implementation defects

### Accepted setup identity can be overwritten

`generate_signal()` saves its swing snapshot before risk, portfolio, or execution accepts the order. Once an H1 range touches the local pending entry, the strategy clears that pending marker and can propose another trade while the first position is still open. That proposal overwrites the original snapshot. The portfolio correctly rejects a duplicate order, but `EventEngine.reject_signal()` deliberately avoids clearing state for an occupied strategy/symbol slot.

At the first position's eventual loss, `notify_loss()` can therefore invalidate the newer swing. The deterministic case creates a trade from 1.10500/1.10000, then a rejected proposal from 1.10800/1.10200. The loss marks the second pair as used. Only one actual order exists throughout.

This happened on real replay data, not only the synthetic case. Over 2020–2025, the observer found 19 incorrectly attributed losses out of 229 losing trades on Dukascopy, and 18 out of 233 on HistData. The April claim that snapshotting fully fixed loss attribution is incomplete.

### An H1 bid touch is not authoritative fill confirmation

The strategy treats `low <= entry <= high` as a fill. Execution uses ask for BUY triggers, stop/limit order semantics, and M5 bars. A BUY can have its bid touch the entry while its ask never reaches it. The deterministic test leaves the actual order pending while the strategy clears its pending entry. The observer found three instances of this general pending-state disagreement in each six-year dataset.

The order can then escape the intended local cancellation checks until later state changes. The code comment saying this heuristic matches the simulator exactly is outdated. Gap fills and fills occurring outside an H1 range also cannot be represented reliably by this rule.

### Closing a trade can leave a phantom pending entry

`notify_loss()` and `notify_win()` clear swing snapshots and placement age, but leave `_pending_entry` and `_pending_direction`. The deterministic case fills and stops a trade on M5 before the next H1 decision. Execution has no remaining order, but the strategy still reports a pending entry.

The observer found this state immediately after 106 of 251 Dukascopy closes and 117 of 258 HistData closes. These counts do not mean that every case skipped a trade: the next H1 may clear the marker. They do establish that the local order state is unreliable and may take the wrong branch before the cooldown or entry checks.

### Restart recovery is incomplete without a usable checkpoint

The runner can restore a valid strategy checkpoint. Without one, historical warm-up clears unsubmitted proposals and the broker reconciliation restores portfolio occupancy. EmaFib has no accepted-order recovery or `sync_order_state` hook to recover an inherited order's original swing and pending state. Consequently, seeing an order in the reconciled portfolio does not prove that EmaFib knows which setup it belongs to. This finding follows from the integration code; this review did not exercise a real terminal restart.

The appropriate fix is to separate an unsubmitted proposal from a broker-accepted order, preserve the originating swing by ticket/setup identity, receive authoritative fill/cancel/close updates, and clear the matching lifecycle state on terminal outcomes. Recovery must work for both valid checkpoints and inherited orders with missing metadata. A simple position-open boolean driven by candle touches would repeat the earlier deadlock problem.

## Fixed-parameter source comparison

R is net of modeled spread and commission. Max DD is drawdown of the combined closed-trade R series. Streaks are consecutive positive/negative net-R outcomes.

| Period | Source | Trades | Win rate | Net R | PF | R/trade | Max DD R | Max wins/losses |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 2020–2025 | Dukascopy | 251 | 8.76% | +39.26 | 1.16 | +0.156 | 65.91 | 2 / 33 |
| 2020–2025 | HistData | 258 | 9.69% | +70.72 | 1.28 | +0.274 | 47.38 | 2 / 30 |
| 2026 through 14 July | Dukascopy | 22 | 13.64% | +17.34 | 1.80 | +0.788 | 13.00 | 2 / 11 |
| 2026 through 14 July | HistData | 21 | 9.52% | +4.37 | 1.20 | +0.208 | 13.00 | 1 / 11 |

The six-year runs have only 22 and 25 winners. HistData makes 80% more net R despite similar trade counts. The recent-period difference is almost entirely one 12.96R AUDUSD winner. These are profitable but fragile results, not close numerical agreement.

Per-symbol six-year results:

| Pair | Source | Trades | Win rate | Net R | PF | R/trade | Max DD R | Max wins/losses |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| EURUSD | Dukascopy | 25 | 12.00% | +15.39 | 1.65 | +0.615 | 20.31 | 2 / 19 |
| EURUSD | HistData | 29 | 13.79% | +26.41 | 2.04 | +0.911 | 17.02 | 2 / 16 |
| GBPUSD | Dukascopy | 30 | 3.33% | -18.02 | 0.42 | -0.601 | 21.53 | 1 / 20 |
| GBPUSD | HistData | 32 | 3.13% | -20.24 | 0.39 | -0.632 | 23.74 | 1 / 22 |
| AUDUSD | Dukascopy | 53 | 9.43% | +13.41 | 1.26 | +0.253 | 16.33 | 1 / 16 |
| AUDUSD | HistData | 51 | 9.80% | +14.56 | 1.29 | +0.285 | 17.54 | 1 / 17 |
| NZDUSD | Dukascopy | 55 | 9.09% | +11.37 | 1.21 | +0.207 | 23.11 | 2 / 17 |
| NZDUSD | HistData | 55 | 12.73% | +37.81 | 1.72 | +0.687 | 16.43 | 2 / 16 |
| USDJPY | Dukascopy | 33 | 12.12% | +20.74 | 1.66 | +0.628 | 25.01 | 2 / 23 |
| USDJPY | HistData | 33 | 12.12% | +21.40 | 1.70 | +0.648 | 25.40 | 2 / 24 |
| USDCAD | Dukascopy | 27 | 3.70% | -15.52 | 0.46 | -0.575 | 21.19 | 1 / 19 |
| USDCAD | HistData | 27 | 3.70% | -15.92 | 0.45 | -0.590 | 21.58 | 1 / 19 |
| USDCHF | Dukascopy | 28 | 10.71% | +11.89 | 1.44 | +0.425 | 13.83 | 1 / 13 |
| USDCHF | HistData | 31 | 9.68% | +6.70 | 1.21 | +0.216 | 14.55 | 1 / 13 |

GBPUSD and USDCAD lose money on both sources. That warrants a future exclusion test after the tracking correction, not immediate symbol selection from this table. NZDUSD accounts for most of the six-year source difference.

Yearly net R from the continuous six-year replays:

| Close year | Dukascopy | HistData |
|---|---:|---:|
| 2020 | +41.84 | +42.92 |
| 2021 | -15.20 | -15.36 |
| 2022 | -3.61 | -3.61 |
| 2023 | -19.94 | -1.25 |
| 2024 | +11.62 | +23.47 |
| 2025 | +24.54 | +24.54 |

Three consecutive losing calendar years appear on both sources. These rows are a breakdown by closing year, not separate walk-forward folds. This is a descriptive rerun, not new out-of-sample validation, because these historical periods have already been used in strategy development. The older +250.5R figure covered a different period, included gold, and used an earlier simulator; it is not an apples-to-apples baseline for this review.

## Why nearly identical prices can give different trades

Across the seven pairs, 99.975% to 99.983% of common M5 timestamps have identical OHLC after rounding to eight decimals. HistData lacks roughly 10,500 to 10,800 M5 candles per pair that exist in Dukascopy over the comparison window. H1 availability and some D1 aggregates also differ. Verified provenance establishes source identity and clock handling; it does not establish completeness or price-feed independence.

One concrete example explains the recent-period difference. HistData contains AUDUSD H1 at 2026-03-23 19:00 UTC, while the Dukascopy H1 file omits it even though its M5 data exists. The extra EMA update leaves HistData just above the 0.001 H1 separation threshold at the next day's 09:00 candle; Dukascopy is just below it.

- HistData submits a SELL at 0.70391592 after the 09:00 candle. It never fills, occupies the strategy slot, and cancels after the 22:00 candle when H1 bias flips.
- Dukascopy waits until the 12:00 candle and submits a SELL at 0.70018242 using a newer swing. It fills at 20:25 UTC and closes on 30 March for +12.96R.
- A diagnostic HistData replay omitting only that one H1 candle reproduces the later entry and the same four first-quarter trades' aggregate +8.48R, versus -4.48R on unmodified HistData. This isolates a material source-coverage effect without changing the actual dataset.

The correct response is to audit higher-timeframe completeness and rerun after fixing order tracking. Deleting the candle to improve results would be data selection. Similarity to Dukascopy also means HistData should not be presented as independent market-feed confirmation.

## What the copied DEMO evidence establishes

The MT5 history export generated on 18 September at 11:20 contains 27 closed positions with EmaFib's full or historical truncated strategy comment. They opened from 20 March onward; the latest EmaFib close is 20 August. Three won and 24 lost. Combined realized profit after commission and swap is **-$1,074.54**, with money-based profit factor **0.66**.

This is actual DEMO evidence, but spans different code, configuration, risk, and operating conditions. It is not directly comparable to the isolated fixed-parameter R series. The copied journal contains only four EmaFib CLOSE rows, despite 24 ORDER_PLACED rows and 27 EmaFib closed positions in the broader broker report, so it is insufficient for a complete broker-to-strategy reconciliation. Of its 16 rejected proposals, 15 were risk-manager rejections and one was a portfolio rejection.

The export and copied logs predate the confirmed 18 September 09:55 UTC restart. The startup excerpt confirms connection, warm-up, and reconciliation of two orders/positions; it does not prove successful subsequent EmaFib trading. Current-server operation requires a fresh journal, trading log, and MT5 history export covering orders submitted after that restart, plus the server revision and process start time. No terminal access was attempted here.

## Recommended sequence

1. Correct accepted-order identity, pending/open/closed state, and restart recovery. Keep the current numeric parameters fixed and add regression tests for the three reproduced defects.
2. Audit and document missing H1/D1 coverage, then repeat the same source comparison and a broker-data replay. Include wider spread and swap sensitivity because some winners remain open for days; the longest holding period here is nearly 17 days.
3. Run fresh walk-forward validation on the corrected implementation before selecting parameters or dropping GBPUSD/USDCAD. The old MODERATE label is historical evidence, not validation of a corrected future implementation.
4. Reconcile fresh DEMO outcomes against that implementation before considering any promotion or increase in risk.

The strategy remains a plausible research candidate. The current code and evidence do not justify calling it fully reliable or increasing exposure.
