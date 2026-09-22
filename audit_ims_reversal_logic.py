"""Small synthetic checks of IMS Reversal's documented lifecycle rules.

Writes observations rather than modifying strategy logic or connecting to MT5.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from models import BarEvent
from research_ims_baseline import ImsReversalStrategy


def candle(hour, low, high, close, tf='M15'):
    return BarEvent('EURUSD',tf,datetime(2020,1,6)+timedelta(hours=hour),
                    close,high,low,close,0.)


def pending_strategy(factory):
    s=factory(ltf_fractal_n=2,blocked_hours=(*range(12),*range(17,24)))
    s.generate_signal(candle(0,1.11,1.12,1.115,'H4'))
    s._htf_bias['EURUSD']={
        'direction':'BUY','swing_low':1.10,'swing_high':1.12,
        'dealing_50':1.11,'fvg_level':1.102,'_swing_ts':datetime(2020,1,5)}
    s._ltf_signal_fired['EURUSD']=True
    s._last_signal_entry['EURUSD']=1.118
    s._last_signal_sl['EURUSD']=1.120
    if hasattr(s,'submitted_targets'):
        s.submitted_targets['EURUSD']=1.110
    return s


def checks(factory):
    rows=[]
    # Same target touch in entry hours and outside entry hours. Both remain
    # above structural expiry, isolating the pending-target rule.
    for hour in [16,18]:
        s=pending_strategy(factory)
        signal=s.generate_signal(candle(hour,1.109,1.115,1.112))
        observed=signal.direction if signal else None
        rows.append(dict(check=f'cancel_unfilled_target_touch_at_{hour}_UTC',
                         expected='CANCEL',observed=observed,passed=observed=='CANCEL'))

    # A submitted target remains 1.110, while the dynamic H4 midpoint moves.
    s=pending_strategy(factory)
    s._htf_bias['EURUSD'].update(swing_high=1.13,dealing_50=1.115)
    signal=s.generate_signal(candle(16,1.114,1.117,1.116))
    observed=signal.direction if signal else None
    rows.append(dict(check='cancel_checks_submitted_target_not_moving_midpoint',
                     expected=None,observed=observed,passed=observed is None,
                     submitted_tp=1.110,moving_midpoint=1.115,bar_low=1.114))

    # Real H4 scanner: the same original pivot remains visible after notify_loss.
    s=factory(max_losses_per_bias=1)
    levels=[(1.099,1.101,1.100),(1.100,1.108,1.104),(1.097,1.103,1.098),
            (1.090,1.097,1.093),(1.096,1.106,1.105),(1.108,1.114,1.113)]
    for i,(low,high,close) in enumerate(levels):
        s.generate_signal(candle(4*i,low,high,close,'H4'))
    original=s._htf_bias['EURUSD']
    assert original is not None
    original_key=(original['direction'],original['_swing_ts'])
    s.notify_loss('EURUSD')
    assert s._htf_bias['EURUSD'] is None
    s.generate_signal(candle(24,1.110,1.115,1.114,'H4'))
    revived=s._htf_bias['EURUSD']
    revived_key=(revived['direction'],revived['_swing_ts']) if revived else None
    rows.append(dict(check='one_loss_per_bias_stays_retired',expected='different_or_no_bias',
                     observed=str(revived_key),same_origin=original_key==revived_key,
                     passed=original_key!=revived_key))

    return rows


def main():
    from research_ims_reversal import ResearchLifecycleIMS
    original=checks(ImsReversalStrategy)
    experimental=checks(lambda **kwargs:ResearchLifecycleIMS(retire_loss=True,pending_lifecycle=True,**kwargs))
    assert sum(not r['passed'] for r in original)==3
    assert all(r['passed'] for r in experimental)
    results={'original':original,'research_both':experimental}
    out=Path('output/ims_reversal_review_20260918');out.mkdir(parents=True,exist_ok=True)
    (out/'synthetic_audit.json').write_text(json.dumps(results,indent=2,default=str))
    print(json.dumps(results,indent=2,default=str))


if __name__=='__main__': main()
