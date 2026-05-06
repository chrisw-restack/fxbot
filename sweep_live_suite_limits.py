"""Sweep portfolio limits for the current live/demo strategy suite."""

import contextlib
import io
import logging

import config
from backtest_engine import BacktestEngine
from data.historical_loader import find_csv, load_and_merge
from live_config import create_live_strategy_specs
from walk_forward import compute_metrics


INITIAL_BALANCE = 10_000.0
RR_RATIO = 2.5

# Keep this intentionally small: each combo is a full multi-symbol replay.
MAX_OPEN_TRADES_VALUES = [4, 6, 8, 10]
MAX_DAILY_LOSS_VALUES = [0.01, 0.02, 0.03, None]


def collect_csv_paths(strategy_specs):
    paths = []
    seen = set()
    for strategy, symbols in strategy_specs:
        for symbol in symbols:
            for timeframe in strategy.TIMEFRAMES:
                for path in find_csv(symbol, timeframe):
                    if path not in seen:
                        paths.append(path)
                        seen.add(path)
    return paths


def run_combo(all_bars, max_open_trades, max_daily_loss_pct):
    engine = BacktestEngine(
        initial_balance=INITIAL_BALANCE,
        rr_ratio=RR_RATIO,
        max_open_trades=max_open_trades,
        max_daily_loss_pct=max_daily_loss_pct,
    )
    for strategy, symbols in create_live_strategy_specs():
        engine.add_strategy(strategy, symbols=symbols)

    with contextlib.redirect_stdout(io.StringIO()):
        for bar in all_bars:
            closed_trades = engine.execution.check_fills(bar)
            for trade in closed_trades:
                engine.portfolio.record_close(
                    trade['symbol'], trade['pnl'], trade.get('strategy_name', ''),
                )
                engine.trade_logger.log_close(trade['ticket'], trade)
                engine.event_engine.notify_trade_closed(trade)
            engine.event_engine.process_bar(bar)

    trades = engine.execution.get_closed_trades()
    metrics = compute_metrics(trades)
    final_balance = INITIAL_BALANCE + sum(t.get('pnl', 0.0) for t in trades)
    return {
        **metrics,
        'final_balance': round(final_balance, 2),
        'max_open_trades': max_open_trades,
        'max_daily_loss_pct': max_daily_loss_pct,
    }


def format_pct(value):
    return 'off' if value is None else f'{value * 100:.0f}%'


def main():
    logging.basicConfig(level=logging.ERROR)
    logging.getLogger().setLevel(logging.ERROR)

    strategy_specs = create_live_strategy_specs()
    csv_paths = collect_csv_paths(strategy_specs)
    if not csv_paths:
        raise SystemExit('No CSV files found for live suite.')

    print(f'Loading {len(csv_paths)} CSV files...')
    all_bars = load_and_merge(csv_paths)
    print(f'Loaded {len(all_bars):,} bars')

    results = []
    total = len(MAX_OPEN_TRADES_VALUES) * len(MAX_DAILY_LOSS_VALUES)
    i = 0
    for max_open in MAX_OPEN_TRADES_VALUES:
        for max_loss in MAX_DAILY_LOSS_VALUES:
            i += 1
            print(f'[{i}/{total}] max_open={max_open} daily_loss={format_pct(max_loss)}')
            results.append(run_combo(all_bars, max_open, max_loss))

    results.sort(key=lambda r: r['total_r'], reverse=True)

    print('\nRESULTS sorted by Total R')
    print(
        f"{'Open':>4} {'DayLoss':>7} {'Trades':>6} {'Win%':>6} "
        f"{'TotalR':>8} {'PF':>5} {'Exp':>7} {'MaxDD':>7} {'LossStk':>7} {'FinalBal':>12}"
    )
    for r in results:
        print(
            f"{r['max_open_trades']:>4} {format_pct(r['max_daily_loss_pct']):>7} "
            f"{r['trades']:>6} {r['win_rate']:>6.1f} {r['total_r']:>8.1f} "
            f"{r['pf']:>5.2f} {r['expectancy']:>7.3f} {r['max_dd_r']:>7.1f} "
            f"{r['worst_loss_streak']:>7} {r['final_balance']:>12,.2f}"
        )


if __name__ == '__main__':
    main()
