# Candle Confirmation GBPUSD recovery study, 2026-09-30

USDJPY Candle Confirmation is removed from new DEMO runs at the user’s request. GBPUSD remains enabled with the same parameters and 0.5% planned risk. Recovery-only remains an experiment. The simpler touch rule improves broker performance and drawdown, but fails wider-spread robustness and does not improve total R across all feeds. Returning inside the range makes results worse.

## Rules tested

Current is the existing corrected GBPUSD strategy. Recovery touch adds one gate: BUY needs a completed M5 low at or below the originating H1 low; SELL needs a completed M5 high at or above its H1 high. The touch can be on the signal bar. The usual confirmed swing break, FVG, daily trend, stop and target rules still apply. Recovery + inside close adds a second gate: the signal close must be strictly between the originating H1 low and high. Equality counts as a touch but not an inside close.

The gate scans the same setup-specific entry buffer as the existing diagnostics (maximum 1,000 M5 bars). It is a recovery of local M5 structure after the touch; the touch-only version can signal while still outside the H1 range. It does not require a fresh crossing or change expiry at the target-side H1 extreme. Filtered detections leave the setup eligible and do not create or consume a proposal. Full sequential replays allow later opportunities and changed setup histories; these results are not obtained by deleting trades from the current trade list.

Shared tracking, 250 D1 / 100 H1 / 1,200 M5 warmup requirements, next-open bid/ask market fills, eight-pip executable minimum stops, and at least 1:1 filled R:R remain active. GBP parameters remain fn=3, retracement=50%, target=150% of H1 range, symmetric proposed R:R=2, daily EMA20/50 separation=0.1%, H1 minimum range=8 pips, body=60%.

## Full matched replays

January 1, 2017 through July 14, 2026. Completed 2016 bars warm each feed; data after the cutoff is excluded. Standalone 0.5% planned risk, constant 0.2-pip spread and configured commission. No news filter, other strategies, daily-loss cap, swap or actual tick slippage. Open positions at the end are not forcibly closed.

Dukascopy

| Case | Trades | Win % | Net R | PF | R/trade | Closed DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| Current | 399 | 38.10 | +27.82 | 1.105 | +0.0697 | 18.87 | 5/11 |
| Recovery touch | 204 | 38.73 | +18.13 | 1.135 | +0.0889 | 17.91 | 5/9 |
| Recovery + inside close | 186 | 36.02 | +0.96 | 1.007 | +0.0052 | 17.85 | 5/9 |

HistData

| Case | Trades | Win % | Net R | PF | R/trade | Closed DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| Current | 399 | 37.34 | +16.84 | 1.063 | +0.0422 | 19.69 | 8/11 |
| Recovery touch | 207 | 37.20 | +8.85 | 1.063 | +0.0427 | 17.91 | 5/10 |
| Recovery + inside close | 187 | 36.36 | +2.61 | 1.020 | +0.0139 | 17.85 | 5/11 |

IC Markets

| Case | Trades | Win % | Net R | PF | R/trade | Closed DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| Current | 397 | 36.27 | +4.95 | 1.018 | +0.0125 | 23.28 | 5/10 |
| Recovery touch | 205 | 38.05 | +15.34 | 1.114 | +0.0748 | 12.39 | 4/10 |
| Recovery + inside close | 190 | 35.26 | -2.14 | 0.984 | -0.0112 | 16.08 | 4/11 |

| Feed / rule | Budget R | Account growth | Equity DD | End exposure |
|---|---:|---:|---:|---:|
| Dukascopy / Current | +27.70 | +13.68% | 8.95% | 0 |
| Dukascopy / Recovery touch | +17.89 | +8.77% | 9.36% | 0 |
| Dukascopy / Recovery + inside close | +1.16 | +0.11% | 9.28% | 0 |
| HistData / Current | +17.26 | +7.91% | 9.36% | 0 |
| HistData / Recovery touch | +8.43 | +3.75% | 9.34% | 0 |
| HistData / Recovery + inside close | +2.86 | +0.96% | 9.24% | 0 |
| IC Markets / Current | +5.12 | +1.58% | 11.60% | 0 |
| IC Markets / Recovery touch | +15.08 | +7.27% | 5.99% | 0 |
| IC Markets / Recovery + inside close | -1.77 | -1.34% | 7.60% | 0 |

Net R uses simulated net P&L divided by modeled risk at the actual fill. Budget R uses net P&L divided by the planned 0.5% balance budget; lot rounding and fill differences mean account growth is not exactly net R × 0.5%. Closed drawdown in R and marked-to-market account drawdown are separate measures.

IC Markets spread sensitivity, full period

| Case | Trades | Win % | Net R | PF | R/trade | Closed DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| Current, 0.2 pip | 397 | 36.27 | +4.95 | 1.018 | +0.0125 | 23.28 | 5/10 |
| Recovery touch, 0.2 pip | 205 | 38.05 | +15.34 | 1.114 | +0.0748 | 12.39 | 4/10 |
| Recovery + inside close, 0.2 pip | 190 | 35.26 | -2.14 | 0.984 | -0.0112 | 16.08 | 4/11 |
| Current, 1 pip | 397 | 35.26 | -20.53 | 0.925 | -0.0517 | 31.07 | 5/10 |
| Recovery touch, 1 pip | 205 | 36.59 | -0.20 | 0.999 | -0.0010 | 14.64 | 4/10 |
| Recovery + inside close, 1 pip | 190 | 33.68 | -16.50 | 0.876 | -0.0869 | 18.61 | 4/11 |
| Current, 2 pip | 397 | 34.76 | -41.10 | 0.851 | -0.1035 | 43.73 | 5/10 |
| Recovery touch, 2 pip | 205 | 36.10 | -10.31 | 0.925 | -0.0503 | 21.18 | 4/10 |
| Recovery + inside close, 2 pip | 190 | 33.16 | -25.26 | 0.811 | -0.1329 | 27.11 | 4/11 |

The touch rule nearly breaks even at one pip and loses at two pips. This is a stress test, not a measurement of historical broker spreads. The inside-close alternative is negative even at the base spread.

## Separate later-period checks

Each two-year broker window starts with a new strategy and $10,000 account. At least the declared warmup counts are verified using preceding history (386 calendar days). No positions or setup state are inherited from a previous test window. Setup state reconstructed during warmup is retained at its start. Trades and floating positions at each boundary are recorded separately. These are retrospective checks: the recovery idea arose from an already-seen full-period subgroup, so the later windows are not untouched out-of-sample evidence. No parameters were optimized or selected within these windows.

July 2020 through June 2022

| Case | Trades | Win % | Net R | PF | R/trade | Closed DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| Current | 83 | 37.35 | +2.85 | 1.051 | +0.0343 | 10.10 | 4/7 |
| Recovery touch | 44 | 38.64 | +4.16 | 1.146 | +0.0946 | 7.44 | 3/7 |
| Recovery + inside close | 39 | 35.90 | +0.48 | 1.018 | +0.0123 | 8.14 | 3/7 |

July 2022 through June 2024

| Case | Trades | Win % | Net R | PF | R/trade | Closed DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| Current | 81 | 40.74 | +9.77 | 1.183 | +0.1206 | 8.08 | 4/6 |
| Recovery touch | 46 | 47.83 | +16.33 | 1.630 | +0.3550 | 5.31 | 3/5 |
| Recovery + inside close | 45 | 42.22 | +8.29 | 1.296 | +0.1843 | 6.57 | 3/5 |

July 2024 through June 2026

| Case | Trades | Win % | Net R | PF | R/trade | Closed DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| Current | 68 | 35.29 | -0.47 | 0.990 | -0.0069 | 11.31 | 3/10 |
| Recovery touch | 39 | 35.90 | +0.29 | 1.011 | +0.0074 | 9.86 | 3/9 |
| Recovery + inside close | 36 | 30.56 | -5.68 | 0.786 | -0.1578 | 9.87 | 2/9 |

Combined closed trades from the three separate windows

| Case | Trades | Win % | Net R | PF | R/trade | Closed DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| Current | 232 | 37.93 | +12.15 | 1.078 | +0.0524 | 11.31 | 4/10 |
| Recovery touch | 129 | 41.09 | +20.78 | 1.257 | +0.1611 | 9.86 | 3/9 |
| Recovery + inside close | 120 | 36.67 | +3.09 | 1.038 | +0.0258 | 12.46 | 3/9 |

Combined R and streaks concatenate closed outcomes in chronological order. Account balances reset for each fold; the individual growth percentages are not added or claimed as continuous portfolio growth.

| Window | Rule | Account growth | Equity DD | End exposure |
|---|---|---:|---:|---:|
| 2020–2022 | Current | +1.45% | 5.54% | 0 |
| 2020–2022 | Recovery touch | +2.13% | 4.12% | 0 |
| 2020–2022 | Recovery + inside close | +0.25% | 4.29% | 0 |
| 2022–2024 | Current | +4.50% | 4.68% | 0 |
| 2022–2024 | Recovery touch | +8.15% | 3.52% | 0 |
| 2022–2024 | Recovery + inside close | +3.94% | 3.52% | 0 |
| 2024–2026 | Current | -0.55% | 5.91% | 0 |
| 2024–2026 | Recovery touch | -0.11% | 5.04% | 0 |
| 2024–2026 | Recovery + inside close | -2.83% | 5.27% | 0 |

Broker continuous replay by entry/close period

| Case | Trades | Win % | Net R | PF | R/trade | Closed DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2017_2019 / Current | 134 | 35.82 | +1.30 | 1.014 | +0.0097 | 14.35 | 5/8 |
| 2017_2019 / Recovery touch | 57 | 31.58 | -6.40 | 0.844 | -0.1123 | 9.34 | 2/5 |
| 2017_2019 / Recovery + inside close | 51 | 31.37 | -6.18 | 0.832 | -0.1211 | 9.65 | 2/7 |
| 2020_2025 / Current | 245 | 36.73 | +4.77 | 1.028 | +0.0195 | 23.09 | 4/9 |
| 2020_2025 / Recovery touch | 136 | 40.44 | +19.53 | 1.227 | +0.1436 | 12.39 | 4/10 |
| 2020_2025 / Recovery + inside close | 128 | 36.72 | +3.86 | 1.045 | +0.0301 | 16.08 | 4/11 |
| 2026_to_july14 / Current | 18 | 33.33 | -1.12 | 0.912 | -0.0620 | 4.20 | 3/4 |
| 2026_to_july14 / Recovery touch | 12 | 41.67 | +2.21 | 1.298 | +0.1843 | 2.14 | 2/2 |
| 2026_to_july14 / Recovery + inside close | 11 | 36.36 | +0.18 | 1.025 | +0.0166 | 2.30 | 2/2 |

A trade enters these period totals only when both its entry and close are within that period. Cross-boundary trades remain in the full replay and need not sum into these subdivisions. This continuous replay differs from resetting each cold window.

Broker BUY/SELL, full base-spread replay

| Case | Trades | Win % | Net R | PF | R/trade | Closed DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| Current / BUY | 227 | 37.44 | +7.71 | 1.050 | +0.0340 | 13.37 | 5/8 |
| Current / SELL | 170 | 34.71 | -2.76 | 0.977 | -0.0162 | 17.68 | 3/9 |
| Recovery touch / BUY | 121 | 38.02 | +7.73 | 1.097 | +0.0639 | 7.68 | 3/5 |
| Recovery touch / SELL | 84 | 38.10 | +7.62 | 1.140 | +0.0907 | 12.79 | 4/7 |
| Recovery + inside close / BUY | 109 | 32.11 | -12.68 | 0.839 | -0.1163 | 14.98 | 3/7 |
| Recovery + inside close / SELL | 81 | 39.51 | +10.54 | 1.205 | +0.1301 | 11.78 | 4/7 |

## Why the original subgroup was too optimistic

The preceding review found 181 touched-extreme trades contributing +28.61R within the current broker trade list. Actual recovery-only replay yields 205 trades and +15.34R. Skipping other entries changes exposure, subsequent H1 biases and future opportunities. For the following comparison, matching requires the same originating setup, attempt, entry/close times, direction and entry/SL/TP prices; volume and tickets can differ after account paths diverge.

Current versus recovery-touch economic opportunity overlap

| Case | Trades | Win % | Net R | PF | R/trade | Closed DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| Common opportunities (recovery sizing) | 181 | 40.88 | +28.61 | 1.252 | +0.1581 | 8.79 | 4/8 |
| Only in current | 216 | 32.41 | -23.66 | 0.850 | -0.1095 | 36.38 | 7/10 |
| Only in recovery | 24 | 16.67 | -13.27 | 0.369 | -0.5527 | 13.27 | 2/8 |

## Validation and limitations

Completed 24 sequential research cases plus three extra plain-production controls. All three unchanged baselines match every trade field from the preceding review and all three observation baselines match plain production trades and ending exposure. Code, CSV and HistData metadata hashes match at completion. Every accepted order reconciles to a close, executable rejection or ending exposure; all closed recovery trades are attributed to qualifying contexts and retain the stop/R:R guards. Five focused recovery tests cover both directions, equality boundaries, no premature entry before fractal/FVG confirmation, filtered setup eligibility, proposal rejection and minimum-stop preservation. The complete 234-test suite passes.

HistData retains the previously documented 2023 provider gaps. Recent matching prices are nearly identical to Dukascopy and do not constitute an independent feed. Broker D1 session boundaries differ from UTC-midnight source bars. Swap, tick-level spread/slippage and portfolio competition can materially change these thin edges. The copied DEMO evidence predates the current corrections and was not used to tune these rules. No new MT5 connection was made.

## Decision

Keep GBPUSD DEMO unchanged as requested. Keep USDJPY Candle Confirmation retired from new runs, with magic number 1009 retained for existing-position reconciliation. USDJPY remains available to other strategies. Existing broker positions are not automatically closed by this configuration change.

Retain the touch-only rule for further research; do not promote the inside-close alternative on these results. Before changing GBPUSD DEMO logic, predefine one further hypothesis, validate it on later evidence not used in selecting it, and measure actual execution costs. The current study does not establish a robust replacement or justify higher risk.

The remote trading process still uses its loaded configuration until the updated code is committed/pushed, pulled on the host and the process is restarted. This task changes local code only; it performs no commit, push or host deployment.

## Reproduce

Use `.venv\Scripts\python.exe research_candle_gbpusd_recovery.py` in a fresh output directory (the runner refuses to overwrite an existing manifest), then `.venv\Scripts\python.exe summarize_candle_gbpusd_recovery.py`. Fixed definitions and original source hashes are recorded in `output/candle_gbpusd_recovery_20260930/manifest.json`; all per-case trades, contexts, controls, completion record and summary are retained there.
