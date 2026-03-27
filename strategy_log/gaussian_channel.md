# Gaussian Channel

**Status:** SHELVED — walk-forward WEAK (inconsistent, fold 2 negative)
**File:** `strategies/gaussian_channel.py`
**Timeframes:** H4
**Order type:** MARKET

---

## Current Config

```python
GaussianChannelStrategy(period=144, poles=4, tr_mult=1.414)
```

---

## Strategy Logic

Trend-following strategy using a Gaussian-filtered price channel.

- **Filter:** Multi-pole Gaussian (IIR) filter applied to HLC3 (typical price). `poles=4` means the filter is applied 4 times recursively, producing a very smooth signal. `period=144` bars = 24 days on H4 — a long-term trend filter.
- **Channel:** Upper and lower bands = filtered HLC3 ± (filtered True Range × `tr_mult`). `tr_mult=1.414` (√2) controls band width.
- **BUY:** Close breaks above the upper band
- **SELL:** Close breaks below the lower band
- **SL:** Filtered midline (the Gaussian HLC3 line itself)
- **TP:** Risk manager default (2:1 R:R)
- Optional cooldown after a loss.

The Gaussian filter's key property: near-zero phase lag at lower frequencies, which means it tracks long-term trends smoothly without the lag artefacts of a simple moving average.

---

## Bug Fix (2026-03-26)

The strategy originally had a warm-up bug: the multi-pole recursive filter only required `poles` bars (= 4) of seeding before emitting signals. However, the large recursive coefficients (3.618, -4.912, etc.) produced wildly incorrect filter values for ~200+ H4 bars after start of data, causing trades with SL pips in the thousands and false R=+1.00 LOSS entries. The inflated result was +541R with $99k commission — clearly invalid.

**Fix applied:**
1. Warm-up guard increased to `2 × period` bars (288 bars = 48 days of H4) before any signal can be emitted.
2. Geometry safety check: BUY signals where SL ≥ entry_price are rejected (and vice versa for SELL). Prevents any residual filter corruption from placing impossible SL levels.
3. Band inversion check: if upper ≤ lower (filter not yet stable), skip the bar.

After fix, clean results: avg loss = 1.00R, no anomalous trades.

---

## Baseline (post-fix, 2026-03-26)

Config: `period=144, poles=4, tr_mult=1.414, cooldown_bars=0`
8 symbols (7 FX + XAUUSD), H4 data 2016–2026.

| Metric | Value |
|--------|-------|
| Trades | 1086 |
| Win rate | 35.1% |
| Total R | +57R |
| Expectancy | +0.052R |
| Profit factor | 1.08 |
| Max DD | 28R (14.8%) |

Low expectancy. Avg loss = 1.00R (correct geometry confirmed).

---

## Parameter Sweep (2026-03-26)

Grid: period [72, 144, 288], poles [2, 3, 4], tr_mult [1.0, 1.414, 2.0], cooldown_bars [0, 3, 6].
81 combinations. H4, 8 symbols.

Best combos by expectancy:

| period | poles | tr_mult | cd | trades | WR | R | Expect | PF | DD |
|--------|-------|---------|----|----|----|----|------|----|----|
| 288 | 2 | 2.000 | 6 | 936 | 35.3% | +54R | +0.058 | 1.09 | 43R |
| 144 | 4 | 1.414 | 0 | 1086 | 35.1% | +57R | +0.052 | 1.08 | 28R |
| 288 | 4 | 2.000 | 6 | 635 | 34.8% | +28R | +0.044 | 1.07 | 31R |

Sweep ceiling is only +0.058R. No combinations show strong expectancy. All results are near breakeven on full sample.

---

## Walk-Forward (2026-03-26) — WEAK

Grid: same 81 combos. 4yr train / 2yr test / 2yr step. 8 symbols.

| Fold | Test period | IS R | OOS R | OOS Expect | OOS WR | OOS PF | Retain |
|------|-------------|------|-------|-----------|--------|--------|--------|
| 1 | 2019–2021 | +23.0 | +3.0 | +0.019 | 34.0% | 1.03 | 21% |
| 2 | 2021–2023 | +21.0 | -9.0 | -0.079 | 30.7% | 0.89 | -68% |
| 3 | 2023–2025 | +35.0 | +26.0 | +0.157 | 38.6% | 1.25 | 165% |
| **Agg** | | | **+20R** | **+0.046R** | | **40%** |

Best params: `period=288, poles=2/4, tr_mult=2.0, cooldown_bars=3/6` (varied by fold).

Fold 2 (2021–2023) negative. Fold 3 strong but follows two weaker folds — likely era-specific rather than persistent. 40% retention = WEAK threshold.

---

## Assessment

WEAK walk-forward. The strategy does have a marginal positive signal (aggregate OOS +20R, +0.046R), but the era-to-era inconsistency and below-50% retention mean there's no reliable edge to trade. The Gaussian filter is technically sound but as a standalone H4 breakout system, there's not enough information in the signal to overcome the noise.

Key limitations:
- No multi-timeframe bias filter
- SL at midline means variable SL width depending on market volatility
- Long warm-up period (288 H4 bars = 48 days) reduces usable data in each fold

---

## Next Steps

- [ ] No further testing — shelved
- [ ] If reviving: consider adding D1 trend filter (HTF bias) before revisiting
