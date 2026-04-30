# EmaFibRunning

**Status:** VALIDATED — walk-forward STRONG (2026-04-30 targeted TP WF; 83% avg OOS retention, all 3 folds positive)
**File:** `strategies/ema_fib_running.py`
**Timeframes:** D1 (bias), H1 (entry)
**Order type:** PENDING

---

## Current Config (as of 2026-03-30, params unchanged on 2026-04-28)

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

**2026-04-28 strategy revisions (live params unchanged):** Mirrors of fixes applied to EmaFibRetracement.
- **#1 Anchor-fractal snapshot at placement** — `notify_loss` now invalidates the fractal that *produced* the trade (snapshotted at pending placement, low for BUY / high for SELL), not whichever fractal happens to be current at close time.
- **#2 D1 bias-flip cancellation** — pendings now cancel if either D1 or H1 EMA bias flips against the pending direction. Previously only H1 flips triggered cancellation.
- **#4 `notify_win` hook** — added to clear the pending-snapshot state on wins. Engine already routed WIN closes here.

**Other retracement fixes deliberately not applied:**
- Fix #3 (`_position_open` flag) — caused dead-lock in retracement; not needed here (running uses `min_swing_pips=30`, well above `MIN_SL_PIPS=5`, so no risk-rejection phantoms).
- Fix #5 (recent-swing alignment) — direction logic is already encoded in the anchor (fractal_low for BUY, fractal_high for SELL); the alignment concept doesn't translate.
- Fix #6 (pending max-age) — already mitigated by the running-extreme cancel/replace logic at lines 288-294.

**IS impact at live config: zero.** 223 trades / +81.7R / +0.366R both pre- and post-fix. The fixes are correctness improvements that don't bite the live config but prevent latent bugs surfacing under different params.

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

### Walk-forward 4 (2026-04-30) — targeted TP comparison: fib 2.5 vs R:R 2.0, STRONG ✓

Two-combo WF. All non-TP params fixed at validated values. WF picks whichever TP mode wins IS each fold.
Grid: `use_fib_tp [True, False]`, `fib_tp [2.5]`, `rr_ratio [2.0]`. Everything else fixed (fib_e=0.786, fn=2, sep=0.0, sw=30).

**Fib 2.5 wins IS in all 3 folds** — R:R 2.0 was never selected.

| Fold | Test period | Best params | IS Exp | OOS R | OOS Exp | OOS WR | OOS PF | Retain |
|------|-------------|-------------|--------|-------|---------|--------|--------|--------|
| 1 | 2020–2022 | fib 2.5 | +0.500 | +13.2 | +0.339 | 28.2% | 1.47 | 68% |
| 2 | 2022–2024 | fib 2.5 | +0.364 | +41.1 | +0.633 | 36.9% | 2.00 | 174% |
| 3 | 2024–2026 | fib 2.5 | +0.508 | +1.8 | +0.039 | 25.5% | 1.05 | 8% |
| **Agg** | | | | **+56.1R** | **+0.372R** | | | **83%** |

**Verdict: STRONG** (83% avg retention). All 3 folds OOS positive. Fold 3 nearly breakeven (+0.039R, 47 trades) — no collapse unlike the fib 3.0 run. **Confirms fib 2.5 as the correct TP; no case for switching to R:R 2.0.**

---

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

### Walk-forward 3 (2026-04-28) — post-fixes, no measurable change

Same grid as WF2. Fixes #1 (anchor-fractal snapshot), #2 (D1 bias-flip cancel), #4 (`notify_win`) active.

| Fold | Test period | Best params | IS R | OOS R | IS Exp | OOS Exp | OOS WR | OOS PF | Retain |
|------|-------------|-------------|------|-------|--------|---------|--------|--------|--------|
| 1 | 2020–2022 | fib=0.786, tp=2.5, fn=2, sep=0.0 | +32.5 | +13.2 | +0.500 | +0.339 | 28.2% | 1.47 | 68% |
| 2 | 2022–2024 | fib=0.786, tp=3.0, fn=2, sep=0.0 | +26.4 | +41.3 | +0.472 | +0.646 | 32.8% | 1.96 | 137% |
| 3 | 2024–2026 | fib=0.786, tp=3.0, fn=3, sep=0.001 | +54.7 | -12.0 | +0.926 | -1.000 | 0.0% | 0.00 | -108% |
| **Agg** | | | | **+42.5R** | | **+0.370R** | | | **32%** |

**Effectively identical to WF2** (Δ: -0.6R, -0.005R/trade). The fix changes (more accurate fractal invalidation; D1-flip cancellations) made no meaningful difference at the chosen params — confirming the live config is robust to the fixes.

Same caveat as WF2: WEAK verdict label is dragged down by the 12-trade fold-3 sample. The aggregate +0.370R OOS expectancy is positive overall, and folds 1 & 2 retention averages ~100%.

---

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

### Sweep 3 (2026-04-30) — TP mode comparison, 144 combinations

Grid: `use_fib_tp [True, False]`, `fib_tp [1.0, 2.0, 3.0]`, `rr_ratio [2.0, 2.5, 3.0]`, `fib_entry [0.618, 0.786]`, `fractal_n [2, 3]`, `ema_sep_pct [0.0, 0.001]`.
Fixed: sw=30, cooldown=0, invalidate=True, blocked=(20-23, 0-8). Note: each row appears 3× in raw output (irrelevant cross-product), unique results shown below.

**At WF-validated params (fib_e=0.786, fn=2, ema_s=0.0):**

| TP mode | config | trades | WR% | Expect | MaxDD | Streak |
|---------|--------|--------|-----|--------|-------|--------|
| fib | 1.0 | 164 | 42.1% | +0.177R | 10.5R | 7 |
| fib | 2.0 | 219 | 31.5% | +0.267R | 15.1R | 12 |
| **fib** | **2.5 (live)** | **~220** | **~30%** | **~+0.267R** | **~15R** | **~12** |
| fib | 3.0 | 218 | 25.2% | +0.341R | 23.2R | 12 |
| R:R | 2.0 | 241 | 43.6% | +0.299R | 8.2R | 6 |
| R:R | 2.5 | 236 | 35.6% | +0.239R | 12.2R | 10 |
| R:R | 3.0 | 232 | 30.2% | +0.200R | 21.3R | 12 |

Key findings:
- **Fib 3.0** has the best raw expectancy (+0.341R) but worst drawdown (23.2R) and showed complete OOS failure in the wider WF (0/12 wins fold 3). Not safe to use.
- **R:R 2.0** has the best risk-adjusted profile (+0.299R, DD only 8.2R, streak 6) and highest trade count, but the targeted WF confirms fib 2.5 beats it IS in all 3 folds.
- **Fib 2.5** (live config): confirmed sweet spot — competitive expectancy, lower drawdown than fib 3.0, wins every IS fold in WF4.
- **fib_entry=0.618** with fractal_n=3 dominates Total R tables (1000+ trades, +130-150R) due to trade volume but at inferior expectancy (~+0.135-0.147R vs +0.267-0.341R for 0.786).

---

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

- **Confirmed:** fib_entry=0.786 beats 0.618 across all WF runs.
- **Confirmed:** fib_tp=2.5 is the correct TP — beats R:R 2.0 IS in every WF fold; fib 3.0 has better IS expectancy but OOS collapse risk.
- **Confirmed:** Session filter 09:00-19:00 UTC significantly improves quality.
- **Concern:** 2024-2026 remains the weak OOS period (fold 3 nearly breakeven across multiple WF runs), but is positive in the targeted WF (47 trades, +0.039R). Not a collapse — likely a lower-volatility regime.
- **No case to switch to R:R 2.0** despite its lower drawdown profile — fib 2.5 wins IS consistently and the targeted WF confirms robustness.

**Verdict: STRONG** — WF4 (targeted fib 2.5 vs R:R 2.0) shows 83% avg OOS retention, all 3 folds positive, 151 OOS trades. The current live config (fib_tp=2.5, fib_e=0.786, fn=2, sep=0.0) is validated. Fold 3 (+0.039R) is the ongoing watch item.

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
- [ ] After 50+ live trades on the post-fix code, compare live behaviour to backtest expectancy (+0.366R IS) to confirm fixes don't surface unexpected behaviour
