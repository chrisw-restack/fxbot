# SmcReversalStrategy

## Summary

ICT-style SMC reversal strategy for NAS100 (USA100). Requires D1 bias via SSL/BSL sweep, multi-timeframe OB confluence (M15 always required + at least one of H4/H1), and a 5M engulfing entry bar during the NY morning killzone (9:45–11:00 AM ET).

**Status: SHELVED** — Walk-forward FAIL. Aggregate OOS -0.022R. Root cause: too few trades per window for reliable optimisation.

---

## Strategy Logic

- **D1 bias**: LONG on wick below fractal low + close back above (SSL sweep); invalidated by wick above fractal high or close below fractal low
- **Order Block**: last consecutive series of non-opposing candles before a displacement; zone = bodies only (open/close). Validated by FVG forming within `fvg_window` candles after the series
- **Confluence**: M15 OB always required + at least 1 of H4 or H1 OB overlapping within `wiggle_room_points`
- **M15 OBs**: reset each new trading day; H4/H1 OBs persist until mitigated (close through OB.low/high)
- **Entry**: M5 engulfing bar (close > prev.open AND close > open) while price is in confluence zone, 9:45–11:00 AM ET only
- **SL**: lowest low while in confluence zone minus `sl_buffer_points`

---

## Parameter Sweep

Grid: `fractal_n` [2,3,5] × `fvg_window` [2,4,6,8] × `wiggle_room_points` [0,25,50,100] × `sl_buffer_points` [5,10,20] × `multiple_trades_per_bias` [True,False] = 288 combinations. 254 met ≥30 trades threshold.

**IS best (all data 2016–2026):**

| fractal_n | fvg_window | wiggle | sl_buf | multi | Trades | WR% | Total R | PF | Expectancy | MaxDD |
|-----------|------------|--------|--------|-------|--------|-----|---------|-----|-----------|-------|
| 2 | 2 | 100 | 10 | N | 59 | 40.7% | +13.0 | 1.37 | +0.220R | 7R |
| 2 | 2 | 50 | 10 | N | 51 | 37.3% | +6.0 | 1.19 | +0.118R | 8R |
| 5 | 6 | 0 | 20 | Y | 148 | 35.1% | +8.0 | 1.08 | +0.054R | 21R |

Key pattern: `multiple_trades_per_bias=False` dominates the top of IS tables with higher expectancy but very low trade counts (~5–6/yr). `multi=True` produces more trades (140–190/10yr) but lower expectancy.

---

## Walk-Forward Validation

**Settings:** 3 folds, 4yr train / 2yr test / 2yr step, symbol=USA100, min_trades=15, metric=expectancy. Grid: 162 combos.

| Fold | OOS Period | IS Trades | IS Exp | OOS Trades | OOS Exp | OOS WR | OOS PF | Retention |
|------|-----------|-----------|--------|-----------|---------|--------|--------|-----------|
| 1 | 2020–2022 | 18 | +0.167R | 11 | -0.455R | 18.2% | 0.44 | -272% |
| 2 | 2022–2024 | 27 | +0.000R | 10 | -0.100R | 30.0% | 0.86 | N/A |
| 3 | 2024–2026 | 74 | +0.135R | 25 | +0.200R | 40.0% | 1.33 | +148% |
| **Agg** | | | | **46** | **-0.022R** | **32.6%** | | **-62%** |

**Best IS params per fold:**
- Fold 1: `frac=2, fvg=4, wiggle=50, sl=10, multi=False`
- Fold 2: `frac=2, fvg=2, wiggle=100, sl=10, multi=False`
- Fold 3: `frac=5, fvg=6, wiggle=0, sl=20, multi=True`

**Interpretation: FAIL.** Aggregate OOS loses money. Params inconsistent across folds (classic curve-fit signature). Fold 1 and 2 had only 18–27 IS trades — statistically insufficient to find a real edge in a 162-combo grid.

---

## Root Cause

Single-symbol single-session selectivity. The setup fires ~5–6 times/year for `multi=False` or ~15/yr for `multi=True` on NAS100. With 4yr IS windows this gives 20–27 trades (multi=False) or ~60 (multi=True) — too few for reliable parameter selection, especially fold 1/2 which are pre-2022.

---

## Options for Revival

1. **Expand to USA30 and USA500** — running all 3 major US indices together would approximately triple trade count. The ICT OB logic should transfer across correlated indices.
2. **Loosen confluence** — allow H4+H1 without requiring M15, which was the original design. More trades but slightly lower quality.
3. **Discretionary use only** — the setup logic is well-specified for hand-trading (validated with a 2R winner on 2026-03-18). Systematic validation may not be feasible given inherent selectivity.

---

## History

- **2026-03-18**: Live trade on USA100 — BUY, entered at 2:1 killzone confirmation, hit 2R TP. Setup: D1 LONG bias, H4+M15 OB confluence, 9:45 AM NY open signal.
- Strategy built from scratch during Claude session. Multiple logic iterations:
  1. Original: any 2-of-3 HTF confluence → 281 trades IS
  2. M15 always required + day reset fix → 234 trades IS
  3. FVG validation replaces engulfing displacement → 199 trades IS
- Parameter sweep: 288 combos, 254 qualifying. Best IS: `frac=2, fvg=2, wiggle=100, multi=False` → +0.220R expectancy, 59 trades/10yr
- Walk-forward: FAIL (2026-04-01)
