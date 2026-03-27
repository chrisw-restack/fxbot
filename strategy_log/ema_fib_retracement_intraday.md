# EmaFibRetracement Intraday

**Status:** SHELVED — walk-forward FAIL (severe curve-fit)
**File:** `strategies/ema_fib_retracement_intraday.py`
**Timeframes:** H4 (bias), M15 (entry)
**Order type:** PENDING

---

## Current Config

```python
EmaFibRetracementIntradayStrategy(
    cooldown_bars=10,
    invalidate_swing_on_loss=True,
    min_swing_pips=15,
    ema_sep_pct=0.0005,
)
```

---

## Strategy Logic

A tighter, intraday variant of the EmaFibRetracement strategy, operating on H4/M15 instead of D1/H1.

- **Bias:** H4 EMA crossover (fast=10, slow=20). Long when H4 close > both EMAs with separation ≥ `ema_sep_pct`.
- **Swing detection:** M15 fractal swing (N bars each side). Must be at least `min_swing_pips` in size.
- **Entry:** PENDING at 61.8% Fib retracement of the M15 swing, only when M15 EMA bias agrees with H4.
- **SL:** Fractal swing extreme (beyond the swing high/low).
- **TP:** Entry ± (swing range × fib_tp = 2.0). Explicit take_profit set on Signal.
- **Cancel:** Pending is cancelled if M15 bias flips (new EMA crossover against the trade direction).
- **Optional filters:** cooldown bars after a loss, swing invalidation on loss, HTF ATR filter.

Key difference from D1/H1 version: uses body-based candle metrics for some calculations; M15 provides more frequent setups but noisier signals.

---

## Walk-Forward History

### Walk-forward 1 (2026-03-25) — FAIL (severe curve-fit)

Fixed: fib_entry=0.786, ema_sep_pct=0.001. Grid: min_swing_pips [10,20,30], cooldown_bars [0,10].
4yr train / 2yr test / 2yr step. 8 symbols (7 FX + XAUUSD).

| Fold | Test period | IS R | OOS R | OOS Expect | OOS WR | Retain |
|------|-------------|------|-------|-----------|--------|--------|
| 1 | 2019–2021 | +1.1 | -8.6 | -0.088 | 11.3% | -1100% |
| 2 | 2021–2023 | +0.7 | -35.1 | -0.253 | 9.4% | -6325% |
| 3 | 2023–2025 | +0.7 | -11.7 | -0.143 | 11.0% | -4767% |
| **Agg** | | | **-55.4R** | **-0.174R** | | **FAIL** |

## Parameter Sweep History

### Sweep 1 (2026-03-25)

Grid: fib_entry [0.5, 0.618, 0.786], min_swing_pips [10, 20, 30], ema_sep_pct [0.0, 0.001], cooldown_bars [0, 10].
36 combinations. H4/M15, 8 symbols.

6 positive combos — all required fib_entry=0.786 AND ema_sep_pct=0.001.
Best: fib=0.786, min_swing=10, sep=0.001, cd=10 → 488 trades, 15% WR, +89.7R, +0.184R expect, MaxDD 46R, avg win 6.91R.

Key finding: the 0.786 entry produces a very unusual profile — 15% WR but ~7R avg win. Without ema_sep_pct=0.001 filtering, even 0.786 goes deeply negative (5286 trades, -130R). The EMA separation filter eliminates 90% of setups and keeps only the highest-quality ones.

Walk-forward showed this was curve-fitting: IS edges were near-zero (+0.003–0.008R) in all 3 training windows, meaning the optimizer had nothing real to find. OOS results inverted severely.

## Root Cause

The IS edge in the full-sample sweep came almost entirely from a small number of very high-R winners (avg 6.9R) that happened to cluster in specific eras. With only ~500 trades over 10 years, a handful of outlier winners can dominate the P&L. Walk-forward confirmed there's no consistent underlying signal.

## Next Steps

- [ ] No further testing — shelved
- [ ] D1/H1 EmaFibRetracement remains the validated version of this concept
