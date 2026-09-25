"""Read copied DEMO exports; never contact the trading terminal."""
from collections import Counter
import csv
from html.parser import HTMLParser
from pathlib import Path

from data.histdata_provenance import file_hash, write_json
from research_ema_fib_review import OUT


class Rows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.row = []
        elif tag in ('td', 'th'):
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            if self.row is not None:
                self.row.append(''.join(self.cell).strip())
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def money(value):
    return float(value.replace(' ', '').replace('\xa0', ''))


def main():
    report = Path('logs/ReportHistory-52775013.html')
    journal = Path('logs/trade_journal.csv')
    parser = Rows()
    raw = report.read_bytes()
    parser.feed(raw.decode('utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8'))
    positions, section = [], None
    for row in parser.rows:
        if len(row) == 1 and row[0] in ('Positions', 'Orders', 'Deals', 'Open Positions', 'Working Orders'):
            section = row[0]
        if section == 'Positions' and len(row) == 14 and row[4] in ('EmaFibRetracemen', 'EmaFibRetracement'):
            positions.append(dict(ticket=row[1], symbol=row[2], strategy_comment=row[4],
                open_time_broker=row[0], close_time_broker=row[9],
                profit=money(row[13]), commission=money(row[11]), swap=money(row[12]),
                net_pnl=sum(money(row[i]) for i in (11,12,13))))
    assert positions and len({p['ticket'] for p in positions}) == len(positions)
    with journal.open(newline='', encoding='utf-8-sig') as handle:
        rows = list(csv.DictReader(handle))
    relevant = [r for r in rows if r['strategy_name'] == 'EmaFibRetracement']
    closes = [r for r in relevant if r['event'] == 'CLOSE']
    rs = [float(r['r_multiple']) for r in closes if r['r_multiple']]
    profits = sum(p['net_pnl'] for p in positions if p['net_pnl'] > 0)
    losses = -sum(p['net_pnl'] for p in positions if p['net_pnl'] < 0)
    out = dict(input_hashes={str(p):file_hash(p) for p in (report,journal)},
        report_generated='2026.09.18 11:20, as printed in broker export',
        note='Export predates the confirmed September 18 restart. Mixed historical code/settings/sizing, not validation of current code.',
        positions=dict(trades=len(positions), wins=sum(p['net_pnl'] > 0 for p in positions),
            net_pnl=sum(p['net_pnl'] for p in positions), profit_factor_money=profits/losses if losses else None,
            first_entry=min(p['open_time_broker'] for p in positions), last_close=max(p['close_time_broker'] for p in positions),
            by_symbol={s:dict(trades=sum(p['symbol'] == s for p in positions),
                net_pnl=sum(p['net_pnl'] for p in positions if p['symbol'] == s)) for s in sorted({p['symbol'] for p in positions})}),
        journal=dict(first_time=min(r['journal_time_utc'] for r in rows), last_time=max(r['journal_time_utc'] for r in rows),
            ema_fib_event_counts=dict(Counter(r['event'] for r in relevant)),
            ema_fib_rejection_reasons=dict(Counter(r['reason'] for r in relevant if r['event'] == 'REJECTED')),
            closed_rows=len(closes), unique_closed_tickets=len({r['ticket'] for r in closes}),
            closes_with_r=len(rs), logged_r_sum=sum(rs),
            warning='Journal is a partial window and recorded R need not include costs. Do not equate with simulated net R.'),
        closed_positions=positions)
    write_json(OUT/'demo_logs.json', out)
    print({k:v for k,v in out.items() if k not in ('closed_positions','input_hashes')})


if __name__ == '__main__':
    main()
