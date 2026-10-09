"""Read-only targeted IFX archive and hole checks after the full download."""
from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd

from inspect_ifx_mt5 import TERMINAL, SYMBOLS, verify_terminal
from data.histdata_provenance import file_hash, write_json

ROOT=Path('output/ifx_inspection_20261008')


def main():
    import MetaTrader5 as mt5
    report=json.loads((ROOT/'inspection.json').read_text())
    identity=report['account']
    if not mt5.initialize(TERMINAL,timeout=20000):
        raise RuntimeError(mt5.last_error())
    checks=[]
    try:
        terminal,_=verify_terminal(mt5,TERMINAL,identity['login'],identity['server'])
        jobs=[(s,'M5','2010-01-04','2010-01-09','before_archive') for s in SYMBOLS]
        jobs += [(s,'M5','2020-01-06','2020-01-11','coarse_prefix') for s in ('EURUSD','CADJPY','USTEC')]
        jobs += [(s,tf,start,end,'intraday_hole') for s in ('EURUSD','CADJPY') for tf in ('M1','M5')
            for start,end in [('2023-11-17','2023-11-18'),('2024-08-02','2024-08-03')]]
        for symbol,tf,start,end,purpose in jobs:
            verify_terminal(mt5,TERMINAL,identity['login'],identity['server'])
            print('[PROBE]',symbol,tf,start,purpose,flush=True)
            a=datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
            b=datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
            rates=mt5.copy_rates_range(SYMBOLS[symbol],getattr(mt5,'TIMEFRAME_'+tf),a,b)
            error=mt5.last_error()
            verify_terminal(mt5,TERMINAL,identity['login'],identity['server'])
            row=dict(symbol=symbol,broker_symbol=SYMBOLS[symbol],timeframe=tf,start=start,end=end,
                purpose=purpose,last_error=error,returned_rows=len(rates) if rates is not None else 0)
            if rates is not None and len(rates):
                frame=pd.DataFrame(rates)
                frame['time']=pd.to_datetime(frame['time'],unit='s')
                frame=frame.loc[frame['time']<pd.Timestamp(end)]
                path=ROOT/'probes'/f'{symbol}_{tf}_{start}_{purpose}.csv'
                path.parent.mkdir(exist_ok=True)
                frame.to_csv(path,index=False)
                row.update(file=str(path),sha256=file_hash(path),rows=len(frame),
                    first=str(frame['time'].iloc[0]) if len(frame) else None,
                    last=str(frame['time'].iloc[-1]) if len(frame) else None)
                if purpose=='intraday_hole':
                    frame=frame.set_index('time')
                    delta=frame.index.to_series().diff().dt.total_seconds()/60
                    row['gaps_at_least_60_minutes']=[dict(previous=str(frame.index[i-1]),next=str(frame.index[i]),elapsed_minutes=float(delta.iloc[i]))
                        for i in range(1,len(frame)) if delta.iloc[i]>=60]
                write_json(str(path)+'.meta.json',dict(provider='IFX',time_basis='ifx_server_unreviewed',
                    research_status='raw_unreviewed',csv_sha256=row['sha256'],symbol=symbol,timeframe=tf))
            checks.append(row)
            write_json(ROOT/'archive_probes.json',dict(checks=checks,terminal_maxbars=terminal.maxbars,
                collected_at_utc=datetime.now(timezone.utc).isoformat(),script_sha256=file_hash(__file__),
                note='Empty old requests show no history returned for these tested dates, not proof '
                     'that other server archives cannot exist. M1 gap probes do not replace full M1 collection.'))
            print(json.dumps(row),flush=True)
    finally:
        mt5.shutdown()


if __name__=='__main__':
    main()
