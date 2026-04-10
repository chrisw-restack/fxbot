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
- **One position per symbol at a time**: the portfolio manager blocks any new signal for a symbol that already has an open position.

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

This is the main workflow for extending the bot. The core system is stable — new work is limited to writing strategies, gathering data, backtesting, and going live if profitable.

### Step 1: Create the strategy file

Create `strategies/<strategy_name>.py`. Use this template:

```python
from collections import deque

from models import BarEvent, Signal


class MyStrategy:
    """
    Brief description of the strategy logic.
    """

    # ── Required class attributes ────────────────────────────────────────────
    TIMEFRAMES = ['H1']          # Timeframes this strategy subscribes to
    ORDER_TYPE = 'MARKET'        # 'MARKET' or 'PENDING' — one per strategy, not both
    NAME = 'MyStrategy'          # Unique name — appears in logs and backtest output

    def __init__(self, lookback: int = 20):
        self.lookback = lookback
        # Per-symbol state — strategies handle multiple symbols via dicts
        self._bars: dict[str, deque] = {}
        self._last_direction: dict[str, str | None] = {}

    def reset(self):
        """Clear all internal state. Called before reusing the instance in a new backtest."""
        self._bars.clear()
        self._last_direction.clear()

    def generate_signal(self, event: BarEvent) -> Signal | None:
        symbol = event.symbol

        # Initialise per-symbol state on first bar
        if symbol not in self._bars:
            self._bars[symbol] = deque(maxlen=self.lookback)
            self._last_direction[symbol] = None

        window = self._bars[symbol]

        # Accumulate bars until the window is full
        if len(window) < self.lookback:
            window.append(event)
            return None

        # ── Your logic here ──────────────────────────────────────────────────
        # Calculate indicators from `window` (the previous N bars).
        # Decide whether to BUY, SELL, or do nothing.
        # Set stop_loss to a price level (the risk manager handles TP and lot size).

        signal = None

        # Example: if some_buy_condition and self._last_direction[symbol] != 'BUY':
        #     self._last_direction[symbol] = 'BUY'
        #     signal = Signal(
        #         symbol=symbol,
        #         direction='BUY',
        #         order_type=self.ORDER_TYPE,
        #         entry_price=event.close,
        #         stop_loss=some_price_level,
        #         strategy_name=self.NAME,
        #         timestamp=event.timestamp,
        #     )

        # Append current bar AFTER checking — window always holds previous bars
        window.append(event)
        return signal
```

### Required elements checklist

| Element | Why |
|---------|-----|
| `TIMEFRAMES` (class attr) | The engine uses this to subscribe the strategy to the correct bar feed |
| `ORDER_TYPE` (class attr) | `'MARKET'` or `'PENDING'` — determines how execution fills the order |
| `NAME` (class attr) | Unique string — appears in trade log, rejection messages, and backtest output |
| `__init__` with parameters | All tuneable parameters as constructor args so they can be adjusted from `run_backtest.py` |
| `reset(self)` | Clears all internal state (deques, dicts, flags). Required so the same instance can be reused across backtests without stale state leaking between runs |
| `generate_signal(self, event: BarEvent) -> Signal or None` | The only method the engine calls. Returns a `Signal` or `None` |
| Per-symbol state via dicts | One strategy instance handles all symbols. Use `event.symbol` as the dict key |
| `stop_loss` on every Signal | The risk manager rejects signals without a stop-loss. Signals with SL < `config.MIN_SL_PIPS` (default 5) are also rejected |
| `notify_loss(self, symbol)` (optional) | Called by the engine when a trade closes at a loss. Use for cooldown timers, swing invalidation, etc. |

### Rules strategies must follow

1. **Only import from `models`** — never import from `execution/`, `risk/`, `portfolio/`, `data/`, or `config`. Strategies are pure signal generators.
2. **Take-profit is optional** — by default the risk manager calculates TP from `entry ± (SL distance x R:R ratio)`. Set `take_profit` on the Signal only if the strategy has its own TP logic (e.g. fibonacci extensions).
3. **CANCEL signals for pending orders** — if a strategy uses PENDING orders and needs to cancel unfilled orders (e.g. when bias flips), return a Signal with `direction='CANCEL'`. Do not emit CLOSE signals — filled trades always run to SL or TP.
4. **Suppress re-entry in the same direction** — track `_last_direction[symbol]` and only fire when direction changes. This prevents duplicate signals on consecutive bars.
5. **Append the current bar to the window AFTER checking conditions** — the window should hold the previous N bars, not include the current bar. This avoids look-ahead bias.
6. **Use `event.close` as `entry_price` for MARKET orders** — the simulated execution fills at the next bar's open (not at `entry_price`), so this is just a reference price for the risk manager.
7. **For PENDING orders**, set `entry_price` to the desired fill level. The execution layer infers the order subtype (Buy Stop, Buy Limit, etc.) automatically.

### Step 2: Register in `run_backtest.py`

Add the import and an entry in the `STRATEGIES` dict:

```python
from strategies.my_strategy import MyStrategy

STRATEGIES = {
    'breakout':       BreakoutStrategy(lookback=20),
    'mean_reversion': MeanReversionStrategy(lookback=20, std_multiplier=2.0, sl_lookback=5),
    'my_strategy':    MyStrategy(lookback=20),
}
```

Then run: `python run_backtest.py my_strategy`

### Step 3: Register in `main_live.py` (when ready for live)

Add the import and append to the `strategies` list:

```python
from strategies.my_strategy import MyStrategy

strategies = [
    BreakoutStrategy(lookback=20),
    MyStrategy(lookback=20),
]
```

### Multi-symbol backtesting

To test on multiple symbols, edit `SYMBOLS` in `run_backtest.py` and ensure you have CSV files for each. The engine handles routing — your strategy receives bars for all symbols and tracks state per symbol via dicts.

### Multi-timeframe strategies

Subscribe to multiple timeframes via `TIMEFRAMES = ['H1', 'H4']`. The strategy receives bars from both timeframes through `generate_signal()`. Use `event.timeframe` to distinguish them and manage internal state accordingly (e.g. store H4 trend direction, trigger entries on H1).

### Data for backtesting

**Option A — MT5** (recent data, requires VPS):
1. On your Windows VPS, run `python fetch_data.py` to download CSV data from MT5.
2. Copy the CSV files to `data/historical/` on your dev machine.

**Option B — Dukascopy** (10+ years, runs anywhere):
1. `pip install dukascopy-python`
2. Edit `SYMBOLS`, `TIMEFRAMES`, `START_YEAR` in `fetch_data_dukascopy.py`
3. Run `python fetch_data_dukascopy.py`

Both output to `data/historical/` with filename format: `<SYMBOL>_<TF>_<YYYYMMDD>-<YYYYMMDD>.csv`. The backtest runner auto-discovers CSVs matching the symbol and timeframe. The historical loader auto-detects the data source and handles timezone conversion.

**Option C — News calendar** (for news filtering):
1. Run `python fetch_news_data.py`
2. Downloads Forex Factory calendar (2007-2025, 75K+ events) from Hugging Face
3. Outputs to `data/news/forex_factory_calendar.csv` (normalized to UTC)

## Risk Manager Logic

1. Validate signal has a stop-loss price; reject if missing.
2. Calculate SL distance in pips from `entry_price` to `stop_loss`.
3. Calculate lot size:
   - `DYNAMIC`: `(account_balance × risk_pct) ÷ (sl_pips × pip_value)`
   - `FIXED`: use `config.FIXED_LOT_SIZE` directly
4. Calculate take-profit: use `signal.take_profit` if provided, otherwise `entry ± (sl_distance × rr_ratio)`.
5. Return enriched signal to portfolio manager.

## Portfolio Manager Logic

On each incoming signal:
1. Check if **(symbol, strategy_name)** already has an open position → block if yes. Multiple strategies may hold positions on the same symbol simultaneously (one slot per strategy per symbol).
2. Check if `open_trade_count >= MAX_OPEN_TRADES` (default 6) → block if yes.
3. Check if daily loss has exceeded `MAX_DAILY_LOSS_PCT` (default 2%) → block if yes.
4. If all checks pass, forward to execution.

`record_close(symbol, pnl, strategy_name)` requires `strategy_name` to identify the correct slot.

## Execution Interface

```python
class BaseExecution(ABC):
    @abstractmethod
    def place_order(self, symbol, direction, order_type, entry_price,
                    lot_size, sl, tp, strategy_name) -> int: ...  # returns ticket ID

    @abstractmethod
    def close_order(self, ticket_id) -> bool: ...

    @abstractmethod
    def get_open_positions(self) -> list[dict]: ...
```

Simulated execution fills at the **open of the next bar** (no look-ahead bias).

For `PENDING` orders, the execution layer infers order subtype from direction vs. entry price vs. current price:
- BUY + entry > current → Buy Stop
- BUY + entry < current → Buy Limit
- SELL + entry < current → Sell Stop
- SELL + entry > current → Sell Limit

## Config Parameters (`config.py`)

```python
SYMBOLS = ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDJPY', 'USDCAD', 'USDCHF']
# Metals/indices available for backtesting: XAUUSD, US30, US500, USTEC, DE40
# (pip sizes and pip values for all of these are configured in config.py)
TIMEFRAMES = ['M5', 'M15', 'H1', 'H4', 'D1']

LOT_SIZE_MODE = 'DYNAMIC'   # 'DYNAMIC' or 'FIXED'
FIXED_LOT_SIZE = 0.01       # used only when LOT_SIZE_MODE = 'FIXED'
RISK_PCT = 0.005            # 0.5% per trade — used only when LOT_SIZE_MODE = 'DYNAMIC'
DEFAULT_RR_RATIO = 2.0      # 1:2 risk/reward
MIN_RR_RATIO = 1.0          # minimum acceptable R:R — signals below this are rejected

MAX_OPEN_TRADES = 6         # allows headroom for future multi-strategy expansion
MAX_DAILY_LOSS_PCT = 0.02   # 2% of account balance
```

Pip sizes and values for all instruments (including XAUUSD, US30, US500, USTEC, DE40) are in `config.PIP_SIZE` and `config.PIP_VALUE_USD`. Add new instruments there before backtesting them.

Per-strategy risk overrides are supported via `risk_pct_overrides` dict in `RiskManager` (keyed by strategy NAME). Currently EmaFibRetracement uses 0.7%, all others use the 0.5% default.

## Live Trading

Run on Windows VPS with MT5 installed and running:
```
python main_live.py
```

Features:
- Polls MT5 every 5 seconds for new completed bars
- Detects trade closures (SL/TP hit on broker side) by tracking open positions
- Telegram notifications: startup, order placed, order closed, daily heartbeat (8am UTC+2)
- File logging to `logs/trading.log`
- Auto-reconnect on MT5 connection failures (3 consecutive failures triggers reconnect)

## Credentials

`.env` file at project root (must be gitignored):
```
MT5_LOGIN=12345678
MT5_PASSWORD=your_password
MT5_SERVER=YourBroker-Server
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```
Load with `python-dotenv` in `main_live.py`. Never hardcode credentials.

## Timezone Standardisation

All timestamps throughout the system are **UTC**.

- **MT5 data** (`fetch_data.py`): saved in ICMarkets server time (UTC+2 winter / UTC+3 summer). The historical loader auto-detects and converts to UTC at load time.
- **Dukascopy data** (`fetch_data_dukascopy.py`): natively UTC. The loader auto-detects (by checking for Sunday bars) and skips conversion.
- **Live feed** (`data/mt5_data.py`): uses `datetime.utcfromtimestamp()` to produce UTC.
- **Simulated execution**: recalculates TP from actual fill price for MARKET orders, so R:R is measured from real entry (not distorted by fill slippage).

## Historical CSV Format

Path: `data/historical/<SYMBOL>_<TF>_<YYYYMMDD>-<YYYYMMDD>.csv`
Columns: `time, open, high, low, close, tick_volume` (MT5) or `time, open, high, low, close, volume` (Dukascopy)

## Backtest Output

**Trade log** (printed as table and/or saved to CSV):
`datetime | symbol | direction | result | r_multiple | strategy`

**Closed trade dict fields** (available in analysis scripts via `engine.execution.get_closed_trades()`):
- `ticket`, `symbol`, `direction`, `strategy_name`
- `entry_price`, `exit_price`, `sl`, `tp`, `sl_pips`
- `result` — `'WIN'` | `'LOSS'` | `'BE'`
- `r_multiple` — profit in units of initial risk
- `pnl`, `commission`, `lot_size`
- `open_time`, `close_time`
- `duration_hours` — time from fill to close
- `pending_hours` — time from signal emission to fill (PENDING orders only; `None` for MARKET orders)

**Performance summary**:
- Total trades, win rate %, total R
- Profit factor (gross profit R ÷ gross loss R)
- Max drawdown (R and %)
- Expectancy (avg R per trade)
- Best win streak / worst loss streak
- Avg R on wins / avg R on losses

**Charts** (saved to `output/`):
- Equity curve (green/red fill, balance annotation)
- Monthly Total R heatmap (year × month grid)
- Yearly performance heatmap (Total R, Trades, Win Rate, Expectancy, Profit Factor)

## Platform

- `MetaTrader5` package is **Windows only**. Live trading requires a Windows VPS with MT5 installed.
- Backtesting (CSV-based) is cross-platform.
- Python 3.10+

## Parameter Optimization

Use `param_sweep.py` for grid search over strategy parameters. It pre-loads bar data once and runs all combinations against it. Edit the `PARAM_GRID` dict and run:
```
python param_sweep.py
```
Outputs ranked tables by Total R, Expectancy, and Profit Factor.

## Walk-Forward Validation

Use `walk_forward.py` to validate that optimized parameters generalize to unseen data. This is the primary defence against overfitting. Any parameter changes should pass walk-forward before going live.

```
python walk_forward.py ema_fib_retracement
python walk_forward.py ebp
python walk_forward.py breakout
```

**How it works**: splits data into rolling train/test windows (default 4yr train, 2yr test, 2yr step). For each fold, optimizes parameters on training data, then tests the best params on out-of-sample data. Reports per-fold and aggregate OOS metrics.

**CLI options**:
- `--train-years N` — training window length (default 4)
- `--test-years N` — test window length (default 2)
- `--step-years N` — advance between folds (default 2)
- `--metric {expectancy,total_r,pf}` — optimization target (default expectancy)
- `--min-trades N` — minimum IS trades required to include a parameter combo (default 50). Raise to 100+ for sparse strategies to avoid selecting combos that "won" due to 1-2 lucky trades.
- `--workers N` — parallel worker processes for IS optimisation (default 1). Use 1 for true sequential execution (no fork overhead, no memory pressure). Set higher only if system has spare headroom.

**`rr_ratio` in param grids**: add `'rr_ratio': [2.0, 2.5]` to a strategy's `param_grid` in `STRATEGY_CONFIGS` to sweep R:R targets. It is automatically extracted from the params dict before passing to the strategy constructor and forwarded to the BacktestEngine instead.

**Interpreting results**: the key metric is **OOS retention** (OOS expectancy / IS expectancy). Above 70% = STRONG (parameters generalize), 40-70% = MODERATE (some overfitting), below 40% = WEAK/FAIL (curve-fit).

**Date filtering**: `filter_bars(bars, start, end)` in `data/historical_loader.py` allows slicing pre-loaded bar data to any date range [start, end). Used by walk-forward internally but also available for manual date-range backtesting.

## Live Suite

The bot runs **3 strategies** in production (`main_live.py`). EmaFib strategies run on 7 FX pairs; Engulfing runs on 5 pairs. Each strategy gets its own position slot per symbol — they can hold concurrent positions on the same symbol independently.

| Strategy | Timeframes | Order Type | Symbols | Key Params |
|----------|-----------|------------|---------|------------|
| EmaFibRetracement | D1, H1 | PENDING | 7 pairs | fib_entry=0.786, fib_tp=3.0, fractal_n=3, min_swing=10, ema_sep=0.001, cooldown=10, invalidate=True, blocked_hours=(20-23, 0-8) |
| EmaFibRunning | D1, H1 | PENDING | 7 pairs | fib_entry=0.786, fib_tp=2.5, fractal_n=2, min_swing=30, ema_sep=0.0, cooldown=0, invalidate=True, blocked_hours=(20-23, 0-8) |
| Engulfing | M5 | MARKET | 5 pairs | fractal_n=3, min_body=3.0, engulf_ratio=1.5, max_sl=15, NY session (13-17 UTC), sma_sep=5.0, rr=2.5 |

EmaFib combined (2016–2026): 519 trades, +284.1R, +0.547R expectancy, MaxDD 28.5R (~14.3%).
MAX_OPEN_TRADES cap is 6 — observed peak across all 3 strategies is ~7–8 (adequate headroom for demo).

EmaFibRetracement: `python3 run_backtest.py ema_fib_retracement`
Walk-forward: MODERATE (+110.9R OOS, +0.427R expect, 67% retention). IS 2016–2026: +247.8R, +0.774R expect, PF=1.89.

EmaFibRunning: `python3 run_backtest.py ema_fib_running`
Walk-forward: MODERATE (folds 1&2 positive, fold 3 sparse/12 OOS trades). IS 2016–2026: +82.7R, +0.371R expect, PF=1.53.

Engulfing: `python3 run_backtest.py three_line_strike`
Walk-forward: STRONG (all 3 folds OOS positive, +0.237R agg OOS, 178% retention). IS 2016–2026 (5 pairs): +22R, +0.22R expect, PF=1.37. ~10 trades/yr. RR=2.5 validated by WF fold 3 (2024–2026).
Engulfing symbols: EURUSD, AUDUSD, NZDUSD, USDJPY, USDCAD (GBPUSD negative on NY session; USDCHF poor IS).

**Needs more data (not live):**
- **EBP** (H1/M15) — INCONCLUSIVE. Real IS edge found (+0.460R, PF 1.86) with mss_bar SL + max_retrace=0.5. WF WEAK on both H4/H1 and H1/M15 stacks — all 3 folds chose identical H1/M15 params (positive sign) but fold 3 OOS failed. Too few OOS trades (10–20/fold) to distinguish edge from noise. Needs 50+ demo trades. See `strategy_log/ebp.md`.
- **HourlyMeanReversion** (M5, XAUUSD) — M5 post-bugfix WF MODERATE: folds 2&3 positive (+0.245R avg OOS), fold 1 fails (2016–2020 regime). Too sparse (~2–5 trades/yr) for standalone live use. M1 fully shelved — tested Asian (FAIL), London bare (WEAK), London + D1 bias (WEAK), London + ATR gate (WEAK). Gold bull regime (2022+) is structural, not fixable with filters. See `strategy_log/hourly_mean_reversion.md`.

**Suspended / shelved:**
- TheStrat — fails walk-forward after fill-bug fix. See `strategy_log/the_strat.md`.
- IMS — walk-forward FAIL, too few trades for reliable OOS optimisation. See `strategy_log/ims.md`.
- EBP Limit — walk-forward FAIL, regime-dependent. See `strategy_log/ebp_limit.md`.
- Breakout — walk-forward FAIL. Simple N-bar channel breakout has no robust edge on forex H1. See `strategy_log/breakout.md`.
- GaussianChannel — walk-forward WEAK (+0.046R OOS, 40% retention, fold 2 negative). Also had a warm-up bug (corrupt filter state for first 2×period bars, now fixed). See `strategy_log/gaussian_channel.md`.
- EmaFibRetracementIntraday — walk-forward FAIL, severe curve-fit. See `strategy_log/ema_fib_retracement_intraday.md`.
- MeanReversion — no positive sweep combos at all. See `strategy_log/mean_reversion.md`.
- KeltnerReversion — walk-forward FAIL (aggregate -0.006R, fold 3 collapse). See `strategy_log/keltner_reversion.md`.
- RangeFade — barely fires (56 trades/10yr best combo), no reliable edge. See `strategy_log/range_fade.md`.
- SupplyDemand — walk-forward MODERATE (+0.020R OOS, 51% retention) but only 150 OOS trades and fold 1 negative. Insufficient evidence. See `strategy_log/supply_demand.md`.
- IctJudasSwing — sweep all 108 combos negative (best -0.024R). M5 MSS pattern has no edge at 2:1 R:R. See `strategy_log/ict_judas_swing.md`.
- SmcZone — SHELVED: swing pivot zones + fractal BOS + wick rejection. Best IS: +0.318R, 43.9% WR, PF 1.57, but only 11 trades/yr — too sparse for walk-forward. WR ceiling ~40–44% across all configs. See `strategy_log/smc_zone.md`.
- BigBelugaSd — SHELVED: 3-candle momentum zone detection. WR 33.4% (breakeven), expectancy ~0R. Volume filter useless with tick volume (FX has no centralised exchange). See `strategy_log/bigbeluga_sd.md`.
- SmcReversal — SHELVED: ICT-style D1 bias + M15/H4/H1 OB confluence + M5 NY killzone entry (USTEC/US30/US500). WF FAIL on both USTEC-only and 3-symbol runs. Regime-dependent: OBs fail in COVID/rate-hike periods (WR collapses to 22-24%), only 2024–2026 fold positive. Discretionary use valid; systematic version cannot capture regime context. See `strategy_log/smc_reversal.md`.

**Strategy logs**: `strategy_log/` folder contains one `.md` per strategy with full parameter, sweep, and walk-forward history.

## News Filter

Optional filter that blocks signals near high-impact economic news events (NFP, CPI, FOMC, rate decisions, etc.). Integrated into `engine.py` — signals are checked after strategy generation, before risk processing.

**Data source**: Forex Factory calendar via Hugging Face (`Ehsanrs2/Forex_Factory_Calendar`). 75K+ events from 2007-2025, normalized to UTC. Download with `python fetch_news_data.py`.

**Usage in backtesting**:
```
python run_backtest.py ema_fib_retracement --news-filter high
python run_backtest.py ema_fib_retracement --news-filter major --news-hours-before 2 --news-hours-after 1
```

**Filter modes**:
- `off` (default) — no filtering
- `high` — block all high-impact news for either currency in the pair
- `high-medium` — block high and medium impact
- `major` — block only NFP, CPI, FOMC, and central bank rate decisions

**Parameters**: `--news-hours-before` (default 4) and `--news-hours-after` (default 1) control the block window.

**For live trading**: pass a `NewsFilter` instance to `EventEngine` via the `news_filter` parameter.

**Programmatic usage**:
```python
from data.news_filter import NewsFilter

nf = NewsFilter(
    block_hours_before=4, block_hours_after=1,
    impact_levels={'HIGH'},
    event_keywords=['Non-Farm', 'CPI', 'FOMC'],  # None = all events matching impact
)
nf.is_blocked(symbol='EURUSD', timestamp=some_datetime)  # True if blocked
```

## Important Notes

- **USDJPY pip size is 0.01** (not 0.0001). Any strategy doing pip calculations internally must handle this. Use a `pip_sizes` dict parameter.
- **Backtest spread is 2.0 pips** — conservative average. ICMarkets Raw typical spreads during London/NY session are 0.1–0.5 pips on majors; p95 is likely 1.0–1.2 pips. Use `measure_spreads.py` on the VPS during active hours to get symbol-accurate values. Current 2.0 pips setting understates real performance by ~1 pip per trade.
- **Commission is $7.00 per lot round-trip** (ICMarkets Raw Spread) — deducted from PnL at trade close in backtesting.
- **Break-even stop loss** is supported via `--breakeven-at-r N` in `run_backtest.py` (e.g. `--breakeven-at-r 2.0`). Tested at 2R, 3R, 5R, 7R, 10R for EmaFibRetracement — all levels hurt performance. At 2R: −52R net vs baseline (14 wins saved, 178R of large wins lost). Large wins (12R+) require price to briefly retrace through the BE trigger before continuing. Do not use for fib retracement strategies.

## Future Work
- Currency exposure limits (max positions per currency to reduce correlation risk)
- Drawdown throttle (reduce position size or pause after X% peak-to-trough decline)
- Variable spread model (wider spreads during news/low-liquidity sessions)
- Additional strategy development (mean-reversion, different asset classes)
