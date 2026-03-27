# Supply & Demand

**Status:** SHELVED — walk-forward MODERATE (+0.020R OOS) but too few trades (150 OOS) and fold 1 negative
**File:** `strategies/supply_demand.py`
**Timeframes:** H4
**Order type:** MARKET

---

## Current Config

```python
SupplyDemandStrategy()
# Defaults: leg_min_pips=30, base_min_candles=2, base_max_body_pips=15, ema_period=50
```

---

## Strategy Logic

Identifies supply and demand zones from price consolidations with strong departure legs, then enters on the first retest of the zone.

### Zone detection
A valid zone consists of:
1. **Base:** 2+ consecutive candles with small bodies (< `base_max_body_pips`) — a consolidation
2. **FVG departure:** A 3-bar Fair Value Gap pattern leaving the base with a strong leg of at least `leg_min_pips`

This identifies areas where price consolidated briefly before an impulsive move — a classic supply/demand zone signature.

### Entry
- **EMA trend filter:** Only take BUY setups when H4 close > 50-period EMA; SELL when below
- **Retest:** Wait for price to trade back into the zone after the departure leg
- **Rejection candle:** Enter on a candle that closes away from the zone (a rejection of the level)
- **Entry:** MARKET at close of rejection candle
- **SL:** Zone low (BUY) / Zone high (SELL)
- **TP:** Risk manager default (2:1 R:R)
- **Zone expiry:** Zones are invalidated when price trades through them, or when a new zone forms

---

## Parameter Sweep (2026-03-26)

Grid: leg_min_pips [20.0, 30.0, 50.0], base_max_body_pips [10.0, 15.0, 20.0], min_leg_zone_ratio [1.5, 2.0, 3.0], zone_max_age_bars [60, 120, 200].
81 combinations. H4, 8 symbols.

Best combos by expectancy (full sample):

| leg_pips | body_pips | ratio | age | trades | WR | R | Expect | PF | DD |
|----------|-----------|-------|-----|--------|-----|----|----|----|----|
| 50 | 10 | 3.0 | 60/120/200 | 103 | 35.9% | +8R | +0.078 | 1.12 | 10R |
| 20/30 | 10 | 2.0 | 120/200 | 263 | 35.7% | +19R | +0.072 | 1.11 | 15R |
| 20/30 | 10 | 1.5 | 120/200 | 345 | 35.4% | +21R | +0.061 | 1.09 | 24R |

`zone_max_age_bars` has little effect on expectancy (only affects trades slightly). Key params are leg_min_pips, base_max_body_pips (tight = 10 is best), and min_leg_zone_ratio.

Best expectancy: +0.078R on 103 trades/10yr (~10/yr). Low trade count.

---

## Walk-Forward (2026-03-26) — MODERATE

Grid: same 81 combos. 4yr train / 2yr test / 2yr step. 8 symbols (H4). MIN_TRADES=15.

| Fold | Test period | IS R | OOS R | OOS Expect | OOS WR | OOS PF | Retain |
|------|-------------|------|-------|-----------|--------|--------|--------|
| 1 | 2019–2021 | +12.0 | -6.0 | -0.154 | 28.2% | 0.79 | -77% |
| 2 | 2021–2023 | +6.0 | +0.0 | +0.000 | 33.3% | 1.00 | 0% |
| 3 | 2023–2025 | +12.0 | +9.0 | +0.100 | 36.7% | 1.16 | 102% |
| **Agg** | | | **+3.0R** | **+0.020R** | | **51%** |

Best params by fold:
- Fold 1: `leg=50, body=10, ratio=2.0, age=60`
- Fold 2: `leg=50, body=10, ratio=3.0, age=60`
- Fold 3: `leg=20, body=10, ratio=1.5, age=120`

Verdict: **MODERATE** (51% retention, aggregate OOS +0.020R).

Warning flags:
- Only 150 total OOS trades across 3 folds (~50/fold) — statistical confidence is low
- Fold 1 (2019–2021) negative: -0.154R OOS, WR 28.2%
- Fold 2: flat (0.000R OOS, PF 1.00)
- Improving trend: fold 3 shows +0.100R OOS with 102% retention — but this follows two poor folds
- Best params changed significantly fold to fold — no stable configuration

---

## Assessment

MODERATE verdict technically passes the 40% retention threshold, but the result is fragile:
- Very low trade count (50 OOS trades per fold) makes each fold unreliable — a handful of trades changes the outcome
- Two of three folds are flat or negative
- Parameter instability: fold 3 selected entirely different params from fold 1/2

The improving trend (fold 3 significantly better) could indicate the S&D concept is gaining relevance in the current market, or could just be noise with 90 trades. Not enough evidence to promote to live.

Shelved pending more data. If live performance data becomes available in 2026–2027, revisit.

---

## Next Steps

- [ ] No further testing — shelved (borderline MODERATE, too few trades for confidence)
- [ ] Revisit if more years of H4 data become available to increase OOS trade count
