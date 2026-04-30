# Engulfing

**Status:** VALIDATED — walk-forward STRONG (all 3 folds OOS positive, consistent params). Running in demo alongside EmaFibRetracement + EmaFibRunning.
**File:** `strategies/three_line_strike.py` (class `ThreeLineStrikeStrategy`, NAME=`'Engulfing'`)
**Timeframes:** M5
**Order type:** MARKET

---

## Current Config (as of 2026-04-15)

```python
ThreeLineStrikeStrategy(
    sl_mode='fractal',
    fractal_n=3,
    min_prev_body_pips=3.0,
    engulf_ratio=1.5,
    max_sl_pips=15,
    allowed_hours=tuple(range(13, 18)),  # NY session: 13:00–17:00 UTC
    sma_sep_pips=5.0,
)
# RR ratio: 2.5 (set on RiskManager — strategy does not set take_profit)
```

Symbols: EURUSD, AUDUSD, USDCAD (3 pairs)
Risk: 0.5% per trade (default).

**Removed 2026-04-15:**
- USDJPY — negative IS in all 6 sessions tested (NY core −0.020R/25t, WR 28%). Worst in London (−0.417R/24t, WR 17%).
- NZDUSD — near-zero IS expectancy in best session (NY core +0.077R/13t, ~1.3 trades/yr). No reliable edge.

---

## Strategy Logic

M5 bullish or bearish engulfing candle pattern, filtered by trend alignment and session.

### Filters (all must pass)

| Filter | Bullish | Bearish |
|--------|---------|---------|
| Trend | `price > SMA200` | `price < SMA200` |
| MA alignment | `SMA21 > SMA50 + sep_pips` | `SMA21 < SMA50 − sep_pips` |
| RSI momentum | `RSI > 50` | `RSI < 50` |
| Session | hour in `allowed_hours` (13–17 UTC) | same |

### Pattern

**Bullish:** Previous bar is bearish with body ≥ `min_prev_body_pips`. Current bar is bullish, opens below previous close, closes above previous open, and body ≥ `engulf_ratio × prev_body`.

**Bearish:** Previous bar is bullish with body ≥ `min_prev_body_pips`. Current bar is bearish, opens above previous close, closes below previous open, and body ≥ `engulf_ratio × prev_body`.

### Stop Loss

`fractal` mode: most recent swing low (bullish) / swing high (bearish) using a window of `2×fractal_n+1` bars (n=3 → 7-bar window). Skips if SL > `max_sl_pips` from entry.

### Take Profit

Risk manager default: `entry ± (SL distance × 2.5R)`.

---

## Full IS Backtest (2026-04-03)

5 pairs (EURUSD, AUDUSD, NZDUSD, USDJPY, USDCAD). 2016–2026. Final config above.

| Metric | Value |
|--------|-------|
| Trades | 101 |
| Win rate | 40.6% (41W / 60L) |
| Total R | +22.0R |
| Profit factor | 1.37 |
| Expectancy | +0.22R per trade |
| Max drawdown | 10.0R (5.5%) |
| Best win streak | 5 |
| Worst loss streak | 10 |
| Avg win | 2.00R |
| Avg loss | 1.00R |

~10 trades/yr across 5 pairs (2 trades/pair/yr). Low frequency is the main practical constraint.

---

## Walk-Forward Results (2026-04-03)

4yr train / 2yr test / 2yr step. 3 folds. 18 combos per fold.
Fixed: `fractal_n=3, allowed_hours=NY, sma_sep_pips=5.0`. Grid: `min_prev_body_pips [0,3,5] × engulf_ratio [1.0,1.5,2.0] × max_sl_pips [15,20]`.

| Fold | Test Period | Best Params | IS Trades | IS Expect | OOS Trades | OOS Expect | OOS WR | OOS PF | Retain |
|------|-------------|-------------|-----------|-----------|------------|------------|--------|--------|--------|
| 1 | 2020–2022 | body=3, ratio=1.5, sl=15 | 33 | +0.091R | 20 | +0.350R | 45.0% | 1.64 | 385% |
| 2 | 2022–2024 | body=3, ratio=1.5, sl=20 | 44 | +0.227R | 53 | +0.132R | 37.7% | 1.21 | 58% |
| 3 | 2024–2026 | body=3, ratio=1.5, sl=15 | 51 | +0.294R | 20 | +0.200R | 40.0% | 1.33 | 68% |

### Walk-forward 1 (2026-04-03) — rr=2.0 fixed

**Aggregate OOS: 93 trades | +18.0R | +0.194R expectancy | Avg retention: 170%**

| Fold | Test Period | Best Params | IS Expect | OOS Expect | Retain |
|------|-------------|-------------|-----------|------------|--------|
| 1 | 2020–2022 | body=3, ratio=1.5, sl=15, rr=2.0 | +0.091R | +0.350R | 385% |
| 2 | 2022–2024 | body=3, ratio=1.5, sl=20, rr=2.0 | +0.227R | +0.132R | 58% |
| 3 | 2024–2026 | body=3, ratio=1.5, sl=15, rr=2.0 | +0.294R | +0.200R | 68% |

### Walk-forward 2 (2026-04-07) — rr_ratio added to grid [2.0, 2.5]

**Aggregate OOS: 93 trades | +22.0R | +0.237R expectancy | Avg retention: 178%**

| Fold | Test Period | Best Params | IS Expect | OOS Expect | Retain |
|------|-------------|-------------|-----------|------------|--------|
| 1 | 2020–2022 | body=3, ratio=1.5, sl=15, **rr=2.0** | +0.091R | +0.350R | 385% |
| 2 | 2022–2024 | body=3, ratio=1.5, sl=20, **rr=2.0** | +0.227R | +0.132R | 58% |
| 3 | 2024–2026 | body=3, ratio=1.5, sl=15, **rr=2.5** | +0.441R | +0.400R | **91%** |

**Verdict: STRONG** — all 3 folds OOS positive. `min_body=3, engulf_ratio=1.5` unanimous across all folds. Fold 3 (most recent, 2020–2024 training) chose rr=2.5 and produced the strongest OOS (+0.400R, 91% retention). Live config updated to rr=2.5.

**Caveat:** 93 total OOS trades across 10 years is sparse (~9–10 trades/yr per fold). STRONG verdict reflects param robustness, not high statistical confidence. Monitor demo carefully.

---

## Session × Symbol Sweep (2026-04-15)

Full 7×6 grid: all 7 major pairs × 6 session windows. Params fixed at validated values.
Grid: EURUSD, GBPUSD, AUDUSD, NZDUSD, USDCAD, USDCHF, USDJPY × NY core / NY open / NY extended / London core / London open / London+NY.

### Expectancy grid (expectancy / trades, 2016–2026)

| Symbol | NY core (13–17) | NY open (13–15) | NY extended (13–20) | London core (8–12) | London open (7–10) | London+NY (8–17) |
|--------|----------------|----------------|--------------------|--------------------|-------------------|-----------------|
| EURUSD | **+1.042R**/24 | +1.100R/20 | +0.885R/26 | −0.125R/12 | +1.000R/7* | +0.432R/44 |
| GBPUSD | −0.149R/37 | −0.093R/27 | +0.013R/38 | +0.217R/46 | **+0.458R**/36 | +0.312R/72 |
| AUDUSD | +0.167R/12 | +0.050R/10 | **+0.531R**/16 | −0.500R/7 | +0.167R/6 | +0.050R/20 |
| NZDUSD | +0.077R/13 | +0.167R/12 | −0.067R/15 | −0.222R/9 | −1.000R/6 | −0.205R/22 |
| USDCAD | +0.037R/27 | +0.167R/24 | +0.100R/35 | **+0.441R**/17 | −0.192R/13 | +0.191R/47 |
| USDCHF | −0.176R/17 | −0.192R/13 | −0.391R/23 | +1.000R/7* | −0.562R/8 | +0.094R/32 |
| USDJPY | −0.020R/25 | −0.087R/23 | +0.132R/34 | −0.417R/24 | −0.500R/21 | −0.388R/40 |
| **ALL** | **+0.129R/155** | +0.167R/129 | +0.160R/187 | +0.061R/122 | +0.010R/97 | +0.125R/277 |

*7 trades — unreliable.*

**Key findings:**
- **EURUSD**: excellent in all NY sessions, bad in London. Keep NY core.
- **GBPUSD**: opposite — negative NY, positive London. London open +0.458R/36t, London core +0.217R/46t.
- **AUDUSD**: NY extended nominally better (+0.531R/16t) vs NY core (+0.167R/12t), but difference driven by ~4 extra trades 18–20 UTC.
- **NZDUSD**: near-zero across all sessions. Best is NY open +0.167R/12t (~1.2 trades/yr). No reliable edge.
- **USDCAD**: best in London core (+0.441R/17t) but current NY core is positive (+0.037R/27t) with more trades.
- **USDCHF**: negative across all meaningful sessions. London core +1.000R on 7 trades is noise.
- **USDJPY**: negative in all sessions except NY extended (+0.132R/34t, PF 1.20). London catastrophic (WR 14–17%).

### Actions taken
- USDJPY removed from live (negative in current live session, all London sessions catastrophic)
- NZDUSD removed from live (no reliable edge in any session, ~1 trade/yr best case)

---

## Single-Symbol Walk-Forwards (2026-04-15)

Followed up session sweep with WF on 5 single-symbol/session candidates. 36 combos each (same grid as original WF). min_trades=5 (appropriate for sparse single-symbol configs).

| Config | OOS Trades | OOS Expect | Avg Retain | Fold 3 (2024–26) | Verdict |
|--------|-----------|-----------|-----------|-----------------|---------|
| GBPUSD London open (7–10) | 16 | +0.281R | 41% | −1.000R / 4t (0% WR) | WEAK |
| GBPUSD London core (8–12) | 17 | +0.147R | 51% | −0.417R / 6t | MODERATE |
| AUDUSD NY extended (13–20) | 13 | +0.769R | 62% | −1.000R / **1t** | INCONCLUSIVE |
| USDCAD London core (8–12) | 9 | +0.389R | 107%* | −1.000R / **1t** | INCONCLUSIVE |
| USDCAD London+NY (8–17) | 10 | −0.300R | −107% | −1.000R / 1t | **FAIL** |

*Automated "STRONG" label is misleading — only 9 total OOS trades, fold 3 had 1 trade.*

**Why none were promoted:**
1. **Extreme sparsity** — single-symbol + narrow session yields 1–9 OOS trades per fold. Fold 3 on AUDUSD and USDCAD London core had 1 OOS trade each.
2. **Fold 3 collapse** — every config produced negative OOS in the most recent period (2024–2026), unlike the original multi-symbol NY config where fold 3 was the strongest.
3. **USDCAD London+NY clean FAIL** — negative aggregate OOS, folds 2 and 3 both 0% WR.

**Decisions:**
- EURUSD: keep NY core (13–17) as-is
- AUDUSD: keep NY core (13–17) as-is — extended session fails WF fold 3
- USDCAD: keep NY core (13–17) as-is — all London variants fail WF
- GBPUSD London: theoretically interesting (fold 2 strong, 2022–2024 +0.800R) but fold 3 collapse disqualifies it. Revisit after more market data.

---

## Per-Symbol Breakdown (IS, Config C from shared config comparison)

Config C: `fractal n=3, min_body=3, engulf_ratio=1.5, max_sl=20, NY session`. 10-year IS (2016–2026).

| Symbol | Expectancy | Trades | Notes |
|--------|------------|--------|-------|
| EURUSD | +0.500R | 36 | Best expectancy |
| NZDUSD | +0.200R | 15 | Good expectancy, very sparse |
| USDCAD | +0.159R | 44 | Solid, decent trade count |
| AUDUSD | +0.167R | 18 | Good expectancy, sparse |
| USDJPY | +0.041R | 49 | Most trades, weakest expectancy |
| GBPUSD | −0.200R | 60 | Excluded — negative on NY session |
| USDCHF | n/a | n/a | Excluded — MaxDD 23R, +0.065R IS |

Note: session sweep (2026-04-15, max_sl=15) showed USDJPY at −0.020R/25t in NY core — effectively breakeven/negative even on IS.

---

## Parameter Sweep History

### Cross-pair shared config comparison (2026-04-03)

8 candidate configs across all 6 major pairs, NY session only. Config C identified as the best shared config.

| Config | EURUSD | GBPUSD | AUDUSD | NZDUSD | USDJPY | USDCAD | Pairs+ | Avg Exp | Total R |
|--------|--------|--------|--------|--------|--------|--------|--------|---------|---------|
| C: frac3 body3 eng1.5 sl20 | +0.500R/36 | −0.200R/60 | +0.167R/18 | +0.200R/15 | +0.041R/49 | +0.159R/44 | **5** | **+0.144** | **+21.0** |

Config C is the only config positive on 5 of 6 pairs.

### Single-pair sweeps

Full 324-combo sweep (3 sessions × 3 min_body × 3 eng_ratio × 4 SL configs × 3 max_sl) was run on AUDUSD and GBPUSD. NY session consistently outperformed London and Both on both pairs. Fractal SL modes outperformed bar_multiple. `min_prev_body_pips=3` and `engulf_ratio=1.5` appeared consistently in top configs.

---

## Assessment

- **Strengths:** Consistent params across all 3 WF folds. All OOS periods positive. Strategy adds diversification complement to EmaFibRetracement (different timeframe, different session logic).
- **Concerns:** Very sparse trade count (~6–7/yr on 3 pairs after USDJPY/NZDUSD removal). Single-pair expectancy can be noisy. The strong WF verdict is driven partly by fold 1 OOS over-performance (2020–2022 volatility was favourable for engulfing patterns).
- **Symbol stability:** EURUSD is the main driver (+1.042R IS on NY core). USDCAD and AUDUSD contribute modestly but positively.

---

## Direction-Lock Investigation (2026-04-29)

Hypothesis: `_last_direction[symbol]` only flips when the opposite direction fires, so once a BUY trade closes (SL/TP) the strategy can't re-enter long until a SELL signal generates — which requires a full trend flip. Suspected this was over-filtering and explained the sparse trade count (~6–7/yr per pair).

**Prototype**: added `clear_lock_on_close` flag + `cooldown_bars` param + `notify_loss`/`notify_win` hooks to clear the lock on trade close.

### IS sweep (3 live pairs, 2016–2026, NY core, RR 2.5)

| Mode | Trades | WR | TotalR | PF | Expect | MaxDD |
|---|---|---|---|---|---|---|
| baseline (lock until flip) | 63 | 41.3% | +28.0R | 1.76 | +0.444 | 8.5R |
| unlock, cd=0  | 117 | 36.8% | +33.5R | 1.45 | +0.286 | 13.5R |
| unlock, cd=12 (1h) | 116 | 37.1% | +34.5R | 1.47 | +0.297 | 13.5R |
| unlock, cd=48 (4h) | 115 | 37.4% | +35.5R | 1.49 | +0.309 | 13.5R |

Trade count nearly doubles, absolute Total R rises ~27%, but per-trade expectancy and PF drop materially. **Cooldown duration is irrelevant** — only the lock toggle matters.

### Per-symbol IS (baseline → unlock cd=0)

| Symbol | Trades | TotalR | Expect | Verdict |
|---|---|---|---|---|
| EURUSD | 24→45 | +25.0→+28.5R | +1.042→+0.633 | More trades, marginal trades still profitable |
| AUDUSD | 12→21 | +2.0→+7.0R | +0.167→+0.333 | Strict improvement |
| USDCAD | 27→51 | +1.0→−2.0R | +0.037→−0.039 | **Turns negative** — extra trades are losers |

### WF — 3 live pairs, unlock in grid

All 3 folds picked `clear_lock_on_close=False`. **Aggregate OOS: 57 trades / +33.5R / +0.588R / 224% retention / STRONG.** IS optimizer rejects unlock in every fold.

### WF — 2 pairs (EUR+AUD only, USDCAD dropped), unlock in grid

| Fold | Lock | OOS Trades | OOS Exp | Retain |
|---|---|---|---|---|
| 1 (2020–22) | False | 7 | +0.714 | 250% |
| 2 (2022–24) | **True** | 33 | +0.485 | 78% |
| 3 (2024–26) | False | 8 | +1.625 | 187% |

**Aggregate OOS: 48 trades / +34.0R / +0.708R / 172% / STRONG.** Better per-trade expectancy than 3-pair, but the unlock variant only wins on fold 2.

### WF — GBPUSD London core + unlock

Tested whether unlock could rescue the previously-disqualified GBPUSD London config (session sweep showed IS goes +0.217R/46t → +0.353R/75t under unlock).

| Fold | Params | OOS Trades | OOS Exp | Retain |
|---|---|---|---|---|
| 1 | body=5, ratio=1.0, lock=False | 6 | +0.167 | 27% |
| 2 | body=5, ratio=1.5, lock=True | 3 | +0.167 | 22% |
| 3 | body=3, ratio=2.0, lock=False | 6 | −0.417 | −34% |

**Aggregate OOS: 15 trades / −1.0R / 5% retention / WEAK.** Each fold picks different params (curve-fit), fold 3 OOS negative. Same fold-3-collapse problem that disqualified GBPUSD London the first time.

### Cross-pair session × symbol IS sweep

7 majors × 5 sessions, baseline vs unlock. **No symbol/session combo is rescued** (no case where baseline is clearly negative AND unlock turns it clearly positive). EURUSD, NZDUSD, USDJPY, USDCHF all stay non-viable or get worse under unlock. The only meaningful improvement was GBPUSD London core (which then failed WF above).

### Verdict

**REJECTED.** The lock-until-flip behaviour is correctly filtering quality on a pattern strategy with no other re-entry control. Reverted prototype on 2026-04-29 — strategy code restored to the validated state.

Why the hypothesis was wrong: the suppressed re-entries are statistically lower-quality. The lock effectively says "wait for the macro trend to actually rotate" before taking another setup, which is the right discipline for an engulfing strategy. IS optimisation correctly identifies this in every WF fold across three configs (3-pair, 2-pair, single-pair London).

---

## Next Steps

- [ ] Monitor 3-pair demo performance — target 30+ trades before drawing conclusions
- [ ] Track per-pair performance — USDCAD low expectancy (+0.037R/27t), watch if it becomes a drag. 2-pair (EUR+AUD only) WF showed +0.708R OOS expectancy vs 3-pair's +0.588R — if live USDCAD trades confirm drag, drop it
- [ ] GBPUSD London revisit — positive IS edge exists but fold 3 WF collapse (2024–2026) disqualifies it now, both with and without the unlock change. Revisit when 2026+ data accumulates
