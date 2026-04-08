# HourlyMeanReversion — Strategy Log

## Concept
ICT Power-of-3 / Institutional Candle Mean-Reversion (inspired by @itstomtrades).
- H1 candle runs cleanly in one direction for the first 20–40 minutes.
- MSS on M5 (or M1) in the opposite direction triggers a mean-reversion entry.
- SL = confirmed swing extreme (fractal high/low from the run).
- TP = 50% retracement of the H1 candle range (open → peak/trough).
- Designed for XAUUSD. Asian + London sessions (UTC 00:00–16:59).

## MSS Detection Logic
For UP run → SELL:
1. Fractal swing HIGH confirmed (fractal_n bars each side).
2. If a fractal swing LOW also formed during the run → MSS = close breaks below that LOW (traditional ICT).
3. Otherwise (clean run, no fractal lows) → MSS = close breaks below the peak bar's own LOW.
Mirror logic for DOWN run → BUY.

Geometry filter: entry must be ABOVE the H1 midpoint (upper half of range) to ensure viable R:R.

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
- M1 CSV: not yet downloaded. Add `'M1'` to TIMEFRAMES in `fetch_data_dukascopy.py`.
  M1 gives more precise MSS detection and ~5–10× more signals.

## Why M1 is Better
On M5, fractal confirmation takes ~10 min. By then, price has often retraced past the
50% TP level, so the geometry filter blocks the trade. On M1, confirmation takes ~2 min
→ entries are closer to the peak, better R:R, more signals.

## Validated Params (XAUUSD M5, walk-forward confirmed)
```python
HourlyMeanReversionStrategy(
    tf_lower='M5',
    min_move_pips=100,        # fold 3 winner (most recent train data 2020-2024)
    entry_window_start=20,
    entry_window_end=45,
    fractal_n=1,
    max_pullback_pips=0,
    session_hours=tuple(range(8, 17)),  # London only
)
```

## Walk-Forward: XAUUSD M5 — STRONG ✓
Folds: 4yr train / 2yr test / 2yr step. 2016–2026 data.

| Fold | Test Period | OOS Trades | OOS WR | OOS Expect | OOS PF |
|------|-------------|-----------|--------|-----------|--------|
| 1 | 2020–2022 | 13 | 53.8% | +0.242R | 1.53 |
| 2 | 2022–2024 | 14 | 57.1% | +0.271R | 1.63 |
| 3 | 2024–2026 | 13 | 53.8% | +0.288R | 1.62 |
| **Agg** | **2020–2026** | **40** | **55%** | **+0.265R** | **~1.60** |

All 3 folds positive. Params consistent across folds (move=50-100, fn=1, London).

**Caveat: ~5 trades/year on M5 is very sparse.** Strategy edge is real but expect long dry spells.
M1 data should multiply signals ~5-10× without changing the logic.

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
XAUUSD M5: **VALIDATED MODERATE** — live-eligible on demo with caution (sparse trade count).
FX + USA100: **SHELVED** pending M1 retest.

## Backtest Commands
```bash
# Edit SYMBOLS in run_backtest.py: SYMBOLS = ['XAUUSD']
python3 run_backtest.py hmr

# Parameter sweep (M5):
python3 param_sweep_hmr.py

# Walk-forward validation:
python3 walk_forward.py hmr
python3 walk_forward.py hmr_fx          # FAIL — do not use
python3 walk_forward.py hmr_usa100      # MODERATE/WEAK — not live-eligible

# Once M1 data downloaded:
python3 run_backtest.py hmr_m1
```

## Download M1 Data
```python
# In fetch_data_dukascopy.py, set:
SYMBOLS = ['XAUUSD']
TIMEFRAMES = ['M1']
START_YEAR = 2016
```
Then: `python3 fetch_data_dukascopy.py`
