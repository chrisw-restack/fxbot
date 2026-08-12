# Live/Demo Audit

## IC Markets Current-Suite Replay - 2026-08-12

Imported a fresh UTC-normalized IC Markets export for the current live/demo suite: 40 CSV files and
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

## Active Demo Suite Snapshot - 2026-07-15

Source: `live_config.py` `create_live_strategy_specs()` on 2026-07-15.

Current configured suite:

- `EmaFibRetracement` on `config.SYMBOLS`: EURUSD, GBPUSD, AUDUSD, NZDUSD, USDJPY, USDCAD, USDCHF.
- `EmaFibRunning` on `config.SYMBOLS`: EURUSD, GBPUSD, AUDUSD, NZDUSD, USDJPY, USDCAD, USDCHF.
- `Engulfing` / `ThreeLineStrikeStrategy` on EURUSD and AUDUSD.
- `IMS_H4_M15` on USDJPY, XAUUSD, EURAUD, CADJPY, USDCAD, AUDUSD, EURUSD, GBPCAD, GBPUSD.
- `IMSRev_H4_M15` on EURUSD only (forward-demo research trial from 2026-07-15).
- `Failed2_H4_H1_M5_market` on USTEC.
- `NYIndexOpeningDrive` on USTEC.
- `CandleConfirmation_USDJPY_H1_M5` on USDJPY.
- `CandleConfirmation_GBPUSD_H1_M5` on GBPUSD.

`live_risk_pct_overrides()` currently returns `{'NYIndexOpeningDrive': 0.0025}`. All other live/demo strategies use the global `config.RISK_PCT` setting.

Use `live_config.py` as the executable source of truth; update this audit when live/demo membership, symbols, risk, or promotion status changes.

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

- Added `NYIndexOpeningDrive` to the demo/live runner on `USTEC`.
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

One-time broker cleanup required on the Windows/VPS terminal:

`python cancel_mt5_orders.py 1688987862 1688988392 1689159224 1713091357 1713091656 1715439958 --execute`

These six orders had already received EmaFibRetracement cancellation signals.
Do not cancel the open NZDUSD EmaFibRetracement position or CADJPY IMS pending
order as part of this cleanup.
