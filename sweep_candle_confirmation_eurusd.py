"""Candle Confirmation broad parameter sweep for one FX symbol.

Focused on H1/M5 candle confirmation with practical but broad trend, engulf
quality, TP, and SL geometry variations. Results are appended to CSV so the
run can be resumed if interrupted.
"""

import argparse
import contextlib
import csv
import io
import itertools
import logging
import os
import sys

from backtest_engine import BacktestEngine
import config
from data.historical_loader import find_csv, load_and_merge
from strategies.candle_confirmation import CandleConfirmationStrategy

logging.basicConfig(level=logging.ERROR)
sys.stdout.reconfigure(line_buffering=True)

INITIAL_BALANCE = 10_000.0
RR_RATIO = 2.5

FRACTAL_N = [1, 2, 3]
TREND_TFS = [None, 'H4', 'D1']
EMA_PAIRS = [(10, 20), (20, 50)]
EMA_SEP = [0.0, 0.0005, 0.001]
MIN_ENGULF_RANGE_PIPS = [8.0, 12.0, 15.0]
MIN_ENGULF_BODY_PCT = [0.4, 0.5, 0.6]
TP_RANGE_PCT = [1.0, 1.25, 1.5]
SL_RR_RATIO = [1.25, 1.5, 2.0]
MIN_SL_PIPS = [8.0, 10.0, 12.0]

FIELDNAMES = [
    'fractal_n', 'tf_trend', 'ema_fast', 'ema_slow', 'ema_sep_pct',
    'min_engulf_range_pips', 'min_engulf_body_pct', 'tp_range_pct',
    'sl_rr_ratio', 'min_sl_pips', 'trades', 'win_rate', 'total_r',
    'pf', 'expectancy', 'max_dd_r', 'best_win_streak', 'worst_loss_streak',
]


def main():
    parser = argparse.ArgumentParser(description='Candle Confirmation broad symbol sweep.')
    parser.add_argument('--symbol', default='EURUSD', help='Symbol to sweep, default EURUSD')
    args = parser.parse_args()
    symbol = args.symbol.upper()
    output_csv = f"output/candle_confirmation_{symbol.lower()}_sweep.csv"

    os.makedirs('output', exist_ok=True)
    combos = _build_combos()
    done_keys = _load_done_keys(output_csv)

    print(f"Loading {symbol} bars...")
    csv_paths = []
    for tf in ('D1', 'H4', 'H1', 'M5'):
        paths = find_csv(symbol, tf)
        if not paths:
            print(f"WARNING: no CSV found for {symbol} {tf}")
        csv_paths.extend(paths)
    bars = load_and_merge(csv_paths)
    print(f"Loaded {len(bars):,} bars; {len(combos):,} combos total; {len(done_keys):,} already done")

    write_header = not os.path.exists(output_csv) or os.path.getsize(output_csv) == 0
    with open(output_csv, 'a', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        if write_header:
            writer.writeheader()

        best = None
        completed_this_run = 0
        for i, params in enumerate(combos, start=1):
            key = _combo_key(params)
            if key in done_keys:
                continue

            row = {**params, **_run_combo(symbol, bars, params)}
            writer.writerow(row)
            fh.flush()
            completed_this_run += 1

            if best is None or row['total_r'] > best['total_r']:
                best = row

            if completed_this_run % 100 == 0:
                best_total = best['total_r'] if best else 0.0
                print(
                    f"{i:,}/{len(combos):,} scanned; "
                    f"{completed_this_run:,} new; best TotalR {best_total:+.1f}"
                )

    _print_results(output_csv)


def _build_combos():
    combos = []
    shared_grid = list(itertools.product(
        FRACTAL_N,
        MIN_ENGULF_RANGE_PIPS,
        MIN_ENGULF_BODY_PCT,
        TP_RANGE_PCT,
        SL_RR_RATIO,
        MIN_SL_PIPS,
    ))

    for fractal_n, range_pips, body_pct, tp_pct, sl_rr, min_sl in shared_grid:
        combos.append({
            'fractal_n': fractal_n,
            'tf_trend': '',
            'ema_fast': 0,
            'ema_slow': 0,
            'ema_sep_pct': 0.0,
            'min_engulf_range_pips': range_pips,
            'min_engulf_body_pct': body_pct,
            'tp_range_pct': tp_pct,
            'sl_rr_ratio': sl_rr,
            'min_sl_pips': min_sl,
        })

    for tf_trend in ('H4', 'D1'):
        for ema_fast, ema_slow in EMA_PAIRS:
            for ema_sep in EMA_SEP:
                for fractal_n, range_pips, body_pct, tp_pct, sl_rr, min_sl in shared_grid:
                    combos.append({
                        'fractal_n': fractal_n,
                        'tf_trend': tf_trend,
                        'ema_fast': ema_fast,
                        'ema_slow': ema_slow,
                        'ema_sep_pct': ema_sep,
                        'min_engulf_range_pips': range_pips,
                        'min_engulf_body_pct': body_pct,
                        'tp_range_pct': tp_pct,
                        'sl_rr_ratio': sl_rr,
                        'min_sl_pips': min_sl,
                    })

    return combos


def _load_done_keys(output_csv):
    if not os.path.exists(output_csv):
        return set()
    with open(output_csv, newline='') as fh:
        return {_combo_key(row) for row in csv.DictReader(fh)}


def _combo_key(params):
    return tuple(str(params[name]) for name in FIELDNAMES[:10])


def _run_combo(symbol, bars, params):
    tf_trend = params['tf_trend'] or None
    strategy = CandleConfirmationStrategy(
        tf_bias='H1',
        tf_entry='M5',
        fractal_n=int(params['fractal_n']),
        retrace_pct=0.5,
        tp_range_pct=float(params['tp_range_pct']),
        sl_rr_ratio=float(params['sl_rr_ratio']),
        sl_mode='symmetric',
        require_fvg=True,
        min_sl_pips=float(params['min_sl_pips']),
        tf_trend=tf_trend,
        ema_fast=int(params['ema_fast']) if tf_trend else 20,
        ema_slow=int(params['ema_slow']) if tf_trend else 50,
        ema_sep_pct=float(params['ema_sep_pct']),
        min_engulf_range_pips=float(params['min_engulf_range_pips']),
        min_engulf_body_pct=float(params['min_engulf_body_pct']),
        close_extreme_pct=1.0,
        require_engulf_color=False,
        pip_sizes=dict(config.PIP_SIZE),
    )
    engine = BacktestEngine(initial_balance=INITIAL_BALANCE, rr_ratio=RR_RATIO)
    engine.add_strategy(strategy, symbols=[symbol])

    with contextlib.redirect_stdout(io.StringIO()):
        for bar in bars:
            closed_trades = engine.execution.check_fills(bar)
            for trade in closed_trades:
                engine.portfolio.record_close(
                    trade['symbol'], trade['pnl'], trade.get('strategy_name', '')
                )
                engine.trade_logger.log_close(trade['ticket'], trade)
                engine.event_engine.notify_trade_closed(trade)
            engine.event_engine.process_bar(bar)

    return _metrics(engine.execution.get_closed_trades())


def _metrics(trades):
    n = len(trades)
    if n == 0:
        return {
            'trades': 0, 'win_rate': 0.0, 'total_r': 0.0, 'pf': 0.0,
            'expectancy': 0.0, 'max_dd_r': 0.0,
            'best_win_streak': 0, 'worst_loss_streak': 0,
        }

    wins = sum(1 for t in trades if t['result'] == 'WIN')
    total_r = sum(t['r_multiple'] for t in trades)
    gross_profit = sum(t['r_multiple'] for t in trades if t['result'] == 'WIN')
    gross_loss = abs(sum(t['r_multiple'] for t in trades if t['result'] == 'LOSS'))

    peak = running = max_dd = 0.0
    best_win = worst_loss = cur_win = cur_loss = 0
    for trade in trades:
        running += trade['r_multiple']
        peak = max(peak, running)
        max_dd = max(max_dd, peak - running)
        if trade['result'] == 'WIN':
            cur_win += 1
            cur_loss = 0
            best_win = max(best_win, cur_win)
        else:
            cur_loss += 1
            cur_win = 0
            worst_loss = max(worst_loss, cur_loss)

    return {
        'trades': n,
        'win_rate': round(wins / n * 100.0, 1),
        'total_r': round(total_r, 1),
        'pf': round(gross_profit / gross_loss, 2) if gross_loss else 0.0,
        'expectancy': round(total_r / n, 3),
        'max_dd_r': round(max_dd, 1),
        'best_win_streak': best_win,
        'worst_loss_streak': worst_loss,
    }


def _print_results(output_csv):
    if not os.path.exists(output_csv):
        return
    with open(output_csv, newline='') as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return
    for row in rows:
        for key in FIELDNAMES[10:]:
            row[key] = float(row[key])

    def print_table(title, sorted_rows):
        print(f"\n{title}")
        print("| frac | trend | ema | sep | range | body | tp | sl_rr | min_sl | trades | WR | Total R | PF | Exp | MaxDD |")
        print("|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for r in sorted_rows[:20]:
            ema = '' if not r['tf_trend'] else f"{r['ema_fast']}/{r['ema_slow']}"
            print(
                f"| {r['fractal_n']} | {r['tf_trend'] or 'off'} | {ema or '-'} | "
                f"{float(r['ema_sep_pct']):.4f} | {float(r['min_engulf_range_pips']):.0f} | "
                f"{float(r['min_engulf_body_pct']):.1f} | {float(r['tp_range_pct']):.2f} | "
                f"{float(r['sl_rr_ratio']):.2f} | {float(r['min_sl_pips']):.0f} | "
                f"{int(r['trades'])} | {r['win_rate']:.1f}% | {r['total_r']:+.1f} | "
                f"{r['pf']:.2f} | {r['expectancy']:+.3f} | {r['max_dd_r']:.1f} |"
            )

    print_table("TOP 20 BY TOTAL R", sorted(rows, key=lambda r: r['total_r'], reverse=True))
    min_trades = [r for r in rows if r['trades'] >= 100]
    print_table(
        "TOP 20 BY EXPECTANCY (MIN 100 TRADES)",
        sorted(min_trades, key=lambda r: (r['expectancy'], r['total_r']), reverse=True),
    )


if __name__ == '__main__':
    main()
