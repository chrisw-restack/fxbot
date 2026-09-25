# EmaFib accepted-order tracking and revalidation, 25 September 2026

**Broker-data update:** The requested M5 files have arrived. NZDUSD and USDCHF cover the full comparison, while USDCAD M5/H1/D1 start in January 2025. The [broker-history extension](ema_fib_broker_completion_20260925.md) supersedes the missing-export status and four-pair broker section below. Original study figures are retained here.

The tracking corrections are implemented locally. DEMO membership, numeric parameters, and 0.5% risk are unchanged. This report does not authorize deployment or real-money trading. The last confirmed trading-server revision remains `4cdc9eb` from 18 September.

## Assessment

The order lifecycle now passes the regression checks, but the current seven-pair strategy has a weak, cost-sensitive historical edge. Corrected 2020 through 2025 results fall from +39.26R to +20.98R on Dukascopy and from +70.72R to +51.34R on verified HistData. Maximum closed-trade drawdowns remain 66.82R and 49.39R. These are sums of independent pair results, not account return percentages.

Both sources produce WEAK retention in the first rolling test and a losing second test. The final test is profitable, but Dukascopy has a negative training baseline and HistData has a near-zero one. HistData's 1796% retention therefore does not establish reliable performance across periods. The former MODERATE label should not be carried forward as the corrected strategy's current verdict.

A 1-pip spread changes the six-year totals to -25.21R and +4.27R. The four available broker pairs return only +11.05R, with a 60.36R drawdown and 47 consecutive losses. These results do not support increasing risk or promoting the strategy. GBPUSD and USDCAD lose on both long-history sources, while AUDUSD is approximately flat. Removing pairs improves the same historical sample, but is not yet a validated selection rule.

Keep the numeric settings fixed while completing the missing broker comparison and reviewing fresh DEMO outcomes. Do not start a broad parameter search to recover the old profit figure. A later search should use a small declared grid, train-only selection in each fold, cost stress, and an untouched evaluation period. Break-even stops and pending-age filters remain unsupported by the existing evidence.

## What changed

Proposed signals and accepted orders now have separate state. Each accepted attempt carries a recoverable original-swing identity through the existing order ledger. New fractals and rejected proposals cannot replace that origin. Broker or simulator snapshots determine whether an order is pending or filled. An H1 price touch no longer changes order state.

Cancellation requests retain their state until confirmed, and target the originating attempt. A filled position remains protected during cancellation retries or cancellation of a partially filled remainder. Final closes clear the matching order, and losses invalidate its original swing. Repeated outcomes are idempotent. Older recovered losses do not reset a current cooldown or replace a newer loss attribution.

Valid checkpoints preserve full strategy state. If a checkpoint is unavailable, ledger-attributed orders recover their original swing from their setup identity. Legacy orders without that identity are still tracked and receive bias-flip cancellation checks. Their eventual losses apply a cooldown without guessing which current swing to invalidate. Pending-age settings remain disabled; the age of an inherited order without a checkpoint is not inferred.

All 150 tests pass, including 17 new regression tests. The new tests cover the three audited defects, gap fills, rejection, cancellation failure and retry, partial outcomes, duplicate closes, ledger recovery including late attribution, checkpoints, legacy orders, and stale recovered losses. Research asserts that strategy and simulator ending exposure agree in every corrected run.

## Research method

Completed 134 corrected replays plus 2 frozen-code controls, one worker at a time. The frozen EURUSD and AUDUSD controls reproduce all original trade fields from the 23 September review. The original implementation is loaded from `0a1caec9307d2f80987d61da8a6228807be6a8e2`. Old result files are retained.

The main comparisons use 2020 through 2025 and a separate 1 January through 14 July 2026 period. Each replay starts fresh with up to 180 days of warm-up. H1/D1 generate decisions and M5 executes orders. Spread and $7 per lot round-trip commission are included. Gaps are modeled, but variable spreads, additional slippage, swap, news blocking, and the shared DEMO daily-loss/portfolio gates are absent. Trade sizes use 0.5% of each independent symbol account, initially $10,000.

Tables combine independent symbol net-R trade histories in closing-time order. Profit factor is positive net R divided by absolute negative net R. These are not pooled account returns or equity drawdowns. Open exposure at each period end is left open and listed in the raw results. It is excluded from closed-trade metrics.

All HistData files pass the provenance-enforcing loader. Numeric parameters are held fixed throughout. No search or symbol selection occurs inside the rolling folds. Because these historical periods were previously used in development, this is historical revalidation, not fresh unseen evidence. Data after 14 July 2026 remains excluded.

The prior source audit found identical OHLC at approximately 99.98% of common M5 timestamps. HistData also omits about 10,500 to 10,800 M5 bars per pair present in Dukascopy. Provenance verification does not establish completeness or an independent price feed. The repaired HistData files are comparable evidence with different coverage, not independent confirmation.

## Before and after, 2020 through 2025

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy, original | 251 | 8.76 | +39.26 | 1.16 | 0.156 | 65.91 | 2 / 33 |
| dukascopy, corrected | 255 | 8.24 | +20.98 | 1.08 | 0.082 | 66.82 | 2 / 33 |
| histdata, original | 258 | 9.69 | +70.72 | 1.28 | 0.274 | 47.38 | 2 / 30 |
| histdata, corrected | 263 | 9.13 | +51.34 | 1.20 | 0.195 | 49.39 | 2 / 30 |

### A removed winner explained

On 22 April 2020, AUDUSD had a pending BUY at 0.6292371. The 23:00 UTC H1 candle had a bid low of 0.62922. With the modeled 0.2-pip spread, the ask low was 0.62924, just above the entry, so the order was still unfilled. The old strategy treated the bid touch as a fill and skipped its bias-flip cancellation. At that candle's midnight close, the corrected strategy sees the real pending state and cancels because H1 bias has turned bearish. The old order instead filled at 00:20 on 23 April and later won +12.98R. Keeping that winner would retain the tracking defect. Separate trace files preserve both event paths.

## Before and after, 2026 through 14 July

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy, original | 22 | 13.64 | +17.34 | 1.80 | 0.788 | 13.00 | 2 / 11 |
| dukascopy, corrected | 23 | 13.04 | +16.23 | 1.72 | 0.706 | 13.00 | 2 / 11 |
| histdata, original | 21 | 9.52 | +4.37 | 1.20 | 0.208 | 13.00 | 1 / 11 |
| histdata, corrected | 22 | 9.09 | +3.27 | 1.14 | 0.149 | 13.00 | 1 / 11 |

## Corrected results by pair, 2020 through 2025

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| EURUSD, dukascopy | 26 | 11.54 | +14.28 | 1.58 | 0.549 | 20.31 | 2 / 19 |
| EURUSD, histdata | 30 | 13.33 | +25.30 | 1.95 | 0.843 | 17.02 | 2 / 16 |
| GBPUSD, dukascopy | 30 | 3.33 | -18.02 | 0.42 | -0.601 | 21.53 | 1 / 20 |
| GBPUSD, histdata | 32 | 3.12 | -20.24 | 0.39 | -0.632 | 23.74 | 1 / 22 |
| AUDUSD, dukascopy | 53 | 7.55 | -0.63 | 0.99 | -0.012 | 19.45 | 1 / 19 |
| AUDUSD, histdata | 51 | 7.84 | +0.51 | 1.01 | 0.010 | 20.66 | 1 / 20 |
| NZDUSD, dukascopy | 58 | 8.62 | +8.13 | 1.14 | 0.140 | 24.15 | 2 / 18 |
| NZDUSD, histdata | 59 | 11.86 | +33.47 | 1.59 | 0.567 | 16.43 | 2 / 16 |
| USDJPY, dukascopy | 33 | 12.12 | +20.86 | 1.67 | 0.632 | 24.89 | 2 / 23 |
| USDJPY, histdata | 33 | 12.12 | +21.52 | 1.71 | 0.652 | 25.28 | 2 / 24 |
| USDCAD, dukascopy | 27 | 3.70 | -15.52 | 0.46 | -0.575 | 21.19 | 1 / 19 |
| USDCAD, histdata | 27 | 3.70 | -15.92 | 0.45 | -0.590 | 21.58 | 1 / 19 |
| USDCHF, dukascopy | 28 | 10.71 | +11.89 | 1.44 | 0.425 | 13.83 | 1 / 13 |
| USDCHF, histdata | 31 | 9.68 | +6.70 | 1.21 | 0.216 | 14.55 | 1 / 13 |

## Rolling train/test checks

Training uses 2016–2019, 2018–2021, and 2020–2023. The corresponding tests are 2020–2021, 2022–2023, and 2024–2025. Each side starts fresh. The first training window has no pre-2016 warm-up because the files start in January 2016. Training and test metrics use the same fixed parameters; no parameter is chosen using a test window. Retention is test expectancy divided by training expectancy. It is undefined when training expectancy is nonpositive. A losing test receives FAIL regardless of the ratio.

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy 2020 train | 174 | 10.92 | +93.15 | 1.56 | 0.535 | 27.84 | 2 / 25 |
| dukascopy 2020 test | 79 | 8.86 | +13.67 | 1.18 | 0.173 | 22.63 | 2 / 21 |
| dukascopy 2022 train | 134 | 11.19 | +66.03 | 1.51 | 0.493 | 22.63 | 2 / 21 |
| dukascopy 2022 test | 115 | 6.09 | -24.46 | 0.79 | -0.213 | 54.16 | 1 / 33 |
| dukascopy 2024 train | 194 | 7.22 | -10.80 | 0.94 | -0.056 | 56.70 | 2 / 33 |
| dukascopy 2024 test | 61 | 11.48 | +31.77 | 1.54 | 0.521 | 23.01 | 1 / 21 |
| histdata 2020 train | 170 | 11.76 | +115.18 | 1.71 | 0.678 | 21.69 | 2 / 21 |
| histdata 2020 test | 78 | 8.97 | +14.59 | 1.19 | 0.187 | 22.63 | 2 / 21 |
| histdata 2022 train | 134 | 11.94 | +79.50 | 1.62 | 0.593 | 22.63 | 2 / 21 |
| histdata 2022 test | 122 | 7.38 | -6.87 | 0.94 | -0.056 | 36.57 | 1 / 30 |
| histdata 2024 train | 200 | 8.00 | +7.71 | 1.04 | 0.039 | 39.27 | 2 / 30 |
| histdata 2024 test | 63 | 12.70 | +43.63 | 1.73 | 0.693 | 23.01 | 2 / 21 |

| Source | Test starts | Expectancy retention | Verdict |
|---|---|---:|---|
| dukascopy | 2020 | 32.3% | WEAK |
| dukascopy | 2022 | -43.2% | FAIL |
| dukascopy | 2024 | undefined | UNDEFINED |
| histdata | 2020 | 27.6% | WEAK |
| histdata | 2022 | -9.5% | FAIL |
| histdata | 2024 | 1796.0% | STRONG |

Combined non-overlapping test windows, with fresh state at each fold boundary:

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy | 255 | 8.24 | +20.98 | 1.08 | 0.082 | 66.82 | 2 / 33 |
| histdata | 263 | 9.13 | +51.34 | 1.20 | 0.195 | 49.39 | 2 / 30 |

## Wider-spread stress

This changes only spread to 1.0 pip on every pair, with the same commission and parameters. It reruns execution, so fill changes can alter later setups; the result need not worsen monotonically for every individual pair.

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy, 2020_2025 | 255 | 8.24 | +20.98 | 1.08 | 0.082 | 66.82 | 2 / 33 |
| dukascopy, spread_1pip | 246 | 6.91 | -25.21 | 0.90 | -0.102 | 98.16 | 2 / 45 |
| histdata, 2020_2025 | 263 | 9.13 | +51.34 | 1.20 | 0.195 | 49.39 | 2 / 30 |
| histdata, spread_1pip | 254 | 7.87 | +4.27 | 1.02 | 0.017 | 81.62 | 2 / 37 |

## Illustrative financing debit

Historical broker swap schedules are unavailable. This is a post-processing sensitivity, not a broker swap backtest: subtract $0, $3, or $7 per lot for each 24 hours held, prorated by duration. It keeps original fills, lot sizes, and trade paths fixed. It does not model directional credits, rollover times, triple-swap days, or changed compounding.

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy, $0/lot/day | 255 | 8.24 | +20.98 | 1.08 | 0.082 | 66.82 | 2 / 33 |
| dukascopy, $3/lot/day | 255 | 8.24 | +14.04 | 1.06 | 0.055 | 70.55 | 2 / 33 |
| dukascopy, $7/lot/day | 255 | 8.24 | +4.79 | 1.02 | 0.019 | 75.52 | 2 / 33 |
| histdata, $0/lot/day | 263 | 9.13 | +51.34 | 1.20 | 0.195 | 49.39 | 2 / 30 |
| histdata, $3/lot/day | 263 | 9.13 | +44.63 | 1.17 | 0.170 | 52.96 | 2 / 30 |
| histdata, $7/lot/day | 263 | 9.13 | +35.67 | 1.13 | 0.136 | 57.72 | 2 / 30 |

## Symbol exclusions, diagnostic only

Each single-symbol exclusion is shown separately, followed by both. These are recombinations of independent pair results, without shared account interaction. GBPUSD and USDCAD were identified using the same historical evaluation years, so these comparisons are post-hoc and do not validate a new five-pair deployment.

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy, omit none | 255 | 8.24 | +20.98 | 1.08 | 0.082 | 66.82 | 2 / 33 |
| dukascopy, omit GBPUSD | 225 | 8.89 | +39.00 | 1.18 | 0.173 | 54.58 | 1 / 31 |
| dukascopy, omit USDCAD | 228 | 8.77 | +36.50 | 1.16 | 0.160 | 55.45 | 2 / 31 |
| dukascopy, omit GBPUSD, USDCAD | 198 | 9.60 | +54.52 | 1.28 | 0.275 | 45.74 | 1 / 29 |
| histdata, omit none | 263 | 9.13 | +51.34 | 1.20 | 0.195 | 49.39 | 2 / 30 |
| histdata, omit GBPUSD | 231 | 9.96 | +71.58 | 1.32 | 0.310 | 38.07 | 2 / 28 |
| histdata, omit USDCAD | 236 | 9.75 | +67.26 | 1.29 | 0.285 | 38.74 | 2 / 28 |
| histdata, omit GBPUSD, USDCAD | 204 | 10.78 | +87.50 | 1.44 | 0.429 | 33.19 | 2 / 26 |

## Matched broker-data comparison

Complete M5/H1/D1 broker files exist for EURUSD, GBPUSD, AUDUSD, USDJPY. The following tables compare exactly those pairs on each source. Broker D1 bars retain the IC Markets session boundaries, including Sunday UTC starts, while the other sources use UTC-day bars. These candle differences are part of the deployment check.

2020_2025

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy | 142 | 8.45 | +16.48 | 1.12 | 0.116 | 46.75 | 2 / 23 |
| histdata | 146 | 8.90 | +27.09 | 1.19 | 0.186 | 36.13 | 2 / 23 |
| mt5_icmarkets_utc | 147 | 8.16 | +11.05 | 1.08 | 0.075 | 60.36 | 2 / 47 |

2026_to_july14

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy | 16 | 12.50 | +9.69 | 1.60 | 0.606 | 8.73 | 1 / 7 |
| histdata | 15 | 6.67 | -3.28 | 0.80 | -0.218 | 15.13 | 1 / 13 |
| mt5_icmarkets_utc | 16 | 6.25 | -4.77 | 0.73 | -0.298 | 16.62 | 1 / 14 |

The broker subset is incomplete. NZDUSD, USDCAD, and USDCHF lack M5 exports here. Run this read-only data export on the MT5 Windows host, then copy the resulting three CSVs into this checkout's `data/historical/mt5_icmarkets_utc/` directory:

```cmd
cd /d C:\fxbot
python fetch_data_mt5_icmarkets.py --symbols NZDUSD USDCAD USDCHF --timeframes M5 --start 2016-01-01 --end 2026-07-15
```

The H1/D1 files for those pairs are already present. This command does not deploy the code changes or start another bot process. Completing the seven-pair broker comparison depends on receiving the missing exports.

## Coverage audit

Dukascopy has two or three missing H1 bars per pair despite complete M5 coverage, plus a few inconsistent higher-timeframe OHLC values. HistData's H1/D1 bars agree with its own M5 aggregation in this check. The known missing Dukascopy AUDUSD H1 candle at 23 March 2026 19:00 UTC explains the approximately 12.96R recent-period source difference documented in the prior review. The remaining coverage findings limit claims of agreement; do not delete valid HistData bars to force its results to match.

Checks compare H1 and weekday D1 availability/OHLC against aggregation of the available M5 candles, from 2020 through 14 July 2026. A complete H1 bucket contains 12 M5 candles; a complete D1 bucket contains 288. These are coverage checks, not proof that every market tick exists. CSV files were not filled, deleted, or rebuilt.

| Source | Pair | TF | Missing higher bars with complete M5 coverage | Different common OHLC |
|---|---|---|---:|---:|
| dukascopy | EURUSD | H1 | 2 | 8 |
| dukascopy | EURUSD | D1 | 0 | 6 |
| dukascopy | GBPUSD | H1 | 2 | 8 |
| dukascopy | GBPUSD | D1 | 0 | 6 |
| dukascopy | AUDUSD | H1 | 3 | 6 |
| dukascopy | AUDUSD | D1 | 0 | 6 |
| dukascopy | NZDUSD | H1 | 3 | 9 |
| dukascopy | NZDUSD | D1 | 0 | 6 |
| dukascopy | USDJPY | H1 | 2 | 8 |
| dukascopy | USDJPY | D1 | 0 | 5 |
| dukascopy | USDCAD | H1 | 3 | 7 |
| dukascopy | USDCAD | D1 | 0 | 5 |
| dukascopy | USDCHF | H1 | 2 | 9 |
| dukascopy | USDCHF | D1 | 0 | 5 |
| histdata | EURUSD | H1 | 0 | 0 |
| histdata | EURUSD | D1 | 0 | 0 |
| histdata | GBPUSD | H1 | 0 | 0 |
| histdata | GBPUSD | D1 | 0 | 0 |
| histdata | AUDUSD | H1 | 0 | 0 |
| histdata | AUDUSD | D1 | 0 | 0 |
| histdata | NZDUSD | H1 | 0 | 0 |
| histdata | NZDUSD | D1 | 0 | 0 |
| histdata | USDJPY | H1 | 0 | 0 |
| histdata | USDJPY | D1 | 0 | 0 |
| histdata | USDCAD | H1 | 0 | 0 |
| histdata | USDCAD | D1 | 0 | 0 |
| histdata | USDCHF | H1 | 0 | 0 |
| histdata | USDCHF | D1 | 0 | 0 |

## Period-end exposure

Open/pending counts by source, symbol, and run are recorded below. These trades are not forcibly liquidated and are excluded from the closed results.

- dukascopy, GBPUSD, fold_2020_train: 1
- histdata, GBPUSD, fold_2020_train: 1

## Reproduction and deployment boundary

The 134-run study finished with matching code hashes. A subsequent recovery-only correction lets authoritative ledger attribution replace an initially unknown legacy origin. The tested strategy snapshot remains in `study_strategy.py`, with the original manifest unchanged. Two additional full-period EURUSD/AUDUSD controls match every corrected trade field and ending exposure. `recovery_hardening_verification.json` records the final source hashes and those checks. This late-attribution branch is not exercised by fresh backtest orders, which receive their origin at acceptance.

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe research_ema_fib_tracking.py
.venv\Scripts\python.exe audit_ema_fib_coverage.py
.venv\Scripts\python.exe summarize_ema_fib_tracking.py
```

Detailed trades, assumptions, input and code hashes, fold results, and controls are saved in `output/ema_fib_tracking_20260925/`. The previous review remains in `output/ema_fib_review_20260923/`. No MT5 terminal connection, deployment, risk increase, or real-money promotion was performed. Any eventual rollout must preserve `logs/setup_ledger.json` and stop the old bot before starting a new instance. Legacy inherited orders remain explicitly unattributed rather than assigned to a guessed swing.
