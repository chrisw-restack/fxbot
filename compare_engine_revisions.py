"""Compare frozen demo settings across engine revisions on identical UTC bars.

The baseline directory must contain an exported revision of this repository.
Runs are sequential and never connect to MT5. USA100 bars are relabeled USTEC
for a Dukascopy comparison; this is not broker-native revalidation.
"""
import argparse
import csv
import gzip
import hashlib
import json
import logging
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def summary(trades, config):
    values = []
    for trade in trades:
        risk = abs(trade['entry_price']-trade['sl']) / config.PIP_SIZE[trade['symbol']]
        risk *= config.PIP_VALUE_USD[trade['symbol']] * trade['lot_size']
        values.append(trade.get('net_r', trade['pnl'] / risk if risk else 0.0))
    peak = running = drawdown = 0.0
    wins = losses = best = worst = 0
    for value in values:
        running += value
        peak = max(peak, running)
        drawdown = max(drawdown, peak-running)
        wins, losses = (wins+1, 0) if value > 0 else (0, losses+1)
        best, worst = max(best, wins), max(worst, losses)
    gain = sum(r for r in values if r > 0)
    loss = -sum(r for r in values if r < 0)
    return dict(trades=len(trades), win_rate=100*sum(r > 0 for r in values)/len(values) if values else 0,
                net_r=sum(values), profit_factor=gain/loss if loss else None,
                expectancy=sum(values)/len(values) if values else 0, max_dd_r=drawdown,
                best_win_streak=best, worst_loss_streak=worst)


def run_child(root, output, label):
    sys.path.insert(0, str(root))
    import config
    from backtest_engine import BacktestEngine
    from live_config import create_live_strategy_specs, live_risk_pct_overrides
    from data.historical_loader import bar_close_time
    from models import BarEvent
    logging.disable(logging.CRITICAL)
    manifest = json.loads((output/'manifest.json').read_text())
    start, end = datetime.fromisoformat(manifest['start']), datetime.fromisoformat(manifest['end'])
    with gzip.open(output/'bars.csv.gz', 'rt', newline='') as stream:
        bars = [BarEvent(r['symbol'], r['timeframe'], datetime.fromisoformat(r['timestamp']),
                         *[float(r[k]) for k in ('open','high','low','close','volume')])
                for r in csv.DictReader(stream)]
    engine = BacktestEngine(initial_balance=10000, rr_ratio=2.5,
                            risk_pct_overrides=live_risk_pct_overrides(),
                            max_open_trades=config.MAX_OPEN_TRADES,
                            max_daily_loss_pct=config.MAX_DAILY_LOSS_PCT)
    specs = create_live_strategy_specs()
    for strategy, symbols in specs:
        engine.add_strategy(strategy, symbols)
    if hasattr(engine, 'replay'):
        engine.replay(bars, start_date=start, end_date=end)
    else:
        for bar in bars:
            if bar_close_time(bar) > end:
                continue
            if bar_close_time(bar) <= start:
                engine.event_engine.warmup_bar(bar)
                continue
            for trade in engine.execution.check_fills(bar):
                engine.portfolio.record_close(trade['symbol'], trade['pnl'], trade['strategy_name'])
                engine.trade_logger.log_close(trade['ticket'], trade)
                engine.event_engine.notify_trade_closed(trade)
            engine.event_engine.process_bar(bar)
    trades = engine.execution.get_closed_trades()
    result = dict(suite=summary(trades, config),
                  strategies={s.NAME: summary([t for t in trades if t['strategy_name']==s.NAME], config) for s, _ in specs},
                  directions={d: summary([t for t in trades if t['direction']==d], config) for d in ('BUY','SELL')},
                  ending_balance=engine.execution.get_account_balance(),
                  open_orders=len(engine.execution.get_open_positions()),
                  marked_equity=engine.execution.get_equity() if hasattr(engine.execution, 'get_equity') else None,
                  max_equity_dd_pct=getattr(engine.execution, 'max_equity_drawdown_pct', None))
    (output/f'{label}.json').write_text(json.dumps(result, indent=2, allow_nan=False))
    with (output/f'{label}_trades.json').open('w') as stream:
        json.dump(trades, stream, default=str, allow_nan=False)
    print(label, json.dumps(result['suite']), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-root', type=Path)
    parser.add_argument('--start', default='2026-01-01')
    parser.add_argument('--end', default='2026-08-01')
    parser.add_argument('--output', type=Path, default=Path('output/engine_revision_comparison'))
    parser.add_argument('--child-root', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--label', help=argparse.SUPPRESS)
    args = parser.parse_args()
    output = args.output.resolve()
    if args.child_root:
        return run_child(args.child_root.resolve(), output, args.label)
    if not args.baseline_root:
        parser.error('--baseline-root is required')
    import config
    from live_config import create_live_strategy_specs
    from data.historical_loader import find_csv, load_and_merge
    root = Path(__file__).resolve().parent
    baseline = args.baseline_root.resolve()
    output.mkdir(parents=True, exist_ok=True)
    specs = create_live_strategy_specs()
    aliases = {'USTEC': 'USA100'}
    pairs = {(aliases.get(symbol, symbol), tf) for s, symbols in specs for symbol in symbols for tf in s.TIMEFRAMES}
    paths = []
    for symbol, tf in sorted(pairs):
        found = find_csv(symbol, tf, path=str(root/'data/historical'))
        if not found:
            raise FileNotFoundError(f'Missing Dukascopy data: {symbol} {tf}')
        paths.extend(found)
    manifest = dict(start=args.start, end=args.end, data_source='dukascopy', aliases=aliases,
                    warmup_days=180, baseline_root=str(baseline),
                    config_sha256=file_hash(root/'config.py'), live_config_sha256=file_hash(root/'live_config.py'),
                    sources=[dict(path=str(Path(p).resolve()), sha256=file_hash(p)) for p in paths])
    logging.disable(logging.CRITICAL)
    print(f'Loading {len(paths)} source files sequentially', flush=True)
    bars = load_and_merge(paths, start=datetime.fromisoformat(args.start)-timedelta(days=180),
                          end=datetime.fromisoformat(args.end), time_basis='utc')
    reverse = {v:k for k,v in aliases.items()}
    with gzip.open(output/'bars.csv.gz', 'wt', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(('symbol','timeframe','timestamp','open','high','low','close','volume'))
        for bar in bars:
            writer.writerow((reverse.get(bar.symbol,bar.symbol),bar.timeframe,bar.timestamp.isoformat(),
                             bar.open,bar.high,bar.low,bar.close,bar.volume))
    manifest['bar_count'] = len(bars)
    manifest['canonical_bars_sha256'] = file_hash(output/'bars.csv.gz')
    del bars
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2))
    for label, revision in [('before',baseline), ('after',root)]:
        print(f'Running {label}', flush=True)
        subprocess.run([sys.executable,str(Path(__file__).resolve()),'--child-root',str(revision),
                        '--output',str(output),'--label',label], check=True, cwd=root)


if __name__ == '__main__':
    main()
