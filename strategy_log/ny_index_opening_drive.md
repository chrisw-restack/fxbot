# NY Index Opening Drive

**Status:** RESEARCH — newly implemented, not validated, not in demo/live.
**File:** `strategies/ny_index_opening_drive.py`

## Concept

Trade USTEC/USA100 only during the NY cash-session opening window.

- Measure the first 30 minutes from 13:30 UTC.
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
- Opening window: `13:30-14:00 UTC`
- Entry cutoff: `16:00 UTC`
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
