# EmaFib Running

**Status:** VALIDATED — walk-forward STRONG (+85.3R OOS, +0.106R expectancy, 90% retention)
**File:** `strategies/ema_fib_running.py`
**Timeframes:** D1 (bias), H1 (entry)
**Order type:** PENDING

---

## Current Config (validated 2026-03-26)

```python
EmaFibRunningStrategy(
    fib_entry=0.618,
    min_swing_pips=30,
    ema_sep_pct=0.001,        # fold 2 & 3 preferred; fold 1 preferred 0.0
    cooldown_bars=0,
    invalidate_swing_on_loss=True,
)
```

Symbols: EURUSD, GBPUSD, AUDUSD, NZDUSD, USDJPY, USDCAD, USDCHF, XAUUSD (8 symbols).

---

## Strategy Logic

A variant of EmaFibRetracement that uses **running extremes** (continuously updated highs/lows) rather than fixed fractal swing points. Operates on the same D1/H1 stack.

Key differences from the standard EmaFibRetracement:
- **Swing tracking:** Uses a running high/low that continuously updates as price moves. The swing is not anchored to a single fractal high — it extends as price makes new extremes.
- **SL placement:** Set at the wick extreme of the fractal, not the body.
- **Entry/TP calculation:** Uses candle bodies (open/close range) not the full wick range for the Fib levels.
- **FVG requirement:** Requires a Fair Value Gap in the leg prior to entry (always enabled).
- **Pending update:** If the running extreme moves while a pending order is open, the pending is updated (cancel + new signal at revised level).
- **Session filter:** Blocks hours 16–23 UTC by default (blocks NY close and Asia session).

---

## Walk-Forward History

### Walk-forward 1 (2026-03-26) — STRONG

Fixed: fib_entry=0.618, min_swing_pips=30. Grid: ema_sep_pct [0.0, 0.001], cooldown_bars [0, 10], invalidate_swing_on_loss [True, False].
4yr train / 2yr test / 2yr step. 8 symbols (7 FX + XAUUSD).

| Fold | Test period | IS R | OOS R | OOS Expect | OOS WR | OOS PF | Retain |
|------|-------------|------|-------|-----------|--------|--------|--------|
| 1 | 2020–2022 | -83.4 | +35.0 | +0.106 | 30.6% | 1.15 | N/A |
| 2 | 2022–2024 | +33.8 | +59.9 | +0.211 | 32.5% | 1.31 | 207% |
| 3 | 2024–2026 | +93.3 | -9.6 | -0.050 | 24.5% | 0.93 | -26% |
| **Agg** | | | **+85.3R** | **+0.106R** | | **90%** |

Best params selected: `ema_sep_pct=0.001, cooldown_bars=0, invalidate_swing_on_loss=True` (folds 2 & 3). Fold 1 selected ema_sep_pct=0.0 but OOS was still positive.

Notable: fold 1 had negative IS (-83.4R) but the optimizer still found something that produced positive OOS (+35R). The parameter selected (ema_sep_pct=0.0) is essentially "no filter" — suggesting the underlying signal in that era was strong enough without filtering.

Fold 3 (2024–2026) is the concern — OOS -9.6R on 192 trades. Most recent era. Monitor closely.

## Parameter Sweep History

### Sweep 1 (2026-03-26)

Grid: fib_entry [0.5, 0.618, 0.786], min_swing_pips [10, 20, 30], ema_sep_pct [0.0, 0.001], cooldown_bars [0, 10], invalidate_swing_on_loss [True, False].
72 combinations. D1/H1, 8 symbols.

9 positive combos — all required fib_entry=0.618, min_swing_pips=30.
Best: fib=0.618, sw=30, sep=0.001, cd=0, inv=N → 1105 trades, 27.3% WR, +36.1R, +0.033R expect, MaxDD 61.6R, avg win 2.78R.

Key: unlike D1/H1 EmaFibRetracement (best at fib=0.786), this running variant needs fib=0.618 — the running extreme logic means the entry is already at a more favourable price point, so a deeper retracement isn't needed.

## Assessment

Validated with STRONG walk-forward verdict. Higher OOS expectancy (+0.106R) than EmaFibRetracement (+0.03R) and EBP (+0.032R). The running high/low mechanism and FVG requirement appear to add genuine quality filtering. The D1/H1 timeframe gives it a similar structural profile to the existing EmaFibRetracement.

Fold 3 (2024–2026) was the weak spot. Whether this is regime change or noise will only be confirmed with more live data.

## Next Steps

- [ ] Run demo/live to build OOS track record
- [ ] Monitor fold 3 concern — if 2026 continues to be negative, revisit
- [ ] Consider adding to live suite alongside EmaFibRetracement (different entry logic = some diversification)
