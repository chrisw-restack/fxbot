# HistData provenance and UTC repair, 21 September 2026

22 September follow-up: the [IMS Reversal performance rerun](ims_histdata_rerun_20260922.md)
is complete. It replaces the earlier HistData figures and documents the near-identical
overlapping Dukascopy prices and remaining missing intervals.

## Scope and status

Completed locally. All 408 source archives were downloaded again from HistData over certificate-verified HTTPS and passed their clock checks. All 121 replacement CSVs are installed with hash-bound provenance sidecars. All original CSVs are preserved and their backup hashes verified.

This repairs the local data pipeline. It does not validate a trading edge, change DEMO parameters, or deploy code to the MT5 host. No strategy evaluation uses the protected period after 14 July 2026. The data rebuild preserves the exclusive cutoff of 25 July, with three D1 files ending earlier because their last days contain conflicting prices. Merely repairing timestamps beyond the research cutoff does not make that period available for tuning.

## Why one timezone rule was wrong

The [HistData FAQ](https://www.histdata.com/f-a-q/) declares fixed EST without daylight saving, and identifies its OHLC as bid prices. Fresh official downloads do not consistently follow that declared clock. The earlier converter applied America/New_York to every archive, which also fails in some years.

Measured results across all 24 symbols:

| Archive period | Files | Compatible clock conversion |
|---|---:|---|
| Annual 2016 to 2018 | 72 | Add five hours in winter and four in summer, using US DST dates |
| Annual 2019 to 2025 | 168 | Add five hours in winter and four in summer, using European DST dates |
| January and February 2026 | 48 | Add five hours; the tested conventions coincide |
| March 2026 | 24 | European DST dates |
| April to July 2026 | 96 | Add four hours; US and European rules coincide during these files |

For the European variant, the implementation adds seven hours to the raw wall clock, localizes it to Europe/Helsinki, and converts to UTC. This expresses the observed UTC-5/UTC-4 clock with European transitions. It does not mean HistData claims to use Helsinki time. Future archives must pass their own check.

Every archive is compared with its matching local Dukascopy UTC M5 reference, with both input hashes retained. The audit separates months and the US/European DST regimes, including the weeks when their clocks disagree. It compares consecutive five-minute close returns at both possible offsets. Accepted windows need correlation of at least 0.80 and a margin of at least 0.30 over the alternative offset. Previously accepted evidence uses Pearson correlation and at least 100 pairs. The final verifier uses rank correlation and at least 50 pairs, with Pearson retained as a diagnostic. The smaller threshold accommodates short Sunday transition windows; rank correlation prevents one exceptional price spike from deciding a month's clock. Each receipt records its actual method and thresholds.

External time anchors support the reference alignment:

| EURUSD raw HistData minute | Correct UTC minute | External anchor |
|---|---|---|
| 20 March 2024, 13:00 | 18:00 | [Federal Reserve announcement at 14:00 EDT](https://www.federalreserve.gov/newsevents/pressreleases/monetary20240320a.htm) |
| 5 July 2024, 08:30 | 12:30 | [BLS employment release at 08:30 ET](https://www.bls.gov/news.release/archives/empsit_07052024.htm) |
| 1 November 2024, 07:30 | 12:30 | [BLS employment release at 08:30 ET](https://www.bls.gov/news.release/archives/empsit_11012024.htm) |

A fresh sample from Dukascopy's official candle service also matches the stored UTC reference around 20 March 2024. The raw +4-hour summer match alone could never establish the full archive's DST convention. The transition weeks are what distinguish the rules.

## Downloads and price conflicts

The 408 archives cover ten annual files and seven 2026 monthly files per symbol. Of these, 384 are byte-identical to the original local ZIPs. All 24 July 2026 archives changed. The complete newly downloaded July archives extend later than the active dataset, so conversion retains the original cutoff.

The raw files contain 10,016 exact duplicate rows, which are removed without choosing between prices. Separately, 31 archives contain different OHLC for the same minute, affecting 1,156 distinct symbol/minute observations across the downloaded coverage. A fresh official MetaTrader-format EURUSD July export has the same four conflicting minutes as its ASCII equivalent, so changing export format does not resolve that case.

The normal reader rejects price conflicts. The audit's explicit `--quarantine-conflicts` option records and excludes **every** version of each conflicting minute. Conversion also removes every M5, M15, H1, H4, or D1 candle containing such a minute. It cannot quietly build a seemingly complete candle from the remaining minutes. Each output sidecar lists the conflicting UTC minutes and the number of resampled candles excluded. These lists describe the source archives, so some minutes can lie beyond a particular output's cutoff.

Within the active cutoff, 711 conflicting symbol/minute observations were excluded. This removed 384 M5, 307 M15, 243 H1, 171 H4, and 105 D1 candles across the 24 instruments. XAUUSD's additional M1 file excludes 282 conflicting minutes. These are overlapping timeframe counts, not independent observations.

The final valid daily candle is 23 July for GBPCAD and USDJPY, and 22 July for USA100. Their filenames now reflect those dates. The removed trailing days are explicitly accounted for by the quarantine metadata; all other files still end on 24 July.

This policy does not recover missing prices. Other existing provider gaps remain, and missing execution candles can affect fills and stops. Verified provenance means the origin and conversion are traceable; it does not certify complete or error-free market history.

## Files and safeguards

- `fetch_data_histdata.py` verifies the requested symbol/period, HTTPS origin, ZIP contents, and CRC before saving a download receipt. Conversion requires matching archive hashes and accepted clock evidence.
- `data/histdata_provenance.py` validates source OHLC, records duplicate cleanup, checks clock evidence, and validates the converted-file contract.
- `audit_histdata_provenance.py` provides sequential downloads and clock checks. Its dated migration stages every existing timeframe before publishing replacements, and checks backup destinations before the first replacement.
- `data/historical_loader.py` rejects HistData files with absent provenance or a changed CSV hash, and refuses a second timezone conversion.
- Each active CSV has a `.csv.meta.json` sidecar containing its hash, UTC/bid contract, source receipts, clock evidence, and exclusions. Keep sidecars with their files when copying data to another PC.

Audit evidence is under `output/histdata_provenance_20260921/`, including `downloads.json`, `clock_audit.json`, `utc_anchors.json`, `rebuild_plan.json`, `published.json`, `integrity_check.json`, and `smoke_replay.json`. The fresh Dukascopy sample and alternative official export are retained there too. These data artifacts follow the repository's existing ignore rules.

The old converted files are retained under `data/historical/_quarantine_histdata_20260921/` with metadata that blocks their use in normal backtests. Changed old raw ZIPs are retained under `data/raw/histdata_unverified_20260921/`. Verified raw archives and receipts are installed in `data/raw/histdata/`; the separately downloaded copies remain under `data/raw/histdata_verified_20260921/`.

## Consequences for IMS research

The HistData performance tables in the 18 September review used the old conversion and are superseded as evidence. They must be rerun from the repaired files before drawing any conclusion about current HistData performance. This repair does not turn HistData into an independent price feed: the observed extensive price overlap with Dukascopy remains relevant.

The IC Markets files were not changed. During clock diagnosis, some early broker-export transition weeks, including March 2016, disagreed with the direct UTC reference. That is a separate broker-export validation issue, not a reason to shift HistData to match it. Existing broker replay numbers remain the numbers produced by those unchanged inputs; the early-year clock discrepancy needs its own audit before relying on those periods.

No numeric parameter selection or DEMO rollout follows from this repair.

## Verification

| Check | Result |
|---|---|
| Official archive download and clock audit | 408 accepted, zero unresolved checks |
| Published CSV hashes and provenance | 121 passed |
| Original CSV backup hashes | 121 passed |
| Installed raw ZIP hashes and clock contracts | 408 passed |
| Unit and regression suite | 133 tests passed |
| Fresh Dukascopy reference sample | All 40 OHLC candles matched the stored UTC reference |
| Fixed-parameter IMS integration replay | 2024 only, with earlier warm-up; 149,668 loaded bars and 12 closed trades |

The replay confirms the repaired M5/M15/H4 files load and complete trades through the current pipeline. It is not a performance comparison or parameter-selection result.

Every active CSV changed. Across all stored timeframes, 1,485,775 common timestamp rows have changed values. Total rows changed from 30,407,472 to 30,406,626. The counts overlap across timeframes and combine corrected resampling, provider revisions, and conflict exclusions. For EURUSD H4, 834 common candles changed, with 27 timestamps added and one removed. Earlier HistData strategy results therefore need a rerun.

Validation commands used:

```text
python -m unittest discover -s tests -v
python output/histdata_provenance_20260921/verify_repair.py
```

The latter is a retained local audit helper, not a tracked application entry point. Historical data and output folders are gitignored, so a code commit alone does not transfer the repaired data. Copy each CSV with its sidecar if another backtest machine needs this dataset. No commit, push, or MT5 deployment was performed.
