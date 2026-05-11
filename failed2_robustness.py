"""
Focused robustness checks for Failed2 on USA100.

This is intentionally not a broad optimizer. It checks whether the current
research candidate survives nearby parameter changes, execution-cost stress, and
basic time/setup breakdowns.
"""

import argparse
import contextlib
import csv
import io
import itertools
import logging
import sys
from collections import defaultdict
from datetime import datetime

import config
from data.historical_loader import find_csv, filter_bars, load_and_merge
from execution.simulated_execution import SimulatedExecution
from portfolio.portfolio_manager import PortfolioManager
from risk.risk_manager import RiskManager
from strategies.failed2 import Failed2Strategy

logging.basicConfig(level=logging.ERROR)
sys.stdout.reconfigure(line_buffering=True)

INITIAL_BALANCE = 10_000.0

SESSIONS = {
    '12_17': (*range(0, 12), *range(17, 24)),
    '13_18': (*range(0, 13), *range(18, 24)),
    '12_18': (*range(0, 12), *range(18, 24)),
}

BIAS_ALL = ('2', '3', 'failed2')


class SlippageExecution(SimulatedExecution):
    """Adverse entry slippage in pips for execution sensitivity tests."""

    def __init__(self, *args, slippage_pips: float = 0.0, **kwargs):
        super().__init__(*args, **kwargs)
        self._slippage_pips = slippage_pips

    def _entry_price(self, bid_price: float, symbol: str, direction: str) -> float:
        price = super()._entry_price(bid_price, symbol, direction)
        slip = self._slippage_pips * config.PIP_SIZE.get(symbol, 0.0001)
        return price + slip if direction == 'BUY' else price - slip


def parse_args():
    parser = argparse.ArgumentParser(description='Run Failed2 USA100 robustness checks.')
    parser.add_argument('--symbol', default='USA100')
    parser.add_argument('--start-date', default='2020-01-01')
    parser.add_argument('--end-date', default='2026-01-01')
    parser.add_argument('--holdout-start', default='2025-01-01')
    parser.add_argument('--output-prefix', default='output/failed2_usa100_robustness')
    parser.add_argument('--data-source', choices=['dukascopy', 'histdata'], default='dukascopy')
    parser.add_argument(
        '--candidate',
        choices=['filtered', 'usa100_candidate'],
        default='filtered',
        help='Fixed Failed2 configuration to evaluate.',
    )
    parser.add_argument(
        '--sections',
        nargs='+',
        choices=['base', 'holdout', 'params', 'costs', 'bias', 'breakdowns', 'all'],
        default=['all'],
        help='Robustness sections to run. Default: all.',
    )
    return parser.parse_args()


def parse_date(value):
    return datetime.strptime(value, '%Y-%m-%d') if value else None


def load_bars(symbol, start_date, end_date, data_source):
    paths = []
    for tf in ('D1', 'H4', 'H1', 'M5'):
        found = find_csv(symbol, tf, data_source=data_source)
        if not found:
            raise SystemExit(f"Missing {symbol} {tf} data for source={data_source}")
        paths.extend(found)

    bars = load_and_merge(paths)
    return filter_bars(bars, start=parse_date(start_date), end=parse_date(end_date))


def make_strategy(
    mss_n=3,
    sl_n=2,
    rr=3.5,
    session='12_17',
    d1_range_block_pct=0.8,
    trend_filter='d1_ema',
    allowed_bias_kinds=BIAS_ALL,
):
    return Failed2Strategy(
        tf_bias='H4',
        tf_intermediate='H1',
        tf_entry='M5',
        entry_mode='market',
        mss_fractal_n=mss_n,
        sl_fractal_n=sl_n,
        rr_ratio=rr,
        blocked_hours=SESSIONS[session],
        sl_anchor='wick',
        trend_filter=trend_filter,
        d1_range_filter='block_top_pct',
        d1_range_block_pct=d1_range_block_pct,
        allowed_bias_kinds=allowed_bias_kinds,
        pip_sizes=dict(config.PIP_SIZE),
        use_d1_diagnostics=True,
    )


def run_backtest(
    bars,
    symbol,
    strategy,
    rr,
    spread_mult=1.0,
    commission_mult=1.0,
    slippage_pips=0.0,
):
    spread = dict(config.BACKTEST_SPREAD_PIPS)
    spread[symbol] = spread.get(symbol, 0.0) * spread_mult

    execution = SlippageExecution(
        INITIAL_BALANCE,
        spread_pips=spread,
        rr_ratio=rr,
        commission_per_lot=config.COMMISSION_PER_LOT * commission_mult,
        slippage_pips=slippage_pips,
    )
    portfolio = PortfolioManager(max_open_trades=99, max_daily_loss_pct=None)
    risk = RiskManager(account_balance_fn=execution.get_account_balance, rr_ratio=rr)

    ticket_context = {}
    closed_with_context = []

    for bar in bars:
        closed = execution.check_fills(bar)
        for trade in closed:
            portfolio.record_close(trade['symbol'], trade['pnl'], trade.get('strategy_name', ''))
            ctx = ticket_context.pop(trade['ticket'], {})
            trade = {**trade, **ctx}
            closed_with_context.append(trade)
            if trade.get('result') == 'LOSS':
                strategy.notify_loss(trade['symbol'])
            elif trade.get('result') == 'WIN':
                strategy.notify_win(trade['symbol'])

        portfolio.set_current_date(bar.timestamp.date())
        if bar.symbol != symbol or bar.timeframe not in strategy.TIMEFRAMES:
            continue

        signal = strategy.generate_signal(bar)
        if signal is None:
            continue

        if signal.direction == 'CANCEL':
            continue

        signal.entry_timeframe = bar.timeframe
        enriched = risk.process(signal)
        if enriched is None or not portfolio.approve(enriched):
            continue

        ticket = execution.place_order(
            symbol=enriched.symbol,
            direction=enriched.direction,
            order_type=enriched.order_type,
            entry_price=enriched.entry_price,
            lot_size=enriched.lot_size,
            sl=enriched.stop_loss,
            tp=enriched.take_profit,
            strategy_name=enriched.strategy_name,
            entry_timeframe=enriched.entry_timeframe,
            tp_locked=enriched.tp_locked,
            signal_time=enriched.timestamp,
        )
        if ticket:
            portfolio.record_open(enriched, ticket)
            ticket_context[ticket] = strategy.get_last_signal_context(enriched.symbol) or {}

    return closed_with_context, execution.get_account_balance()


def trade_net_r(trade):
    pip_value = config.PIP_VALUE_USD.get(trade['symbol'], 10.0)
    risk_cash = trade['sl_pips'] * pip_value * trade['lot_size']
    return trade['pnl'] / risk_cash if risk_cash > 0 else 0.0


def metrics(trades, final_balance=None):
    if not trades:
        return {
            'trades': 0,
            'win_rate': 0.0,
            'net_r': 0.0,
            'expectancy': 0.0,
            'pf': 0.0,
            'max_dd_r': 0.0,
            'worst_loss_streak': 0,
            'final_balance': final_balance or INITIAL_BALANCE,
            'return_pct': ((final_balance or INITIAL_BALANCE) / INITIAL_BALANCE - 1.0) * 100,
        }

    net_rs = [trade_net_r(t) for t in trades]
    wins = sum(1 for t in trades if t['result'] == 'WIN')
    gross_profit = sum(r for r in net_rs if r > 0)
    gross_loss = abs(sum(r for r in net_rs if r < 0))

    peak = running = max_dd = 0.0
    worst_streak = cur_streak = 0
    for trade, r in zip(trades, net_rs):
        running += r
        peak = max(peak, running)
        max_dd = max(max_dd, peak - running)
        if trade['result'] == 'LOSS':
            cur_streak += 1
            worst_streak = max(worst_streak, cur_streak)
        else:
            cur_streak = 0

    balance = final_balance or INITIAL_BALANCE + sum(t['pnl'] for t in trades)
    return {
        'trades': len(trades),
        'win_rate': wins / len(trades) * 100,
        'net_r': sum(net_rs),
        'expectancy': sum(net_rs) / len(trades),
        'pf': gross_profit / gross_loss if gross_loss > 0 else 0.0,
        'max_dd_r': max_dd,
        'worst_loss_streak': worst_streak,
        'final_balance': balance,
        'return_pct': (balance / INITIAL_BALANCE - 1.0) * 100,
    }


def format_row(label, m):
    return (
        f"{label:<28} {m['trades']:>6} {m['win_rate']:>6.1f}% "
        f"{m['net_r']:>+8.1f} {m['expectancy']:>+7.3f} "
        f"{m['pf']:>6.2f} {m['max_dd_r']:>7.1f} "
        f"{m['worst_loss_streak']:>4} {m['return_pct']:>+7.1f}%"
    )


def print_rows(title, rows, limit=None):
    print(f"\n{'=' * 118}")
    print(title)
    print('=' * 118)
    print(f"{'label':<28} {'trades':>6} {'WR%':>7} {'NetR':>8} {'Exp':>7} {'PF':>6} {'MaxDD':>7} {'LStk':>4} {'Ret%':>8}")
    print('-' * 118)
    for label, m in rows[:limit]:
        print(format_row(label, m))


def write_rows(path, rows):
    with open(path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['label', 'trades', 'win_rate', 'net_r', 'expectancy', 'pf', 'max_dd_r', 'worst_loss_streak', 'final_balance', 'return_pct'])
        for label, m in rows:
            writer.writerow([
                label,
                m['trades'],
                round(m['win_rate'], 2),
                round(m['net_r'], 3),
                round(m['expectancy'], 4),
                round(m['pf'], 3),
                round(m['max_dd_r'], 3),
                m['worst_loss_streak'],
                round(m['final_balance'], 2),
                round(m['return_pct'], 2),
            ])


def run_config(bars, symbol, **params):
    if params.pop('candidate', 'filtered') == 'usa100_candidate':
        params = {
            'mss_n': 4,
            'sl_n': 2,
            'rr': 4.0,
            'session': '13_18',
            'd1_range_block_pct': 0.7,
            'trend_filter': 'd1_ema',
            'allowed_bias_kinds': BIAS_ALL,
            **params,
        }

    rr = params.get('rr', 3.5)
    strategy = make_strategy(
        mss_n=params.get('mss_n', 3),
        sl_n=params.get('sl_n', 2),
        rr=rr,
        session=params.get('session', '12_17'),
        d1_range_block_pct=params.get('d1_range_block_pct', 0.8),
        trend_filter=params.get('trend_filter', 'd1_ema'),
        allowed_bias_kinds=params.get('allowed_bias_kinds', BIAS_ALL),
    )
    with contextlib.redirect_stdout(io.StringIO()):
        trades, balance = run_backtest(
            bars,
            symbol,
            strategy,
            rr=rr,
            spread_mult=params.get('spread_mult', 1.0),
            commission_mult=params.get('commission_mult', 1.0),
            slippage_pips=params.get('slippage_pips', 0.0),
        )
    return trades, metrics(trades, balance)


def parameter_neighborhood(bars, symbol):
    rows = []
    for mss_n, sl_n, rr, session, block_pct in itertools.product(
        (2, 3, 4),
        (1, 2, 3),
        (3.0, 3.5, 4.0),
        ('12_17', '13_18', '12_18'),
        (0.7, 0.8, 0.9),
    ):
        label = f"mss{mss_n}/sl{sl_n}/rr{rr:g}/{session}/blk{int(block_pct * 100)}"
        _, m = run_config(
            bars,
            symbol,
            mss_n=mss_n,
            sl_n=sl_n,
            rr=rr,
            session=session,
            d1_range_block_pct=block_pct,
        )
        if m['trades'] >= 40:
            rows.append((label, m))
    return sorted(rows, key=lambda item: (item[1]['net_r'], item[1]['expectancy']), reverse=True)


def cost_stress(bars, symbol):
    rows = []
    for spread_mult, commission_mult, slippage_pips in itertools.product(
        (1.0, 1.5, 2.0),
        (1.0, 1.5, 2.0),
        (0.0, 0.5, 1.0),
    ):
        label = f"spr{spread_mult:g}/comm{commission_mult:g}/slip{slippage_pips:g}"
        _, m = run_config(
            bars,
            symbol,
            spread_mult=spread_mult,
            commission_mult=commission_mult,
            slippage_pips=slippage_pips,
        )
        rows.append((label, m))
    return sorted(rows, key=lambda item: (item[1]['net_r'], item[1]['expectancy']), reverse=True)


def bias_variants(bars, symbol):
    variants = [
        ('all_bias', BIAS_ALL),
        ('2_only', ('2',)),
        ('3_only', ('3',)),
        ('2_3_only', ('2', '3')),
        ('failed2_only', ('failed2',)),
    ]
    rows = []
    for label, allowed in variants:
        _, m = run_config(bars, symbol, allowed_bias_kinds=allowed)
        rows.append((label, m))
    return rows


def group_rows(trades, key_fn, min_trades=10):
    grouped = defaultdict(list)
    for trade in trades:
        grouped[key_fn(trade)].append(trade)

    rows = []
    for key, group in grouped.items():
        if len(group) >= min_trades:
            rows.append((str(key), metrics(group)))
    return sorted(rows, key=lambda item: item[1]['net_r'], reverse=True)


def range_bucket(trade):
    pct = trade.get('d1_range_percentile')
    if pct is None:
        return 'unknown'
    if pct >= 0.8:
        return 'top_20pct'
    if pct >= 0.6:
        return '60_80pct'
    if pct >= 0.4:
        return '40_60pct'
    return 'bottom_40pct'


def month_key(trade):
    close_time = trade.get('close_time')
    return close_time.strftime('%Y-%m') if close_time else 'unknown'


def main():
    args = parse_args()
    symbol = args.symbol.upper()
    sections = set(args.sections)
    if 'all' in sections:
        sections = {'base', 'holdout', 'params', 'costs', 'bias', 'breakdowns'}

    print(f"Loading {symbol} bars from {args.data_source}...")
    bars = load_bars(symbol, args.start_date, args.end_date, args.data_source)
    print(f"Loaded {len(bars):,} bars from {args.start_date} to {args.end_date}")

    base_trades = None
    if 'base' in sections or 'breakdowns' in sections:
        print("\nRunning base configuration...")
        base_trades, base_metrics = run_config(bars, symbol, candidate=args.candidate)
        if 'base' in sections:
            print_rows("BASE CONFIG", [(args.candidate, base_metrics)])

    if 'holdout' in sections:
        print("\nRunning holdout...")
        holdout_bars = [b for b in bars if b.timestamp >= parse_date(args.holdout_start)]
        _, holdout_metrics = run_config(holdout_bars, symbol, candidate=args.candidate)
        print_rows(f"HOLDOUT FROM {args.holdout_start}", [(f"holdout_{args.holdout_start}", holdout_metrics)])

    if 'params' in sections:
        print("\nRunning parameter neighborhood grid...")
        param_rows = parameter_neighborhood(bars, symbol)
        print_rows("PARAMETER NEIGHBORHOOD - TOP 25", param_rows, limit=25)
        print_rows("PARAMETER NEIGHBORHOOD - BOTTOM 15", list(reversed(param_rows)), limit=15)
        write_rows(f"{args.output_prefix}_params.csv", param_rows)

    if 'costs' in sections:
        print("\nRunning execution-cost stress grid...")
        cost_rows = cost_stress(bars, symbol)
        print_rows("COST STRESS - BEST TO WORST", cost_rows)
        write_rows(f"{args.output_prefix}_costs.csv", cost_rows)

    if 'bias' in sections:
        print("\nRunning HTF bias variants...")
        bias_rows = bias_variants(bars, symbol)
        print_rows("HTF BIAS VARIANTS", bias_rows)
        write_rows(f"{args.output_prefix}_bias.csv", bias_rows)

    if 'breakdowns' in sections:
        print("\nRunning breakdowns...")
        print_rows("BY YEAR", group_rows(base_trades, lambda t: t['close_time'].year, min_trades=5))
        print_rows("BY MONTH - TOP 20", group_rows(base_trades, month_key, min_trades=3), limit=20)
        print_rows("BY MONTH - BOTTOM 20", list(reversed(group_rows(base_trades, month_key, min_trades=3))), limit=20)
        print_rows("BY DIRECTION", group_rows(base_trades, lambda t: t.get('direction')))
        print_rows("BY HTF BIAS TYPE", group_rows(base_trades, lambda t: t.get('htf_bias_type') or 'unknown'))
        print_rows("BY ENTRY HOUR UTC", group_rows(base_trades, lambda t: t.get('session_hour'), min_trades=5))
        print_rows("BY D1 RANGE BUCKET", group_rows(base_trades, range_bucket, min_trades=5))

    print(f"\nCSV saved:")
    if 'params' in sections:
        print(f"  {args.output_prefix}_params.csv")
    if 'costs' in sections:
        print(f"  {args.output_prefix}_costs.csv")
    if 'bias' in sections:
        print(f"  {args.output_prefix}_bias.csv")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
