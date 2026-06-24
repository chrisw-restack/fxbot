# Live/Demo Audit

## Active Demo Suite Snapshot - 2026-06-03

Source: `live_config.py` `create_live_strategy_specs()` on 2026-06-03.

Current configured suite:

- `EmaFibRetracement` on `config.SYMBOLS`: EURUSD, GBPUSD, AUDUSD, NZDUSD, USDJPY, USDCAD, USDCHF.
- `EmaFibRunning` on `config.SYMBOLS`: EURUSD, GBPUSD, AUDUSD, NZDUSD, USDJPY, USDCAD, USDCHF.
- `Engulfing` / `ThreeLineStrikeStrategy` on EURUSD and AUDUSD.
- `IMS_H4_M15` on USDJPY, XAUUSD, EURAUD, CADJPY, USDCAD, AUDUSD, EURUSD, GBPCAD, GBPUSD.
- `IMSRev_H4_M15` on GBPNZD, AUDUSD, US30, USDCHF, XAUUSD, AUDJPY, AUDCAD, USDCAD.
- `Failed2_H4_H1_M5_market` on USTEC.
- `NYIndexOpeningDrive` on USTEC.
- `CandleConfirmation_USDJPY_H1_M5` on USDJPY.
- `CandleConfirmation_GBPUSD_H1_M5` on GBPUSD.

`live_risk_pct_overrides()` currently returns `{'NYIndexOpeningDrive': 0.0025}`. All other live/demo strategies use the global `config.RISK_PCT` setting.

Use `live_config.py` as the executable source of truth; update this audit when live/demo membership, symbols, risk, or promotion status changes.

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
