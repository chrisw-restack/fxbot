# Analysis of HourlyMeanReversionStrategy

After thoroughly analyzing `/strategies/hourly_mean_reversion.py`, I can confirm whether the strategy relies on forward lookup biases and identify several critical logical errors that drastically restrict its performance or execute trades under false assumptions.

## 1. Forward Lookup Bias Check: **CLEAN ✓**

The good news is that **there is no forward lookup bias or lookahead data leakage** in this code.
- The strategy utilizes `self._buf` properly as a rolling window of recent M5 bars.
- You only confirm a fractal swing point (`mid_bar`) when the currently completing bar (`event`) has a lower high (for fractals highs) or higher low (for fractal lows).
- The checks (`if event.close < mss_level`) happen entirely at the close of `event`, utilizing information constructed up to that exact moment.
- The `tp` limit orders and variables like `h1_open` and `self._peak` do not bleed future data because they are dynamically updated bar-by-bar before any checks run.

The Walk-Forward results you measured (55% WR, sparse trades) are structurally legitimate.

## 2. Logic Issue: Stop Loss (SL) Missing the True Sweep High

**Severity: HIGH**

In your markdown log, you specify `SL = confirmed swing extreme (fractal high/low from the run)`. The code faithfully places the stop loss at `self._last_sh` (the last *confirmed* fractal high). However, this causes a major vulnerability in Market Structure Shift (MSS) mechanics:

**The Issue:** A very common MSS setup involves a sudden "liquidity sweep" bar that shoots up to create a massive new absolute peak, then violently rejects and closes below the internal low (`mss_level`).
- When this happens, `self._peak` updates instantly to the new high.
- But `last_sh` **DOES NOT UPDATE**, because it takes `fractal_n` subsequent bars to confirm that sweep wick as a fractal.
- The code triggers an entry right away on the sweep bar's close.
- Your `sl` is placed at the OLD `last_sh`—which is drastically lower than the actual sweep high!
- **Result:** You place your true Stop Loss *inside* the wick of the absolute top of the run, virtually guaranteeing a premature stop-out if price breathes into the wick before dropping further to TP.

**The Fix:** You should set your Stop Loss at the absolute peak/trough of the evaluated run:
```python
# For SELL setups:
sl = self._peak[sym]

# For BUY setups:
sl = self._trough[sym]
```

## 3. Logic Issue: `max_pullback_pips` Fails to Track Choppiness

**Severity: MODERATE** (Nullified currently because `max_pullback_pips = 0`)

The code tracks "intra-run pullback depth" by comparing `self._peak` against `self._peak_pullback_low`.

**The Issue:** Whenever price makes a new high, `self._peak_pullback_low` structurally resets to the new peak bar's own low:
```python
if event.high > self._peak[sym]:
    self._peak[sym] = event.high
    self._peak_pullback_low[sym] = event.low # Completely resets!
```
If a run goes up 150 pips, has a **massive 100-pip drop**, and then slowly grinds up to a new high (151 pips) through tiny higher-low bars, the massive 100-pip drop is entirely erased from memory. `up_pullback` becomes 0. The code will mischaracterize the run as a "clean one-directional run" when it wasn't.

**The Fix:** You need a global `max_pullback_seen` variable for the hour that persists the largest recorded difference without resetting. If you do parametric sweeps with values > 0, the current implementation is flawed and won't filter out choppy runs correctly.

## 4. Logic Bug: `last_sl` Fallback Blockade

**Severity: MODERATE**

For a SELL, the script determines the `mss_level`:
```python
mss_level = last_sl if last_sl is not None else (
    last_sh_bar.low if last_sh_bar is not None else None
)
```
**The Issue:** Because of standard conditional logic, if *any* fractal low forms during the hour, it enforces the requirement that price must break **all the way back down to that low**.
If the hour starts with a minor dip at 00:05 and then rallies linearly 120 pips for the next 30 minutes, `last_sl` is stuck at the bottom dip of the hour.
To trigger a short, price must drop 120 pips to break the bottom of the hour, which will completely blow past the 50% `tp` level. Your geometry rule (`sl > event.close > tp`) will permanently block these trades.

**Impact:** This hyper-restrictive logic is likely the primary mathematical reason you are only seeing ~5 trades a year on M5. By using `last_sh_bar.low` slightly more dynamically (or the fractal low closest to the peak), you could safely boost trade counts dramatically without dropping to M1.
