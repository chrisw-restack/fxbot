# IMS (ICT Market Structure)

**Status:** SHELVED — walk-forward FAIL
**File:** `strategies/ims.py`
**Timeframes:** HTF + LTF (configurable; tested D1/H4, H4/H1, H4/M15)
**Order type:** PENDING

---

## Current Config (as of 2026-03-23)

```python
ImsStrategy(
    tf_htf='D1', tf_ltf='H4',
    fractal_n=1,          # 3-candle fractal on HTF
    ltf_fractal_n=2,      # 5-candle fractal on LTF
    htf_lookback=50,
    tp_mode='htf_high',
    cooldown_bars=0,
    ema_fast=20, ema_slow=50,
)
```

Symbols tested: EURUSD, GBPUSD, AUDUSD, NZDUSD, USDJPY, USDCAD, USDCHF.

---

## Strategy Logic

ICT-inspired multi-timeframe market structure strategy.

### HTF Bias
1. Identify a **dealing range**: swing low → running max high (BUY) or swing high → running min low (SELL)
2. The **50% level** of this range is the key zone
3. Bias is BUY when price is approaching the 50% from above (retracing into it)
4. HTF swing high updates dynamically as price makes new highs; bias expires if price closes below the swing low

### LTF Setup (once price enters the 50% zone)
1. Look for a **5-candle fractal swing** (2 bars each side) — a more meaningful MSS signal than a 3-candle fractal
2. Wait for price to **close above/below** the fractal swing extreme → LTF MSS confirmed
3. **Critical filter:** the LTF swing low (for BUY) must be at or below the HTF 50% level — the MSS must form from within the zone, not above it

**Entry:** PENDING at 50% of the LTF leg that formed the MSS
**SL:** LTF fractal swing extreme
**TP:** HTF swing high (tp_mode='htf_high') or risk manager 2R

**Filters:**
- HTF EMA 20/50: only take BUY when fast > slow on HTF
- LTF zone anchor: LTF swing origin must be at/below HTF 50% level (prevents false setups where price bounced back above the zone)
- FVG requirement in LTF leg (optional, currently enabled)

**Pending updates:** When a new LTF setup forms while one is already pending, emit CANCEL + defer new signal one bar.

---

## Walk-Forward History

### Walk-forward 1 — D1/H4 (2026-03-23) — FAIL

Config: fractal_n=1, ltf_fractal_n=2, ema_fast=20, ema_slow=50, tp_mode='htf_high'
Param grid: fractal_n [1, 2], htf_lookback [30, 50, 80], cooldown_bars [0, 3]
4yr train / 2yr test / 2yr step

| Fold | Test period | IS R | OOS R | OOS Expect | OOS WR | OOS PF | Retain |
|------|-------------|------|-------|------------|--------|--------|--------|
| 1 | 2019–2021 | +23.1 | -10.2 | -0.250 | 22.0% | 0.68 | -58% ✗ |
| 2 | 2021–2023 | +22.4 | +6.3 | +0.176 | 30.6% | 1.25 | 44% ~ |
| 3 | 2023–2025 | -3.8 | -20.6 | -0.624 | 9.1% | 0.31 | N/A ✗ |
| **Agg** | | | **-24.5R** | **-0.223R** | | | **-7%** |

**Verdict: FAIL.** Only fold 2 (2021–2023) showed genuine OOS edge. Fold 3 had no IS edge (training data was already negative) and OOS was severely negative. Too few trades (~17/year across 7 pairs) for reliable optimization.

---

## Parameter Sweep / Development History

### v1 — Initial D1/H4 (2026-03-23)
- First run: +32R full-sample, ~18 trades/year per 7 pairs
- Promising but modest

### v2 — Added EMA filter + 5-candle LTF fractal (2026-03-23)
- EMA 10/20 filter added first (per ema_fib approach), then changed to 20/50
- ltf_fractal_n=2 (5-candle) added to require more meaningful LTF MSS
- Result: +22R (down from +32R — filters removed some winning trades)

### v3 — LTF zone anchor fix (2026-03-23) — critical bug fix
- **Bug:** `_ltf_in_zone` flag was being set True on any price touch of the HTF 50% zone, even if price subsequently bounced well above it. Trades were being placed with LTF swing lows 30-40 pips above the 50% level.
- **Fix:** Added guard `if sl_price > bias['dealing_50']: return None` (BUY side). The LTF swing origin must be at or below the 50% level at the time of MSS — not just historically.
- Result: +20R (minor reduction, drawdown improved, fewer spurious trades)

### H4/H1 testing (2026-03-23)
- Initial: -220R → after EMA filter: -69R → after zone anchor fix: -44R
- Never got close to positive — too many low-quality LTF setups on H1

### H4/M15 testing (2026-03-23)
- Always negative across all parameter combinations — dropped early

---

## Stacks Tested

| Stack | Result | Notes |
|-------|--------|-------|
| D1/H4 | FAIL (walk-forward) | Only fold 2 positive OOS; too few trades |
| H4/H1 | Negative | Reduced to -44R with all filters, still negative |
| H4/M15 | Strongly negative | Dropped |

---

## Known Issues / Open Questions

- **Trade count problem:** D1/H4 generates ~17 trades/year across 7 pairs. With 4yr training windows that's only ~68 trades — too few for reliable parameter optimization. Walk-forward is noisy as a result.
- **Regime sensitivity:** The strategy clearly worked in 2021–2023 (fold 2) but failed before and after. Market structure setups may be era-dependent.
- **LTF fractal timing:** The 5-candle LTF fractal requires waiting 2 bars after the potential swing high, which may cause entry to be too late in fast-moving markets.

---

## Next Steps

- [ ] Consider testing with longer history (Dukascopy 10yr data) once available for more fold coverage
- [ ] Re-test D1/H4 with a reduced parameter grid focused on the fold-2-winning params (fractal_n=1, htf_lookback=30) as fixed params
