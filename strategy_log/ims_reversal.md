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

### Forward Demo Review — 2026-06-10

Files reviewed: `logs/trade_journal.csv`, `logs/trading.log`, and `logs/ReportHistory-52775013.html`.

MT5 report attribution since 2026-05-11:

| Scope | Trades | Wins | Net P/L | Notes |
|-------|-------:|-----:|--------:|-------|
| IMSRev_H4_M15 | 12 | 1 | -$1,131.55 | 8.3% WR; recent demo underperforming validation |
| Full bot suite | 24 | 2 | -$2,269.99 | 8.3% WR across all closed positions |

This is poor, but not yet outside the known IMSRev risk profile. The latest available local Dukascopy
data only reaches 2026-03-19, so the May/June 2026 demo cluster cannot be replayed locally. A focused
replay over 2024-01-01 through available data (`python run_backtest.py ims_reversal_best --symbols
GBPNZD AUDUSD USA30 USDCHF XAUUSD AUDJPY AUDCAD USDCAD --start-date 2024-01-01 --end-date 2026-06-10`)
remained positive: 385 trades, 23.1% WR, +79.96R, PF 1.26, expectancy +0.21R, max DD 46.8R, worst loss
streak 22. The forward demo run is therefore a serious monitor item, but not enough evidence by itself
to change IMSRev parameters or remove it from demo.

Operational fix made during the review: MT5 close-history matching now keys off the tracked position/order
id instead of requiring the exit deal comment to match the strategy name. SL/TP exit deals usually carry
comments like `[sl ...]`, which caused the journal to fall back to cached PnL and record `r_multiple=0.0`.

### Forward Demo And Broker-Feed Review - 2026-07-14

Dukascopy H4/M15 data was extended through the last completed market day, 2026-07-13. The updated
backtest exactly reproduced the previous 2026-03-19 checkpoint before adding the new period, which
confirms that the strategy configuration and earlier result have not drifted.

| Scope | Trades | Win rate | Total R | PF | Expectancy | Max DD | Loss streak |
|-------|-------:|---------:|--------:|---:|-----------:|-------:|------------:|
| Dukascopy 2024-01-01 to 2026-03-19 checkpoint | 385 | 23.1% | +79.96R | 1.26 | +0.208R | 46.80R | 22 |
| Dukascopy new data, 2026-03-20 onward | 46 | 23.9% | +5.71R | 1.16 | +0.124R | 8.09R | 8 |
| Dukascopy full 2024-01-01 to 2026-07-13 | 431 | 23.2% | +85.67R | 1.25 | +0.199R | 46.80R | 22 |
| Dukascopy since deployment, 2026-04-23 onward | 30 | 23.3% | +4.84R | 1.21 | +0.161R | 6.12R | 6 |
| IC Markets 2025-01-01 to 2026-05-25 | 229 | 21.4% | +13.40R | 1.07 | +0.059R | 39.54R | 17 |
| Dukascopy same 2025-01-01 to 2026-05-25 window | 230 | 20.9% | +23.50R | 1.13 | +0.102R | 46.80R | 22 |

The MT5 report contains 23 filled IMSRev positions since deployment: 3 wins, 20 losses,
approximately -9.44 price-based R, and -$1,704.36 after commission and swap. This is materially
worse than the standalone Dukascopy replay. It is not evidence that different code is running:

- A direct replay of the saved IC Markets candles through 2026-05-25 produced 7 trades, 1 win,
  and -1.34R. The six comparable broker fills had 1 win and roughly -0.6R.
- Several broker orders were reproduced exactly or very closely, including AUDJPY on 2026-05-12,
  both XAUUSD trades on 2026-05-19/20, the 2026-06-08 cluster, both 2026-06-11 winners, and the
  2026-07-13 XAUUSD loss.
- Live portfolio constraints dropped six valid IMSRev signals, and an AUDJPY order on 2026-06-29
  failed because MT5 reported no network connection. Bot downtime also removed opportunities.
- Pending fills and H4/LTF structure are feed-sensitive. IC Markets remains profitable over its
  available 229-trade common window, but its expectancy is thinner than Dukascopy.

**Decision:** do not rework the core signal logic or change live parameters from this sample. Keep the
strategy on demo only. Reassess at 50 broker fills, or sooner if an updated IC Markets replay turns
negative over a meaningful sample. Any proposed symbol removal or filter must be tested one at a time
and pass walk-forward before changing `live_config.py`. The next validation priority is broker-specific
data coverage and portfolio-aware replay, not another unvalidated setup filter.

### Completed IC Markets Replay - 2026-07-15

Fresh IC Markets H4/M15 candles for all eight symbols were exported through 2026-07-14. The new
M15 overlap matches the live bot's logged timestamps and OHLC values. The terminal revised part of
the older AUDUSD overlap; the fresh export was treated as authoritative for overlapping bars.

The parity review also identified a shared simulation mismatch for BUY pending orders. MT5 places
the strategy's pending price directly and triggers a BUY from ask. `SimulatedExecution` currently
tests the unadjusted bid range and then adds spread to the fill price. This produced a false AUDCAD
winner on 2026-07-14: bid touched the pending price, but ask did not, so MT5 correctly left the order
unfilled and the strategy cancelled it. A broker-accurate experimental replay tested ask-touch at the
actual pending price without changing production backtest code.

| Source / period | Trades | Win rate | Total R | PF | Expectancy | Max DD | Loss streak |
|-----------------|-------:|---------:|--------:|---:|-----------:|-------:|------------:|
| IC Markets corrected, 2025-01-01 to 2026-07-14 | 250 | 20.0% | -2.19R | 0.99 | -0.009R | 41.82R | 17 |
| IC Markets corrected, deployment onward | 29 | 10.3% | -16.01R | 0.40 | -0.552R | 16.01R | 10 |
| IC Markets corrected, fresh export from 2026-05-20 | 23 | 13.0% | -9.88R | 0.52 | -0.430R | 14.73R | 10 |
| Actual demo, deployment onward | 23 | 13.0% | about -9.44R | n/a | -0.410R | n/a | 9 |
| Dukascopy corrected, 2024-01-01 to 2026-07-13 | 431 | 23.2% | +92.43R | 1.27 | +0.214R | 46.38R | 22 |

The actual demo did better than the standalone corrected broker replay because portfolio limits,
downtime, and one network failure skipped several modeled losses. Signal direction, price levels,
clusters, and outcomes otherwise align closely. The bot is executing the intended logic; the poor
demo result is not an implementation fault.

**Revised verdict:** the IMS Reversal concept remains profitable on Dukascopy, but no meaningful edge
is present in the available common IC Markets sample. Do not rework parameters against this short
broker window because that would invite overfitting. Recommend pausing/removing IMSRev from the IC
Markets demo suite pending a broker-specific revalidation with longer history. Do not change
`live_config.py` until the user approves. The shared pending-fill simulator correction must be handled
as a separate cross-strategy change with revalidation of every affected pending strategy.

### Extended IC Markets History - 2026-07-15

Increasing the requested range with MT5 chart history already set to unlimited recovered ten years of
broker-native H4/M15 data for five of the eight IMSRev symbols. AUDCAD, AUDJPY, and USDCAD remain
limited to 2025-01-01 onward on the IC Markets server.

| Symbols | Available period | Coverage note |
|---------|------------------|---------------|
| AUDUSD, GBPNZD, USDCHF | 2016-07-14 to 2026-07-14 | Continuous H4/M15 coverage |
| US30, XAUUSD | 2016-07-14 to 2026-07-14 | M15 contains hourly-only timestamps until April 2017; use 2017-04 onward for clean M15 comparison |
| AUDCAD, AUDJPY, USDCAD | 2025-01-01 to 2026-07-14 | Broker server returned no older bars |

The CSV audit found no duplicate timestamps, missing OHLC values, invalid candles, or out-of-order
rows. The broker-accurate BUY pending-order correction was promoted to `SimulatedExecution` after
focused regression coverage and the full test suite passed.

| Source / symbols / period | Trades | Win rate | Total R | PF | Expectancy | Max DD | Ending balance |
|---------------------------|-------:|---------:|--------:|---:|-----------:|-------:|---------------:|
| IC Markets, 5 complete symbols, 2016-07 to 2026-07 | 1,119 | 21.4% | +78.58R | 1.09 | +0.07R | 57.67R | $10,669.78 |
| Dukascopy, same 5 symbols and dates | 1,110 | 24.1% | +312.76R | 1.36 | +0.28R | 52.94R | $22,247.69 |
| IC Markets, 5 symbols, clean M15 period from 2017-04 | 1,072 | 21.3% | +64.00R | 1.07 | +0.06R | n/a | n/a |
| Dukascopy, same 5 symbols from 2017-04 | 1,012 | 23.4% | +256.28R | 1.32 | +0.25R | n/a | n/a |
| IC Markets, all 8 symbols, 2025-01 to 2026-07 | 251 | 20.3% | +0.59R | 1.00 | +0.00R | 39.04R | $9,114.93 |

`Total R` is the price-move R multiple before commission; account PnL includes configured commission.
The corrected five-symbol IC replay earns only 6.7% over ten years while suffering a 35.2% account
drawdown. Trade counts are close between feeds, but IC has a lower win rate and much lower payout
retention. This confirms outcome/fill sensitivity rather than a lack of historical signals.

Per-symbol IC results over the full available ten-year window were AUDUSD -18.72R, GBPNZD +34.16R,
US30 +25.91R, USDCHF +16.81R, and XAUUSD +20.42R. These are research observations, not evidence for
removing AUDUSD or promoting a four-symbol subset; any broker-specific subset must pass IC Markets
walk-forward validation and an untouched holdout after the shared pending-fill correction is made.

**Updated verdict:** the longer direct broker history removes the need for a proxy feed for these five
symbols, but it does not rescue the current IMSRev deployment. The IC edge is too thin to survive
costs and the all-eight-symbol common period is flat before costs. Keep the recommendation to pause
IMSRev on IC Markets. A future rework should be treated as a new IC-native strategy validation, not a
minor retune of the Dukascopy configuration.

### IC Markets Symbol Salvage Test - 2026-07-15

Added ten-year IC Markets H4/M15 exports for EURUSD, GBPUSD, NZDUSD, USDJPY, USTEC, and US500.
All files passed structural validation. USTEC and US500 have hourly-only timestamps in their nominal
M15 history before April 2017, matching the old US30/XAUUSD limitation; all strict OOS folds begin in
2020 and are unaffected.

The established parameters were tested without tuning across the eleven long-history IC symbols.
Each OOS fold resets strategy state and uses broker-accurate pending fills. Net R includes configured
spread and broker-specific commission. The MT5 report confirmed that IC Markets index CFDs are
spread-only, while FX and XAUUSD pay commission; the simulator was corrected accordingly. The folds
are 2020-2021, 2022-2023, and 2024-2025.

| Symbol | Fold 1 net R | Fold 2 net R | Fold 3 net R | Aggregate net R | Positive folds | Verdict |
|--------|-------------:|-------------:|-------------:|----------------:|---------------:|---------|
| AUDUSD | -15.80 | -23.32 | -1.76 | -40.88 | 0/3 | FAIL |
| EURUSD | +13.80 | +4.39 | +13.95 | +32.14 | 3/3 | STRONG candidate |
| GBPNZD | -2.93 | -2.71 | +17.43 | +11.79 | 1/3 | WEAK/regime-dependent |
| GBPUSD | -14.72 | +21.55 | +24.25 | +31.08 | 2/3 | WEAK; one severe failed fold |
| NZDUSD | +6.34 | -18.85 | -16.33 | -28.84 | 1/3 | FAIL |
| US30 | +0.65 | -1.05 | +5.72 | +5.32 | 2/3 | Thin/flat |
| US500 | -38.09 | +20.00 | -7.07 | -25.16 | 1/3 | FAIL |
| USDCHF | +10.76 | -14.55 | +5.65 | +1.86 | 2/3 | Flat after costs |
| USDJPY | -1.31 | +7.00 | +2.69 | +8.38 | 2/3 | Thin/WEAK |
| USTEC | +6.86 | +22.11 | -1.29 | +27.68 | 2/3 | WEAK; failed latest fold |
| XAUUSD | +21.93 | -1.64 | -17.01 | +3.28 | 1/3 | Decaying/FAIL |

The short-history 2025-2026 symbols cannot be walk-forward validated. Their available net results are
AUDCAD -5.15R (27 trades), AUDJPY +0.35R (36 trades), and USDCAD +5.51R (25 trades). USDCAD is worth
monitoring but has insufficient history for promotion.

A research subset selected from the strict folds by requiring positive aggregate OOS net R and at
least two profitable folds was EURUSD, GBPUSD, US30, USDCHF, USDJPY, and USTEC. It was positive in each
combined OOS fold through 2025 (+16.04R, +39.45R, and +50.97R net). An additional fresh-state replay
over 2026-01-01 through 2026-07-14 produced 64 trades, 12 wins, -9.76R net, net PF 0.82, and -0.153R
expectancy. GBPUSD (+4.62R) and US30 (+6.93R) were profitable; EURUSD (-7.57R), USDCHF (-2.91R),
USDJPY (-6.46R), and USTEC (-4.37R) lost. This is a recent-period stress test rather than a pristine
holdout because parts of 2026 had already appeared in the earlier broker review.

**Decision:** symbol replacement does not currently salvage IMSRev as a robust IC Markets portfolio.
EURUSD is the only convincing long-run individual candidate, but it opened the 2026 check with seven
straight losses. GBPUSD is profitable in 2026 but failed the first OOS fold; adding it based on the
latest period would be period-selection overfitting. USTEC improves after correcting index commission
but failed the latest OOS fold and the 2026 check. Do not alter the live/demo suite from this search.
Pause the current IC suite as previously recommended, or treat EURUSD-only/GBPUSD research as a
separate future demo experiment with a genuinely new forward-validation checkpoint.

### EURUSD-Only Forward Demo Decision - 2026-07-15

The user approved pausing the deployed eight-symbol IMS Reversal suite and retaining EURUSD as a
separate forward-demo research candidate. `live_config.py` now subscribes `IMSRev_H4_M15` only to
EURUSD. Parameters, strategy name, magic number `1005`, and the global `0.5%` demo risk remain
unchanged.

The evidence cutoff is 2026-07-14. Bars and actual demo trades after that date are forward evidence
and must not be used to tune parameters during the trial. An interim review can be made after 12
months or 15-20 closed trades, but at least 30 trades are required before promotion is considered;
50 trades are preferable. Promotion also requires positive net expectancy, PF above 1, acceptable
drawdown, and close agreement between actual broker signals/fills and a frozen IC Markets replay.

On the first restart, cancel any still-pending IMS Reversal orders on the removed symbols. Filled
positions may remain to their broker SL/TP and will continue to be reconciled by magic number.

Operational follow-up on 2026-07-16: before this configuration reached the VPS, XAUUSD pending ticket
`1810114142` received a valid strategy cancellation during the broker's daily maintenance window.
MT5 returned `Market closed`; the one-shot cancellation was not retried, and the order later filled.
Shared cancellation handling now retries temporary failures without ever converting a pending-order
cancellation into a position close. The resulting XAUUSD trade remains an old-suite trade and is
excluded from the EURUSD forward sample.

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
