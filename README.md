# Python FX Trading Bot

## Overview

A modular, event-driven Python trading bot for FX, metals, and index CFDs using MetaTrader 5. The configured strategies currently run only on an IC Markets demo account. No strategy is approved for real-money live trading.

Key design principles:

- **Separation of responsibilities**: strategy, risk, execution, data, portfolio, and backtest layers are fully decoupled.
- **Event-driven, synchronous**: strategies respond to bar-close events via direct method calls (no asyncio, no queue overhead).
- **Reproducible backtesting**: historical data is stored locally as CSV and replayed bar by bar. Market orders fill on the next matching-timeframe open, while pending orders fill when their submitted level is touched.
- **Walk-forward validation**: strategies must pass rolling train/test validation before demo deployment. Real-money promotion requires a separate forward-demo review and explicit approval.


## Directory Layout

```
fxbot/
│
├── .env                          # MT5 + Telegram credentials (gitignored)
├── config.py                     # Global parameters (symbols, risk, lot size, etc.)
├── main_live.py                  # MT5 demo runner; filename retained for compatibility
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
│   ├── ema_fib_retracement.py    # DEMO: D1/H1 EMA trend + fib entry
│   ├── ema_fib_running.py        # DEMO: D1/H1 EMA trend + fib entry, running variant
│   ├── three_line_strike.py      # DEMO: M5 engulfing, NY session, 2 FX pairs
│   ├── ims.py                    # DEMO: H4/M15 ICT market structure, 9 symbols
│   ├── ims_reversal.py           # FORWARD DEMO: EURUSD-only frozen research trial
│   ├── failed2.py                # DEMO: USTEC H4/H1/M5 reversal
│   ├── ny_index_opening_drive.py # DEMO: USTEC NY opening drive
│   ├── candle_confirmation.py    # DEMO: separate USDJPY and GBPUSD instances
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
│   └── telegram_notifier.py      # Telegram alerts for MT5 demo execution
│
└── strategy_log/                 # One .md per strategy: params, sweep, WF history
```


## Layer Responsibilities

| Layer | Responsibility |
|-------|----------------|
| **Data** | Fetch live or historical OHLC bars per symbol/timeframe. Store locally as CSV for reproducible backtests. Auto-detects MT5 vs Dukascopy format and converts to UTC. |
| **Strategy** | Generate `BUY`/`SELL` signals from bar events. Fully isolated — never touches execution, risk, portfolio, or data layers. |
| **Risk** | Validates the signal has a stop-loss, computes lot size (dynamic or fixed), and sets take-profit. |
| **Execution** | Places demo or live orders through MT5. Backtests fill market orders on the next matching-timeframe open and pending orders when the submitted level is touched. Both implementations use the same `BaseExecution` interface. |
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

- **Commission**: $7.00 per lot round trip for FX and metals. Configured index CFDs are spread-only in the backtest model.
- **Spread**: `config.BACKTEST_SPREAD_PIPS` stores a measured or estimated value for each symbol. The model is static per symbol and does not reproduce intrabar spread spikes.
- **Minimum SL**: signals with SL < 5 pips are rejected.
- **Minimum R:R**: signals below 1.0 R:R are rejected.
- **Per-strategy overrides**: `risk_pct_overrides` dict in `RiskManager` (keyed by strategy NAME).


## Portfolio & Conflict Management

- **One position per (symbol, strategy) pair**: multiple strategies may hold concurrent positions on the same symbol independently.
- **Max open trades**: 8 total across all strategies in the demo runner and `live_suite` backtest. Single-strategy backtests use 99 to avoid unrelated portfolio-capacity effects.
- **Max daily loss**: 2% of account balance in the demo runner and `live_suite` backtest. Single-strategy backtests disable it.


## Historical Data

### Option A — Dukascopy (preferred, 10+ years, runs anywhere)

```bash
pip install dukascopy-python
python fetch_data_dukascopy.py --symbols EURUSD GBPUSD --timeframes M5 H1 --start-date 2016-01-01 --end-date 2026-08-01
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

**Simulated execution**: market orders fill at the next matching-timeframe bar open. Pending orders fill at their submitted price when the matching bid or ask range touches the level. The simulator applies configured spread, commission, and lot sizing, but it does not model tick-level slippage or variable spread.

### Backtest Output

**Trade log fields** (also accessible via `engine.execution.get_closed_trades()`):
`ticket, symbol, direction, strategy_name, entry_price, exit_price, sl, tp, sl_pips, result, r_multiple, pnl, commission, lot_size, open_time, close_time, duration_hours, pending_hours`

**Performance summary**: Total trades, Win rate, Total R, Profit factor, Max drawdown (R and %), Expectancy, Best/worst streak, Avg R on wins/losses.

**Charts** saved to `output/`: equity curve, monthly R heatmap, yearly performance heatmap.


## Walk-Forward Validation

The primary defence against overfitting. Splits data into rolling train/test windows, optimizes on each training window, then tests best params on unseen data.

```bash
python walk_forward.py ema_fib_retracement
python walk_forward.py engulfing --train-years 4 --test-years 2
```

**Interpreting OOS retention** (OOS expectancy / IS expectancy):
- ≥ 70% → **STRONG** (parameters generalize)
- 40–70% → **MODERATE** (some overfitting, acceptable)
- < 40% → **WEAK/FAIL** (curve-fit, do not deploy)

Walk-forward is required before demo deployment. Real-money live promotion also requires satisfactory forward-demo evidence and explicit user approval.


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

1. Create `strategies/<name>.py` using `strategies/ims.py` or `strategies/three_line_strike.py` as the pattern.

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
4. Register in `live_config.py` for demo only after walk-forward passes and the user approves it.
5. Consider real-money live promotion only after a satisfactory forward-demo sample and a separate explicit decision.


## Demo suite

This is the configured IC Markets demo suite as of 2026-08-31. `live_config.py` is the executable source of truth.

| Strategy | Timeframes | Type | Symbols | Current evidence |
|----------|------------|------|---------|------------------|
| EmaFibRetracement | D1, H1 | PENDING | 7 FX pairs | MODERATE walk-forward; positive IC Markets replay |
| EmaFibRunning | D1, H1 | PENDING | 7 FX pairs | STRONG walk-forward; positive IC Markets replay |
| Engulfing | M5 | MARKET | EURUSD, AUDUSD | Proxy walk-forward STRONG; IC Markets replay negative; pause under review |
| IMS | H4, M15 | PENDING | 9 symbols | MODERATE walk-forward; IC Markets replay close to flat; XAUUSD removal proposed |
| IMS Reversal | H4, M15 | PENDING | EURUSD | Frozen forward-demo research trial; not a promotion candidate yet |
| Failed2 | D1, H4, H1, M5 | MARKET | USTEC | STRONG on Dukascopy and HistData; positive IC Markets replay |
| NY Index Opening Drive | D1, H1, M5 | MARKET | USTEC | STRONG on Dukascopy and HistData; positive IC Markets replay; 0.25% risk |
| Candle Confirmation USDJPY | D1, H1, M5 | MARKET | USDJPY | MODERATE validation; IC Markets net edge near zero; pause under review |
| Candle Confirmation GBPUSD | D1, H1, M5 | MARKET | GBPUSD | Fixed candidate positive OOS; weak IC Markets net edge; pause under review |

Run the demo account on the Windows VPS with `python main_live.py`.

Features: MT5 polling every 5s, Telegram notifications (startup / order placed / order closed / 8am heartbeat), file logging to `logs/trading.log`, auto-reconnect on MT5 failures.


## Execution Interface

```python
class BaseExecution(ABC):
    def place_order(self, symbol, direction, order_type, entry_price,
                    lot_size, sl, tp, strategy_name,
                    entry_timeframe=None, tp_locked=False,
                    signal_time=None) -> int: ...
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
