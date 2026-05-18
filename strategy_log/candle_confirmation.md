# Candle Confirmation

## Status

USDJPY and GBPUSD demo candidates. USDJPY walk-forward validation is MODERATE for the fixed conservative candidate. GBPUSD fixed D1 candidate is positive in all three OOS folds and added to demo/live config on 2026-05-15.

## Concept

Use an H1 engulfing candle as directional bias, wait for price to retrace into 50% of that candle's range, then enter from M5 confirmation in the engulfing direction.

Default bullish rules:

- HTF engulf: current H1 close is above the previous H1 candle body high.
- Pre-entry invalidation: any M5 wick reaches the engulfing H1 high before entry.
- Retrace trigger: M5 low trades to or below the H1 candle midpoint.
- Entry trigger: M5 close breaks above a confirmed fractal swing high.
- Confirmation: the M5 breaking leg contains a bullish FVG.
- TP: H1 engulfing high.
- SL: symmetric 1:1 from entry to TP.

Bearish rules are mirrored.

## Default Config

- Strategy key: `candle_confirmation`
- Timeframes: `H1/M5`
- `fractal_n=2`
- `retrace_pct=0.5`
- `tp_range_pct=1.0`
- `sl_rr_ratio=1.0`
- `sl_mode='symmetric'`
- `require_fvg=True`
- `blocked_hours=()`

## Sweep Plan

Run `python sweep_candle_confirmation.py` and compare:

- `fractal_n`: 1, 2, 3, 4
- `retrace_pct`: 0.382, 0.5, 0.618
- `tp_range_pct`: 0.75, 0.875, 1.0
- `sl_mode`: symmetric, mss_bar, structural
- Session presets: none, London/NY, NY-only, block Asia/rollover

Report trades, win rate, total R, profit factor, expectancy, max drawdown R, and worst loss streak.

## Verdict

Baseline default config failed on all available major FX Dukascopy data. Do not promote.

Latest filter sweep found one barely positive USDJPY configuration, but the edge is too thin to validate:
`D1 EMA 20/50`, minimum EMA separation `0.0005`, minimum H1 engulf range `8` pips, minimum H1 body `50%`, no candle-color requirement. Result was only `+2.36R` over `781` trades, PF `1.01`, expectancy `+0.003R`, max DD `32.02R`. Treat as research only; next step should be a narrower follow-up sweep or walk-forward check before changing the strategy verdict.

TP/SL sweep on the same USDJPY filter found a materially better in-sample pocket:
`tp_range_pct=1.25`, `sl_mode='symmetric'`, `sl_rr_ratio=1.5`, `min_sl_pips=5`. Result was `+70.6R` over `899` trades, PF `1.14`, expectancy `+0.079R`, max DD `32.5R`. This is promising enough for walk-forward, but not validated.

Walk-forward validation of the conservative USDJPY TP/SL pocket passed. The optimized conservative family scored MODERATE with `+46.7R` aggregate OOS, `+0.135R` OOS expectancy, and `69%` average retention. Fixed-parameter checks were also positive in every fold; the best fixed variant was `tp_range_pct=1.25`, `sl_rr_ratio=1.5`, `min_sl_pips=8`, with `+54.0R` aggregate OOS and `+0.144R` expectancy.

Live/demo status: registered for `USDJPY` and `GBPUSD` only using fixed candidates. Do not add other pairs without separate walk-forward validation.

## Backtest History

### 2026-05-12 - Default H1/M5, major FX, all available Dukascopy data

Command:

`python run_backtest.py candle_confirmation --symbols EURUSD GBPUSD AUDUSD NZDUSD USDJPY USDCAD USDCHF`

Result:

| Trades | Win rate | Total R | PF | Expectancy | Max DD | Worst loss streak |
|---:|---:|---:|---:|---:|---:|---:|
| 9,668 | 47.7% | -694.69R | 0.86 | -0.07R | 695.68R | 13 |

Notes:

- Data covered 2016-01-04 to 2026-03-19 from local Dukascopy files.
- The default 1:1 symmetric SL/TP version is overactive and unprofitable before filtering.
- Commission and spread drag are material because the strategy takes many short-duration M5 trades.
- Next research should focus on session filtering, fewer signals, and possibly structural SL/partial TP variants before any walk-forward attempt.

### 2026-05-12 - H1/M5 parameter sweep, major FX, all available Dukascopy data

Command:

`python sweep_candle_confirmation.py`

Grid:

- `fractal_n`: 1, 2, 3, 4
- `retrace_pct`: 0.382, 0.5, 0.618
- `tp_range_pct`: 0.75, 0.875, 1.0
- `sl_mode`: symmetric, mss_bar, structural
- `session`: none, London/NY, NY-only, block Asia/rollover

Result:

| Filter | Best config | Trades | Win rate | Total R | PF | Expectancy | Max DD |
|---|---|---:|---:|---:|---:|---:|---:|
| All combos | `fractal_n=1, retrace=0.618, tp=0.750, sl=mss_bar, session=ny_only` | 6 | 50.0% | +3.7R | 2.20 | +0.613R | 2.0R |
| Min 30 trades | `fractal_n=3, retrace=0.382, tp=0.750, sl=symmetric, session=london_ny` | 1,229 | 50.0% | -35.8R | 0.94 | -0.029R | 46.1R |

Session impact, min 30 trades:

| Session | Avg expectancy | Best expectancy |
|---|---:|---:|
| none | -0.067R | -0.032R |
| London/NY | -0.065R | -0.029R |
| NY-only | -0.077R | -0.038R |
| block Asia/rollover | -0.069R | -0.030R |

Notes:

- 335 combinations produced closed trades.
- Positive total-R configs were all too small to trust, typically 1-9 trades.
- Every configuration with at least 30 trades was negative.
- Current H1/M5 version has no robust edge on major FX. Do not walk-forward or promote without a materially different filter/entry model.

### 2026-05-13 - Per-symbol baseline diagnostic, major FX, all available Dukascopy data

Command:

`python run_backtest.py candle_confirmation --symbols <SYMBOL>`

Config:

- `tf_bias='H1'`, `tf_entry='M5'`
- `fractal_n=2`, `retrace_pct=0.5`, `tp_range_pct=1.0`
- `sl_mode='symmetric'`, `require_fvg=True`
- No session, trend, or engulf-quality filters

Result:

| Symbol | Trades | Win rate | Total R | PF | Expectancy | Max DD R | Best/Worst streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| EURUSD | 1,496 | 46.7% | -117.10R | 0.85 | -0.078R | 120.61R | 8/11 |
| GBPUSD | 1,832 | 45.7% | -191.92R | 0.81 | -0.105R | 195.18R | 7/12 |
| AUDUSD | 1,355 | 48.9% | -64.79R | 0.91 | -0.048R | 70.68R | 11/16 |
| NZDUSD | 1,285 | 47.7% | -157.88R | 0.77 | -0.123R | 159.06R | 8/12 |
| USDJPY | 1,931 | 48.6% | -57.89R | 0.94 | -0.030R | 78.00R | 9/8 |
| USDCAD | 1,613 | 48.9% | -91.34R | 0.89 | -0.057R | 108.08R | 10/8 |
| USDCHF | 156 | 46.2% | -13.77R | 0.84 | -0.088R | 20.83R | 9/9 |

Notes:

- USDJPY was the best meaningful candidate by PF and expectancy over a full sample.
- USDCHF had the smallest total R loss, but only 156 trades because available data stopped in 2017, so it was not selected for follow-up.

### 2026-05-13 - USDJPY EMA bias and H1 engulf-quality sweep

Implementation added optional strategy parameters for research:

- `tf_trend`: `None`, `H4`, or `D1`
- `ema_fast=20`, `ema_slow=50`, `ema_sep_pct`
- `min_engulf_range_pips`
- `min_engulf_body_pct`
- `close_extreme_pct`
- `require_engulf_color`

Grid:

- Trend: off, H4 EMA 20/50, D1 EMA 20/50
- EMA separation: `0.0`, `0.0005`, `0.001`, `0.0015`
- Minimum H1 engulf range: `0`, `8`, `12` pips
- Minimum H1 body: `0%`, `50%`, `60%`, `70%`
- Close extreme: off (`1.0`) or top/bottom `25%`
- Require candle color: `False`, `True`

Top result:

| Trend | Range | Body | ClosePct | Color | Trades | Win rate | Total R | PF | Expectancy | Max DD | Loss streak |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| D1 EMA 20/50 sep 0.0005 | 8 | 50% | 1.00 | False | 781 | 48.7% | +2.36R | 1.01 | +0.003R | 32.02R | 12 |

Notes:

- The filters meaningfully reduced losses versus the USDJPY baseline (`-57.89R` to `+2.36R`), but the best edge is very thin.
- D1 EMA alignment dominated the top results; H4 EMA did not appear in the top 10 by total R.
- Requiring the engulf candle to close in the top/bottom 25% did not appear in the top results.
- Requiring candle color generally hurt results in this grid.
- This is not strong enough for promotion. A follow-up should test the best D1 filter on walk-forward and then separately test entry-trigger improvements or TP model changes.

### 2026-05-13 - USDJPY TP/SL sweep on best EMA/quality filter

Implementation added `sl_rr_ratio` for the symmetric SL mode:

- `sl_rr_ratio=1.0`: original 1:1 distance to the selected TP level.
- `sl_rr_ratio=1.5`: SL distance is TP distance / 1.5.
- `sl_rr_ratio=2.0`: SL distance is TP distance / 2.0.

Fixed filter:

- Symbol: `USDJPY`
- `tf_bias='H1'`, `tf_entry='M5'`
- `D1 EMA 20/50`, `ema_sep_pct=0.0005`
- Minimum H1 engulf range: `8` pips
- Minimum H1 engulf body: `50%`
- Close-extreme filter disabled
- Candle color not required

Grid:

- `tp_range_pct`: `0.75`, `1.0`, `1.25`, `1.5`, `2.0`
- `sl_mode`: `symmetric`, `mss_bar`, `structural`
- `sl_rr_ratio`: `1.0`, `1.25`, `1.5`, `2.0`
- `min_sl_pips`: `5`, `8`, `10`, `12`

Top results by total R:

| TP pct | SL mode | SL RR | Min SL | Trades | Win rate | Total R | PF | Expectancy | Max DD | Loss streak |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1.25 | symmetric | 1.50 | 5 | 899 | 42.8% | +70.6R | 1.14 | +0.079R | 32.5R | 12 |
| 1.25 | symmetric | 1.50 | 8 | 633 | 43.3% | +69.6R | 1.19 | +0.110R | 22.9R | 13 |
| 1.25 | symmetric | 1.50 | 10 | 488 | 45.1% | +56.2R | 1.21 | +0.115R | 16.8R | 11 |
| 1.25 | symmetric | 1.25 | 12 | 487 | 49.3% | +49.0R | 1.20 | +0.101R | 14.9R | 10 |
| 1.25 | symmetric | 1.25 | 10 | 602 | 46.8% | +33.3R | 1.10 | +0.055R | 16.5R | 10 |

Impact summary:

| Group | Avg expectancy | Best expectancy |
|---|---:|---:|
| TP 0.75 | -0.109R | +0.047R |
| TP 1.00 | -0.052R | +0.046R |
| TP 1.25 | +0.043R | +0.115R |
| TP 1.50 | +0.017R | +0.043R |
| TP 2.00 | +0.026R | +0.197R |
| Symmetric SL | -0.016R | +0.115R |
| MSS-bar SL | +0.096R | +0.197R |
| Structural SL | -0.033R | +0.081R |

Notes:

- Best total-R result uses TP beyond the engulfing extreme (`1.25x` H1 engulf range) and a tighter symmetric SL (`1.5R` geometry).
- `min_sl_pips=8` and `10` reduce drawdown and improve expectancy, but give up total R.
- MSS-bar SL had the best average expectancy, but top configs had few trades and large loss streaks; treat as less robust until walk-forward tested.
- Next step: walk-forward the top 3-5 configs on USDJPY before considering broader symbols or live/demo discussion.

### 2026-05-13 - USDJPY conservative TP/SL walk-forward validation

Command:

`./venv/bin/python -u walk_forward.py candle_confirmation_usdjpy_wf --workers 1`

Walk-forward setup:

- Symbol: `USDJPY`
- Folds: 4-year train, 2-year test, 2-year step
- Optimization metric: expectancy
- Conservative candidate grid only:
  - `tp_range_pct=1.25`
  - `sl_mode='symmetric'`
  - `sl_rr_ratio`: `1.25`, `1.5`
  - `min_sl_pips`: `8`, `10`, `12`
- Fixed filter:
  - `D1 EMA 20/50`, `ema_sep_pct=0.0005`
  - H1 engulf range >= `8` pips
  - H1 engulf body >= `50%`
  - Close-extreme filter disabled
  - Candle color not required

Optimized-family WF result:

| Fold | Test period | Best params | IS R | OOS R | IS Exp | OOS Exp | OOS WR | OOS PF | Retention |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 2020-2022 | `sl_rr=1.5, min_sl=10` | +29.7R | +6.8R | +0.189R | +0.136R | 46.0% | 1.25 | 72% |
| 2 | 2022-2024 | `sl_rr=1.5, min_sl=8` | +29.3R | +32.6R | +0.189R | +0.193R | 42.0% | 1.33 | 102% |
| 3 | 2024-2026 | `sl_rr=1.5, min_sl=8` | +45.6R | +7.3R | +0.178R | +0.057R | 43.0% | 1.10 | 32% |

Aggregate:

| OOS trades | OOS R | OOS expectancy | Avg retention | Verdict |
|---:|---:|---:|---:|---|
| 347 | +46.7R | +0.135R | 69% | MODERATE |

Fixed-variant checks:

| Candidate | OOS trades | OOS R | OOS expectancy | Avg retention |
|---|---:|---:|---:|---:|
| `sl_rr=1.5, min_sl=8` | 374 | +54.0R | +0.144R | 140% |
| `sl_rr=1.5, min_sl=10` | 298 | +27.4R | +0.092R | 77% |
| `sl_rr=1.25, min_sl=12` | 298 | +26.9R | +0.090R | 197% |

Notes:

- Every fixed conservative variant was OOS-positive in all three folds.
- `sl_rr=1.5, min_sl=8` is the best balance of trade count, total R, and OOS expectancy.
- The 2024-2026 OOS fold retained less edge for the optimized-family run, so this should be treated as MODERATE, not STRONG.
- Next step: test this exact fixed candidate on HistData if available for USDJPY H1/M5/D1, then consider a small robustness check around sessions or entry trigger.

### 2026-05-13 - Best USDJPY fixed candidate on other FX majors

Command:

Inline single-symbol backtests using the fixed best candidate:

- `tp_range_pct=1.25`
- `sl_mode='symmetric'`
- `sl_rr_ratio=1.5`
- `min_sl_pips=8`
- `D1 EMA 20/50`, `ema_sep_pct=0.0005`
- H1 engulf range >= `8` pips
- H1 engulf body >= `50%`
- Close-extreme filter disabled
- Candle color not required

Result:

| Symbol | Data end | Trades | Win rate | Total R | PF | Expectancy | Max DD | Best/Worst streak |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| EURUSD | 2026-03-19 | 463 | 35.0% | -63.1R | 0.79 | -0.136R | 63.1R | 8/11 |
| GBPUSD | 2026-03-19 | 641 | 39.3% | -20.0R | 0.95 | -0.031R | 59.4R | 9/15 |
| AUDUSD | 2026-03-19 | 440 | 36.1% | -49.6R | 0.83 | -0.113R | 49.8R | 7/12 |
| NZDUSD | 2026-03-19 | 377 | 37.9% | -40.2R | 0.83 | -0.107R | 63.6R | 6/11 |
| USDJPY | 2026-03-19 | 633 | 43.3% | +69.6R | 1.19 | +0.110R | 22.9R | 9/13 |
| USDCAD | 2026-03-19 | 457 | 36.3% | -52.4R | 0.82 | -0.115R | 64.7R | 5/13 |
| USDCHF | 2026-03-19 | 401 | 41.9% | +16.9R | 1.07 | +0.042R | 16.3R | 8/9 |

Notes:

- The USDJPY candidate does not transfer cleanly to most other majors.
- USDCHF is the only other positive pair on the same fixed settings, but the edge is much weaker than USDJPY.
- GBPUSD is closest among the losers, but still negative and drawdown-heavy.
- Do not broaden the strategy to all majors. If expanding beyond USDJPY, USDCHF should be walk-forward tested separately first.

### 2026-05-14 - EURUSD broad parameter sweep

Command:

`./venv/bin/python -u sweep_candle_confirmation_eurusd.py`

Results written to:

`output/candle_confirmation_eurusd_sweep.csv`

Grid:

- Symbol: `EURUSD`
- Fixed: `H1/M5`, `retrace_pct=0.5`, `require_fvg=True`, `sl_mode='symmetric'`, no session filter
- `fractal_n`: `1`, `2`, `3`
- `tf_trend`: off, `H4`, `D1`
- EMA pairs for trend branches: `10/20`, `20/50`
- `ema_sep_pct`: `0.0`, `0.0005`, `0.001`
- `min_engulf_range_pips`: `8`, `12`, `15`
- `min_engulf_body_pct`: `0.4`, `0.5`, `0.6`
- `tp_range_pct`: `1.0`, `1.25`, `1.5`
- `sl_rr_ratio`: `1.25`, `1.5`, `2.0`
- `min_sl_pips`: `8`, `10`, `12`

Total combinations:

- `9,477` non-redundant combinations.

Top results by total R:

| Fractal | Trend | EMA | Sep | Range | Body | TP | SL RR | Min SL | Trades | WR | Total R | PF | Exp | Max DD |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | D1 | 10/20 | 0.0000 | 8 | 0.4 | 1.25 | 2.00 | 10 | 338 | 38.2% | +48.0R | 1.23 | +0.142R | 12.4R |
| 1 | D1 | 10/20 | 0.0005 | 8 | 0.4 | 1.25 | 2.00 | 10 | 308 | 38.3% | +45.0R | 1.24 | +0.146R | 11.1R |
| 1 | D1 | 10/20 | 0.0005 | 12 | 0.4 | 1.25 | 2.00 | 10 | 395 | 37.0% | +41.3R | 1.17 | +0.105R | 12.1R |
| 1 | D1 | 10/20 | 0.0000 | 12 | 0.4 | 1.25 | 2.00 | 10 | 432 | 36.6% | +40.3R | 1.15 | +0.093R | 13.1R |
| 1 | off | - | 0.0000 | 15 | 0.6 | 1.00 | 2.00 | 12 | 307 | 37.5% | +35.4R | 1.18 | +0.115R | 19.0R |

Top expectancy result with at least 100 trades:

| Fractal | Trend | EMA | Sep | Range | Body | TP | SL RR | Min SL | Trades | WR | Total R | PF | Exp | Max DD |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | H4 | 10/20 | 0.0005 | 15 | 0.5 | 1.00 | 2.00 | 12 | 129 | 39.5% | +22.6R | 1.29 | +0.175R | 9.0R |

Notes:

- EURUSD does have profitable in-sample pockets, unlike the direct USDJPY-param transfer.
- The best total-R cluster favors `fractal_n=1`, D1 EMA `10/20`, TP `1.25`, SL RR `2.0`, and looser body filter `0.4`.
- D1 trend filtering improved total R materially; H4 produced the best expectancy row but with fewer trades.
- This is in-sample only. Do not promote EURUSD without a walk-forward validation on the top D1/H4 candidate families.

### 2026-05-14 - EURUSD walk-forward validation

Command:

`./venv/bin/python -u walk_forward.py candle_confirmation_eurusd_wf --workers 1`

Optimized-family WF setup:

- Symbol: `EURUSD`
- Folds: 4-year train, 2-year test, 2-year step
- Optimization metric: expectancy
- Candidate family around sweep winners:
  - `fractal_n`: `1`, `3`
  - `tf_trend`: `D1`, `H4`
  - EMA: `10/20`, `20/50`
  - `ema_sep_pct`: `0`, `0.0005`, `0.001`
  - `min_engulf_range_pips`: `8`, `12`, `15`
  - `min_engulf_body_pct`: `0.4`, `0.5`
  - `tp_range_pct`: `1.0`, `1.25`
  - `sl_rr_ratio`: `1.5`, `2.0`
  - `min_sl_pips`: `10`, `12`

Optimized-family result:

| Fold | Test period | Best params summary | IS R | OOS R | IS Exp | OOS Exp | OOS WR | OOS PF | Retention |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 2019-2021 | `fn=3, H4 10/20 sep .001, range 8, body .4, tp 1.25, slrr 1.5, minSL 12` | +12.3R | +3.7R | +0.409R | +0.175R | 47.6% | 1.33 | 43% |
| 2 | 2021-2023 | `fn=3, H4 20/50 sep .0005, range 8, body .4, tp 1.25, slrr 2.0, minSL 10` | +23.5R | -2.0R | +0.490R | -0.069R | 31.0% | 0.90 | -14% |
| 3 | 2023-2025 | `fn=1, H4 10/20 sep .0005, range 8, body .5, tp 1.0, slrr 2.0, minSL 12` | +11.5R | -5.1R | +0.348R | -0.463R | 18.2% | 0.44 | -133% |

Aggregate optimized-family result:

| OOS trades | OOS R | OOS expectancy | Avg retention | Verdict |
|---:|---:|---:|---:|---|
| 61 | -3.4R | -0.056R | -35% | FAIL |

Fixed D1 candidate checks:

| Candidate | OOS trades | OOS R | OOS expectancy | Avg retention |
|---|---:|---:|---:|---:|
| `D1 10/20 sep0, range8, body0.4, tp1.25, slrr2, minSL10` | 185 | +41.3R | +0.223R | 119% |
| `D1 10/20 sep0.0005, range8, body0.4, tp1.25, slrr2, minSL10` | 172 | +30.2R | +0.176R | 61% |
| `D1 10/20 sep0.0005, range12, body0.4, tp1.25, slrr2, minSL10` | 225 | +30.9R | +0.137R | 116% |
| `D1 10/20 sep0, range12, body0.4, tp1.25, slrr2, minSL10` | 241 | +41.9R | +0.174R | 474% |

Fixed-candidate fold detail:

| Candidate | Fold 1 OOS | Fold 2 OOS | Fold 3 OOS |
|---|---:|---:|---:|
| `sep0, range8` | +17.2R | +28.5R | -4.4R |
| `sep0.0005, range8` | +11.2R | +22.4R | -3.4R |
| `sep0.0005, range12` | +12.1R | +22.3R | -3.5R |
| `sep0, range12` | +16.1R | +30.3R | -4.5R |

Notes:

- EURUSD fixed D1 candidates are aggregate OOS-positive, but every fixed candidate failed the most recent full OOS fold (`2023-2025`).
- The optimized-family WF failed outright because it selected sparse H4 high-expectancy configs that did not generalize.
- EURUSD is not ready for demo/live. It may be worth further research, but the next step should focus on why the 2023-2025 fold fails before adding it to the suite.

### 2026-05-14 - GBPUSD broad parameter sweep

Command:

`./venv/bin/python -u sweep_candle_confirmation_eurusd.py --symbol GBPUSD`

Results written to:

`output/candle_confirmation_gbpusd_sweep.csv`

Grid:

- Same broad grid as EURUSD: `9,477` non-redundant combinations.

Top results by total R:

| Fractal | Trend | EMA | Sep | Range | Body | TP | SL RR | Min SL | Trades | WR | Total R | PF | Exp | Max DD |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3 | D1 | 20/50 | 0.0010 | 8 | 0.6 | 1.50 | 2.00 | 8 | 426 | 39.2% | +68.3R | 1.26 | +0.160R | 17.5R |
| 3 | D1 | 20/50 | 0.0005 | 8 | 0.6 | 1.50 | 2.00 | 8 | 440 | 38.4% | +60.1R | 1.22 | +0.137R | 17.6R |
| 3 | H4 | 10/20 | 0.0005 | 8 | 0.5 | 1.50 | 2.00 | 8 | 440 | 38.4% | +59.5R | 1.22 | +0.135R | 18.7R |
| 3 | D1 | 20/50 | 0.0000 | 8 | 0.6 | 1.50 | 2.00 | 8 | 458 | 38.0% | +56.8R | 1.20 | +0.124R | 18.6R |
| 3 | H4 | 10/20 | 0.0005 | 12 | 0.5 | 1.50 | 2.00 | 8 | 500 | 37.6% | +55.8R | 1.18 | +0.112R | 23.7R |

Top expectancy result with at least 100 trades:

| Fractal | Trend | EMA | Sep | Range | Body | TP | SL RR | Min SL | Trades | WR | Total R | PF | Exp | Max DD |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3 | D1 | 20/50 | 0.0010 | 8 | 0.6 | 1.00 | 1.50 | 12 | 144 | 50.0% | +33.9R | 1.47 | +0.235R | 14.0R |

Notes:

- GBPUSD in-sample sweep is stronger than EURUSD.
- The top total-R cluster is coherent: `fractal_n=3`, D1 EMA `20/50`, body `0.6`, TP `1.5`, SL RR `2.0`, min SL `8`.
- H4 `10/20` variants also scored well but appear less stable in fixed walk-forward checks.

### 2026-05-14 - GBPUSD walk-forward validation

Command:

`./venv/bin/python -u walk_forward.py candle_confirmation_gbpusd_wf --workers 1`

Optimized-family WF setup:

- Symbol: `GBPUSD`
- Folds: 4-year train, 2-year test, 2-year step
- Optimization metric: expectancy
- Candidate family around sweep winners:
  - `fractal_n`: `1`, `3`
  - `tf_trend`: `D1`, `H4`
  - EMA: `10/20`, `20/50`
  - `ema_sep_pct`: `0`, `0.0005`, `0.001`
  - `min_engulf_range_pips`: `8`, `12`, `15`
  - `min_engulf_body_pct`: `0.5`, `0.6`
  - `tp_range_pct`: `1.0`, `1.25`, `1.5`
  - `sl_rr_ratio`: `1.5`, `2.0`
  - `min_sl_pips`: `8`, `10`, `12`

Optimized-family result:

| Fold | Test period | Best params summary | IS R | OOS R | IS Exp | OOS Exp | OOS WR | OOS PF | Retention |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 2019-2021 | `fn=3, D1 20/50 sep .001, range 8, body .6, tp 1.0, slrr 1.5, minSL 12` | +14.9R | -3.1R | +0.355R | -0.078R | 37.5% | 0.88 | -22% |
| 2 | 2021-2023 | `fn=3, H4 10/20 sep .0005, range 8, body .6, tp 1.5, slrr 2.0, minSL 8` | +34.8R | +33.4R | +0.230R | +0.522R | 50.0% | 2.11 | 227% |
| 3 | 2023-2025 | `fn=3, H4 10/20 sep .001, range 8, body .6, tp 1.5, slrr 2.0, minSL 8` | +45.8R | -2.5R | +0.385R | -0.070R | 31.4% | 0.90 | -18% |

Aggregate optimized-family result:

| OOS trades | OOS R | OOS expectancy | Avg retention | Verdict |
|---:|---:|---:|---:|---|
| 139 | +27.8R | +0.200R | 62% | MODERATE |

Fixed candidate checks:

| Candidate | OOS trades | OOS R | OOS expectancy | Avg retention | Fold profile |
|---|---:|---:|---:|---:|---|
| `D1 20/50 sep0.001, range8, body0.6, tp1.5, slrr2, minSL8` | 222 | +41.4R | +0.186R | 118% | all 3 folds positive |
| `D1 20/50 sep0.0005, range8, body0.6, tp1.5, slrr2, minSL8` | 228 | +41.3R | +0.181R | 120% | all 3 folds positive |
| `H4 10/20 sep0.0005, range8, body0.5, tp1.5, slrr2, minSL8` | 248 | +49.7R | +0.200R | 168% | fold 3 negative |
| `D1 20/50 sep0, range8, body0.6, tp1.5, slrr2, minSL8` | 239 | +39.2R | +0.164R | 111% | all 3 folds positive |
| `D1 20/50 sep0.001, range8, body0.6, tp1.0, slrr1.5, minSL12` | 76 | +3.0R | +0.039R | -61% | weak / sparse |

Fixed-candidate fold detail:

| Candidate | Fold 1 OOS | Fold 2 OOS | Fold 3 OOS |
|---|---:|---:|---:|
| `D1 sep0.001` | +10.0R | +19.2R | +12.2R |
| `D1 sep0.0005` | +11.9R | +18.2R | +11.2R |
| `H4 sep0.0005 body0.5` | +22.9R | +30.9R | -4.1R |
| `D1 sep0` | +10.9R | +19.2R | +9.1R |
| `D1 sep0.001 tp1.0/slrr1.5/minSL12` | -3.1R | -6.6R | +12.7R |

Notes:

- GBPUSD is stronger than EURUSD after fixed-candidate validation.
- The optimized-family WF is MODERATE, but fold 1 and fold 3 are negative because the optimizer selected fragile/sparse configs in those folds.
- Fixed D1 variants are more stable: the top three D1 variants are positive in every OOS fold.
- Best fixed candidate for follow-up: `fractal_n=3`, D1 EMA `20/50`, `ema_sep_pct=0.001`, range `8`, body `0.6`, TP `1.5`, SL RR `2.0`, min SL `8`.
- Before demo/live, compare the fixed D1 candidate on HistData if available and consider whether adding GBPUSD alongside USDJPY increases correlated drawdown.

### 2026-05-14 - Added USDJPY candidate to live/demo config

Files changed:

- `live_config.py`: added `CandleConfirmationStrategy` to `create_live_strategy_specs()` on `['USDJPY']`.
- `config.py`: added MT5 magic number `CandleConfirmation_H1_M5: 1008`.

Live/demo parameters:

- Symbol: `USDJPY`
- `tf_bias='H1'`, `tf_entry='M5'`
- `fractal_n=2`
- `retrace_pct=0.5`
- `tp_range_pct=1.25`
- `sl_rr_ratio=1.5`
- `sl_mode='symmetric'`
- `require_fvg=True`
- `min_sl_pips=8.0`
- `tf_trend='D1'`
- `ema_fast=20`, `ema_slow=50`
- `ema_sep_pct=0.0005`
- `min_engulf_range_pips=8.0`
- `min_engulf_body_pct=0.5`
- `close_extreme_pct=1.0`
- `require_engulf_color=False`

Verification:

- `./venv/bin/python -m pytest tests/test_core_design.py -q` passed: 12 tests.
- Live config smoke check passed: strategy name `CandleConfirmation_H1_M5`, symbols `['USDJPY']`, timeframes `['H1', 'M5', 'D1']`, magic number `1008`.

### 2026-05-15 - Added GBPUSD candidate to live/demo config

Files changed:

- `strategies/candle_confirmation.py`: added optional `name` override so multiple candle-confirmation instances with different params can coexist safely.
- `live_config.py`: added separate USDJPY and GBPUSD candle-confirmation strategy instances.
- `config.py`: added MT5 magic numbers:
  - `CandleConfirmation_USDJPY_H1_M5: 1009`
  - `CandleConfirmation_GBPUSD_H1_M5: 1010`

Why the names changed:

- `EventEngine` indexes trade-close callbacks by `strategy.NAME`.
- USDJPY and GBPUSD use different params, so they need distinct live strategy names to avoid one instance receiving the other instance's close callback.

GBPUSD live/demo parameters:

- Symbol: `GBPUSD`
- Strategy name: `CandleConfirmation_GBPUSD_H1_M5`
- `tf_bias='H1'`, `tf_entry='M5'`
- `fractal_n=3`
- `retrace_pct=0.5`
- `tp_range_pct=1.5`
- `sl_rr_ratio=2.0`
- `sl_mode='symmetric'`
- `require_fvg=True`
- `min_sl_pips=8.0`
- `tf_trend='D1'`
- `ema_fast=20`, `ema_slow=50`
- `ema_sep_pct=0.001`
- `min_engulf_range_pips=8.0`
- `min_engulf_body_pct=0.6`
- `close_extreme_pct=1.0`
- `require_engulf_color=False`

USDJPY live/demo name update:

- Symbol: `USDJPY`
- Strategy name changed from default `CandleConfirmation_H1_M5` to `CandleConfirmation_USDJPY_H1_M5`
- Params unchanged from the validated USDJPY candidate.

Verification:

- `./venv/bin/python -m pytest tests/test_core_design.py -q` passed: 12 tests.
- Live config smoke check passed for both candle-confirmation variants:
  - `CandleConfirmation_USDJPY_H1_M5`, symbols `['USDJPY']`, magic `1009`
  - `CandleConfirmation_GBPUSD_H1_M5`, symbols `['GBPUSD']`, magic `1010`

### 2026-05-15 - AUDUSD broad sweep and walk-forward validation

Broad sweep:

- Command: `./venv/bin/python -u sweep_candle_confirmation_eurusd.py --symbol AUDUSD`
- Output CSV: `output/candle_confirmation_audusd_sweep.csv`
- Grid: 9,477 non-redundant combinations covering `fractal_n`, trend filter off/H4/D1, EMA pair/separation, engulf range/body filters, TP range percent, SL RR ratio, and min SL.

Top sweep rows:

| Rank | Params summary | Trades | WR | Total R | PF | Exp | Max DD |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | `fn=1, D1 20/50 sep .001, range 8, body .6, tp 1.0, slrr 2.0, minSL 8` | 185 | 42.2% | +44.5R | 1.41 | +0.240R | 18.7R |
| 2 | `fn=2, H4 10/20 sep 0, range 15, body .4, tp 1.25, slrr 2.0, minSL 12` | 233 | 39.9% | +43.1R | 1.31 | +0.185R | 8.0R |
| 3 | `fn=1, D1 20/50 sep .0005, range 8, body .6, tp 1.0, slrr 2.0, minSL 8` | 190 | 41.6% | +42.4R | 1.38 | +0.223R | 20.7R |

Optimized-family walk-forward:

- Config: `candle_confirmation_audusd_wf`
- Targeted grid: 3 folds x 1,152 combos, focused on the D1 20/50 and H4 10/20 sweep neighborhoods.

| Fold | Test period | Best params summary | IS R | OOS R | IS Exp | OOS Exp | OOS WR | OOS PF | Retention |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 2019-2021 | `fn=3, D1 10/20 sep .0005, range 15, body .4, tp 1.0, slrr 2.0, minSL 12` | +24.7R | +4.7R | +0.823R | +0.294R | 43.8% | 1.52 | 36% |
| 2 | 2021-2023 | `fn=3, D1 10/20 sep .0005, range 15, body .4, tp 1.0, slrr 2.0, minSL 12` | +24.6R | -15.1R | +0.631R | -1.009R | 0.0% | 0.00 | -160% |
| 3 | 2023-2025 | `fn=1, D1 20/50 sep .001, range 8, body .4, tp 1.0, slrr 2.0, minSL 8` | +21.4R | +1.5R | +0.305R | +0.070R | 36.4% | 1.11 | 23% |

Aggregate optimized-family result:

| OOS trades | OOS R | OOS expectancy | Avg retention | Verdict |
|---:|---:|---:|---:|---|
| 53 | -8.9R | -0.168R | -34% | FAIL |

Fixed candidate checks:

| Candidate | OOS trades | OOS R | OOS expectancy | Fold profile |
|---|---:|---:|---:|---|
| `H4 10/20 sep0, range15, body0.4, tp1.25, slrr2, minSL12` | 130 | +36.4R | +0.280R | all 3 folds positive |
| `D1 20/50 sep0.001, range8, body0.6, tp1.0, slrr2, minSL8` | 99 | +30.7R | +0.310R | fold 1 negative, folds 2-3 strong |
| `D1 20/50 sep0.0005, range8, body0.6, tp1.0, slrr2, minSL8` | 103 | +26.6R | +0.258R | fold 1 negative, folds 2-3 strong |
| `D1 20/50 sep0.001, range12, body0.5, tp1.0, slrr1.5, minSL12` | 60 | +12.0R | +0.200R | all 3 folds positive, lower trade count |

Fixed-candidate fold detail:

| Candidate | Fold 1 OOS | Fold 2 OOS | Fold 3 OOS |
|---|---:|---:|---:|
| `H4 top` | +20.3R | +1.2R | +14.9R |
| `D1 top sep0.001` | -13.6R | +28.9R | +15.4R |
| `D1 adjacent sep0.0005` | -14.6R | +26.8R | +14.4R |
| `D1 conservative lowDD` | +5.2R | +2.5R | +4.3R |

Notes:

- AUDUSD optimized-family WF fails because the training optimizer selects a fragile sparse D1 10/20 row that collapses in 2021-2023.
- The exact H4 top sweep row is more stable than the D1 top row: lower full-sample expectancy, but all OOS folds positive and lower full-sweep max drawdown.
- AUDUSD is not added to live/demo yet. Candidate for follow-up: `fractal_n=2`, H4 EMA `10/20`, `ema_sep_pct=0.0`, range `15`, body `0.4`, TP `1.25`, SL RR `2.0`, min SL `12`.

### 2026-05-15 - XAUUSD broad sweep

Broad sweep:

- Command: `./venv/bin/python -u sweep_candle_confirmation_eurusd.py --symbol XAUUSD`
- Output CSV: `output/candle_confirmation_xauusd_sweep.csv`
- Grid: 9,477 non-redundant combinations covering `fractal_n`, trend filter off/H4/D1, EMA pair/separation, engulf range/body filters, TP range percent, SL RR ratio, and min SL.

Top sweep rows:

| Rank | Params summary | Trades | WR | Total R | PF | Exp | Max DD |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | `fn=2, H4 10/20 sep .0005, range 12, body .5, tp 1.5, slrr 1.25, minSL 12` | 898 | 46.2% | +4.6R | 1.01 | +0.005R | 58.9R |
| 2 | `fn=2, H4 10/20 sep .0005, range 15, body .5, tp 1.5, slrr 1.25, minSL 8` | 944 | 46.2% | +1.8R | 1.00 | +0.002R | 57.0R |
| 3 | `fn=2, H4 10/20 sep .0005, range 12, body .5, tp 1.5, slrr 1.25, minSL 10` | 919 | 46.1% | +1.7R | 1.00 | +0.002R | 62.9R |

Fixed top-row fold check:

| Fold | Test period | IS trades | IS R | IS Exp | IS DD | OOS trades | OOS R | OOS Exp | OOS PF | OOS DD |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 2019-2021 | 269 | +12.4R | +0.046R | 13.4R | 169 | -34.7R | -0.205R | 0.68 | 38.0R |
| 2 | 2021-2023 | 337 | -21.2R | -0.063R | 38.0R | 170 | -19.5R | -0.115R | 0.81 | 23.1R |
| 3 | 2023-2025 | 341 | -54.0R | -0.158R | 58.9R | 156 | +27.6R | +0.177R | 1.38 | 6.5R |

Aggregate fixed top-row result:

| OOS trades | OOS R | OOS expectancy | Verdict |
|---:|---:|---:|---|
| 495 | -26.6R | -0.054R | FAIL |

Notes:

- XAUUSD did not produce a meaningful in-sample winner: the best sweep row was only `+4.6R` over 898 trades with PF `1.01`, expectancy `+0.005R`, and max drawdown `58.9R`.
- Because the sweep edge was effectively flat and the fixed top-row fold check failed, no optimized walk-forward grid was run.
- Do not promote XAUUSD candle confirmation to demo/live from this parameter family.
