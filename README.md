# Python FX Trading Bot

## Overview

A **modular, event-driven Python trading bot** for FX and metals markets using **MetaTrader 5 (MT5)** for live execution. Designed for both live trading and backtesting, with full support for multiple strategies, symbols, timeframes, and risk configurations.

Key design principles:

- **Separation of responsibilities**: strategy, risk, execution, data, portfolio, and backtest layers are fully decoupled.
- **Event-driven, synchronous**: strategies respond to bar-close events via direct method calls (no asyncio, no queue overhead).
- **Reproducible backtesting**: historical data is stored locally as CSV and replayed bar-by-bar with next-bar fills — no look-ahead bias.
- **Walk-forward validated**: all strategies are tested via rolling train/test windows before going live.


## Directory Layout

```
fxbot/
│
├── .env                          # MT5 + Telegram credentials (gitignored)
├── config.py                     # Global parameters (symbols, risk, lot size, etc.)
├── main_live.py                  # Live trading engine entry point
├── backtest_engine.py            # Backtesting engine
├── run_backtest.py               # Run a single backtest by strategy name
├── param_sweep.py                # Grid search over strategy parameters
├── walk_forward.py               # Walk-forward validation (rolling train/test folds)
├── fetch_data_dukascopy.py       # Download historical data from Dukascopy (any TF)
├── fetch_data_histdata.py        # Download/convert free HistData M1 data
├── fetch_news_data.py            # Download Forex Factory calendar from Hugging Face
├── measure_spreads.py            # Poll live MT5 bid/ask to measure real spreads
│
├── data/
│   ├── mt5_data.py               # Fetch live bars from MT5
│   ├── historical_loader.py      # Load/merge/filter CSV historical data
│   ├── news_filter.py            # Block signals near high-impact news events
│   └── historical/               # CSVs: <SYMBOL>_<TF>_<YYYYMMDD>-<YYYYMMDD>.csv
│
├── strategies/
│   ├── ema_fib_retracement.py    # LIVE: D1/H1 EMA trend + fib entry
│   ├── ema_fib_running.py        # LIVE: D1/H1 EMA trend + fib entry (running variant)
│   ├── three_line_strike.py      # LIVE: M5 engulfing, NY session, 5 FX pairs
│   ├── ims.py                    # LIVE: H4/M15 ICT market structure (IMS), 9 pairs
│   ├── hourly_mean_reversion.py  # MODERATE (M5/XAUUSD): ICT power-of-3 mean-reversion
│   ├── ebp.py                    # INCONCLUSIVE: H1/M15 EBP structure
│   └── ...                       # Shelved strategies — see strategy_log/
│
├── execution/
│   ├── base_execution.py         # Abstract interface (place/close/query orders)
│   ├── mt5_execution.py          # Live execution via MT5 API
│   └── simulated_execution.py    # Simulated fills for backtests
│
├── risk/
│   └── risk_manager.py           # SL validation, lot sizing, TP calculation
│
├── portfolio/
│   └── portfolio_manager.py      # Position tracking, conflict blocking, limits
│
├── utils/
│   ├── trade_logger.py           # Trade log + metrics + equity/monthly charts
│   └── telegram_notifier.py      # Telegram alerts for live trading
│
└── strategy_log/                 # One .md per strategy: params, sweep, WF history
```


## Layer Responsibilities

| Layer | Responsibility |
|-------|----------------|
| **Data** | Fetch live or historical OHLC bars per symbol/timeframe. Store locally as CSV for reproducible backtests. Auto-detects MT5 vs Dukascopy format and converts to UTC. |
| **Strategy** | Generate `BUY`/`SELL` signals from bar events. Fully isolated — never touches execution, risk, portfolio, or data layers. |
| **Risk** | Validates the signal has a stop-loss, computes lot size (dynamic or fixed), and sets take-profit. |
| **Execution** | Places orders via MT5 (live) or simulates fills at next-bar open (backtest). Both implement the same `BaseExecution` interface. |
| **Portfolio** | Tracks open positions per (symbol, strategy) pair. Enforces conflict blocking, max open trades, and max daily loss. |
| **Backtest** | Replays CSVs bar-by-bar through the full pipeline. Produces trade log, performance summary, and equity/monthly charts. |


## Data & Signal Schemas

```python
@dataclass
class BarEvent:
    symbol: str        # 'EURUSD', 'XAUUSD', etc.
    timeframe: str     # 'M1' | 'M5' | 'M15' | 'H1' | 'H4' | 'D1'
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

@dataclass
class Signal:
    symbol: str
    direction: str          # 'BUY' | 'SELL' | 'CANCEL'
    order_type: str         # 'MARKET' | 'PENDING'
    entry_price: float      # current price (MARKET) or specific level (PENDING)
    stop_loss: float        # price level — always set by the strategy
    strategy_name: str
    timestamp: datetime
    take_profit: float | None = None      # optional — overrides risk manager TP
    entry_timeframe: str | None = None    # auto-set by engine from the triggering bar
```

- **Stop-loss** is always a price level set by the strategy. The risk manager rejects any signal without one.
- **Take-profit** defaults to `entry ± (SL distance × R:R ratio)`. Strategies may set it explicitly (e.g. for fibonacci extension targets).
- **CANCEL signals**: strategies with pending orders can emit `direction='CANCEL'` to cancel unfilled orders. There is no `CLOSE` signal — filled trades always run to SL or TP.


## Risk Management

### Lot Sizing Modes

| Mode | Behaviour |
|------|-----------|
| `DYNAMIC` | `(account balance × risk%) ÷ (SL distance pips × pip value)`. Default: 0.5% per trade. |
| `FIXED` | Fixed lot size (e.g. `0.01`) regardless of SL or balance. |

- **Commission**: $7.00 per lot round-trip (ICMarkets Raw Spread). Deducted from PnL at trade close.
- **Spread**: 2.0 pips (conservative average; actual ICMarkets Raw spreads are 0.1–0.5 pips during London/NY).
- **Minimum SL**: signals with SL < 5 pips are rejected.
- **Minimum R:R**: signals below 1.0 R:R are rejected.
- **Per-strategy overrides**: `risk_pct_overrides` dict in `RiskManager` (keyed by strategy NAME).


## Portfolio & Conflict Management

- **One position per (symbol, strategy) pair**: multiple strategies may hold concurrent positions on the same symbol independently.
- **Max open trades**: 8 total across all strategies (live). Disabled in backtesting (`max_open_trades=99`) to avoid ordering artifacts skewing multi-symbol evaluation.
- **Max daily loss**: 2% of account balance (live). Disabled in backtesting (`max_daily_loss_pct=None`) for the same reason.


## Historical Data

### Option A — Dukascopy (preferred, 10+ years, runs anywhere)

```bash
pip install dukascopy-python
# Edit SYMBOLS, TIMEFRAMES, START_YEAR in fetch_data_dukascopy.py
python fetch_data_dukascopy.py
```

### Option B — MT5 (recent data only, Windows VPS required)

```bash
# On your Windows VPS with MT5 open:
python fetch_data.py
# Copy CSVs back to data/historical/
```

Both output to `data/historical/<SYMBOL>_<TF>_<YYYYMMDD>-<YYYYMMDD>.csv`.
The backtest runner auto-discovers CSVs matching the symbol and timeframe.

### Option C — HistData (free independent cross-check)

```bash
python fetch_data_histdata.py --symbols EURUSD GBPUSD AUDUSD NZDUSD USDJPY USDCAD USDCHF XAUUSD EURAUD CADJPY GBPCAD GBPNZD AUDJPY AUDCAD --timeframes M5 M15 H1 H4 D1 --start-year 2016 --end-date 2026-03-20 --insecure
python run_backtest.py live_suite --data-source histdata
```

HistData is downloaded as M1 ASCII ZIPs, converted from New York local market time to UTC, resampled locally, and saved under `data/historical/histdata/`.
`--insecure` is only needed if the HistData certificate fails validation locally.
US30 is not mapped because HistData does not provide a direct Dow/US30 symbol equivalent.

### News calendar (for news filtering)

```bash
python fetch_news_data.py
# Outputs data/news/forex_factory_calendar.csv (75K+ events, 2007–2025, UTC)
```


## Backtesting

```bash
python run_backtest.py ema_fib_retracement
python run_backtest.py three_line_strike --start-date 2022-01-01
python run_backtest.py ema_fib_retracement --news-filter high
```

**Simulated execution**: fills at the open of the next bar (no look-ahead bias). Spread, commission, and lot sizing are applied identically to live trading.

### Backtest Output

**Trade log fields** (also accessible via `engine.execution.get_closed_trades()`):
`ticket, symbol, direction, strategy_name, entry_price, exit_price, sl, tp, sl_pips, result, r_multiple, pnl, commission, lot_size, open_time, close_time, duration_hours, pending_hours`

**Performance summary**: Total trades, Win rate, Total R, Profit factor, Max drawdown (R and %), Expectancy, Best/worst streak, Avg R on wins/losses.

**Charts** saved to `output/`: equity curve, monthly R heatmap, yearly performance heatmap.


## Walk-Forward Validation

The primary defence against overfitting. Splits data into rolling train/test windows, optimizes on each training window, then tests best params on unseen data.

```bash
python walk_forward.py ema_fib_retracement
python walk_forward.py three_line_strike --train-years 4 --test-years 2
```

**Interpreting OOS retention** (OOS expectancy / IS expectancy):
- ≥ 70% → **STRONG** (parameters generalize)
- 40–70% → **MODERATE** (some overfitting, acceptable)
- < 40% → **WEAK/FAIL** (curve-fit, do not trade live)

No strategy goes live without passing walk-forward.


## News Filter

Blocks signals near high-impact economic events (NFP, CPI, FOMC, rate decisions).

```bash
python run_backtest.py ema_fib_retracement --news-filter high
python run_backtest.py ema_fib_retracement --news-filter major --news-hours-before 2 --news-hours-after 1
```

Filter modes: `off` (default), `high`, `high-medium`, `major`.


## Multi-Timeframe Strategies

Subscribe to multiple timeframes via `TIMEFRAMES = ['D1', 'H1']`. The strategy receives bars from all timeframes and manages state per symbol via dicts. Use `event.timeframe` to distinguish them.


## Adding a New Strategy

1. Create `strategies/<name>.py` using the template in `CLAUDE.md`.

**Required elements:**

| Element | Why |
|---------|-----|
| `TIMEFRAMES` (class or instance attr) | Engine subscribes to the correct bar feed |
| `ORDER_TYPE` | `'MARKET'` or `'PENDING'` |
| `NAME` | Unique string — appears in logs and reports |
| `reset(self)` | Clears all state. Required for walk-forward reuse across folds. |
| `generate_signal(self, event) -> Signal \| None` | Only method the engine calls |
| `stop_loss` on every Signal | Risk manager rejects signals without SL |
| Per-symbol state via dicts | One instance handles all symbols |

2. Register in `run_backtest.py` `STRATEGIES` dict.
3. Run backtest, then param sweep, then walk-forward.
4. Register in `main_live.py` only after walk-forward passes.


## Live Suite (current, demo)

| Strategy | Timeframes | Order Type | Symbols | Walk-Forward |
|----------|-----------|------------|---------|-------------|
| EmaFibRetracement | D1, H1 | PENDING | 7 FX pairs | MODERATE (+0.427R OOS, 67% retention) |
| EmaFibRunning | D1, H1 | PENDING | 7 FX pairs | MODERATE (+0.375R OOS agg, folds 1&2) |
| Engulfing (ThreeLineStrike) | M5 | MARKET | EURUSD, AUDUSD | STRONG on Dukascopy and HistData after bid/ask spread retest |
| IMS (ImsStrategy) | H4, M15 | PENDING | 9 pairs | MODERATE (+0.165R OOS, 64% retention, all 3 folds positive) |

Run on Windows VPS: `python main_live.py`

Features: MT5 polling every 5s, Telegram notifications (startup / order placed / order closed / 8am heartbeat), file logging to `logs/trading.log`, auto-reconnect on MT5 failures.


## Execution Interface

```python
class BaseExecution(ABC):
    def place_order(self, symbol, direction, order_type, entry_price,
                    lot_size, sl, tp, strategy_name) -> int: ...  # returns ticket ID
    def close_order(self, ticket_id) -> bool: ...
    def get_open_positions(self) -> list[dict]: ...
```

For PENDING orders, the execution layer infers subtype from direction vs price:
- BUY + entry > current → Buy Stop
- BUY + entry < current → Buy Limit
- SELL + entry < current → Sell Stop
- SELL + entry > current → Sell Limit


## Credentials

`.env` at project root (gitignored):
```
MT5_LOGIN=12345678
MT5_PASSWORD=your_password
MT5_SERVER=YourBroker-Server
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```


## Instruments & Pip Sizes

| Symbol | Pip size | Notes |
|--------|----------|-------|
| EURUSD, GBPUSD, AUDUSD, NZDUSD, USDCAD, USDCHF | 0.0001 | Standard FX majors |
| USDJPY | 0.01 | JPY pairs |
| XAUUSD | 0.10 | Gold (10 pips = $1) |
| US30, USA30 | 1.0 | Dow Jones index points |
| US500, USA500 | 0.1 | S&P 500 |
| USTEC, USA100 | 1.0 | Nasdaq 100 |

All pip sizes and values are configured in `config.PIP_SIZE` and `config.PIP_VALUE_USD`.


## Timezone

All timestamps throughout the system are **UTC**. MT5 server time (UTC+2/+3) is auto-converted at load time. Dukascopy data is natively UTC.


## Platform Note

The `MetaTrader5` Python package is **Windows only**. Live trading requires a Windows VPS with MT5 installed. Backtesting (CSV-based) runs cross-platform on Python 3.10+.
