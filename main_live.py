"""
Live trading entry point.

Requires:
- Windows environment with MetaTrader5 installed and running.
- A .env file at the project root with MT5_LOGIN, MT5_PASSWORD, MT5_SERVER.

To add or remove strategies, edit the 'strategies' list in main() below.
"""

import os
import time
import logging
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv

from engine import EventEngine
from risk.risk_manager import RiskManager
from portfolio.portfolio_manager import PortfolioManager
from execution.mt5_execution import MT5Execution
from utils.trade_logger import TradeLogger
from data.mt5_data import connect, disconnect, reconnect, get_latest_completed_bar, get_recent_bars
from strategies.ema_fib_retracement import EmaFibRetracementStrategy

from utils.telegram_notifier import TelegramNotifier
import config

HEARTBEAT_HOUR = 8  # 8am UTC+2
HEARTBEAT_TZ = timezone(timedelta(hours=2))

os.makedirs('logs', exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s  %(name)s — %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/trading.log'),
    ],
)
logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 5


def main():
    load_dotenv()
    config.validate()

    login    = int(os.environ['MT5_LOGIN'])
    password = os.environ['MT5_PASSWORD']
    server   = os.environ['MT5_SERVER']

    if not connect(login, password, server):
        logger.error("Could not connect to MT5 — aborting")
        return

    try:
        execution    = MT5Execution()
        portfolio    = PortfolioManager()
        trade_logger = TradeLogger()
        risk         = RiskManager(
            account_balance_fn=execution.get_account_balance,
        )

        notifier = TelegramNotifier()

        event_engine = EventEngine(
            risk_manager=risk,
            portfolio_manager=portfolio,
            execution=execution,
            trade_logger=trade_logger,
            notifier=notifier,
        )

        # ── Register strategies ───────────────────────────────────────────────
        # Add or remove strategies here. Each strategy is registered against
        # the full symbol list, but will only fire when its declared timeframes
        # produce a new completed bar.
        strategies = [
            EmaFibRetracementStrategy(
                fib_entry=0.786,
                fib_tp=3.0,
                fractal_n=3,
                min_swing_pips=10,
                ema_sep_pct=0.001,
                cooldown_bars=10,
                invalidate_swing_on_loss=True,
                blocked_hours=(*range(20, 24), *range(0, 9)),  # allow 09:00-19:00 UTC (London + early NY)
            ),
        ]
        for strategy in strategies:
            event_engine.register(strategy, config.SYMBOLS)

        # ── Bar-detection state ───────────────────────────────────────────────
        # Tracks the timestamp of the last processed bar per (symbol, timeframe).
        last_bar_time: dict[tuple[str, str], datetime] = {}
        subscribed_pairs = event_engine.get_subscribed_pairs()

        # ── Warm-up: feed historical bars so EMAs/ATR/fractals are seeded ────
        # D1 needs ~50 bars for EMA(20) + ATR(14) with margin.
        # H4/H1 need ~100 bars for fractal window + swing detection.
        # M15 needs ~200 bars for fractal window + swing detection on faster TF.
        WARMUP_BARS = {'D1': 50, 'H4': 100, 'H1': 100, 'M15': 200}
        logger.info("Warming up strategy state with historical bars...")
        warmup_count = 0
        # Sort so higher TFs come first — strategies need bias seeded before entry TF
        TF_ORDER = {'D1': 0, 'H4': 1, 'H1': 2, 'M15': 3, 'M5': 4}
        warmup_pairs = sorted(subscribed_pairs, key=lambda p: (p[0], TF_ORDER.get(p[1], 99)))
        for symbol, timeframe in warmup_pairs:
            count = WARMUP_BARS.get(timeframe, 50)
            bars = get_recent_bars(symbol, timeframe, count)
            for bar in bars:
                event_engine.warmup_bar(bar)
                warmup_count += 1
            if bars:
                # Set last_bar_time so the poll loop doesn't re-process the last bar
                last_bar_time[(symbol, timeframe)] = bars[-1].timestamp
        logger.info(f"Warm-up complete: {warmup_count} bars processed across {len(subscribed_pairs)} pairs")

        logger.info(f"Live trading started — watching {len(subscribed_pairs)} symbol/timeframe pairs")
        notifier.notify_started(config.SYMBOLS, [s.NAME for s in strategies])

        consecutive_failures = 0
        last_heartbeat_date = None
        tracked_tickets: dict[int, dict] = {}  # ticket -> position info

        while True:
            # Daily heartbeat at 8am UTC+2
            now_local = datetime.now(HEARTBEAT_TZ)
            if now_local.hour >= HEARTBEAT_HOUR and last_heartbeat_date != now_local.date():
                last_heartbeat_date = now_local.date()
                notifier.notify_heartbeat(
                    balance=execution.get_account_balance(),
                    open_positions=len(execution.get_open_positions()),
                )

            try:
                # Detect closed trades by comparing tracked tickets to current positions
                current_positions = execution.get_open_positions()
                current_tickets = {p['ticket'] for p in current_positions}
                for ticket, pos in list(tracked_tickets.items()):
                    if ticket not in current_tickets:
                        # Position closed (SL/TP hit on broker side)
                        del tracked_tickets[ticket]
                        pnl = pos.get('profit', 0.0)
                        result = 'WIN' if pnl > 0 else ('BE' if pnl == 0 else 'LOSS')
                        strategy_name = pos.get('comment', 'unknown')
                        logger.info(
                            f"Trade closed by broker: {pos['symbol']} {pos['direction']} "
                            f"ticket={ticket} result={result} pnl={pnl:.2f}"
                        )
                        notifier.notify_order_closed(
                            symbol=pos['symbol'],
                            direction=pos['direction'],
                            result=result,
                            r_multiple=0.0,
                            pnl=pnl,
                            strategy=strategy_name,
                        )
                        portfolio.record_close(pos['symbol'], pnl)
                        event_engine.notify_trade_closed({
                            'symbol':        pos['symbol'],
                            'strategy_name': strategy_name,
                            'result':        result,
                        })
                # Update tracked positions with latest profit values
                for p in current_positions:
                    tracked_tickets[p['ticket']] = p

                for symbol, timeframe in subscribed_pairs:
                    bar = get_latest_completed_bar(symbol, timeframe)
                    if bar is None:
                        continue

                    key = (symbol, timeframe)
                    if last_bar_time.get(key) == bar.timestamp:
                        continue  # No new completed bar yet

                    last_bar_time[key] = bar.timestamp
                    logger.info(f"New bar: {symbol} {timeframe} @ {bar.timestamp}  O={bar.open} H={bar.high} L={bar.low} C={bar.close}")
                    event_engine.process_bar(bar)

                    # Log strategy status after each D1 bar (daily diagnostic)
                    if timeframe == 'D1':
                        for strat in strategies:
                            if hasattr(strat, 'get_status'):
                                status = strat.get_status(symbol)
                                logger.info(
                                    f"Status {symbol}: D1={status['d1_bias']} H1={status['h1_bias']} "
                                    f"ATR={status['atr_pips']}p EMA_sep={status['ema_sep']} "
                                    f"swing={status['swing']} ({status['swing_pips']}p age {status['swing_age']}) "
                                    f"→ {status['blocker']}"
                                )

                consecutive_failures = 0
            except Exception:
                consecutive_failures += 1
                logger.exception(f"Error in poll loop (failure #{consecutive_failures})")
                if consecutive_failures >= 3:
                    logger.warning("Multiple consecutive failures — attempting MT5 reconnect")
                    if not reconnect():
                        logger.error("Reconnect failed — shutting down")
                        return
                    consecutive_failures = 0

            time.sleep(POLL_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        logger.info("Shutdown requested by user")
    except Exception:
        logger.exception("Unexpected error in main loop")
    finally:
        disconnect()


if __name__ == '__main__':
    main()
