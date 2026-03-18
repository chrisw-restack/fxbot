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
}

# ── Spread ───────────────────────────────────────────────────────────────────
# Simulated spread in pips applied at entry during backtesting.
# Historical bars are bid-based, so spread is added to BUY entries and
# subtracted from SELL entries to model the ask/bid cost realistically.
BACKTEST_SPREAD_PIPS = 1.0

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

    if MIN_SL_PIPS < 0:
        errors.append(f"MIN_SL_PIPS must be non-negative, got {MIN_SL_PIPS}")

    if BACKTEST_SPREAD_PIPS < 0:
        errors.append(f"BACKTEST_SPREAD_PIPS must be non-negative, got {BACKTEST_SPREAD_PIPS}")

    for sym in SYMBOLS:
        if sym not in PIP_SIZE:
            errors.append(f"Symbol '{sym}' listed in SYMBOLS but missing from PIP_SIZE")
        if sym not in PIP_VALUE_USD:
            errors.append(f"Symbol '{sym}' listed in SYMBOLS but missing from PIP_VALUE_USD")

    if errors:
        raise ValueError("Config validation failed:\n  - " + "\n  - ".join(errors))
