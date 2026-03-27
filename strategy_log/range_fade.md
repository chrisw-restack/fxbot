# Range Fade

**Status:** SHELVED — barely fires (best combo 56 trades/10yr), no reliable edge
**File:** `strategies/range_fade.py`
**Timeframes:** H1
**Order type:** MARKET

---

## Current Config

```python
RangeFadeStrategy()
# Defaults: atr_period=14, atr_long_period=100, squeeze_ratio=0.7,
#           range_period=48, edge_pct=0.15, cooldown_bars=5
```

---

## Strategy Logic

Fade the edges of a consolidation range when volatility is compressed.

### Range detection
- Tracks rolling high/low over `range_period` bars (48 hours on H1)
- `edge_pct=0.15` defines the "edge zone": the top 15% and bottom 15% of the range

### Volatility filter (ATR squeeze)
- Short ATR (14 bars) vs long ATR (100 bars)
- Only take signals when `short_ATR / long_ATR < squeeze_ratio` (0.7) — current volatility is compressed relative to the 100-bar baseline
- This filters out breakout periods and only trades during genuine consolidation

### Entry condition
1. Price enters the edge zone (top 15% for SELL, bottom 15% for BUY)
2. Rejection candle forms: for BUY at bottom — bullish candle with the lower wick larger than the body (rejection of the low); for SELL at top — bearish candle with upper wick larger than body

**Entry:** MARKET at close of rejection candle
**SL:** Range extreme - small buffer (opposite side of the range from entry)
**TP:** Risk manager default (2:1 R:R, targeting the range mean or opposite edge)
**Cooldown:** 5 bars after a loss

---

## Parameter Sweep (2026-03-26)

Grid: squeeze_ratio [0.5, 0.7, 0.9], range_period [24, 48, 96], edge_pct [0.10, 0.15, 0.20], cooldown_bars [0, 5, 10].
81 combinations. H1, 8 symbols.

Only 2 of 81 combos produced meaningful positive results — both identical params (cooldown just reduces trades, doesn't change expectancy when 0):

| squeeze_ratio | range_period | edge_pct | cd | trades | WR | R | Expect | PF |
|---|---|---|---|---|---|---|---|---|
| 0.70 | 96 | 0.20 | 0 | 56 | 35.7% | +4R | +0.071 | 1.11 |
| 0.70 | 48 | 0.20 | 5/10 | 113 | 33.6% | +1R | +0.009 | 1.01 |

56 trades in 10 years = ~6 per year. The ATR squeeze filter (squeeze_ratio=0.7) combined with 96-bar range period is so restrictive it barely fires. All other combos have < 5 trades or negative results. The strategy is extremely selective but produces almost no signals.

Root cause: the combination of ATR squeeze (current vol < 70% of long-term avg) + specific range period + rejection candle pattern is almost never satisfied simultaneously on H1 forex. The signals that do pass are marginally positive but far too rare to form a meaningful edge.

---

## Assessment

Not viable. The strategy concept is sound but the signal frequency is too low to trade. 6 trades/year across 8 symbols is less than 1 per symbol per year. Walk-forward would have 0–5 trades per fold, making any result statistically meaningless.

---

## Next Steps

- [ ] No further testing — shelved
