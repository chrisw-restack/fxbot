"""Summarize copied EmaFibRunning DEMO evidence without contacting MT5."""
from collections import Counter
import csv
from pathlib import Path

from audit_ema_fib_demo_logs import Rows, money
from data.histdata_provenance import file_hash, write_json
from research_ema_fib_running_review import OUT


def main():
    report=Path('logs/ReportHistory-52775013.html')
    journal=Path('logs/trade_journal.csv')
    raw=report.read_bytes()
    parser=Rows()
    parser.feed(raw.decode('utf-16' if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8'))
    section=None
    positions=[]
    for row in parser.rows:
        if len(row)==1 and row[0] in ('Positions','Orders','Deals','Open Positions','Working Orders'):
            section=row[0]
        if section=='Positions' and len(row)==14 and row[4]=='EmaFibRunning':
            positions.append(dict(ticket=row[1],symbol=row[2],open_time_broker=row[0],close_time_broker=row[9],
                net_pnl=sum(money(row[i]) for i in (11,12,13)),commission=money(row[11]),swap=money(row[12]),profit=money(row[13])))
    assert len({p['ticket'] for p in positions})==len(positions)
    with journal.open(newline='',encoding='utf-8-sig') as f:
        rows=list(csv.DictReader(f))
    relevant=[r for r in rows if r['strategy_name']=='EmaFibRunning']
    gains=sum(p['net_pnl'] for p in positions if p['net_pnl']>0)
    losses=-sum(p['net_pnl'] for p in positions if p['net_pnl']<0)
    result=dict(input_hashes={str(p):file_hash(p) for p in (report,journal)},
        report_generated='2026-09-18 11:20 broker report label; before confirmed restart',
        trades=len(positions),wins=sum(p['net_pnl']>0 for p in positions),
        net_pnl=sum(p['net_pnl'] for p in positions),profit_factor_money=gains/losses if losses else None,
        first_entry=min((p['open_time_broker'] for p in positions),default=None),
        last_close=max((p['close_time_broker'] for p in positions),default=None),
        event_counts=dict(Counter(r['event'] for r in relevant)),
        rejection_reasons=dict(Counter(r['reason'] for r in relevant if r['event']=='REJECTED')),
        journal_first=min(r['journal_time_utc'] for r in rows),journal_last=max(r['journal_time_utc'] for r in rows),
        closed_positions=positions,
        note='Mixed historical versions, settings, risk, and runtime conditions. Partial journal, not a current-code forward validation.')
    log=Path('logs/trading_20260610_123557.log')
    lines=log.read_text(encoding='utf-8',errors='replace').splitlines()
    evidence=[dict(line=i+1,text=line) for i,line in enumerate(lines)
              if '1689274839' in line and ('Cancel pending order failed' in line or 'Cancelled pending order' in line)]
    assert len(evidence)==2 and 'retcode=10018' in evidence[0]['text']
    result['input_hashes'][str(log)]=file_hash(log)
    result['failed_cancellation_winner']=dict(ticket='1689274839',symbol='EURUSD',
        net_pnl=next(p['net_pnl'] for p in positions if p['ticket']=='1689274839'),
        cancellation_attempt_utc='2026-06-07 21:00:04',log=str(log),evidence=evidence,
        journal_rows=[r for r in relevant if r['ticket']=='1689274839'],
        interpretation='The old execution path logged a rejected cancellation as successful. '
                       'The later winner is not evidence that the intended strategy would retain this order. '
                       'This incident predates the September execution fixes.')
    write_json(OUT/'demo_evidence.json',result)
    print({k:v for k,v in result.items() if k not in ('input_hashes','closed_positions')})


if __name__=='__main__':
    main()
