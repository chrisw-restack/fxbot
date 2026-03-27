"""Plot D1 close + EMA10/EMA20: ICMarkets vs Dukascopy (raw) vs Dukascopy (weekends removed)."""

import csv
import os
from datetime import datetime

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


def load_csv(path):
    rows = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            dt = datetime.strptime(row['time'].strip(), '%Y-%m-%d')
            rows.append({
                'time': dt,
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close']),
            })
    return rows


def calc_ema(closes, period):
    emas = []
    k = 2.0 / (period + 1)
    sma_sum = 0.0
    ema = None
    for i, c in enumerate(closes):
        if i < period:
            sma_sum += c
            if i == period - 1:
                ema = sma_sum / period
            emas.append(ema)
        else:
            ema = c * k + ema * (1 - k)
            emas.append(ema)
    return emas


def dedup_sorted(rows):
    seen = set()
    out = []
    for r in sorted(rows, key=lambda x: x['time']):
        key = r['time'].strftime('%Y-%m-%d')
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


base = 'data/historical/'

# Load ICMarkets
ic_data = load_csv(base + 'AUDUSD_D1_20260101-20260320icmarkets.csv')

# Load all Dukascopy D1 files (long + short)
dk_files = sorted(f for f in os.listdir(base)
                  if f.startswith('AUDUSD_D1_') and f.endswith('.csv')
                  and 'icmarkets' not in f)
all_dk = []
for f in dk_files:
    all_dk.extend(load_csv(base + f))
all_dk = dedup_sorted(all_dk)

# Raw Dukascopy (includes weekends)
dk_raw = all_dk
# Filtered Dukascopy (no weekends — matches the loader fix)
dk_filtered = [r for r in all_dk if r['time'].weekday() < 5]

print(f"ICMarkets: {len(ic_data)} bars")
print(f"Dukascopy raw: {len(dk_raw)} bars")
print(f"Dukascopy filtered: {len(dk_filtered)} bars")

# Calculate EMAs
ic_ema10 = calc_ema([r['close'] for r in ic_data], 10)
ic_ema20 = calc_ema([r['close'] for r in ic_data], 20)

dk_raw_ema10 = calc_ema([r['close'] for r in dk_raw], 10)
dk_raw_ema20 = calc_ema([r['close'] for r in dk_raw], 20)

dk_filt_ema10 = calc_ema([r['close'] for r in dk_filtered], 10)
dk_filt_ema20 = calc_ema([r['close'] for r in dk_filtered], 20)

# Print comparison table
print(f"\n{'Date':<12} {'IC EMA10':>10} {'IC bias':>8} | {'DK raw':>10} {'raw bias':>9} | {'DK filt':>10} {'filt bias':>10}")
ic_lookup = {r['time'].strftime('%Y-%m-%d'): i for i, r in enumerate(ic_data)}
dk_raw_lookup = {r['time'].strftime('%Y-%m-%d'): i for i, r in enumerate(dk_raw)}
dk_filt_lookup = {r['time'].strftime('%Y-%m-%d'): i for i, r in enumerate(dk_filtered)}

for d in sorted(set(
    [r['time'].strftime('%Y-%m-%d') for r in ic_data] +
    [r['time'].strftime('%Y-%m-%d') for r in dk_raw]
)):
    if d < '2026-03-10':
        continue

    ic_str = ic_bias = ""
    if d in ic_lookup:
        i = ic_lookup[d]
        if ic_ema10[i] is not None:
            ic_bias = 'BUY' if ic_ema10[i] > ic_ema20[i] else 'SELL'
            ic_str = f"{ic_ema10[i]:.5f}"

    dk_r_str = dk_r_bias = ""
    if d in dk_raw_lookup:
        i = dk_raw_lookup[d]
        if dk_raw_ema10[i] is not None:
            dk_r_bias = 'BUY' if dk_raw_ema10[i] > dk_raw_ema20[i] else 'SELL'
            dk_r_str = f"{dk_raw_ema10[i]:.5f}"

    dk_f_str = dk_f_bias = ""
    if d in dk_filt_lookup:
        i = dk_filt_lookup[d]
        if dk_filt_ema10[i] is not None:
            dk_f_bias = 'BUY' if dk_filt_ema10[i] > dk_filt_ema20[i] else 'SELL'
            dk_f_str = f"{dk_filt_ema10[i]:.5f}"

    print(f"{d:<12} {ic_str:>10} {ic_bias:>8} | {dk_r_str:>10} {dk_r_bias:>9} | {dk_f_str:>10} {dk_f_bias:>10}")

# ── Plot 3 panels ────────────────────────────────────────────────────────────
cut = datetime(2026, 2, 15)

fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 13))

def plot_panel(ax, data, ema10, ema20, title, cut_date):
    dates = [r['time'] for r in data if r['time'] >= cut_date]
    closes = [r['close'] for i, r in enumerate(data) if r['time'] >= cut_date]
    e10 = [ema10[i] for i, r in enumerate(data) if r['time'] >= cut_date and ema10[i] is not None]
    e20 = [ema20[i] for i, r in enumerate(data) if r['time'] >= cut_date and ema20[i] is not None]
    e_dates = [r['time'] for i, r in enumerate(data) if r['time'] >= cut_date and ema10[i] is not None]

    ax.plot(dates, closes, 'k-', linewidth=1, label='Close', alpha=0.5)
    ax.plot(e_dates, e10, 'b-', linewidth=2, label='EMA 10')
    ax.plot(e_dates, e20, 'r-', linewidth=2, label='EMA 20')
    ax.set_title(title, fontsize=13, fontweight='bold')
    ax.legend(loc='upper left')
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))

    # Highlight March 16
    for r in data:
        if r['time'].strftime('%Y-%m-%d') == '2026-03-16':
            ax.axvline(r['time'], color='orange', linewidth=1.5, linestyle='--', alpha=0.7, label='Mar 16')
            break

plot_panel(ax1, ic_data, ic_ema10, ic_ema20, 'ICMarkets D1 — AUDUSD', cut)
plot_panel(ax2, dk_raw, dk_raw_ema10, dk_raw_ema20, 'Dukascopy D1 — AUDUSD (raw, incl. weekend bars)', cut)
plot_panel(ax3, dk_filtered, dk_filt_ema10, dk_filt_ema20, 'Dukascopy D1 — AUDUSD (weekends removed) ✓', cut)

fig.tight_layout()
fig.savefig('output/ema_compare_audusd_d1.png', dpi=150)
plt.close(fig)
print("\nChart saved to output/ema_compare_audusd_d1.png")
