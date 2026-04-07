"""Quick comparison of the three SL modes for ThreeLineStrike on AUDUSD M5."""

import io
import contextlib
import logging

from backtest_engine import BacktestEngine
from strategies.three_line_strike import ThreeLineStrikeStrategy
from data.historical_loader import find_csv, load_and_merge

logging.basicConfig(level=logging.ERROR)

SYMBOLS = ['AUDUSD']
INITIAL_BALANCE = 10_000.0
RR_RATIO = 2.0

csv_paths = []
for symbol in SYMBOLS:
    csv_paths.extend(find_csv(symbol, 'M5'))

print("Loading bar data...")
all_bars = load_and_merge(csv_paths)
print(f"Loaded {len(all_bars)} bars\n")

VARIANTS = [
    ('bar_multiple x1.5', ThreeLineStrikeStrategy(sl_mode='bar_multiple', sl_bar_multiplier=1.5)),
    ('bar_multiple x2.0', ThreeLineStrikeStrategy(sl_mode='bar_multiple', sl_bar_multiplier=2.0)),
    ('bar_multiple x2.5', ThreeLineStrikeStrategy(sl_mode='bar_multiple', sl_bar_multiplier=2.5)),
    ('sma50',             ThreeLineStrikeStrategy(sl_mode='sma50')),
    ('fractal n=3',       ThreeLineStrikeStrategy(sl_mode='fractal', fractal_n=3)),
    ('fractal n=5',       ThreeLineStrikeStrategy(sl_mode='fractal', fractal_n=5)),
]

results = []

for label, strategy in VARIANTS:
    engine = BacktestEngine(initial_balance=INITIAL_BALANCE, rr_ratio=RR_RATIO)
    engine.add_strategy(strategy, symbols=SYMBOLS)

    with contextlib.redirect_stdout(io.StringIO()):
        for bar in all_bars:
            closed = engine.execution.check_fills(bar)
            for trade in closed:
                engine.portfolio.record_close(trade['symbol'], trade['pnl'], trade.get('strategy_name', ''))
                engine.trade_logger.log_close(trade['ticket'], trade)
                engine.event_engine.notify_trade_closed(trade)
            engine.event_engine.process_bar(bar)

    trades = engine.execution.get_closed_trades()
    n = len(trades)
    if n == 0:
        results.append({'label': label, 'trades': 0})
        continue

    wins = sum(1 for t in trades if t['result'] == 'WIN')
    total_r = sum(t['r_multiple'] for t in trades)
    expectancy = total_r / n
    gp = sum(t['r_multiple'] for t in trades if t['result'] == 'WIN')
    gl = abs(sum(t['r_multiple'] for t in trades if t['result'] == 'LOSS'))
    pf = gp / gl if gl > 0 else 0.0

    peak, max_dd, running = 0.0, 0.0, 0.0
    for t in trades:
        running += t['r_multiple']
        peak = max(peak, running)
        max_dd = max(max_dd, peak - running)

    results.append({
        'label': label,
        'trades': n,
        'win_rate': wins / n * 100,
        'total_r': total_r,
        'pf': pf,
        'expectancy': expectancy,
        'max_dd_r': max_dd,
    })
    print(f"  done: {label}")

W = 90
print(f"\n{'='*W}")
print(f"SL MODE COMPARISON  —  AUDUSD M5  (default params: max_sl=15, sma_sep=5, sessions=08-17 UTC)")
print(f"{'='*W}")
print(f"{'sl_mode':<20} {'trades':>6} {'WR%':>6} {'TotalR':>8} {'PF':>6} {'Expect':>7} {'MaxDD':>6}")
print('-' * W)
for r in results:
    if r['trades'] == 0:
        print(f"{r['label']:<20} {'0':>6}")
    else:
        print(
            f"{r['label']:<20} {r['trades']:>6} {r['win_rate']:>5.1f}% "
            f"{r['total_r']:>+8.1f} {r['pf']:>6.2f} {r['expectancy']:>+7.3f} {r['max_dd_r']:>6.1f}"
        )
