# Live/Demo Audit

This file audits the IC Markets demo account. No entry in this file authorizes real-money trading. Older dated sections may use `live` to refer to the MT5 runner or `live_config.py`; current deployment status is DEMO.

## Failed2 parameter study, 2026-09-29

The user requested parameter comparisons after the tracking corrections.
Completed 128 sequential replays across 19 configurations with 16 exact baseline
controls. The search ranks by training total R with predeclared trade-count,
profit-factor, and drawdown limits. Three alternatives passed to later-period
evaluation alongside current settings.

Keep the current configuration. Extending the session to 17:00 weakens later
broker performance substantially. Lookbacks of 40 or 90 days offer no convincing
overall improvement. Rolling selection also underperforms unchanged parameters
on the combined independent Dukascopy test folds. No DEMO parameter, risk,
membership, production-code, or host change occurred. See the
[parameter report](failed2_parameters_20260928.md) for evidence and limitations.

## Failed2 market corrections, 2026-09-28

The user authorized the review recommendations. Failed2 market proposals now
carry setup/attempt identities. Only accepted submissions consume a setup;
rejections while another position is open do not. The existing setup ledger
restores consumed identities from attributed open orders and closed trades.
Old orders without identity remain unattributed. Preserve logs/setup_ledger.json.

Cold startup now uses strategy-specific history requirements. Current Failed2
settings request 250 completed USTEC D1 bars, covering the 61-bar range minimum
and allowing EMA initialization error to decay. Missing required history stops
startup; the strategy also blocks entries with incomplete daily range history.
Changed code invalidates the previous checkpoint and starts a fresh warm-up.

Corrected 2020 through 2025 results are +103.00R Dukascopy, +99.68R HistData,
and +53.29R broker data. The last broker historical test remains +17.28R with
71.6% expectancy retention. Latest long-history retention remains WEAK, although
those test periods are profitable. All 186 unit tests pass. Parameters were not
optimized; fresh corrected DEMO evidence is still needed.

Numeric parameters, USTEC membership, and 0.5% risk remain unchanged. EmaFibRunning
remains removed from new runs. No code was deployed or MT5 account accessed here.
See the [correction report](failed2_corrections_20260928.md) for validation.

## Failed2 market review before corrections, 2026-09-28

Failed2 remains configured for DEMO on USTEC with unchanged logic, parameters,
and global 0.5% risk. Current 2020–2025 replays earn +105.00R Dukascopy,
+101.68R verified HistData, and +53.29R broker data. The last 2024–2025 broker
test earns +17.28R with STRONG retention; the same long-history tests remain
profitable but have WEAK retention. The evidence supports correction and further
validation rather than retirement or parameter promotion.

The 50-D1-bar startup history is insufficient for the 60-prior-day range filter.
An isolated reconstruction of the actual 14 July restart reproduces its logged
15:05 entry with 50 bars and blocks it with 61. Proposed/accepted setup tracking
and cold-restart recovery also need correction. These issues were audited, not
changed. The copied DEMO export shows eight trades and -$778.31 net, including a
weekend gap loss exceeding its reported stop risk. See the
[full review](failed2_review_20260928.md). No host deployment occurred.

## EmaFib Running removed from new DEMO runs, 2026-09-28

The user explicitly requested removal. `live_config.py` no longer constructs or
registers EmaFibRunning. Its corrected strategy code, backtest registration,
historical research settings, and magic number 1002 remain available.

The trading host must be updated and its old bot stopped before starting the new
version. Removal prevents new strategy signals; it does not cancel orders already
held by MT5. Cancel any remaining EmaFibRunning pending orders on the host. Filled
positions retain their broker SL/TP and remain identifiable for reconciliation.
Preserve `logs/setup_ledger.json`. No host deployment or MT5 interaction occurred here.

## EmaFib Running corrected locally, latest validation fails, 2026-09-25

The user authorized the Running review recommendations. Local code now tracks
accepted orders by setup/attempt, recovers their original anchors through the
setup ledger, handles partial-fill cancellation races, and initializes running
extremes from all known closes since the anchor. All 172 tests pass.

Research completed 204 sequential replays, two original-code controls, and six
final-code broker controls. Corrected six-pair 2020 through 2025 returns are
+27.03R Dukascopy, +35.40R HistData, and +13.26R broker. Broker PF is 1.13,
closed-trade drawdown 22.73R, and the maximum losing streak is 22. The latest
2024 through 2025 broker test loses 15.10R with PF 0.59; that test fails on all
three sources. Earlier long-history tests are mixed. The historical STRONG
label no longer describes current validation.

Pausing new Running entries in the default DEMO suite is recommended, but no
membership, numeric parameter, symbol, or risk change has been made. There was
no deployment or restart on the trading host. Preserve `logs/setup_ledger.json`
for eventual recovery; old orders without origin metadata cannot acquire a
reliable historical anchor. See the
[full correction report](ema_fib_running_corrections_20260925.md).

## EmaFib Running initial review, before corrections, 2026-09-25

The user requested the same logic/performance analysis for EmaFibRunning.
Sixty-four sequential replays and two observer controls are complete, using
current numeric settings. Six matched pairs over 2020 through 2025 return
+33.59R Dukascopy, +42.41R HistData, and +17.31R broker data. Broker PF is 1.17,
max closed-trade drawdown 24.10R, and the longest losing streak is 23. The broker
2024 through 2025 slice loses 14.04R.

These are current-code results, not corrected results. Reproduced defects include
bid-touch fill inference, overwritten accepted anchors, stale pending state after
close, premature state clearing on cancellation, missing cold-recovery attribution,
and omitted known closes when initializing the running extreme. The old STRONG
label is historical. Correct and compare these changes before tuning parameters
or deciding retirement. Running remains in the default DEMO suite unchanged.

The copied DEMO export contains two wins totaling $1,300.76 net. Of that,
$1,205.46 came from EURUSD ticket 1689274839, whose 7 June cancellation failed
with retcode 10018 while the old engine incorrectly logged success. It later
filled and won. This predates the September execution fixes and does not validate
the intended strategy. See the [full Running review](ema_fib_running_review_20260925.md).

## EmaFib Retracement removed from new DEMO runs, 2026-09-25

The user explicitly requested removal from new bot runs. `live_config.py` no longer
constructs or registers EmaFibRetracement. Its strategy code, backtest registration,
research settings, and magic number 1001 are retained. EmaFibRunning remains active.
The decision follows the corrected six-pair broker result of -20.82R and 84.05R
closed-trade drawdown. This supersedes the earlier unchanged-membership notes below.

The local configuration change requires updating and restarting the trading-host
bot before it takes effect. Deployment is not yet confirmed. Existing broker
pending orders are not cancelled by removing the strategy; cancel any remaining
EmaFibRetracement pending orders separately on the host. Filled positions retain
their broker SL/TP and remain identifiable for reconciliation. Stop the old bot
before starting the updated instance, and preserve the setup ledger.

## EmaFib accepted-order tracking prepared locally, 2026-09-25

The user authorized the EmaFib review recommendations. Local corrections separate
unsubmitted proposals from accepted orders, preserve their original swing through
the existing setup ledger, and use execution-confirmed pending/open/closed state.
Recovery supports valid checkpoints and ledger-attributed orders. Legacy orders
without setup metadata remain tracked but their origin is not inferred.

Numeric parameters, seven-pair membership, and global 0.5% risk are unchanged.
This is not a deployment or a promotion decision. The last confirmed server
revision remains `4cdc9eb`, as recorded below. See the
[correction and validation report](ema_fib_tracking_20260925.md) for test results,
fixed-parameter source comparisons, rolling validation, and remaining broker-data
requirements. Preserve `logs/setup_ledger.json` during any eventual update.

All 150 tests pass. The 134 corrected historical replays show a weak,
cost-sensitive baseline: +20.98R Dukascopy and +51.34R HistData over 2020 through
2025, falling to -25.21R and +4.27R with a 1-pip spread. Both sources have a WEAK
first rolling test and a losing second test. These are independent pair R sums,
not account returns. The old MODERATE label does not validate this corrected
implementation. No new parameters or symbol exclusions are approved by this study.

The three additional broker M5 exports are now present. NZDUSD and USDCHF extend
the long-history comparison to six matched pairs. USDCAD M5/H1/D1 begin in January
2025, so only shorter comparisons are supported for that pair. See the
[broker-history extension](ema_fib_broker_completion_20260925.md). This data update
does not change DEMO settings or deployment status.

The repeated USDCAD export again starts at 2025-01-01 22:00 UTC on M5, H1, and
D1. Accept that as the current setup's available history limit and stop requesting
further downloads. The completed long-history comparison remains six matched
pairs, with USDCAD excluded from all sources.

The extended six-pair broker result is -20.82R over 2020 through 2025, PF 0.91,
with 84.05R closed-trade drawdown. The same pairs return +36.50R on Dukascopy and
+67.26R on HistData. This source discrepancy remains unresolved. The seven-pair
broker result for January through 14 July 2026 is +1.78R from 23 trades.

## IMS Reversal setup tracking prepared locally - 2026-09-21

The user authorized correcting setup tracking and testing the alternative
cancellation rules. The local implementation now links signals, orders, and
final outcomes to an originating setup, with an account-bound recovery ledger.
All 114 unit tests pass. Thirty broker comparisons plus four final verification
replays excluded the protected period after 14 July 2026.

Corrected entry-hours cancellation returned +37.52R over 2020-2025 versus
+32.54R for the original code and +27.28R with all-hours cancellation. Original
and moving target references gave identical trade paths. Defaults remain
entry-hours cancellation and a moving target reference; numeric parameters,
EURUSD-only membership, and risk have not changed.

This work is not deployed and does not replace the frozen DEMO trial or authorize
real-money trading. The last confirmed server revision is still `4cdc9eb` below.
Before any eventual rollout, review inherited IMS pending orders because older
orders lack setup IDs. See [the full report](ims_setup_tracking_20260919.md).

## Infrastructure corrections deployed to DEMO - 2026-09-18

The user committed and pushed the September corrections, pulled commit
`4cdc9eb7bc0bcd758d04af9e83f035faaa9bce09` on the Windows MT5 host, installed
`requirements.txt`, and restarted the demo runner. All 89 unit tests passed on
the host under Python 3.13. The tests' simulated failure logs were expected;
the final unittest result was `OK`.

User-supplied startup output confirms connection to `ICMarketsSC-Demo`, account
`52775013`, at 11:55:18 host time. Warm-up completed at 11:55:21 with 4,950 bars
across 38 symbol/timeframe pairs. The runner reconciled two existing broker
positions/orders, reported `Demo trading started`, and processed new completed
bars at 11:55:23. No startup warnings or errors appear in the supplied excerpt.
The excerpt does not distinguish pending orders from filled positions or give
their ticket IDs. No new order submission or close is demonstrated yet.

Use approximately 2026-09-18 09:55 UTC as the deployment boundary, based on the
host's UTC+2 log time and the 09:50 UTC M5 candles completing at startup. Assess
orders submitted after the restart separately from the two inherited broker
positions/orders. Existing pending orders retain their submitted volume and
levels; a later fill alone does not make them orders sized by the corrected code.

Demo membership, parameters, and configured risk are unchanged. The startup
registrations confirm eight IMS symbols excluding XAUUSD and EURUSD-only IMS
Reversal. This is a demo deployment, with no real-money promotion. The prior
September entry describes implementation before this deployment. Successful
startup and unit tests do not establish improved trading performance.

## Infrastructure corrections - 2026-09-07

The approved code review corrections have been implemented locally. Demo membership, strategy parameters, and risk configuration are unchanged; no deployment or real-money promotion occurred. The simulator now accounts for entry-candle exits, adverse stop gaps, corrected SELL spread handling, and net R. Historical results below were produced with the earlier engine and require fresh runs before direct comparison. The local Dukascopy comparison and implementation details are in [Codebase improvements](codebase_improvements_20260907.md). Broker-native data is absent from this checkout, so that comparison does not replace the broker validation decisions below.

## IMS XAUUSD Broker Revalidation - 2026-08-31

Frozen current IMS parameters were replayed on XAUUSD using IC Markets, Dukascopy, and HistData bars. The broker-native IC Markets result is a decisive fail: 56 trades, 12.5% wins, -33.66 net R, -0.601R expectancy, PF 0.34, and 33.66R max drawdown. Every non-overlapping IC Markets period from 2016 onward is negative, including -11.72R over 15 trades from 2024 and -7.05R over seven trades from 2025-04-01. The strategy lost -32.29R before commission, so costs are not the cause.

Dukascopy is flat at +0.58R over 70 trades and HistData is negative at -3.67R over 67 trades. Deeper 61.8% and 78.6% entries reduced IC Markets trade count but stayed negative; the recent variants had no wins. Disabling LTF-origin expiry produced no change.

The portfolio-aware IC Markets replay from 2025-04-01 improves from +69.67R, PF 1.31, and 16.84R max drawdown with XAUUSD to +76.73R, PF 1.36, and 15.37R max drawdown without it. All 306 non-XAUUSD trades are unchanged; the removed trades are seven XAUUSD losses totaling -7.05R.

Decision: XAUUSD fails broker revalidation. The user approved its removal from the IMS demo scope on 2026-08-31, and `live_config.py` now contains the eight remaining IMS symbols. Keep their parameters frozen and do not tune a gold-specific rescue on this sample. Artifacts are under `output/ims_xauusd_revalidation_20260831/`, with the detailed conclusion in `strategy_log/ims.md`.

Deployment note: sync this change to the Windows demo PC and restart `main_live.py`. The copied journal through 2026-08-28 shows the latest XAUUSD IMS order closed on 2026-08-26, with no later XAUUSD IMS order recorded. Check MT5 before restarting because the remote account may have newer activity. Cancel any active XAUUSD pending order with IMS magic `1004`; removing the symbol stops new signals and future strategy cancellation signals. Leave any filled position protected by its broker SL and TP to close normally.

## IC Markets Current-Suite Replay - 2026-08-12

Imported a fresh UTC-normalized IC Markets export for the current demo suite: 40 CSV files and
6,346,863 bars. Structural validation found no duplicate timestamps, out-of-order rows, missing OHLC,
invalid candles, or negative volume. Most history begins in January 2016; CADJPY M15/H4 and USDCAD
M15/H1/H4/D1 are limited to 2025 onward by broker availability.

The audit corrected the D1 loader so genuine IC Markets Monday sessions, stamped Sunday evening after
UTC normalization, are retained. All 42 repository unit tests pass after the change.

Frozen current-strategy standalone replay results, net of configured commission:

| Strategy | Trades | Net R | Net expectancy | Net PF | Max DD R |
|---|---:|---:|---:|---:|---:|
| EmaFibRetracement | 301 | +134.26 | +0.446 | 1.46 | 34.43 |
| EmaFibRunning | 196 | +52.64 | +0.269 | 1.36 | 23.26 |
| Engulfing | 35 | -6.49 | -0.186 | 0.77 | 19.48 |
| IMS H4/M15 | 367 | +9.32 | +0.025 | 1.03 | 27.24 |
| IMS Reversal EURUSD | 187 | +26.74 | +0.143 | 1.18 | 22.40 |
| Failed2 USTEC | 247 | +77.73 | +0.315 | 1.43 | 13.24 |
| NY Index Opening Drive | 68 | +49.85 | +0.733 | 2.31 | 4.00 |
| Candle Confirmation USDJPY | 672 | +0.05 | +0.000 | 1.00 | 30.59 |
| Candle Confirmation GBPUSD | 432 | +14.96 | +0.035 | 1.05 | 22.25 |

IMS XAUUSD is the clearest broker-specific failure: 56 trades, -33.66 net R, negative in every tested
period. IMS excluding XAUUSD produces +42.98 net R over 311 trades (+0.138R expectancy). Candle
Confirmation's raw price edge is almost entirely consumed by commission, and Engulfing reverses from
positive proxy validation to negative on IC Markets.

The portfolio-aware current suite remains positive from 2025-04-01 (+69.67 net R over 313 trades,
PF 1.31, max DD 16.84R), driven mainly by EmaFibRetracement, Failed2, and NY Index Opening Drive.
The untouched current-config period from 2026-07-16 is nine straight modeled losses (-9.62 net R).
The MT5 report independently shows nine actual trades and nine losses after the reset; eight trades
match the replay by strategy, symbol, direction, and approximate time. This supports intended-logic
execution and a genuinely adverse IC Markets sequence rather than a different-code diagnosis.

The MT5 report's 70 closed positions total approximately -$2,500 net. The old eight-symbol IMS
Reversal deployment accounts for -$2,014, so it remains the dominant realized loss source. Current
OHLC replay does not model dynamic spread or slippage; actual EURAUD IMS and EURUSD IMS Reversal losses
show that these can materially worsen individual fills/stops.

Decision: no automatic `live_config.py` change. Keep this account demo-only. Discuss pausing Engulfing
and both Candle Confirmation variants; broker-revalidate IMS with XAUUSD removed as the first isolated
change; keep the EURUSD-only IMS Reversal forward trial frozen and unpromoted. Full report and replay
artifacts are under `output/icmarkets_replay_report.md` and `output/icmarkets_replay_*`.

## Active demo suite snapshot, verified 2026-08-31

Source: `live_config.py` `create_live_strategy_specs()`. Membership has not changed since the EURUSD-only IMS Reversal update on 2026-07-15.

Current configured suite:

- `EmaFibRetracement` on `config.SYMBOLS`: EURUSD, GBPUSD, AUDUSD, NZDUSD, USDJPY, USDCAD, USDCHF.
- `EmaFibRunning` on `config.SYMBOLS`: EURUSD, GBPUSD, AUDUSD, NZDUSD, USDJPY, USDCAD, USDCHF.
- `Engulfing` / `ThreeLineStrikeStrategy` on EURUSD and AUDUSD.
- `IMS_H4_M15` on USDJPY, EURAUD, CADJPY, USDCAD, AUDUSD, EURUSD, GBPCAD, GBPUSD.
- `IMSRev_H4_M15` on EURUSD only (forward-demo research trial from 2026-07-15).
- `Failed2_H4_H1_M5_market` on USTEC.
- `NYIndexOpeningDrive` on USTEC.
- `CandleConfirmation_USDJPY_H1_M5` on USDJPY.
- `CandleConfirmation_GBPUSD_H1_M5` on GBPUSD.

`live_risk_pct_overrides()` currently returns `{'NYIndexOpeningDrive': 0.0025}`. All other demo strategies use the global `config.RISK_PCT` setting.

Use `live_config.py` as the executable source of truth. Update this audit when demo membership, symbols, risk, or promotion status changes.

## IMS Reversal EURUSD Forward Trial - 2026-07-15

Decision:

- Removed GBPNZD, AUDUSD, US30, USDCHF, XAUUSD, AUDJPY, AUDCAD, and USDCAD from the configured IMS Reversal demo scope.
- Retained `IMSRev_H4_M15` on EURUSD only, with its validated parameters frozen.
- Kept the existing magic number `1005` and global demo risk of `0.5%` per trade.
- Treat IC Markets bars and demo trades after 2026-07-14 as new forward evidence. Do not tune against them during the trial.

Review checkpoints:

- Review after 12 months or 15-20 closed trades as an interim health check only.
- Require at least 30 closed trades before considering promotion; 50 is preferable.
- Compare demo signals, pending fills/cancellations, and realized outcomes against a frozen IC Markets replay before any promotion decision.

One-time restart check:

- Existing filled IMS Reversal trades on removed symbols remain broker-managed by their SL/TP and are still reconciled by magic number.
- Cancel any still-pending `IMSRev_H4_M15` orders on removed symbols before or immediately after restarting `main_live.py`; removed symbols no longer receive strategy cancellation signals.

## Pending Cancellation Retry - 2026-07-16

At 22:00 UTC on 2026-07-15, IMS Reversal invalidated XAUUSD pending ticket `1810114142`.
IC Markets rejected the cancellation with retcode `10018` (`Market closed`) during the daily gold
maintenance window. The bot alerted correctly but did not retain the cancellation intent. The order
remained active and filled at 02:42:56 UTC at `4025.95` with broker SL `4017.41` and TP `4052.28`.

Correction:

- Failed pending cancellations are retained and retried once per minute, up to five total attempts.
- The first Telegram notice says automatic retry is scheduled. A manual-action alert is sent only if all attempts fail.
- Retry uses a pending-only execution operation. It cannot close a position if the order fills between inspection and cancellation.
- If a fill wins the race, the bot reports that the protected position remains open with its broker SL/TP.
- Close callbacks are skipped for symbols removed from a strategy's current subscription, while broker reconciliation, journaling, and close Telegram reporting continue.

The XAUUSD trade was created by the old eight-symbol configuration at VPS commit `bea6018`. It is not
part of the EURUSD-only forward trial and should remain broker-managed to SL/TP.

## NY Index Opening Drive Demo Addition - 2026-06-11

Decision:

- Added `NYIndexOpeningDrive` to the demo runner on `USTEC`.
- Added magic number `1011`.
- Added temporary per-strategy risk override of `0.25%`.
- Reason: NY-time-aware walk-forward passed STRONG on both Dukascopy and HistData, and fixed `body30` sanity check remained positive across all 2020-2026 OOS periods on both sources.

Configured core:

- `09:30-10:00 America/New_York` opening drive.
- `12:00 America/New_York` entry cutoff.
- `min_drive_pips=40`, `min_drive_body_pct=0.30`.
- D1+H1 EMA 20/50 trend alignment.
- D1 prior-range block top 20%.
- 38.2-61.8% pullback, M5 fractal confirmation, `3R` TP.

Monitoring notes:

- Watch overlap with existing `Failed2_H4_H1_M5_market` USTEC exposure.
- Check first several signals for correct NY-open timing after MT5 UTC normalization.
- Review USTEC spread/slippage during the NY opening window before considering any risk increase.

## MT5 Time Normalization - 2026-05-25

Evidence from `logs/trade_journal.csv` and `logs/ReportHistory-52775013.html`
showed that MT5 chart/order timestamps were IC Markets server time, while
`journal_time_utc` was true UTC. In May 2026 the observed offset was +3 hours.

Decision:

- Keep project strategy logic and journals on UTC.
- Convert MT5 bar timestamps from IC Markets server time to UTC in
  `data/mt5_data.py` before strategies see them.
- Write future MT5 history exports to `data/historical/mt5_icmarkets_utc/`.
- Keep the existing `data/historical/mt5_icmarkets/` snapshot as broker-time
  audit evidence; do not merge new UTC-normalized files into it.

Impact:

- Live session filters now run on intended UTC hours instead of broker-server
  hours.
- Future `signal_time_utc` values should be actual UTC.
- Existing journal rows before this change have broker/server candle timestamps
  in `signal_time_utc`, despite the column name.

## Unknown R Multiple Telegram Display - 2026-06-17

Observed Telegram close example:

`USDCAD BUY`, `LOSS`, `PnL: $-89.33`, `R: +0.00`, strategy `IMS_H4_M15`.

Diagnosis:

- The trade result and PnL can be correct while `R` is wrong.
- `R: +0.00` was used as a fallback when live close reconstruction could not calculate initial risk from tracked entry/SL data, or when MT5 supplied `sl=0.0` and the code treated it as a valid huge risk.

Fix:

- Unknown live `r_multiple` is now stored/passed as `None`, not `0.0`.
- Telegram now displays `R: n/a` when R cannot be reconstructed.
- MT5 close reconstruction treats `sl=0.0` as missing and, for broker SL exits with comments like `[sl ...]`, falls back to calculating roughly `-1.00R` from entry to exit price.

Follow-up - 2026-06-24:

- Repeated `R: n/a` alerts showed that converting unknown R to `n/a` exposed, but did not solve, MT5 close-history timing failures.
- Close reconciliation now waits up to 30 seconds for MT5 to publish the exit deal instead of immediately sending a fallback alert.
- Deal history is queried directly by MT5 position ID first, with the broad date-range query retained as a fallback.
- For pending orders that fill and close between polls, the fallback now follows the opening order deal to its MT5 position ID and then includes the linked exit deal.
- If the last in-memory position snapshot has no valid SL, the original SL/TP is recovered from MT5 order history. The broker `[sl ...]` comment remains the final SL fallback.
- Close logs now include the calculated R and its source (`tracked_position`, `order_history`, or `sl_comment`) for VPS diagnosis.

## MT5 Identity And Reconciliation Hardening - 2026-06-24

Review of the June 10-24 forward-demo period found that IC Markets truncates
the 17-character `EmaFibRetracement` order comment to `EmaFibRetracemen`.
Live cancellation and portfolio reconciliation were comparing the broker
comment to the full strategy name, so valid cancellation signals did not find
the existing pending orders. This allowed duplicate EURUSD and GBPUSD pending
orders and left six cancelled-by-strategy orders active at the broker.

Corrections:

- Canonical strategy identity is now resolved from the unique MT5 magic number.
  Broker comments are retained only as diagnostics.
- Duplicate magic numbers are rejected during execution initialization.
- Duplicate `(symbol, strategy)` broker slots trigger critical logs and Telegram
  operational alerts, and every broker ticket counts toward `MAX_OPEN_TRADES`.
- Strategy cancellation removes every matching pending order, verifies that MT5
  no longer reports each ticket, and records `CANCEL_FAILED` instead of a false
  success when broker confirmation fails.
- Execution failures now store MT5 retcode/comment, `last_error`, normalized
  request values, bid/ask, stop/freeze levels, filling mode, and `order_check`
  diagnostics in the journal context. Unsupported filling mode is the only
  automatically retried execution error.
- Missing close history is recorded as `CLOSE_PENDING_RECONCILIATION`. Open
  positions are no longer finalized using cached floating P/L. MT5 deal history
  remains the source of truth for realized P/L, commission, swap, and R.
- Added `cancel_mt5_orders.py`, which is read-only by default and can cancel
  explicitly supplied bot-owned pending tickets with `--execute`.

Cleanup status: COMPLETED on the Windows/VPS terminal and confirmed on 2026-08-31. The six stale
EmaFibRetracement pending orders identified in this review were removed. The
old ticket command has been deleted from this log to prevent accidental reuse.
The open NZDUSD EmaFibRetracement position and CADJPY IMS pending order were
excluded from that cleanup.
