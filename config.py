# ── Instruments & Timeframes ─────────────────────────────────────────────────
SYMBOLS = ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDJPY', 'USDCAD', 'USDCHF']
TIMEFRAMES = ['M5', 'M15', 'H1', 'H4', 'D1']

# ── Lot Sizing ────────────────────────────────────────────────────────────────
# Set LOT_SIZE_MODE to 'DYNAMIC' or 'FIXED'
LOT_SIZE_MODE = 'DYNAMIC'
FIXED_LOT_SIZE = 0.01       # Used only when LOT_SIZE_MODE = 'FIXED'
RISK_PCT = 0.005            # 0.5% risk per trade — used only when LOT_SIZE_MODE = 'DYNAMIC'

# ── Risk / Reward ─────────────────────────────────────────────────────────────
DEFAULT_RR_RATIO = 2.0      # 1:2 risk/reward by default
MIN_RR_RATIO = 1.0          # Minimum acceptable R:R — signals below this are rejected
MIN_SL_PIPS = 5             # Signals with a stop-loss smaller than this are rejected

# ── Portfolio Limits ──────────────────────────────────────────────────────────
MAX_OPEN_TRADES = 6
MAX_DAILY_LOSS_PCT = 0.02   # 2% of account balance — pauses trading for the day if hit

# ── Pip Sizes ─────────────────────────────────────────────────────────────────
# Size of one pip in price terms for each instrument
PIP_SIZE = {
    'EURUSD': 0.0001,
    'GBPUSD': 0.0001,
    'AUDUSD': 0.0001,
    'NZDUSD': 0.0001,
    'USDJPY': 0.01,
    'USDCAD': 0.0001,
    'USDCHF': 0.0001,
    # FX crosses — non-JPY
    'AUDCAD': 0.0001,
    'AUDNZD': 0.0001,
    'EURAUD': 0.0001,
    'EURCAD': 0.0001,
    'EURCHF': 0.0001,
    'EURGBP': 0.0001,
    'GBPAUD': 0.0001,
    'GBPCAD': 0.0001,
    'GBPNZD': 0.0001,
    # FX crosses — JPY (1 pip = 0.01)
    'AUDJPY': 0.01,
    'CADJPY': 0.01,
    'EURJPY': 0.01,
    'GBPJPY': 0.01,
    'NZDJPY': 0.01,
    # Metals & indices — 1 pip defined as the minimum meaningful unit
    'XAUUSD': 0.10,   # gold: 1 pip = $0.10 (10 cents per troy oz)
    'USA30':  1.0,    # Dow Jones: 1 pip = 1 index point
    'USA500': 0.1,    # S&P 500: 1 pip = 0.1 index point
    'USA100': 1.0,    # Nasdaq 100: 1 pip = 1 index point
    'USTEC':  1.0,    # Nasdaq 100 (ICMarkets name): 1 pip = 1 index point
}

# ── Spread ───────────────────────────────────────────────────────────────────
# Per-symbol spread in pips applied at entry during backtesting.
# Historical bars are bid-based, so spread is added to BUY entries and
# subtracted from SELL entries to model the ask/bid cost realistically.
# Based on observed ICMarkets raw-spread averages across typical trading hours.
# XAUUSD: $0.11 price spread / pip_size $0.10 = 1.1 pips.
# USTEC/USA100: 10 index points (= 10 pips at pip_size 1.0).
BACKTEST_SPREAD_PIPS: dict[str, float] = {
    # Measured via measure_spreads.py on ICMarkets Raw demo, active session (p95), 2026-04-01
    'EURUSD': 0.1,
    'GBPUSD': 0.2,
    'AUDUSD': 0.1,
    'NZDUSD': 0.4,
    'USDJPY': 0.1,
    'USDCAD': 0.2,
    'USDCHF': 0.1,
    # FX crosses — placeholders, calibrate with measure_spreads.py on VPS
    'AUDCAD': 0.5,
    'AUDNZD': 0.5,
    'AUDJPY': 0.4,
    'CADJPY': 0.5,
    'EURAUD': 0.5,
    'EURCAD': 0.5,
    'EURCHF': 0.5,
    'EURGBP': 0.3,
    'EURJPY': 0.3,
    'GBPAUD': 0.8,
    'GBPCAD': 0.8,
    'GBPJPY': 0.4,
    'GBPNZD': 0.8,
    'NZDJPY': 0.5,
    'XAUUSD': 1.1,
    'USTEC':  10.0,
    'USA100': 10.0,
    'USA30':  2.0,    # not measured — conservative placeholder
    'USA500': 2.0,    # not measured — conservative placeholder
}

# ── Commission ──────────────────────────────────────────────────────────────
# Round-trip commission per 1.0 standard lot (ICMarkets Raw Spread: $7.00/lot).
COMMISSION_PER_LOT = 7.0

# ── Pip Values ────────────────────────────────────────────────────────────────
# USD value of 1 pip per 1 standard lot (100,000 units)
# For XXX/USD pairs this is fixed at $10.
# For USD/XXX pairs the actual value varies with price; $10 is used as an approximation.
PIP_VALUE_USD = {
    'EURUSD': 10.0,
    'GBPUSD': 10.0,
    'AUDUSD': 10.0,
    'NZDUSD': 10.0,
    'USDJPY': 10.0,
    'USDCAD': 10.0,
    'USDCHF': 10.0,
    # FX crosses — approximate USD value per pip per 1 standard lot.
    # Actual value varies with exchange rate; these are typical-rate estimates.
    # Counter currency converted to USD: 10 units of counter / rate.
    'AUDCAD':  7.5,   # 10 CAD / ~1.33 USDCAD
    'AUDNZD':  6.0,   # 10 NZD × ~0.60 NZDUSD
    'AUDJPY':  7.0,   # 1000 JPY / ~143 USDJPY
    'CADJPY':  7.0,
    'EURAUD':  6.5,   # 10 AUD × ~0.65 AUDUSD
    'EURCAD':  7.5,
    'EURCHF': 11.0,   # 10 CHF / ~0.91 USDCHF
    'EURGBP': 12.5,   # 10 GBP × ~1.25 GBPUSD
    'EURJPY':  7.0,
    'GBPAUD':  6.5,
    'GBPCAD':  7.5,
    'GBPJPY':  7.0,
    'GBPNZD':  6.0,
    'NZDJPY':  7.0,
    # Metals & indices — USD value per pip per 1 standard lot
    'XAUUSD': 10.0,   # 100 troy oz × $0.10/pip = $10/lot
    'USA30':   1.0,   # $1/lot per 1-point move (ICMarkets CFD)
    'USA500':  1.0,   # $1/lot per 0.1-point move
    'USA100':  1.0,   # $1/lot per 1-point move
    'USTEC':   1.0,   # $1/lot per 1-point move (ICMarkets name for Nasdaq 100)
}


# ── Validation ───────────────────────────────────────────────────────────────

def validate():
    """Validate config parameters at startup. Raises ValueError on bad config."""
    errors = []

    if LOT_SIZE_MODE not in ('DYNAMIC', 'FIXED'):
        errors.append(f"LOT_SIZE_MODE must be 'DYNAMIC' or 'FIXED', got '{LOT_SIZE_MODE}'")

    if not (0 < RISK_PCT <= 1):
        errors.append(f"RISK_PCT must be between 0 and 1, got {RISK_PCT}")

    if FIXED_LOT_SIZE < 0.01:
        errors.append(f"FIXED_LOT_SIZE must be >= 0.01, got {FIXED_LOT_SIZE}")

    if not isinstance(MAX_OPEN_TRADES, int) or MAX_OPEN_TRADES < 1:
        errors.append(f"MAX_OPEN_TRADES must be a positive integer, got {MAX_OPEN_TRADES}")

    if not (0 < MAX_DAILY_LOSS_PCT <= 1):
        errors.append(f"MAX_DAILY_LOSS_PCT must be between 0 and 1, got {MAX_DAILY_LOSS_PCT}")

    if DEFAULT_RR_RATIO <= 0:
        errors.append(f"DEFAULT_RR_RATIO must be positive, got {DEFAULT_RR_RATIO}")

    if MIN_RR_RATIO <= 0:
        errors.append(f"MIN_RR_RATIO must be positive, got {MIN_RR_RATIO}")

    if MIN_SL_PIPS < 0:
        errors.append(f"MIN_SL_PIPS must be non-negative, got {MIN_SL_PIPS}")

    for sym, spread in BACKTEST_SPREAD_PIPS.items():
        if spread < 0:
            errors.append(f"BACKTEST_SPREAD_PIPS['{sym}'] must be non-negative, got {spread}")

    for sym in SYMBOLS:
        if sym not in PIP_SIZE:
            errors.append(f"Symbol '{sym}' listed in SYMBOLS but missing from PIP_SIZE")
        if sym not in PIP_VALUE_USD:
            errors.append(f"Symbol '{sym}' listed in SYMBOLS but missing from PIP_VALUE_USD")

    if errors:
        raise ValueError("Config validation failed:\n  - " + "\n  - ".join(errors))
