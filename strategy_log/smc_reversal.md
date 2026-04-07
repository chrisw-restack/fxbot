# SmcReversalStrategy

## Summary

ICT-style SMC reversal strategy for US equity indices (USTEC/US30/US500). Requires D1 bias via SSL/BSL sweep, multi-timeframe OB confluence (M15 always required + at least one of H4/H1), and a 5M engulfing entry bar during the NY morning killzone (9:45–11:00 AM ET).

**Status: SHELVED** — Walk-forward FAIL on both NAS100-only and 3-symbol (NAS100+DOW+SPX) runs. Regime-dependent: folds covering COVID crash and rate-hike periods lose badly OOS; only 2024–2026 fold is positive. Likely reflects discretionary setup that requires current market context (trending/recovering) that cannot be systematically captured.

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

## Walk-Forward Validation — Run 1: NAS100 only

**Settings:** 3 folds, 4yr train / 2yr test / 2yr step, symbol=USTEC, min_trades=15, metric=expectancy. Grid: 162 combos.

| Fold | OOS Period | IS Trades | IS Exp | OOS Trades | OOS Exp | OOS WR | OOS PF | Retention |
|------|-----------|-----------|--------|-----------|---------|--------|--------|-----------|
| 1 | 2020–2022 | 18 | +0.167R | 11 | -0.455R | 18.2% | 0.44 | -272% |
| 2 | 2022–2024 | 27 | +0.000R | 10 | -0.100R | 30.0% | 0.86 | N/A |
| 3 | 2024–2026 | 74 | +0.135R | 25 | +0.200R | 40.0% | 1.33 | +148% |
| **Agg** | | | | **46** | **-0.022R** | **32.6%** | | **-62%** |

FAIL. Fold 1/2 had too few IS trades (18–27) to find real edge in a 162-combo grid.

---

## Walk-Forward Validation — Run 2: USTEC + US30 + US500

Parameters converted to price-relative (pct-based) for multi-symbol scaling.

**Sweep (all data 2016–2026, 3 symbols, 216 combos):**

Best IS combo: `frac=2, fvg_w=2, wiggle=0.6%, sl_buf=0.1%, multi=N`
→ 169 trades, 39.1% WR, +29R total, PF 1.28, +0.172R expectancy, MaxDD 10R

**Walk-forward:** 3 folds, 4yr train / 2yr test / 2yr step, min_trades=30, 216 combos.

| Fold | OOS Period | IS Trades | IS Exp | OOS Trades | OOS Exp | OOS WR | OOS PF | Retention |
|------|-----------|-----------|--------|-----------|---------|--------|--------|-----------|
| 1 | 2020–2022 | 56 | +0.232R | 32 | -0.344R | 21.9% | 0.56 | -148% |
| 2 | 2022–2024 | 56 | +0.125R | 21 | -0.286R | 23.8% | 0.62 | -229% |
| 3 | 2024–2026 | 36 | +0.333R | 20 | +0.050R | 35.0% | 1.08 | +15% |
| **Agg** | | | | **73** | **-0.219R** | **27.4%** | | **-121%** |

FAIL. Aggregate OOS -0.219R, -16R total. Params inconsistent across folds (`fvg=4` vs `fvg=2` vs `fvg=2`; `frac=2` vs `frac=2` vs `frac=5`).

**Regime-dependent pattern:** Fold 3 OOS (2024–2026) shows faint positive edge (+0.050R). Folds 1 and 2 covering COVID crash and 2022 rate hike period collapse to ~22-24% WR — well below the ~33% breakeven at 2:1 RR. The setup may be context-dependent in ways that a 2-bar entry trigger cannot systematically capture.

---

## Root Cause

The strategy's signal quality degrades severely in volatile/choppy/trending-against regimes (COVID 2020, rate hike 2022). In those periods OBs get violated quickly and engulf signals fail. The 9:45–11 AM ET killzone alone is not sufficient to filter regime. Each fold selects different optimal params, suggesting the optimizer is finding noise, not signal.

---

## Conclusion

The setup is sound for discretionary hand-trading where the trader reads current macro regime, correlated timeframe structure, and news context before entering. The 2026-03-18 live winner (2R, NAS100) is an example of correct discretionary use. But codifying regime-selection into the strategy has proven insufficient, and the systematic version lacks the robustness to pass walk-forward across different market conditions over a 10-year period.

**Discretionary use only.**

---

## History

- **2026-03-18**: Live trade on USTEC — BUY, entered at 2:1 killzone confirmation, hit 2R TP. Setup: D1 LONG bias, H4+M15 OB confluence, 9:45 AM NY open signal.
- Strategy built from scratch. Logic iterations: any 2-of-3 confluence (281 trades) → M15 required + day reset fix (234 trades) → FVG validation (199 trades on USTEC alone).
- Run 1 sweep: USTEC only, 288 combos. Best IS: +0.220R, 59 trades/10yr.
- Run 1 WF: FAIL (2026-04-01). Too few IS trades.
- Expanded to US30+US500. Parameters converted to pct-based for cross-symbol scaling.
- Run 2 sweep: 3 symbols (USTEC/US30/US500), 216 combos. Best IS: +0.172R, 169 trades/10yr.
- Run 2 WF: FAIL (2026-04-02). Regime-dependent, OOS folds 1-2 collapse.
