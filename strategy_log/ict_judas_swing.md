# ICT Judas Swing

**Status:** SHELVED — sweep all negative (108 combos, best -0.024R expectancy)
**File:** `strategies/ict_judas_swing.py`
**Timeframes:** D1 (bias), M5 (entry)
**Order type:** MARKET

---

## Current Config

```python
IctJudasSwingStrategy(
    fractal_n=3,
    min_sl_pips=15,
    max_sl_pips=30,
    min_sweep_pips=2.0,
    require_sweep_pullback=True,
    require_fvg=False,
    require_d1_bias=False,
)
```

---

## Strategy Logic

ICT (Inner Circle Trader) concept: the market makes a false move (Judas Swing) against the true daily direction during the early London session to sweep liquidity, then reverses.

### Session timing
- **Asian session:** Tracks range (high/low) during Asian hours (approx 20:00–02:00 UTC, adjusted for US DST)
- **London session:** 03:00–08:00 UTC — look for sweep of Asian range
- **NY session:** 08:00–16:00 UTC — alternatively valid entry window

### Setup
1. Asian range established
2. **Sweep:** Price exceeds the Asian session high or low by at least `min_sweep_pips`
3. **Pullback** (if `require_sweep_pullback=True`): price pulls back inside the Asian range after the sweep
4. **MSS on M5:** A fractal swing break in the opposite direction of the sweep confirms entry
5. **FVG** (if `require_fvg=True`): an imbalance in the breakout leg strengthens the signal

**Entry:** MARKET at close of M5 MSS bar
**SL:** Session range extreme (the swept level)
**TP:** Risk manager default (2:1 R:R)

**Filters:**
- `min_sl_pips` / `max_sl_pips`: range constraints on SL distance
- `require_d1_bias`: if True, only take setups aligned with D1 EMA (10/20) trend direction — currently disabled
- Trades once per session (resets daily)

---

## Parameter Sweep (2026-03-26)

Grid: fractal_n [1,2,3], min_sl_pips [10,15,20], min_sweep_pips [1.0,2.0,5.0], require_sweep_pullback [True,False], require_fvg [True,False].
108 combinations. D1+M5, 8 symbols (7 FX + XAUUSD), 6M bars loaded.

**All 108 combinations negative.** Best: -0.024R expectancy, 8470 trades, 32.5% WR.

Top 5 by expectancy:

| fractal_n | min_sl | sweep | pullback | fvg | trades | WR | R | Expect |
|-----------|--------|-------|---------|-----|--------|-----|----|----|
| 3 | 20 | 2.0 | True | True | 8470 | 32.5% | -205R | -0.024 |
| 1 | 20 | 5.0 | True | True | 10918 | 32.5% | -268R | -0.025 |
| 1 | 20 | 2.0 | True | True | 11507 | 32.5% | -302R | -0.026 |
| 1 | 20 | 2.0 | False | True | 11455 | 32.5% | -295R | -0.026 |
| 3 | 20 | 1.0 | True | True | 8637 | 32.5% | -222R | -0.026 |

All combinations show WR ≈ 32.5%, stuck below the 33.3% break-even for 2:1 R:R. The strategy generates 8k–12k trades over 10 years but has no edge across any combination tested.

---

## Assessment

No edge. The session sweep + MSS concept produces frequent signals but WR is persistently ~32.5% regardless of parameter choice. Possible reasons:
- M5 fractals too noisy — MSS confirmation fires on noise, not genuine reversals
- Spread (2 pips) on M5 MARKET fills has outsized impact vs small M5 moves
- The Judas Swing may work better with limit entries at the FVG or tighter MSS confirmation

Note: Previously identified as deeply negative on 7-symbol dataset. Re-confirmed with 8 symbols.

---

## Next Steps

- [ ] No further testing — shelved
