# Live/Demo Audit

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
