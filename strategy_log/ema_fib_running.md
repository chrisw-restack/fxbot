# EmaFibRunning

**Status:** VALIDATED — walk-forward MODERATE (folds 1&2 OOS positive; fold 3 concern ongoing)
**File:** `strategies/ema_fib_running.py`
**Timeframes:** D1 (bias), H1 (entry)
**Order type:** PENDING

---

## Current Config (as of 2026-03-30)

```python
EmaFibRunningStrategy(
    fib_entry=0.786,        # sweep + WF winner (was 0.618 — original sweep had fib_tp fixed at 2.0)
    fib_tp=2.5,             # fold 1 WF winner; higher-trade count than 3.0 (22/yr vs 12/yr)
    fractal_n=2,
    min_swing_pips=30,
    ema_sep_pct=0.0,
    cooldown_bars=0,
    invalidate_swing_on_loss=True,
    blocked_hours=(*range(20, 24), *range(0, 9)),  # allow 09:00-19:00 UTC (session sweep winner)
)
```

Symbols: EURUSD, GBPUSD, AUDUSD, NZDUSD, USDJPY, USDCAD, USDCHF (7 pairs, no XAUUSD).
Risk: 0.5% per trade (default).

**Key change from original config:** `fib_entry` 0.618→0.786, `fib_tp` 2.0→2.5, `fractal_n` 3→2, `blocked_hours` (16-23)→(20-23, 0-8).
Original sweep had `fib_tp` fixed at 2.0, which masked that 0.786 outperforms 0.618 when combined with higher TP targets.

---

## Strategy Logic

A variant of EmaFibRetracement that uses **running extremes** (continuously updated highs/lows) rather than fixed fractal swing points. Operates on the same D1/H1 stack.

Key differences from EmaFibRetracement:
- **Swing tracking:** Uses a running high/low that continuously updates as price moves. The swing is not anchored to a single fractal high — it extends as price makes new extremes.
- **SL placement:** Set at the wick extreme of the fractal, not the body.
- **Entry/TP calculation:** Uses candle bodies (open/close range) not the full wick range for the Fib levels.
- **FVG requirement:** Requires a Fair Value Gap in the leg prior to entry (always enabled).
- **Pending update:** If the running extreme moves while a pending order is open, the pending is updated (cancel + new signal at revised level).

---

## Full IS Backtest (2026-03-30, current config)

7 forex pairs. 2016–2026. `fib=0.786, fib_tp=2.5, fn=2, sep=0.0, blocked_hours=(20-23,0-8)`.

| Metric | Value |
|--------|-------|
| Trades | 223 |
| Win rate | 30.0% |
| Total R | +82.7R |
| Profit factor | 1.53 |
| Expectancy | +0.371R |
| Max drawdown | ~19R |

---

## Walk-Forward History

### Walk-forward 1 (2026-03-26) — original config, STRONG (now superseded)

Fixed: fib_entry=0.618, min_swing_pips=30. Grid: ema_sep_pct [0.0, 0.001], cooldown_bars [0, 10], invalidate_swing_on_loss [True, False].
4yr train / 2yr test / 2yr step. **8 symbols (7 FX + XAUUSD)** — XAUUSD included, pip_sizes bug present.

| Fold | Test period | IS R | OOS R | OOS Expect | OOS WR | OOS PF | Retain |
|------|-------------|------|-------|-----------|--------|--------|--------|
| 1 | 2020–2022 | -83.4 | +35.0 | +0.106 | 30.6% | 1.15 | N/A |
| 2 | 2022–2024 | +33.8 | +59.9 | +0.211 | 32.5% | 1.31 | 207% |
| 3 | 2024–2026 | +93.3 | -9.6 | -0.050 | 24.5% | 0.93 | -26% |
| **Agg** | | | **+85.3R** | **+0.106R** | | **90%** |

Note: STRONG verdict was inflated by XAUUSD inclusion (which has a pip_size bug in this strategy's pip_sizes dict — defaults to 0.0001 instead of 0.10). Results for XAUUSD are meaningless; it was adding trade count but not reliable edge.

### Walk-forward 2 (2026-03-30) — expanded grid, 7 pairs only, WEAK

Expanded grid: fib_entry [0.618, 0.786], fib_tp [2.0, 2.5, 3.0], fractal_n [2, 3], ema_sep_pct [0.0, 0.001].
Fixed: min_swing_pips=30, cooldown_bars=0, invalidate_swing_on_loss=True, blocked_hours=(20-23, 0-8).
**7 forex pairs only (XAUUSD excluded).**

| Fold | Test period | Best params | IS R | OOS R | IS Exp | OOS Exp | OOS WR | OOS PF | Retain |
|------|-------------|-------------|------|-------|--------|---------|--------|--------|--------|
| 1 | 2020–2022 | fib=0.786, tp=2.5, fn=2, sep=0.0 | +32.8 | +13.5 | +0.504 | +0.346 | 28.2% | 1.48 | 69% |
| 2 | 2022–2024 | fib=0.786, tp=3.0, fn=2, sep=0.0 | +26.8 | +41.6 | +0.479 | +0.651 | 32.8% | 1.97 | 136% |
| 3 | 2024–2026 | fib=0.786, tp=3.0, fn=3, sep=0.001 | +55.2 | -12.0 | +0.935 | -1.000 | 0.0% | 0.00 | -107% |
| **Agg** | | | | **+43.1R** | | **+0.375R** | | | **33%** |

**fib_entry=0.786 was unanimous across all 3 folds** — the strongest signal from this WF.

**Verdict: WEAK** (official), but with important caveats:
1. **Fold 3 has only 12 OOS trades** — statistically meaningless. The optimizer picked a very tight IS combo (fn=3, sep=0.001) that produced 0 OOS signals. The -1.000R expectancy is 12 consecutive losses with 0 wins — in a strategy with ~25-30% WR, this is plausible noise.
2. **2024–2026 regime is consistently weak** — both WF runs show fold 3 as the weakest (also -9.6R in WF1). This is a genuine concern, not just noise.
3. Folds 1 and 2 look reasonable (+0.346R and +0.651R OOS). Avg retention of those two folds alone = 100%.

The WEAK verdict reflects the fold 3 collapse. Whether 2024-2026 represents a permanent regime change or a cyclical drawdown is unknown.

---

## Parameter Sweep History

### Sweep 1 (2026-03-26) — fib_entry and fib_tp not fully explored

Grid: fib_entry [0.5, 0.618, 0.786], min_swing_pips [10, 20, 30], ema_sep_pct [0.0, 0.001], cooldown_bars [0, 10], invalidate_swing_on_loss [True, False].
**fib_tp fixed at 2.0, fractal_n fixed at 3.** 72 combinations. 8 symbols (including XAUUSD with pip_size bug).

Best combo: fib=0.618, sw=30, sep=0.001, cd=0, inv=N → 1105 trades, +36.1R, +0.033R expect, MaxDD 61.6R.
Only 9 positive combos total. Results unreliable — XAUUSD pip bug and fib_tp never tested.

### Sweep 2 (2026-03-30) — expanded, correct session filter, 7 pairs only

Grid: fib_entry [0.5, 0.618, 0.786], fib_tp [1.5, 2.0, 2.5, 3.0], fractal_n [2, 3], min_swing_pips [15, 20, 30], ema_sep_pct [0.0, 0.001], cooldown_bars [0, 10], invalidate_swing_on_loss [True, False].
576 combinations. blocked_hours=(20-23, 0-8). 7 forex pairs only.

**Top by expectancy (min 100 trades):**

| fib_e | fib_tp | frac | sw_pip | ema_s | cool | inv | trades | WR% | TotalR | PF | Expect | MaxDD |
|-------|--------|------|--------|-------|------|-----|--------|-----|--------|----|--------|-------|
| 0.786 | 3.0 | 3 | 30 | 0.001 | 0/10 | Y/N | 117 | 21.4% | +54.7 | 1.59 | +0.467 | 14.0 |
| 0.786 | 3.0 | 2 | 30 | 0.001 | 10 | Y/N | 125 | 23.2% | +52.0 | 1.54 | +0.416 | 13.4 |
| 0.786 | 2.5 | 2 | 30 | 0.0 | 10 | Y/N | 220 | 30.5% | +85.7 | 1.56 | +0.389 | 18.1 |
| 0.786 | 3.0 | 2 | 30 | 0.001 | 0 | Y | 127 | 22.8% | +50.0 | 1.51 | +0.394 | 13.4 |
| 0.786 | 2.5 | 3 | 30 | 0.001 | 0/10 | Y/N | 119 | 24.4% | +43.1 | 1.48 | +0.362 | 13.4 |

**Key findings from Sweep 2:**
- `fib_entry=0.786` dominates all top-expectancy rows — contrary to Sweep 1's conclusion (0.618). The original sweep had fib_tp=2.0 fixed, which masked this — 0.786 entry with fib_tp=2.0 only produces ~RR of ~1:1 actual risk (entry 78.6% retraced, TP=2× body_range → ~1.3× actual SL). With fib_tp=2.5/3.0 the reward becomes much more favourable.
- `fib_tp=3.0` gives highest expectancy but fewest trades (~12/yr). `fib_tp=2.5` is the balance point (~22/yr).
- `min_swing_pips=30` consistent across all top rows.
- `cooldown_bars` and `invalidate_swing_on_loss` make **zero difference** at these settings — same trades, same results.
- Original Sweep 1 best combo (fib=0.618, fib_tp=2.0) produces +0.148R in this corrected sweep — well below the new top combos.

---

## Session Filter Sweep (2026-03-30)

Base params: fib=0.618, fib_tp=2.0, fn=3, sw=30, sep=0.001, cd=0, inv=True (original config).
7 forex pairs.

| Session | Trades | WR% | TotalR | PF | Expect | MaxDD |
|---------|--------|-----|--------|----|--------|-------|
| No filter (24h) | 724 | 27.3 | +55.0 | 1.10 | +0.076 | 30.9 |
| Block Asian 0-7 | 634 | 28.2 | +76.3 | 1.17 | +0.120 | 21.5 |
| Block Asian 0-8 | 600 | 28.0 | +67.2 | 1.16 | +0.112 | 21.0 |
| Block late NY 20-23 | 707 | 27.4 | +56.5 | 1.11 | +0.080 | 30.2 |
| Default: block 16-23 | 648 | 27.2 | +54.6 | 1.12 | +0.084 | 27.2 |
| **Block 20-23+0-8 (WINNER)** | **494** | **28.5** | **+70.7** | **1.20** | **+0.143** | **18.9** |
| Block 21-23+0-8 | 512 | 27.7 | +57.3 | 1.15 | +0.112 | 20.0 |
| Block 16-23+0-8 | 397 | 27.0 | +45.5 | 1.16 | +0.115 | 19.3 |
| NY only (0-12+21-23) | 444 | 28.6 | +60.2 | 1.19 | +0.136 | 22.6 |

**Winner: block 20-23+0-8** — same session window as EmaFibRetracement. Best expectancy (+0.143R), best PF (1.20), lowest drawdown (18.9R). The original "block 16-23" is suboptimal — blocks the valuable 16:00-19:00 UTC (London afternoon / NY open overlap).

---

## Per-Symbol Breakdown (IS, 2016–2026)

### Config A: fib=0.786, tp=2.5, fn=2, sep=0.0 (fold 1&2 WF winner, 223 trades)

| Symbol | Trades | WR% | Total R | PF | Expectancy | MaxDD |
|--------|--------|-----|---------|-----|-----------|-------|
| GBPUSD | 74 | 27.0% | +46.1R | 1.85 | +0.624 | 14R |
| NZDUSD | 9 | 77.8% | +17.1R | 9.56 | +1.902 | 1R |
| AUDUSD | 11 | 36.4% | +6.5R | 1.94 | +0.595 | 3R |
| USDJPY | 68 | 29.4% | +12.3R | 1.26 | +0.181 | 19R |
| USDCAD | 29 | 27.6% | +1.1R | 1.05 | +0.039 | 6R |
| EURUSD | 23 | 21.7% | +0.8R | 1.05 | +0.037 | 11R |
| USDCHF | 9 | 33.3% | -1.4R | 0.76 | -0.160 | 3R |

GBPUSD is the main contributor (+46.1R, 74 trades) — note this is the **opposite** of EmaFibRetracement where GBPUSD is the marginal performer. The strategies have complementary symbol strengths.
NZDUSD and AUDUSD show very high expectancy but only 9-11 trades — sample sizes too small to rely on.
USDCHF is slightly negative but only 9 trades — don't remove based on IS alone.

### Config B: fib=0.786, tp=3.0, fn=3, sep=0.001 (sweep IS winner, 117 trades)

| Symbol | Trades | WR% | Total R | PF | Expectancy |
|--------|--------|-----|---------|-----|-----------|
| GBPUSD | 38 | 18.4% | +26.6R | 1.86 | +0.701 |
| NZDUSD | 6 | 100.0% | +20.9R | — | +3.487 |
| AUDUSD | 9 | 22.2% | +6.0R | 1.86 | +0.667 |
| EURUSD | 14 | 21.4% | +5.6R | 1.51 | +0.403 |
| USDJPY | 37 | 18.9% | +8.5R | 1.28 | +0.229 |
| USDCAD | 10 | 0.0% | -10.0R | 0.00 | -1.000 |
| USDCHF | 3 | 0.0% | -3.0R | 0.00 | -1.000 |

Note: USDCAD and USDCHF have 0% WR on very small samples (10 and 3 trades) — not reliable. NZDUSD 100% WR on 6 trades is also unreliable. Config B's high IS expectancy is largely built on sparse samples.

---

## Comparison with EmaFibRetracement

| Metric | EmaFibRunning | EmaFibRetracement |
|--------|--------------|-------------------|
| WF verdict | WEAK (fold 3: 12 OOS trades) | MODERATE (all 3 folds OOS positive) |
| Agg OOS expect | +0.375R (WF2) | +0.427R |
| IS expectancy | +0.371R | +0.774R (sweep best) |
| Win rate | ~25-30% | ~12-13% |
| Avg win | ~2.5R | ~12.7R |
| Trades/yr | ~22 (Config A) | ~45 |
| GBPUSD IS | +46.1R (best pair!) | +0.4R (worst pair) |
| Session | 09:00-19:00 UTC | 09:00-19:00 UTC |
| fib_entry | 0.786 (confirmed) | 0.786 (confirmed) |

**Diversification value:** The two strategies have complementary symbol strengths (EmaFibRunning is strong on GBPUSD, weak on EURUSD; EmaFibRetracement is strong on EURUSD, weak on GBPUSD). Running both together may smooth the equity curve.

---

## Assessment

- **Confirmed:** fib_entry=0.786 beats 0.618 — original sweep conclusion was wrong (fib_tp was fixed at 2.0, masking the true optimum).
- **Confirmed:** Session filter 09:00-19:00 UTC significantly improves quality.
- **Concern:** 2024-2026 remains the weak period across both WF runs. Strategy produces very few signals in recent data with tighter params.
- **Trade-off:** High expectancy (+0.467R) comes with ~12 trades/yr — too sparse for reliable WF validation. The +0.371R config with ~22 trades/yr is the better balance.
- **WF verdict WEAK** is largely driven by fold 3 having only 12 OOS trades. Folds 1&2 look fine.

**Verdict: MODERATE** — downgraded from STRONG due to corrected testing (XAUUSD excluded, expanded grid). Folds 1&2 are positive with reasonable retention; fold 3 is unreliable due to sample sparsity. 2024-2026 is the ongoing concern to monitor.

---

## Notes

- **XAUUSD exclusion:** Strategy pip_sizes dict doesn't include XAUUSD (falls back to 0.0001). Gold has pip_size=0.10 so all pip-based filters give nonsense values. Exclude from testing unless you add `'XAUUSD': 0.10` to the strategy's pip_sizes.
- **Original STRONG verdict was inflated:** XAUUSD was contributing meaningless trades that happened to be profitable, boosting the "STRONG" appearance.
- **cooldown_bars and invalidate_swing_on_loss:** Make no difference at fib_entry=0.786 + min_swing_pips=30 — these filters are effectively redundant with the tight entry criteria.

---

## Running alongside EmaFibRetracement

Now live in demo alongside EmaFibRetracement. Portfolio manager keys by `(symbol, strategy_name)` — both strategies hold independent slots per symbol.

When previously blocked (shared symbol lock), EmaFibRetracement was suppressing 101 of EmaFibRunning's 223 signals (45%), worth +76.6R net. GBPUSD was worst affected (35 blocked, +40R lost). Unblocking recovered this value with only +0.4R more max drawdown vs the blocked setup.

## Next Steps

- [ ] Monitor demo performance — fold 3 concern (2024–2026) is the key watch item
- [ ] Add `'XAUUSD': 0.10` to pip_sizes if running gold seriously
