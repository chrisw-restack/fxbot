# AGENTS.md

Codex-facing project guide for this repo. Treat this file as authoritative for agent work. `CLAUDE.md` and `.claude/` are retained as historical context only.

## Project Snapshot

Python FX/CFD trading bot for backtesting and MT5 live/demo execution. The system is synchronous and event driven: bars feed strategies, strategies emit signals, risk sizes trades and sets TP when needed, portfolio applies limits, execution places or simulates orders, and logging records results.

Primary day-to-day work is strategy development, data gathering, backtesting, parameter sweeps, walk-forward validation, and promoting validated strategies to demo/live.

## Runtime And Platform

- Python 3.10+ for backtesting on Linux.
- Live trading requires Windows with MetaTrader 5 and the `MetaTrader5` Python package.
- Credentials live in `.env` at repo root and are gitignored: `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
- All timestamps should be UTC throughout the codebase.
- Default sweep/walk-forward worker count should stay at `1`; higher parallelism has previously hung the user’s PC.

## Key Files

- `config.py` - global symbols, risk, pip sizes/values, spreads, commission, magic numbers.
- `main_live.py` - Windows/MT5 live trading entry point.
- `run_backtest.py` - single backtest entry point and strategy registry.
- `backtest_engine.py` - CSV bar replay through the full pipeline.
- `walk_forward.py` - rolling train/test validation.
- `data/historical_loader.py` - CSV discovery/loading/timezone handling.
- `execution/simulated_execution.py` - backtest fills, spread, commission, closed trades.
- `execution/mt5_execution.py` - MT5 live orders and open-position/order inspection.
- `risk/risk_manager.py` - SL validation, lot sizing, TP calculation.
- `portfolio/portfolio_manager.py` - per `(symbol, strategy_name)` position tracking and limits.
- `strategies/*.py` - pure signal generators.
- `strategy_log/*.md` - durable strategy status, sweep results, WF history, and decisions.

## Core Design Rules

- No asyncio. Keep the event flow synchronous unless the user explicitly agrees to an architecture change.
- Strategies are pure signal generators. They should import `Signal`/`BarEvent` from `models` and must not import execution, risk, portfolio, data, or config modules.
- Every non-`CANCEL` signal must set `stop_loss`. The risk manager rejects missing SL.
- Never allow R:R below `1.0`; `1:1` is the minimum acceptable reward/risk.
- Strategies may set `take_profit`; otherwise the risk manager sets TP from configured R:R.
- Pending-order strategies may emit `direction='CANCEL'` to cancel unfilled orders. There is no `CLOSE` signal; filled trades run to SL or TP.
- One open position per `(symbol, strategy_name)` is allowed. Multiple strategies may hold concurrent positions on the same symbol.
- In backtests, fills occur at the next bar open. Avoid look-ahead bias; strategy rolling windows should normally evaluate against previous bars, then append the current bar.
- Do not hardcode credentials or broker secrets.

## New Strategy Workflow

1. Create `strategies/<name>.py` using existing strategies such as `strategies/ims.py` or `strategies/three_line_strike.py` as patterns.
2. Required strategy elements: `TIMEFRAMES`, `ORDER_TYPE`, `NAME`, constructor args for tuneable params, `reset(self)`, and `generate_signal(self, event)`.
3. Use per-symbol dictionaries for state because one strategy instance handles all symbols.
4. Register the strategy in `run_backtest.py` `STRATEGIES`.
5. Backtest with `python run_backtest.py <strategy>`.
6. Add or update sweep and walk-forward configs before treating params as validated.
7. Update `strategy_log/<name>.md` with results and verdict.
8. Register in `main_live.py` only after walk-forward is at least MODERATE and the user agrees.

## Validation Standards

- Walk-forward validation is the primary defence against curve-fitting.
- Default interpretation: `>=70%` OOS retention is STRONG, `40-70%` is MODERATE, `<40%` is WEAK/FAIL.
- Any new live candidate or material parameter change should pass walk-forward before live/demo promotion.
- When reporting strategy comparisons to the user, include side-by-side metrics: trades, win rate, total R, profit factor, expectancy, max drawdown, and relevant streaks.
- The user values total R/account growth over per-trade expectancy when both choices are profitable, but risk should remain conservative.
- Test filters iteratively, one at a time, so the effect of each change is visible.

## Current Live/Demo Suite Context

As of the imported Claude memory, demo/live code is built around five strategies:

- `EmaFibRetracement` - D1/H1 pending fib retracement on 7 FX pairs, WF MODERATE.
- `EmaFibRunning` - D1/H1 pending running variant on 7 FX pairs, WF STRONG/MODERATE depending on memory source; check `strategy_log/ema_fib_running.md` for latest.
- `Engulfing` / `ThreeLineStrikeStrategy` - M5 market strategy on EURUSD/AUDUSD/USDCAD, WF STRONG.
- `IMS_H4_M15` - H4/M15 pending IMS on 9 symbols including XAUUSD/crosses, WF MODERATE.
- `IMSRev_H4_M15` - H4/M15 reversal strategy on 8 symbols including XAUUSD/US30, WF STRONG.

Before changing live status or params, check `main_live.py`, `strategy_log/`, and recent git diff because the memory may lag the code.

## Known Project Decisions

- Portfolio slots are keyed by `(symbol, strategy_name)` to avoid one strategy suppressing another on the same symbol.
- Break-even stops hurt EmaFib strategies and should not be reintroduced without a new reason.
- Pending order age was not useful as a quality filter for EmaFibRetracement.
- Dynamic risk throttling after drawdown hurt low-win-rate, high-payout fib strategies.
- News filters did not improve current strategies.
- IMS Reversal drawdown reduction attempts via ADX, efficiency ratio, circuit breaker, and tiered sizing were rejected; drawdown is treated as structural and managed through account sizing.
- `.claude/commands/docs.md` describes the old end-of-session documentation routine; for Codex, update `strategy_log/` and `AGENTS.md`/Codex memory when decisions change.

## User Preferences

- Prefer concise, plain-language explanations and practical trade-offs.
- Show comparison tables for parameter choices instead of a single opaque recommendation.
- Consult before broad architecture changes, live deployment changes, or destructive cleanup.
- Keep risk defaults conservative: `RISK_PCT = 0.005` unless a per-strategy override is deliberately chosen.
- The user is comfortable with Python but is not a professional developer; explain quant ideas with concrete examples when needed.

## Local Data Notes

- Historical data is stored under `data/historical/` with names like `<SYMBOL>_<TF>_<YYYYMMDD>-<YYYYMMDD>.csv`.
- Dukascopy data is preferred for long backtests and is natively UTC.
- MT5 data requires Windows/VPS and is converted from broker server time to UTC by the loader.
- Backtest outputs and charts are written to `output/`.
- Live logs are under `logs/`.

## Working Notes For Codex

- Use `rg`/`rg --files` for search.
- Do not delete or rewrite Claude artifacts unless the user explicitly asks; they are historical context.
- Do not revert user changes in a dirty worktree.
- Use focused edits and follow existing local patterns.
- If inspecting logs from demo/live, check for max-open-trade rejections, correlated USD drawdowns, IMS pending fill rate, daily loss limit events, and per-strategy trade counts versus expectation.
