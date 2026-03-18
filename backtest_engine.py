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

import config
from engine import EventEngine
from risk.risk_manager import RiskManager
from portfolio.portfolio_manager import PortfolioManager
from execution.simulated_execution import SimulatedExecution
from utils.trade_logger import TradeLogger
from data.historical_loader import load_csv, load_and_merge
from data.news_filter import NewsFilter

logger = logging.getLogger(__name__)


class BacktestEngine:

    def __init__(
        self,
        initial_balance: float = 10_000.0,
        rr_ratio: float | None = None,
        spread_pips: float = config.BACKTEST_SPREAD_PIPS,
        breakeven_at_r: float | None = None,
        news_filter: NewsFilter | None = None,
        risk_pct_overrides: dict[str, float] | None = None,
    ):
        config.validate()
        self.execution = SimulatedExecution(
            initial_balance, spread_pips=spread_pips, breakeven_at_r=breakeven_at_r,
            rr_ratio=rr_ratio or config.DEFAULT_RR_RATIO,
        )
        self.portfolio = PortfolioManager()
        self.trade_logger = TradeLogger(initial_balance=initial_balance)
        self.risk = RiskManager(
            account_balance_fn=self.execution.get_account_balance,
            rr_ratio=rr_ratio,
            risk_pct_overrides=risk_pct_overrides,
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

    def run(self, csv_paths: str | list[str]):
        """
        Run the backtest.

        csv_paths: a single CSV filepath or a list of CSV filepaths.
        When multiple files are provided, bars are merged and replayed in
        chronological order (correct for multi-symbol / multi-timeframe testing).
        """
        if isinstance(csv_paths, str):
            bars = load_csv(csv_paths)
        else:
            bars = load_and_merge(csv_paths)

        logger.info(f"Backtest starting — {len(bars)} bars total")

        for bar in bars:
            # 1. Check if any open positions closed this bar (SL/TP hit)
            closed_trades = self.execution.check_fills(bar)
            for trade in closed_trades:
                self.portfolio.record_close(trade['symbol'], trade['pnl'])
                self.trade_logger.log_close(trade['ticket'], trade)
                self.event_engine.notify_trade_closed(trade)

            # 2. Process strategies (daily loss check is inside event_engine.process_bar)
            self.event_engine.process_bar(bar)

        logger.info("Backtest complete")
        self.trade_logger.print_trade_log()
        self.trade_logger.print_summary()
        self.trade_logger.plot_equity_curve()
