# Keltner Reversion

**Status:** SHELVED — walk-forward FAIL (aggregate -0.006R OOS, fold 3 collapse)
**File:** `strategies/keltner_reversion.py`
**Timeframes:** H1
**Order type:** MARKET

---

## Current Config

```python
KeltnerReversionStrategy()
# Defaults: kc_period=20, kc_mult=2.0, atr_period=14, rsi_period=14,
#           adx_period=14, adx_threshold=25.0, sl_lookback=10, cooldown_bars=5
```

---

## Strategy Logic

Multi-indicator mean reversion — more sophisticated version of the basic Bollinger Band approach.

- **Keltner Channel:** EMA-based channel using ATR for band width. More stable than Bollinger Bands in trending markets.
- **BUY signal:** Price touches or exceeds the lower KC band AND RSI divergence present AND ADX < threshold
- **SELL signal:** Price touches or exceeds the upper KC band AND RSI divergence present AND ADX < threshold

**RSI divergence:** Price makes a new extreme but RSI does not confirm — a classically reliable reversal signal. Detected by comparing the current bar's price extreme to the prior swing, and checking whether RSI moved in the same direction.

**ADX filter:** ADX < 25 means the market is in a ranging (non-trending) regime. Mean reversion is only attempted in ranging conditions, avoiding fading strong trends.

- **SL:** Recent swing extreme (lowest low / highest high of `sl_lookback` bars) + small buffer
- **TP:** Risk manager default (2:1 R:R)
- **Cooldown:** 5 bars after a loss before re-entering

---

## Parameter Sweep (2026-03-26)

Grid: kc_mult [1.5, 2.0, 2.5], adx_threshold [20.0, 25.0, 30.0], sl_lookback [5, 10, 20], cooldown_bars [0, 5, 10].
81 combinations. H1, 8 symbols.

Best combos by expectancy (full sample):

| kc_mult | adx_thr | sl_lb | cd | trades | WR | R | Expect | PF | DD |
|---------|---------|-------|----|----|----|----|------|----|----|
| 2.5 | 30.0 | 5 | 0 | 212 | 35.4% | +13R | +0.061 | 1.09 | 18R |
| 2.5 | 20.0 | 5 | 0 | 54 | 35.2% | +3R | +0.056 | 1.09 | 8R |
| 1.5 | 20.0 | 20 | 10 | 464 | 34.9% | +22R | +0.047 | 1.07 | 32R |

Note: `sl_lookback` has no effect — the SL is almost always constrained by `min_sl_pips`/`max_sl_pips` regardless of the lookback window. Effective grid is 3×3×3 = 27 unique combos.

Ceiling: +0.061R expectancy. Only 212 trades over 10 years on the best combo (~21/yr).

---

## Walk-Forward (2026-03-26) — FAIL

Grid: same 81 combos. 4yr train / 2yr test / 2yr step. 8 symbols (H1).

| Fold | Test period | IS R | OOS R | OOS Expect | OOS WR | OOS PF | Retain |
|------|-------------|------|-------|-----------|--------|--------|--------|
| 1 | 2020–2022 | -3.0 | +1.0 | +0.013 | 33.8% | 1.02 | N/A |
| 2 | 2022–2024 | +21.0 | +7.0 | +0.125 | 37.5% | 1.20 | 66% |
| 3 | 2024–2026 | +28.0 | -9.0 | -0.273 | 24.2% | 0.64 | -57% |
| **Agg** | | | **-1.0R** | **-0.006R** | | | |

Best params (fold 3): `kc_mult=2.0, adx_threshold=20.0` — IS showed +0.475R expectancy (49.2% WR on 59 trades), but OOS was -0.273R on 33 trades. The train window produced a dramatic overfitting artifact.

Fold 2 was encouraging (+0.125R OOS, 66% retention), but fold 3 entirely reversed this. Aggregate OOS is -0.006R = barely negative.

---

## Assessment

FAIL. Despite a conceptually solid setup (KC band touch + RSI divergence + ADX ranging filter), the strategy shows no consistent OOS edge. Low trade count (169 OOS across 3 folds = ~56/fold) makes each fold noisy. Fold 3's collapse from +0.475R IS to -0.273R OOS is a clear overfitting signal — the 2020–2024 training window likely captured a period with concentrated mean-reversion conditions that didn't persist.

The RSI divergence filter adds complexity but not predictive power. The "ranging ADX" filter by itself is not sufficient to predict mean-reversion success.

---

## Next Steps

- [ ] No further testing — shelved
