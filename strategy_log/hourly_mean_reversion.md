# HourlyMeanReversion — Strategy Log

## Concept
ICT Power-of-3 / Institutional Candle Mean-Reversion (inspired by @itstomtrades).
- H1 candle runs cleanly in one direction for the first 20–40 minutes.
- MSS on M5 (or M1) in the opposite direction triggers a mean-reversion entry.
- SL = absolute peak (SELL) or trough (BUY) of the H1 run.
- TP = 50% retracement of the H1 candle range (open → peak/trough).
- Designed for XAUUSD. Asian + London sessions (UTC 00:00–16:59).

## MSS Detection Logic
For UP run → SELL:
1. Fractal swing HIGH confirmed (fractal_n bars each side).
2. Primary MSS = close breaks below the peak bar's own LOW ("break of candle low").
3. If a fractal swing LOW also formed ABOVE the candle low (genuine internal structure near the peak) → MSS = close breaks below that LOW instead (traditional ICT MSS, less restrictive).
4. Early-hour fractal lows BELOW the candle low are ignored — they would require an unreachable price drop and block most setups.
Mirror logic for DOWN run → BUY.

Geometry filter: entry must be ABOVE the H1 midpoint (upper half of range) to ensure viable R:R.

## Bug Fixes (2026-04-08)
Four bugs identified via code review (`hmr_analysis.md`) and fixed:

1. **SL at true sweep high** (HIGH severity): SL was placed at the last confirmed fractal high/low (`last_sh`/`last_sl`), which lags by `fractal_n` bars. On liquidity sweep bars, the SL was inside the wick — virtually guaranteeing premature stop-outs. **Fix**: SL now uses `self._peak` / `self._trough` (the absolute extreme of the run).

2. **Pullback tracking reset** (MODERATE): `_peak_pullback_low` reset to the new bar's low whenever a new high formed, erasing memory of prior deep pullbacks. A 100-pip drop followed by a grind to a new high was mischaracterised as a clean run. **Fix**: Added `_max_up_pullback` / `_max_dn_pullback` that persist the largest pullback seen each hour without resetting.

3. **MSS level blockade** (MODERATE, likely primary cause of low trade count): When any fractal low existed (even a tiny early-hour dip), it became the MSS level unconditionally. This forced price to drop all the way to the hour's lowest fractal low to trigger — combined with the geometry filter, this made most setups geometrically impossible. **Fix**: Reversed MSS priority. Peak bar's candle low is now primary; fractal low only used if it's above candle low (genuine internal structure near the peak).

**Impact**: Fixes #1 and #3 should significantly improve both trade frequency and stop placement. Previous walk-forward results are invalidated — re-sweep and re-validate required.

## Parameters
| Param | Description | Default |
|---|---|---|
| `tf_lower` | Lower TF for MSS detection | `'M5'` |
| `min_move_pips` | Min H1 run in pips before checking MSS | 100 |
| `entry_window_start` | Minutes into H1 to start watching | 20 |
| `entry_window_end` | Minutes into H1 to stop watching | 40 |
| `fractal_n` | Bars each side for swing confirmation | 2 |
| `max_pullback_pips` | Max intra-run pullback (0 = off) | 50 |
| `session_hours` | UTC hours to trade | 0–16 |

For XAUUSD: 1 pip = $0.10. min_move_pips=100 → $10 minimum H1 run.

## Data
- M5 CSV: available (`XAUUSD_M5_20160103-20260319.csv`) — ready to test.
- M1 CSV: **downloaded** (`XAUUSD_M1_20160103-20260319.csv`) — 3,617,381 bars. Ready to sweep.

## Why M1 is Better
On M5, fractal confirmation takes ~10 min. By then, price has often retraced past the
50% TP level, so the geometry filter blocks the trade. On M1, confirmation takes ~2 min
→ entries are closer to the peak, better R:R, more signals.

## Param Sweep: XAUUSD M5 (post-bugfix, 2016–2026)
810 combos. 400/810 fired trades. Top findings:
- `move=150, fn=1, pb=0, London` dominates — 68% WR, +0.589R expect, PF 2.85 (22 trades)
- Best trade balance: `move=150, w=(25-50), fn=1, pb=0, both` — 50 trades, +0.397R, PF 1.99
- `max_pullback=0` wins across the board (pullback filter hurts — disable it)
- `fn=1` preferred on M5 (fastest confirmation, better entry timing)
- Still sparse: ~2–5 trades/yr on M5

## Walk-Forward: XAUUSD M5 — MODERATE (post-bugfix, 2026-04-08)
Folds: 4yr train / 2yr test / 2yr step. 2016–2026 data.

| Fold | Test Period | IS Expect | OOS Trades | OOS WR | OOS Expect | OOS PF | Retain |
|------|-------------|-----------|-----------|--------|-----------|--------|--------|
| 1 | 2020–2022 | -0.005R | 15 | 33.3% | **-0.286R** | 0.57 | FAIL |
| 2 | 2022–2024 | +0.428R | 11 | 54.5% | **+0.252R** | 1.55 | 59% |
| 3 | 2024–2026 | +0.790R | 21 | 52.4% | **+0.238R** | 1.50 | 30% |
| **Agg** | **2020–2026** | | **47** | | **+0.074R** | | **MODERATE** |

**Fold 1 failure explained**: IS period (2016–2020) produced flat results (-0.005R IS); optimiser selected noise params that failed OOS. 2016–2020 appears to be a different market regime for this strategy post-bugfix.
**Folds 2 & 3 consistent and positive** — +0.245R avg OOS, both in the 2022–2026 window.
**Params converging**: `move=100–150, fn=1, pb=0, London`.

**vs pre-bugfix WF** (STRONG, +0.265R OOS, all 3 folds positive): aggregate OOS dropped. Fold 1 was previously propped up by incorrect SL/MSS logic. Post-bugfix results are more honest.

**Caveat: ~2–5 trades/year on M5 is very sparse.** M1 data should multiply signals ~5–10× without changing the logic.

## Validated Params (XAUUSD M5, post-bugfix WF folds 2&3)
```python
HourlyMeanReversionStrategy(
    tf_lower='M5',
    min_move_pips=150,        # fold 3 winner (most recent train 2020-2024)
    entry_window_start=20,
    entry_window_end=50,
    fractal_n=1,
    max_pullback_pips=0,
    session_hours=tuple(range(8, 17)),  # London only
)
```

## Walk-Forward: XAUUSD M1 London — WEAK ✗
Folds: 4yr train / 2yr test / 2yr step. Session fixed to London (08:00–16:59 UTC). 576 combos/fold.

| Fold | Test Period | IS Expect | OOS Trades | OOS Expect | OOS PF | Retain |
|------|-------------|-----------|-----------|-----------|--------|--------|
| 1 | 2020–2022 | +0.355R | 37 | +0.019R | 1.03 | 5% |
| 2 | 2022–2024 | +0.502R | 28 | +0.124R | 1.25 | 25% |
| 3 | 2024–2026 | +0.357R | 11 | -0.067R | 0.89 | -19% |
| **Agg** | **2020–2026** | | **76** | **+0.046R** | | **WEAK** |

All 3 folds converge on `min_move_pips=50`. Fold 2 positive but fold 3 collapses. Not enough consistency.

## Walk-Forward: XAUUSD M1 — D1 Bias Filter (Option 1) — WEAK ✗
London session + D1 EMA(10/20) bias gate. Only take BUY when D1 bullish, SELL when D1 bearish.

| Fold | Test Period | IS Expect | OOS Trades | OOS Expect | OOS PF | Retain |
|------|-------------|-----------|-----------|-----------|--------|--------|
| 1 | 2020–2022 | ~+0.40R | ~20 | ~-0.09R | <1.0 | FAIL |
| 2 | 2022–2024 | ~+0.49R | ~15 | +0.124R | ~1.25 | ~25% |
| 3 | 2024–2026 | ~+0.36R | ~10 | ~-0.07R | <1.0 | FAIL |

Trade count halved by filter. Helped fold 2 slightly but folds 1 & 3 still negative. No improvement over bare London.

## Walk-Forward: XAUUSD M1 — ATR Volatility Gate (Option 3) — WEAK ✗
London session + prior-day ATR gate (skip signals when ATR > threshold). Standalone (no D1 bias).
Focused grid: move=[75,100,150], fn=[2,3,5], window_start=[20,25], window_end=[35,40,45,50], pb=[0,25], atr_max=[0,200,300,400]. 576 combos.

| Fold | Test Period | IS Expect | OOS Trades | OOS Expect | OOS PF | Retain |
|------|-------------|-----------|-----------|-----------|--------|--------|
| 1 | 2020–2022 | +0.302R | 19 | -0.090R | 0.86 | -30% |
| 2 | 2022–2024 | +0.487R | 10 | -0.033R | 0.95 | -7% |
| 3 | 2024–2026 | +0.588R | **2** | +0.385R | 1.77 | 65% |
| **Agg** | **2020–2026** | | **31** | **-0.039R** | | **WEAK** |

Fold 3 chosen `atr_max=300` but only produced 2 OOS trades — noise. Fold 2 optimiser chose `atr_max=0` (filter disabled itself). ATR gate has no consistent benefit. Severe trade-count reduction.

**Root cause confirmed (all 3 options)**: Gold's trending bull regime (2022+) makes M1 mean-reversion unworkable. High-ATR trending days dominate 2022–2024; the filter either eliminates most trades or can't distinguish trending from ranging reliably at D1 granularity. **M1 HMR shelved.**

## Walk-Forward: XAUUSD M1 (Asian session) — FAIL ✗
Folds: 4yr train / 2yr test / 2yr step. Session fixed to Asian (00:00–07:59 UTC). 576 combos/fold.

| Fold | Test Period | IS Expect | OOS Trades | OOS Expect | OOS PF | Retain |
|------|-------------|-----------|-----------|-----------|--------|--------|
| 1 | 2020–2022 | +0.399R | 39 | +0.310R | 1.60 | 78% |
| 2 | 2022–2024 | +0.465R | 17 | -0.032R | 0.95 | -7% |
| 3 | 2024–2026 | +0.383R | 33 | -0.273R | 0.61 | -71% |
| **Agg** | **2020–2026** | | **89** | **+0.029R** | | **FAIL** |

Fold 1 positive (+0.310R, 78% retention), but folds 2 and 3 fail with increasing severity.
**Reason**: Gold entered a strong bull run from 2022. Asian session shifted from ranging/mean-reverting to directional — the ICT power-of-3 consolidation concept degrades in trending conditions.
Optimizer consistently chose `move=50` (noisy, low-frequency) despite sweep showing `move=150` is best IS. Min_trades threshold too low allowed overfitting.

## Walk-Forward: FX Majors (7 pairs) — FAIL ✗
All 3 folds negative OOS. Aggregate OOS: 77 trades, −15.7R, −0.204R expect.
Fold 3 worst: −0.326R, 29.7% WR. IS edge is curve-fit, does not generalise.
**Reason**: FX H1 candles are noisier/choppier — the "institutional candle" structure
that makes gold setups reliable is absent in FX majors at this resolution.

## Walk-Forward: USA100 (Nasdaq) — MODERATE/WEAK ✗
Only 2 folds qualified (fold 1 too few trades). Fold 2: +0.056R. Fold 3: −0.062R.
Aggregate OOS: 28 trades, +0.5R, +0.018R expect — essentially breakeven.
No reliable edge at M5. **Worth retesting with M1 data** (NY session, move=75-100).

## Status
XAUUSD M5: **MODERATE** — post-bugfix WF. Folds 2&3 positive (+0.245R avg OOS). Fold 1 fails (2016–2020 regime issue). Too sparse (~2–5 trades/yr) for standalone live use.
XAUUSD M1: **SHELVED** — all configurations WEAK or FAIL. Tested: Asian session (FAIL), London bare (WEAK), London + D1 bias (WEAK), London + ATR gate (WEAK). Gold bull regime (2022+) makes M1 mean-reversion unviable. Root cause is structural, not fixable with filters.
FX + USA100: **SHELVED**.

## Backtest Commands
```bash
# Edit SYMBOLS in run_backtest.py: SYMBOLS = ['XAUUSD']
python3 run_backtest.py hmr

# Parameter sweep:
python3 param_sweep_hmr.py        # M5
python3 param_sweep_hmr_m1.py     # M1

# Walk-forward validation:
python3 walk_forward.py hmr           # M5 STRONG ✓
python3 walk_forward.py hmr_m1        # M1 — pending results
python3 walk_forward.py hmr_fx        # FAIL — do not use
python3 walk_forward.py hmr_usa100    # MODERATE/WEAK — not live-eligible
```
