"""IMS lifecycle reproductions and copied demo evidence. No terminal connection."""
from collections import Counter
import csv
from datetime import datetime, timedelta
from pathlib import Path

from audit_ema_fib_demo_logs import Rows, money
from data.histdata_provenance import file_hash, write_json
from models import BarEvent
from research_ims_trend_review import OUT, settings
from research_ims_trend_baseline import ImsStrategy


def fixture(hour):
    params, _ = settings()
    strategy = ImsStrategy(**params)
    bar = BarEvent('EURUSD', 'M15', datetime(2020, 1, 2, hour), 1.107, 1.108, 1.106, 1.107, 1)
    strategy.generate_signal(bar)
    strategy._htf_bias['EURUSD'] = dict(direction='BUY', swing_low=1.10, swing_high=1.12,
        dealing_50=1.11, fvg_level=1.102, _swing_ts=datetime(2020,1,1))
    strategy._ltf_signal_fired['EURUSD'] = True
    strategy._last_signal_entry['EURUSD'] = 1.104
    strategy._last_signal_sl['EURUSD'] = 1.103
    return strategy, bar


def logic():
    results = {}
    params, _ = settings()
    strategy = ImsStrategy(**params)
    lows = [100,101,99,90,93,96,99,92,89]
    highs = [105,110,104,95,99,108,112,106,100]
    candles = [BarEvent('EURUSD','H4',datetime(2020,1,1)+timedelta(hours=4*i),
                       (lo+hi)/2,hi,lo,(lo+hi)/2,1) for i,(lo,hi) in enumerate(zip(lows,highs))]
    for candle in candles[:7]:
        strategy.generate_signal(candle)
    assert strategy._htf_bias['EURUSD']['_swing_ts'] == candles[3].timestamp
    strategy.generate_signal(candles[7])
    assert strategy._htf_bias['EURUSD'] is None
    strategy.generate_signal(candles[8])
    revived = strategy._htf_bias['EURUSD']
    assert revived['_swing_ts'] == candles[3].timestamp
    assert candles[8].low < revived['swing_low']
    results['expired_origin_reactivated_despite_origin_breach'] = (
        'H4 origin low 90, high 112. Candle low 92 expires bias. Next candle low 89 '
        'recreates the same origin at 90, although that candle has already breached it.')
    strategy, bar = fixture(18)
    assert strategy.generate_signal(bar) is None
    assert strategy._ltf_signal_fired['EURUSD']
    strategy, bar = fixture(12)
    signal = strategy.generate_signal(bar)
    assert signal.direction == 'CANCEL'
    assert strategy._htf_bias['EURUSD'] is None
    assert not strategy._ltf_signal_fired['EURUSD']
    results['target_cancellation_is_entry_hours_only'] = 'Same target-touch candle cancels at 12:00 but stays active at 18:00 UTC.'
    results['tracking_cleared_before_cancel_confirmation'] = 'On emitting CANCEL, bias and fired flag are already cleared without a broker response.'
    strategy, _ = fixture(12)
    old_origin = strategy._htf_bias['EURUSD']['_swing_ts']
    strategy._htf_bias['EURUSD']['_swing_ts'] = datetime(2020,1,2)
    strategy.notify_win('EURUSD')
    assert strategy._htf_bias['EURUSD'] is None
    results['win_has_no_origin_attribution'] = f'An old trade win clears the current newer origin; callback takes symbol only. Old origin {old_origin}.'
    strategy, _ = fixture(12)
    strategy._reset_ltf('EURUSD')
    assert strategy._last_signal_entry['EURUSD'] == 1.104
    results['reset_retains_price_anchors'] = 'LTF reset clears fired flag but leaves prior entry and SL anchors.'
    assert not hasattr(strategy, 'sync_order_state')
    assert not hasattr(strategy, 'notify_order_accepted')
    assert not hasattr(strategy, 'notify_proposal_rejected')
    results['no_order_lifecycle_identity'] = 'No acceptance, synchronization, proposal identity, or attributed close callbacks.'
    write_json(OUT/'logic_reproductions.json', results)
    print(results)


def demo():
    report = Path('logs/ReportHistory-52775013.html')
    journal = Path('logs/trade_journal.csv')
    raw = report.read_bytes()
    parser = Rows()
    parser.feed(raw.decode('utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8'))
    with journal.open(newline='', encoding='utf-8-sig') as handle:
        rows = list(csv.DictReader(handle))
    relevant = [r for r in rows if r['strategy_name'] == 'IMS_H4_M15']
    positions, section = [], None
    for row in parser.rows:
        if len(row) == 1 and row[0] in ('Positions','Orders','Deals','Open Positions','Working Orders'):
            section = row[0]
        if section == 'Positions' and len(row) == 14 and row[4] == 'IMS_H4_M15':
            positions.append(dict(ticket=row[1], symbol=row[2], direction=row[3],
                open_time_broker=row[0], close_time_broker=row[9], entry=money(row[6]),
                sl=money(row[7]), tp=money(row[8]), exit=money(row[10]),
                commission=money(row[11]), swap=money(row[12]), profit=money(row[13]),
                net_pnl=sum(money(row[i]) for i in (11,12,13))))
    assert positions and len(positions) == len({p['ticket'] for p in positions})
    _, symbols = settings()
    def summary(ps):
        positive = sum(p['net_pnl'] for p in ps if p['net_pnl'] > 0)
        negative = -sum(p['net_pnl'] for p in ps if p['net_pnl'] < 0)
        ordered = sorted(ps, key=lambda p:(p['close_time_broker'],p['ticket']))
        total = peak = dd = 0
        losses = worst = 0
        for p in ordered:
            total += p['net_pnl']
            peak = max(peak,total)
            dd = max(dd,peak-total)
            losses = losses+1 if p['net_pnl'] < 0 else 0
            worst = max(worst,losses)
        return dict(trades=len(ps), wins=sum(p['net_pnl']>0 for p in ps),
            net_pnl=total, profit_factor_money=positive/negative if negative else None,
            max_closed_money_drawdown=dd, max_loss_streak=worst,
            first_entry=min((p['open_time_broker'] for p in ps),default=None),
            last_close=max((p['close_time_broker'] for p in ps),default=None))
    placed = {r['ticket'] for r in relevant if r['event']=='ORDER_PLACED' and r['ticket']}
    closed = {p['ticket'] for p in positions}
    result = dict(input_hashes={str(p):file_hash(p) for p in (report,journal)},
        all_ims=summary(positions), current_eight_symbols=summary([p for p in positions if p['symbol'] in symbols]),
        by_symbol={s:summary([p for p in positions if p['symbol']==s]) for s in sorted({p['symbol'] for p in positions})},
        event_counts=dict(Counter(r['event'] for r in relevant)),
        rejection_reasons=dict(Counter(r['reason'] for r in relevant if r['event']=='REJECTED')),
        placed_tickets=len(placed), placed_tickets_with_closed_position=len(placed & closed),
        position_target_rr_counts=dict(Counter(round(abs(p['tp']-p['entry'])/abs(p['entry']-p['sl']),2)
            for p in positions if p['sl'] and p['sl'] != p['entry'])), positions=positions,
        note='Mixed historical versions and sizes. Export predates September 18 restart. Money PF includes commission/swap; do not compare directly to simulated R PF. Matched closed/placed ratio is only a lower bound on fills, not a full lifecycle fill rate.')
    write_json(OUT/'demo_evidence.json', result)
    print({k:v for k,v in result.items() if k not in ('positions','input_hashes')})


if __name__ == '__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    logic()
    demo()
