"""Check higher-timeframe coverage against available M5; never repair prices."""
from pathlib import Path
import pandas as pd

from data.historical_loader import find_csv
from data.histdata_provenance import file_hash, write_json
from research_ema_fib_tracking import OUT
import config


def frame(source, symbol, tf):
    files = find_csv(symbol,tf,data_source=source)
    data = pd.concat([pd.read_csv(p,parse_dates=['time']) for p in files]).set_index('time').sort_index()
    data = data.loc[(data.index >= '2020-01-01') & (data.index < '2026-07-15')]
    assert data.index.is_unique
    assert not data[['open','high','low','close']].isna().any().any()
    return data


def main():
    results = []
    for source in ('dukascopy','histdata'):
        for symbol in config.SYMBOLS:
            m5 = frame(source,symbol,'M5')
            for tf,rule,complete in [('H1','h',12),('D1','D',288)]:
                higher = frame(source,symbol,tf)
                grouped = m5.groupby(m5.index.floor(rule)).agg(
                    open=('open','first'),high=('high','max'),low=('low','min'),close=('close','last'),count=('close','size'))
                if tf == 'D1':
                    higher = higher.loc[higher.index.dayofweek < 5]
                    grouped = grouped.loc[grouped.index.dayofweek < 5]
                missing = grouped.index.difference(higher.index)
                complete_missing = grouped.loc[missing].query('count == @complete')
                common = grouped.index.intersection(higher.index)
                same = (grouped.loc[common,['open','high','low','close']].round(8) ==
                        higher.loc[common,['open','high','low','close']].round(8)).all(axis=1)
                row = dict(source=source,symbol=symbol,timeframe=tf,
                    higher_bars=len(higher),m5_buckets=len(grouped),
                    missing_higher_despite_m5=len(missing),missing_despite_complete_m5=len(complete_missing),
                    common_ohlc_differ=int((~same).sum()),
                    missing_complete_by_year={str(k):int(v) for k,v in complete_missing.groupby(complete_missing.index.year).size().items()},
                    examples=[str(t) for t in complete_missing.index[:12]])
                results.append(row)
    paths = [p for s in ('dukascopy','histdata') for sym in config.SYMBOLS
             for tf in ('M5','H1','D1') for p in find_csv(sym,tf,data_source=s)]
    write_json(OUT/'coverage.json',dict(start='2020-01-01',end_exclusive='2026-07-15',
        note='Availability check, not proof of tick completeness. D1 weekday filter matches replay. No CSV was changed.',
        input_hashes={p:file_hash(p) for p in paths},results=results))
    for row in results:
        if row['missing_despite_complete_m5']:
            print(row)


if __name__ == '__main__':
    main()
