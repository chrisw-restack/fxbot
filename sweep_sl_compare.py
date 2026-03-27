"""Compare TheStrat H4/H1/M15 with sl=5, sl=8, and sl=15."""

import logging
import sys
import io
import contextlib
from backtest_engine import BacktestEngine
from strategies.the_strat import TheStratStrategy
from data.historical_loader import find_csv

logging.basicConfig(level=logging.ERROR)

SYMBOLS = ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDJPY', 'USDCAD', 'USDCHF']
INITIAL_BALANCE = 10_000.0
RR_RATIO = 2.0
SPREAD_PIPS = 2.0

COMBOS = [
    {'label': 'H4/H1/M15 sl=5  cd=3 daily', 'min_sl_pips': 5,  'cooldown_bars': 3, 'tp_mode': 'daily'},
    {'label': 'H4/H1/M15 sl=8  cd=3 daily', 'min_sl_pips': 8,  'cooldown_bars': 3, 'tp_mode': 'daily'},
    {'label': 'H4/H1/M15 sl=15 cd=3 daily', 'min_sl_pips': 15, 'cooldown_bars': 3, 'tp_mode': 'daily'},
    {'label': 'H4/H1/M15 sl=15 cd=0 daily', 'min_sl_pips': 15, 'cooldown_bars': 0, 'tp_mode': 'daily'},
    {'label': 'H4/H1/M15 sl=15 cd=6 daily', 'min_sl_pips': 15, 'cooldown_bars': 6, 'tp_mode': 'daily'},
]

results = []

for combo in COMBOS:
    label = combo['label']
    sys.stderr.write(f"Running: {label}\n")

    strat = TheStratStrategy(
        tp_mode=combo['tp_mode'],
        min_sl_pips=combo['min_sl_pips'],
        cooldown_bars=combo['cooldown_bars'],
        tf_bias='H4', tf_intermediate='H1', tf_entry='M15',
    )

    csv_paths = []
    for sym in SYMBOLS:
        for tf in strat.TIMEFRAMES:
            csv_paths.extend(find_csv(sym, tf))

    engine = BacktestEngine(initial_balance=INITIAL_BALANCE, rr_ratio=RR_RATIO, spread_pips=SPREAD_PIPS)
    engine.add_strategy(strat, symbols=SYMBOLS)

    with contextlib.redirect_stdout(io.StringIO()):
        engine.run(csv_paths)

    trades = engine.trade_logger._closed_trades
    total_trades = len(trades)
    if total_trades == 0:
        results.append({'label': label, 'trades': 0})
        continue

    wins = sum(1 for t in trades if t.get('r_multiple', 0) > 0)
    total_r = sum(t.get('r_multiple', 0) for t in trades)
    win_rate = wins / total_trades * 100

    gross_win = sum(t['r_multiple'] for t in trades if t.get('r_multiple', 0) > 0)
    gross_loss = abs(sum(t['r_multiple'] for t in trades if t.get('r_multiple', 0) < 0))
    pf = gross_win / gross_loss if gross_loss > 0 else float('inf')

    equity = peak = max_dd = 0
    for t in trades:
        equity += t.get('r_multiple', 0)
        if equity > peak: peak = equity
        dd = peak - equity
        if dd > max_dd: max_dd = dd

    max_win_streak = max_loss_streak = cur_win = cur_loss = 0
    for t in trades:
        if t.get('r_multiple', 0) > 0:
            cur_win += 1; cur_loss = 0
        else:
            cur_loss += 1; cur_win = 0
        max_win_streak = max(max_win_streak, cur_win)
        max_loss_streak = max(max_loss_streak, cur_loss)

    results.append({
        'label': label, 'trades': total_trades, 'wins': wins,
        'win_rate': win_rate, 'total_r': total_r, 'pf': pf,
        'max_dd': max_dd, 'expectancy': total_r / total_trades,
        'win_streak': max_win_streak, 'loss_streak': max_loss_streak,
    })

print(f"\n{'='*130}")
print(f"{'TheStrat H4/H1/M15 — SL COMPARISON':^130}")
print(f"{'='*130}")
print(f"{'Config':<32} {'Trades':>7} {'WinRate':>8} {'TotalR':>10} {'PF':>7} {'Expect':>8} {'MaxDD':>8} {'WStrk':>6} {'LStrk':>6}")
print(f"{'-'*130}")
for r in results:
    if r['trades'] == 0:
        print(f"{r['label']:<32} {'0':>7}")
        continue
    print(f"{r['label']:<32} {r['trades']:>7} {r['win_rate']:>7.1f}% {r['total_r']:>+10.1f} {r['pf']:>7.2f} {r['expectancy']:>+8.3f} {r['max_dd']:>8.1f} {r['win_streak']:>6} {r['loss_streak']:>6}")
