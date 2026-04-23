"""
Tiered drawdown-based position sizing model for IMS Reversal.

Simulates the full IS backtest (2016-2026, 8 symbols) with two approaches:
  baseline  — fixed 0.5% risk per trade throughout
  tiered    — dynamic risk based on rolling notional DD from equity peak

Tier thresholds (notional = what the full-size R curve shows):
  Full    (1.0x, 0.5% risk):    DD from peak <  20R
  Half    (0.5x, 0.25% risk):   DD from peak >= 20R
  Quarter (0.25x, 0.125% risk): DD from peak >= 35R

Step-up: when notional equity recovers 10R from its lowest point in the
current reduced tier. Quarter -> Half, then Half -> Full (two separate
recoveries of 10R each).

Also runs a sensitivity sweep over different DD_HALF and DD_QUARTER thresholds.
"""

import io
import contextlib
import logging
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import numpy as np

import config
from backtest_engine import BacktestEngine
from strategies.ims_reversal import ImsReversalStrategy
from data.historical_loader import find_csv, load_and_merge

logging.basicConfig(level=logging.ERROR)

SYMBOLS = ['GBPNZD', 'AUDUSD', 'USA30', 'USDCHF', 'XAUUSD', 'AUDJPY', 'AUDCAD', 'USDCAD']
INITIAL_BALANCE = 10_000.0
RISK_PCT_FULL   = 0.005      # 0.5% at full size

# Default thresholds
DD_HALF     = 20.0   # notional R DD to step down to half
DD_QUARTER  = 35.0   # notional R DD to step down to quarter
RECOVERY_R  = 10.0   # notional R recovery from trough to step up one tier

FIXED = dict(
    tf_htf='H4', tf_ltf='M15',
    fractal_n=1, ltf_fractal_n=2, htf_lookback=30,
    entry_mode='pending', tp_mode='htf_pct', htf_tp_pct=0.5,
    rr_ratio=2.5, zone_pct=0.5, cooldown_bars=0,
    blocked_hours=(*range(0, 12), *range(17, 24)),
    ema_fast=20, ema_slow=50, ema_sep=0.001,
    sl_anchor='swing', sl_buffer_pips=0.0,
    max_losses_per_bias=1,
    pip_sizes={sym: config.PIP_SIZE[sym] for sym in SYMBOLS if sym in config.PIP_SIZE},
)

# ── Collect all IS trades ─────────────────────────────────────────────────────

print("Loading bar data and collecting trades...")
all_trades: list[dict] = []
for symbol in SYMBOLS:
    htf = find_csv(symbol, 'H4')
    ltf = find_csv(symbol, 'M15')
    if not htf or not ltf:
        print(f"  {symbol}: SKIPPED (no data)")
        continue
    bars = load_and_merge(htf + ltf)
    strategy = ImsReversalStrategy(**FIXED)
    engine   = BacktestEngine(initial_balance=INITIAL_BALANCE, rr_ratio=FIXED['rr_ratio'])
    engine.add_strategy(strategy, symbols=[symbol])
    with contextlib.redirect_stdout(io.StringIO()):
        for bar in bars:
            closed = engine.execution.check_fills(bar)
            for trade in closed:
                engine.portfolio.record_close(
                    trade['symbol'], trade['pnl'], trade.get('strategy_name', ''))
                engine.trade_logger.log_close(trade['ticket'], trade)
                engine.event_engine.notify_trade_closed(trade)
            engine.event_engine.process_bar(bar)
    trades = engine.execution.get_closed_trades()
    all_trades.extend(trades)
    print(f"  {symbol}: {len(trades)} trades")

all_trades.sort(key=lambda t: t['close_time'])
print(f"\nTotal trades loaded: {len(all_trades)}")


# ── Simulation ────────────────────────────────────────────────────────────────

def simulate(trades: list[dict],
             use_tiered: bool,
             dd_half: float = DD_HALF,
             dd_quarter: float = DD_QUARTER,
             recovery_r: float = RECOVERY_R) -> dict:
    """
    Simulate dollar-account performance with optional tiered sizing.

    Tier transitions are driven by the *notional* (full-size) equity curve so
    that the tier state is independent of the actual bet size — no feedback loop.
    """
    balance      = INITIAL_BALANCE
    peak_bal     = INITIAL_BALANCE
    notional_eq  = 0.0
    notional_peak = 0.0
    tier_mult    = 1.0
    trough_eq    = 0.0   # lowest notional_eq while in reduced tier

    max_dd_pct   = 0.0
    wins = losses = streak = max_streak = 0

    balance_curve : list[float] = [INITIAL_BALANCE]
    dd_curve      : list[float] = [0.0]
    tier_curve    : list[float] = [1.0]
    times                       = [trades[0]['close_time']]

    tier_counts = {1.0: 0, 0.5: 0, 0.25: 0}

    for trade in trades:
        r = trade['r_multiple']

        # --- notional (full-size) equity bookkeeping ---
        notional_eq   += r
        notional_peak  = max(notional_peak, notional_eq)
        notional_dd    = notional_peak - notional_eq

        # track worst trough while in a reduced tier
        if tier_mult < 1.0:
            trough_eq = min(trough_eq, notional_eq)

        # --- dollar account update ---
        mult      = tier_mult if use_tiered else 1.0
        risk_amt  = balance * RISK_PCT_FULL * mult
        balance  += risk_amt * r
        peak_bal  = max(peak_bal, balance)
        dd_pct    = (peak_bal - balance) / peak_bal * 100
        max_dd_pct = max(max_dd_pct, dd_pct)

        # --- win/loss stats ---
        if r > 0:
            wins  += 1
            streak = 0
        else:
            losses += 1
            streak += 1
            max_streak = max(max_streak, streak)

        tier_counts[tier_mult if use_tiered else 1.0] += 1

        # --- tier transitions (evaluated after current trade, affects NEXT trade) ---
        if use_tiered:
            if tier_mult == 1.0:
                if notional_dd >= dd_half:
                    tier_mult = 0.5
                    trough_eq = notional_eq
            elif tier_mult == 0.5:
                if notional_dd >= dd_quarter:
                    tier_mult = 0.25
                    # keep tracking trough (don't reset — continue measuring minimum)
                elif notional_eq >= trough_eq + recovery_r:
                    tier_mult = 1.0
            elif tier_mult == 0.25:
                if notional_eq >= trough_eq + recovery_r:
                    tier_mult = 0.5
                    trough_eq = notional_eq   # reset: track half-tier trough separately

        balance_curve.append(balance)
        dd_curve.append(dd_pct)
        tier_curve.append(tier_mult if use_tiered else 1.0)
        times.append(trade['close_time'])

    n = wins + losses
    return dict(
        balance       = balance,
        total_return  = (balance - INITIAL_BALANCE) / INITIAL_BALANCE * 100,
        max_dd_pct    = max_dd_pct,
        win_rate      = wins / n * 100,
        total_r       = sum(t['r_multiple'] for t in trades),
        max_streak    = max_streak,
        n             = n,
        tier_counts   = tier_counts,
        balance_curve = balance_curve,
        dd_curve      = dd_curve,
        tier_curve    = tier_curve,
        times         = times,
    )


# ── Run baseline + tiered ─────────────────────────────────────────────────────

print("\nSimulating...")
base   = simulate(all_trades, use_tiered=False)
tiered = simulate(all_trades, use_tiered=True)

# ── Summary table ─────────────────────────────────────────────────────────────

W = 68
print(f"\n{'='*W}")
print("TIERED SIZING MODEL — IMS Reversal  (H4/M15, 8 symbols, 2016–2026)")
print(f"  DD_HALF={DD_HALF}R  DD_QUARTER={DD_QUARTER}R  RECOVERY={RECOVERY_R}R")
print(f"{'='*W}")
print(f"  {'Metric':<30} {'Baseline':>12} {'Tiered':>12} {'Change':>10}")
print('-' * W)

rows = [
    ('Total trades',              f"{base['n']}",
                                  f"{tiered['n']}",     ''),
    ('Final balance ($10k start)',f"${base['balance']:,.0f}",
                                  f"${tiered['balance']:,.0f}",
                                  f"{tiered['balance']-base['balance']:+,.0f}"),
    ('Total return %',            f"{base['total_return']:+.1f}%",
                                  f"{tiered['total_return']:+.1f}%",
                                  f"{tiered['total_return']-base['total_return']:+.1f}pp"),
    ('Max drawdown %',            f"{base['max_dd_pct']:.1f}%",
                                  f"{tiered['max_dd_pct']:.1f}%",
                                  f"{tiered['max_dd_pct']-base['max_dd_pct']:+.1f}pp"),
    ('Max loss streak',           f"{base['max_streak']}",
                                  f"{tiered['max_streak']}",
                                  f"{tiered['max_streak']-base['max_streak']:+d}"),
    ('Win rate',                  f"{base['win_rate']:.1f}%",
                                  f"{tiered['win_rate']:.1f}%",   ''),
    ('Total R (unscaled)',        f"{base['total_r']:+.1f}R",
                                  f"{base['total_r']:+.1f}R",   '(same)'),
]
for label, bv, tv, ch in rows:
    print(f"  {label:<30} {bv:>12} {tv:>12} {ch:>10}")

n_trades = tiered['n']
print(f"\n  Trades by tier (% of all trades):")
for mult in [1.0, 0.5, 0.25]:
    count = tiered['tier_counts'][mult]
    name  = {1.0: 'Full  (1.0x, 0.50% risk)',
             0.5: 'Half  (0.5x, 0.25% risk)',
             0.25:'Quarter (0.25x, 0.13% risk)'}[mult]
    pct = count / n_trades * 100 if n_trades else 0
    print(f"    {name:<32} {count:>5} trades  ({pct:.1f}%)")

# ── Sensitivity sweep ─────────────────────────────────────────────────────────

SENS_CONFIGS = [
    (15, 30, 10),
    (20, 35, 10),   # default
    (25, 40, 10),
    (20, 35,  5),
    (20, 35, 15),
]

print(f"\n{'='*W}")
print("THRESHOLD SENSITIVITY  (dd_half / dd_quarter / recovery_R)")
print(f"{'='*W}")
print(f"  {'config':<22} {'final_$':>9} {'return%':>8} {'maxDD%':>8} {'streak':>7}")
print('-' * W)

for dh, dq, rec in SENS_CONFIGS:
    s = simulate(all_trades, use_tiered=True, dd_half=dh, dd_quarter=dq, recovery_r=rec)
    marker = ' ← default' if (dh, dq, rec) == (DD_HALF, DD_QUARTER, RECOVERY_R) else ''
    label  = f"≥{dh}R / ≥{dq}R / +{rec}R"
    print(f"  {label:<22} ${s['balance']:>8,.0f}  {s['total_return']:>+7.1f}%  "
          f"{s['max_dd_pct']:>7.1f}%  {s['max_streak']:>6}{marker}")

print(f"  {'baseline (no tiers)':<22} ${base['balance']:>8,.0f}  "
      f"{base['total_return']:>+7.1f}%  {base['max_dd_pct']:>7.1f}%  {base['max_streak']:>6}")

# ── Chart ─────────────────────────────────────────────────────────────────────

print("\nGenerating chart...")

times = tiered['times']

fig, axes = plt.subplots(3, 1, figsize=(14, 10),
                          gridspec_kw={'height_ratios': [3, 2, 1]},
                          sharex=True)
fig.patch.set_facecolor('#0f0f0f')
for ax in axes:
    ax.set_facecolor('#1a1a1a')
    ax.tick_params(colors='#cccccc')
    ax.yaxis.label.set_color('#cccccc')
    for spine in ax.spines.values():
        spine.set_edgecolor('#333333')

# ── Panel 1: Account balance ──────────────────────────────────────────────────
ax1 = axes[0]

ax1.plot(times, base['balance_curve'],   color='#555555', linewidth=1.2,
         label='Baseline (fixed 0.5%)', alpha=0.8, zorder=2)
ax1.plot(times, tiered['balance_curve'], color='#4fc3f7', linewidth=1.5,
         label='Tiered sizing', zorder=3)

ax1.axhline(INITIAL_BALANCE, color='#444444', linewidth=0.8, linestyle='--')
ax1.set_ylabel('Account Balance ($)', color='#cccccc', fontsize=10)
ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x:,.0f}'))
ax1.legend(loc='upper left', facecolor='#1a1a1a', edgecolor='#333333',
           labelcolor='#cccccc', fontsize=9)
ax1.set_title('Tiered Position Sizing — IMS Reversal  (H4/M15, 8 symbols, 2016–2026)',
              color='#eeeeee', fontsize=12, pad=10)

# annotate final balances
ax1.annotate(f"${base['balance']:,.0f}", xy=(times[-1], base['balance_curve'][-1]),
             xytext=(8, 0), textcoords='offset points',
             color='#888888', fontsize=8, va='center')
ax1.annotate(f"${tiered['balance']:,.0f}", xy=(times[-1], tiered['balance_curve'][-1]),
             xytext=(8, 0), textcoords='offset points',
             color='#4fc3f7', fontsize=8, va='center')

# ── Panel 2: Drawdown % ───────────────────────────────────────────────────────
ax2 = axes[1]

ax2.fill_between(times, base['dd_curve'],   color='#ff6b6b', alpha=0.25, zorder=1)
ax2.fill_between(times, tiered['dd_curve'], color='#4fc3f7', alpha=0.30, zorder=2)
ax2.plot(times, base['dd_curve'],   color='#ff6b6b', linewidth=1.0, alpha=0.7,
         label=f"Baseline  max {base['max_dd_pct']:.1f}%")
ax2.plot(times, tiered['dd_curve'], color='#4fc3f7', linewidth=1.2,
         label=f"Tiered    max {tiered['max_dd_pct']:.1f}%")

ax2.invert_yaxis()
ax2.set_ylabel('Drawdown %', color='#cccccc', fontsize=10)
ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x:.0f}%'))
ax2.legend(loc='lower left', facecolor='#1a1a1a', edgecolor='#333333',
           labelcolor='#cccccc', fontsize=9)

# ── Panel 3: Tier level ───────────────────────────────────────────────────────
ax3 = axes[2]

tier_vals = tiered['tier_curve']
color_map  = {1.0: '#4caf50', 0.5: '#ff9800', 0.25: '#f44336'}
prev_t     = times[0]
prev_v     = tier_vals[0]

for i in range(1, len(times)):
    color = color_map[prev_v]
    ax3.axvspan(prev_t, times[i], alpha=0.6, color=color, linewidth=0)
    prev_t = times[i]
    prev_v = tier_vals[i]

ax3.set_ylim(0, 1.2)
ax3.set_yticks([])
ax3.set_ylabel('Tier', color='#cccccc', fontsize=10)

patches = [
    mpatches.Patch(color='#4caf50', alpha=0.7, label='Full (1.0x)'),
    mpatches.Patch(color='#ff9800', alpha=0.7, label='Half (0.5x)'),
    mpatches.Patch(color='#f44336', alpha=0.7, label='Quarter (0.25x)'),
]
ax3.legend(handles=patches, loc='upper right', ncol=3, facecolor='#1a1a1a',
           edgecolor='#333333', labelcolor='#cccccc', fontsize=8)

ax3.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
ax3.xaxis.set_major_locator(mdates.YearLocator())
plt.setp(ax3.xaxis.get_majorticklabels(), rotation=0, ha='center')

plt.tight_layout(h_pad=0.5)

out_path = Path('output/tiered_sizing_model.png')
out_path.parent.mkdir(exist_ok=True)
plt.savefig(out_path, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
plt.close()
print(f"Chart saved to {out_path}")
