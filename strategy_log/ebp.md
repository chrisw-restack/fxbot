# EBP (Engulfing Bar Play)

**Status:** VALIDATED — walk-forward STRONG, not yet in live suite
**File:** `strategies/ebp.py`
**Timeframes:** H4 (bias), H1 (entry)
**Order type:** MARKET

---

## Current Config (as of 2026-03-22)

```python
EbpStrategy(
    tf_bias='H4',
    tf_entry='H1',
    fractal_n=2,
    min_retrace_pct=0.382,
    max_retrace_pct=0.618,
    require_fvg=False,
)
```

Symbols: EURUSD, GBPUSD, AUDUSD, NZDUSD, USDJPY, USDCAD, USDCHF (7 pairs).

---

## Strategy Logic

### Bias (H4)
A **bullish engulfing bar** when:
- `current.low < prev.low` (extends below previous bar)
- `current.close > prev.open` (closes above previous bar's open — not the high)

Bearish is the mirror (`current.high > prev.high` AND `current.close < prev.open`).

### Retracement zone (H1 entry)
After the H4 engulfing bar closes, wait for H1 price to pull back into the engulfing bar's range:
- **Zone entry** (min retrace = 38.2% level): price must trade through this to enter the zone
- **Zone exit** (max retrace = 61.8% level): price closing beyond this invalidates the bias

Valid zone = 38.2%–61.8% retracement — the Fibonacci golden pocket.

### Entry — Market Structure Shift (MSS)
Once price is in the zone, look for:
1. A **confirmed swing high** on H1: bar[i].high is higher than all bars within `fractal_n=2` bars on each side
2. The **current bar closes above** that swing high → MSS confirmed
3. `require_fvg=False` — FVG in the bullish leg is NOT required (it was removed after sweeping showed it filtered too many valid setups)

**Entry:** MARKET at close of MSS bar
**SL:** Most recent confirmed swing low on H1
**TP:** H4 engulfing bar high (fixed level — set on Signal, overrides risk manager R:R)

### Bias expiry conditions
- New H4 engulfing bar forms (bias replaced)
- H1 bar closes below the 61.8% level (retracement too deep)
- Price reaches engulf high/low on either TF (TP level reached, setup stale)
- Trade closes at SL (`notify_loss`)

---

## Walk-Forward History

### Walk-forward 1 (2026-03-22) — STRONG

Param grid: fractal_n [2,3], min_retrace [0.1, 0.25, 0.382], max_retrace [0.5, 0.618, 0.75], require_fvg fixed=False
4yr train / 2yr test / 2yr step

| Fold | Test period | IS R | OOS R | OOS Expect | OOS PF | Retain |
|------|-------------|------|-------|------------|--------|--------|
| 1 | 2019–2021 | +0.0 | -5.0 | -0.085 | 0.88 | N/A |
| 2 | 2021–2023 | +1.0 | +3.0 | +0.091 | 1.14 | 569% |
| 3 | 2023–2025 | +3.0 | +6.0 | +0.182 | 1.30 | 404% |
| **Agg** | | | **+4.0R** | **+0.032** | | **STRONG** |

Best params selected: `fractal_n=2, min_retrace=0.382, max_retrace=0.618` (consistent across folds 2 and 3).

**Notes:**
- Fold 1 lost -5R OOS. The training window (2015–2019) found no IS edge (expect=0.000), so this fold had nothing to generalise. Strategy may not have worked well in that era.
- Folds 2 and 3 both show OOS *outperforming* in-sample — a strong sign.
- WR improves OOS each fold: 30.5% → 36.4% → 39.4%.
- Aggregate OOS expectancy (+0.032R) is modest but real and positive.

---

## Parameter Sweep History

### Sweep 1 — D1/H4, with/without FVG (2026-03-22)
- D1/H4 breakeven at best — 59 trades over 9 years, +1R total
- FVG pending variant consistently underperformed MARKET
- Trade count too low to be conclusive

### Sweep 2 — D1/H4, FVG required vs not (2026-03-22)
- Dropping FVG requirement (`require_fvg=False`) improved results across the board
- Best D1/H4 config: fractal_n=1, min=0.382, max=0.5, no FVG — 40 trades, +8R, PF 1.33, Expect +0.200
- Still only 40 trades in 9 years — too few

### Sweep 3 — H4/H1 and H4/M15 (2026-03-22)
- **H4/M15: every combo negative — dropped**
- **H4/H1: clear edge**, especially with fractal_n=2 or 3
- Top configs: fractal_n=3, max=0.618, no FVG → 66 trades, PF 1.47, Expect +0.273, MaxDD 6R
- Walk-forward selected fractal_n=2 (better sample size in train windows)
- Key finding: max_retrace=0.618 is the critical filter. The Fibonacci golden pocket (38.2%–61.8%) outperforms wider or narrower zones.
- `min_retrace_pct` has minimal effect — 0.1, 0.25, 0.382 all give similar results

---

## Stacks Tested

| Stack | Result | Notes |
|-------|--------|-------|
| D1/H4 | Marginal / breakeven | Too few trades (~6/year), small edge |
| H4/M15 | Negative across all combos | Dropped |
| H4/H1 | **VALIDATED** | Current config |

---

## Known Issues / Open Questions

- Fold 1 (2019–2021) is the weak spot — strategy had no IS edge in the 2015–2019 training window. Worth monitoring whether this was an era-specific issue or a structural weakness.
- Aggregate OOS expectancy (+0.032R) is modest — real but not high-confidence. More OOS data needed over time (live performance).
- `require_fvg=False` was chosen after sweeping. The original strategy concept included FVG as a quality filter — could be worth revisiting once more trades accumulate.
- FVG pending entry tested on H4/H1 (2026-03-23): 151 trades, -17.1R, PF 0.83, avg win 1.73R. Worse than MARKET because the FVG entry is higher in the structure, shrinking win R while loss stays at -1R. **FVG pending rejected for H4/H1 — use MARKET only.**

---

## Next Steps

- [ ] Monitor live/demo performance to build OOS track record
- [ ] After 50+ live trades, assess whether adding back `require_fvg=True` improves quality
- [ ] Consider adding to live suite once demo results confirm backtest edge
