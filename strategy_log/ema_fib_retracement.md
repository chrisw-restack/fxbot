# EmaFibRetracement

**Status:** LIVE (demo)
**File:** `strategies/ema_fib_retracement.py`
**Timeframes:** D1 (bias), H1 (entry)
**Order type:** MARKET

---

## Current Config (as of 2026-03-22)

```python
EmaFibRetracementStrategy(
    fib_entry=0.786,
    fib_tp=2.5,
    fractal_n=3,
    min_swing_pips=10,
    ema_sep_pct=0.001,
    cooldown_bars=0,
    invalidate_swing_on_loss=False,
    blocked_hours=(*range(20, 24), *range(0, 9)),  # allow 09:00–19:00 UTC only
)
```

Risk override: 0.7% per trade (default is 0.5%).
Symbols: EURUSD, GBPUSD, AUDUSD, NZDUSD, USDJPY, USDCAD, USDCHF (7 pairs).

---

## Strategy Logic

- **Bias:** D1 EMA trend direction. Long if close > both EMAs (and EMAs separated by `ema_sep_pct`), short if below.
- **Swing:** Fractal-based swing high/low detection on H1 (N bars each side). Must be at least `min_swing_pips` in size.
- **Entry:** Wait for price to retrace to `fib_entry` level of the swing. Enter in bias direction.
- **SL:** Beyond the swing high/low.
- **TP:** Entry ± (SL distance × `fib_tp`). E.g. fib_tp=2.5 means 2.5× the SL distance from entry.
- **Session filter:** `blocked_hours` tuple — bars during these hours are skipped entirely.

---

## Walk-Forward History

| Date | Params snapshot | Folds | OOS trades | OOS total R | OOS expectancy | Avg retention | Verdict |
|------|----------------|-------|------------|-------------|----------------|---------------|---------|
| Pre-2026-03 | fib_entry=0.618, fib_tp=2.0, fractal_n=3, min_swing=10 | 3 | ~551 | +407R | +0.739 | 118% | STRONG — but this was before the D1 fill bug fix; results were inflated |
| 2026-03-20 | fib_entry=0.618 (original post-fix) | 3 | — | ~+2.9R total | ~breakeven | FAIL | After entry_timeframe fix, original params barely profitable |
| 2026-03-21 | fib_entry=0.786, fib_tp=2.5, fractal_n=3, min_swing=10, ema_sep=0.001, cooldown=0, blocked=(20-23,0-8) | 3 | 3 folds OOS positive | +45.1R | — | ~70% | MODERATE — 3 folds all positive |

Latest walk-forward fold detail (2026-03-21, blocked_hours session filter):

| Fold | Test period | OOS R | OOS Expect | OOS PF | Retain |
|------|-------------|-------|------------|--------|--------|
| 1 | 2019–2021 | — | — | — | — |
| 2 | 2021–2023 | — | — | — | — |
| 3 | 2023–2025 | — | — | — | — |
| **Agg** | | **+45.1R** | **positive** | | **~70%** |

> Exact per-fold numbers not recorded — re-run `python3 walk_forward.py ema_fib_retracement` to get current figures.

---

## Parameter Sweep History

### Sweep 1 (pre-bug-fix era)
- Optimized: fib_entry=0.618, fib_tp=2.0 as defaults
- Walk-forward showed STRONG but was inflated by D1/H4 fill bug

### Sweep 2 (2026-03-20 — post entry_timeframe fix)
- Grid: fib_entry [0.5, 0.618, 0.786], fib_tp [1.5, 2.0, 2.5, 3.0], fractal_n [2, 3, 5], min_swing_pips [10, 20, 30], ema_sep_pct [0.0, 0.001], cooldown_bars [0, 10], invalidate_swing_on_loss [True, False], swing_max_age [50, 100, 200]
- **Key finding:** fib_entry=0.786 dramatically outperforms 0.618. Deeper entry = tighter SL = larger R on wins.
- Best config: fib_entry=0.786, fib_tp=2.5, fractal_n=3, min_swing_pips=10
- Note: walk-forward selected fib_tp=3.0 in 2 of 3 folds, but fib_tp=2.5 chosen as more conservative. Not yet re-tested.

### Session filter sweep (2026-03-21)
- Swept 12 different blocked_hours windows
- **Winner:** block 20:00–08:00 UTC (allow London + early NY: 09:00–19:00)
- Result vs old window: +117R vs +85R, MaxDD 20R vs 33.5R
- Tokyo/Asian session trades were net-negative drag

---

## Bug History

- **D1/H4 fill bug (fixed 2026-03-19):** The original simulated_execution.py did not gate fills by timeframe. D1 bars (wide range) were triggering H1 pending orders on the same bar the order was placed, causing unrealistic fills. Fix: `entry_timeframe` field added to Signal/EnrichedSignal; fills and SL/TP checks now gated per-position by TF hierarchy.
- **Impact on EmaFib:** Moderate. EmaFib uses MARKET orders on H1, so D1 bars were not filling pending orders — but D1 bars could still trigger SL/TP on open positions from the same bar they opened. After the fix, results dropped from ~+407R to ~+2.9R (original 0.618 params). This confirmed the original walk-forward was significantly overstated.

---

## Known Issues / Open Questions

- fib_tp=3.0 was selected by walk-forward in 2 of 3 folds — worth running a dedicated walk-forward comparison of 2.5 vs 3.0
- MODERATE verdict (not STRONG) — acceptable for demo but not ideal. Monitor live performance before scaling risk.
- `blocked_hours` is currently hardcoded as a constructor arg — if deploying multiple EmaFib instances on different sessions this would need rethinking.

---

## Next Steps

- [ ] Run walk-forward with fib_tp=2.5 vs 3.0 to make final call
- [ ] Monitor demo performance — promote to live if results track backtest
- [ ] Consider adding USDCHF walk-forward data to the logs above
