"""
Backtesting engine.

Usage — single symbol:
    from backtest_engine import BacktestEngine
    from strategies.breakout import BreakoutStrategy

    engine = BacktestEngine(initial_balance=10000)
    engine.add_strategy(BreakoutStrategy(lookback=20), symbols=['EURUSD'])
    engine.run('data/historical/EURUSD_H1_20230101-20240101.csv')

Usage — multiple symbols / timeframes (bars merged by timestamp):
    engine.add_strategy(BreakoutStrategy(), symbols=['EURUSD', 'GBPUSD'])
    engine.run([
        'data/historical/EURUSD_H1_20230101-20240101.csv',
        'data/historical/GBPUSD_H1_20230101-20240101.csv',
    ])
"""

import logging
from types import SimpleNamespace

import config
from engine import EventEngine
from risk.risk_manager import RiskManager
from portfolio.portfolio_manager import PortfolioManager
from execution.simulated_execution import SimulatedExecution
from utils.trade_logger import TradeLogger
from datetime import datetime, timedelta
from data.historical_loader import load_csv, load_and_merge, bar_close_time
from data.news_filter import NewsFilter

logger = logging.getLogger(__name__)


class BacktestEngine:

    def __init__(
        self,
        initial_balance: float = 10_000.0,
        rr_ratio: float | None = None,
        spread_pips: dict[str, float] | float = config.BACKTEST_SPREAD_PIPS,
        breakeven_at_r: float | None = None,
        news_filter: NewsFilter | None = None,
        risk_pct_overrides: dict[str, float] | None = None,
        max_open_trades: int = 99,
        max_daily_loss_pct: float | None = None,
    ):
        config.validate()
        self.execution = SimulatedExecution(
            initial_balance, spread_pips=spread_pips, breakeven_at_r=breakeven_at_r,
            rr_ratio=rr_ratio or config.DEFAULT_RR_RATIO,
        )
        self.portfolio = PortfolioManager(
            max_open_trades=max_open_trades,
            max_daily_loss_pct=max_daily_loss_pct,
        )
        self.trade_logger = TradeLogger(initial_balance=initial_balance)
        self.risk = RiskManager(
            account_balance_fn=self.execution.get_account_balance,
            rr_ratio=rr_ratio,
            risk_pct_overrides=risk_pct_overrides,
            loss_per_lot_fn=self.execution.loss_per_lot,
        )
        self.event_engine = EventEngine(
            risk_manager=self.risk,
            portfolio_manager=self.portfolio,
            execution=self.execution,
            trade_logger=self.trade_logger,
            news_filter=news_filter,
        )

    def add_strategy(self, strategy, symbols: list[str]):
        """Register a strategy and the symbols it should run on."""
        self.event_engine.register(strategy, symbols)

    def replay(self, bars, start_date=None, end_date=None):
        """Shared synchronous replay; prior completed bars warm state without orders.

        Open exposure at the end remains open and is reported separately. No
        synthetic liquidation or future bars enter the closed-trade metrics.
        """
        self.execution.configure_timeframes(bars)
        for bar in bars:
            close_time = bar_close_time(bar)
            if end_date is not None and close_time > end_date:
                continue
            if start_date is not None and close_time <= start_date:
                self.event_engine.warmup_bar(bar)
                continue
            self.process_bar(bar)
        return self.execution.get_closed_trades()

    def process_bar(self, bar):
        """One replay step. Advance the risk day before applying realized losses."""
        self.portfolio.set_current_date(bar_close_time(bar).date())
        closed = self.execution.check_fills(bar)
        for trade in closed:
            self.portfolio.record_close(trade['symbol'], trade['pnl'], trade.get('strategy_name', ''),
                                        close_time=trade['close_time'])
            self.trade_logger.log_close(trade['ticket'], trade)
            self.event_engine.notify_trade_closed(trade)
        for rejected in self.execution.take_rejected_orders():
            self.portfolio.record_close(rejected['symbol'], 0.0, rejected['strategy_name'])
            self.trade_logger.discard_unfilled(rejected['ticket'])
            self.event_engine.reject_signal(SimpleNamespace(**rejected))
        self.event_engine.process_bar(bar)
        return closed

    def run(self, csv_paths: str | list[str],
            start_date: datetime | None = None,
            end_date: datetime | None = None):
        """
        Run the backtest.

        csv_paths: a single CSV filepath or a list of CSV filepaths.
        When multiple files are provided, bars are merged and replayed in
        chronological order (correct for multi-symbol / multi-timeframe testing).
        start_date / end_date: optional date range filter [start, end).
        """
        load_start = start_date - timedelta(days=180) if start_date else None
        if isinstance(csv_paths, str):
            bars = load_csv(csv_paths, start=load_start, end=end_date)
        else:
            bars = load_and_merge(csv_paths, start=load_start, end=end_date)

        logger.info(f"Backtest starting — {len(bars)} bars total")

        self.replay(bars, start_date=start_date, end_date=end_date)

        logger.info("Backtest complete")
        self.trade_logger.print_trade_log()
        self.trade_logger.print_summary()
        logger.info('Ending open exposure: %s; equity %.2f; marked-to-market drawdown %.2f%%',
                    len(self.execution.get_open_positions()), self.execution.get_equity(),
                    self.execution.max_equity_drawdown_pct)
        self.trade_logger.plot_equity_curve()
