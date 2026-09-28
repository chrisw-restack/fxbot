"""Read copied Failed2 journal and MT5 history; no terminal connection."""
from collections import Counter
import csv
from pathlib import Path

from audit_ema_fib_demo_logs import Rows, money
from data.histdata_provenance import file_hash, write_json
from research_failed2_review import OUT


def main():
    report=Path('logs/ReportHistory-52775013.html')
    journal=Path('logs/trade_journal.csv')
    raw=report.read_bytes()
    parser=Rows()
    parser.feed(raw.decode('utf-16' if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8'))
    with journal.open(newline='',encoding='utf-8-sig') as f:
        rows=list(csv.DictReader(f))
    relevant=[r for r in rows if r['strategy_name']=='Failed2_H4_H1_M5_market']
    positions=[]
    section=None
    for row in parser.rows:
        if len(row)==1 and row[0] in ('Positions','Orders','Deals','Open Positions','Working Orders'):
            section=row[0]
        if section=='Positions' and len(row)==14 and row[4].startswith('Failed2_H4_H1_M5'):
            matches=[r for r in relevant if r['ticket']==row[1]]
            positions.append(dict(ticket=row[1],symbol=row[2],direction=row[3],comment=row[4],
                open_time_broker=row[0],close_time_broker=row[9],lots=money(row[5]),entry=money(row[6]),sl=money(row[7]),tp=money(row[8]),exit=money(row[10]),
                profit=money(row[13]),commission=money(row[11]),swap=money(row[12]),
                net_pnl=sum(money(row[i]) for i in (11,12,13)),
                journal_order_types=sorted({r['order_type'] for r in matches if r['order_type']})))
    assert len({p['ticket'] for p in positions})==len(positions)
    for p in positions:
        risk=abs(p['entry']-p['sl'])*p['lots']
        p['reported_sl_risk_usd']=risk
        p['net_r_using_reported_sl']=p['net_pnl']/risk if risk else None
    gains=sum(p['net_pnl'] for p in positions if p['net_pnl']>0)
    losses=-sum(p['net_pnl'] for p in positions if p['net_pnl']<0)
    result=dict(input_hashes={str(p):file_hash(p) for p in (report,journal)},positions=positions,
        trades=len(positions),wins=sum(p['net_pnl']>0 for p in positions),net_pnl=sum(p['net_pnl'] for p in positions),
        profit_factor_money=gains/losses if losses else None,total_swap=sum(p['swap'] for p in positions),
        event_counts=dict(Counter(r['event'] for r in relevant)),
        rejection_reasons=dict(Counter(r['reason'] for r in relevant if r['event']=='REJECTED')),
        first_journal=min(r['journal_time_utc'] for r in rows),last_journal=max(r['journal_time_utc'] for r in rows),
        note='Copied export dated 18 September before confirmed restart. Mixed versions, settings, and sizing. '
             'Broker comments are truncated; journal matching is reported per ticket. Not current-code forward validation.')
    write_json(OUT/'demo_evidence.json',result)
    print({k:v for k,v in result.items() if k not in ('positions','input_hashes')})


if __name__=='__main__':
    main()
