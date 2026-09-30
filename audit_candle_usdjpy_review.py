"""Local Candle Confirmation reproductions and copied DEMO evidence; no MT5."""
from collections import Counter
import csv
from datetime import datetime, timedelta
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'output/candle_usdjpy_review_20260930'
NAMES = {'CandleConfirmation_USDJPY_H1_M5', 'CandleConfirmation_H1_M5'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/name).write_text(json.dumps(data, indent=2, default=str), encoding='utf-8')


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


def demo():
    report, journal = ROOT/'logs/ReportHistory-52775013.html', ROOT/'logs/trade_journal.csv'
    parser, raw = Rows(), report.read_bytes()
    parser.feed(raw.decode('utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8'))
    with journal.open(newline='', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    relevant = [r for r in rows if r['symbol'] == 'USDJPY' and r['strategy_name'] in NAMES]
    positions, section = [], None
    for row in parser.rows:
        if len(row) == 1 and row[0] in ('Positions', 'Orders', 'Deals', 'Open Positions', 'Working Orders'):
            section = row[0]
        if section == 'Positions' and len(row) == 14 and row[2] == 'USDJPY' and (
            row[4] in NAMES or row[4].startswith('CandleConfirm')):
            positions.append(dict(ticket=row[1], symbol=row[2], direction=row[3], strategy_comment=row[4],
                open_time_broker=row[0], close_time_broker=row[9], entry=money(row[6]), sl=money(row[7]),
                tp=money(row[8]), commission=money(row[11]), swap=money(row[12]), profit=money(row[13]),
                net_pnl=sum(money(row[i]) for i in (11,12,13))))
    assert len(positions) == len({p['ticket'] for p in positions})
    journal_closes = [r for r in relevant if r['event'] == 'CLOSE']
    assert len(journal_closes) == len({r['ticket'] for r in journal_closes})
    by_ticket = {p['ticket']: p for p in positions}
    matches = []
    for r in journal_closes:
        p = by_ticket.get(r['ticket'])
        if p:
            matches.append(dict(ticket=r['ticket'], journal_pnl=float(r['pnl']),
                report_profit=p['profit'], report_net=p['net_pnl'],
                journal_r=r['r_multiple'], difference_to_profit=float(r['pnl'])-p['profit'],
                difference_to_net=float(r['pnl'])-p['net_pnl']))
    assert len(matches)==len(journal_closes)==len(positions), 'Unmatched Candle USDJPY position or close.'
    assert all(abs(m['difference_to_net'])<.011 for m in matches), 'Journal P/L does not reconcile to broker costs.'
    rejected = [r for r in relevant if r['event']=='REJECTED']
    errors=[]
    for r in rejected:
        context=json.loads(r['context_json']) if r.get('context_json') else {}
        error=context.get('execution_error',{})
        errors.append(dict(time=r['journal_time_utc'],reason=r['reason'],last_error=error.get('last_error'),
                           retcode=error.get('retcode')))
    total = peak = dd = 0.
    loss_run = win_run = max_loss = max_win = 0
    for p in sorted(positions, key=lambda p: (p['close_time_broker'], p['ticket'])):
        total += p['net_pnl']
        peak, dd = max(peak,total), max(dd, max(peak,total)-total)
        loss_run = loss_run+1 if p['net_pnl'] < 0 else 0
        win_run = win_run+1 if p['net_pnl'] > 0 else 0
        max_loss, max_win = max(max_loss,loss_run), max(max_win,win_run)
    profits = sum(p['net_pnl'] for p in positions if p['net_pnl'] > 0)
    losses = -sum(p['net_pnl'] for p in positions if p['net_pnl'] < 0)
    result = dict(input_hashes={str(p.relative_to(ROOT)): digest(p) for p in (report,journal)},
        positions=positions, summary=dict(trades=len(positions), wins=sum(p['net_pnl']>0 for p in positions),
            net_pnl=total, profit_factor_money=profits/losses if losses else None,
            max_closed_money_drawdown=dd, max_loss_streak=max_loss, max_win_streak=max_win,
            first_entry=min((p['open_time_broker'] for p in positions),default=None),
            last_close=max((p['close_time_broker'] for p in positions),default=None)),
        event_counts=dict(Counter(r['event'] for r in relevant)),
        rejection_reasons=dict(Counter(r['reason'] for r in relevant if r['event']=='REJECTED')),
        execution_rejections=errors,
        journal_closes=len(journal_closes), matched_closes=matches,
        report_target_rr=[abs(p['tp']-p['entry'])/abs(p['entry']-p['sl']) for p in positions if p['sl']!=p['entry']],
        note='Copied report predates September 18 restart; mixed historical versions/sizing. '
             'Journal P/L matches broker net P/L including commission/swap. Journal R has a different denominator/cost convention '
             'and is not used as net performance. Broker report times remain broker wall time. '
             'Shortened broker comments are attributed by USDJPY symbol and exact journal ticket matches.')
    save('demo_evidence.json', result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('positions','input_hashes')},indent=2))


def logic():
    from models import BarEvent
    from strategies.candle_confirmation import CandleConfirmationStrategy
    from utils.warmup import warmup_counts
    from live_config import create_live_strategy_specs
    def bar(tf, minute, o, h, l, c):
        return BarEvent('USDJPY', tf, datetime(2020,1,1)+timedelta(minutes=minute), o,h,l,c,1)
    def fixture():
        s = CandleConfirmationStrategy(fractal_n=1, min_sl_pips=0, tp_range_pct=1.25, sl_rr_ratio=1.5)
        s.generate_signal(bar('H1',0,120,130,110,115))
        s.generate_signal(bar('H1',60,115,140,90,130))
        return s
    s = fixture()
    sequence = [(102,105,99,103), (103,110,101,106), (106,109,103,107),
                (107,112,104,111), (111,114,109.5,113)]
    for i, ohlc in enumerate(sequence):
        signal = s.generate_signal(bar('M5',120+5*i,*ohlc))
        if i < 4:
            assert signal is None
    assert signal and sequence[-2][-1] > sequence[1][1]
    stale = dict(previous_close=111, selected_swing=110, signal_close=113,
        note='The first close through 110 had no FVG; a later bar creates an FVG and enters although the previous close was already above 110.')
    s = fixture()
    assert s.generate_signal(bar('M5',120,100,105,89,103)) is None
    assert s._bias['USDJPY'] is not None
    for i,ohlc in enumerate(sequence[1:],1):
        signal = s.generate_signal(bar('M5',120+5*i,*ohlc))
    assert signal is not None
    opposite = 'A BUY setup survives an M5 low of 89 below the engulf low of 90, then emits BUY. Current invalidation checks only the high of 140.'
    # A recovered earlier trade has no setup attribution. Its outcome resets whichever bias is current.
    s = fixture()
    s._signal_fired['USDJPY'] = True
    s.notify_signal_rejected('USDJPY')
    assert s._bias['USDJPY'] and not s._signal_fired['USDJPY']
    s.notify_win('USDJPY')
    assert s._bias['USDJPY'] is None
    specs = [(s,syms) for s,syms in create_live_strategy_specs() if s.NAME == 'CandleConfirmation_USDJPY_H1_M5']
    counts = warmup_counts(specs)
    result = dict(stale_structure_break=stale, opposite_extreme_policy=opposite,
        proposal_rejection='Unsubmitted rejection releases fired flag and preserves setup; confirmed by reproduction.',
        close_attribution='No setup/attempt IDs or sync/acceptance/attributed-close callbacks. A restored old close clears the current bias by symbol. Normal uninterrupted trades freeze bias changes while fired.',
        warmup_counts={tf:count for (_,tf),count in counts.items()},
        warmup_note='50 D1 bars seed EMA50 with no settling history, and only 250 M5 bars cover roughly 21 hours versus 100 H1 bars. Broker history gaps change calendar span.',
        model_note='Synthetic fixtures isolate behavior; they do not claim profitable alternatives or quantify production frequency.')
    save('logic_reproductions.json', result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    if '--demo' in sys.argv:
        demo()
    else:
        logic()
