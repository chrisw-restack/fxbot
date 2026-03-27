# Mean Reversion (Bollinger Band)

**Status:** SHELVED — sweep shows no viable configuration
**File:** `strategies/mean_reversion.py`
**Timeframes:** H1
**Order type:** MARKET

---

## Current Config

```python
MeanReversionStrategy(lookback=20, std_multiplier=2.0, sl_lookback=5)
```

---

## Strategy Logic

Bollinger Band mean reversion — fade extended moves back toward the mean.

- **BUY:** Close below lower Bollinger Band (mean - 2σ)
- **SELL:** Close above upper Bollinger Band (mean + 2σ)
- **SL:** Lowest low of the last `sl_lookback` bars (BUY) / Highest high (SELL)
- **TP:** Risk manager default (2:1 R:R)

No trend filter, session filter, or multi-timeframe logic. Pure statistical mean reversion.

---

## Parameter Sweep (2026-03-25)

Grid: lookback [10, 20, 30, 50], std_multiplier [1.5, 2.0, 2.5, 3.0], sl_lookback [3, 5, 10]
48 combinations. H1, 8 symbols (7 FX + XAUUSD).

Every combination negative. Best result: lb=10, std=3.0, sl_lb=3 → -66R, -0.014R expect, 32.9% WR.
Win rate stuck at 31–33% across all settings. At 2R target, breakeven requires >33.3%.

Key finding: wider bands (std=3.0) are better than narrow (std=1.5) because they filter out more noise, but even at 3.0σ the win rate never clears the 33.3% breakeven threshold. The fundamental problem is that a 3σ extension on H1 forex is often a genuine breakout, not a reversion.

## Assessment

No viable configuration found. The strategy is structurally unable to achieve the required win rate at 2R. Fading Bollinger Band extremes without a ranging-market filter consistently loses on trending forex pairs.

`keltner_reversion.py` is a more sophisticated version that adds RSI divergence + ADX ranging filter — worth testing before concluding mean reversion is unworkable on this universe.

## Next Steps

- [ ] No further testing of BB mean reversion — shelved
- [ ] See `keltner_reversion.md` for the better-designed variant
