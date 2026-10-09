"""Write the connection, coverage and execution-specification findings."""
import json
from pathlib import Path

import pandas as pd

from data.histdata_provenance import file_hash, write_json

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'output/exness_inspection_20261001_full'
QUOTES = ROOT/'output/exness_inspection_20261001_quotes'


def main():
    data = json.loads((OUT/'inspection.json').read_text())
    quality = json.loads((OUT/'quality.json').read_text())
    quotes = json.loads((QUOTES/'inspection.json').read_text())
    assert len(data['history'])==55
    assert file_hash(OUT/'inspection.json')==quality['input_manifest_sha256']
    assert all(file_hash(r['file'])==r['sha256'] for r in data['history'])
    probe = json.loads((OUT/'narrow_probe.json').read_text())
    assert probe[0]['returned_rows']==5 and probe[1]['returned_rows']==289
    ic = {}
    for symbol in data['symbols']:
        paths = list((ROOT/'data/historical/mt5_icmarkets_utc').glob(symbol+'_M5_*.csv'))
        if paths:
            assert len(paths)==1
            series = pd.read_csv(paths[0], usecols=['time'], parse_dates=['time'])['time']
            ic[symbol] = dict(first=str(series.min()), last=str(series.max()), bars=len(series),
                yearly_counts={str(k):int(v) for k,v in series.dt.year.value_counts().sort_index().items()},
                input_sha256=file_hash(paths[0]), file=str(paths[0]))
    write_json(OUT/'icmarkets_coverage_comparison.json',ic)
    lines = ['# Exness demo connection and history inspection, 1 October 2026', '',
        'Connected to the explicitly requested `C:\\Program Files\\MetaTrader 5 EXNESS\\terminal64.exe`. '
        'Confirmed demo account 81753094, server `Exness-MT5Trial10`, USD currency, '
        '$500 virtual balance, 1:500 account leverage, and MT5 retail hedging mode. '
        'Symbols are in `Raw\\Forex` and `Raw\\Indices`, consistent with Raw Spread. '
        'No credentials were loaded from `.env`, no account login was requested, and '
        'no orders, preflights, cancellations or bot configuration changes were made.', '',
        '## Download', '',
        f"Saved 55 raw OHLC files across 11 instruments and M5/M15/H1/H4/D1, containing "
        f"{sum(r['bars'] for r in data['history']):,} rows. Requested January 2008 through "
        'July 14, 2026; completed bars only. The July 15 research boundary excludes later '
        'history already protected for forward evaluation. Current quotes were sampled '
        'only for a cost inspection, not parameter selection.', '',
        'The initial terminal chart limit was 100,000 bars. After the user changed it and '
        f"restarted the terminal, the full snapshot reported {data['maxbars']:,}. "
        'No full request reached that limit. Python disconnected after each collection '
        'without closing MT5. All raw CSV SHA256 hashes match the recorded manifest.', '',
        '## The early dates are misleading', '',
        'Exness returns higher-timeframe history under lower-timeframe requests in the '
        'older section of this server’s archive. For EURUSD, every one of the 1,050 M5 '
        'records before 2020 exactly matches the corresponding D1 OHLC and tick volume. '
        'The old M5 request contains one bar per day, then hourly bars, before regularly '
        'populated five-minute data begins. Success from the API does not certify resolution.', '',
        'A separate EURUSD M5 request for January 7–12, 2019 still returns just five daily '
        'records. A request for July 13–14, 2021 returns 289 genuine five-minute grid '
        'timestamps including the endpoint. The export removes the endpoint, leaving '
        '288 completed five-minute bars for that day. These probes confirm the discrepancy '
        'is in the MT5 response, not our UTC conversion.', '',
        'An isolated nonmatching M5 record appears in June 2021 for several symbols, '
        'but hourly records continue afterward. The audit therefore also checks for '
        'five consecutive observed weekdays with at least 150 M5, 50 M15, 16 H1, or '
        'four H4 records per day. This is a coverage diagnostic, not proof of tick '
        'provenance or gap-free data. Holidays, maintenance, and short sessions still '
        'need consideration. July 13, 2021 is a conservative common lower-timeframe '
        'boundary for a later comparison, subject to the remaining gap audit.', '',
        '| Instrument | First returned D1 | First dense M5 window | First dense M15 window | First dense H1 window | First dense H4 window |',
        '|---|---|---|---|---|---|']
    for symbol in data['symbols']:
        q = quality['symbols'][symbol]
        dates = [q['D1']['reported_first'][:10]]+[q[tf]['first_dense_weekday_window'][:10] for tf in ('M5','M15','H1','H4')]
        lines.append('| '+symbol+' | '+' | '.join(dates)+' |')
    lines += ['', 'Raw files stay in `output/exness_inspection_20261001_full/history`, '
        'separate from approved backtest datasets. The loader now refuses Exness files '
        'without an explicit `approved_native_resolution` review status. No raw file '
        'was promoted or replayed. A future prepared dataset must remove the coarse '
        'prefix, document any remaining missing sessions, preserve broker-native '
        'Sunday candles, and retain source hashes.', '',
        '## Comparison with our IC Markets files', '',
        '| Instrument | IC Markets stored M5 first timestamp | Exness first dense M5 window |',
        '|---|---|---|']
    for symbol in data['symbols']:
        first = ic[symbol]['first'][:10] if symbol in ic else 'No local export'
        lines.append(f"| {symbol} | {first} | {quality['symbols'][symbol]['M5']['first_dense_weekday_window'][:10]} |")
    lines += ['', 'IC Markets EURUSD/GBPUSD exports contain roughly 74,500 M5 bars per '
        'full year from 2016, whereas older Exness M5 years contain roughly 300 daily '
        'records. USDCAD gains several years of detailed history versus our IC Markets '
        'file beginning January 2025. Exness also supplies EURAUD/CADJPY/GBPCAD, for '
        'which no local IC Markets M5 export is present. It is useful additional '
        'evidence, but this demo server does not provide universally longer intraday history. '
        'These findings do not establish limits for other Exness servers or the public tick archive.', '',
        '## Short spread sample and contract details', '',
        'Sampled eleven instruments once per second for 60 seconds, excluding quotes '
        'older than 30 seconds. Values below use the project’s FX pip convention. '
        'USTEC is shown in index price points. Commission is not included. The sample '
        'was around 10:30 UTC, before the NY cash open, and cannot establish typical '
        'entry-session, news or rollover costs. All sixty polls need not be distinct ticks.', '',
        '| Instrument | Mean spread | P95 spread | Units | Distinct ticks | Minimum lot | Lot step |',
        '|---|---:|---:|---|---:|---:|---:|']
    for symbol, detail in data['symbols'].items():
        p, s = detail['properties'], quotes['spread_sample']['symbols'][symbol]
        lines.append(f"| {symbol} | {s['mean']:.3f} | {s['p95']:.3f} | "
                     f"{'index points' if symbol=='USTEC' else 'FX pips'} | {s['distinct_ticks']} | {p['volume_min']:g} | {p['volume_step']:g} |")
    lines += ['', 'All inspected instruments report zero static stop and freeze levels. '
        'This does not guarantee that every request will be accepted. Market execution '
        'and actual slippage were not tested because no trades were submitted.', '',
        'Exness publishes Raw Spread commission up to $3.50 per lot per side for most '
        'instruments. Instrument-specific values must be checked; commission is not '
        'available in the inspected MT5 symbol properties. '
        '[Raw Spread account specifications](https://get.exness.help/hc/en-us/articles/17537767270556-Raw-Spread-account).', '',
        'Exness’s published USTEC Raw Spread fee is $0.3125 per lot per side, or $0.625 '
        'round trip. With the inspected one-unit contract and $1 per index point per '
        'lot, that is 0.625 index points before spread. Adding the short 0.06-point '
        'spread sample gives an illustrative 0.685-point round-trip cost. This is '
        'not a verified realized fee or an entry-session average. Our IC Markets '
        'simulation currently assumes a one-point spread and no index commission. '
        '[Exness index specifications](https://get.exness.help/hc/en-us/articles/17854383867548-Indices).', '',
        'USTEC minimum volume is 0.05 lot with 0.01 steps; one lot represents one '
        'index unit. `USTEC_x100` also exists with a 100-unit contract and was deliberately '
        'not selected. At the current $500 balance, 0.5% planned risk is $2.50. A '
        '100-point USTEC stop at minimum 0.05 lot risks $5 before costs, so the '
        'existing risk cap would reject it. The smallest lot can therefore reduce '
        'trade counts on this account; higher leverage does not reduce stop-loss risk.', '',
        'USTEC reports swap mode 1, points, long swap -694.9 and short swap zero, '
        'with Friday as its triple-swap day. At its 0.01 point size and one-unit '
        'contract, the displayed long rate corresponds to about -$6.949 per lot '
        'for an ordinary rollover, before account-specific exemptions or changes. '
        'That is larger than the quoted round-trip commission, so overnight Failed2 '
        'positions need financing in an Exness replay. No broker debit was observed.', '',
        '## Code and validation', '',
        'Added an explicitly targeted, demo-only data collector and resolution audit. '
        'No `.env` or trading settings changed. The loader recognizes approved Exness '
        'native sessions and preserves their Sunday D1 candles. Unreviewed Exness '
        'exports fail rather than entering a backtest silently. All 240 tests pass, '
        'including six focused collection/audit checks. No strategy performance '
        'claim follows from this collection.', '',
        'The production feed and execution history conversion still assume IC Markets '
        'UTC+2/+3. Exness timestamps are GMT+0 and were exported without that shift. '
        'H4/D1 candle boundaries also differ; a future migration needs a broker profile '
        'for both feed and execution reconciliation, cost calibration, and a frozen '
        'strategy comparison. The current bot must not be pointed at Exness unchanged.', '',
        '## Decision and next step', '',
        'Keep Exness as a research data source for now. Prepare a reviewed common '
        'post-July-2021 dataset, then compare frozen parameters against IC Markets '
        'over matching dates with broker-specific costs and daily-session boundaries. '
        'Collect longer spread samples in the actual entry windows before judging '
        'trading conditions. The public tick archive may provide additional history, '
        'but it has not been downloaded or audited in this task. No bot migration, '
        'strategy optimization, real-money execution, commit or push occurred.', '',
        '## Artifacts and reproduction', '',
        '- `output/exness_inspection_20261001_full/inspection.json`: identity, properties, raw coverage, CSV hashes.',
        '- `output/exness_inspection_20261001_full/quality.json`: coarse matches, density boundaries, monthly counts, short weekday sessions.',
        '- `output/exness_inspection_20261001_full/narrow_probe.json`: fresh old/recent M5 requests.',
        '- `output/exness_inspection_20261001_quotes/quote_samples.csv`: actual bid/ask observations.',
        '- `output/exness_inspection_20261001_quotes/inspection.json`: quote sample statistics.',
        '- `output/exness_inspection_20261001_initial`: preliminary daily download, before the full snapshot.', '',
        'Repeat the collection with a fresh output directory using '
        '`python inspect_exness_mt5.py --expected-login 81753094 --expected-server '
        'Exness-MT5Trial10 --download`. Use `--sample-seconds 60` for a separate '
        'short quote sample. The runner never switches accounts; it refuses a '
        'mismatched terminal, account, server or real-money account.']
    path = ROOT/'strategy_log/exness_inspection_20261001.md'
    path.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(path)


if __name__ == '__main__':
    main()
