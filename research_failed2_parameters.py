"""One-variable Failed2 search with training-only selection and serial replays.

No DEMO configuration writes, MT5 connection, or data after 14 July 2026.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import time

from data.historical_loader import load_and_merge
from data.histdata_provenance import file_hash, metadata_path, write_json
from research_failed2_corrections import replay, OUT as CORRECTED
from research_failed2_review import ROOT, SOURCES, FOLDS, settings, paths_for
from research_ema_fib_review import metrics

OUT = ROOT / 'output/failed2_parameters_20260928'
CUTOFF = datetime(2026, 7, 15)
OPTIONS = {'current': {}}
for value in (2.5, 3., 3.5, 4.5, 5.):
    OPTIONS[f'rr_{value:g}'] = {'rr_ratio': value}
for value in (2, 3, 5):
    OPTIONS[f'mss_{value}'] = {'mss_fractal_n': value}
for value in (1, 3):
    OPTIONS[f'stop_{value}'] = {'sl_fractal_n': value}
for value in (.6, .8, .9):
    OPTIONS[f'range_{value:g}'] = {'d1_range_block_pct': value}
for value in (40, 90):
    OPTIONS[f'lookback_{value}'] = {'d1_range_lookback': value}
OPTIONS['session_12_16'] = {'blocked_hours': [h for h in range(24) if h not in range(12,16)]}
OPTIONS['session_13_17'] = {'blocked_hours': [h for h in range(24) if h not in range(13,17)]}
OPTIONS['trend_off'] = {'trend_filter': 'off'}
assert len(OPTIONS) == 19


def eligible(row, baseline):
    m, base = row['metrics'], baseline['metrics']
    return (m['trades'] >= 40 and m['total_r'] > 0 and
            (m['profit_factor'] is None or m['profit_factor'] >= 1.1) and
            m['max_dd_r'] <= 1.5 * base['max_dd_r'])


def ranked(rows, baseline):
    return sorted((r for r in rows if eligible(r, baseline)),
                  key=lambda r: (-r['metrics']['total_r'], r['metrics']['max_dd_r'], r['option']))


def verdict(train, test):
    retention = test['expectancy']/train['expectancy'] if train['expectancy'] and train['expectancy'] > 0 else None
    value = ('FAIL' if test['total_r'] <= 0 else 'UNDEFINED' if retention is None else
             'STRONG' if retention >= .7 else 'MODERATE' if retention >= .4 else 'WEAK')
    return dict(retention=retention, verdict=value)


class Study:
    def __init__(self):
        self.params = settings()
        self.paths = {source:paths_for(source) for source in SOURCES}
        self.rows = []
        self.controls = []
        self.bars = None
        self.source = None
        code = ['research_failed2_parameters.py','research_failed2_corrections.py',
            'research_failed2_review.py','research_ema_fib_review.py','strategies/failed2.py',
            'engine.py','backtest_engine.py','execution/simulated_execution.py',
            'portfolio/portfolio_manager.py','risk/risk_manager.py','risk/validation.py',
            'config.py','live_config.py','data/historical_loader.py','data/histdata_provenance.py']
        manifest = dict(parameters=self.params, options=OPTIONS, workers=1,
            code_hashes={p:file_hash(ROOT/p) for p in code},
            input_hashes={p:file_hash(p) for _,files in self.paths.values() for p in files},
            metadata_hashes={str(metadata_path(p)):file_hash(metadata_path(p))
                for _,files in self.paths.values() for p in files if metadata_path(p).exists()},
            protocol=dict(selection='Highest training total R among eligible cases; tie lower DD then option name',
                minimum_training_trades=40, minimum_training_pf=1.1, maximum_training_dd_multiple=1.5,
                finalists='Top three non-current broker 2020-2023 training options also eligible on Dukascopy training',
                rolling='Dukascopy train 2016-2019, 2018-2021, 2020-2023; following two years test',
                end_exclusive=str(CUTOFF), daily_warmup=250, other_warmup_calendar_days=180,
                risk_pct=.005, starting_balance=10000, default_spread_points=1,
                commission=0, actual_swap=False, news=False, shared_portfolio=False,
                extra_slippage=False, daily_loss_gate=False, optimization='one variable at a time',
                fresh_unseen_data=False, demo_changes=False))
        # Resume only an identical experiment; never silently mix runs.
        OUT.mkdir(parents=True, exist_ok=True)
        if (OUT/'manifest.json').exists():
            assert json.loads((OUT/'manifest.json').read_text()) == json.loads(json.dumps(manifest,default=str))
        else:
            write_json(OUT/'manifest.json', manifest)
        self.manifest = manifest

    def load(self, source):
        self.bars = None
        self.source = source
        self.symbol, files = self.paths[source]
        print('Loading '+source, flush=True)
        self.bars = load_and_merge(files, start=datetime(2018,7,1) if source=='mt5_icmarkets_utc' else datetime(2016,1,1), end=CUTOFF)

    def run(self, option, label, start, end, spread=1):
        name = f'{self.source}_{option}_{label}_spread{spread}'
        file = OUT/(name+'.json')
        if file.exists() and (OUT/(name+'_trades.json')).exists():
            result = json.loads(file.read_text())
        else:
            params = deepcopy(self.params)
            params.update(OPTIONS[option])
            began = time.monotonic()
            result, trades = replay(self.bars, self.symbol, params, start, end, spread=spread)
            result.update(source=self.source,option=option,label=label,start=start,end=end,
                          spread=spread,seconds=time.monotonic()-began)
            write_json(OUT/(name+'_trades.json'), trades)
            write_json(file,result)
            print(json.dumps(dict(job=name,metrics=result['metrics'],seconds=result['seconds'])),flush=True)
        if not any((r['source'],r['option'],r['label'],r['spread']) ==
                   (result['source'],option,label,spread) for r in self.rows):
            self.rows.append(result)
            write_json(OUT/'results.json', self.rows)
        if option=='current' and spread==1:
            old = CORRECTED/f'{self.source}_corrected_{label}_trades.json'
            if old.exists():
                actual=json.loads((OUT/(name+'_trades.json')).read_text())
                assert actual == json.loads(old.read_text()), name+' baseline changed'
                old_result=json.loads((CORRECTED/f'{self.source}_corrected_{label}.json').read_text())
                assert json.loads(json.dumps(result['open_exposure'],default=str)) == old_result['open_exposure']
                control=dict(source=self.source,label=label,all_trade_fields_match=True,ending_exposure_matches=True)
                if control not in self.controls:
                    self.controls.append(control)
                    write_json(OUT/'controls.json',self.controls)
        return result

    def trades(self, source, option, label, spread=1):
        return json.loads((OUT/f'{source}_{option}_{label}_spread{spread}_trades.json').read_text())


def main():
    logging.disable(logging.CRITICAL)
    study=Study()
    training={}
    choices=[]
    # Freeze the whole search protocol above before looking at validation outcomes.
    study.load('dukascopy')
    for start, split, end in FOLDS:
        cohort=[study.run(option,f'fold_{split.year}_train',start,split) for option in OPTIONS]
        baseline=cohort[0]
        winners=ranked(cohort,baseline)
        winner=winners[0]['option'] if winners else 'current'
        choice=dict(source='dukascopy',test_year=split.year,option=winner,
                    training_ranking=[r['option'] for r in winners],fallback=not bool(winners))
        choices.append(choice)
        write_json(OUT/'rolling_choices.json',choices)
        for option in dict.fromkeys(('current',winner)):
            study.run(option,f'fold_{split.year}_test',split,end)
        if split.year==2024:
            training['dukascopy']={r['option']:r for r in cohort}
    study.load('mt5_icmarkets_utc')
    start,split,end=FOLDS[-1]
    cohort=[study.run(option,'fold_2024_train',start,split) for option in OPTIONS]
    training['mt5_icmarkets_utc']={r['option']:r for r in cohort}
    candidates=[r for r in ranked(cohort,cohort[0]) if r['option']!='current' and
        eligible(training['dukascopy'][r['option']],training['dukascopy']['current'])]
    finalists=[r['option'] for r in candidates[:3]]
    write_json(OUT/'finalists.json',dict(options=finalists,
        broker_training_ranking=[r['option'] for r in ranked(cohort,cohort[0])],
        joint_eligible_ranking=[r['option'] for r in candidates],
        selected_before_validation=True,created_utc=datetime.now(timezone.utc)))
    print('Frozen finalists: '+str(finalists),flush=True)
    # All finalist evaluations occur after the training-only selection above.
    for source in ('mt5_icmarkets_utc','dukascopy','histdata'):
        if study.source!=source:
            study.load(source)
        for option in ['current']+finalists:
            if source=='histdata':
                study.run(option,'fold_2024_train',start,split)
            study.run(option,'fold_2024_test',split,end)
            study.run(option,'2026_to_july14',end,CUTOFF)
            study.run(option,'2020_2025',start,end)
            if source=='mt5_icmarkets_utc':
                for spread in (2,5):
                    study.run(option,'2020_2025',start,end,spread)
    index={(r['source'],r['option'],r['label'],r['spread']):r for r in study.rows}
    validation=[]
    for source in SOURCES:
        for option in ['current']+finalists:
            train=index[source,option,'fold_2024_train',1]['metrics']
            test=index[source,option,'fold_2024_test',1]['metrics']
            validation.append(dict(source=source,option=option,train=train,test=test,**verdict(train,test)))
    write_json(OUT/'finalist_validation.json',validation)
    rolling=[]
    stitched={'current':[],'selected':[]}
    for choice in choices:
        year,option=choice['test_year'],choice['option']
        train=index['dukascopy',option,f'fold_{year}_train',1]['metrics']
        test=index['dukascopy',option,f'fold_{year}_test',1]['metrics']
        rolling.append(dict(**choice,train=train,test=test,**verdict(train,test)))
        for label,key in [('current','current'),('selected',option)]:
            stitched[label].extend(study.trades('dukascopy',key,f'fold_{year}_test'))
    write_json(OUT/'rolling_validation.json',dict(folds=rolling,stitched={key:metrics(trades) for key,trades in stitched.items()},
        note='Independent fresh-start folds; boundary exposure omitted, not continuous equity or fresh unseen data.'))
    assert all(file_hash(ROOT/p)==h for p,h in study.manifest['code_hashes'].items())
    assert all(file_hash(p)==h for p,h in study.manifest['metadata_hashes'].items())
    write_json(OUT/'complete.json',dict(replays=len(study.rows),controls=len(study.controls),
        options=len(OPTIONS),finalists=finalists,code_hashes_match=True,metadata_hashes_match=True))
    print('Failed2 parameter study complete.',flush=True)


if __name__=='__main__':
    main()
