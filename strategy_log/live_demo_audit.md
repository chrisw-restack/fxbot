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
