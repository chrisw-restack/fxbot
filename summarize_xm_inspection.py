"""Summarize the completed XM collection without promoting raw data or trading."""
import json
from pathlib import Path

import pandas as pd

from data.histdata_provenance import file_hash, write_json

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'output/xm_inspection_20261001_final'
LATER_QUOTES = ROOT/'output/xm_inspection_20261001_later_quotes'


def month_ranges(values):
    periods = sorted(pd.Period(v,freq='M') for v in values)
    spans = []
    for period in periods:
        if spans and period==spans[-1][1]+1:
            spans[-1][1] = period
        else:
            spans.append([period,period])
    return ', '.join(str(a) if a==b else f'{a} through {b}' for a,b in spans)


def main():
    data = json.loads((OUT/'inspection.json').read_text())
    complete = json.loads((OUT/'complete.json').read_text())
    quality = json.loads((OUT/'quality.json').read_text())
    clock = json.loads((OUT/'clock_audit.json').read_text())
    assert complete['files']==55 and complete['hashes_match']
    assert file_hash(OUT/'inspection.json')==quality['input_manifest_sha256']==clock['input_manifest_sha256']
    assert all(file_hash(r['file'])==r['sha256'] for r in data['history'])
    first_quotes = pd.read_csv(OUT/'quote_samples.csv')
    later = json.loads((LATER_QUOTES/'inspection.json').read_text())
    assert later['account']==data['account'] and (LATER_QUOTES/'complete.json').exists()
    quotes = pd.read_csv(LATER_QUOTES/'quote_samples.csv')
    write_json(OUT/'quote_sample_comparison.json',dict(
        first_file=str(OUT/'quote_samples.csv'), first_sha256=file_hash(OUT/'quote_samples.csv'),
        later_file=str(LATER_QUOTES/'quote_samples.csv'), later_sha256=file_hash(LATER_QUOTES/'quote_samples.csv'),
        first_means=first_quotes.groupby('symbol').spread_project_pips.mean().to_dict(),
        later_means=quotes.groupby('symbol').spread_project_pips.mean().to_dict()))
    spread = {}
    for symbol, group in quotes.groupby('symbol'):
        # Round the current epoch offset to the nearest hour, then check freshness.
        # The separately measured historical rule still controls any UTC export.
        offset = round(float(group.epoch_minus_observed_seconds.median())/3600)*3600
        fresh = group.loc[(offset-group.epoch_minus_observed_seconds).between(0,30)]
        if fresh.empty:
            spread[symbol] = dict(error='No sufficiently fresh quote samples')
            continue
        values = fresh.spread_project_pips
        spread[symbol] = dict(samples=len(fresh), distinct_ticks=fresh.tick_time_msc.nunique(),
            mean=float(values.mean()), median=float(values.median()), p95=float(values.quantile(.95)),
            first_sample_utc=str(fresh.sampled_at_utc.min()),last_sample_utc=str(fresh.sampled_at_utc.max()))
    write_json(OUT/'spread_summary.json',spread)
    exness = json.loads((ROOT/'output/exness_inspection_20261001_full/quality.json').read_text())
    account = data['account']
    lines = ['# XM demo connection and history inspection, 1 October 2026', '',
        f"Connected to `{data['terminal_path']}\\terminal64.exe`, demo account "
        f"{account['login']} on `{account['server']}`. USD virtual balance "
        f"${account['balance']:,.0f}, account leverage 1:{account['leverage']}, retail hedging mode. "
        'FX instruments are in the Standard Ultra Low groups and have a `#` suffix. '
        '`US100Cash#` is the Nasdaq cash CFD mapped to the project research name `USTEC`. '
        'No credentials were read from `.env`, and no orders, preflights, cancellations, '
        'account changes, or bot deployment changes were made.', '',
        '## Collection and terminal limit', '',
        f"Collected 55 raw M5/M15/H1/H4/D1 CSVs for eleven instruments, "
        f"{complete['rows']:,} rows. Requested 2008-01-01 through 2026-07-15 in broker "
        'wall-clock time, retaining completed bars only. With the measured positive '
        'UTC offsets, this excludes post-July-14 UTC prices and conservatively omits '
        'the last few hours of July 14. The 2008 start is a requested boundary, '
        'not evidence that the broker has no earlier history.', '',
        'Initially the saved and reported chart setting was 100,000,000 bars, but '
        'existing timeframe caches remained limited to about 100,000 recent bars. '
        'Even after older minute-history cache files downloaded, a EURUSD M5 request '
        'for January 4-9, 2010 returned no rows. After verifying the XM account had '
        'zero positions and orders, only the XM terminal was closed gracefully and '
        'restarted. The identical request then returned 1,368 five-minute records. '
        'The final collection uses the restarted terminal; preliminary snapshots are '
        'retained separately and must not be used as coverage conclusions.', '',
        'All final raw CSV hashes match the manifest. The current account and '
        'terminal identity were checked throughout collection. API failures while '
        'history loaded were retried and are recorded per request.', '',
        '## Coverage and resolution', '',
        '| Instrument | Returned M5 first, server clock | M5 bars | First dense M5 window | IC Markets local M5 first, UTC | Exness first dense M5 window |',
        '|---|---|---:|---|---|---|']
    for symbol in data['symbols']:
        row = next(r for r in data['history'] if r['symbol']==symbol and r['timeframe']=='M5')
        q = quality['symbols'][symbol]['M5']
        ic_paths = list((ROOT/'data/historical/mt5_icmarkets_utc').glob(symbol+'_M5_*.csv'))
        ic_first = (str(pd.read_csv(ic_paths[0],usecols=['time'],nrows=1).time.iloc[0])[:10]
            if len(ic_paths)==1 else 'No single local M5 export')
        lines.append(f"| {symbol} | {row['first_server'][:10]} | {row['bars']:,} | "
            f"{q.get('first_dense_weekday_window')} | {ic_first} | {exness['symbols'][symbol]['M5'].get('first_dense_weekday_window')} |")
    lines += ['', 'The dense-window diagnostic requires five consecutive observed '
        'weekdays with at least 150 M5 bars per day. It is not a guarantee that later '
        'history is gap-free. OHLC and tick-volume equality against higher timeframes '
        'also detects coarse records inside the archive, not only at its beginning.', '',
        '| Instrument | Timeframe | Months flagged for substantial coarse records and low weekday density |',
        '|---|---|---|']
    for symbol, frames in quality['symbols'].items():
        for tf,q in frames.items():
            if q.get('suspect_coarse_months'):
                lines.append(f"| {symbol} | {tf} | {month_ranges(q['suspect_coarse_months'])} |")
    lines += ['', 'These are investigation flags, not an automatic approval or complete '
        'list of bad intervals. A low-count partial month or holiday can differ from '
        'a genuine hole. Native D1 weekend/short-session records also need review. '
        'Replay preparation must audit required timeframes together, split around '
        'unusable intervals, and re-establish warmup state. Do not fill holes with '
        'another broker or replay hourly bars as M5 candles.', '',
        '## Historical clock evidence', '',
        'The current tick epoch is approximately three hours ahead of UTC. Each '
        'available M5 reference comparison tests shifts of zero, two, and three '
        'hours using consecutive return rank correlation, split by month and '
        'European/US DST disagreement periods. Thresholds are at least 50 matched '
        'returns, correlation at least 0.8, and a 0.3 margin over the next offset. '
        'References and raw inputs are bound to their SHA256 hashes.', '',
        '| Instrument | Compatible rules in verified windows | Verified windows | Overlapping windows failing thresholds |',
        '|---|---|---:|---:|']
    for symbol,c in clock['symbols'].items():
        verified = sum(w['verified'] for w in c['windows'])
        failed = sum(not w['verified'] and max(s['pairs'] for s in w['scores'].values())>=50 for w in c['windows'])
        lines.append(f"| {symbol} | {', '.join(c['compatible_rules']) or 'No single rule fits verified periods'} | {verified} | {failed} |")
    lines += ['', 'Native UTC Dukascopy is the primary reference. Independent checks '
        'of EURUSD/GBPUSD/USDJPY in March and October-November 2016, March and '
        'October-November 2017, and March 2026 identify the European rule for XM. '
        'An initial comparison against the existing IC Markets UTC exports appeared '
        'to suggest a changing XM rule. The second reference corrected that '
        'interpretation: the IC Markets export appears one hour early in the '
        'March/October-November 2016 and March 2017 disagreement weeks. '
        '`independent_clock_check.json` records the native-UTC cross-check. '
        '`icmarkets_utc_reference_check.json` separately measures the IC Markets '
        'export against native UTC and records the required one-hour correction '
        'in those older weeks. '
        'The IC Markets historical conversion needs a separate provenance audit '
        'before old broker-specific session results are treated as settled. '
        'No IC Markets file or strategy result was changed in this task.', '',
        'The current IC Markets US-DST conversion must not be reused for XM. '
        'Earlier years without a UTC reference and failed overlapping windows '
        'remain unverified. No raw timestamp has been silently converted to UTC.', '',
        '## Quotes and contract constraints', '',
        'Two quote samples were taken after history collection. The first, '
        f"{first_quotes.sampled_at_utc.min()} through {first_quotes.sampled_at_utc.max()}, "
        'includes widening around 12:30 UTC. A later minute was collected separately, '
        f"{quotes.sampled_at_utc.min()} through {quotes.sampled_at_utc.max()}. "
        'The table uses the later sample; both raw sets and their hashes are retained. '
        'These are short '
        'demo quote observations, not proof of NY-open, news, rollover, or realized '
        'execution costs. An earlier sample was interrupted by history loading and '
        'is excluded from conclusions. FX spreads use project pips; USTEC uses '
        'index price points.', '',
        '| Instrument | Mean spread | P95 spread | Fresh samples / distinct ticks | Minimum lot / lot step | Swap mode |',
        '|---|---:|---:|---|---|---:|']
    for symbol,d in data['symbols'].items():
        s, p = spread[symbol], d['properties']
        lines.append(f"| {symbol} | {s.get('mean',float('nan')):.3f} | {s.get('p95',float('nan')):.3f} | "
            f"{s.get('samples',0)} / {s.get('distinct_ticks',0)} | {p['volume_min']:g} / {p['volume_step']:g} | {p['swap_mode']} |")
    lines += ['', 'FX contracts use 100,000 base-currency units per standard lot. '
        'Nasdaq cash uses a contract size of 1, USD profit currency, and a '
        '0.1 minimum lot and lot step. A 100-point entry-to-stop distance at '
        'the minimum lot implies $10 of gross price risk. Nasdaq cash uses '
        'a different minimum lot/step from Exness. Minimum lot and risk-rounding '
        'effects must be checked at the same research balance. High account leverage '
        'does not reduce the cash loss at the stop.', '',
        'The snapshot reports swap mode 0 for FX, despite nonzero swap-long/short '
        'fields. [MetaQuotes documents disabled swap mode]'
        '(https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants); '
        'those unused values must not be treated as '
        'charged overnight financing. Nasdaq cash reports enabled swap mode 3 '
        'in USD margin currency, displayed long debit $5.00 and short credit '
        '$0.74 per lot for ordinary rollover, and triple rollover on Friday. '
        'Account eligibility and actual charges have '
        'not been measured with trades.', '',
        'XM publishes spread-only pricing in its [trading-conditions help]'
        '(https://www.xm.com/help-center/trading-conditions/faq-why-are-rollover-rates-tripled). '
        'Our IC Markets FX backtests include $7 round-trip commission per standard '
        'lot. Compare total cost, not raw spreads alone. The source spread column '
        'is in MT5 integer points and is not necessarily the average spread at an '
        'entry. Historical fill-cost scenarios must be calibrated independently.', '',
        '## Research decision', '',
        'Keep the raw snapshot in `output/xm_inspection_20261001_final/history`, '
        'outside approved datasets. The loader refuses XM exports without a '
        'review status; the raw files also declare an unsupported unreviewed clock '
        'basis. No strategy replay, parameter optimization, broker migration, or '
        'real-money promotion was performed.', '',
        'Next, audit the existing IC Markets timestamp discrepancy and prepare '
        'provenance-bound UTC datasets with explicit valid intervals '
        'and native session handling, then compare frozen strategy parameters on '
        'matched broker windows with each broker’s full cost model. Extra early '
        'history may provide additional evidence, but another broker is not by '
        'itself an untouched strategy validation sample.', '',
        'Validation: all 249 unit tests pass; raw file hashes, terminal/account '
        'identity, old-window probes before/after restart, resolution diagnostics, '
        'native-UTC clock comparisons, and both post-download quote samples were checked.']
    (ROOT/'strategy_log/xm_inspection_20261001.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Wrote strategy_log/xm_inspection_20261001.md')


if __name__ == '__main__':
    main()
