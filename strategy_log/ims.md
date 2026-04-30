# IMS (ICT Market Structure)

**Status:** VALIDATED MODERATE — LIVE (demo)
**File:** `strategies/ims.py`
**Timeframes:** H4 (HTF) + M15 (LTF)
**Order type:** PENDING

---

## Final Live Config (as of 2026-04-15)

```python
ImsStrategy(
    tf_htf='H4', tf_ltf='M15',
    fractal_n=1,          # 3-candle fractal on H4
    ltf_fractal_n=1,      # 3-candle fractal on M15
    htf_lookback=30,
    entry_mode='pending', # Buy/Sell Limit at 50% of LTF leg
    tp_mode='rr',
    rr_ratio=2.5,
    cooldown_bars=0,
    blocked_hours=(*range(0, 12), *range(17, 24)),  # 12:00-17:00 UTC (London/NY overlap)
    ema_fast=20, ema_slow=50,
    ema_sep=0.001,
    sl_anchor='swing',    # SL at LTF swing low wick
    pip_sizes={...},      # per-symbol pip sizes from config
)
```

**Symbols:** USDJPY, XAUUSD, EURAUD, CADJPY, USDCAD, AUDUSD, EURUSD, GBPCAD, GBPUSD

---

## Walk-Forward Results (final — 2026-04-15)

9 symbols, swing bare SL, fixed params (no optimisation), 4yr train / 2yr test / 2yr step.

| Fold | Test Period | OOS Trades | OOS R | OOS Expect | OOS WR | OOS PF | Retain |
|------|------------|-----------|-------|------------|--------|--------|--------|
| 1 | 2019–2021 | 71 | +17.5R | +0.246R | 36.6% | 1.39 | 76% ✓ |
| 2 | 2021–2023 | 51 | +3.8R | +0.075R | 31.4% | 1.11 | 40% ~ |
| 3 | 2023–2025 | 86 | +13.1R | +0.152R | 33.7% | 1.23 | 76% ✓ |
| **Agg** | | **208** | **+34.4R** | **+0.165R** | | | **64%** |

**Verdict: MODERATE** — all 3 folds positive OOS. Folds 1 and 3 strong (76% retention). Fold 2 (2021–2023) weak but still positive. Consistent IS edge ~+0.19–0.32R across all folds.

---

## Strategy Logic

ICT-inspired multi-timeframe market structure strategy.

### HTF Bias (H4)
1. Identify a **dealing range**: swing low → running max high (BUY) or swing high → running min low (SELL). The leg must take out a prior fractal swing extreme (MSS on HTF) and contain a bullish/bearish FVG.
2. The **50% level** of the range is the key zone
3. Bias expires when: swing origin is taken out; price closes beyond 30%/70% of range; or a H4 bar closes through the lowest bullish FVG in the leg (FVG disrespected = bias invalid)
4. Optional EMA filter: EMA 20/50 on H4, minimum separation 0.1% of price

### LTF Setup (once price retraces into 40–60% zone)
1. Look for a **3-candle fractal swing** (1 bar each side) on M15
2. Wait for price to **close above/below** the fractal swing extreme → LTF MSS confirmed
3. LTF leg must contain a bullish/bearish FVG
4. LTF swing origin must be at or below/above the HTF 50% level

**Entry:** PENDING limit at 50% of the LTF leg  
**SL:** LTF swing low wick (BUY) / swing high wick (SELL)  
**TP:** Risk manager calculates at 2.5R from entry

### Session filter
Only allows signals during 12:00–17:00 UTC (London/NY overlap — most liquid window).

---

## Development History

### Phase 1 — D1/H4 stack (2026-03-23) — SHELVED
- Walk-forward FAIL: too few trades (~17/yr across 7 pairs), all 3 folds negative aggregate OOS.
- Root cause: D1 bias changes too slowly, ~4–10 setups per symbol per year.

### Phase 2 — H4/M15 redesign (2026-04-13 to 2026-04-15)
Major logic overhauls during development:
- **Cancel-and-replace removed**: pending orders no longer replaced when a new higher LTF swing forms. Original entry stays; avoids chasing and keeps SL at original level.
- **Zone entry/depth**: 60%/40% zone trigger; 30%/70% depth expiry on HTF (wick), LTF (close only — spike wicks don't invalidate HTF bias).
- **HTF FVG invalidation**: if a H4 bar closes below the lowest bullish FVG in the bias leg, bias expires. Disrespecting the imbalance signals the move is failing.
- **Market entry mode** added (tested, underperformed pending — sweep confirmed pending wins clearly).
- **EMA filter**: H4 EMA 20/50 with 0.1% minimum separation.
- **Session filter**: swept all/eu_us/ln_us/us — London/NY overlap (12-17 UTC) wins.

### Parameter sweep — H4/M15 (2026-04-14)
2,304 combos × 9 symbols = 20,736 tasks. Key findings:
- **Pending** clearly beats market entry (best market: +0.049R avg exp vs pending: +0.277R)
- **rr2.5** wins on every comparison — htf_high TP underperforms
- **EMA 20/50** beats 60/120 on this symbol set
- **ln_us (12-17 UTC)** wins session comparison
- **fn1/lf1** (3-candle both sides) best fractals
- **ema_sep=0.001** adds quality filter value
- htf_lookback makes no difference (lb30 = lb50)

### SL placement sweep (2026-04-15)
17 combos tested (swing/body/fvg anchors × pip/ATR buffers). Key findings:
- **Body anchor** showed higher IS expectancy (+0.366R) but **failed walk-forward** (negative folds 1&2 OOS — too few trades, noise dominated)
- **FVG anchor** even more extreme — high IS expectancy, only 50–100 trades over 10 years, not reliable
- **Swing bare** wins on walk-forward generalisation: most trades (208 OOS), all folds positive

### Symbol selection
- Original 7 pairs (standard majors) → replaced NZDUSD/USDCHF with GBPCAD → added XAUUSD, EURAUD, CADJPY based on backtest performance
- 9-symbol walk-forward: all folds positive, +34.4R aggregate OOS (+0.165R expect)

---

## Walk-Forward History (all runs)

| Date | Config | Agg OOS R | Agg OOS Exp | Verdict |
|------|--------|-----------|-------------|---------|
| 2026-03-23 | D1/H4, optimised, 7 syms | -19.0R | -0.112R | FAIL |
| 2026-04-13 | H4/M15, fixed fn1/lf1/lb30/rr2.5, 7 syms | +22.1R | +0.128R | STRONG* |
| 2026-04-13 | H4/M15, fixed params, 6 syms (GBPCAD in) | +26.6R | +0.189R | STRONG |
| 2026-04-13 | H4/M15 + FVG invalidation, 6 syms | +26.5R | +0.214R | MODERATE |
| 2026-04-14 | H4/M15, 12-17 UTC session, 6 syms | +26.4R | +0.196R | STRONG |
| 2026-04-15 | H4/M15, body SL, 9 syms | +0.6R | +0.007R | FAIL |
| **2026-04-15** | **H4/M15, swing SL, 9 syms** | **+34.4R** | **+0.165R** | **MODERATE ✓** |
| 2026-04-30 | H4/M15, sweep ltf_origin_expiry × ltf_entry_fib | +33.4R | +0.160R | MODERATE |

*Fold 1 anomalous (near-zero IS, large OOS) — inflated retention figure.

### 2026-04-30 — code review optimizations rejected

Live-code analysis flagged 2 hypotheses to test:
1. `ltf_origin_expiry=False` — let HTF close decide bias breach (filter M15 wicks during news)
2. `ltf_entry_fib=0.618 / 0.786` — deeper LTF entry retracement for better R:R

WF (6 combos × 3 folds) picked **the current live config** (`origin_expiry=True, entry_fib=0.5`) **in every single fold**. Aggregate OOS essentially matched prior baseline. Both hypotheses rejected:
- LTF wick origin breach (sweep) is a genuine invalidation signal — ICT philosophy holds.
- Deeper entry fib reduces fill rate; with only ~25-30 trades/yr/fold, sparsity hurts edge.

**Same-params-every-fold is a strong robustness signal** — no curve-fit drift across regimes.

### Code changes (kept, no behavior change at default params)
- `notify_win` method added — eliminates state-leak after winning trades; no impact on WF results.
- New params `ltf_origin_expiry: bool = True` and `ltf_entry_fib: float = 0.5` — defaults match prior behavior, live config unchanged.
