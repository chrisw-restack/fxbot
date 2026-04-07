# Engulfing

**Status:** VALIDATED — walk-forward STRONG (all 3 folds OOS positive, consistent params). Running in demo alongside EmaFibRetracement + EmaFibRunning.
**File:** `strategies/three_line_strike.py` (class `ThreeLineStrikeStrategy`, NAME=`'Engulfing'`)
**Timeframes:** M5
**Order type:** MARKET

---

## Current Config (as of 2026-04-03)

```python
ThreeLineStrikeStrategy(
    sl_mode='fractal',
    fractal_n=3,
    min_prev_body_pips=3.0,
    engulf_ratio=1.5,
    max_sl_pips=15,
    allowed_hours=tuple(range(13, 18)),  # NY session: 13:00–17:00 UTC
    sma_sep_pips=5.0,
    pip_sizes={'USDJPY': 0.01},
)
# RR ratio: 2.5 (set on RiskManager — strategy does not set take_profit)
```

Symbols: EURUSD, AUDUSD, NZDUSD, USDJPY, USDCAD (5 pairs — GBPUSD excluded: positive London/Both but negative NY; USDCHF excluded: MaxDD 23R, only +0.065R IS).
Risk: 0.5% per trade (default).

---

## Strategy Logic

M5 bullish or bearish engulfing candle pattern, filtered by trend alignment and session.

### Filters (all must pass)

| Filter | Bullish | Bearish |
|--------|---------|---------|
| Trend | `price > SMA200` | `price < SMA200` |
| MA alignment | `SMA21 > SMA50 + sep_pips` | `SMA21 < SMA50 − sep_pips` |
| RSI momentum | `RSI > 50` | `RSI < 50` |
| Session | hour in `allowed_hours` (13–17 UTC) | same |

### Pattern

**Bullish:** Previous bar is bearish with body ≥ `min_prev_body_pips`. Current bar is bullish, opens below previous close, closes above previous open, and body ≥ `engulf_ratio × prev_body`.

**Bearish:** Previous bar is bullish with body ≥ `min_prev_body_pips`. Current bar is bearish, opens above previous close, closes below previous open, and body ≥ `engulf_ratio × prev_body`.

### Stop Loss

`fractal` mode: most recent swing low (bullish) / swing high (bearish) using a window of `2×fractal_n+1` bars (n=3 → 7-bar window). Skips if SL > `max_sl_pips` from entry.

### Take Profit

Risk manager default: `entry ± (SL distance × 2.0R)`.

---

## Full IS Backtest (2026-04-03)

5 pairs (EURUSD, AUDUSD, NZDUSD, USDJPY, USDCAD). 2016–2026. Final config above.

| Metric | Value |
|--------|-------|
| Trades | 101 |
| Win rate | 40.6% (41W / 60L) |
| Total R | +22.0R |
| Profit factor | 1.37 |
| Expectancy | +0.22R per trade |
| Max drawdown | 10.0R (5.5%) |
| Best win streak | 5 |
| Worst loss streak | 10 |
| Avg win | 2.00R |
| Avg loss | 1.00R |

~10 trades/yr across 5 pairs (2 trades/pair/yr). Low frequency is the main practical constraint.

---

## Walk-Forward Results (2026-04-03)

4yr train / 2yr test / 2yr step. 3 folds. 18 combos per fold.
Fixed: `fractal_n=3, allowed_hours=NY, sma_sep_pips=5.0`. Grid: `min_prev_body_pips [0,3,5] × engulf_ratio [1.0,1.5,2.0] × max_sl_pips [15,20]`.

| Fold | Test Period | Best Params | IS Trades | IS Expect | OOS Trades | OOS Expect | OOS WR | OOS PF | Retain |
|------|-------------|-------------|-----------|-----------|------------|------------|--------|--------|--------|
| 1 | 2020–2022 | body=3, ratio=1.5, sl=15 | 33 | +0.091R | 20 | +0.350R | 45.0% | 1.64 | 385% |
| 2 | 2022–2024 | body=3, ratio=1.5, sl=20 | 44 | +0.227R | 53 | +0.132R | 37.7% | 1.21 | 58% |
| 3 | 2024–2026 | body=3, ratio=1.5, sl=15 | 51 | +0.294R | 20 | +0.200R | 40.0% | 1.33 | 68% |

### Walk-forward 1 (2026-04-03) — rr=2.0 fixed

**Aggregate OOS: 93 trades | +18.0R | +0.194R expectancy | Avg retention: 170%**

| Fold | Test Period | Best Params | IS Expect | OOS Expect | Retain |
|------|-------------|-------------|-----------|------------|--------|
| 1 | 2020–2022 | body=3, ratio=1.5, sl=15, rr=2.0 | +0.091R | +0.350R | 385% |
| 2 | 2022–2024 | body=3, ratio=1.5, sl=20, rr=2.0 | +0.227R | +0.132R | 58% |
| 3 | 2024–2026 | body=3, ratio=1.5, sl=15, rr=2.0 | +0.294R | +0.200R | 68% |

### Walk-forward 2 (2026-04-07) — rr_ratio added to grid [2.0, 2.5]

**Aggregate OOS: 93 trades | +22.0R | +0.237R expectancy | Avg retention: 178%**

| Fold | Test Period | Best Params | IS Expect | OOS Expect | Retain |
|------|-------------|-------------|-----------|------------|--------|
| 1 | 2020–2022 | body=3, ratio=1.5, sl=15, **rr=2.0** | +0.091R | +0.350R | 385% |
| 2 | 2022–2024 | body=3, ratio=1.5, sl=20, **rr=2.0** | +0.227R | +0.132R | 58% |
| 3 | 2024–2026 | body=3, ratio=1.5, sl=15, **rr=2.5** | +0.441R | +0.400R | **91%** |

**Verdict: STRONG** — all 3 folds OOS positive. `min_body=3, engulf_ratio=1.5` unanimous across all folds. Fold 3 (most recent, 2020–2024 training) chose rr=2.5 and produced the strongest OOS (+0.400R, 91% retention). Live config updated to rr=2.5.

**Caveat:** 93 total OOS trades across 10 years is sparse (~9–10 trades/yr per fold). STRONG verdict reflects param robustness, not high statistical confidence. Monitor demo carefully.

---

## Per-Symbol Breakdown (IS, Config C from shared config comparison)

Config C: `fractal n=3, min_body=3, engulf_ratio=1.5, max_sl=20, NY session`. 10-year IS (2016–2026).

| Symbol | Expectancy | Trades | Notes |
|--------|------------|--------|-------|
| EURUSD | +0.500R | 36 | Best expectancy |
| NZDUSD | +0.200R | 15 | Good expectancy, very sparse |
| USDCAD | +0.159R | 44 | Solid, decent trade count |
| AUDUSD | +0.167R | 18 | Good expectancy, sparse |
| USDJPY | +0.041R | 49 | Most trades, weakest expectancy |
| GBPUSD | −0.200R | 60 | Excluded — negative on NY session |
| USDCHF | n/a | n/a | Excluded — MaxDD 23R, +0.065R IS |

---

## Parameter Sweep History

### Cross-pair shared config comparison (2026-04-03)

8 candidate configs across all 6 major pairs, NY session only. Config C identified as the best shared config.

| Config | EURUSD | GBPUSD | AUDUSD | NZDUSD | USDJPY | USDCAD | Pairs+ | Avg Exp | Total R |
|--------|--------|--------|--------|--------|--------|--------|--------|---------|---------|
| C: frac3 body3 eng1.5 sl20 | +0.500R/36 | −0.200R/60 | +0.167R/18 | +0.200R/15 | +0.041R/49 | +0.159R/44 | **5** | **+0.144** | **+21.0** |

Config C is the only config positive on 5 of 6 pairs.

### Single-pair sweeps

Full 324-combo sweep (3 sessions × 3 min_body × 3 eng_ratio × 4 SL configs × 3 max_sl) was run on AUDUSD and GBPUSD. NY session consistently outperformed London and Both on both pairs. Fractal SL modes outperformed bar_multiple. `min_prev_body_pips=3` and `engulf_ratio=1.5` appeared consistently in top configs.

---

## Assessment

- **Strengths:** Consistent params across all 3 WF folds. All OOS periods positive. Strategy adds diversification complement to EmaFibRetracement (different timeframe, different session logic).
- **Concerns:** Very sparse trade count (~9–10/yr per fold). Single-pair expectancy can be noisy. The strong WF verdict is driven partly by fold 1 OOS over-performance (2020–2022 volatility was favourable for engulfing patterns).
- **Not recommended for live yet:** Need 50+ demo trades to validate the real-market edge. Go to demo first; monitor for at least 6 months.

---

## Next Steps

- [ ] Put on demo — monitor with 50+ trade target before considering live promotion
- [ ] Track per-pair performance — USDJPY has lowest expectancy, watch if it drags
- [ ] Consider adding GBPUSD back if London session added later (positive on London, negative on NY)
