# London Breakout Strategy (LBS)

**Status:** SHELVED — walk-forward FAIL
**File:** `strategies/london_breakout.py`
**Timeframes:** M5
**Order type:** PENDING
**Symbols tested:** EURUSD, GBPUSD (+ AUDUSD, USDJPY, USDCAD, USDCHF in sweep)

---

## Final Config

```python
LondonBreakoutStrategy(rr_ratio=1.5)
```

Range: NY midnight–2:55am (Asian session). Entry: NY 3:00–6:55am. Cancel: NY 7:00am.
SL: midpoint of range. TP: risk manager via rr_ratio.

---

## Strategy Logic

- **Range:** Accumulate M5 bar highs/lows from NY midnight to 2:55am (Asian session consolidation, 36 bars)
- **Lock:** Range locked at NY 3:00am (London open)
- **BUY:** First M5 close above range_high → PENDING at range_high, SL at range midpoint
- **SELL:** First M5 close below range_low → PENDING at range_low, SL at range midpoint
- **Cancel:** Unfilled pending cancelled at NY 7:00am
- One signal per day per symbol

---

## Development History

### Version 1 — Fractal SL (2026-04-24)

Initial spec: NY 3–3:55am range, fractal swing low/high as SL, RR 2.5.
Result: EURUSD + GBPUSD, -0.03R expectancy. No edge.

### Version 2 — EMA trend filter + body ratio filter (2026-04-24)

Added D1 EMA filter (fast/slow crossover for bias) and body ratio filter (close must be X× the body size).
81-combo sweep (fractal_n, ema_fast/slow, body_ratio) on EURUSD + GBPUSD.
Best combo: -0.007R. All negative.

### Version 3 — Range-midpoint SL, NY 3–4am range (2026-04-24)

Stripped all filters. SL = midpoint of range. Swept RR [1.0–3.0].
EURUSD + GBPUSD. All combos negative, best -0.009R at RR 3.0.
Root cause identified: NY 3am = UTC 8am is already mid-London session — no true pre-breakout consolidation.

### Version 4 — Shifted to Asian session range (2026-04-24)

Moved range window to NY midnight–2:55am (Asian session) and entry to NY 3–7am (London open).
EURUSD + GBPUSD, RR 1.5: **+0.029R expectancy, PF 1.05, 1,551 trades** — first positive result.

---

## Parameter Sweep History

### Sweep 1 — EUR/GBP only, Asian range (2026-04-24)

Grid: rr_ratio [1.0, 1.5, 2.0, 2.5, 3.0]. Symbols: EURUSD + GBPUSD.

| RR  | Trades | WR%  | Total R | PF   | Expectancy |
|-----|--------|------|---------|------|-----------|
| 1.5 | 1,551  | 41.7 | +45.6   | 1.05 | +0.029R   |
| 2.0 | 1,536  | 34.2 | +21.4   | 1.02 | +0.014R   |
| 1.0 | 1,557  | 51.3 | +18.5   | 1.02 | +0.012R   |
| 3.0 | 1,499  | 25.2 | -7.1    | 0.99 | -0.005R   |
| 2.5 | 1,516  | 28.6 | -16.9   | 0.98 | -0.011R   |

### Sweep 2 — 6 symbols, finer RR grid (2026-04-27)

Grid: rr_ratio [1.2–2.0]. Symbols: EURUSD, GBPUSD, AUDUSD, USDJPY, USDCAD, USDCHF.

All combos negative (best RR 2.0: -0.000R, PF 1.00). The edge does not generalise beyond EUR/GBP.

---

## Walk-Forward History

### Walk-forward 1 (2026-04-27) — FAIL

EUR/GBP only. Param grid: rr_ratio [1.3–2.0]. 4yr train / 2yr test / 2yr step. min_trades=30.

| Fold | Test period       | Best param | IS R   | OOS R  | OOS Expect | OOS WR | OOS PF | Retain |
|------|-------------------|------------|--------|--------|-----------|--------|--------|--------|
| 1    | 2020–2022         | rr=1.7     | +41.8  | +6.3   | +0.044R   | 39.2%  | 1.07   | 94%    |
| 2    | 2022–2024         | rr=1.7     | +9.9   | -42.3  | -0.094R   | 34.0%  | 0.86   | -495%  |
| 3    | 2024–2026         | rr=1.3     | -16.9  | +42.3  | +0.097R   | 48.4%  | 1.19   | N/A    |
| **Agg** |               |            |        | **+6.3R** | **+0.006R** |     |        | **FAIL** |

Fold 2 (2022–2024) blew up -42R — same high-volatility regime that hurt other strategies.
Fold 3 OOS positive but IS was negative, so OOS recovery is not attributable to the optimised params.

---

## Assessment

The Asian session range → London open entry is the only configuration that produced a positive IS edge on EUR/GBP (+0.029R, PF 1.05). However:
- The edge is pair-specific: adding AUDUSD/USDJPY/USDCAD/USDCHF turned all results negative
- Walk-forward failed due to fold 2 collapse in the 2022–2024 rate-hike regime
- Aggregate OOS is only +0.006R across 1,031 trades — statistically negligible

The London/Asian breakout concept works in some regimes and not others. Without a regime filter, it is not deployable.

## Next Steps

- [ ] No immediate plans — shelved
