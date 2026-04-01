# EBP (Engulfing Bar Play)

**Status:** INCONCLUSIVE — real IS edge found, WF WEAK on both stacks (too few OOS trades for reliable verdict). Not in live suite.
**File:** `strategies/ebp.py`
**Timeframes:** H1 (bias), M15 (entry) — best stack after full sweep
**Order type:** MARKET

---

## Current Config (as of 2026-03-30)

```python
EbpStrategy(
    tf_bias='H1',
    tf_entry='M15',
    fractal_n=1,
    min_retrace_pct=0.1,
    max_retrace_pct=0.5,
    require_fvg=False,
    sl_mode='mss_bar',
)
```

Symbols: EURUSD, GBPUSD, AUDUSD, NZDUSD, USDJPY, USDCAD, USDCHF + XAUUSD (8 symbols).

**Changed from 2026-03-22 config:**
- `tf_bias` H4→H1, `tf_entry` H1→M15 (more frequency)
- `sl_mode` structural→mss_bar (single biggest lever — avg +0.077R improvement)
- `max_retrace_pct` 0.618→0.5 (tighter zone exit)
- `require_fvg` False unchanged (FVG filter confirmed to add no value on M15)
- Added `blocked_hours` parameter to strategy (sweep showed session filter hurts EBP — leave empty)

IS 2016–2026 (8 symbols): 88 trades, 46.6% WR, +40.5R, PF 1.86, +0.460R expect, MaxDD 12.3R.

---

## Strategy Logic

### Bias (H1)
A **bullish engulfing bar** when:
- `current.low < prev.low` (extends below previous bar)
- `current.close > prev.open` (closes above previous bar's open — not the high)

Bearish is the mirror.

### Retracement zone (M15 entry)
After the H1 engulfing bar closes, wait for M15 price to pull back into the engulfing bar's range:
- **Zone entry** (min retrace = 10% level): price must trade through this
- **Zone exit** (max retrace = 50% level): price closing beyond this invalidates the bias

Valid zone = 10%–50% retracement. Midpoint filter rather than the Fibonacci golden pocket.

### Entry — Market Structure Shift (MSS)
Once in zone:
1. A **confirmed swing high** on M15 (`fractal_n=1` — 1 bar each side)
2. Current bar closes above that swing high → MSS confirmed
3. `require_fvg=False` — no FVG filter

**Entry:** MARKET at MSS bar close (fills next bar open)
**SL:** Low of the MSS bar itself (`sl_mode='mss_bar'`) — tighter than structural swing low
**TP:** H1 engulfing bar high (fixed — set on Signal, overrides risk manager)

### Why `mss_bar` SL beats `structural`
Structural SL = prior confirmed swing low. This can be far below entry, giving poor R:R geometry.
MSS bar SL = low of the bar that broke the swing high. Tighter, more logical: if that specific bar's low is violated, the MSS is invalidated.

### Bias expiry conditions
- New H1 engulfing bar forms (bias replaced)
- M15 bar closes beyond the 50% level (too deep)
- Price reaches engulf high/low on either TF (TP level reached)
- Trade closes at SL (`notify_loss`)

---

## Code Correctness (reviewed 2026-03-30)

Logic is correct — no look-ahead bias:
- MSS swing highs use `range(fn, n-fn-1)` — confirmed highs exist before current bar
- FVG detection uses closed bars only
- Entry at `current.close`, fills next open
- `blocked_hours` parameter added 2026-03-30; sweep confirmed session filter hurts — leave as default `()`

---

## Full IS Backtest (2026-03-30, H1/M15 config, 8 symbols, 2016–2026)

| Metric | H1/M15 (new) | H4/H1 original | H4/H1 new params |
|--------|-------------|----------------|-----------------|
| Trades | 88 | 30 | 47 |
| Win rate | 46.6% | ~35% | 51.1% |
| Total R | +40.5R | ~+0.2R | +22.4R |
| PF | 1.86 | ~1.0 | 1.97 |
| Expectancy | +0.460R | +0.008R | +0.476R |
| MaxDD | 12.3R | — | 4.9R |

The original config (H4/H1, structural SL, no FVG) was essentially breakeven. The new params unlock the edge.

---

## Walk-Forward History

### WF 1 (2026-03-22) — previously labelled STRONG, now superseded

See below. Original WF was unreliable: ~6–8 OOS trades per fold, near-zero IS R values. Superseded by WF 2 with correct params.

---

### WF 2 — H4/H1 (2026-03-30) — WEAK

Config: fn=1–3, max_retrace=[0.5, 0.618, 0.75], require_fvg=[T,F], sl_mode=[mss_bar, structural], 36 combos.
min_trades threshold: 15 (lowered from 50 — H4/H1 only generates ~5 trades/year).

| Fold | Test | Best params | IS R | OOS R | IS Exp | OOS Exp | OOS WR | OOS PF | Retain |
|------|------|-------------|------|-------|--------|---------|--------|--------|--------|
| 1 | 2019–2021 | fn=1, max=0.618, FVG=Y, mss_bar | +19.0 | +10.9 | +0.577 | +0.729 | 53.3% | 2.56 | 126% |
| 2 | 2021–2023 | fn=1, max=0.618, FVG=Y, mss_bar | +24.3 | -0.1 | +0.639 | -0.005 | 27.3% | 0.99 | -1% |
| 3 | 2023–2025 | fn=2, max=0.5, FVG=N, mss_bar | +6.6 | -1.3 | +0.332 | -0.217 | 33.3% | 0.68 | -65% |
| **Agg** | | | | **+9.5R** | | **+0.221R** | | | **20%** |

OOS trades: 15 / 22 / 6 (total 43). Fold 3 only 6 OOS trades — unreliable.
**Verdict: WEAK**

---

### WF 3 — H1/M15 (2026-03-30) — WEAK

Config: same grid as H4/H1 above. 36 combos.
min_trades threshold: 25.

| Fold | Test | Best params | IS R | OOS R | IS Exp | OOS Exp | OOS WR | OOS PF | Retain |
|------|------|-------------|------|-------|--------|---------|--------|--------|--------|
| 1 | 2020–2022 | fn=1, max=0.5, FVG=N, mss_bar | +35.4 | +2.7 | +0.863 | +0.269 | 50.0% | 1.54 | 31% |
| 2 | 2022–2024 | fn=1, max=0.5, FVG=N, mss_bar | +13.8 | +12.4 | +0.477 | +0.621 | 55.0% | 2.38 | 130% |
| 3 | 2024–2026 | fn=1, max=0.5, FVG=N, mss_bar | +15.1 | -9.0 | +0.504 | -0.565 | 18.8% | 0.30 | -112% |
| **Agg** | | | | **+6.1R** | | **+0.133R** | | | **16%** |

OOS trades: 10 / 20 / 16 (total 46).
**Verdict: WEAK**

**Positive signal:** All 3 folds chose identical params (fn=1, max=0.5, no FVG, mss_bar) — consistent optimization across different time windows indicates a structural feature, not noise. Compare H4/H1 where fold 3 diverged.

**Fold 3 concern (both stacks):** 2021–2023 (H4/H1) and 2024–2026 (H1/M15) both failed OOS. EmaFibRunning also had a weak recent fold. Could be a genuine regime shift in recent years, or statistical noise given tiny OOS samples (6–16 trades).

---

## Full Sweep Results (2026-03-30)

972 combos: 3 stacks × fractal_n[1,2,3] × zone[9 combos] × FVG[T,F] × sl_mode[3] × session[2].

**Key findings:**
- `sl_mode='mss_bar'` avg +0.064R vs `structural` avg -0.013R vs `symmetric` avg -0.009R. Single biggest lever.
- `max_retrace=0.5` best for H1/M15. Tighter zone exit = more selective entries.
- `max_retrace=0.618` best for H4/H1 with FVG required.
- Session filter (09:00–19:00 UTC) **hurts** EBP: -0.014R (H4/H1), -0.133R (H1/M15). Do NOT apply.
- `require_fvg=True` improves H4/H1 quality but adds no value for H1/M15 (more noise at M15).
- D1/H4 stack: avg 13 IS trades, not enough data.
- H1/M15 generates avg 119 trades, max 1243 across all combos — sufficient frequency.

**Top H4/H1 result:** fn=2, max=0.618, FVG=Y, mss_bar → 47 trades, 51.1% WR, +22.4R, PF 1.97, +0.476R
**Top H1/M15 result:** fn=1, max=0.5, FVG=N, mss_bar → 88 trades, 46.6% WR, +40.5R, PF 1.86, +0.460R

---

## Stacks Tested

| Stack | IS trades (best config) | WF verdict | Notes |
|-------|------------------------|------------|-------|
| D1/H4 | ~20 | Not run | Too few trades |
| H4/H1 | 47 | WEAK | Fold 1 strong, folds 2-3 fail |
| H4/M15 | — | FAIL (prior) | All combos negative |
| H1/M15 | 88 | WEAK | Consistent params all 3 folds; fold 3 fails |

---

## Known Issues

- **Fold 3 regime concern:** Both H4/H1 and H1/M15 fail OOS in the most recent period. Possibly genuine recent-market regime shift.
- **OOS sample too small:** 6–22 OOS trades per fold. Can't reliably distinguish edge from noise at these sizes.
- **mss_bar SL is tighter but not structural:** Strategy is technically correct, but the MSS bar low can be very close to entry for fractal_n=1, potentially getting stopped out by spread/noise.

---

## Path Forward

- **Run H1/M15 config on demo** — at 8-10 trades/year this gives 50+ trades in ~5 years, or maybe 1-2 years if signals cluster.
- **Do NOT add to live suite yet.** WEAK WF on both stacks.
- **Reassess after 50+ demo trades.** If OOS expectancy is positive, could promote to MODERATE.

## Next Steps

- [ ] Start demo trading H1/M15 config (new params)
- [ ] After 50+ demo trades, re-run WF and update verdict
- [ ] Monitor whether fold 3 regime issue persists or was transient
