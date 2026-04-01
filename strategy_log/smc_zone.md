# SMC Zone

**Status:** SHELVED — too few trades (11/yr) for reliable walk-forward; IS edge not strong enough to justify
**File:** `strategies/smc_zone.py`
**Timeframes:** D1, H4 (tf_entry configurable)
**Order type:** MARKET

---

## Strategy Logic

Swing pivot zones (Williams fractal) with 3-candle BOS confirmation and wick rejection market entry.

1. **Zone detection:** Pivot high/low using `swing_length` bars each side. Demand = pivot low + ATR×zone_atr_mult wide. D1 EMA bias filter (demand in uptrend, supply in downtrend).
2. **Zone leg filter (optional):** The impulse move away from the pivot (over the `swing_length` bars after) must be ≥ `zone_leg_atr × ATR`. Rejects weak pivots formed by slow grinds.
3. **Fractal BOS:** 3-candle fractal inside zone confirms short-term structure break.
4. **Wick rejection entry:** After BOS, bar wicks into zone (`low ≤ zone.top`) but closes back outside (`close > zone.top`) AND closes bullish (`close > open`) → MARKET BUY.
5. **SL:** `zone.bottom - sl_buffer_atr × ATR` (structural, below swing low).

---

## Development History (2026-04-01)

### v1 — Pending at POI (H1)
5,579 trades. Commission ($9,517) nearly wiped the account. Discarded.

### v2 — Fractal BOS + pending at zone.top (H4)
169 trades after bug fixes. WR 29.6%, expectancy negative. Discarded.

Key bugs found:
- Pending-at-POI flaw: price passes through POI to reach BOS level, filling the pending order before cancellation can fire. Fixed by moving entry to far side of zone (zone.top for demand).
- `_bar_count` bug: deque maxlen caps `len()` at a constant, making `bars_since_creation` always 0. Fixed with a separate incrementing `_bar_count` counter.

### v3 — Wick rejection MARKET entry (H4) — final
Zone cleared on signal emission. Portfolio manager handles "one position at a time". Win/loss both reset zone state.

Bug fixed: `_order_placed` lock never reset on WIN (only `notify_loss` fired). Removed `_order_placed` entirely — zone cleared at signal, portfolio manager blocks re-entry.

---

## Parameter Sweep (2026-04-01)

Grid: swing_length [3,5,7,10] × zone_atr_mult [1.0,1.5,2.0,2.5,3.0] × zone_leg_atr [0.0,1.0,1.5,2.0,2.5] = 100 combos. 7 pairs, H4, 2016–2026.

**Top results by expectancy (min 30 trades):**

| swing_len | zone_atr | leg_atr | Trades | WR | Expectancy | PF | MaxDD | Streak |
|-----------|----------|---------|--------|----|------------|-----|-------|--------|
| 3 | 1.5 | 1.5 | 107 | 43.9% | +0.318R | 1.57 | 10R | 5 |
| 3 | 1.5 | 2.5 | 60 | 43.3% | +0.300R | 1.53 | 8R | 5 |
| 3 | 1.5 | 0.0 | 127 | 43.3% | +0.299R | 1.53 | 15R | 8 |
| 3 | 1.5 | 1.0 | 128 | 42.2% | +0.266R | 1.46 | 16R | 8 |
| 3 | 2.0 | 1.5 | 190 | 41.1% | +0.232R | 1.39 | 18R | 11 |

Key finding: **zone_atr_mult=1.5 was the main driver** — tighter zones around the swing extreme are more precise and hold more reliably. swing_length=3 won across all configurations; broader pivots (5, 7, 10) consistently underperformed.

### Filters tested

- **Bullish close (close > open):** +0.02R improvement, minimal impact.
- **BOS spacing (≥3 bars between BOS and entry):** Harmful — halved trades, WR dropped to 35.8%, expectancy collapsed to +0.07R. Trades close to BOS are higher quality.
- **Zone leg filter (zone_leg_atr=1.5):** +0.086R over no-filter baseline (at zone_atr_mult=1.5). Modest but real.

---

## Assessment

Best IS combo: swing_length=3, zone_atr_mult=1.5, zone_leg_atr=1.5 → +0.318R expectancy, PF 1.57, MaxDD 10R, worst streak 5.

**Why shelved:**
- Only 107 trades over 10 years = ~11/year. Walk-forward (4yr train / 2yr test) would yield ~20 OOS trades per fold — too sparse to distinguish edge from luck (same problem as EBP, IMS).
- IS expectancy of +0.318R is below live suite (+0.427–0.547R).
- The WR ceiling across all configs appears to be ~40–44%. Filters improve it marginally but can't break through substantially.
- The fundamental issue: zone-based entries depend on price returning to and holding a level, which happens reliably ~40% of the time regardless of zone detection method.

Shelved. Could revisit with more years of data or a different entry mechanism (e.g. pending limit at zone boundary rather than wick rejection).
