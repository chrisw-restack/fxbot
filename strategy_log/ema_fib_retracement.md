# EmaFibRetracement

**Status:** LIVE (demo)
**File:** `strategies/ema_fib_retracement.py`
**Timeframes:** D1 (bias), H1 (entry)
**Order type:** PENDING

---

## Current Config (as of 2026-03-30)

```python
EmaFibRetracementStrategy(
    fib_entry=0.786,
    fib_tp=3.0,
    fractal_n=3,
    min_swing_pips=10,
    ema_sep_pct=0.001,
    cooldown_bars=10,
    invalidate_swing_on_loss=True,
    blocked_hours=(*range(20, 24), *range(0, 9)),  # allow 09:00–19:00 UTC only
)
```

Risk override: 0.7% per trade (default is 0.5%).
Symbols: EURUSD, GBPUSD, AUDUSD, NZDUSD, USDJPY, USDCAD, USDCHF (7 pairs).

**Changes from 2026-03-22 config:** `cooldown_bars` 0→10, `invalidate_swing_on_loss` False→True, `fib_tp` 2.5→3.0. All three changes driven by the 2026-03-30 walk-forward (WF chose these in 2/3 or all 3 folds) and confirmed by the full param sweep.

---

## Strategy Logic

- **Bias:** D1 EMA trend direction. Long if close > both EMAs (and EMAs separated by `ema_sep_pct`), short if below.
- **Swing:** Fractal-based swing high/low detection on H1 (N bars each side). Must be at least `min_swing_pips` in size.
- **Entry:** PENDING order at `fib_entry` level of the swing. Cancelled if H1 bias flips before fill.
- **SL:** Beyond the swing high/low.
- **TP:** `swing_low + fib_tp × swing_range` (BUY) or `swing_high − fib_tp × swing_range` (SELL). E.g. fib_tp=3.0 means TP at 3× the swing range from the swing origin.
- **Session filter:** `blocked_hours` tuple — bars during these hours are skipped entirely.
- **Cooldown:** `cooldown_bars` H1 bars skipped after a loss.
- **Swing invalidation:** If `invalidate_swing_on_loss=True`, the swing that produced a losing trade is marked used and won't generate another entry.

---

## Full Backtest (2026-03-30, current config)

Symbols: 7 forex pairs + XAUUSD (included by default in run_backtest.py).
Data range: 2016–2026.

| Metric | Value |
|--------|-------|
| Trades | 450 |
| Win rate | 11.3% (51W / 399L) |
| Total R | +250.5R |
| Profit factor | 1.63 |
| Expectancy | +0.56R |
| Max drawdown | 31.1R (22.2%) |
| Best win streak | 3 |
| Worst loss streak | 25 |
| Avg win | +12.73R |
| Avg loss | −1.00R |

Note: XAUUSD is included in run_backtest.py SYMBOLS. For WF and param sweep, XAUUSD is excluded (7 forex pairs only) — see Walk-Forward section.

---

## Walk-Forward History

| Date | Config | Folds | OOS trades | OOS total R | OOS expectancy | Avg retention | Verdict |
|------|--------|-------|------------|-------------|----------------|---------------|---------|
| Pre-2026-03 | fib_entry=0.618, fib_tp=2.0, fractal_n=3, min_swing=10 | 3 | ~551 | +407R | +0.739 | 118% | INFLATED — before D1 fill bug fix |
| 2026-03-20 | fib_entry=0.618 (original post-fix) | 3 | — | ~+2.9R | ~breakeven | — | FAIL — original params barely profitable after fix |
| 2026-03-21 | fib_entry=0.786, fib_tp=2.5, blocked=(20-23,0-8) | 3 | — | +45.1R | positive | ~70% | MODERATE — per-fold detail not recorded; had SPREAD_PIPS bug |
| 2026-03-30 | fib_entry=0.786, fib_tp=3.0, cool=10, inv=True, blocked=(20-23,0-8) | 3 | 260 | +110.9R | +0.427R | 67% | MODERATE (SPREAD_PIPS bug fixed; XAUUSD excluded) |

### Walk-forward 2026-03-30 (current/authoritative)

7 forex pairs only. XAUUSD excluded (strategy pip_sizes dict does not include it; results would be misleading).
SPREAD_PIPS bug fixed in walk_forward.py (`SPREAD_PIPS` → `config.BACKTEST_SPREAD_PIPS`).

| Fold | Train | Test | Best params | IS R | OOS R | IS Exp | OOS Exp | OOS WR | OOS PF | Retain |
|------|-------|------|-------------|------|-------|--------|---------|--------|--------|--------|
| 1 | 2016–2020 | 2020–2022 | fib_tp=3.0, min_sw=10, ema_sep=0.001, cool=10, inv=True | +126.1 | +61.4 | +0.712 | +0.682 | 12.2% | 1.78 | 96% |
| 2 | 2018–2022 | 2022–2024 | fib_tp=3.0, min_sw=10, ema_sep=0.001, cool=10, inv=True | +102.0 | +26.8 | +0.703 | +0.244 | 9.1% | 1.27 | 35% |
| 3 | 2020–2024 | 2024–2026 | fib_tp=2.0, min_sw=10, ema_sep=0.001, cool=10, inv=True | +110.3 | +22.7 | +0.528 | +0.378 | 15.0% | 1.44 | 72% |
| **Agg** | | | | | **+110.9R** | | **+0.427R** | | | **67%** |

fib_entry=0.786 was unanimous across all 3 folds (not shown above as it was always the winner).

**Verdict: MODERATE** — all 3 folds OOS positive. Fold 2 (2022–2024) is the weak link (35% retention) — that period had violent trend reversals. Fold 1 is exceptional (96%).

---

## Parameter Sweep History

### Sweep 1 (pre-bug-fix era)
Optimized fib_entry=0.618, fib_tp=2.0 as defaults. Walk-forward showed STRONG but was inflated by D1 fill bug.

### Sweep 2 (2026-03-20 — post entry_timeframe fix)
Grid: fib_entry [0.5, 0.618, 0.786], fib_tp [1.5, 2.0, 2.5, 3.0], fractal_n [2, 3, 5], min_swing_pips [10, 20, 30], ema_sep_pct [0.0, 0.001], cooldown_bars [0, 10], invalidate_swing_on_loss [True, False], swing_max_age [50, 100, 200].
**Bug:** `blocked_hours` not passed to strategy — used wrong default `(16–23)` instead of proven winner `(20-23, 0-8)`. Results were IS-only estimates, not aligned with walk-forward config. Superseded by Sweep 3.

### Sweep 3 (2026-03-30 — correct session filter)
Grid: same as Sweep 2 (2592 combos). `blocked_hours=(20-23, 0-8)` now correctly passed to every strategy instance. 7 forex pairs only.

**Top by expectancy (min 200 trades):**

| fib_e | fib_tp | frac | sw_pip | ema_s | cool | inv | sw_age | trades | WR% | TotalR | PF | Expect | MaxDD | Streak |
|-------|--------|------|--------|-------|------|-----|--------|--------|-----|--------|----|--------|-------|--------|
| 0.786 | 3.0 | 3 | 10 | 0.001 | 10 | Y | 50/100/200 | 320 | 12.8% | +247.8 | 1.89 | +0.774 | 21.0 | 21 |
| 0.786 | 3.0 | 3 | 10 | 0.001 | 0 | Y | any | 322 | 12.7% | +245.8 | 1.87 | +0.763 | 21.0 | 21 |
| 0.786 | 3.0 | 3 | 10 | 0.001 | 0 | N | any | 324 | 12.7% | +243.8 | 1.86 | +0.752 | 22.0 | 22 |
| 0.786 | 3.0 | 2 | 10 | 0.001 | 0/10 | Y | any | 496 | 12.3% | +349.2 | 1.80 | +0.704 | 22–24 | 22 |
| 0.786 | 2.5 | 3 | 10 | 0.001 | 10 | Y/N | any | 323 | 14.6% | +219.4 | 1.80 | +0.679 | 21.0 | 21 |
| 0.786 | 2.0 | 3 | 10 | 0.001 | 0 | N | any | 330 | 18.2% | +224.1 | 1.83 | +0.679 | 17.0 | 17 |

**Key findings:**
- `fib_entry=0.786` dominates all top rows — confirmed.
- `fib_tp=3.0` beats 2.5 (+0.774R vs +0.679R expectancy) and has higher PF.
- `swing_max_age` makes **zero difference** (50/100/200 produce identical results) — fixed at 100.
- `cooldown_bars=10` gives marginally fewer trades with same or slightly better expectancy.
- `invalidate_swing_on_loss` has minimal IS effect at these settings, but WF chose True in all 3 folds.
- `ema_sep_pct=0.001` is required for top performance.
- `fractal_n=3` slightly better than 2 on quality (expectancy); fractal_n=2 wins on total R.
- Old "current live config" (fib_entry=0.618, fib_tp=2.0): +0.281R expectancy — far below best.

---

## Bug History

- **D1/H4 fill bug (fixed 2026-03-19):** Simulated execution didn't gate fills by timeframe. D1 bars could trigger SL/TP on positions in the same bar they were opened. After fix, results dropped from ~+407R to ~+2.9R (original 0.618 params). Confirmed original WF was overstated.
- **`blocked_hours` missing from param_sweep.py (fixed 2026-03-30):** Strategy was instantiated in the sweep loop without passing `blocked_hours`, so every combo used the wrong default `(16–23)` instead of the proven winner `(20-23, 0-8)`. Sweep 3 fixes this.
- **`SPREAD_PIPS` NameError in walk_forward.py (fixed 2026-03-30):** `test_oos()` referenced `SPREAD_PIPS` which was never defined. Should be `config.BACKTEST_SPREAD_PIPS`. Walk-forward run on 2026-03-21 crashed after fold 1 optimization but before OOS testing — explains why per-fold numbers were never recorded. Walk-forward 2026-03-30 is the first correctly-completed run.

---

## Per-Symbol Breakdown (IS, 2016–2026, current config)

| Symbol | Trades | WR% | Total R | PF | Expectancy | MaxDD |
|--------|--------|-----|---------|-----|-----------|-------|
| EURUSD | 30 | 23.3% | +67.2R | 3.92 | +2.240 | 17R |
| USDJPY | 59 | 15.3% | +65.6R | 2.31 | +1.112 | 20R |
| USDCHF | 30 | 16.7% | +39.0R | 2.56 | +1.299 | 11R |
| AUDUSD | 60 | 11.7% | +36.9R | 1.70 | +0.614 | 11R |
| USDCAD | 31 | 9.7% | +10.6R | 1.38 | +0.341 | 21R |
| NZDUSD | 55 | 9.1% | +14.4R | 1.29 | +0.261 | 15R |
| GBPUSD | 55 | 7.3% | +0.4R | 1.01 | +0.008 | 19R |

GBPUSD looks like a drag (breakeven over 10yr IS). GBPUSD removal was tested via walk-forward (2026-03-30) — **do not remove**. See below.

### GBPUSD removal WF test (2026-03-30)

| | 7 pairs | 6 pairs (no GBPUSD) |
|--|---------|---------------------|
| Fold 1 OOS expect | +0.682R (96%) | +1.203R (100%) |
| Fold 2 OOS expect | +0.244R (35%) | +0.538R (42%) |
| Fold 3 OOS expect | **+0.378R (72%)** | **+0.088R (9%)** |
| Agg OOS R | +110.9R, 260 trades | +94.7R, 150 trades |
| Avg retention | **67%** | **50%** |

Folds 1 and 2 improve without GBPUSD, but fold 3 (2024–2026) collapses to near-breakeven. GBPUSD contributed positively in the most recent OOS period despite poor IS stats. Removing based on IS performance is overfitting. Keep 7 pairs.

---

## Notes

- **XAUUSD:** Included in `run_backtest.py` SYMBOLS but excluded from WF/sweep (7 forex pairs only). Strategy's internal `pip_sizes` dict doesn't include XAUUSD — it falls back to 0.0001 default, which means pip-based filters (min_swing_pips, min_d1_atr_pips) don't work correctly for gold. Add `'XAUUSD': 0.10` to the strategy's pip_sizes dict if testing gold seriously.
- **fib_tp=2.0 in fold 3:** The most recent WF fold (2024–2026) chose fib_tp=2.0 not 3.0. This is the only disagreement across the 3 folds. The full IS sweep strongly favours 3.0. Monitoring live performance will clarify.
- **MODERATE, not STRONG:** Fold 2 (2022–2024) shows only 35% retention. That period was unusually volatile (COVID recovery, rapid Fed hikes). The strategy still profited OOS in all 3 folds.

---

## Running alongside EmaFibRunning

Portfolio manager now keys positions by `(symbol, strategy_name)` — both strategies can hold concurrent positions on the same symbol. Blocking analysis (IS, 7 pairs, 2016–2026):

- EmaFibRunning blocking EmaFibRetracement: **17 trades (all losses)** — EmaFibRunning's occupancy filters out bad EmaFibRetracement entries, saving 17R.
- EmaFibRetracement blocking EmaFibRunning: **101 trades (+76.6R net)** — EmaFibRetracement's pending orders were suppressing 45% of EmaFibRunning's signals, especially GBPUSD (35 blocked, +40R).

Combined unblocked IS result: 519 trades, +284.1R, MaxDD 28.5R (~14.3%). Peak simultaneous positions: 5.

## Next Steps

- [ ] Monitor demo performance against backtest expectancy (+0.774R/trade solo, +0.547R combined)
- [ ] Add `'XAUUSD': 0.10` to strategy pip_sizes if running gold seriously
