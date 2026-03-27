# TheStrat

**Status:** SUSPENDED — fails walk-forward after simulator bug fix
**File:** `strategies/the_strat.py`
**Variants:** D1/H4/H1 (daily bias) and H4/H1/M15 (4H bias)
**Order type:** PENDING

---

## Current Config (in run_backtest.py — not in live suite)

```python
# D1/H4/H1 stack
TheStratStrategy(min_sl_pips=8, cooldown_bars=3)

# H4/H1/M15 stack
TheStratStrategy(min_sl_pips=5, cooldown_bars=3, tf_bias='H4', tf_intermediate='H1', tf_entry='M15')
```

Symbols: EURUSD, GBPUSD, AUDUSD, NZDUSD, USDJPY, USDCAD, USDCHF (7 pairs).

---

## Strategy Logic

- **Bias TF:** Classifies each candle as type 1 (inside), 2U (bullish engulf), 2D (bearish engulf), or 3 (outside). Combines consecutive candles into patterns: `2-1-2_rev`, `2-1-2_cont`, `3-1-2`, `1-2-2`, `3`. Patterns determine directional bias.
- **Intermediate TF:** Confirms alignment — requires intermediate TF candle to be in the bias direction.
- **Entry TF:** Detects fractal swing high/low (N bars each side). Places PENDING order at the fractal level. SL beyond the prior fractal.
- **FVG (Fair Value Gap):** Optional — requires a 3-bar gap on the entry TF before entry.
- **Bias types:** Configurable set of patterns that trigger a bias. Reversal-only patterns outperform; continuation patterns add noise.

---

## Walk-Forward History

### Pre-bug-fix era (inflated results — DO NOT USE)
| Date | Verdict | OOS trades | OOS expectancy | Avg retention | Notes |
|------|---------|------------|----------------|---------------|-------|
| ~2026-03-18 | STRONG (D1/H4/H1) | — | — | ~94% | Entirely artificial — D1/H4 fill bug |
| ~2026-03-18 | STRONG (H4/H1/M15) | — | — | ~118% | Entirely artificial — D1/H4 fill bug |

### Post-bug-fix (2026-03-22 — correct results)

**D1/H4/H1 — FAIL**

| Fold | Test period | IS R | OOS R | OOS Expect | OOS PF | Retain |
|------|-------------|------|-------|------------|--------|--------|
| 1 | 2019–2021 | +18.2 | +3.0 | +0.053 | 1.09 | 28% |
| 2 | 2021–2023 | +22.9 | -18.9 | -0.199 | 0.72 | -147% |
| 3 | 2023–2025 | +7.5 | +0.1 | +0.003 | 1.00 | 2% |
| **Agg** | | | **-15.8R** | **-0.089** | | **-39%** |

**H4/H1/M15 — WEAK**

| Fold | Test period | IS R | OOS R | OOS Expect | OOS PF | Retain |
|------|-------------|------|-------|------------|--------|--------|
| 1 | 2019–2021 | +5.9 | +2.5 | +0.061 | 1.10 | 56% |
| 2 | 2021–2023 | +11.7 | +5.0 | +0.066 | 1.11 | 47% |
| 3 | 2023–2025 | +15.9 | +0.6 | +0.029 | 1.05 | 9% |
| **Agg** | | | **+8.1R** | **+0.059** | | **37%** |

Walk-forward param grid used (2026-03-22):
- `bias_types`: [rev_only={2-1-2_rev, 3-1-2, 1-2-2}, rev+3={...+3}, strong={2-1-2_rev, 3-1-2}]
- `min_sl_pips`: [5, 8, 15] for D1/H4/H1 | [5, 10, 15, 20] for H4/H1/M15
- `cooldown_bars`: [0, 3, 6]
- `fractal_n`: [2, 3]

---

## Parameter Sweep History

### Sweep 1 (sweep_the_strat.py, 2026-03-22)
Grid: min_sl_pips [5,8,10,15,20], cooldown_bars [0,3,6], fractal_n [1,2,3], bias_preset [all/no_cont/rev_only/strong]
360 total runs (180 per stack).

Key findings:
- **Reversal-only bias patterns consistently outperform.** Including `2-1-2_cont` and `3` (continuation) hurts performance across both stacks.
- Best D1/H4/H1 (by PF): rev_only or strong preset, min_sl=8-15, fractal_n=2-3. PF ~1.42 in-sample.
- Best H4/H1/M15 (by PF): strong preset, min_sl=10-15, fractal_n=2-3. PF ~1.33 in-sample.
- Note: these in-sample figures did not hold OOS (see walk-forward above).

---

## Bug History

### D1/H4 fill bug (the root cause of all inflated results)
- **What happened:** `simulated_execution.py` had no timeframe gating. When a D1 bar was processed, it would check all pending orders for that symbol — including H1 and M15 pending orders placed the same bar. The D1 bar's wide range (e.g. 100 pips) would trigger the H1 pending entry and then also hit the TP in the same bar. This made TheStrat look extremely profitable.
- **Discovery (2026-03-19):** User manually traced a live trade and noticed the 4H bias bar hadn't closed yet when M15 entries were being placed. The backtest was consuming future price data from the unclosed bias bar.
- **Fix (2026-03-20):** Added `entry_timeframe` field to `Signal` and `EnrichedSignal`. Engine auto-tags each signal with the bar's timeframe. `SimulatedExecution` stores this on the pending order and gates:
  - MARKET/PENDING fills: only on bars matching `entry_timeframe`
  - SL/TP checks: only on bars equal or finer than `entry_timeframe` (by minutes)
- **Impact:** D1/H4/H1 collapsed from artificially strong → -45.7R full backtest. H4/H1/M15 similarly -268.3R. The "STRONG 94-118%" walk-forward results were entirely artificial.

---

## Known Issues / Open Questions

- The H4/H1/M15 stack shows marginal positive OOS in all 3 folds (+8.1R aggregate) — the concept isn't completely without merit, but the edge is too small and decaying (fold 3 retention = 9%) to trade.
- The entry trigger (fractal + optional FVG) may be too loose — generates entries that don't have sufficient follow-through.
- Candle classification logic in `the_strat.py` should be reviewed: is a "2U" correctly requiring a full engulf, or just a higher high/lower low?

---

## Next Steps (if reviving)

- [ ] Structural rethink of entry trigger — consider requiring confirmed MSS (market structure shift) on entry TF before placing the pending
- [ ] Tighten FVG requirement — make it mandatory rather than optional
- [ ] Add volume/ATR filter to avoid entering during low-volatility compression
- [ ] Consider reducing to single TF stack (H4 bias + H1 entry only, no M15) to reduce parameter sensitivity
- [ ] Any new config must pass walk-forward with STRONG verdict (>70% avg OOS retention) before going live
