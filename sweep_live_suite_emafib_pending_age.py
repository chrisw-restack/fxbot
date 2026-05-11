"""Sweep EmaFibRetracement pending expiry inside the current live/demo suite.

This tests the portfolio-level question: a pending order can be bad even if it
is acceptable for the strategy in isolation, because it consumes one of the
global MAX_OPEN_TRADES slots and may crowd out other strategies.
"""

import contextlib
import io
import logging
from collections import Counter

import config
from backtest_engine import BacktestEngine
from data.historical_loader import find_csv, load_and_merge
from live_config import (
    ENGULFING_SYMBOLS,
    IMS_REV_SYMBOLS,
    IMS_SYMBOLS,
)
from portfolio.portfolio_manager import PortfolioManager
from strategies.ema_fib_retracement import EmaFibRetracementStrategy
from strategies.ema_fib_running import EmaFibRunningStrategy
from strategies.ims import ImsStrategy
from strategies.ims_reversal import ImsReversalStrategy
from strategies.three_line_strike import ThreeLineStrikeStrategy
from walk_forward import compute_metrics


INITIAL_BALANCE = 10_000.0
RR_RATIO = 2.5
SCENARIOS = [
    {
        'name': 'baseline',
        'pending_max_age_bars': 0,
        'cancel_if_virtual_tp_hit': False,
        'pending_cancel_at_r': None,
    },
    {
        'name': 'virtual_tp',
        'pending_max_age_bars': 0,
        'cancel_if_virtual_tp_hit': True,
        'pending_cancel_at_r': None,
    },
    {
        'name': 'move_1r',
        'pending_max_age_bars': 0,
        'cancel_if_virtual_tp_hit': False,
        'pending_cancel_at_r': 1.0,
    },
    {
        'name': 'move_1_5r',
        'pending_max_age_bars': 0,
        'cancel_if_virtual_tp_hit': False,
        'pending_cancel_at_r': 1.5,
    },
    {
        'name': 'move_2r',
        'pending_max_age_bars': 0,
        'cancel_if_virtual_tp_hit': False,
        'pending_cancel_at_r': 2.0,
    },
]


class CountingPortfolioManager(PortfolioManager):
    """PortfolioManager that records why approvals are rejected."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.same_slot_rejections: Counter[str] = Counter()
        self.max_open_rejections: Counter[str] = Counter()

    def approve(self, signal) -> bool:
        key = (signal.symbol, signal.strategy_name)
        if key in self._open_positions:
            self.same_slot_rejections[signal.strategy_name] += 1
            return False

        if len(self._open_positions) >= self._max_open_trades:
            self.max_open_rejections[signal.strategy_name] += 1
            return False

        return True


def create_strategy_specs(scenario: dict):
    ema_fib = EmaFibRetracementStrategy(
        fib_entry=0.786,
        fib_tp=3.0,
        fractal_n=3,
        min_swing_pips=10,
        ema_sep_pct=0.001,
        cooldown_bars=10,
        invalidate_swing_on_loss=True,
        blocked_hours=(*range(20, 24), *range(0, 9)),
        pending_max_age_bars=scenario['pending_max_age_bars'],
        cancel_if_virtual_tp_hit=scenario['cancel_if_virtual_tp_hit'],
        pending_cancel_at_r=scenario['pending_cancel_at_r'],
    )
    ema_fib_running = EmaFibRunningStrategy(
        fib_entry=0.786,
        fib_tp=2.5,
        fractal_n=2,
        min_swing_pips=30,
        ema_sep_pct=0.0,
        cooldown_bars=0,
        invalidate_swing_on_loss=True,
        blocked_hours=(*range(20, 24), *range(0, 9)),
    )
    engulfing = ThreeLineStrikeStrategy(
        sl_mode='fractal',
        fractal_n=3,
        min_prev_body_pips=3.0,
        engulf_ratio=1.5,
        max_sl_pips=15,
        allowed_hours=tuple(range(13, 18)),
        sma_sep_pips=5.0,
    )
    ims = ImsStrategy(
        tf_htf='H4',
        tf_ltf='M15',
        fractal_n=1,
        ltf_fractal_n=1,
        htf_lookback=30,
        entry_mode='pending',
        tp_mode='rr',
        rr_ratio=2.5,
        cooldown_bars=0,
        blocked_hours=(*range(0, 12), *range(17, 24)),
        ema_fast=20,
        ema_slow=50,
        ema_sep=0.001,
        sl_anchor='swing',
        pip_sizes={s: config.PIP_SIZE[s] for s in IMS_SYMBOLS if s in config.PIP_SIZE},
    )
    ims_reversal = ImsReversalStrategy(
        tf_htf='H4',
        tf_ltf='M15',
        fractal_n=1,
        ltf_fractal_n=2,
        htf_lookback=30,
        entry_mode='pending',
        tp_mode='htf_pct',
        htf_tp_pct=0.5,
        zone_pct=0.5,
        cooldown_bars=0,
        blocked_hours=(*range(0, 12), *range(17, 24)),
        ema_fast=20,
        ema_slow=50,
        ema_sep=0.001,
        sl_anchor='swing',
        sl_buffer_pips=0.0,
        max_losses_per_bias=1,
        pip_sizes={s: config.PIP_SIZE[s] for s in IMS_REV_SYMBOLS if s in config.PIP_SIZE},
    )
    return [
        (ema_fib, config.SYMBOLS),
        (ema_fib_running, config.SYMBOLS),
        (engulfing, ENGULFING_SYMBOLS),
        (ims, IMS_SYMBOLS),
        (ims_reversal, IMS_REV_SYMBOLS),
    ]


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


def replay(all_bars, scenario: dict) -> dict:
    engine = BacktestEngine(
        initial_balance=INITIAL_BALANCE,
        rr_ratio=RR_RATIO,
        max_open_trades=config.MAX_OPEN_TRADES,
        max_daily_loss_pct=config.MAX_DAILY_LOSS_PCT,
    )
    portfolio = CountingPortfolioManager(
        max_open_trades=config.MAX_OPEN_TRADES,
        max_daily_loss_pct=config.MAX_DAILY_LOSS_PCT,
    )
    engine.portfolio = portfolio
    engine.event_engine.portfolio = portfolio

    for strategy, symbols in create_strategy_specs(scenario):
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
        'scenario': scenario['name'],
        'final_balance': round(final_balance, 2),
        'max_open_rejections': sum(portfolio.max_open_rejections.values()),
        'same_slot_rejections': sum(portfolio.same_slot_rejections.values()),
        'max_open_by_strategy': dict(portfolio.max_open_rejections),
        'same_slot_by_strategy': dict(portfolio.same_slot_rejections),
    }


def format_strategy_counts(counts: dict[str, int]) -> str:
    if not counts:
        return '-'
    return ', '.join(f'{name}:{count}' for name, count in sorted(counts.items()))


def main():
    logging.basicConfig(level=logging.ERROR)
    logging.getLogger().setLevel(logging.ERROR)

    specs = create_strategy_specs(SCENARIOS[0])
    csv_paths = collect_csv_paths(specs)
    if not csv_paths:
        raise SystemExit('No CSV files found for live suite.')

    print(f'Loading {len(csv_paths)} CSV files...')
    all_bars = load_and_merge(csv_paths)
    print(f'Loaded {len(all_bars):,} bars')
    print(
        f'Sweeping EmaFibRetracement pending expiry with '
        f'MAX_OPEN_TRADES={config.MAX_OPEN_TRADES}, '
        f'MAX_DAILY_LOSS_PCT={config.MAX_DAILY_LOSS_PCT}\n'
    )

    results = []
    for i, scenario in enumerate(SCENARIOS, start=1):
        print(f'[{i}/{len(SCENARIOS)}] scenario={scenario["name"]}')
        results.append(replay(all_bars, scenario))

    print('\nRESULTS sorted by Total R')
    print(
        f"{'Scenario':>12} {'Trades':>6} {'Win%':>6} {'TotalR':>8} {'PF':>5} "
        f"{'Exp':>7} {'MaxDD':>7} {'LossStk':>7} {'MaxBlk':>7} "
        f"{'SlotBlk':>7} {'FinalBal':>12}"
    )
    for result in sorted(results, key=lambda r: r['total_r'], reverse=True):
        print(
            f"{result['scenario']:>12} {result['trades']:>6} "
            f"{result['win_rate']:>6.1f} {result['total_r']:>8.1f} "
            f"{result['pf']:>5.2f} {result['expectancy']:>7.3f} "
            f"{result['max_dd_r']:>7.1f} {result['worst_loss_streak']:>7} "
            f"{result['max_open_rejections']:>7} "
            f"{result['same_slot_rejections']:>7} "
            f"{result['final_balance']:>12,.2f}"
        )

    print('\nMAX_OPEN rejection breakdown')
    for result in results:
        print(
            f"{result['scenario']:>12}: "
            f"{format_strategy_counts(result['max_open_by_strategy'])}"
        )


if __name__ == '__main__':
    main()
