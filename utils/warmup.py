"""History requirements for a cold strategy start, keyed by symbol/timeframe."""
from math import ceil

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


def warmup_days(strategy_specs, minimum=180):
    """Calendar allowance for CSV replay, including weekends and a 10% margin.

    Broker startup requests exact bar counts. CSV availability still needs
    inspection when a source has gaps; elapsed days cannot guarantee coverage.
    """
    minutes = {'M1': 1, 'M5': 5, 'M15': 15, 'M30': 30, 'H1': 60, 'H4': 240, 'D1': 1440}
    counts = warmup_counts(strategy_specs)
    return max([minimum] + [ceil(n * minutes[tf] / 1440 * 7 / 5 * 1.1)
                           for (_, tf), n in counts.items()])
