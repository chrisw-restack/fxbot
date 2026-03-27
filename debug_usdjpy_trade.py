"""Debug and plot the USDJPY BUY trade filled on 2026-03-11."""

import logging
from datetime import datetime, timedelta
from collections import deque

from strategies.ema_fib_retracement import EmaFibRetracementStrategy
from data.historical_loader import find_csv, load_and_merge, filter_bars

logging.basicConfig(level=logging.ERROR)

strat = EmaFibRetracementStrategy(
    cooldown_bars=10, invalidate_swing_on_loss=True,
    min_swing_pips=15, ema_sep_pct=0.001,
)

csv_paths = []
for tf in ['D1', 'H1']:
    csv_paths.extend(find_csv('USDJPY', tf))

all_bars = load_and_merge(csv_paths)
# Use enough history for EMA warmup
bars = filter_bars(all_bars, start=datetime(2025, 6, 1))

sym = 'USDJPY'
trade_signal = None
signal_bar = None

# Track bars for plotting
h1_bars = []
d1_bars = []

for bar in bars:
    signal = strat.generate_signal(bar)

    if bar.timeframe == 'H1' and bar.timestamp >= datetime(2026, 2, 1):
        h1_bars.append(bar)

    if bar.timeframe == 'D1' and bar.timestamp >= datetime(2026, 2, 1):
        d1_bars.append(bar)

    if signal and signal.direction in ('BUY', 'SELL') and bar.timestamp >= datetime(2026, 3, 1):
        d1_bias = strat._get_bias(strat._d1_ema_fast.get(sym), strat._d1_ema_slow.get(sym))
        h1_bias = strat._get_bias(strat._h1_ema_fast.get(sym), strat._h1_ema_slow.get(sym))

        print(f"\nSIGNAL: {signal.direction} {sym} @ {bar.timestamp}")
        print(f"  Entry: {signal.entry_price:.3f}")
        print(f"  SL:    {signal.stop_loss:.3f}")
        print(f"  TP:    {signal.take_profit:.3f}")
        print(f"  D1 bias: {d1_bias}  (EMA10={strat._d1_ema_fast[sym]:.3f}, EMA20={strat._d1_ema_slow[sym]:.3f})")
        print(f"  H1 bias: {h1_bias}  (EMA10={strat._h1_ema_fast[sym]:.3f}, EMA20={strat._h1_ema_slow[sym]:.3f})")
        print(f"  Swing High: {strat._swing_high[sym]:.3f}  (bar #{strat._swing_high_bar[sym]})")
        print(f"  Swing Low:  {strat._swing_low[sym]:.3f}  (bar #{strat._swing_low_bar[sym]})")
        swing_range = strat._swing_high[sym] - strat._swing_low[sym]
        print(f"  Swing range: {swing_range:.3f} ({swing_range / 0.01:.1f} pips)")

        # Find which bar was the swing high/low
        # Check if this is the trade we want (filled around March 11)
        if bar.timestamp >= datetime(2026, 3, 10) and bar.timestamp <= datetime(2026, 3, 12):
            trade_signal = signal
            signal_bar = bar

            # Find the fractal bars
            print(f"\n  Looking for fractal bars...")
            counter = strat._h1_counter[sym]
            sh_bar_idx = strat._swing_high_bar[sym]
            sl_bar_idx = strat._swing_low_bar[sym]
            # Count back from current
            sh_offset = counter - sh_bar_idx
            sl_offset = counter - sl_bar_idx
            print(f"  Swing high is {sh_offset} H1 bars ago")
            print(f"  Swing low is {sl_offset} H1 bars ago")

# Now plot
if trade_signal is None:
    print("Trade not found!")
    exit()

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

sig = trade_signal

# Find the fractal bar timestamps by searching h1_bars
swing_high_val = strat._swing_high[sym]
swing_low_val = strat._swing_low[sym]

# Search for the bars matching the swing values
swing_high_time = None
swing_low_time = None
for b in h1_bars:
    if b.high == swing_high_val and swing_high_time is None:
        swing_high_time = b.timestamp
    if b.low == swing_low_val and swing_low_time is None:
        swing_low_time = b.timestamp

# Also look backwards more carefully - find the LAST occurrence before the signal
swing_high_time = None
swing_low_time = None
for b in reversed(h1_bars):
    if b.timestamp > signal_bar.timestamp:
        continue
    if b.high == swing_high_val and swing_high_time is None:
        swing_high_time = b.timestamp
    if b.low == swing_low_val and swing_low_time is None:
        swing_low_time = b.timestamp

print(f"\n  Swing high {swing_high_val:.3f} at {swing_high_time}")
print(f"  Swing low  {swing_low_val:.3f} at {swing_low_time}")

# Focus window: a few days before the swing to a few days after signal
plot_start = min(swing_high_time or datetime(2026, 3, 1),
                 swing_low_time or datetime(2026, 3, 1)) - timedelta(days=3)
plot_end = signal_bar.timestamp + timedelta(days=5)

plot_bars = [b for b in h1_bars if plot_start <= b.timestamp <= plot_end]

# Calculate EMAs for the plot window using the strategy's approach
# Re-run to collect EMA values per bar
strat2 = EmaFibRetracementStrategy(
    cooldown_bars=10, invalidate_swing_on_loss=True,
    min_swing_pips=15, ema_sep_pct=0.001,
)
h1_ema_data = []
d1_ema_data = []

for bar in bars:
    strat2.generate_signal(bar)
    if bar.timeframe == 'H1' and plot_start <= bar.timestamp <= plot_end:
        h1_ema_data.append({
            'time': bar.timestamp,
            'close': bar.close,
            'ema10': strat2._h1_ema_fast.get(sym),
            'ema20': strat2._h1_ema_slow.get(sym),
        })
    if bar.timeframe == 'D1' and plot_start - timedelta(days=5) <= bar.timestamp <= plot_end:
        d1_ema_data.append({
            'time': bar.timestamp,
            'close': bar.close,
            'ema10': strat2._d1_ema_fast.get(sym),
            'ema20': strat2._d1_ema_slow.get(sym),
        })

# ── Create chart ──────────────────────────────────────────────────────────────
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10), height_ratios=[3, 1],
                                gridspec_kw={'hspace': 0.3})

# H1 candlestick-style plot (simplified: use line + fill)
times = [b.timestamp for b in plot_bars]
highs = [b.high for b in plot_bars]
lows = [b.low for b in plot_bars]
opens = [b.open for b in plot_bars]
closes = [b.close for b in plot_bars]

# Draw candle bodies
for i, b in enumerate(plot_bars):
    color = '#16a34a' if b.close >= b.open else '#dc2626'
    # Wick
    ax1.plot([b.timestamp, b.timestamp], [b.low, b.high], color=color, linewidth=0.8)
    # Body
    body_lo = min(b.open, b.close)
    body_hi = max(b.open, b.close)
    body_height = max(body_hi - body_lo, 0.005)  # minimum visible height
    ax1.bar(b.timestamp, body_height, bottom=body_lo, width=timedelta(hours=0.6),
            color=color, edgecolor=color, linewidth=0.5)

# H1 EMAs
ema_times = [e['time'] for e in h1_ema_data if e['ema10'] is not None]
ema10 = [e['ema10'] for e in h1_ema_data if e['ema10'] is not None]
ema20 = [e['ema20'] for e in h1_ema_data if e['ema20'] is not None]
ax1.plot(ema_times, ema10, 'b-', linewidth=1.5, label='H1 EMA 10', alpha=0.8)
ax1.plot(ema_times, ema20, 'r-', linewidth=1.5, label='H1 EMA 20', alpha=0.8)

# Mark swing high and low
ax1.axhline(swing_high_val, color='purple', linewidth=1, linestyle='--', alpha=0.5)
ax1.axhline(swing_low_val, color='orange', linewidth=1, linestyle='--', alpha=0.5)

if swing_high_time:
    ax1.plot(swing_high_time, swing_high_val, 'v', color='purple', markersize=12,
             label=f'Swing High {swing_high_val:.3f}', zorder=5)
if swing_low_time:
    ax1.plot(swing_low_time, swing_low_val, '^', color='orange', markersize=12,
             label=f'Swing Low {swing_low_val:.3f}', zorder=5)

# Entry, SL, TP lines
ax1.axhline(sig.entry_price, color='blue', linewidth=1.5, linestyle='-', alpha=0.7)
ax1.axhline(sig.stop_loss, color='red', linewidth=1.5, linestyle='-', alpha=0.7)
ax1.axhline(sig.take_profit, color='green', linewidth=1.5, linestyle='-', alpha=0.7)

# Annotate levels on right side
y_offset = (max(highs) - min(lows)) * 0.01
ax1.annotate(f'Entry {sig.entry_price:.3f}', xy=(plot_end, sig.entry_price),
             fontsize=9, color='blue', fontweight='bold', va='bottom')
ax1.annotate(f'SL {sig.stop_loss:.3f}', xy=(plot_end, sig.stop_loss),
             fontsize=9, color='red', fontweight='bold', va='bottom')
ax1.annotate(f'TP {sig.take_profit:.3f}', xy=(plot_end, sig.take_profit),
             fontsize=9, color='green', fontweight='bold', va='bottom')

# Fib levels
swing_range = swing_high_val - swing_low_val
fib_382 = swing_high_val - 0.382 * swing_range
fib_500 = swing_high_val - 0.500 * swing_range
ax1.axhline(fib_382, color='grey', linewidth=0.8, linestyle=':', alpha=0.5)
ax1.axhline(fib_500, color='grey', linewidth=0.8, linestyle=':', alpha=0.5)
ax1.annotate(f'38.2% {fib_382:.3f}', xy=(plot_start, fib_382),
             fontsize=8, color='grey', va='bottom')
ax1.annotate(f'50.0% {fib_500:.3f}', xy=(plot_start, fib_500),
             fontsize=8, color='grey', va='bottom')
ax1.annotate(f'61.8% {sig.entry_price:.3f}', xy=(plot_start, sig.entry_price),
             fontsize=8, color='blue', va='bottom')

# Mark fill bar
ax1.axvline(signal_bar.timestamp, color='blue', linewidth=1, linestyle=':', alpha=0.4)

ax1.set_title(f'USDJPY H1 — EmaFibRetracement BUY Trade (filled {signal_bar.timestamp.strftime("%Y-%m-%d %H:%M")})',
              fontsize=13, fontweight='bold')
ax1.legend(loc='upper left', fontsize=9)
ax1.grid(True, alpha=0.2)
ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
fig.autofmt_xdate(rotation=45)

# D1 panel - EMAs
d1_times = [e['time'] for e in d1_ema_data if e['ema10'] is not None]
d1_e10 = [e['ema10'] for e in d1_ema_data if e['ema10'] is not None]
d1_e20 = [e['ema20'] for e in d1_ema_data if e['ema20'] is not None]
d1_close = [e['close'] for e in d1_ema_data if e['ema10'] is not None]

ax2.plot(d1_times, d1_close, 'k-', linewidth=1, label='D1 Close', alpha=0.5)
ax2.plot(d1_times, d1_e10, 'b-', linewidth=2, label='D1 EMA 10')
ax2.plot(d1_times, d1_e20, 'r-', linewidth=2, label='D1 EMA 20')
ax2.set_title('D1 EMA Bias', fontsize=11, fontweight='bold')
ax2.legend(loc='upper left', fontsize=9)
ax2.grid(True, alpha=0.2)
ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))

fig.tight_layout()
fig.savefig('output/usdjpy_trade_20260311.png', dpi=150)
plt.close(fig)
print(f"\nChart saved to output/usdjpy_trade_20260311.png")
