import logging
import os

from models import EnrichedSignal


def _format_duration(hours: float | None) -> str:
    if hours is None:
        return '—'
    total_hours = int(hours)
    days = total_hours // 24
    remaining_hours = total_hours % 24
    if days > 0:
        return f"{days}d {remaining_hours}h"
    return f"{total_hours}h"

logger = logging.getLogger(__name__)


class TradeLogger:

    def __init__(self, initial_balance: float = 10_000.0):
        self._initial_balance = initial_balance
        self._open_trades: dict[int, EnrichedSignal] = {}  # ticket -> signal
        self._closed_trades: list[dict] = []

    def log_open(self, signal: EnrichedSignal, ticket: int):
        self._open_trades[ticket] = signal
        logger.info(
            f"OPEN  | {signal.symbol:<8} {signal.direction:<5} | "
            f"entry={signal.entry_price:.5f}  sl={signal.stop_loss:.5f}  "
            f"tp={signal.take_profit:.5f}  lots={signal.lot_size} | {signal.strategy_name}"
        )

    def log_close(self, ticket: int, trade: dict):
        self._closed_trades.append(trade)
        self._open_trades.pop(ticket, None)
        logger.info(
            f"CLOSE | {trade['symbol']:<8} {trade['direction']:<5} | "
            f"{trade['result']:<4} R={trade['r_multiple']:+.2f} | {trade['strategy_name']}"
        )

    def print_trade_log(self):
        if not self._closed_trades:
            print("\nNo closed trades.")
            return

        print("\n" + "=" * 100)
        print("TRADE LOG")
        print("=" * 100)
        print(f"{'Datetime':<20}  {'Symbol':<8}  {'Dir':<5}  {'Result':<6}  {'R':>6}  {'Entry':>10}  {'SL Pips':>8}  {'Duration':>9}  Strategy")
        print("-" * 110)
        for t in self._closed_trades:
            open_time = t.get('open_time') or t.get('close_time')
            dt = open_time.strftime('%Y-%m-%d %H:%M') if hasattr(open_time, 'strftime') else str(open_time)
            entry = t.get('fill_price') or t.get('entry_price')
            entry_str = f"{entry:>10.5f}" if entry is not None else f"{'—':>10}"
            sl_pips = t.get('sl_pips')
            sl_pips_str = f"{sl_pips:>7.1f}" if sl_pips is not None else f"{'—':>7}"
            duration_str = _format_duration(t.get('duration_hours'))
            print(
                f"{dt:<20}  {t['symbol']:<8}  {t['direction']:<5}  "
                f"{t['result']:<6}  {t['r_multiple']:>+6.2f}  {entry_str}  {sl_pips_str}  {duration_str:>9}  {t['strategy_name']}"
            )

    def print_summary(self):
        trades = self._closed_trades
        if not trades:
            print("\nNo trades to summarise.")
            return

        total = len(trades)
        wins   = [t for t in trades if t['result'] == 'WIN']
        losses = [t for t in trades if t['result'] == 'LOSS']
        bes    = [t for t in trades if t['result'] == 'BE']

        win_rate       = len(wins) / total * 100
        total_r        = sum(t['r_multiple'] for t in trades)
        gross_profit_r = sum(t['r_multiple'] for t in wins)   if wins   else 0.0
        gross_loss_r   = abs(sum(t['r_multiple'] for t in losses)) if losses else 0.0
        profit_factor  = gross_profit_r / gross_loss_r if gross_loss_r > 0 else float('inf')
        expectancy     = total_r / total
        avg_win_r      = gross_profit_r / len(wins)   if wins   else 0.0
        avg_loss_r     = gross_loss_r   / len(losses) if losses else 0.0

        # Max drawdown in R (peak-to-trough on cumulative R curve)
        peak, max_dd_r, running = 0.0, 0.0, 0.0
        for t in trades:
            running += t['r_multiple']
            peak = max(peak, running)
            max_dd_r = max(max_dd_r, peak - running)

        # Max drawdown in % (peak-to-trough on cumulative equity curve)
        balance = self._initial_balance
        peak_balance = balance
        max_dd_pct = 0.0
        for t in trades:
            balance += t.get('pnl', 0.0)
            peak_balance = max(peak_balance, balance)
            dd_pct = (peak_balance - balance) / peak_balance * 100 if peak_balance > 0 else 0.0
            max_dd_pct = max(max_dd_pct, dd_pct)

        # Win / loss streaks
        best_win_streak = worst_loss_streak = current_streak = 0
        streak_type = None
        for t in trades:
            if t['result'] == streak_type:
                current_streak += 1
            else:
                current_streak = 1
                streak_type = t['result']
            if streak_type == 'WIN':
                best_win_streak = max(best_win_streak, current_streak)
            else:
                worst_loss_streak = max(worst_loss_streak, current_streak)

        # Final balance
        final_balance = self._initial_balance
        for t in trades:
            final_balance += t.get('pnl', 0.0)

        print("\n" + "=" * 100)
        print("PERFORMANCE SUMMARY")
        print("=" * 100)
        print(f"  Starting balance   ${self._initial_balance:,.2f}")
        print(f"  Ending balance     ${final_balance:,.2f}")
        print(f"  Total trades       {total}")
        be_str = f" / {len(bes)}BE" if bes else ""
        print(f"  Win rate           {win_rate:.1f}%  ({len(wins)}W / {len(losses)}L{be_str})")
        print(f"  Total R            {total_r:+.2f}R")
        print(f"  Profit factor      {profit_factor:.2f}")
        print(f"  Expectancy         {expectancy:+.2f}R per trade")
        print(f"  Max drawdown       {max_dd_r:.2f}R  ({max_dd_pct:.1f}%)")
        print(f"  Best win streak    {best_win_streak}")
        print(f"  Worst loss streak  {worst_loss_streak}")
        print(f"  Avg win            {avg_win_r:.2f}R")
        print(f"  Avg loss           {avg_loss_r:.2f}R")

        total_commission = sum(t.get('commission', 0.0) for t in trades)
        if total_commission > 0:
            print(f"  Total commission   ${total_commission:,.2f}")

        print("=" * 100)

    def plot_equity_curve(self, output_dir: str = 'output'):
        """Save an equity curve chart as a PNG file."""
        trades = self._closed_trades
        if not trades:
            print("No trades to plot.")
            return

        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
        except ImportError:
            print("matplotlib not installed — skipping equity curve plot.")
            return

        # Build equity series: starting point + one entry per closed trade
        timestamps = []
        equity = []
        balance = self._initial_balance

        # Add the starting point using the first trade's open time
        first_open = trades[0].get('open_time') or trades[0].get('close_time')
        timestamps.append(first_open)
        equity.append(balance)

        for t in trades:
            balance += t.get('pnl', 0.0)
            close_time = t.get('close_time') or t.get('open_time')
            timestamps.append(close_time)
            equity.append(balance)

        # Determine strategy/symbol names and date range for title and filename
        strategy_names = sorted(set(t['strategy_name'] for t in trades))
        symbols = sorted(set(t['symbol'] for t in trades))
        symbol_str = ', '.join(symbols)
        first_dt = timestamps[0]
        last_dt = timestamps[-1]
        date_from = first_dt.strftime('%Y%m%d')
        date_to = last_dt.strftime('%Y%m%d')
        date_range_label = f"{first_dt.strftime('%Y-%m-%d')} to {last_dt.strftime('%Y-%m-%d')}"

        fig, ax = plt.subplots(figsize=(12, 5))
        ax.plot(timestamps, equity, linewidth=1.5, color='#2563eb')
        ax.fill_between(timestamps, self._initial_balance, equity,
                        where=[e >= self._initial_balance for e in equity],
                        alpha=0.15, color='#16a34a', interpolate=True)
        ax.fill_between(timestamps, self._initial_balance, equity,
                        where=[e < self._initial_balance for e in equity],
                        alpha=0.15, color='#dc2626', interpolate=True)
        ax.axhline(self._initial_balance, color='grey', linewidth=0.8, linestyle='--')

        ax.set_title(f'{symbol_str} — {date_range_label}', fontsize=13, fontweight='bold')
        ax.set_xlabel('Date')
        ax.set_ylabel('Account Balance ($)')
        span_days = (timestamps[-1] - timestamps[0]).days
        if span_days > 1825:  # 5+ years
            ax.xaxis.set_major_locator(mdates.YearLocator())
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        elif span_days > 730:  # 2-5 years
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        elif span_days > 365:  # 1-2 years
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        else:
            ax.xaxis.set_major_locator(mdates.MonthLocator())
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        fig.autofmt_xdate(rotation=45)
        ax.grid(True, alpha=0.3)

        # Annotate final balance
        final = equity[-1]
        pnl = final - self._initial_balance
        pnl_pct = pnl / self._initial_balance * 100
        ax.annotate(f'${final:,.2f} ({pnl_pct:+.1f}%)',
                    xy=(timestamps[-1], final), fontsize=10,
                    xytext=(10, 10), textcoords='offset points',
                    bbox=dict(boxstyle='round,pad=0.3', fc='white', ec='grey', alpha=0.9))

        fig.tight_layout()

        os.makedirs(output_dir, exist_ok=True)
        file_symbols = '_'.join(symbols)
        base_name = f'{strategy_names[0]}_{file_symbols}_{date_from}-{date_to}'
        filepath = os.path.join(output_dir, f'equity_curve_{base_name}.png')
        fig.savefig(filepath, dpi=150)
        plt.close(fig)
        print(f"\nEquity curve saved to {filepath}")

        self._plot_heatmaps(output_dir, base_name)

    def _plot_heatmaps(self, output_dir: str, base_name: str):
        """Generate monthly R heatmap and yearly performance heatmap."""
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import numpy as np
        from collections import defaultdict

        trades = self._closed_trades
        month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                       'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

        # ── Aggregate R by year/month ────────────────────────────────────────
        monthly_r: dict[int, dict[int, float]] = defaultdict(lambda: defaultdict(float))
        monthly_count: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
        for t in trades:
            ct = t.get('close_time') or t.get('open_time')
            monthly_r[ct.year][ct.month] += t['r_multiple']
            monthly_count[ct.year][ct.month] += 1

        years = sorted(monthly_r.keys())
        if not years:
            return

        # ── Monthly heatmap ──────────────────────────────────────────────────
        grid = np.full((len(years), 12), np.nan)
        for i, y in enumerate(years):
            for m in range(1, 13):
                if monthly_count[y][m] > 0:
                    grid[i, m - 1] = round(monthly_r[y][m], 2)

        max_abs = np.nanmax(np.abs(grid)) if not np.all(np.isnan(grid)) else 1.0
        fig_h = max(3, len(years) * 0.6 + 1.5)
        fig, ax = plt.subplots(figsize=(14, fig_h))

        cmap = plt.cm.RdYlGn
        im = ax.imshow(grid, cmap=cmap, aspect='auto',
                       vmin=-max_abs, vmax=max_abs)

        ax.set_xticks(range(12))
        ax.set_xticklabels(month_names)
        ax.set_yticks(range(len(years)))
        ax.set_yticklabels(years)
        ax.set_title('Monthly Total R', fontsize=13, fontweight='bold', pad=12)

        # Annotate cells
        for i in range(len(years)):
            for j in range(12):
                val = grid[i, j]
                if np.isnan(val):
                    continue
                color = 'white' if abs(val) > max_abs * 0.6 else 'black'
                ax.text(j, i, f'{val:+.1f}', ha='center', va='center',
                        fontsize=9, fontweight='bold', color=color)

        fig.colorbar(im, ax=ax, label='Total R', shrink=0.8, pad=0.02)
        fig.tight_layout()
        path = os.path.join(output_dir, f'heatmap_monthly_{base_name}.png')
        fig.savefig(path, dpi=150)
        plt.close(fig)
        print(f"Monthly heatmap saved to {path}")

        # ── Yearly performance heatmap ───────────────────────────────────────
        yearly_stats = []
        for y in years:
            yt = [t for t in trades if (t.get('close_time') or t.get('open_time')).year == y]
            total = len(yt)
            wins = sum(1 for t in yt if t['result'] == 'WIN')
            total_r = sum(t['r_multiple'] for t in yt)
            gp = sum(t['r_multiple'] for t in yt if t['result'] == 'WIN')
            gl = abs(sum(t['r_multiple'] for t in yt if t['result'] == 'LOSS'))
            pf = gp / gl if gl > 0 else 0.0
            wr = wins / total * 100 if total > 0 else 0.0
            exp = total_r / total if total > 0 else 0.0
            yearly_stats.append({
                'year': y, 'trades': total, 'wr': wr,
                'total_r': total_r, 'pf': pf, 'expect': exp,
            })

        metrics = ['Total R', 'Trades', 'Win Rate %', 'Expectancy', 'Profit Factor']
        grid_y = np.zeros((len(metrics), len(years)))
        for j, s in enumerate(yearly_stats):
            grid_y[0, j] = s['total_r']
            grid_y[1, j] = s['trades']
            grid_y[2, j] = s['wr']
            grid_y[3, j] = s['expect']
            grid_y[4, j] = s['pf']

        fig_w = max(8, len(years) * 1.1 + 2)
        fig, ax = plt.subplots(figsize=(fig_w, 4))

        # Normalise each row independently for colour mapping
        norm_grid = np.zeros_like(grid_y)
        for i in range(len(metrics)):
            row = grid_y[i]
            rmin, rmax = row.min(), row.max()
            if rmax > rmin:
                norm_grid[i] = (row - rmin) / (rmax - rmin)
            else:
                norm_grid[i] = 0.5

        im = ax.imshow(norm_grid, cmap=plt.cm.RdYlGn, aspect='auto',
                       vmin=0, vmax=1)

        ax.set_xticks(range(len(years)))
        ax.set_xticklabels(years)
        ax.set_yticks(range(len(metrics)))
        ax.set_yticklabels(metrics)
        ax.set_title('Yearly Performance', fontsize=13, fontweight='bold', pad=12)

        # Annotate with actual values
        formats = ['{:+.1f}', '{:.0f}', '{:.1f}%', '{:+.2f}', '{:.2f}']
        for i in range(len(metrics)):
            for j in range(len(years)):
                val = grid_y[i, j]
                nv = norm_grid[i, j]
                color = 'white' if nv < 0.25 or nv > 0.75 else 'black'
                label = formats[i].format(val)
                ax.text(j, i, label, ha='center', va='center',
                        fontsize=9, fontweight='bold', color=color)

        fig.tight_layout()
        path = os.path.join(output_dir, f'heatmap_yearly_{base_name}.png')
        fig.savefig(path, dpi=150)
        plt.close(fig)
        print(f"Yearly heatmap saved to {path}")
