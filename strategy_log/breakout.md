# Breakout

**Status:** SHELVED — walk-forward FAIL
**File:** `strategies/breakout.py`
**Timeframes:** H1
**Order type:** MARKET

---

## Current Config

```python
BreakoutStrategy(lookback=20)
```

---

## Strategy Logic

Simple N-bar channel breakout.

- **BUY:** Close above the highest high of the previous `lookback` bars
- **SELL:** Close below the lowest low of the previous `lookback` bars
- **SL:** Lowest low (BUY) / Highest high (SELL) of the lookback window
- **TP:** Risk manager default (2:1 R:R)
- Suppresses re-entry in the same direction on consecutive bars

No filters. No multi-timeframe logic.

---

## Walk-Forward History

### Walk-forward 1 (2026-03-24) — FAIL

Param grid: lookback [50, 100, 150, 200]. 4yr train / 2yr test / 2yr step. Symbols: 7 FX pairs + XAUUSD.

| Fold | Test period | IS R | OOS R | OOS Expect | OOS WR | Retain |
|------|-------------|------|-------|-----------|--------|--------|
| 1 | 2020–2022 | +38.0 | +1.0 | +0.010 | 33.7% | 6% |
| 2 | 2022–2024 | +7.0 | -24.0 | -0.174 | 27.5% | -580% |
| 3 | 2024–2026 | -11.0 | -1.0 | -0.008 | 33.1% | N/A |
| **Agg** | | | **-24R** | **-0.067R** | | **FAIL** |

lookback=100 selected by optimizer in all 3 folds.

## Parameter Sweep History

### Sweep 1 (2026-03-24)

Grid: lookback [5, 10, 20, 30, 50, 100]. H1, 8 symbols (7 FX + XAUUSD).

| Lookback | Trades | WR | Total R | Expectancy |
|----------|--------|----|---------|-----------|
| 100 | 561 | 35.8% | +42R | +0.075R |
| 50 | 1,243 | 32.8% | -19R | -0.015R |
| 20 | 2,945 | 32.3% | -92R | -0.031R |
| 5 | 7,444 | 31.1% | -502R | -0.067R |

Clear pattern: longer lookback → higher WR → better results. But walk-forward showed this is a regime effect, not a robust edge.

## Assessment

The full-sample +42R at lookback=100 was driven almost entirely by the 2016–2020 training era. Out-of-sample performance collapsed in 2022–2024. Simple N-bar channel breakouts on forex produce too many false breakouts without additional filtering (trend context, volatility squeeze, session timing).

## Next Steps

- [ ] No immediate plans — shelved
