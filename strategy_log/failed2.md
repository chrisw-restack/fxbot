# Failed2

## Status

Unvalidated. Initial implementation added for H4 > H1 > M5 testing.

## Rules

- HTF bias uses `H4` by default.
- Bullish bias can come from:
  - 2 candle: closes above the previous candle body high without taking the previous low.
  - 3 candle: takes the previous low and closes above the previous candle body high.
  - failed2 candle: wicks below the previous low and closes back above the previous candle body low.
- Bearish bias is the inverse:
  - 2 candle: closes below the previous candle body low without taking the previous high.
  - 3 candle: takes the previous high and closes below the previous candle body low.
  - failed2 candle: wicks above the previous high and closes back below the previous candle body high.
- Bias remains active until an opposite HTF bias signal replaces it.
- `invalidate_on_bias_extreme` exists for testing, default `False`.

## Confirmation And Entry

- ITF confirmation uses `H1` by default and must close after the active HTF bias candle.
- BUY confirmation: H1 wicks below the previous H1 low and closes back above that low.
- SELL confirmation: H1 wicks above the previous H1 high and closes back below that high.
- LTF entry uses `M5` by default after the H1 failed2 candle has closed.
- BUY MSS: M5 closes above a confirmed swing high.
- SELL MSS: M5 closes below a confirmed swing low.
- `entry_mode='market'`: enter at the MSS candle close.
- `entry_mode='fvg'`: place a pending order in the nearest FVG from the MSS leg.
- SL uses the previous confirmed opposite fractal swing point.
- TP is strategy-set from `rr_ratio`, default `2.0`.
- One trade is allowed per confirmed H1 failed2 setup.

## Sweep Candidates

- `entry_mode`: `market`, `fvg`
- `mss_fractal_n`: 1, 2, 3
- `sl_fractal_n`: 1, 2, 3
- `rr_ratio`: 1.5, 2.0, 2.5, 3.0
- `fvg_entry_pct`: 0.0, 0.5, 1.0
- `invalidate_on_bias_extreme`: False, True
- Future timeframe combo: H1 > M15 > M1 after M1 data is available.

## Initial Registry

- `failed2`: H4 > H1 > M5, market MSS entry, 2R TP.
- `failed2_fvg`: H4 > H1 > M5, FVG pending entry, 2R TP, 50% FVG fill.

## Parameter Sweep - 2026-05-08

Symbols: `USA100`, `EURUSD`, `GBPUSD`

Date range: 2022-01-01 through available data.

First pass:

- Grid: entry mode `market/fvg`, fractal pairs `(1,1) (1,2) (2,1) (2,2) (2,3) (3,2)`, SL anchor `wick/body`, RR `1.5/2.0/2.5`, sessions `all/ln_us/ny`.
- Best first-pass result: `fvg`, MSS fractal `1`, SL fractal `1`, body SL, `2.5R`, NY session. Result: 1,340 trades, 31.3% WR, +90.9R, +0.068R expectancy, max DD 40.7R. Positive on all 3 symbols.

TP extension:

- Grid: same structure, sessions `ln_us/ny`, RR `2.5/3.0/3.5`.
- Best Total R: `market`, MSS fractal `3`, SL fractal `2`, wick SL, `3.5R`, NY session. Result: 1,404 trades, 25.9% WR, +215.6R, +0.154R expectancy, max DD 27.9R. Per symbol: USA100 +121.2R, EURUSD +76.7R, GBPUSD +17.7R.
- Best risk-adjusted / lower DD: `market`, MSS fractal `3`, SL fractal `2`, wick SL, `3.5R`, London/NY overlap. Result: 1,327 trades, 25.9% WR, +203.7R, +0.154R expectancy, max DD 22.8R. Per symbol: USA100 +109.5R, EURUSD +70.8R, GBPUSD +23.5R.

Current backtest registry:

- `failed2_best`: risk-adjusted preferred config, London/NY overlap, 3.5R.
- `failed2_best_ny`: highest Total R config, NY session, 3.5R.

Notes:

- The initial 2R defaults were weak. Higher TP targets materially improved Failed2.
- The strongest cluster used market entries, wick SL, MSS fractal `3`, SL fractal `2`, and `3.5R`.
- FVG entries remained viable, especially `1/1` or `1/2` body SL at `3R`, but market entries dominated the TP-extension sweep.
- Results are optimization only. Walk-forward validation is still required before treating either config as robust.

## Walk-Forward Validation - 2026-05-08

Symbols: `USA100`, `EURUSD`, `GBPUSD`

Grid: entry mode `market/fvg`, MSS fractal `1/2/3`, SL fractal `1/2/3`, SL anchor `wick/body`, TP `2.5/3.0/3.5R`, sessions `12-17 UTC` and `13-18 UTC`.

Window: 4-year train, 2-year test, 2-year step. Optimization metric: expectancy. Minimum IS trades: 100. Workers: 1.

| Fold | Train | Test | Best params | IS R | OOS R | OOS Exp | Retention |
|---|---|---|---|---:|---:|---:|---:|
| 1 | 2015-2018 | 2019-2020 | fvg, MSS 1, SL 1, wick SL, 3.0R, NY | +30.4R | +12.1R | +0.019R | 63% |
| 2 | 2017-2020 | 2021-2022 | fvg, MSS 1, SL 2, wick SL, 3.5R, London/NY | +101.4R | -73.1R | -0.117R | -130% |
| 3 | 2019-2022 | 2023-2024 | market, MSS 3, SL 3, body SL, 3.5R, NY | +105.2R | +41.1R | +0.064R | 77% |

Aggregate OOS: 1,910 trades, -19.9R total, -0.010R expectancy. Average retention: 3%.

Verdict: WEAK/FAIL. The 2022+ optimization result does not generalize across the 2021-2022 OOS regime. Do not promote Failed2 as a validated candidate without further regime filtering or a materially narrower hypothesis.

## HTF Extreme Invalidation Test - 2026-05-09

Hypothesis: after an HTF bias candle forms, invalidate that trade idea if a later HTF candle takes out the bias candle extreme before the ITF/LTF setup completes. Example: after a bullish H4 number 2, if a later H4 candle trades above that H4 bias candle high, stop looking for H1/M5 continuation entries from that bias.

Implementation note: `invalidate_on_bias_extreme=True` now checks only HTF bars. Lower timeframe wicks into the HTF extreme do not invalidate by themselves.

Tested against `failed2_best` on `USA100`, `EURUSD`, `GBPUSD`, from 2022-01-01 through available data.

| Config | Trades | Win rate | Total R | PF | Expectancy | Max DD |
|---|---:|---:|---:|---:|---:|---:|
| `failed2_best` baseline | 1,327 | 25.9% | +203.71R | 1.21 | +0.15R | 31.35R |
| `failed2_best_htf_extreme` | 1,325 | 26.0% | +205.72R | 1.21 | +0.16R | 31.35R |

Verdict: neutral/slightly positive on the 2022+ in-sample window, but the effect is tiny. This filter alone is unlikely to solve the walk-forward failure; it should be included as a small toggle in later robustness tests rather than treated as a major edge.

## Diagnostic Breakdown And Filter WF - 2026-05-09

Diagnostic baseline: `failed2_best`, `USA100` + `EURUSD` + `GBPUSD`, from 2022-01-01 through available data.

Overall diagnostic sample: 1,327 trades, +203.7R, +0.154R expectancy, PF 1.21, max DD 31.4R.

Key breakdowns:

| Bucket | Trades | Total R | Expectancy | Note |
|---|---:|---:|---:|---|
| USA100 | 502 | +109.5R | +0.218R | Best symbol |
| EURUSD | 412 | +70.8R | +0.172R | Good |
| GBPUSD | 413 | +23.5R | +0.057R | Weakest symbol |
| BUY | 624 | +140.4R | +0.225R | Better than sells |
| SELL | 703 | +63.3R | +0.090R | Still positive |
| HTF `2` bias | 876 | +148.0R | +0.169R | Main contributor |
| HTF `failed2` bias | 226 | +58.9R | +0.261R | Best expectancy |
| HTF `3` bias | 225 | -3.2R | -0.014R | Weak overall, mostly GBPUSD drag |
| D1 range bottom 40% | 509 | +175.2R | +0.344R | Strongest diagnostic edge |
| D1 range top 20% | 306 | +1.3R | +0.004R | Nearly flat; block candidate |

Filter WF grid:

- Symbol sets: all three, USA100 only, EURUSD+GBPUSD.
- Bias type: all vs failed2-only vs 2/3-only.
- D1 range filter: off vs block top 20%.
- Trend filter: off vs D1 EMA alignment vs H4 EMA alignment.
- Fixed base: market entry, MSS fractal 3, SL fractal 2, wick SL, 3.5R, 12-17 UTC.

### All Three Symbols

| Fold | Test | Best filter | OOS R | OOS Exp | Retention |
|---|---|---|---:|---:|---:|
| 1 | 2019-2020 | all bias, block top 20% D1 range, D1 EMA aligned | +26.7R | +0.119R | 84% |
| 2 | 2021-2022 | all bias, block top 20% D1 range, D1 EMA aligned | -5.1R | -0.020R | -10% |
| 3 | 2023-2024 | all bias, block top 20% D1 range, no trend filter | +100.0R | +0.202R | 185% |

Aggregate OOS: 982 trades, +121.6R, +0.124R expectancy. Verdict: STRONG/MODERATE, but fold 2 remains slightly negative.

### USA100 Only

Every fold selected: all bias types, block top 20% D1 range, D1 EMA aligned.

| Fold | Test | OOS R | OOS Exp | Retention |
|---|---|---:|---:|---:|
| 1 | 2020-2021 | +55.0R | +0.585R | 281% |
| 2 | 2022-2023 | +22.5R | +0.244R | 66% |
| 3 | 2024-2025 | +24.9R | +0.290R | 70% |

Aggregate OOS: 272 trades, +102.4R, +0.376R expectancy. Verdict: STRONG. This is the cleanest Failed2 candidate so far.

### EURUSD + GBPUSD Only

| Fold | Test | OOS R | OOS Exp |
|---|---|---:|---:|
| 1 | 2019-2020 | -17.8R | -0.108R |
| 2 | 2021-2022 | -30.4R | -0.180R |
| 3 | 2023-2024 | +43.1R | +0.111R |

Aggregate OOS: 723 trades, -5.1R, -0.007R expectancy. Verdict: FAIL despite the old WF script's retention-based label; aggregate OOS is negative.

Decision:

- Keep `failed2_filtered` as the current research candidate.
- Treat Failed2 as a USA100-first strategy.
- Do not include EURUSD/GBPUSD in a live/demo candidate unless a separate FX-specific filter is found.

## USA100 Robustness Suite - 2026-05-09

Script: `failed2_robustness.py`

Scope: `USA100`, Dukascopy data, 2020-01-01 to 2026-01-01. Net-R metrics include commission by calculating each trade's realised PnL divided by its initial cash risk.

Base config: `failed2_filtered` (`H4/H1/M5`, market MSS, MSS fractal 3, SL fractal 2, wick SL, 3.5R, 12-17 UTC, D1 EMA alignment, block top 20% D1 range).

| Test | Trades | WR | Net R | Exp | PF | Max DD | Return |
|---|---:|---:|---:|---:|---:|---:|---:|
| Base 2020-2026 | 294 | 30.6% | +55.2R | +0.188R | 1.23 | 23.6R | +29.8% |
| Holdout 2025+ | 45 | 33.3% | +15.1R | +0.336R | 1.44 | 9.3R | +7.5% |

Year breakdown:

| Year | Trades | Net R | Exp | Note |
|---|---:|---:|---:|---|
| 2020 | 46 | +17.0R | +0.370R | Strong |
| 2021 | 48 | +20.4R | +0.424R | Strongest year |
| 2022 | 51 | +0.6R | +0.011R | Flat |
| 2023 | 49 | +7.7R | +0.157R | Positive |
| 2024 | 50 | +0.3R | +0.005R | Flat |
| 2025 | 50 | +9.4R | +0.187R | Positive |

Parameter-neighborhood test:

- Grid: MSS fractal `2/3/4`, SL fractal `1/2/3`, TP `3.0/3.5/4.0R`, session `12-17/13-18/12-18`, D1 range block `70/80/90%`.
- Best result: `mss4/sl2/rr4/13_18/block80`, 260 trades, +79.0 net R, +0.304R expectancy, PF 1.38, max DD 16.4R.
- Current neighborhood remains positive, but not the top point. The strongest cluster favours `MSS 4`, `SL 2/3`, `4R`, `13-18 UTC`, and block `70/80%`.
- Weakest cluster is mostly `3R` with the loose `90%` volatility block, often flat to negative.

Execution-cost stress on current base config:

| Stress | Net R | Exp | PF | Max DD | Return |
|---|---:|---:|---:|---:|---:|
| Normal spread/commission, no slippage | +55.2R | +0.188R | 1.23 | 23.6R | +29.8% |
| 2x spread, normal commission, 1 pip slippage | +41.8R | +0.142R | 1.18 | 24.3R | +21.6% |
| Normal spread, 1.5x commission, no slippage | +31.6R | +0.107R | 1.12 | 28.6R | +15.0% |
| 2x spread, 1.5x commission, 1 pip slippage | +19.5R | +0.066R | 1.08 | 32.4R | +7.6% |
| 2x spread, 2x commission, 1 pip slippage | -2.8R | -0.009R | 0.99 | 44.1R | -4.9% |

Bias-variant check:

| Bias filter | Trades | Net R | Exp | PF | Max DD |
|---|---:|---:|---:|---:|---:|
| All bias types | 294 | +55.2R | +0.188R | 1.23 | 23.6R |
| `2` only | 466 | +6.6R | +0.014R | 1.02 | 45.1R |
| `3` only | 608 | -43.8R | -0.072R | 0.92 | 72.9R |
| `2/3` only | 351 | +34.5R | +0.098R | 1.12 | 37.3R |
| `failed2` only | 552 | -79.8R | -0.145R | 0.84 | 115.2R |

Breakdown notes:

- Direction was balanced enough: BUY +42.5 net R, SELL +12.7 net R.
- Hour quality: 13 and 14 UTC carried most of the edge; 15 UTC was barely positive.
- D1 range after the top-20% block: `40-60%` was strongest (+30.7 net R), `bottom 40%` was positive (+22.1 net R), `60-80%` was barely positive (+2.4 net R).
- Month-level losses still cluster; worst months include 2021-03, 2023-09, 2022-11/12, 2024-01, 2025-07.

Second-source check:

- HistData USA100 could not be checked because local `USA100 D1` HistData files are missing.

Decision:

- Keep `failed2_filtered` as the conservative registered research candidate for now because it is already walk-forward selected.
- Do not switch immediately to the top neighborhood point without walk-forward testing it; the robustness grid suggests a promising next candidate family around `MSS 4 / SL 2 / 4R / 13-18 UTC / D1 range block 70-80%`.
- Required next validation: walk-forward the smaller USA100-only candidate family and then confirm on broker/MT5 or another second data source before demo promotion.

## USA100 HistData Second Source - 2026-05-11

HistData symbol mapping added:

- Project `USA100` -> HistData `NSXUSD` (NASDAQ 100 in USD)
- Project `USTEC` -> HistData `NSXUSD`

Fetched with:

`python fetch_data_histdata.py --symbols USA100 --timeframes M5 H1 H4 D1 --start-year 2016 --end-date 2026-03-20 --insecure`

Created files:

- `data/historical/histdata/USA100_M5_20160103-20260319.csv`
- `data/historical/histdata/USA100_H1_20160103-20260319.csv`
- `data/historical/histdata/USA100_H4_20160103-20260319.csv`
- `data/historical/histdata/USA100_D1_20160103-20260319.csv`

Smoke test:

`python run_backtest.py failed2_filtered --symbols USA100 --start-date 2020-01-01 --end-date 2026-01-01 --data-source histdata`

| Data source | Trades | WR | Total R | PF | Expectancy | Max DD | Ending balance |
|---|---:|---:|---:|---:|---:|---:|---:|
| HistData `NSXUSD` as `USA100` | 267 | 31.8% | +108.07R | 1.59 | +0.40R | 17.33R | $13,762.18 |

Decision:

- Second-source confirmation is positive. HistData/NSXUSD does not invalidate the Dukascopy USA100 result.
- Next validation remains a USA100-only walk-forward on the smaller candidate family around `MSS 4 / SL 2 / 4R / 13-18 UTC / D1 range block 70-80%`.

## USA100 Candidate-Family Walk-Forward - 2026-05-11

Purpose: test the robustness-suite's better-looking parameter cluster without reopening a broad search.

WF config added: `failed2_usa100_candidate`

Grid:

- Symbols: `USA100` only
- Timeframes: `D1/H4/H1/M5`
- Fixed: market entry, wick SL, all HTF bias types, D1 EMA alignment, block top D1 range, pip sizes
- Swept: MSS fractal `3/4`, SL fractal `2/3`, TP `3.5/4.0R`, session `12-17/13-18 UTC`, D1 range block `70/80%`
- 32 combinations per fold, workers 1, metric `expectancy`

### Dukascopy

Command:

`python walk_forward.py failed2_usa100_candidate --metric expectancy --workers 1 --data-source dukascopy`

| Fold | Test | Selected core | OOS trades | OOS R | OOS Exp | PF | Retention |
|---|---|---|---:|---:|---:|---:|---:|
| 1 | 2020-2021 | MSS4, SL2, 4R, 12-17 UTC, block 70% | 74 | +62.2R | +0.841R | 2.35 | 213% |
| 2 | 2022-2023 | MSS4, SL2, 4R, 13-18 UTC, block 70% | 58 | +15.6R | +0.269R | 1.36 | 45% |
| 3 | 2024-2025 | MSS4, SL2, 4R, 13-18 UTC, block 70% | 76 | +17.8R | +0.234R | 1.31 | 37% |

Aggregate OOS: 208 trades, +95.6R, +0.460R expectancy. Verdict: STRONG.

### HistData / NSXUSD

Command:

`python walk_forward.py failed2_usa100_candidate --metric expectancy --workers 1 --data-source histdata`

| Fold | Test | Selected core | OOS trades | OOS R | OOS Exp | PF | Retention |
|---|---|---|---:|---:|---:|---:|---:|
| 1 | 2020-2021 | MSS4, SL2, 4R, 12-17 UTC, block 70% | 73 | +63.2R | +0.866R | 2.40 | 249% |
| 2 | 2022-2023 | MSS4, SL2, 4R, 13-18 UTC, block 70% | 46 | +13.2R | +0.287R | 1.39 | 49% |
| 3 | 2024-2025 | MSS4, SL2, 4R, 13-18 UTC, block 70% | 71 | +22.8R | +0.321R | 1.44 | 47% |

Aggregate OOS: 190 trades, +99.2R, +0.522R expectancy. Verdict: STRONG.

Decision:

- Candidate-family WF passed on both Dukascopy and HistData.
- The stable selected core is `MSS 4 / SL 2 / 4R / D1 range block 70%`.
- Prefer `13-18 UTC` for the named candidate because it was selected in the two later folds on both data sources; `12-17 UTC` was selected only in the 2016-2019 train / 2020-2021 test fold.
- Registered `failed2_usa100_candidate` in `run_backtest.py` with `MSS4`, `SL2`, `4R`, `13-18 UTC`, D1 EMA alignment, and D1 range block `70%`.
- Next step before demo: direct fixed-parameter backtest on both sources, then execution/live-readiness review for USA100 broker symbol mapping and spread/commission assumptions.

## Fixed Candidate Backtests - 2026-05-11

Fixed strategy key: `failed2_usa100_candidate`

Config: `H4/H1/M5`, market entry, MSS fractal 4, SL fractal 2, wick SL, 4R TP, 13-18 UTC, D1 EMA alignment, D1 range filter blocking top 30% volatility, all HTF bias types.

Commands:

- `python run_backtest.py failed2_usa100_candidate --symbols USA100 --start-date 2016-01-01 --end-date 2026-01-01 --data-source dukascopy`
- `python run_backtest.py failed2_usa100_candidate --symbols USA100 --start-date 2016-01-01 --end-date 2026-01-01 --data-source histdata`

Standard backtest summary (`r_multiple` price-based, commission included in balance):

| Data source | Trades | WR | Total R | PF | Exp | Max DD | Worst loss streak | Ending balance |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Dukascopy | 373 | 29.8% | +163.49R | 1.62 | +0.44R | 16.61R | 13 | $12,597.35 |
| HistData / NSXUSD | 351 | 30.2% | +162.21R | 1.66 | +0.46R | 15.61R | 13 | $13,227.79 |

Net-R robustness summary (`pnl / initial cash risk`, so commission reduces R):

| Data source | Trades | WR | Net R | Exp | PF | Max DD | Worst loss streak | Return |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Dukascopy | 375 | 29.9% | +57.5R | +0.153R | 1.17 | 28.9R | 13 | +27.0% |
| HistData / NSXUSD | 353 | 30.0% | +61.9R | +0.175R | 1.19 | 27.2R | 13 | +30.2% |

Yearly net-R breakdown:

| Year | Dukascopy Net R | HistData Net R | Note |
|---|---:|---:|---|
| 2016 | -13.1R | -10.5R | weak |
| 2017 | -4.2R | -2.9R | weak |
| 2018 | +19.3R | +14.1R | strong |
| 2019 | -21.1R | -20.9R | worst year |
| 2020 | +28.8R | +27.7R | strong |
| 2021 | +25.4R | +27.7R | strong |
| 2022 | +1.9R | +0.8R | flat but positive |
| 2023 | +10.4R | +10.1R | positive |
| 2024 | +11.5R | +11.3R | positive |
| 2025 | -1.6R | +4.5R | mixed/flat |

Breakdown notes:

- Direction: buys are positive but weaker; sells have much higher expectancy.
- HTF bias type: `2` is the dominant edge. `failed2` HTF bias remains a drag on both sources.
- Entry hour: all allowed hours are acceptable on HistData; Dukascopy shows 14 UTC roughly flat while 15 UTC is strongest.
- D1 range bucket: `40-60%` prior D1 range is the strongest bucket; bottom 40% is only mildly positive; 60-80% is flat to mildly positive.

Decision:

- Fixed final candidate remains demo-worthy, with consistent cross-source performance and no source-specific failure.
- Caveat: early history 2016-2019 is choppy/weak, while 2020-2024 is much stronger. Demo should be monitored for regime degradation.

## Demo Registration - 2026-05-11

Registered `failed2_usa100_candidate` for demo/live runner as `Failed2_H4_H1_M5_market`.

Live/demo config:

- File: `live_config.py`
- Symbol: `USTEC` (ICMarkets-style Nasdaq 100 symbol; historical aliases remain `USA100`/HistData `NSXUSD`)
- Timeframes subscribed: `D1`, `H4`, `H1`, `M5`
- Parameters: market entry, MSS fractal 4, SL fractal 2, wick SL, 4R TP, 13-18 UTC, D1 EMA alignment, D1 range block 70%, all HTF bias types
- Risk: uses global demo default `RISK_PCT = 0.005` (`0.5%` per trade), same as the other demo strategies.
- Magic number: `1007`

Readiness checks completed locally:

- `config.validate()` passes.
- Failed2 live config instantiates successfully.
- Strategy name matches magic key: `Failed2_H4_H1_M5_market`.
- Strategy subscribes to `['D1', 'H4', 'H1', 'M5']`.
- Strategy sets its own TP on the signal, so the live runner's default 2.5R risk-manager setting does not override the 4R candidate TP.
- `USTEC` has pip size, pip value, and backtest spread config.

MT5/VPS checks still required before leaving demo unattended:

- Confirm broker symbol is exactly `USTEC`. If broker uses `NAS100`, `US100`, or another suffix/prefix, update `FAILED2_SYMBOLS` and add matching `PIP_SIZE`, `PIP_VALUE_USD`, and spread config.
- Run `measure_spreads.py` on the VPS during 13-18 UTC and verify typical USTEC spread is close to or below the 0.9-pip backtest assumption.
- Run `check_pip_values.py` on the VPS to confirm USTEC tick value and point size match the local `PIP_VALUE_USD['USTEC'] = 1.0` and `PIP_SIZE['USTEC'] = 1.0` assumptions.
- Watch first demo signals manually to verify broker H4/H1/M5 candles form the same setup logic as historical `USA100`/`NSXUSD`.

VPS check update, 2026-05-11:

- Broker symbol confirmed: `USTEC`.
- `measure_spreads.py` on ICMarketsSC-Demo measured USTEC p95 spread at `1.0` pip during the active session. `config.BACKTEST_SPREAD_PIPS['USTEC']` and `['USA100']` were updated from `0.9` to `1.0`.
- `check_pip_values.py` reported `USTEC` tick size `0.0100` and tick value `$0.0100`. With project pip size `1.0`, that is 100 ticks per pip/point, so one pip is worth `$1.00` per lot. Local `PIP_SIZE['USTEC'] = 1.0` and `PIP_VALUE_USD['USTEC'] = 1.0` are correct.

Decision:

- Approved for demo registration only, not live capital.
- Start at the shared demo default of `0.5%` risk per trade.
- Do not add more strategy filters until there is a meaningful forward-demo sample; only add execution safety checks if live spread/slippage is poor.

## Central Demo Trade Journal - 2026-05-11

Added a system-wide structured journal for all demo/live strategies, not just Failed2.

File:

- `logs/trade_journal.csv`

Purpose:

- Keep `logs/trading.log` as the operational text log.
- Use `logs/trade_journal.csv` as the audit trail for signal/order/close validation across every strategy.

Journal events:

- `SIGNAL` - strategy emitted a signal
- `REJECTED` - signal blocked by risk, portfolio, news, or execution failure
- `ORDER_PLACED` - order sent successfully to MT5
- `CANCEL_REQUESTED` - strategy requested pending-order cancellation
- `ORDER_CANCELLED` - pending order removed/missing from broker
- `CLOSE` - broker close detected

Common fields include:

- timestamp, event, ticket, symbol, strategy name, direction, order type, entry timeframe
- expected entry, actual MT5 fill/request price when available, SL, TP, lot size, risk pips, R:R
- result, PnL, realised R, close time
- spread in pips at order placement when MT5 tick data is available
- strategy context JSON

Failed2-specific fields are lifted into first-class columns when available:

- HTF bias type
- session hour
- D1/H4 trend alignment
- D1 range percentile
- D1 range blocked flag

Decision:

- Use the central journal to validate the first demo signals/trades.
- For Failed2, compare `SIGNAL` and `ORDER_PLACED` rows to ensure H4 bias, H1 confirmation, M5 MSS entry, SL, TP, spread, and fill price are behaving as expected.

## FX Majors Optimisation Pass - 2026-05-11

Purpose: check whether the NASDAQ Failed2 idea can be adapted to forex majors instead of assuming the USA100 parameters transfer.

Baseline diagnostic command:

`python analyze_failed2_diagnostics.py --symbols EURUSD GBPUSD AUDUSD NZDUSD USDJPY USDCAD USDCHF --start-date 2020-01-01 --end-date 2026-01-01 --data-source histdata --candidate best`

Baseline result on all seven majors:

- 3,922 trades, 23.1% WR, +90.0R, +0.023R expectancy, PF 1.03, max DD 148.9R.
- Best symbols: `USDCAD` +75.4R, `USDJPY` +35.2R, `AUDUSD` +28.1R, `GBPUSD` +22.8R, `EURUSD` +19.7R.
- Weak symbols: `USDCHF` -24.7R, `NZDUSD` -66.5R.
- HTF bias type: `2` carried the edge (+194.7R, +0.074R expectancy), `failed2` was roughly flat/weak (-5.5R), and `3` was poor (-99.2R).
- Time-of-day: 15 UTC was strongest (+147.9R), 13 UTC was positive (+32.3R), 12 UTC was positive but sparse (+20.0R), 14 UTC was poor (-112.9R).
- D1 EMA alignment helped: aligned trades +112.0R, counter-trend trades -10.1R.

Initial decision from diagnostics:

- Do not trade all majors as one pooled strategy.
- Exclude `NZDUSD` and `USDCHF`.
- Avoid HTF `3` bias for FX research.
- Keep D1 EMA trend alignment.
- Avoid 14 UTC.

### FX Walk-Forward Checks

Configs added in `walk_forward.py`:

- `failed2_fx_top5_candidate`: `USDCAD`, `USDJPY`, `AUDUSD`, `GBPUSD`, `EURUSD`
- `failed2_fx_top4_candidate`: `USDCAD`, `USDJPY`, `AUDUSD`, `GBPUSD`
- `failed2_fx_usdcad_candidate`: `USDCAD`
- `failed2_fx_usdjpy_candidate`: `USDJPY`

Top-5 pooled WF was stopped after fold 1 because the selected in-sample edge was too weak to justify the runtime:

| Scope | Fold | IS trades | IS R | IS Exp | OOS trades | OOS R | OOS Exp | Note |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Top 5 majors | 1 | 810 | +4.9R | +0.006R | 431 | +13.0R | +0.030R | Too diluted |

USDCAD single-symbol WF failed despite looking best in the baseline diagnostic:

| Fold | Test | OOS trades | OOS R | OOS Exp |
|---|---|---:|---:|---:|
| 1 | 2020-2021 | 73 | +11.1R | +0.152R |
| 2 | 2022-2023 | 54 | -14.7R | -0.272R |
| 3 | 2024-2025 | 108 | +2.1R | +0.019R |

Aggregate: 235 trades, -1.5R, -0.006R expectancy. Verdict: FAIL.

USDJPY is the only FX major with a constructive walk-forward result so far.

HistData WF:

| Fold | Test | Selected core | OOS trades | OOS R | OOS Exp | PF |
|---|---|---|---:|---:|---:|---:|
| 1 | 2020-2021 | MSS3, SL2, 3.5R, `2` bias, 13/15 UTC, no range filter | 120 | +14.0R | +0.117R | 1.16 |
| 2 | 2022-2023 | MSS4, SL2, 4R, `2/failed2`, 12/13/15 UTC, D1 range block | 69 | +20.2R | +0.293R | 1.40 |
| 3 | 2024-2025 | MSS3, SL3, 4R, `2/failed2`, 12/13/15/16 UTC, D1 range block | 98 | +5.1R | +0.052R | 1.07 |

Aggregate HistData OOS: 287 trades, +39.3R, +0.137R expectancy.

Dukascopy WF:

| Fold | Test | Selected core | OOS trades | OOS R | OOS Exp | PF |
|---|---|---|---:|---:|---:|---:|
| 1 | 2019-2020 | MSS4, SL2, 3.5R, `2/failed2`, 13/15 UTC, no range filter | 73 | +2.4R | +0.033R | 1.04 |
| 2 | 2021-2022 | MSS3, SL3, 3.5R, `2/failed2`, 12/13/15 UTC, no range filter | 117 | +25.4R | +0.217R | 1.30 |
| 3 | 2023-2024 | MSS3, SL3, 4R, `2/failed2`, 12/13/15/16 UTC, D1 range block | 83 | +50.9R | +0.614R | 1.91 |

Aggregate Dukascopy OOS: 273 trades, +78.7R, +0.288R expectancy.

### Fixed USDJPY Research Candidate

Registered in `run_backtest.py` as `failed2_fx_usdjpy_candidate`.

Config:

- Symbol: `USDJPY`
- Timeframes: `H4/H1/M5`
- Entry: market MSS
- MSS fractal: `3`
- SL fractal: `3`
- SL anchor: wick
- TP: `4R`
- Allowed HTF bias: `2` and `failed2`
- Allowed hours: `12`, `13`, `15`, `16` UTC
- Trend filter: D1 EMA aligned
- D1 range filter: block top 20% prior-day range

Fixed backtests from 2016-01-01 to 2026-01-01:

| Data source | Trades | WR | Total R | PF | Exp | Max DD | Worst loss streak | Ending balance |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| HistData | 469 | 23.0% | +64.96R | 1.18 | +0.14R | 68.22R | 19 | $12,091.61 |
| Dukascopy | 485 | 23.3% | +73.79R | 1.20 | +0.15R | 68.23R | 27 | $12,615.56 |

Decision:

- USDJPY is a research candidate only. It is not demo-ready.
- Cross-source profitability is encouraging, but the fixed-parameter equity profile is much worse than USA100: about 68R max drawdown and up to 27 consecutive losses.
- Parameter selection is less stable than the USA100 candidate, especially around session, D1 range filter, and MSS/SL fractal pair.
- Do not register FX Failed2 for demo until a focused robustness pass proves the drawdown and losing-streak profile is acceptable.

Recommended next FX step:

- Run a USDJPY-only robustness pass focused on reducing drawdown, not maximising Total R.
- Specifically test lower TP (`3R/3.5R`), stricter `2`-only HTF bias, smaller session windows (`13/15` and `12/13/15`), D1 range filter on/off, and a max-spread/slippage stress check.
- If the drawdown remains near 60-70R, shelve FX Failed2 and keep Failed2 as a NASDAQ-only strategy.

## FX Session Sweep - 2026-05-11

Script added: `sweep_failed2_fx_sessions.py`

Purpose: compare normal session buckets for FX Failed2 instead of only testing hand-picked individual hours.

Session definitions are fixed UTC approximations:

| Session | Allowed UTC hours |
|---|---|
| Asian | `00-06` |
| London | `07-11` |
| London full | `07-15` |
| NY AM | `12-16` |
| NY AM skip 14 | `12,13,15,16` |
| NY PM | `17-20` |
| NY full | `12-20` |
| London/NY overlap | `12-15` |
| London+NY | `07-20` |

First broad top-5-major run was stopped because the full grid was too slow for this targeted question. The useful run was USDJPY-only using the fixed research candidate parameters:

- MSS fractal `3`
- SL fractal `3`
- `4R`
- HTF bias `2` and `failed2`
- D1 EMA alignment
- D1 range filter blocking top 20%

Command:

`python sweep_failed2_fx_sessions.py --symbols USDJPY --start-date 2020-01-01 --end-date 2026-01-01 --data-source histdata --fixed-usdjpy-candidate --sessions asian london london_full ny_am ny_am_skip14 ny_pm ny_full london_ny_overlap london_ny --output output/failed2_fx_session_sweep_usdjpy_fixed_with_current.csv`

Results:

| Session | Hours UTC | Trades | WR | Total R | Exp | PF | Max DD | Worst loss streak |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| NY AM skip 14 | `12,13,15,16` | 265 | 27.9% | +101.5R | +0.383R | 1.53 | 15.4R | 10 |
| NY AM | `12-16` | 283 | 27.6% | +102.9R | +0.364R | 1.50 | 20.1R | 17 |
| NY PM | `17-20` | 229 | 27.5% | +80.6R | +0.352R | 1.48 | 17.6R | 13 |
| London/NY overlap | `12-15` | 268 | 26.9% | +88.4R | +0.330R | 1.45 | 19.3R | 17 |
| NY full | `12-20` | 407 | 26.5% | +125.8R | +0.309R | 1.42 | 27.6R | 15 |
| London full | `07-15` | 501 | 25.7% | +135.6R | +0.271R | 1.36 | 26.5R | 15 |
| London+NY | `07-20` | 606 | 25.2% | +147.8R | +0.244R | 1.32 | 34.6R | 20 |
| London | `07-11` | 395 | 24.8% | +87.2R | +0.221R | 1.29 | 24.0R | 18 |
| Asian | `00-06` | 390 | 24.1% | +73.0R | +0.187R | 1.24 | 30.6R | 17 |

Decision:

- The current USDJPY session window, `12/13/15/16 UTC`, is better than the generic NY AM bucket because excluding 14 UTC cut drawdown from 20.1R to 15.4R and reduced the worst loss streak from 17 to 10 with almost no loss of Total R.
- NY PM is interesting as a secondary hypothesis: lower Total R than NY AM, but good expectancy and low drawdown.
- Asian and standalone London are clearly weaker on this fixed-parameter test.
- This improves the USDJPY research case, but it is still not a demo candidate until this session result is walk-forward tested and checked on Dukascopy.

## USD Major Session/Parameter Sweep - 2026-05-11

Purpose: test whether the USDJPY FX edge also appears on the other USD majors.

Data source: HistData, 2020-01-01 to 2026-01-01.

Initial fixed-parameter session screen used the USDJPY research candidate settings:

- MSS fractal `3`
- SL fractal `3`
- `4R`
- HTF bias `2` and `failed2`
- D1 EMA alignment
- D1 range filter blocking top 20%

Symbols tested: `EURUSD`, `GBPUSD`, `AUDUSD`, `NZDUSD`, `USDCAD`, `USDCHF`.

Fixed screen result:

- Best pooled session was `12/13/15/16 UTC`, but only +33.0R total, +0.021R expectancy, and 77.5R max DD across all six.
- Positive pairs in that fixed screen: `AUDUSD`, `EURUSD`, `GBPUSD`, `USDCHF`.
- Weak/negative pairs: `USDCAD`, `NZDUSD`.

Focused parameter grid then ran per symbol on the promising session set:

- Sessions: `12/13/15/16`, `12-16`, `12-15`, `17-20` UTC
- MSS fractal: `3/4`
- SL fractal: `2/3`
- TP: `3.5/4.0R`
- HTF bias: `2` vs `2+failed2`
- D1 range filter: off vs block top 20%

Best rows by symbol:

| Symbol | Best session | Params | Trades | WR | Total R | Exp | PF | Max DD | Worst loss streak | Verdict |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| `AUDUSD` | `12-15` | MSS3, SL2, 3.5R, `2+failed2`, D1 range on | 269 | 27.1% | +55.2R | +0.205R | 1.28 | 12.0R | 12 | Promising |
| `GBPUSD` | `17-20` | MSS4, SL3, 4.0R, `2+failed2`, D1 range off | 241 | 24.5% | +50.7R | +0.210R | 1.28 | 15.0R | 15 | Promising |
| `USDCHF` | `12-15` | MSS4, SL3, 3.5R, `2+failed2`, D1 range on | 259 | 27.8% | +63.6R | +0.246R | 1.34 | 33.5R | 14 | Positive but high DD |
| `EURUSD` | `12-15` | MSS3, SL2, 3.5R, `2+failed2`, D1 range off | 360 | 24.2% | +28.9R | +0.080R | 1.11 | 19.7R | 18 | Marginal |
| `USDCAD` | `12/13/15/16` | MSS4, SL3, 4.0R, `2+failed2`, D1 range off | 268 | 22.4% | +26.5R | +0.099R | 1.13 | 48.6R | 21 | Weak risk profile |
| `NZDUSD` | `12-15` | MSS3, SL3, 3.5R, `2+failed2`, D1 range off | 299 | 21.4% | -25.4R | -0.085R | 0.89 | 50.4R | 22 | Fail |

Decision:

- `AUDUSD` and `GBPUSD` deserve walk-forward testing next. They have useful Total R, acceptable drawdown, and plausible session-specific behavior.
- `USDCHF` is profitable but riskier; only test it after AUDUSD/GBPUSD, or include it as a high-DD secondary candidate.
- `EURUSD` is positive but weak. Keep it as a possible portfolio diversifier only if walk-forward on stronger pairs is good.
- `USDCAD` and `NZDUSD` should be excluded from the next Failed2 FX pass.
- These results are still optimisation results, not validation. The next required step is walk-forward on `AUDUSD` and `GBPUSD` using the selected candidate families.

## AUDUSD/GBPUSD Walk-Forward - 2026-05-11

Purpose: validate the two cleanest USD-major optimisation candidates.

Data source: HistData. Window: 4-year train, 2-year test, 2-year step. Metric: expectancy. Workers: 1.

Configs added:

- `failed2_fx_audusd_candidate`
- `failed2_fx_gbpusd_candidate`

### AUDUSD

Command:

`python walk_forward.py failed2_fx_audusd_candidate --metric expectancy --workers 1 --data-source histdata`

Focused grid:

- Sessions: `12-15`, `12/13/15/16`, `12-16` UTC
- MSS fractal: `3/4`
- SL fractal: `2`
- TP: `3.5/4.0R`
- HTF bias: `2` vs `2+failed2`
- D1 range filter: off vs block top 20%

| Fold | Test | Selected core | IS R | OOS R | OOS Exp | PF | Retention |
|---|---|---|---:|---:|---:|---:|---:|
| 1 | 2020-2021 | MSS3, SL2, 4R, `2+failed2`, `12/13/15/16`, D1 range on | +1.2R | -4.3R | -0.044R | 0.95 | -629% |
| 2 | 2022-2023 | MSS4, SL2, 4R, `2` only, `12/13/15/16`, D1 range off | +11.8R | +18.3R | +0.166R | 1.22 | 369% |
| 3 | 2024-2025 | MSS3, SL2, 3.5R, `2+failed2`, `12-15`, D1 range on | +54.4R | +6.5R | +0.080R | 1.10 | 26% |

Aggregate OOS: 290 trades, +20.5R, +0.071R expectancy.

Decision:

- AUDUSD is not validated. The aggregate is positive, but fold 1 loses money and fold 3 retains only 26% of the IS edge.
- The selected parameters are unstable enough that the optimisation result should be treated as curve-fit until a narrower hypothesis is tested.

### GBPUSD

Command:

`python walk_forward.py failed2_fx_gbpusd_candidate --metric expectancy --workers 1 --data-source histdata`

Focused grid:

- Sessions: `17-20`, `12/13/15/16`, `12-16` UTC
- MSS fractal: `3/4`
- SL fractal: `2/3`
- TP: `3.5/4.0R`
- HTF bias: `2` vs `2+failed2`
- D1 range filter: off vs block top 20%

| Fold | Test | Selected core | IS R | OOS R | OOS Exp | PF | Retention |
|---|---|---|---:|---:|---:|---:|---:|
| 1 | 2020-2021 | MSS3, SL3, 4R, `2` only, `12-16`, D1 range on | +44.9R | +1.8R | +0.015R | 1.02 | 7% |
| 2 | 2022-2023 | MSS4, SL2, 4R, `2+failed2`, `17-20`, D1 range on | +28.3R | +3.3R | +0.065R | 1.08 | 32% |
| 3 | 2024-2025 | MSS4, SL3, 4R, `2+failed2`, `17-20`, D1 range off | +41.2R | +11.6R | +0.142R | 1.18 | 52% |

Aggregate OOS: 255 trades, +16.7R, +0.065R expectancy.

Decision:

- GBPUSD is better than AUDUSD because all three OOS folds are positive, but it is still weak validation.
- Retention is poor at 31% average, and the first fold is barely above breakeven.
- Do not promote GBPUSD Failed2 to demo yet. It may justify a narrower follow-up around `17-20 UTC`, MSS4, SL2/3, 4R, and `2+failed2`, but that needs a second WF pass and preferably Dukascopy confirmation.

Overall FX decision:

- Neither `AUDUSD` nor `GBPUSD` is demo-ready.
- GBPUSD is the only one worth a follow-up validation pass.
- Keep Failed2 demo focus on NASDAQ/USTEC for now.
