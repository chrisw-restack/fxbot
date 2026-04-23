# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

Python FX trading bot — core system stable. All layers (data, strategy, risk, portfolio, execution, logging) are implemented and tested. Day-to-day work is developing new strategies, gathering data, backtesting, and promoting profitable strategies to live. See "Creating a New Strategy" below for the full workflow.

## Architecture Summary

Synchronous, event-driven, modular system. All layers communicate via synchronous event dispatch (direct method calls, no queue). No asyncio.

```
MT5 / CSV → Event Generator → Strategies
                                         ↓ Signal
                                   Risk Manager (lot size, TP)
                                         ↓
                                 Portfolio Manager (conflict check, limits)
                                         ↓
                                 Execution (MT5 live | simulated backtest)
                                         ↓
                                   Trade Logger
```

## Layer Map

| Module | Path | Role |
|--------|------|------|
| Config | `config.py` | All global parameters |
| Live engine | `main_live.py` | Entry point for live trading |
| Backtest engine | `backtest_engine.py` | Bar-by-bar CSV replay |
| Data (live) | `data/mt5_data.py` | Polls MT5 per symbol/timeframe |
| Data (backtest) | `data/historical_loader.py` | Reads CSVs from `data/historical/` |
| Strategies | `strategies/*.py` | Signal generation only |
| Execution base | `execution/base_execution.py` | Shared interface (ABC) |
| Live execution | `execution/mt5_execution.py` | MT5 API orders |
| Sim execution | `execution/simulated_execution.py` | Backtest fill simulation |
| Risk | `risk/risk_manager.py` | Lot sizing + TP calculation |
| Portfolio | `portfolio/portfolio_manager.py` | Position tracking + limits |
| Logger | `utils/trade_logger.py` | Trade log + backtest metrics + charts |
| Notifications | `utils/telegram_notifier.py` | Telegram alerts (live trading) |
| Param sweep | `param_sweep.py` | Parameter optimization runner |
| Walk-forward | `walk_forward.py` | Walk-forward validation (rolling train/test) |
| Dukascopy fetch | `fetch_data_dukascopy.py` | Download historical data from Dukascopy (any TF) |
| News data fetch | `fetch_news_data.py` | Download Forex Factory calendar from Hugging Face |
| News filter | `data/news_filter.py` | Block signals near high-impact news events |
| Spread monitor | `measure_spreads.py` | Poll live MT5 bid/ask to measure real spreads (run on VPS) |

## Key Design Rules

- **Strategies are pure signal generators**: `strategies/*.py` must never import from `execution/`, `risk/`, `portfolio/`, or `data/`. They receive a `BarEvent` and return a `Signal` or `None`.
- **Stop-loss is always set by the strategy**: the risk manager never guesses or defaults the SL. If a signal has no SL, it is rejected.
- **Take-profit defaults to the risk manager**: `entry ± (SL distance × R:R ratio)`. Strategies may optionally set `take_profit` on the Signal to override this (e.g. for fibonacci extension targets).
- **Execution is interchangeable**: `mt5_execution.py` and `simulated_execution.py` both inherit `BaseExecution`. Strategy/risk code is identical for live and backtest.
- **CANCEL signals**: strategies with PENDING orders can emit `direction='CANCEL'` to cancel unfilled pending orders (e.g. when bias flips). The engine handles cancellation via `_handle_cancel()`.
- **No CLOSE signals**: trades always run to SL or TP. There is no mechanism to manually close a filled position from strategy code.
- **One position per symbol per strategy**: the portfolio manager keys by `(symbol, strategy_name)` — multiple strategies can hold concurrent positions on the same symbol independently.

## Core Data Structures

```python
@dataclass
class BarEvent:
    symbol: str        # 'EURUSD'
    timeframe: str     # 'M5' | 'M15' | 'H1' | 'H4' | 'D1'
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

@dataclass
class Signal:
    symbol: str
    direction: str      # 'BUY' | 'SELL' | 'CANCEL'
    order_type: str     # 'MARKET' | 'PENDING'
    entry_price: float  # current price (MARKET) or specific level (PENDING)
    stop_loss: float    # price level, set by strategy
    strategy_name: str
    timestamp: datetime
    take_profit: float | None = None  # optional — if set, overrides risk manager TP
    entry_timeframe: str | None = None  # auto-set by engine from the bar that generated the signal
# Risk manager adds: lot_size, take_profit (if not already set) before passing to execution
```

## Creating a New Strategy

### Step 1: Create the strategy file

Create `strategies/<strategy_name>.py`. Read an existing strategy (e.g. `strategies/ims.py` or `strategies/three_line_strike.py`) for the full pattern. Required elements:

- `TIMEFRAMES` class attr — engine uses this to subscribe the strategy to the correct bar feed
- `ORDER_TYPE` class attr — `'MARKET'` or `'PENDING'`
- `NAME` class attr — unique string, appears in logs and backtest output
- `__init__` with all tuneable params as constructor args
- `reset(self)` — clears all internal state; called before each backtest run
- `generate_signal(self, event: BarEvent) -> Signal | None` — the only method the engine calls
- Per-symbol state via dicts (one instance handles all symbols; key by `event.symbol`)
- `notify_loss(self, symbol)` (optional) — called by engine on loss close; use for cooldowns

### Rules strategies must follow

1. **Only import from `models`** — never from `execution/`, `risk/`, `portfolio/`, `data/`, or `config`.
2. **Set `stop_loss` on every Signal** — risk manager rejects signals without one. Min SL is `config.MIN_SL_PIPS` (default 5).
3. **CANCEL signals for pending orders** — return `direction='CANCEL'` to cancel unfilled orders when bias flips. Never emit CLOSE.
4. **Suppress re-entry in the same direction** — track `_last_direction[symbol]` and only fire on direction change.
5. **Append current bar AFTER checking conditions** — window holds previous N bars, not the current one (avoids look-ahead bias).
6. **Use `event.close` as `entry_price` for MARKET orders** — sim fills at next bar's open; this is just a reference price.
7. **For PENDING orders**, set `entry_price` to the desired fill level. Execution infers subtype (Buy Stop/Limit etc.) automatically.

### Step 2: Register in `run_backtest.py`

Add an import and entry in the `STRATEGIES` dict, then run: `python run_backtest.py my_strategy`

### Step 3: Register in `main_live.py` (when ready for live)

Add import, instantiate with validated params, append to `strategies` list, call `event_engine.register(strategy, SYMBOLS)`.

### Multi-symbol / Multi-timeframe

- Multi-symbol: edit `SYMBOLS` in `run_backtest.py`. Strategy receives bars for all symbols and tracks state per symbol via dicts.
- Multi-timeframe: set `TIMEFRAMES = ['H1', 'H4']`. Distinguish timeframes via `event.timeframe` inside `generate_signal`.

### Data for backtesting

**Dukascopy** (10+ years, runs anywhere): `pip install dukascopy-python`, edit `fetch_data_dukascopy.py`, run it.
**MT5** (recent data, requires VPS): run `python fetch_data.py` on VPS, copy CSVs to `data/historical/`.
Both output to `data/historical/<SYMBOL>_<TF>_<YYYYMMDD>-<YYYYMMDD>.csv`. The loader auto-detects source and handles timezone conversion.

## Risk Manager Logic

1. Validate signal has a stop-loss price; reject if missing.
2. Calculate SL distance in pips from `entry_price` to `stop_loss`.
3. Lot size: `DYNAMIC` = `(balance × risk_pct) ÷ (sl_pips × pip_value)`; `FIXED` = `config.FIXED_LOT_SIZE`.
4. Take-profit: use `signal.take_profit` if set, otherwise `entry ± (sl_distance × rr_ratio)`.
5. Return enriched signal to portfolio manager.

## Portfolio Manager Logic

On each incoming signal:
1. Check if **(symbol, strategy_name)** already has an open position → block if yes.
2. Check if `open_trade_count >= MAX_OPEN_TRADES` (default 6) → block if yes.
3. Check if daily loss has exceeded `MAX_DAILY_LOSS_PCT` (default 2%) → block if yes.

`record_close(symbol, pnl, strategy_name)` requires `strategy_name` to identify the correct slot.

**Backtest behaviour**: `BacktestEngine` uses `PortfolioManager(max_open_trades=99, max_daily_loss_pct=None)` — both limits disabled to prevent trade-ordering artifacts skewing multi-symbol results.

## Execution Interface

```python
class BaseExecution(ABC):
    def place_order(self, symbol, direction, order_type, entry_price,
                    lot_size, sl, tp, strategy_name) -> int: ...  # returns ticket ID
    def close_order(self, ticket_id) -> bool: ...
    def get_open_positions(self) -> list[dict]: ...
```

Simulated execution fills at the **open of the next bar**. For PENDING orders, subtype is inferred: BUY+entry>current = Buy Stop, BUY+entry<current = Buy Limit, etc.

**MT5 magic numbers**: every order is tagged with a per-strategy integer from `config.MAGIC_NUMBERS`. `get_open_positions` filters to only positions/orders whose magic is in the known set — manual trades are invisible to the bot.

## Config Parameters (`config.py`)

Key values: `RISK_PCT = 0.005` (0.5%/trade), `MAX_OPEN_TRADES = 6`, `MAX_DAILY_LOSS_PCT = 0.02`.
Magic numbers: EmaFibRetracement=1001, EmaFibRunning=1002, Engulfing=1003, IMS_H4_M15=1004, IMSRev_H4_M15=1005.
Pip sizes and pip values for all instruments (XAUUSD, US30, US500, USTEC, DE40 included) are in `config.PIP_SIZE` and `config.PIP_VALUE_USD`. Add new instruments there before backtesting.
Per-strategy risk overrides: `risk_pct_overrides` dict in `RiskManager`. EmaFibRetracement uses 0.7%; others use 0.5%.

## Live Trading

Run on Windows VPS with MT5 installed: `python main_live.py`

- Polls MT5 every 5 seconds for new completed bars
- Detects trade closures (SL/TP hit) by comparing tracked tickets to open positions
- Telegram notifications: startup, order placed, order closed, daily heartbeat (8am UTC+2)
- File logging to `logs/trading.log` (rolled over on each startup)
- Auto-reconnect on MT5 connection failures (3 consecutive failures triggers reconnect)

## Credentials

`.env` file at project root (gitignored): `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. Loaded via `python-dotenv` in `main_live.py`. Never hardcode.

## Timezone Standardisation

All timestamps throughout the system are **UTC**.

- **MT5 data**: saved in ICMarkets server time (UTC+2/+3). Historical loader auto-detects and converts to UTC.
- **Dukascopy data**: natively UTC. Loader auto-detects (checks for Sunday bars) and skips conversion.
- **Live feed**: uses `datetime.utcfromtimestamp()`.

## Historical CSV Format

Path: `data/historical/<SYMBOL>_<TF>_<YYYYMMDD>-<YYYYMMDD>.csv`
Columns: `time, open, high, low, close, tick_volume` (MT5) or `time, open, high, low, close, volume` (Dukascopy)

## Backtest Output

**Performance summary**: total trades, win rate, total R, profit factor, max drawdown (R and %), expectancy, best/worst streaks, avg R on wins/losses.

**Charts** (saved to `output/`): equity curve, monthly Total R heatmap, yearly performance heatmap.

**Closed trade dict** (from `engine.execution.get_closed_trades()`): `ticket, symbol, direction, strategy_name, entry_price, exit_price, sl, tp, sl_pips, result, r_multiple, pnl, commission, lot_size, open_time, close_time, duration_hours, pending_hours`.

## Platform

- `MetaTrader5` package is **Windows only**. Live trading requires a Windows VPS with MT5 installed.
- Backtesting (CSV-based) is cross-platform. Python 3.10+.

## Parameter Optimization

`param_sweep.py` — grid search, pre-loads bar data once, runs all combos. Edit `PARAM_GRID` and run: `python param_sweep.py`. Outputs ranked tables by Total R, Expectancy, and Profit Factor.

## Walk-Forward Validation

Primary defence against overfitting. Run: `python walk_forward.py <strategy_name>`

**CLI options**: `--train-years` (default 4), `--test-years` (default 2), `--step-years` (default 2), `--metric {expectancy,total_r,pf}` (default expectancy), `--min-trades` (default 50 — raise to 100+ for sparse strategies), `--workers` (default 1).

**`rr_ratio` in param grids**: add `'rr_ratio': [2.0, 2.5]` to sweep R:R; it's extracted and forwarded to BacktestEngine automatically.

**OOS retention** (OOS expectancy ÷ IS expectancy): >70% = STRONG, 40–70% = MODERATE, <40% = WEAK/FAIL.

**Date filtering**: `filter_bars(bars, start, end)` in `data/historical_loader.py` slices pre-loaded bars to any date range.

## Live Suite

5 strategies in demo (`main_live.py`). Each strategy gets its own position slot per symbol — concurrent positions across strategies are allowed.

| Strategy | Timeframes | Order Type | Symbols | Key Params |
|----------|-----------|------------|---------|------------|
| EmaFibRetracement | D1, H1 | PENDING | 7 pairs | fib_entry=0.786, fib_tp=3.0, fractal_n=3, min_swing=10, ema_sep=0.001, cooldown=10, invalidate=True, blocked_hours=(20-23, 0-8) |
| EmaFibRunning | D1, H1 | PENDING | 7 pairs | fib_entry=0.786, fib_tp=2.5, fractal_n=2, min_swing=30, ema_sep=0.0, cooldown=0, invalidate=True, blocked_hours=(20-23, 0-8) |
| Engulfing | M5 | MARKET | 3 pairs | fractal_n=3, min_body=3.0, engulf_ratio=1.5, max_sl=15, NY session (13-17 UTC), sma_sep=5.0, rr=2.5 |
| IMS | H4, M15 | PENDING | 9 pairs | fractal_n=1, ltf_fractal_n=1, htf_lookback=30, rr=2.5, ema_fast=20, ema_slow=50, ema_sep=0.001, sl_anchor=swing, session=12-17 UTC |
| IMS Reversal | H4, M15 | PENDING | 8 pairs | fractal_n=1, ltf_fractal_n=2, htf_lookback=30, tp=htf_pct 0.5, max_losses_per_bias=1, ema_fast=20, ema_slow=50, ema_sep=0.001, session=12-17 UTC |

Backtest commands: `python run_backtest.py ema_fib_retracement` / `ema_fib_running` / `three_line_strike` / `ims_h4_m15` / `ims_reversal_best`

MAX_OPEN_TRADES=6 — with 5 strategies monitor peak concurrent positions. IMS Reversal MT5 symbol: US30 (backtest data used USA30 Dukascopy label — verify on broker if needed).

**Needs more data (not live):**
- **EBP** (H1/M15) — INCONCLUSIVE: +0.460R IS, PF 1.86. WF WEAK — fold 3 OOS fails. Needs 50+ demo trades. See `strategy_log/ebp.md`.
- **HourlyMeanReversion** (M5, XAUUSD) — MODERATE: folds 2&3 positive, fold 1 fails (pre-2020 regime). Too sparse (~2–5 trades/yr). M1 fully shelved. See `strategy_log/hourly_mean_reversion.md`.

**Suspended / shelved** (see individual strategy logs for full history):
- TheStrat — WF FAIL after fill-bug fix
- EBP Limit — WF FAIL, regime-dependent
- Breakout — WF FAIL, no H1 edge
- GaussianChannel — WF WEAK, warm-up bug fixed
- EmaFibRetracementIntraday — WF FAIL, curve-fit
- MeanReversion — all sweep combos negative
- KeltnerReversion — WF FAIL, fold 3 collapse
- RangeFade — 56 trades/10yr, not viable
- SupplyDemand — WF MODERATE but fold 1 negative, only 150 OOS trades
- IctJudasSwing — all 108 combos negative
- SmcZone — 11 trades/yr, too sparse for WF
- BigBelugaSd — WR 33.4%, ~0R expectancy
- SmcReversal — WF FAIL, regime-dependent (COVID/rate-hike collapse)

**Strategy logs**: `strategy_log/` — one `.md` per strategy with full parameter, sweep, and walk-forward history.

## News Filter

Optional, integrated into `engine.py`. Data: Forex Factory calendar via `python fetch_news_data.py`.

**Modes**: `off` (default), `high` (all high-impact), `high-medium`, `major` (NFP/CPI/FOMC/rates only).

**CLI usage**: `python run_backtest.py ema_fib_retracement --news-filter high --news-hours-before 4 --news-hours-after 1`

**Live trading**: pass a `NewsFilter` instance to `EventEngine` via the `news_filter` parameter.

## Important Notes

- **USDJPY pip size is 0.01** (not 0.0001). Strategies doing pip calculations internally must pass a `pip_sizes` dict.
- **ImsStrategy SL anchor**: `'swing'` (wick), `'body'` (open/close min), `'fvg'` (bottom of lowest LTF FVG). WF validated `swing` with no buffer — body and FVG fail OOS.
- **Backtest spread is 2.0 pips** — conservative. ICMarkets Raw actual is 0.1–0.5 pips on majors during London/NY. Real performance is understated by ~1 pip/trade.
- **Commission is $7.00/lot round-trip** (ICMarkets Raw Spread) — deducted at close in backtesting.
- **Break-even stop** (`--breakeven-at-r N`): tested 2–10R for EmaFibRetracement — all levels hurt performance. Large wins require price to briefly retrace through the trigger. Do not use for fib retracement strategies.

## Future Work
- Currency exposure limits (max positions per currency to reduce correlation risk)
- Drawdown throttle (reduce position size after X% peak-to-trough decline) — modelled for IMS Reversal (tiered 20R/35R): −6.8pp DD at cost of −16% return; rejected for now
- Variable spread model (wider spreads during news/low-liquidity sessions)
- Additional strategy development (mean-reversion, different asset classes)
