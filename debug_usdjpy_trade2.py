"""Debug and plot the USDJPY BUY trade from ~2026-03-11."""

import logging
from datetime import datetime, timedelta

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
bars = filter_bars(all_bars, start=datetime(2025, 6, 1))

sym = 'USDJPY'

# Collect H1/D1 bars and EMA values for plotting
h1_bars = []
h1_ema_data = []
d1_ema_data = []
trade_info = None

for bar in bars:
    signal = strat.generate_signal(bar)

    if bar.timeframe == 'H1' and bar.timestamp >= datetime(2026, 2, 20):
        h1_bars.append(bar)
        h1_ema_data.append({
            'time': bar.timestamp,
            'ema10': strat._h1_ema_fast.get(sym),
            'ema20': strat._h1_ema_slow.get(sym),
        })

    if bar.timeframe == 'D1' and bar.timestamp >= datetime(2026, 2, 15):
        d1_ema_data.append({
            'time': bar.timestamp,
            'close': bar.close,
            'ema10': strat._d1_ema_fast.get(sym),
            'ema20': strat._d1_ema_slow.get(sym),
        })

    # Capture the signal placed around March 11
    if (signal and signal.direction == 'BUY' and signal.symbol == sym
            and datetime(2026, 3, 11) <= bar.timestamp <= datetime(2026, 3, 12)):
        # Snapshot swing state at signal time
        trade_info = {
            'signal': signal,
            'signal_bar': bar,
            'swing_high': strat._swing_high[sym],
            'swing_low': strat._swing_low[sym],
            'swing_high_bar_idx': strat._swing_high_bar[sym],
            'swing_low_bar_idx': strat._swing_low_bar[sym],
            'h1_counter': strat._h1_counter[sym],
            'd1_ema10': strat._d1_ema_fast[sym],
            'd1_ema20': strat._d1_ema_slow[sym],
            'h1_ema10': strat._h1_ema_fast[sym],
            'h1_ema20': strat._h1_ema_slow[sym],
        }
        print(f"SIGNAL CAPTURED at {bar.timestamp}")
        print(f"  Direction: {signal.direction}")
        print(f"  Entry: {signal.entry_price:.3f}")
        print(f"  SL:    {signal.stop_loss:.3f}")
        print(f"  TP:    {signal.take_profit:.3f}")
        print(f"  Swing High: {trade_info['swing_high']:.3f}")
        print(f"  Swing Low:  {trade_info['swing_low']:.3f}")
        swing_range = trade_info['swing_high'] - trade_info['swing_low']
        print(f"  Swing range: {swing_range:.3f} ({swing_range / 0.01:.1f} pips)")
        print(f"  D1 EMA10={trade_info['d1_ema10']:.3f}  EMA20={trade_info['d1_ema20']:.3f}  bias=BUY")
        print(f"  H1 EMA10={trade_info['h1_ema10']:.3f}  EMA20={trade_info['h1_ema20']:.3f}  bias=BUY")

        # Find swing bar timestamps
        sh_offset = trade_info['h1_counter'] - trade_info['swing_high_bar_idx']
        sl_offset = trade_info['h1_counter'] - trade_info['swing_low_bar_idx']
        print(f"  Swing high was {sh_offset} H1 bars ago")
        print(f"  Swing low was {sl_offset} H1 bars ago")

if trade_info is None:
    print("Trade not found!")
    exit()

sig = trade_info['signal']
sig_time = trade_info['signal_bar'].timestamp
sh_val = trade_info['swing_high']
sl_val = trade_info['swing_low']

# Find swing bar timestamps by searching backwards from signal
swing_high_time = None
swing_low_time = None
for b in reversed(h1_bars):
    if b.timestamp > sig_time:
        continue
    if b.high == sh_val and swing_high_time is None:
        swing_high_time = b.timestamp
    if b.low == sl_val and swing_low_time is None:
        swing_low_time = b.timestamp
    if swing_high_time and swing_low_time:
        break

print(f"\n  Swing high {sh_val:.3f} at {swing_high_time}")
print(f"  Swing low  {sl_val:.3f} at {swing_low_time}")

# Find when the pending was filled
fill_time = None
fill_price = None
for b in h1_bars:
    if b.timestamp <= sig_time:
        continue
    if b.low <= sig.entry_price <= b.high:
        fill_time = b.timestamp
        fill_price = sig.entry_price
        print(f"  Filled at {fill_time}")
        break

# Find SL/TP hit
result_time = None
result_type = None
for b in h1_bars:
    if fill_time is None or b.timestamp <= fill_time:
        continue
    if b.low <= sig.stop_loss:
        result_time = b.timestamp
        result_type = 'SL HIT'
        break
    if b.high >= sig.take_profit:
        result_time = b.timestamp
        result_type = 'TP HIT'
        break

if result_time:
    print(f"  {result_type} at {result_time}")

# ── PLOT ──────────────────────────────────────────────────────────────────────
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

earliest_swing = min(t for t in [swing_high_time, swing_low_time] if t is not None)
plot_start = earliest_swing - timedelta(days=2)
plot_end = (result_time or sig_time) + timedelta(days=2)

plot_bars = [b for b in h1_bars if plot_start <= b.timestamp <= plot_end]
plot_ema = [e for e in h1_ema_data if plot_start <= e['time'] <= plot_end]

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(18, 11), height_ratios=[3, 1])

# H1 candles
for b in plot_bars:
    color = '#16a34a' if b.close >= b.open else '#dc2626'
    ax1.plot([b.timestamp, b.timestamp], [b.low, b.high], color=color, linewidth=0.7)
    body_lo = min(b.open, b.close)
    body_hi = max(b.open, b.close)
    body_h = max(body_hi - body_lo, 0.01)
    ax1.bar(b.timestamp, body_h, bottom=body_lo, width=timedelta(hours=0.6),
            color=color, edgecolor=color, linewidth=0.5)

# H1 EMAs
ema_t = [e['time'] for e in plot_ema if e['ema10'] is not None]
e10 = [e['ema10'] for e in plot_ema if e['ema10'] is not None]
e20 = [e['ema20'] for e in plot_ema if e['ema20'] is not None]
ax1.plot(ema_t, e10, 'b-', linewidth=1.5, label='H1 EMA 10', alpha=0.8)
ax1.plot(ema_t, e20, 'r-', linewidth=1.5, label='H1 EMA 20', alpha=0.8)

# Swing markers
if swing_high_time:
    ax1.plot(swing_high_time, sh_val, 'v', color='purple', markersize=14, zorder=5,
             label=f'Fractal High {sh_val:.3f}')
if swing_low_time:
    ax1.plot(swing_low_time, sl_val, '^', color='orange', markersize=14, zorder=5,
             label=f'Fractal Low {sl_val:.3f}')

# Swing range shading
ax1.axhspan(sl_val, sh_val, alpha=0.05, color='blue')

# Fib levels
swing_range = sh_val - sl_val
fib_levels = {
    '0%': sh_val,
    '38.2%': sh_val - 0.382 * swing_range,
    '50%': sh_val - 0.5 * swing_range,
    '61.8% (Entry)': sh_val - 0.618 * swing_range,
    '100%': sl_val,
}

for label, level in fib_levels.items():
    if 'Entry' in label:
        ax1.axhline(level, color='#2563eb', linewidth=2, linestyle='-', alpha=0.8)
    else:
        ax1.axhline(level, color='grey', linewidth=0.8, linestyle=':', alpha=0.5)
    ax1.annotate(f' {label} — {level:.3f}', xy=(plot_start, level),
                 fontsize=8, color='#2563eb' if 'Entry' in label else 'grey',
                 fontweight='bold' if 'Entry' in label else 'normal',
                 va='bottom')

# SL and TP
ax1.axhline(sig.stop_loss, color='#dc2626', linewidth=2, linestyle='-', alpha=0.8)
ax1.annotate(f' SL {sig.stop_loss:.3f}', xy=(plot_end - timedelta(hours=6), sig.stop_loss),
             fontsize=10, color='#dc2626', fontweight='bold', va='top')

ax1.axhline(sig.take_profit, color='#16a34a', linewidth=2, linestyle='-', alpha=0.8)
ax1.annotate(f' TP {sig.take_profit:.3f}', xy=(plot_end - timedelta(hours=6), sig.take_profit),
             fontsize=10, color='#16a34a', fontweight='bold', va='bottom')

# Signal and fill markers
ax1.axvline(sig_time, color='blue', linewidth=1, linestyle=':', alpha=0.3)
ax1.annotate(f'Signal placed\n{sig_time.strftime("%m-%d %H:%M")}',
             xy=(sig_time, sh_val), fontsize=8, ha='center', va='bottom',
             color='blue')

if fill_time:
    ax1.plot(fill_time, fill_price, 'D', color='#2563eb', markersize=10, zorder=5,
             label=f'Fill @ {fill_price:.3f}')

if result_time:
    result_color = '#16a34a' if result_type == 'TP HIT' else '#dc2626'
    result_price = sig.take_profit if result_type == 'TP HIT' else sig.stop_loss
    ax1.plot(result_time, result_price, 'X', color=result_color, markersize=12, zorder=5,
             label=result_type)

ax1.set_title(f'USDJPY H1 — EmaFib BUY (signal {sig_time.strftime("%Y-%m-%d %H:%M")})',
              fontsize=14, fontweight='bold')
ax1.legend(loc='lower left', fontsize=9, ncol=2)
ax1.grid(True, alpha=0.2)
ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
ax1.tick_params(axis='x', rotation=45)

# D1 EMA panel
d1_t = [e['time'] for e in d1_ema_data if e['ema10'] is not None]
d1_c = [e['close'] for e in d1_ema_data if e['ema10'] is not None]
d1_e10 = [e['ema10'] for e in d1_ema_data if e['ema10'] is not None]
d1_e20 = [e['ema20'] for e in d1_ema_data if e['ema10'] is not None]

ax2.plot(d1_t, d1_c, 'k-', linewidth=1, label='D1 Close', alpha=0.5)
ax2.plot(d1_t, d1_e10, 'b-', linewidth=2, label='D1 EMA 10')
ax2.plot(d1_t, d1_e20, 'r-', linewidth=2, label='D1 EMA 20')
ax2.axvline(sig_time, color='blue', linewidth=1, linestyle=':', alpha=0.3)
ax2.set_title('D1 Bias — EMA 10 > EMA 20 = BUY', fontsize=11, fontweight='bold')
ax2.legend(loc='upper left', fontsize=9)
ax2.grid(True, alpha=0.2)
ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))

fig.tight_layout()
fig.savefig('output/usdjpy_trade_20260311.png', dpi=150)
plt.close(fig)
print(f"\nChart saved to output/usdjpy_trade_20260311.png")
