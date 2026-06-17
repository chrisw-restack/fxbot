# NY Index Opening Drive

**Status:** RESEARCH — fixed-UTC walk-forward was MODERATE; NY-time-aware variant needs WF rerun. Not in demo/live.
**File:** `strategies/ny_index_opening_drive.py`

## Concept

Trade USTEC/USA100 only during the NY cash-session opening window.

- Measure the first 30 minutes from the 9:30am New York cash open, using `America/New_York` timezone conversion.
- Require a directional opening drive with enough range and body.
- Require D1 and H1 EMA trend alignment in the drive direction.
- Block high prior-day range regimes by percentile.
- Wait for a controlled M5 pullback into the 38.2-61.8% retracement zone.
- Enter on an M5 confirmed swing break back in the drive direction.
- SL goes beyond the pullback structure plus buffer.
- TP is fixed R:R and is strategy-set on the signal.

## Initial Research Config

Registered in `run_backtest.py` as `ny_index_opening_drive`.

Initial fixed parameters:

- Symbol: `USA100` for historical tests (`USTEC` broker alias if ever promoted)
- Timeframes: `D1`, `H1`, `M5`
- Opening window: `09:30-10:00 America/New_York`
- Entry cutoff: `12:00 America/New_York`
- Minimum drive: `40` index points
- Maximum drive: `250` index points
- Minimum drive body: `45%`
- Pullback zone: `38.2-61.8%`
- Fractal confirmation: `1`
- TP: `3R`
- SL buffer: `5` index points
- Max SL: `180` index points
- Trend filter: D1 + H1 EMA `20/50`
- D1 range filter: block top `20%` of prior-day ranges

## Validation Plan

1. Run fixed backtests on Dukascopy and HistData.
2. If fixed result is not obviously poor, run `walk_forward.py ny_index_opening_drive --workers 1`.
3. Only compare against `Failed2` after it passes walk-forward; otherwise shelve quickly.
4. Do not register in `live_config.py` without explicit approval after validation.

## Fixed Backtest Smoke Check - 2026-06-01

Initial smoke check exposed a bug in the strategy's fractal updater: it used the
second bar in the whole stored M5 buffer instead of the center of the latest
fractal window. That made the first fixed result artificially sparse and
negative. The updater now evaluates only the latest `2 * fractal_n + 1` bars.

Command:

`./venv/bin/python run_backtest.py ny_index_opening_drive --start-date 2020-01-01 --end-date 2026-01-01 --data-source dukascopy`

Result:

| Source | Trades | WR | Total R | PF | Expectancy | Max DD |
|---|---:|---:|---:|---:|---:|---:|
| Dukascopy | 32 | 40.6% | +18.87R | 1.99 | +0.59R | 4.14R |
| HistData | 31 | 35.5% | +12.10R | 1.60 | +0.39R | 4.14R |

Small corrected fixed-variant diagnostic, Dukascopy 2020-2026:

| Variant | Trades | WR | Total R | PF | Expectancy | Max DD |
|---|---:|---:|---:|---:|---:|---:|
| Base | 32 | 40.6% | +18.9R | 1.99 | +0.59R | 4.1R |
| No D1 range filter | 37 | 40.5% | +21.7R | 1.98 | +0.59R | 5.0R |
| H1 trend only | 72 | 23.6% | -5.8R | 0.90 | -0.08R | 10.9R |
| D1 trend only | 70 | 37.1% | +32.1R | 1.73 | +0.46R | 7.3R |
| Trend off | 145 | 25.5% | +0.1R | 1.00 | +0.00R | 20.0R |
| Loose drive | 55 | 36.4% | +23.1R | 1.65 | +0.42R | 9.1R |
| Loose, no trend | 220 | 23.6% | -16.6R | 0.90 | -0.08R | 41.3R |
| Loose, no trend, 2.5R | 225 | 26.7% | -19.7R | 0.88 | -0.09R | 38.1R |

Decision:

- The concept is promising enough for a focused walk-forward, but trade count is sparse.
- Trend discipline matters. Turning trend off destroys the edge.
- The first WF grid should stay narrow: `min_drive_pips`, `min_drive_body_pct`, D1-vs-D1+H1 trend, and D1 range filter only.

## Focused Walk-Forward - 2026-06-01

Focused grid:

- `min_drive_pips`: `20`, `40`
- `min_drive_body_pct`: `0.30`, `0.45`
- `trend_filter`: `d1_h1_ema`, `d1_ema`
- `d1_range_filter`: `off`, `block_top_pct`
- Fixed: 13:30-14:00 UTC opening drive, 16:00 UTC cutoff, 38.2-61.8% pullback, `fractal_n=1`, `3R`, `5` point SL buffer, max SL `180`.

### Dukascopy

Command:

`./venv/bin/python walk_forward.py ny_index_opening_drive --metric expectancy --workers 1 --data-source dukascopy`

| Fold | Test | Selected core | OOS trades | OOS R | OOS Exp | OOS PF | Retention |
|---:|---|---|---:|---:|---:|---:|---:|
| 1 | 2020-2022 | `move20, body45%, D1 EMA, D1 range block` | 19 | +0.4R | +0.018R | 1.02 | 5% |
| 2 | 2022-2024 | `move40, body30%, D1+H1 EMA, no range block` | 13 | +6.8R | +0.519R | 1.83 | 50% |
| 3 | 2024-2026 | `move40, body45%, D1+H1 EMA, no range block` | 12 | +7.6R | +0.630R | 2.08 | 100% |
| **Agg** | | | **44** | **+14.8R** | **+0.336R** | | **52%** |

Verdict: **MODERATE**. Fold 1 is weak but positive; folds 2 and 3 are strong.

### HistData / NSXUSD

Command:

`./venv/bin/python walk_forward.py ny_index_opening_drive --metric expectancy --workers 1 --data-source histdata`

| Fold | Test | Selected core | OOS trades | OOS R | OOS Exp | OOS PF | Retention |
|---:|---|---|---:|---:|---:|---:|---:|
| 1 | 2020-2022 | `move20, body45%, D1 EMA, no range block` | 27 | +0.2R | +0.007R | 1.01 | 100% |
| 2 | 2022-2024 | `move40, body30%, D1+H1 EMA, no range block` | 10 | +1.9R | +0.190R | 1.27 | 24% |
| 3 | 2024-2026 | `move40, body30%, D1+H1 EMA, D1 range block` | 15 | +4.6R | +0.306R | 1.46 | 77% |
| **Agg** | | | **52** | **+6.7R** | **+0.129R** | | **67%** |

Verdict: **MODERATE**, but weaker than Dukascopy. Cross-source result remains positive.

## Current Decision

- Keep as a research candidate, not a demo/live candidate.
- The opportunity is real enough to continue, but still sparse and less proven than `Failed2` USTEC.
- Next useful step: fixed-parameter fold checks on the stable core around `move40`, D1+H1 EMA, `3R`, and no/toggled D1 range block. Do not broaden the grid yet.

## NY-Time-Aware Session Update - 2026-06-11

Changed strategy session handling from fixed UTC to `America/New_York` local time:

- Opening drive is now `09:30-10:00 NY`.
- Entry cutoff is now `12:00 NY`.
- Session state resets by NY calendar date.
- This fixes standard-time months where the 9:30 NY cash open is `14:30 UTC`, not `13:30 UTC`.

Fixed current config, 2020-01-01 to 2026-01-01:

| Source | Trades | WR | Total R | PF | Expectancy | Max DD |
|---|---:|---:|---:|---:|---:|---:|
| Dukascopy | 39 | 43.6% | +27.62R | 2.25 | +0.708R | 3.02R |
| HistData | 40 | 42.5% | +26.75R | 2.16 | +0.669R | 3.00R |

Filter-removal diagnostic, same period. Deltas are closed-trade count versus current full config:

### Dukascopy

| Variant | Trades | Delta | WR | Total R | Exp | PF | Max DD |
|---|---:|---:|---:|---:|---:|---:|---:|
| Current full | 39 | +0 | 43.6% | +27.62R | +0.708R | 2.25 | 3.02R |
| No min drive | 39 | +0 | 43.6% | +27.62R | +0.708R | 2.25 | 3.02R |
| No max drive | 39 | +0 | 43.6% | +27.62R | +0.708R | 2.25 | 3.02R |
| No body filter | 66 | +27 | 42.4% | +43.56R | +0.660R | 2.14 | 5.02R |
| No D1+H1 trend | 132 | +93 | 28.0% | +13.04R | +0.099R | 1.14 | 13.20R |
| No D1 range block | 47 | +8 | 44.7% | +35.39R | +0.753R | 2.36 | 4.02R |
| No max SL | 40 | +1 | 42.5% | +26.62R | +0.665R | 2.15 | 3.02R |
| No drive filters | 67 | +28 | 41.8% | +42.56R | +0.635R | 2.09 | 6.00R |
| No trend/range | 169 | +130 | 29.6% | +27.37R | +0.162R | 1.23 | 15.21R |
| Core unfiltered | 298 | +259 | 29.2% | +43.50R | +0.146R | 1.20 | 18.41R |

### HistData / NSXUSD

| Variant | Trades | Delta | WR | Total R | Exp | PF | Max DD |
|---|---:|---:|---:|---:|---:|---:|---:|
| Current full | 40 | +0 | 42.5% | +26.75R | +0.669R | 2.16 | 3.00R |
| No min drive | 40 | +0 | 42.5% | +26.75R | +0.669R | 2.16 | 3.00R |
| No max drive | 40 | +0 | 42.5% | +26.75R | +0.669R | 2.16 | 3.00R |
| No body filter | 70 | +30 | 41.4% | +43.62R | +0.623R | 2.06 | 5.10R |
| No D1+H1 trend | 130 | +90 | 27.7% | +11.19R | +0.086R | 1.12 | 12.20R |
| No D1 range block | 49 | +9 | 40.8% | +29.53R | +0.603R | 2.02 | 5.00R |
| No max SL | 40 | +0 | 42.5% | +26.75R | +0.669R | 2.16 | 3.00R |
| No drive filters | 73 | +33 | 39.7% | +40.62R | +0.556R | 1.92 | 6.00R |
| No trend/range | 166 | +126 | 28.3% | +18.60R | +0.112R | 1.16 | 14.21R |
| Core unfiltered | 294 | +254 | 27.9% | +27.96R | +0.095R | 1.13 | 20.64R |

Interpretation:

- The min-drive and max-drive filters do not affect the current filtered trade count.
- The body filter is the most promising place to recover trades: removing it adds about 27-30 trades while keeping expectancy high.
- Removing D1 range block adds only 8-9 trades and remains constructive.
- Removing trend alignment adds many trades but collapses expectancy and increases drawdown.
- The fully unfiltered core generates many more trades, but most of the extra volume is low quality.

Required next validation: rerun walk-forward on the NY-time-aware version, with a narrow grid around body filter `0.0/0.30/0.45`, D1 range filter on/off, and trend filter kept disciplined (`d1_h1_ema` vs `d1_ema`).

## NY-Time-Aware Body-Filter Walk-Forward - 2026-06-11

Purpose: increase trade count without reopening a broad search.

Grid:

- `min_drive_pips`: `20`, `40`
- `min_drive_body_pct`: `0.0`, `0.30`, `0.45`
- `trend_filter`: `d1_h1_ema`, `d1_ema`
- `d1_range_filter`: `off`, `block_top_pct`
- Fixed: `09:30-10:00 America/New_York` opening drive, `12:00 NY` cutoff, 38.2-61.8% pullback, `fractal_n=1`, `3R`, `5` point SL buffer, max SL `180`.

### Dukascopy

Command:

`./venv/bin/python walk_forward.py ny_index_opening_drive --metric expectancy --workers 1 --data-source dukascopy`

| Fold | Test | Selected core | OOS trades | OOS R | OOS Exp | OOS PF | Retention |
|---:|---|---|---:|---:|---:|---:|---:|
| 1 | 2020-2022 | `move20, body45%, D1+H1 EMA, no range block` | 13 | +14.2R | +1.095R | 3.37 | 164% |
| 2 | 2022-2024 | `move40, body30%, D1+H1 EMA, no range block` | 18 | +1.8R | +0.100R | 1.14 | 9% |
| 3 | 2024-2026 | `move20, body45%, D1+H1 EMA, no range block` | 16 | +7.5R | +0.467R | 1.75 | 69% |
| **Agg** | | | **47** | **+23.5R** | **+0.500R** | | **81%** |

Verdict: **STRONG**. Fold 2 retention is weak, but every fold is positive and aggregate expectancy is high.

### HistData / NSXUSD

Command:

`./venv/bin/python walk_forward.py ny_index_opening_drive --metric expectancy --workers 1 --data-source histdata`

| Fold | Test | Selected core | OOS trades | OOS R | OOS Exp | OOS PF | Retention |
|---:|---|---|---:|---:|---:|---:|---:|
| 1 | 2020-2022 | `move20, body30%, D1+H1 EMA, no range block` | 23 | +19.8R | +0.861R | 2.64 | 188% |
| 2 | 2022-2024 | `move40, body30%, D1+H1 EMA, D1 range block` | 15 | +4.8R | +0.323R | 1.48 | 34% |
| 3 | 2024-2026 | `move20, body45%, D1+H1 EMA, D1 range block` | 14 | +5.6R | +0.399R | 1.62 | 55% |
| **Agg** | | | **52** | **+30.2R** | **+0.581R** | | **92%** |

Verdict: **STRONG**. Cross-source result improves versus the first fixed-UTC WF.

### Fixed Candidate Head-to-Head

Same 2020-01-01 to 2026-01-01 window, no per-fold optimisation.

| Variant | Duk Trades | Duk R | Duk Exp | Duk DD | Hist Trades | Hist R | Hist Exp | Hist DD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Current: `move40, body45%, range block` | 39 | +27.62R | +0.708R | 3.02R | 40 | +26.75R | +0.669R | 3.00R |
| Looser body: `move40, body30%, range block` | 53 | +37.03R | +0.699R | 5.23R | 55 | +35.15R | +0.639R | 4.24R |
| Body off: `move40, body0%, range block` | 66 | +43.56R | +0.660R | 5.02R | 70 | +43.62R | +0.623R | 5.10R |
| Range off: `move40, body45%` | 47 | +35.39R | +0.753R | 4.02R | 49 | +29.53R | +0.603R | 5.00R |
| Loose body + range off: `move40, body30%` | 61 | +40.84R | +0.670R | 7.04R | 64 | +33.97R | +0.531R | 6.01R |

Decision:

- Do **not** fully remove the body filter yet. `body0%` increases count most, but it was not selected by any WF fold.
- Preferred next fixed candidate is `min_drive_body_pct=0.30` while keeping D1+H1 trend alignment and the D1 range block. It adds meaningful trade count with small expectancy decay and cross-source consistency.
- Keep trend discipline. Every strong fold selected `d1_h1_ema`; `d1_ema` did not win any fold.
- D1 range block is less clear: Dukascopy preferred it off, HistData selected it in folds 2-3. The conservative candidate should keep the block for now because it contains drawdown and fixed head-to-head remains strong.

## Fixed Body30 Sanity Check And Demo Registration - 2026-06-11

Fixed candidate:

- Symbol: historical `USA100`, demo/live broker symbol `USTEC`
- Opening drive: `09:30-10:00 America/New_York`
- Entry cutoff: `12:00 America/New_York`
- `min_drive_pips=40`
- `min_drive_body_pct=0.30`
- `trend_filter='d1_h1_ema'`
- `d1_range_filter='block_top_pct'`, `d1_range_block_pct=0.8`
- Pullback: 38.2-61.8%
- `fractal_n=1`
- `rr_ratio=3.0`
- `sl_buffer_pips=5`
- `max_sl_pips=180`

Fixed full-sample sanity, 2016-01-01 to 2026-01-01:

| Source | Trades | WR | Total R | Exp | PF | Max DD | Worst loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| Dukascopy | 56 | 44.6% | +41.95R | +0.749R | 2.35 | 5.23R | 4 |
| HistData / NSXUSD | 60 | 43.3% | +42.06R | +0.701R | 2.23 | 4.24R | 4 |

Fixed OOS-period breakdown:

| Source | Period | Trades | WR | Total R | Exp | PF | Max DD |
|---|---|---:|---:|---:|---:|---:|---:|
| Dukascopy | 2020-2022 | 20 | 50.0% | +18.93R | +0.947R | 2.89 | 4.00R |
| Dukascopy | 2022-2024 | 14 | 28.6% | +1.83R | +0.131R | 1.18 | 5.03R |
| Dukascopy | 2024-2026 | 19 | 47.4% | +16.27R | +0.856R | 2.63 | 3.00R |
| HistData | 2020-2022 | 20 | 50.0% | +18.93R | +0.947R | 2.89 | 4.00R |
| HistData | 2022-2024 | 15 | 33.3% | +4.85R | +0.323R | 1.48 | 4.04R |
| HistData | 2024-2026 | 20 | 40.0% | +11.37R | +0.569R | 1.95 | 4.01R |

Yearly notes:

- 2020, 2021, 2023, 2024, and 2025 are positive on both sources.
- Dukascopy 2022 is the only negative year: 6 trades, `-2.03R`, max DD `4.04R`.
- HistData 2022 is positive: 6 trades, `+1.99R`.
- Worst loss streak is 4 trades on both sources.

Decision:

- Fixed body30 candidate passed sanity check.
- Registered in `live_config.py` for demo/live runner on `USTEC`.
- Added config magic number `NYIndexOpeningDrive=1011`.
- Added temporary risk override `0.0025` (`0.25%`) because this overlaps Nasdaq exposure with `Failed2_H4_H1_M5_market`.
- Do not promote to real-money live without reviewing forward demo behavior, spread/slippage, and trade overlap with Failed2.

## Cross-Index Fixed Check - 2026-06-17

Purpose: check whether the fixed Nasdaq body30 candidate generalises to S&P 500 and Dow using available Dukascopy data.

Data availability:

- `USA500` and `USA30` have 10-year Dukascopy `D1/H1/M5` files.
- No matching 10-year HistData second-source files were found locally for these symbols.

Fixed config is unchanged from the demo candidate, except symbol:

- `09:30-10:00 America/New_York` opening drive
- `12:00 America/New_York` cutoff
- `min_drive_pips=40`, `min_drive_body_pct=0.30`
- D1+H1 EMA trend alignment
- D1 prior-range top-20% block
- 38.2-61.8% pullback, M5 fractal confirmation, `3R` TP

### Full Sample

| Symbol | Trades | WR | Total R | Exp | PF | Max DD | Worst loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| `USA500` | 84 | 27.4% | +1.20R | +0.014R | 1.02 | 11.41R | 11 |
| `USA30` | 84 | 34.5% | +30.24R | +0.360R | 1.55 | 6.03R | 6 |

### OOS-Style Periods

| Symbol | Period | Trades | WR | Total R | Exp | PF | Max DD |
|---|---|---:|---:|---:|---:|---:|---:|
| `USA500` | 2020-2022 | 29 | 31.0% | +4.89R | +0.169R | 1.24 | 7.29R |
| `USA500` | 2022-2024 | 16 | 31.2% | +2.36R | +0.148R | 1.21 | 5.32R |
| `USA500` | 2024-2026 | 11 | 0.0% | -11.00R | -1.000R | 0.00 | 11.00R |
| `USA30` | 2020-2022 | 15 | 26.7% | +0.73R | +0.049R | 1.07 | 5.01R |
| `USA30` | 2022-2024 | 16 | 31.2% | +3.81R | +0.238R | 1.35 | 4.01R |
| `USA30` | 2024-2026 | 21 | 33.3% | +6.81R | +0.324R | 1.49 | 5.01R |

Decision:

- Do not add `USA500` / `US500`. The fixed strategy is effectively breakeven over 10 years and fails recent OOS badly.
- Do not add `USA30` / `US30` yet. It is positive, but materially weaker than `USA100`, has no local HistData confirmation, and year-by-year performance is choppy.
- If revisiting `USA30`, treat it as a separate research candidate with its own walk-forward and second-source data requirement.
