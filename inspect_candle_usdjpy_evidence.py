"""Inspect CSV similarity and the R denominator of saved Candle USDJPY trades."""
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'output/candle_usdjpy_review_20260930'


def main():
    manifest = json.loads((OUT/'manifest.json').read_text())
    start, end = pd.Timestamp('2016-07-01'), pd.Timestamp('2026-07-15')
    feeds = {}
    for source in ('dukascopy', 'histdata', 'mt5_icmarkets_utc'):
        paths = [ROOT/p for p in manifest['input_hashes']
                 if Path(p).name.startswith('USDJPY_M5_') and
                 (('histdata' in Path(p).parts) if source=='histdata' else
                  ('mt5_icmarkets_utc' in Path(p).parts) if source=='mt5_icmarkets_utc' else
                  not any(x in Path(p).parts for x in ('histdata','mt5_icmarkets_utc')))]
        assert len(paths) == 1
        frame = pd.read_csv(paths[0], parse_dates=['time']).set_index('time')
        feeds[source] = frame.loc[(frame.index>=start)&(frame.index<end), ['open','high','low','close']]
    a,b = feeds['dukascopy'],feeds['histdata']
    joined = a.join(b, how='inner', lsuffix='_duka', rsuffix='_hist')
    delta = pd.concat([(joined[f'{c}_duka']-joined[f'{c}_hist']).abs() for c in a.columns],axis=1).max(axis=1)
    similarity = dict(matched_m5_bars=len(joined), duka_bars=len(a),hist_bars=len(b),
        all_ohlc_equal_pct=100*(delta<1e-9).mean(), all_ohlc_within_point_pct=100*(delta<=.001+1e-9).mean(),
        years={str(y):dict(bars=int((delta.index.year==y).sum()),
            equal_pct=100*(delta.loc[delta.index.year==y]<1e-9).mean(),
            max_ohlc_difference=float(delta.loc[delta.index.year==y].max())) for y in sorted(set(delta.index.year))})
    results = json.loads((OUT/'results.json').read_text())
    budgets = {}
    anomalies = []
    for r in results:
        name = f"{r['source']}_{r['variant']}_spread{r['spread_pips']:g}"
        ts = json.loads((OUT/(name+'_trades.json')).read_text())
        balance, previous_close = 10000., ''
        prepared = []
        for t in ts:
            assert previous_close <= t['open_time'], 'Cannot infer pre-order balance across overlapping positions.'
            budget = balance*.005
            prepared.append(dict(t, net_r=t['pnl']/budget, budget=budget))
            balance += t['pnl']
            previous_close = t['close_time']
        assert abs(balance-r['ending_balance']) < 1e-7
        # Metrics here use planned account-risk units, unlike the production filled-SL R.
        rs=[t['net_r'] for t in prepared]
        total=peak=dd=0.
        for value in rs:
            total += value
            peak=max(peak,total)
            dd=max(dd,peak-total)
        budget_summary=dict(trades=len(ts), total_planned_r=total,
            expectancy_planned_r=total/len(ts), max_dd_planned_r=dd,
            closed_balance=balance, closed_growth_pct=100*(balance/10000-1),
            filled_sl_below_8_pips=sum(abs(t['entry_price']-t['sl'])/.01 < 8-1e-9 for t in ts),
            top_trade=sorted(ts,key=lambda t:t['net_r'],reverse=True)[0])
        budgets[name]=budget_summary
        for t,p in zip(ts,prepared):
            if abs(t['net_r'])>3:
                frame=feeds[r['source']]
                opened=pd.Timestamp(t['open_time'])
                before=frame.loc[frame.index<opened].tail(1)
                anomalies.append(dict(case=name, trade=t, planned_r=p['net_r'],
                    previous_bar_time=before.index[0], previous_bar_close=before.iloc[0]['close'],
                    entry_bar_open=frame.loc[opened,'open'],
                    previous_bar_to_fill_minutes=(opened-before.index[0]).total_seconds()/60))
    monthly_2023={source:{str(month.date()):int(count) for month,count in frame.loc['2023'].resample('MS').size().items()}
                  for source,frame in feeds.items()}
    output=dict(similarity=similarity,monthly_m5_2023=monthly_2023,planned_risk=budgets,large_r_trades=anomalies,
        note='Planned-risk denominator is 0.5% of standalone balance before acceptance. '
             'No overlapping positions or realized P/L between acceptance and fill. '
             'Source similarity is price evidence, not proof of independence. '
             'No source rows are changed or removed.')
    (OUT/'denominator_and_feed_audit.json').write_text(json.dumps(output,indent=2,default=str),encoding='utf-8')
    print(json.dumps(dict(similarity=similarity,planned_risk={k:{x:v for x,v in m.items() if x!='top_trade'}
        for k,m in budgets.items()},large_r_trades=anomalies),indent=2,default=str))


if __name__ == '__main__':
    main()
