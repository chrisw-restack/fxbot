"""History requirements for a cold strategy start, keyed by symbol/timeframe."""

DEFAULT_WARMUP_BARS = {'D1': 50, 'H4': 100, 'H1': 100, 'M15': 200, 'M5': 250}


def warmup_counts(strategy_specs):
    counts = {}
    for strategy, symbols in strategy_specs:
        requirements = getattr(strategy, 'warmup_requirements', lambda: {})()
        for symbol in symbols:
            for timeframe in strategy.TIMEFRAMES:
                requested = max(DEFAULT_WARMUP_BARS.get(timeframe, 50), requirements.get(timeframe, 0))
                key = (symbol, timeframe)
                counts[key] = max(counts.get(key, 0), requested)
    return counts
