"""Read-only price-feed and copied DEMO reconciliation for Candle GBPUSD.

Run with bundled Python for CSV analysis. No MT5 connection or source mutation.
"""
from collections import Counter
import csv
from datetime import datetime,timedelta
import json
from pathlib import Path
import pandas as pd
from audit_candle_usdjpy_review import Rows,money,digest

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/candle_gbpusd_review_20260930'


def save(name,data):
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/name).write_text(json.dumps(data,indent=2,default=str),encoding='utf-8')


def demo():
    report,journal=ROOT/'logs/ReportHistory-52775013.html',ROOT/'logs/trade_journal.csv'
    raw=report.read_bytes()
    parser=Rows()
    parser.feed(raw.decode('utf-16' if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8'))
    with journal.open(newline='',encoding='utf-8-sig') as stream:
        rows=list(csv.DictReader(stream))
    names={'CandleConfirmation_GBPUSD_H1_M5','CandleConfirmation_H1_M5'}
    relevant=[r for r in rows if r['symbol']=='GBPUSD' and r['strategy_name'] in names]
    closes=[r for r in relevant if r['event']=='CLOSE']
    close_by_ticket={r['ticket']:r for r in closes}
    assert len(close_by_ticket)==len(closes),'Duplicate journal closes require investigation.'
    section=None
    positions=[]
    for row in parser.rows:
        if len(row)==1 and row[0] in ('Positions','Orders','Deals','Open Positions','Working Orders'):
            section=row[0]
        if section=='Positions' and len(row)==14 and row[2]=='GBPUSD' and (
            row[1] in close_by_ticket or row[4].startswith('CandleConfirm')):
            positions.append(dict(ticket=row[1],comment=row[4],direction=row[3],
                open_time_broker=row[0],close_time_broker=row[9],entry=money(row[6]),
                sl=money(row[7]),tp=money(row[8]),commission=money(row[11]),swap=money(row[12]),
                profit=money(row[13]),net_pnl=sum(money(row[i]) for i in (11,12,13))))
    assert len(positions)==len({p['ticket'] for p in positions})
    matches=[]
    for p in positions:
        r=close_by_ticket.get(p['ticket'])
        if r:
            matches.append(dict(ticket=p['ticket'],difference=float(r['pnl'])-p['net_pnl'],
                journal_pnl=float(r['pnl']),report_net=p['net_pnl']))
    assert all(abs(m['difference'])<.011 for m in matches),'Net journal/broker P&L mismatch.'
    total=peak=dd=0.
    win_run=loss_run=max_win=max_loss=0
    for p in sorted(positions,key=lambda p:(p['close_time_broker'],p['ticket'])):
        total+=p['net_pnl']
        peak=max(peak,total)
        dd=max(dd,peak-total)
        win_run=win_run+1 if p['net_pnl']>0 else 0
        loss_run=loss_run+1 if p['net_pnl']<0 else 0
        max_win,max_loss=max(max_win,win_run),max(max_loss,loss_run)
    profit=sum(p['net_pnl'] for p in positions if p['net_pnl']>0)
    loss=-sum(p['net_pnl'] for p in positions if p['net_pnl']<0)
    errors=[]
    for r in relevant:
        if r['event']=='REJECTED':
            ctx=json.loads(r['context_json'] or '{}')
            errors.append(dict(time=r['journal_time_utc'],reason=r['reason'],
                execution_error=ctx.get('execution_error')))
    result=dict(input_hashes={str(p):digest(p) for p in (report,journal)},positions=positions,
        matches=matches,journal_closes=len(closes),unmatched_journal=[r['ticket'] for r in closes
            if r['ticket'] not in {p['ticket'] for p in positions}],
        unmatched_report=[p['ticket'] for p in positions if p['ticket'] not in close_by_ticket],
        summary=dict(trades=len(positions),wins=sum(p['net_pnl']>0 for p in positions),
            win_rate=100*sum(p['net_pnl']>0 for p in positions)/len(positions) if positions else None,
            net_pnl=total,pf_money=profit/loss if loss else None,closed_money_dd=dd,
            max_win_streak=max_win,max_loss_streak=max_loss,
            first_entry=min((p['open_time_broker'] for p in positions),default=None),
            last_close=max((p['close_time_broker'] for p in positions),default=None)),
        events=dict(Counter(r['event'] for r in relevant)),
        rejected=dict(Counter(r['reason'] for r in relevant if r['event']=='REJECTED')),
        errors=errors,note='Copied evidence predates September 18 restart and tracking correction; '
            'mixed historical versions/sizing. Broker times remain wall time. '
            'Short comments require symbol and exact journal-ticket attribution. '
            'Use net money including commission/swap, not legacy journal R.')
    save('demo_evidence.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('positions','errors','input_hashes')},indent=2))


def feeds():
    manifest=json.loads((OUT/'manifest.json').read_text())
    start,end=pd.Timestamp(manifest['start']),pd.Timestamp(manifest['end'])
    frames={}
    for src in ('dukascopy','histdata','mt5_icmarkets_utc'):
        paths=[Path(p) for p in manifest['input_hashes'] if Path(p).name.startswith('GBPUSD_M5_') and
            (('histdata' in Path(p).parts) if src=='histdata' else
             ('mt5_icmarkets_utc' in Path(p).parts) if src=='mt5_icmarkets_utc' else
             not any(x in Path(p).parts for x in ('histdata','mt5_icmarkets_utc')))]
        assert len(paths)==1
        df=pd.read_csv(paths[0],parse_dates=['time']).set_index('time')
        assert not df.index.duplicated().any()
        frames[src]=df.loc[(df.index>=start)&(df.index<end),['open','high','low','close']]
    d,h=frames['dukascopy'],frames['histdata']
    joined=d.join(h,how='inner',lsuffix='_d',rsuffix='_h')
    delta=pd.concat([(joined[c+'_d']-joined[c+'_h']).abs() for c in d.columns],axis=1).max(axis=1)
    years={str(y):dict(matched_bars=int((delta.index.year==y).sum()),
        identical_pct=100*float((delta[delta.index.year==y]<1e-9).mean())) for y in sorted(set(delta.index.year))}
    coverage={src:dict(bars=len(f),first=f.index.min(),last=f.index.max(),
        monthly_2023={str(t.date()):int(n) for t,n in f.loc['2023'].resample('MS').size().items()},
        weekdays_2023_with_under_200_m5={str(t.date()):int(n) for t,n in f.loc['2023'].resample('D').size().items()
            if t.weekday()<5 and n<200}) for src,f in frames.items()}
    result=dict(similarity=dict(matched=len(joined),identical_pct=100*float((delta<1e-9).mean()),years=years),
        coverage=coverage,note='Matching prices do not establish independent feeds. '
            'Weekday short sessions include holidays as well as missing provider data. No gaps are filled.')
    save('feed_audit.json',result)
    print(json.dumps(dict(similarity=result['similarity'],coverage={s:{k:v for k,v in x.items()
        if k!='weekdays_2023_with_under_200_m5'} for s,x in coverage.items()}),indent=2,default=str))


def logic():
    from models import BarEvent
    from research_candle_gbpusd_review import ObservedCandle,settings
    params=settings()
    # Isolate entry mechanics from the trend gate while retaining GBP's fn=3.
    params.update(tf_trend=None,min_engulf_range_pips=0,min_engulf_body_pct=0)
    def bar(tf,minute,h,l,c,o=None):
        return BarEvent('GBPUSD',tf,datetime(2024,1,1)+timedelta(minutes=minute),c if o is None else o,h,l,c,1)
    def fixture(variant):
        s=ObservedCandle(variant=variant,**params)
        s.generate_signal(bar('H1',0,1.102,1.098,1.099,1.10))
        s.generate_signal(bar('H1',60,1.103,1.095,1.101,1.099))
        return s
    sequence=[(1.0984,1.097,1.0978),(1.099,1.0974,1.0984),(1.0994,1.0978,1.0989),
        (1.1000,1.098,1.0993),(1.0995,1.0984,1.0990),(1.0996,1.0987,1.0992),
        (1.0997,1.099,1.0994),(1.1004,1.0991,1.1001),(1.1005,1.0999,1.1003)]
    observations={}
    for variant in ('current','fresh_cross','opposite_extreme'):
        s=fixture(variant)
        signals=[s.generate_signal(bar('M5',120+5*i,*ohlc)) for i,ohlc in enumerate(sequence)]
        assert all(x is None for x in signals[:8]),'Signal before confirmed swing plus FVG.'
        assert (signals[-1] is None)==(variant=='fresh_cross')
        observations[variant]=dict(stale_cross_signal=signals[-1] is not None,
            context=s.get_last_signal_context('GBPUSD'))
        s=fixture(variant)
        s.generate_signal(bar('M5',115,1.098,1.0945,1.0978))
        survives=s._bias['GBPUSD'] is not None
        assert survives==(variant!='opposite_extreme')
        observations[variant]['survives_opposite_extreme']=survives
    save('logic_reproductions.json',dict(params=params,observations=observations,
        note='Synthetic entry fixtures retain GBP fn=3, with trend/quality gates disabled solely '
             'to isolate mechanics. These are rule demonstrations, not strategy performance.'))
    print(json.dumps(observations,indent=2))


def trade_details():
    """Attribute filled trades to observed context and inspect cost/clock limitations."""
    manifest=json.loads((OUT/'manifest.json').read_text())
    results=json.loads((OUT/'results.json').read_text())
    details={}
    clock={}
    for source in ('dukascopy','histdata','mt5_icmarkets_utc'):
        input_paths=[Path(p) for p in manifest['input_hashes'] if
            (('histdata' in Path(p).parts) if source=='histdata' else
             ('mt5_icmarkets_utc' in Path(p).parts) if source=='mt5_icmarkets_utc' else
             not any(x in Path(p).parts for x in ('histdata','mt5_icmarkets_utc')))]
        h1path=next(p for p in input_paths if p.name.startswith('GBPUSD_H1_'))
        d1path=next(p for p in input_paths if p.name.startswith('GBPUSD_D1_'))
        h1=pd.read_csv(h1path,parse_dates=['time']).set_index('time')
        d1=pd.read_csv(d1path,parse_dates=['time'])
        clock[source]=dict(d1_open_hour_counts={str(k):int(v) for k,v in d1['time'].dt.hour.value_counts().items()})
        for r in results:
            if r['source']!=source or r['spread_pips']!=.2:
                continue
            name=f"{source}_{r['variant']}_spread0.2"
            trades=json.loads((OUT/f'{name}_trades.json').read_text())
            contexts=json.loads((OUT/f'{name}_contexts.json').read_text())
            matched={x['attempt_id']:x for x in contexts if x['attempt_id']}
            breakdown={}
            if r['variant'] not in ('original','tracking_only'):
                for t in trades:
                    x=matched[t['attempt_id']]
                    assert x['setup_id']==t['setup_id']
                    c=x['context']
                    origin_time=pd.Timestamp(c['engulf_time_utc'])
                    pivot_time=pd.Timestamp(c['pivot_time_utc'])
                    signal_time=pd.Timestamp(x['signal_time'])
                    assert pivot_time>=origin_time+pd.Timedelta(hours=1)
                    assert signal_time>=pivot_time+pd.Timedelta(minutes=20)
                    if r['variant']=='fresh_cross':
                        assert c['fresh_cross']
                    if r['variant']=='opposite_extreme':
                        assert not c['opposite_extreme_breached']
                    origin=h1.loc[pd.Timestamp(c['engulf_time_utc'])]
                    correct_color=(origin['close']>origin['open']) if t['direction']=='BUY' else (origin['close']<origin['open'])
                    features=dict(fresh_cross=c['fresh_cross'],opposite_extreme_breached=c['opposite_extreme_breached'],
                        correct_engulf_color=bool(correct_color))
                    for feature,value in features.items():
                        group=breakdown.setdefault(feature+'_'+str(value).lower(),[])
                        group.append(t)
                assert len(trades)+sum(r['rejected'].values())+len(r['final_exposure'])==len(contexts)
            from research_ema_fib_review import metrics
            details[name]=dict(groups={k:metrics(v) for k,v in breakdown.items()},
                overnight_trades=sum(pd.Timestamp(t['open_time']).date()!=pd.Timestamp(t['close_time']).date() for t in trades),
                mean_duration_hours=sum(t['duration_hours'] for t in trades)/len(trades) if trades else None,
                max_duration_hours=max((t['duration_hours'] for t in trades),default=None),
                below_8_pip_fills=[t for t in trades if abs(t['entry_price']-t['sl'])/.0001<8-1e-8],
                top_r_trade=max(trades,key=lambda t:t['net_r']) if trades else None)
    result=dict(daily_session_clocks=clock,details=details,
        note='Signal-context subgroups are descriptive and cannot predict a rule-change replay. '
             'Backtests include spread/commission, but no broker swap or actual tick slippage. '
             'UTC date changes are an overnight proxy, not an exact broker swap charge count.')
    save('trade_details.json',result)
    print(json.dumps(dict(daily_session_clocks=clock,details={k:{x:v for x,v in d.items()
        if x not in ('groups','top_r_trade','below_8_pip_fills')} for k,d in details.items()}),indent=2))


if __name__=='__main__':
    import sys
    {'demo':demo,'feeds':feeds,'logic':logic,'trade_details':trade_details}[sys.argv[1]]()
