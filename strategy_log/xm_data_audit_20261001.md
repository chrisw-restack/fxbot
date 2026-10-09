# XM historical data audit, 1 October 2026

Research data only. The IC Markets DEMO strategy suite and risk are unchanged. No MT5 trading calls or strategy performance tests were made.

Audited all 55 source files containing 16,212,221 records across eleven instruments and M5/M15/H1/H4/D1. Prepared 10,957,525 UTC records and retained 5,254,696 excluded records separately with their original server timestamps and exclusion flags. Counts include overlapping timeframes, so they are not counts of independent observations.

Prepared candles are in `output/xm_processed_20261001/history/`. Raw downloads remain unchanged in `output/xm_inspection_20261001_final/history/`. The dataset ends conservatively at July 14, 2026, 21:00 UTC for most streams. No later prices were admitted to parameter research.

## Timing

For the accepted recent windows, XM uses UTC+2 in winter and UTC+3 in summer, following European daylight-saving dates. Each instrument was checked against native UTC Dukascopy prices by month and separately during European/US DST disagreement periods. The weakest accepted monthly return correlation was 0.941. This establishes alignment in measured windows, not independent price-feed provenance or a tick-by-tick timing guarantee.

A recent March 16, 2026 server timestamp of 00:00 converts to March 15 at 22:00 UTC. March 30 at 00:00 converts to March 29 at 21:00 UTC. The US changes clocks earlier in March, so the IC Markets US-DST conversion must not be reused for XM.

The older archive needs different treatment. Fresh official HTTPS Dukascopy chart responses cover an EURUSD reference sample from January 2012 through January 2014. Most verified older windows fit UTC+1 winter and UTC+2 summer, one hour different from the recent XM rule. June 2013 is mixed even within the same month. Daily comparisons identify UTC+3 on June 6, 7, 10, 11, 12, 13, 27, and 28; other tested weekdays align at UTC+2. Those daily correlations are about 0.925 to 0.997. The full older changeover and other instruments have not been established. All pre-2016 candles remain quarantined, including portions of 2012/2013 with useful individual clock evidence.

An additional event check supports the older June 19 offset. The Federal Reserve scheduled its June 19, 2013 statement for 14:00 Eastern, which is 18:00 UTC that day. The largest EURUSD five-minute range appears at 18:00 in the UTC reference and 20:00 in XM. This is corroboration, not a reason to approve every older timestamp. [Federal Reserve meeting page](https://www.federalreserve.gov/monetarypolicy/A4110FBE934A4A278474425B2BA9A0D8.htm).

The request for an older public candle-file endpoint timed out. The chart service response to a 2008 start request actually began in January 2012. These limitations are recorded; neither establishes that the 2008 XM prices are wrong or that older Dukascopy history does not exist.

## Prepared coverage

These bounds describe the retained files. They do not promise one uninterrupted usable backtest. Each file has allowed replay intervals in its sidecar.

| Instrument | First retained M5, UTC | Retained M5 rows | Excluded M5 rows | M5 unexplained long gaps |
|---|---|---:|---:|---:|
| EURUSD | 2016-01-03 22:00:00 | 784,655 | 591,384 | 0 |
| GBPUSD | 2016-01-03 22:00:00 | 753,204 | 595,507 | 1 |
| USDJPY | 2016-01-03 22:00:00 | 753,246 | 594,358 | 1 |
| AUDUSD | 2018-09-30 21:00:00 | 579,830 | 5,923 | 0 |
| NZDUSD | 2018-09-30 21:00:00 | 579,622 | 5,937 | 0 |
| USDCAD | 2016-01-03 22:00:00 | 772,191 | 591,605 | 1 |
| USDCHF | 2016-01-03 22:00:00 | 753,134 | 596,269 | 1 |
| EURAUD | 2018-09-30 21:00:00 | 579,583 | 5,919 | 1 |
| CADJPY | 2016-01-03 22:00:00 | 782,133 | 591,169 | 2 |
| GBPCAD | 2018-09-30 21:00:00 | 579,558 | 5,922 | 0 |
| USTEC | 2016-10-31 23:00:00 | 679,120 | 4,678 | 32 |

## Resolution and mislabeled records

Older lower-timeframe requests contain daily and hourly substitutes. A proxy candle can expose its parent’s later high, low, and close at the start of a five-minute interval. That would cause look-ahead in a replay. The processor excludes the prefix before regular detailed history, flagged coarse months, and unproven nonflat candles that exactly match a higher candle in OHLC and tick volume. For M15/H1/H4, verified finer M5 candles can demonstrate that the values belong entirely to the requested period. This preserves genuine short sessions, such as a final Friday M15 candle that also equals the shortened H1 candle. Remaining individual equality flags are conservative candidates and stay quarantined.

The month exclusion is deliberately conservative. For GBPUSD, USDJPY, and USDCHF, May through September 2018 are excluded from M5/M15, including some genuine candles near the edges. USDCAD excludes August and September 2018. AUDUSD/NZDUSD/EURAUD/GBPCAD detailed M5 begins late September 2018, but the flagged September boundary month is excluded, so the prepared files start with the following session. USTEC starts with the first session after its flagged October 2016 boundary month. The raw/excluded files preserve these edge days for later review.

Across all instruments, 3,338,980 complete M5 groups were compared with native higher-timeframe candles. OHLC differences: 0. Higher candles retain XM server-session boundaries; they were not rebuilt around UTC midnight. Partial sessions are checked separately in `partial_session_consistency.json`. Of 13,550 partial groups, 298 differ in OHLC. A difference on a partial finer grid can reflect missing/excluded quotes; it is not automatically a bad native parent candle. The entire affected parent period is blocked on all timeframe streams, because finer prices may otherwise miss a stop or target. Those extra boundaries are recorded in `partial_price_hazard_intervals` in the audit and sidecars.

## Gaps and trading sessions

Every nominal-grid hole is listed per instrument/timeframe. Reports distinguish likely weekends, holiday closures, recurrent overnight breaks, short quote gaps, rollover candidates, and unexplained long gaps. For US index holidays beyond Christmas/New Year, the classifier also requires a fully covered UTC reference window with no M5 records. A rare overnight index pattern needs at least five occurrences and reference absence, while common recurring patterns need twenty occurrences. These labels are evidence-based candidates rather than a complete historical exchange calendar. A reference candle within a hole shows activity on another feed; it does not prove XM was open or lost a tick.

US-equity holiday names and early closes provide calendar context. They are not a verified historical XM CFD session schedule. [NYSE holiday and trading-hours calendar](https://www.nyse.com/trade/hours-calendars).

Nasdaq cash has regular overnight pauses and holiday short sessions. Treating the nominal 24-hour grid as uninterrupted trading would overstate missing data. FX has occasional missing five-minute records and thin rollover periods. Small gaps remain explicit; no interpolation or fabricated bid/ask prices were added.

Long unexplained gaps require independent replay segments. Native D1/H4 candles spanning European clock changes can have a UTC duration different from their nominal 24/four hours. The current engine assumes fixed durations, so these particular parent candles are quarantined and create additional boundaries. Otherwise native short Sunday sessions are preserved, including genuine broker weekday candles whose UTC timestamp falls on Sunday.

| Instrument | All-timeframe shared intervals | Longest shared interval, UTC | Length, days |
|---|---:|---|---:|
| EURUSD | 40 | 2020-10-25 22:00:00 to 2021-10-30 21:00:00 | 370.0 |
| GBPUSD | 37 | 2020-10-25 22:00:00 to 2021-10-30 21:00:00 | 370.0 |
| USDJPY | 35 | 2020-10-25 22:00:00 to 2021-10-30 21:00:00 | 370.0 |
| AUDUSD | 11 | 2020-10-25 22:00:00 to 2021-10-30 21:00:00 | 370.0 |
| NZDUSD | 14 | 2020-10-25 22:00:00 to 2021-10-30 21:00:00 | 370.0 |
| USDCAD | 46 | 2020-10-25 22:00:00 to 2021-10-30 21:00:00 | 370.0 |
| USDCHF | 49 | 2020-10-25 22:00:00 to 2021-10-30 21:00:00 | 370.0 |
| EURAUD | 16 | 2020-10-25 22:00:00 to 2021-10-30 21:00:00 | 370.0 |
| CADJPY | 36 | 2020-10-25 22:00:00 to 2021-10-30 21:00:00 | 370.0 |
| GBPCAD | 14 | 2020-10-25 22:00:00 to 2021-10-30 21:00:00 | 370.0 |
| USTEC | 34 | 2020-03-24 11:00:00 to 2023-02-20 18:00:00 | 1063.3 |

These are conservative intervals shared by all five timeframes for each instrument. A strategy using fewer timeframes can use the intersection of just those files’ allowed intervals. A portfolio also needs the intersection across its instruments. Warmup must fit within the selected interval. Start each independent segment with fresh strategy/portfolio state and report any exposure still open at its end. Do not stitch segments into one uninterrupted account curve or carry exposure across their gaps.

## Volume, spreads, and other limitations

The volume column is MT5 tick volume, not exchange traded volume. Many older candles have zero recorded volume despite moving prices. The retained files still contain some zero volume records before 2019. Keep those prices for OHLC research, but do not assume those zero values represent a verified absence of activity or use them to validate a volume filter.

Many historical spread values are zero. They are treated as unavailable cost evidence. Nonzero MT5 spread fields are integer symbol points, not automatically FX pips or Nasdaq points, and do not establish bid/ask movement throughout the candle. These are bid OHLC files. Commission, spread, slippage, minimum volume, and overnight financing still need explicit broker-specific simulation assumptions.

## Outputs and validation

- `coverage_summary.csv` lists all 55 prepared files, retained/excluded counts, and bounds.
- `joint_replay_intervals.csv` lists the shared interval boundaries for each instrument.
- Per-instrument `*_raw_gaps.csv` and `*_prepared_gaps.csv` list every hole and reference activity.
- Per-instrument `*_excluded_server_clock.csv` preserves rejected source rows and all applicable reason flags.
- `audit.json`, `complete.json`, sidecars, and `history/xm_dataset.json` bind outputs and replay metadata to source hashes.
- `earlier_clock_diagnostic.json` and `earlier_daily_clock_audit.json` retain the older clock findings.

The loader checks prepared CSV hashes and completed dataset sidecar hashes, blocks a second clock conversion, rejects bounds outside verified coverage, and refuses a replay that crosses an excluded interval or unexplained long gap. A missing sidecar in the XM prepared folder also fails. All 55 file hashes matched, row accounting balanced, and the actual loader accepted a bounded sample from every prepared file. No strategy trades were simulated.

The preparation tests cover copied parent candles, genuine short sessions proven by M5, flat sparse candles, interval boundaries, weekends/holidays versus intraday gaps, complete versus partial aggregation, mixed offsets within a month, European/US clock differences, DST duration, changed files/sidecars, missing metadata, and out-of-coverage dates. The full unit suite passes. Detailed test output is in `output/xm_preparation_tests_20261001.txt`.

Reproduce offline preparation with `python prepare_xm_history.py`, then `python audit_xm_early_clocks.py`, then `python summarize_xm_preparation.py`. The optional `fetch_xm_clock_references.py --cached-only` rebuilds the already-downloaded older reference without network access. Its network mode is sequential and request-bounded; it does not guarantee the requested early dates are available.

XM remains useful for research, but the apparent 2008 coverage is not yet approved UTC history. The next data step is to reconstruct older per-instrument clock regimes from independent UTC anchors, then review the coarse-month edge days. For strategy testing now, use the verified recent intervals and frozen parameters with measured costs. No DEMO deployment, parameter choice, real-money trading, commit, or push occurred.
