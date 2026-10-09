# IFX chart history comparison, 8 October 2026

IFX did not provide a longer uninterrupted intraday archive than our other broker downloads. Its earlier dates include higher-timeframe substitutes. Raw exports remain research files, and must not be replayed before bounded clock conversion and gap review.

Downloaded 55 CSV files containing 5,915,397 rows across M5, M15, H1, H4, and D1. The eleven symbols include all nine symbols in the current DEMO suite, plus NZDUSD and USDCHF for comparison with prior broker collections. Requests span 1970-01-01 through 2026-10-08 in the unreviewed server clock, retaining completed candles through 7 October. All file hashes match the collection manifest.

Attached explicitly to `C:\Program Files\IFX Brokers MetaTrader 5\terminal64.exe`, account 2155212 on `IFXBrokers-Real`. MT5 trade_mode=0 identifies a demo account despite the Real server name. Active FX instruments use `.ifx`; Nasdaq cash is `T100.ifx_m`, mapped to USTEC. The unsuffixed major FX symbols are disabled and were not used for the final collection.

No credentials, account login changes, order submission, cancellation, bot parameters, risk settings, or DEMO deployment changes were made. The post-14-July-2026 forward holdout was downloaded for storage and coverage inspection only. The price-based clock audit excludes it. No strategy replay or optimization was run.

## Coverage comparison

| Instrument | Current DEMO | IFX first returned | IFX dense M5 | IC Markets stored M5 first | Exness dense M5 | XM dense M5 |
|---|---|---|---|---|---|---|
| EURUSD | Yes | 2018-04-10 | 2022-03-17 | 2016-01-03 | 2021-07-12 | 2008-01-02 |
| GBPUSD | Yes | 2018-04-10 | 2022-03-17 | 2016-01-03 | 2021-07-12 | 2008-01-02 |
| USDJPY | Yes | 2018-04-10 | 2022-03-17 | 2016-01-03 | 2021-07-12 | 2008-01-02 |
| AUDUSD | Yes | 2018-04-10 | 2022-03-17 | 2016-01-03 | 2021-07-12 | 2018-09-28 |
| NZDUSD | No | 2018-04-10 | 2022-03-17 | 2016-01-03 | 2021-07-13 | 2018-09-28 |
| USDCAD | Yes | 2018-04-12 | 2022-03-17 | 2025-01-01 | 2021-07-12 | 2008-01-02 |
| USDCHF | No | 2018-04-11 | 2022-03-17 | 2016-01-03 | 2021-07-12 | 2008-01-02 |
| EURAUD | Yes | 2018-04-10 | 2022-03-17 | None | 2021-07-12 | 2018-09-28 |
| CADJPY | Yes | 2018-04-10 | 2022-03-17 | None | 2021-07-13 | 2008-01-02 |
| GBPCAD | Yes | 2018-04-10 | 2022-03-17 | None | 2021-07-13 | 2018-09-28 |
| USTEC | Yes | 2013-07-16 | 2017-10-23 | 2016-01-03 | 2021-07-13 | 2016-10-27 |

IFX/XM dates in this table are raw server-clock dates. Exness dates are UTC, and IC Markets dates are from the stored UTC exports. IC Markets was not freshly queried on this device. These are observations for the tested accounts and servers, not universal broker limits. XM dense first dates can precede holes inside its archive, including several 2018 intervals. XM historical clock coverage is also bounded. See the prior [Exness report](exness_inspection_20261001.md), [XM report](xm_inspection_20261001.md), and [XM preparation audit](xm_data_audit_20261001.md).

A dense start requires five consecutive observed weekdays with at least 150 M5, 50 M15, 16 H1, or four H4 candles per day. OHLC and tick-volume equality with higher timeframes flags substitutes. These diagnostics do not certify that all later timestamps have native resolution or that every missing candle is a data defect.

## IFX detail

| Instrument | M5 rows | Dense M5/M15 first | Dense H1 first | Dense H4 first | First D1 | Long intraday M5 gaps after dense start |
|---|---:|---|---|---|---|---:|
| EURUSD | 342,610 | 2022-03-17 / 2022-03-17 | 2022-01-20 | 2022-01-19 | 2018-04-10 | 2 |
| GBPUSD | 342,565 | 2022-03-17 / 2022-03-17 | 2022-01-20 | 2022-01-19 | 2018-04-10 | 2 |
| USDJPY | 342,575 | 2022-03-17 / 2022-03-17 | 2022-01-20 | 2022-01-19 | 2018-04-10 | 1 |
| AUDUSD | 342,599 | 2022-03-17 / 2022-03-17 | 2022-01-20 | 2022-01-19 | 2018-04-10 | 2 |
| NZDUSD | 342,370 | 2022-03-17 / 2022-03-17 | 2022-01-20 | 2022-01-19 | 2018-04-10 | 2 |
| USDCAD | 342,564 | 2022-03-17 / 2022-03-17 | 2022-01-20 | 2022-01-19 | 2018-04-12 | 2 |
| USDCHF | 342,480 | 2022-03-17 / 2022-03-17 | 2022-01-20 | 2022-01-19 | 2018-04-11 | 2 |
| EURAUD | 342,568 | 2022-03-17 / 2022-03-17 | 2022-01-20 | 2022-01-19 | 2018-04-10 | 3 |
| CADJPY | 342,555 | 2022-03-17 / 2022-03-17 | 2022-01-20 | 2022-01-19 | 2018-04-10 | 3 |
| GBPCAD | 342,408 | 2022-03-17 / 2022-03-17 | 2022-01-20 | 2022-01-19 | 2018-04-10 | 3 |
| USTEC | 635,525 | 2017-10-23 / 2017-10-23 | 2017-06-08 | 2017-06-08 | 2013-07-16 | 404 |

The full quality audit records coarse months, monthly counts, short sessions, and gap candidates for every required timeframe. Long intraday gaps here mean at least 60 elapsed minutes between observations within the same weekday server date. The index has regular trading pauses, so its count needs its own session calendar.

- EURUSD: 22 same-day weekday gaps. Largest candidates: 2023-11-17 15:35:00 to 2023-11-17 18:00:00, 28 missing five-minute slots; 2024-08-02 15:55:00 to 2024-08-02 16:55:00, 11 missing five-minute slots. Full empty weekday candidates excluding 1 January/25 December: 2022-12-26.
- GBPUSD: 64 same-day weekday gaps. Largest candidates: 2023-11-17 15:35:00 to 2023-11-17 18:00:00, 28 missing five-minute slots; 2024-08-02 15:55:00 to 2024-08-02 16:55:00, 11 missing five-minute slots. Full empty weekday candidates excluding 1 January/25 December: 2022-12-26.
- USDJPY: 58 same-day weekday gaps. Largest candidates: 2023-11-17 15:35:00 to 2023-11-17 18:00:00, 28 missing five-minute slots. Full empty weekday candidates excluding 1 January/25 December: 2022-12-26.
- AUDUSD: 38 same-day weekday gaps. Largest candidates: 2023-11-17 15:35:00 to 2023-11-17 18:00:00, 28 missing five-minute slots; 2024-08-02 15:45:00 to 2024-08-02 16:55:00, 13 missing five-minute slots. Full empty weekday candidates excluding 1 January/25 December: 2022-12-26.
- NZDUSD: 154 same-day weekday gaps. Largest candidates: 2023-11-17 15:35:00 to 2023-11-17 18:00:00, 28 missing five-minute slots; 2024-08-02 15:55:00 to 2024-08-02 16:55:00, 11 missing five-minute slots. Full empty weekday candidates excluding 1 January/25 December: 2022-12-26.
- USDCAD: 67 same-day weekday gaps. Largest candidates: 2023-11-17 15:35:00 to 2023-11-17 18:00:00, 28 missing five-minute slots; 2024-08-02 15:55:00 to 2024-08-02 16:55:00, 11 missing five-minute slots. Full empty weekday candidates excluding 1 January/25 December: 2022-12-26.
- USDCHF: 106 same-day weekday gaps. Largest candidates: 2023-11-17 15:35:00 to 2023-11-17 18:00:00, 28 missing five-minute slots; 2024-08-02 15:55:00 to 2024-08-02 16:55:00, 11 missing five-minute slots. Full empty weekday candidates excluding 1 January/25 December: 2022-12-26.
- EURAUD: 10 same-day weekday gaps. Largest candidates: 2023-11-17 15:35:00 to 2023-11-17 18:00:00, 28 missing five-minute slots; 2022-11-09 00:05:00 to 2022-11-09 02:00:00, 22 missing five-minute slots; 2024-08-02 15:45:00 to 2024-08-02 16:55:00, 13 missing five-minute slots. Full empty weekday candidates excluding 1 January/25 December: 2022-12-26.
- CADJPY: 28 same-day weekday gaps. Largest candidates: 2023-11-17 15:35:00 to 2023-11-17 18:00:00, 28 missing five-minute slots; 2022-11-09 00:05:00 to 2022-11-09 02:00:00, 22 missing five-minute slots; 2024-08-02 15:45:00 to 2024-08-02 16:55:00, 13 missing five-minute slots. Full empty weekday candidates excluding 1 January/25 December: 2022-12-26.
- GBPCAD: 86 same-day weekday gaps. Largest candidates: 2023-11-17 15:35:00 to 2023-11-17 18:00:00, 28 missing five-minute slots; 2022-11-09 00:05:00 to 2022-11-09 02:00:00, 22 missing five-minute slots; 2024-08-02 15:55:00 to 2024-08-02 16:55:00, 11 missing five-minute slots. Full empty weekday candidates excluding 1 January/25 December: 2022-12-26.
- USTEC: 1555 same-day weekday gaps. Largest candidates: 2019-04-19 08:45:00 to 2019-04-19 23:45:00, 179 missing five-minute slots; 2020-03-16 01:10:00 to 2020-03-16 15:45:00, 174 missing five-minute slots; 2020-03-17 03:55:00 to 2020-03-17 10:35:00, 79 missing five-minute slots; 2018-07-06 03:10:00 to 2018-07-06 09:10:00, 71 missing five-minute slots. Full empty weekday candidates excluding 1 January/25 December: 2018-03-30, 2020-04-10, 2021-12-24, 2022-04-15, 2022-12-26, 2023-01-02, 2024-03-29, 2025-04-18.

Christmas/New Year and weekend closures are recorded separately. Boxing Day can also explain a full missing session. A shared midday FX hole needs investigation even when annual bar counts look normal. No gap was filled from another broker.

## Clock evidence

Compared raw M5 returns with hash-bound native UTC Dukascopy references, using offsets 0, 1, 2, and 3 hours. Windows split around European and US DST disagreement periods. Verification requires at least 50 consecutive matched returns, rank correlation at least 0.8, and a margin of at least 0.3 over the next offset. Coarse/short windows fail these thresholds and do not establish clock coverage.

| Instrument | Verified clock windows | Candidate rules by year |
|---|---:|---|
| EURUSD | 67 | 2022: european_dst; 2023: us_dst; 2024: us_dst; 2025: us_dst; 2026: us_dst |
| GBPUSD | 67 | 2022: european_dst; 2023: us_dst; 2024: us_dst; 2025: us_dst; 2026: us_dst |
| USDJPY | 67 | 2022: european_dst; 2023: us_dst; 2024: us_dst; 2025: us_dst; 2026: us_dst |
| AUDUSD | 67 | 2022: european_dst; 2023: us_dst; 2024: us_dst; 2025: us_dst; 2026: us_dst |
| NZDUSD | 67 | 2022: european_dst; 2023: us_dst; 2024: us_dst; 2025: us_dst; 2026: us_dst |
| USDCAD | 67 | 2022: european_dst; 2023: us_dst; 2024: us_dst; 2025: us_dst; 2026: us_dst |
| USDCHF | 67 | 2022: european_dst; 2023: us_dst; 2024: us_dst; 2025: us_dst; 2026: us_dst |
| EURAUD | 67 | 2022: european_dst; 2023: us_dst; 2024: us_dst; 2025: us_dst; 2026: us_dst |
| CADJPY | 67 | 2022: european_dst; 2023: us_dst; 2024: us_dst; 2025: us_dst; 2026: us_dst |
| GBPCAD | 67 | 2022: european_dst; 2023: us_dst; 2024: us_dst; 2025: us_dst; 2026: us_dst |
| USTEC | 136 | 2017: european_dst; 2018: none; 2019: european_dst; 2020: european_dst; 2021: european_dst; 2022: european_dst; 2023: us_dst; 2024: us_dst; 2025: us_dst; 2026: us_dst |

A single timeless broker offset is not approved by this audit. Per-year compatible rules are evidence from observed windows, not permission to extrapolate beyond them. UTC conversion must retain those boundaries and native parent-session consistency. Raw sidecars declare `ifx_server_unreviewed` and `raw_unreviewed`; the existing loader rejects them even if UTC is explicitly requested.

## Maximum-history checks and files

The connected terminal reports a 100,000,000-bar chart limit. No final request reached it. The first cache-limited EURUSD probe returned only June 2025 onward; after the terminal reconnected/restarted, the broad request returned the longer archive recorded above. Do not use that preliminary probe as the broker limit. MetaTrader documents that chart limits constrain Python history requests in its [copy_rates_range reference](https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesrange_py).

Saved files are under `output/ifx_inspection_20261008/history/`. The snapshot also contains `inspection.json`, `complete.json`, `quality.json`, `clock_audit.json`, and `comparison.json`. The collector and audit are `inspect_ifx_mt5.py` and `audit_ifx_history.py`; `summarize_ifx_inspection.py` rebuilds this report. Focused collection, identity, cutoff, gap, and loader-rejection checks are in `tests/test_ifx_collection.py`.

For a future walk-forward run, use IFX only as an additional recent broker feed after UTC preparation and splitting at unexplained gaps. It does not solve the request for a longer gap-free archive. Do not enlarge the selection period into the protected forward holdout or stitch prices from different brokers.

## Direct archive probes

Re-requested 4-9 January 2010 for 11 instruments. 11 returned no retained rows inside the tested window. This confirms no data was obtained for those tested old dates. API errors are retained in `archive_probes.json`. Broad requests beginning 1970 also returned only the archive dates in the tables above.

The 6-11 January 2020 M5 requests returned these completed row counts: EURUSD 5, CADJPY 5, USTEC 1365. A five-day FX window should have hundreds of bars per day at five-minute resolution. These probes support the coarse-prefix finding.

| Instrument | Date | Timeframe | Completed rows | Gaps of at least 60 minutes |
|---|---|---|---:|---|
| EURUSD | 2023-11-17 | M1 | 1291 | 15:35:00 to 18:01:00, 146 minutes |
| EURUSD | 2024-08-02 | M1 | 1378 | 15:55:00 to 16:58:00, 63 minutes |
| EURUSD | 2023-11-17 | M5 | 260 | 15:35:00 to 18:00:00, 145 minutes |
| EURUSD | 2024-08-02 | M5 | 277 | 15:55:00 to 16:55:00, 60 minutes |
| CADJPY | 2023-11-17 | M1 | 1294 | 15:35:00 to 18:01:00, 146 minutes |
| CADJPY | 2024-08-02 | M1 | 1368 | 15:45:00 to 16:58:00, 73 minutes |
| CADJPY | 2023-11-17 | M5 | 260 | 15:35:00 to 18:00:00, 145 minutes |
| CADJPY | 2024-08-02 | M5 | 275 | 15:45:00 to 16:55:00, 70 minutes |

These direct M1/M5 requests test whether the same broker can supply the missing observations. The small M1 samples are diagnostic files, not a full M1 archive. Probe CSVs and raw sidecars are under `probes/`, with recorded hashes.
