# AGENTS.md

Codex-facing project guide for this repo. Treat this file as authoritative for agent work. `CLAUDE.md` and `.claude/` are historical context only.

## Project Snapshot

Python FX/CFD trading bot for CSV backtesting and MT5 live/demo execution. The system is synchronous and event driven: bars feed strategies, strategies emit signals, risk sizes trades and sets TP when needed, portfolio applies limits, execution places or simulates orders, and logging records results.

Primary work is strategy development, data gathering, backtesting, parameter sweeps, walk-forward validation, and promoting validated strategies to demo/live.

## Runtime And Platform

- Python 3.10+ for backtesting on Linux.
- Live trading requires Windows with MetaTrader 5 and the `MetaTrader5` Python package.
- Credentials live in a gitignored root `.env`: `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
- All code and strategy logic should use UTC timestamps.
- Keep sweep/walk-forward worker count at `1` by default; higher parallelism has previously hung the user's PC.

## Source Of Truth

- `config.py` - global symbols, risk, pip sizes/values, spreads, commission, magic numbers.
- `live_config.py` - current live/demo strategy suite, symbols, params, and risk overrides.
- `main_live.py` - Windows/MT5 live trading entry point.
- `run_backtest.py` - single backtest entry point and strategy registry.
- `walk_forward.py` - rolling train/test validation configs.
- `backtest_engine.py` - CSV bar replay through the full pipeline.
- `data/historical_loader.py` - CSV discovery/loading/timezone handling.
- `execution/simulated_execution.py` - backtest fills, spread, commission, closed trades.
- `execution/mt5_execution.py` - MT5 live orders and open-position/order inspection.
- `risk/risk_manager.py` - SL validation, lot sizing, TP calculation.
- `portfolio/portfolio_manager.py` - per `(symbol, strategy_name)` position tracking and limits.
- `strategies/*.py` - pure signal generators.
- `strategy_log/*.md` - durable strategy status, sweep results, WF history, and decisions.

Before changing live status, live params, or risk, check `live_config.py`, the relevant `strategy_log/` file, `strategy_log/live_demo_audit.md`, and recent git diff.

## Core Design Rules

- No asyncio. Keep the event flow synchronous unless the user explicitly agrees to an architecture change.
- Strategies are pure signal generators. They should import `Signal`/`BarEvent` from `models` and must not import execution, risk, portfolio, data, or config modules.
- Every non-`CANCEL` signal must set `stop_loss`; the risk manager rejects missing SL.
- Never allow R:R below `1.0`; `1:1` is the minimum acceptable reward/risk.
- Strategies may set `take_profit`; otherwise the risk manager sets TP from configured R:R.
- Pending-order strategies may emit `direction='CANCEL'` to cancel unfilled orders. There is no `CLOSE` signal; filled trades run to SL or TP.
- One open position per `(symbol, strategy_name)` is allowed. Multiple strategies may hold concurrent positions on the same symbol.
- In backtests, fills occur at the next bar open. Avoid look-ahead bias; strategy rolling windows should normally evaluate against previous bars, then append the current bar.
- Backtest OHLC is treated as bid prices: BUY enters at ask and exits at bid; SELL enters at bid and exits/triggers SL/TP at ask.
- Do not hardcode credentials or broker secrets.

## New Strategy Workflow

1. Create `strategies/<name>.py` using existing strategies such as `strategies/ims.py` or `strategies/three_line_strike.py` as patterns.
2. Required strategy elements: `TIMEFRAMES`, `ORDER_TYPE`, `NAME`, constructor args for tuneable params, `reset(self)`, and `generate_signal(self, event)`.
3. Use per-symbol dictionaries for state because one strategy instance handles all symbols.
4. Register the strategy in `run_backtest.py` `STRATEGIES`.
5. Backtest with `python run_backtest.py <strategy>`.
6. Add or update sweep and walk-forward configs before treating params as validated.
7. Update `strategy_log/<name>.md` with results and verdict.
8. Register in `live_config.py` only after walk-forward is at least MODERATE and the user agrees.

## Validation Standards

- Walk-forward validation is the primary defence against curve-fitting.
- Default interpretation: `>=70%` OOS retention is STRONG, `40-70%` is MODERATE, `<40%` is WEAK/FAIL.
- Any new live candidate or material parameter change should pass walk-forward before live/demo promotion.
- When reporting strategy comparisons, include side-by-side metrics: trades, win rate, total R, profit factor, expectancy, max drawdown, and relevant streaks.
- The user values total R/account growth over per-trade expectancy when both choices are profitable, but risk should remain conservative.
- Test filters iteratively, one at a time, so the effect of each change is visible.

## Research Guardrails

- Break-even stops hurt EmaFib strategies and should not be reintroduced without new validation.
- Pending order age was not useful as a quality filter for EmaFibRetracement.
- Dynamic risk throttling after drawdown hurt low-win-rate, high-payout fib strategies.
- News filters did not improve current strategies.
- IMS Reversal drawdown-reduction attempts via ADX, efficiency ratio, circuit breaker, and tiered sizing were rejected; drawdown is managed through account sizing.

## Data Notes

- Historical data is stored under `data/historical/` with names like `<SYMBOL>_<TF>_<YYYYMMDD>-<YYYYMMDD>.csv`.
- Dukascopy data is preferred for long backtests and is natively UTC.
- HistData is available as a free second source via `fetch_data_histdata.py`; raw M1 ZIPs are stored under `data/raw/histdata/`, converted from New York local market time to UTC, resampled, and written to `data/historical/histdata/`. Use `--data-source histdata` in `run_backtest.py` and `walk_forward.py`.
- MT5 data requires Windows/VPS and is converted from broker server time to UTC before strategies see it.
- Backtest outputs and charts are written to `output/`.
- Live logs are under `logs/`.

## User Preferences

- Prefer concise, plain-language explanations and practical trade-offs.
- Show comparison tables for parameter choices instead of a single opaque recommendation.
- Consult before broad architecture changes, live deployment changes, or destructive cleanup.
- Keep risk defaults conservative: `RISK_PCT = 0.005` unless a per-strategy override is deliberately chosen.
- The user is comfortable with Python but is not a professional developer; explain quant ideas with concrete examples when needed.

## Working Notes For Codex

- Use `rg`/`rg --files` for search.
- Do not delete or rewrite Claude artifacts unless the user explicitly asks.
- Do not revert user changes in a dirty worktree.
- Use focused edits and follow existing local patterns.
- If inspecting demo/live logs, check for max-open-trade rejections, correlated USD drawdowns, IMS pending fill rate, daily loss limit events, and per-strategy trade counts versus expectation.
