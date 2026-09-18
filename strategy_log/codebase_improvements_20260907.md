# Codebase improvements, 7 September 2026

The approved review corrections are implemented locally. The largest changes address risk enforcement, broker query failures, simulator fills, and research accounting. The synchronous architecture remains in place. `config.py` and `live_config.py` are unchanged, including demo membership, parameters, and risk overrides. No broker connection, order submission, demo deployment, or real-money promotion was performed.

## Risk and broker execution

- Reject missing, nonfinite, or incorrectly positioned stops and targets. Enforce minimum 1:1 reward/risk against the signal and the normalized executable request.
- Size MT5 requests using broker contract calculations in account currency. Round volume down to the broker step. Reject a trade when the smallest allowed volume exceeds its price-to-stop risk budget.
- Refresh market entry prices and reduce volume when needed. Recalculate unlocked targets; reject locked targets that fail minimum reward/risk before submission. Record actual returned fill price, volume, levels, and realized fill reward/risk in the order journal. Report adverse fill reward/risk rather than silently treating it as compliant.
- Treat unavailable positions, pending orders, balance, history, and preflight results as failures. A failed query cannot replace known exposure with an empty snapshot. The existing reconnect path handles these errors.
- Require the configured demo account and hedging mode at connection. The runner also supplies account identity to the executor for balance and order checks.

The budget covers price movement to the requested stop. Commission, slippage, and a gap beyond the stop can make realized losses larger. Pending orders already accepted by the broker cannot be resized at their later fill using these pre-submission checks.

## Daily limits and strategy state

The risk date now advances in UTC and cannot move backwards when a higher-timeframe candle arrives. Replay advances the date before recording closures. Reaching the daily limit blocks new entries while indicators, cooldowns, and cancellation signals continue to update.

The demo runner restores today's bot-owned losing position cash flows from broker history before processing new entries. It includes profit, commission, swap, and fees, groups partial deals by position, and sums only negative groups for the UTC day. This includes opening costs paid today. Profitable positions do not offset other losing positions. The threshold remains the configured percentage of current balance. Replay counts net losses when simulated trades close, so opening-cost timing can differ from the broker's daily history total.

Compatible restarts restore strategy state and completed-bar cursors from an atomic JSON checkpoint at `logs/strategy_state.json`. The checkpoint fingerprint covers account identity, constructor state, configuration, and relevant source files. A changed fingerprint uses normal historical warm-up; malformed matching state stops startup. Startup also refuses insufficient warm-up history.

Recovery fetches every missed completed candle, feeds them in completion order, and applies recovered trade closures at the appropriate candle boundary. Old candles can update state and cancel orders but cannot create stale entries. An in-process retry does not dispatch the same candle to the same strategy twice. Rejected proposals release strategy bookkeeping without clearing an existing accepted portfolio slot.

The checkpoint is not a transaction shared with MT5. A crash between broker submission and local persistence still requires broker/journal reconciliation. A cold start without a compatible checkpoint cannot reconstruct every historical fill-dependent strategy decision from candles alone. Pending cancellation retry intents are not stored in this checkpoint.

## Simulator and research changes

Replay uses one finest available execution timeframe per symbol, with strategies receiving only completed candles on their subscriptions. Submitted orders cannot execute before the signal candle closes. The shared replay method now handles fills, trade callbacks, rejected fills, portfolio accounting, and strategy delivery for the generic sweeps and comparisons that previously duplicated that loop.

- Market trades can hit SL or TP on their entry candle.
- Pending orders distinguish stop and limit behavior from the known quote. Gap fills use the opening quote; normal touches use the order level.
- Existing stops crossed by a gap exit at the worse opening quote. An opening target hit precedes a later stop touch on that same candle.
- SELL exits use the ask trigger price once, removing the second spread charge.
- If OHLC cannot establish event order, the simulator assumes SL first. For an intrabar pending entry, TP requires the close to have reached the target after entry. Intrabar entry timestamps use the candle close because the precise fill time is unknown.
- Trade records expose `initial_risk`, `gross_r`, and `net_r`. The existing `r_multiple` field now means net R after configured commission. Win/loss classification also uses net P/L.
- USD FX conversion uses known historical quotes where available, including historical USDJPY conversion. Crosses without a conversion stream retain the configured pip-value fallback. CFD contract values remain configured assumptions.
- Ending open exposure stays open and is reported separately. Equity includes open P/L and estimated commission; maximum equity drawdown samples execution-candle closes.

The finest execution stream must cover the evaluation period. Replay does not substitute overlapping coarse candles for missing fine candles. OHLC cannot reproduce intrabar ordering, variable spreads, or all broker slippage. The new equity drawdown is measured at candle closes and can understate intrabar drawdown.

Walk-forward selection uses net R at full precision, handles a profitable no-loss result as infinite profit factor, and excludes failed combinations with an explicit error. Constructor-aware parameter handling passes IMS `rr_ratio` to both strategy and engine. OOS periods receive prior warm-up candles without placing warm-up orders. Training and OOS exclude candles closing beyond their respective end boundaries. Training still starts with fresh strategy state. Worker count defaults to one; optional multiprocessing uses Windows-compatible spawning.

## Data and repeatability

The CSV loader no longer guesses timezone from Sunday candles. The default input contract is UTC. Raw `mt5_icmarkets` folders or explicit `time_basis='icmarkets'` use the existing broker-time conversion. A `<file>.csv.meta.json` sidecar can declare `time_basis` and `session_origin`. UTC-normalized IC Markets daily session candles remain intact. Unknown time-basis values fail. External broker exports placed elsewhere need explicit metadata or the loader argument.

Bar construction uses dataframe tuples instead of row objects. A local 20,000-row construction check fell from about 0.410 seconds to 0.033 seconds. This measures construction only, not full backtest runtime.

Asymmetric news windows now apply the configured hours before and after an event correctly, including CHF and cross-currency mapping. This does not enable a news filter in the demo suite.

`requirements-backtest.lock` captures the tested Python 3.14 environment, including timezone data. A GitHub Actions workflow runs the unit suite on Windows and Ubuntu with that lock. The workflow has been added locally; hosted CI has not run yet.

## Frozen-suite comparison

Baseline engine revision `0709948` and the corrected engine used the same canonical UTC bars, frozen current demo configuration, configured portfolio limits, and a $10,000 starting balance. Evaluation is 1 January through 31 July 2026, with 180 days of prior warm-up. The local Dukascopy input contains 38 source files and 678,664 candles including warm-up. USA100 is a proxy for USTEC. Broker-native IC Markets files are absent from this checkout, so this is an implementation comparison, not renewed broker validation or a parameter search.

Both columns use net R. Baseline net R is reconstructed from its dollar P/L and initial modeled stop risk. Each engine retains its own sizing and fill assumptions, which are part of the changes being measured.

| Metric | Baseline | Corrected |
|---|---:|---:|
| Closed trades | 79 | 126 |
| Win rate | 24.1% | 27.8% |
| Total net R | +17.30 | +10.04 |
| Net profit factor | 1.27 | 1.09 |
| Expectancy per trade | +0.219R | +0.080R |
| Maximum closed-trade drawdown | 17.44R | 24.91R |
| Longest winning streak | 2 | 2 |
| Longest losing streak | 9 | 12 |
| Ending balance | $10,846.89 | $10,158.64 |
| Ending open orders | 1 | 1 |
| Maximum equity drawdown | Not measured | 11.52% |

The corrected ending open order is pending, so ending equity equals balance. Total R is not percentage account growth: strategy risk overrides, changing balance, volume floors, and trade sequencing change the dollar value of each R.

The most consequential inspected difference is an AUDUSD IMS BUY entered at 0.705875 on 10 April with SL 0.70531. The next available reopening quote crossed the stop and produced an exit at 0.69933, about -11.71 net R. The old simulator capped the fill at the stop level. This example demonstrates the model's gap behavior; it does not establish the exact fill IC Markets would have provided. Candle Confirmation also begins trading after the warm-up rejection bookkeeping fix, where the baseline sample produced no trades.

Correcting execution reduced aggregate net R and increased drawdown on this sample. That is a change in measurement, not evidence that the code improved profitability. Existing research tables retain their historical meaning and need fresh runs before comparing them directly with the new simulator.

### Strategy comparison

Each row is that strategy's contribution inside the same portfolio run. DD is maximum closed-trade net-R drawdown; W/L are longest winning and losing streaks.

| Strategy | Version | Trades | Win % | Net R | PF | Expectancy R | DD R | W/L |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| EmaFibRetracement | Before | 12 | 16.7 | +15.15 | 2.42 | +1.263 | 8.49 | 1/8 |
| EmaFibRetracement | After | 22 | 13.6 | +17.34 | 1.80 | +0.788 | 13.00 | 2/11 |
| EmaFibRunning | Before | 4 | 50.0 | +1.15 | 1.56 | +0.287 | 2.06 | 1/2 |
| EmaFibRunning | After | 4 | 50.0 | +1.10 | 1.54 | +0.275 | 2.05 | 1/2 |
| Engulfing | Before | 4 | 25.0 | -0.95 | 0.72 | -0.239 | 3.37 | 1/3 |
| Engulfing | After | 4 | 25.0 | -0.89 | 0.73 | -0.222 | 3.32 | 1/3 |
| IMS H4/M15 | Before | 16 | 31.3 | -0.12 | 0.99 | -0.008 | 6.66 | 2/6 |
| IMS H4/M15 | After | 17 | 29.4 | -9.46 | 0.64 | -0.556 | 17.88 | 2/6 |
| IMS Reversal | Before | 8 | 25.0 | +3.47 | 1.53 | +0.434 | 4.37 | 1/4 |
| IMS Reversal | After | 9 | 22.2 | +2.43 | 1.32 | +0.270 | 4.34 | 2/4 |
| Failed2 | Before | 30 | 20.0 | -0.35 | 0.99 | -0.012 | 6.16 | 1/6 |
| Failed2 | After | 30 | 20.0 | -1.15 | 0.95 | -0.038 | 6.13 | 1/6 |
| NY Index Opening Drive | Before | 5 | 20.0 | -1.05 | 0.74 | -0.209 | 3.01 | 1/3 |
| NY Index Opening Drive | After | 5 | 20.0 | -1.04 | 0.74 | -0.208 | 3.00 | 1/3 |
| Candle Confirmation USDJPY | Before | 0 | N/A | 0.00 | N/A | N/A | 0.00 | 0/0 |
| Candle Confirmation USDJPY | After | 21 | 47.6 | +1.46 | 1.12 | +0.070 | 4.92 | 3/4 |
| Candle Confirmation GBPUSD | Before | 0 | N/A | 0.00 | N/A | N/A | 0.00 | 0/0 |
| Candle Confirmation GBPUSD | After | 14 | 35.7 | +0.24 | 1.03 | +0.017 | 3.12 | 2/3 |

### Direction comparison

| Direction | Version | Trades | Win % | Net R | PF | Expectancy R | DD R | W/L |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| BUY | Before | 45 | 20.0 | -8.61 | 0.77 | -0.191 | 14.91 | 2/11 |
| BUY | After | 80 | 25.0 | -31.29 | 0.59 | -0.391 | 32.64 | 2/11 |
| SELL | Before | 34 | 29.4 | +25.91 | 2.01 | +0.762 | 7.56 | 2/7 |
| SELL | After | 46 | 32.6 | +41.33 | 2.19 | +0.898 | 7.43 | 4/7 |

These direction results combine all pipeline corrections. They do not isolate the SELL spread fix alone.

## Validation and reproduction

All 89 local unit tests pass, including 46 new regression tests. Coverage includes broker failures through a fake MT5 API, normalization and risk budgets, daily resets, gap and entry-candle exits, mixed timeframes, net R, UTC metadata, news windows, IMS construction, fold boundaries, checkpoint round trips for all nine demo strategy instances, missed candles, rejection bookkeeping, and recovery order. No connected MT5 integration test was run.

Run tests with `python -m unittest discover -s tests -v`. Reproduce the comparison with `python compare_engine_revisions.py --baseline-root <exported-0709948-directory>`. Export complete Python packages, including their `__init__.py` files. The comparison runs sequentially and writes source hashes, canonical candles, both trade lists, and metrics under `output/engine_revision_comparison/`.

Long-history walk-forward and broker-native revalidation have not been repeated as part of this code correction. They remain necessary evidence before changing strategy settings or treating earlier rankings as validated by the corrected engine.

Aggregate currency-exposure limits remain a separate research option from the review. No new exposure filter, portfolio risk limit, or data cache was introduced. Profiling and frozen portfolio comparisons should determine whether those additions are justified.
