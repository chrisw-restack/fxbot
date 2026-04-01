# BigBeluga Supply & Demand

**Status:** SHELVED — no edge (WR 33.4%, expectancy ~0R)
**File:** `strategies/bigbeluga_sd.py`
**Timeframes:** D1, H4
**Order type:** MARKET

---

## Strategy Logic

Based on BigBeluga's "Supply and Demand Zones" TradingView indicator. Identifies zones from 3-candle momentum patterns rather than swing pivots.

**Zone detection:**
- Supply: 3 consecutive bearish candles + above-average volume on middle bar. Scans back up to 6 bars for the most recent bullish "origin" candle. Zone = `[origin.low, origin.low + ATR×zone_atr_mult]`.
- Demand: 3 consecutive bullish candles + above-average volume. Origin = most recent bearish candle. Zone = `[origin.high - ATR×zone_atr_mult, origin.high]`.
- 15-bar cooldown per direction after each zone forms.
- D1 EMA(50) bias filter.

**Entry:** Wick rejection (same as SmcZone) — bar wicks into zone but closes back outside, directional close required.

---

## Results (2026-04-01)

7 pairs, H4, 2016–2026. ATR(200)×2 zones, 15-bar cooldown.

| Config | Trades | WR | Expectancy | PF | MaxDD |
|--------|--------|----|------------|-----|-------|
| With volume filter | 613 | 33.4% | +0.00R | 1.00 | 39R (19.4%) |
| Without volume filter | 665 | 33.7% | +0.01R | 1.02 | 39R (19.6%) |

---

## Assessment

**No edge.** WR of 33.4% is right at the 33.3% breakeven for 2:1 R:R. Expectancy is essentially zero.

**Why it failed:**

1. **Volume filter useless with tick volume.** FX spot has no centralised exchange — MT5/Dukascopy "volume" is tick count, not real traded volume. "Above average tick volume" carries no meaningful signal about institutional participation. The filter made no difference (33.4% vs 33.7%).

2. **3-candle pattern has no edge as a zone identifier.** Three consecutive candles in one direction is too common on H4 to mark significant institutional levels. The pattern fires ~60 times/year across 7 pairs and produces nothing. Contrast with SmcZone's swing pivots (rarer, more structurally significant) which achieved 43.9% WR.

3. **Wide zones (ATR(200)×2).** Very long ATR lookback × large multiplier creates 80–100 pip zones on EURUSD H4. The wick rejection condition fires on many bars near such a wide zone, effectively making entry near-random.

**Volume concern:** The BigBeluga indicator was likely designed for equities or futures where centralised exchange volume is meaningful. On FX spot, the volume condition is a proxy at best. Real futures data (e.g. CME 6E for EURUSD) would make the condition meaningful, but would require futures broker and data infrastructure.

Shelved permanently for spot FX. Might be worth revisiting for futures or crypto (centralised exchange volume).
