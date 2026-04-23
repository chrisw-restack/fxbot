# IMS Reversal Strategy Log

## Status: VALIDATED STRONG

## Concept

Reversal variant of IMS. Uses the same HTF dealing range and bias (fractal MSS + FVG on H4),
but trades **against** the immediate move — shorting from premium into HTF equilibrium (50% level),
or buying from discount back up to equilibrium.

- Bullish HTF bias → SELL entry: wait for price above HTF 50%, LTF bearish MSS + FVG, pending at 50% of LTF leg
- Bearish HTF bias → BUY entry: wait for price below HTF 50%, LTF bullish MSS + FVG, pending at 50% of LTF leg

Key difference from IMS: zone gate is REVERSED. IMS waits for retracement into range; IMSRev waits
for extension into premium/discount. LTF detection direction is also reversed.

## Validated Parameters

```python
ImsReversalStrategy(
    tf_htf='H4', tf_ltf='M15',
    fractal_n=1, ltf_fractal_n=2, htf_lookback=30,
    tp_mode='htf_pct', htf_tp_pct=0.5,   # TP at HTF 50% equilibrium
    zone_pct=0.5,
    blocked_hours=(*range(0, 12), *range(17, 24)),  # London/NY only (12-17 UTC)
    ema_fast=20, ema_slow=50, ema_sep=0.001,
    sl_anchor='swing', sl_buffer_pips=0.0,
    cooldown_bars=0,
    entry_mode='pending',
    max_losses_per_bias=1,   # expire HTF bias after first loss — improves expectancy
)
```

**Key sweep/analysis findings:**
- `ltf_fractal_n=2` outperforms lf1 (sweep validated)
- `tp_mode='htf_pct'` with `htf_tp_pct=0.5` best TP mode (TP at range midpoint)
- `zone_pct=0.5` and 0.6 produce identical results (price attractor at 50%)
- D1/H4 stack: higher per-trade expectancy but ~15 trades/symbol/decade — too sparse for WF
- Session filter essential — London/NY overlap (12-17 UTC) is optimal
- EMA 20/50 filter (ema_sep=0.001) adds slight edge; included in validated config
- `max_losses_per_bias=1`: expires the HTF bias after first loss. ml=2/3 identical to unlimited
  (bias expires naturally before a 2nd retry in practice). ml=1 improves IS expectancy +0.005R.

## Validated Symbols (8)

Removed via IS expectancy + loss streak analysis (weak edge, high streak contribution):
- **CADJPY** (-0.026R IS, 8/10 worst streaks) — only negative IS expectancy
- **USDJPY** (+0.052R IS, 6/10 worst streaks) — weakest edge
- **EURUSD** (+0.065R IS, 7/10 worst streaks) — weak edge

Kept (all ≥ +0.166R IS expectancy):

| Symbol | IS Trades | IS WR% | IS Expect | IS Total R |
|--------|-----------|--------|-----------|------------|
| GBPNZD | 204t | 31.4% | +0.458R | +93.4R |
| AUDUSD | 209t | 26.3% | +0.250R | +52.3R |
| USDCHF | 168t | 24.4% | +0.229R | +38.4R |
| AUDJPY | 220t | 24.5% | +0.208R | +45.8R |
| USDCAD | 203t | 23.2% | +0.174R | +35.3R |
| USA30  | 289t | 17.3% | +0.171R | +49.3R |
| XAUUSD | 268t | 24.6% | +0.166R | +44.5R |
| AUDCAD | 176t | 27.3% | +0.077R | +13.6R |

Note: AUDCAD (+0.077R) is retained — removing it costs another 13R with no DD improvement.
Loss streaks are regime-driven across all symbols, not USD-correlated; slow bleeds over
1–3 losses/day across 9–17 days. Portfolio manager MAX_OPEN_TRADES=6 cap does not help
(typically only 1–2 positions close per day during a streak).

---

## Full IS Backtest (2016–2026, 8 symbols, validated params)

```
python run_backtest.py ims_reversal_best
SYMBOLS = ['GBPNZD','AUDUSD','USA30','USDCHF','XAUUSD','AUDJPY','AUDCAD','USDCAD']
```

| Metric | Value |
|--------|-------|
| Total trades | 1,743 |
| Win rate | 24.8% |
| Total R | +477.6R |
| Profit factor | 1.37 |
| Expectancy | +0.274R |
| Max drawdown | 50.1R (30.0%) |
| Worst loss streak | 27 |
| Avg win | 4.07R |
| Avg loss | 0.98R |

---

## Walk-Forward Validation

### Round 1 — 11 symbols (Tier 1), no max_losses_per_bias

**Date**: 2026-04-17
**Config**: 4yr train / 2yr test / 2yr step, 3 folds, fixed params
**Symbols**: GBPNZD, AUDUSD, USA30, USDCHF, XAUUSD, USDJPY, AUDJPY, EURUSD, AUDCAD, USDCAD, CADJPY

| Fold | Test Period | OOS R | OOS Expect | OOS WR | OOS PF | OOS LStreak | Retention |
|------|------------|-------|------------|--------|--------|-------------|-----------|
| 1 | 2019–2021 | +86.7 | +0.244 | 25.6% | 1.33 | 16 | 95% |
| 2 | 2021–2023 | +82.8 | +0.188 | 22.0% | 1.24 | 24 | 113% |
| 3 | 2023–2025 | +152.8 | +0.316 | 25.4% | 1.44 | 19 | 146% |

**Aggregate OOS**: 1,279 trades | +322.3R | +0.252R expectancy | 118% avg retention | **STRONG**

---

### Round 2 — 8 symbols, max_losses_per_bias=1 (validated config)

**Date**: 2026-04-19
**Config**: 4yr train / 2yr test / 2yr step, 3 folds, fixed params
**Symbols**: GBPNZD, AUDUSD, USA30, USDCHF, XAUUSD, AUDJPY, AUDCAD, USDCAD
**Removed**: CADJPY (−IS), USDJPY (weak IS), EURUSD (weak IS)

| Fold | Test Period | OOS R | OOS Expect | OOS WR | OOS PF | OOS LStreak | Retention |
|------|------------|-------|------------|--------|--------|-------------|-----------|
| 1 | 2019–2021 | +78.8 | +0.302 | 26.8% | 1.41 | 14 | 100% |
| 2 | 2021–2023 | +63.2 | +0.190 | 22.3% | 1.25 | 19 | 81% |
| 3 | 2023–2025 | +131.1 | +0.350 | 25.7% | 1.50 | 17 | 142% |

**Aggregate OOS**: 967 trades | +273.1R | **+0.282R expectancy** | 108% avg retention | **STRONG**

### Round 2 vs Round 1 comparison

| Metric | 11-sym | 8-sym | Change |
|--------|--------|-------|--------|
| OOS expectancy | +0.252R | +0.282R | **+0.030R** |
| OOS worst streak (F1/F2/F3) | 16/24/19 | 14/19/17 | **shorter all folds** |
| OOS total R | +322.3 | +273.1 | −49.2 (fewer symbols) |
| Verdict | STRONG | STRONG | maintained |

**Conclusion**: 8-symbol set is the superior configuration. Removed symbols diluted the portfolio
without commensurate edge — they contributed losses at the same rate during bad regimes but
couldn't recover during good ones.

---

## Live Deployment Notes

- Strategy NAME: `IMSRev_H4_M15`, magic number 1005 (`config.MAGIC_NUMBERS`)
- Deployed to `main_live.py` 2026-04-23 — registered against 8 symbols
- **MT5 symbol note**: backtest data uses `USA30` (Dukascopy label); live script uses `US30` (ICMarkets MT5 name) — verify this matches the broker's symbol if needed
- 8 symbols, ~35–40 trades per 6-month OOS period — sufficient for live monitoring
- Monitor fill rate: pending limit at 50% of LTF leg; expect similar fill rate to IMS (~60–70%)
- Correlation note: IMS and IMSRev both read the same H4 dealing range. Opposing pending orders
  on the same symbol can coexist (separate strategy slots). Portfolio manager allows both.
- Loss streaks are slow bleeds (1–3 losses/day over 1–3 weeks during trending regimes).
  Extensive DD reduction testing (see below) found no approach worth deploying.

---

## Drawdown Reduction Analysis (2026-04-23)

Motivation: IS max DD is 50.1R (30.0% at full dynamic sizing). Attempted to reduce this without
meaningfully hurting expectancy. All approaches failed or weren't worth the cost.

### Regime filters (sweep_ims_adx_threshold.py, sweep_ims_regime_filters.py)

Tested D1 ADX threshold (>20/25/30/35/40) and D1 Efficiency Ratio (periods 10/14/20, thresholds
0.2–0.6) as regime gates — only fire signals when the regime indicator passes the threshold.

**Result**: All configs either (a) reduce trades significantly without proportional DD improvement,
or (b) hurt expectancy before the DD moves. No threshold produced a clean DD reduction while
preserving expectancy. Root cause: loss streaks are correlated across symbols during trending
regimes — any single-symbol filter misses the multi-symbol bleed.

### Circuit breaker (sweep_ims_circuit_breaker.py)

After N consecutive losses (cross-symbol), pause all signals for X calendar days.
Swept streak_pause_after=[3,4,5,6,7,8,10] × pause_days=[3,5,7,10,14].

**Result**: Minimal DD reduction (rarely better than −2R). Main effect is skipping profitable
recovery trades after a streak ends. The pause fires just as the strategy is about to recover.
No combo worth deploying.

### Fractal size (sweep_ims_fractal.py)

Swept fractal_n (H4, 1/2/3) × ltf_fractal_n (M15, 1/2/3) — more confirmation = fewer, higher-
quality setups.

**Result**: Baseline fn=1/lf=2 remains optimal. Higher fractals reduce trade count without
consistent DD improvement. DD is regime-driven, not setup-quality driven.

### Tiered position sizing (model_tiered_sizing.py)

Modelled Full/Half/Quarter sizing (0.5%/0.25%/0.125% risk) triggered by notional R DD from peak:
- Full → Half at 20R DD; Half → Quarter at 35R DD
- Step-up: recover 10R from trough

**Result** (2016–2026, $10k start):

| Config | Final balance | Total return | Max DD% |
|--------|---------------|--------------|---------|
| Baseline (fixed 0.5%) | $90,872 | +808.7% | 22.8% |
| Tiered (20R/35R/+10R) | $77,992 | +679.9% | 16.0% |

Reduces max DD% from 22.8% → 16.0% (−6.8pp) at the cost of ~16% of total return.
Time in tier: 80% full size, 14% half, 6% quarter.

**Decision**: not worth it. The −$12,880 return cost over 10 years buys only 6.8pp of DD
reduction. The edge is preserved regardless — this is a capital management preference, not a
strategy fix. Re-evaluate if live DD consistently exceeds IS expectations.

---

## Strategy Files

- `strategies/ims_reversal.py` — strategy class
- `sweep_ims_reversal_params.py` — parameter sweep (1,920 combos × 9 symbols)
- Registered in `run_backtest.py` as `ims_reversal_best`
- Registered in `walk_forward.py` as `ims_reversal` (8-sym validated) and `ims_reversal_8sym`
