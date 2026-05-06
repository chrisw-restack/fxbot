"""Compare current live strategy configs across historical data sources."""

from __future__ import annotations

import json
import re
import subprocess


SUITE = [
    (
        'EmaFibRetracement',
        'ema_fib_retracement',
        ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDJPY', 'USDCAD', 'USDCHF'],
    ),
    (
        'EmaFibRunning',
        'ema_fib_running',
        ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDJPY', 'USDCAD', 'USDCHF'],
    ),
    (
        'Engulfing',
        'three_line_strike',
        ['EURUSD', 'AUDUSD', 'USDCAD'],
    ),
    (
        'IMS_H4_M15',
        'ims_h4_m15',
        ['USDJPY', 'XAUUSD', 'EURAUD', 'CADJPY', 'USDCAD', 'AUDUSD', 'EURUSD', 'GBPCAD', 'GBPUSD'],
    ),
    (
        'IMSRev_H4_M15',
        'ims_reversal_h4_m15',
        ['GBPNZD', 'AUDUSD', 'US30', 'USDCHF', 'XAUUSD', 'AUDJPY', 'AUDCAD', 'USDCAD'],
    ),
]

FIELDS = {
    'ending_balance': r'Ending balance\s+\$([0-9,]+\.\d+)',
    'total_trades': r'Total trades\s+(\d+)',
    'win_rate': r'Win rate\s+([0-9.]+%)\s+\((\d+)W / (\d+)L\)',
    'total_r': r'Total R\s+([+-]?[0-9.]+R)',
    'profit_factor': r'Profit factor\s+([0-9.]+)',
    'expectancy': r'Expectancy\s+([+-]?[0-9.]+R)',
    'max_drawdown': r'Max drawdown\s+([0-9.]+R)\s+\(([0-9.]+%)\)',
    'worst_loss_streak': r'Worst loss streak\s+(\d+)',
}


def parse_summary(text: str) -> dict[str, str]:
    row = {}
    for key, pattern in FIELDS.items():
        match = re.search(pattern, text)
        if not match:
            row[key] = 'NA'
            continue
        if key == 'win_rate':
            row[key] = match.group(1)
            row['wins'] = match.group(2)
            row['losses'] = match.group(3)
        elif key == 'max_drawdown':
            row[key] = match.group(1)
            row['max_drawdown_pct'] = match.group(2)
        else:
            row[key] = match.group(1)
    return row


def main() -> None:
    results = []
    for strategy_name, strategy_key, symbols in SUITE:
        for source in ['dukascopy', 'histdata']:
            cmd = [
                'python', 'run_backtest.py', strategy_key,
                '--data-source', source,
                '--symbols', *symbols,
                '--start-date', '2016-01-03',
                '--end-date', '2026-03-19',
            ]
            print(f'RUNNING {strategy_name} {source}', flush=True)
            proc = subprocess.run(cmd, capture_output=True, text=True)
            text = proc.stdout + '\n' + proc.stderr
            row = {
                'strategy': strategy_name,
                'source': source,
                'returncode': proc.returncode,
                'missing_csv': '; '.join(sorted(set(re.findall(r'WARNING: No CSV found for ([^\n]+)', text)))),
            }
            row.update(parse_summary(text))
            results.append(row)

    print('RESULTS_JSON_START')
    print(json.dumps(results, indent=2))
    print('RESULTS_JSON_END')


if __name__ == '__main__':
    main()
