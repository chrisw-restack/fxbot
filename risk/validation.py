"""Price and volume checks shared by risk and execution."""
from math import floor, isfinite


def positive(value) -> bool:
    return isinstance(value, (int, float)) and isfinite(value) and value > 0


def valid_levels(direction, entry, sl, tp=None, minimum_rr=1.0) -> bool:
    if direction not in ('BUY', 'SELL') or not all(positive(v) for v in (entry, sl)):
        return False
    risk = entry - sl if direction == 'BUY' else sl - entry
    if risk <= 0:
        return False
    if tp is None:
        return True
    if not positive(tp):
        return False
    reward = tp - entry if direction == 'BUY' else entry - tp
    return reward > 0 and reward / risk + 1e-10 >= minimum_rr


def floor_volume(volume, step=0.01, minimum=0.01, maximum=100.0) -> float:
    if not all(positive(v) for v in (volume, step, minimum, maximum)):
        return 0.0
    rounded = floor((min(volume, maximum) + step * 1e-10) / step) * step
    return round(rounded, 10) if rounded + step * 1e-10 >= minimum else 0.0
