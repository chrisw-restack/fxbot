# EBP Limit (Engulfing Bar Play — Limit Entry)

**Status:** SHELVED — walk-forward FAIL
**File:** `strategies/ebp_limit.py`
**Timeframes:** Single TF (H4 / H1 / D1) + optional higher-TF EMA trend
**Order type:** PENDING (Buy Limit / Sell Limit)

---

## Current Config (as of 2026-03-23)

```python
EbpLimitStrategy(
    tf='H4',
    entry_pct=0.382,
    min_range_pips=60,
    max_sl_pips=80,
    tf_trend='D1',
    ema_fast=10,
    ema_slow=20,
)
```

Symbols tested: EURUSD, GBPUSD, AUDUSD, NZDUSD, USDJPY, USDCAD, USDCHF.

---

## Strategy Logic

Single-timeframe engulfing bar play with a limit re-entry.

- **Bullish engulf:** `current.low < prev.low` AND `current.close > prev.open`
- **Bearish engulf:** `current.high > prev.high` AND `current.close < prev.open`

**Entry:** Place a limit order at `entry_pct` (default 38.2%) into the engulfing bar's range from the extreme. For a BUY: `entry = bar.high - entry_pct * range`. Price must retrace back into the bar to fill.

**SL:** Previous bar's violated extreme — the liquidity that was swept.
- BUY: `prev.low`
- SELL: `prev.high`

**TP:** Risk manager calculates at R:R ratio (default 2:1). Not set on Signal.

**Filters:**
- `min_range_pips`: skip engulfing bars smaller than this (key parameter — spread is a large % of small bars)
- `max_sl_pips`: skip if SL distance exceeds this (default 80 pips)
- `tf_trend` / `ema_fast` / `ema_slow`: optional higher-TF EMA trend filter

**Cancel conditions:**
- New engulfing bar forms while pending is live: cancel old, defer new signal one bar
- TP level reached before fill: if price hits the 2R target but order was never filled, cancel

---

## Walk-Forward History

### Walk-forward 1 (2026-03-23) — FAIL

Config: H4 entry, D1 EMA trend filter, entry_pct=0.382
Param grid: min_range_pips [40, 60, 80], ema_fast [10, 20], ema_slow [20, 50]
4yr train / 2yr test / 2yr step

| Fold | Test period | IS R | OOS R | OOS Expect | OOS WR | OOS PF | Retain |
|------|-------------|------|-------|------------|--------|--------|--------|
| 1 | 2019–2021 | +13.1 | +12.6 | +0.194 | 41.5% | 1.33 | 167% ✓ |
| 2 | 2021–2023 | +31.3 | -22.7 | -0.256 | 25.8% | 0.66 | -96% ✗ |
| 3 | 2023–2025 | +13.7 | -8.3 | -0.051 | 33.5% | 0.92 | -134% ✗ |
| **Agg** | | | **-18.4R** | **-0.058R** | | | **-21%** |

**Verdict: FAIL.** Fold 1 was carrying the full-sample positive result. Folds 2 and 3 fall apart — fold 2 win rate collapsed to 25.8% (-22.7R OOS). Strategy is not robust across market regimes.

---

## Parameter Sweep History

### Sweep 1 — min_range_pips × entry_pct (2026-03-23)

Grid: TF [D1, H4, H1], min_range [0, 10, 20, 30, 40, 60], entry_pct [0.25, 0.382, 0.50]
All combos used max_sl_pips=80.

Key findings:
- **min_range_pips=60 is the critical threshold** — below it, the 2-pip spread is too large a fraction of the bar range and eats into avg win R
- Only two combos went positive: H4/rng=60/ep=0.382 (+30R, +0.016R expect) and H1/rng=60/ep=0.25 (+3.4R, barely positive)
- D1 never went positive at any setting
- H1 with trend filter hurt rather than helped (win rate dropped to 32-34%)
- Avg win was consistently 1.5–1.87R (never reaching the theoretical 2.0R) due to spread

### Sweep 2 — EMA trend filter (2026-03-23)

Grid: H4 entry + D1 trend, min_range [40, 60, 80], EMA combos [(10,20), (20,50), (50,200), off]

Best result: H4/D1, min_rng=60, EMA 10/20 → 961 trades, 36.7% WR, +35.7R, +0.037R expect, MaxDD 40.5R
- D1 EMA filter halved max drawdown vs no filter (40.5R vs 82R)
- 10/20 EMA marginally outperformed 20/50 and 50/200

This was taken to walk-forward and failed (see above).

---

## Spread Impact Analysis

For a BUY LIMIT order with 2-pip spread:
- Fill price = signal entry + 2 pips
- Reward to TP shrinks by 2 pips; risk to SL grows by 2 pips
- On a 92-pip SL trade: costs ~0.05R. On a 20-pip SL: costs ~0.20R per winner
- This is why H1 (smaller bars) is hardest to make work and why min_range_pips=60 is the threshold

---

## Full-Sample Baseline Results (2026-03-23, pre-filter)

| TF | Trades | WR | Total R | Expectancy | Avg Win |
|----|--------|----|---------|-----------:|---------|
| D1 | 1,682 | 33.3% | -91.3R | -0.05R | 1.84R |
| H4 | 6,252 | 35.0% | -461.8R | -0.07R | 1.65R |
| H1 | 3,651 | 33.7% | -572.8R | -0.16R | 1.50R |

---

## Root Cause Assessment

The strategy's ~33-36% win rate is structurally insufficient to overcome spread + commission, even targeting 2R. The limit entry raises win rate slightly vs a market entry (fills only happen on retraces) but not enough. The underlying engulfing bar pattern produces real directional signal (fold 1 is genuine) but not consistently across all market regimes.

---

## Next Steps

- [ ] Re-evaluate if trading on indices or gold (wider ranges, same absolute spread cost) improves the R math
- [ ] Consider adding a volatility expansion confirmation (e.g. only take engulfs on bars that break the last N-bar ATR) to further filter for high-quality setups
