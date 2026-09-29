"""Summarize the frozen Failed2 parameter study without changing selection."""
from copy import deepcopy
import json
from statistics import median

from data.histdata_provenance import write_json
from research_failed2_parameters import OUT, ROOT, OPTIONS, eligible
from research_ema_fib_review import metrics
from summarize_ema_fib_tracking import table


def read(name):
    return json.loads((OUT/name).read_text())


def main():
    done=read('complete.json')
    rows=read('results.json')
    finalists=read('finalists.json')['options']
    options=['current']+finalists
    validation=read('finalist_validation.json')
    rolling=read('rolling_validation.json')
    index={(r['source'],r['option'],r['label'],r['spread']):r for r in rows}
    descriptions={
        'current':'Current: target 4R; MSS 4; stop fractal 2; daily range threshold 0.70 over 60 days; 13:00–16:00 UTC; D1 EMA20/50',
        **{f'rr_{v:g}':f'Target {v:g}R instead of 4R' for v in (2.5,3.,3.5,4.5,5.)},
        **{f'mss_{v}':f'Structure fractal {v} instead of 4' for v in (2,3,5)},
        **{f'stop_{v}':f'Stop fractal {v} instead of 2' for v in (1,3)},
        **{f'range_{v:g}':f'Daily range blocking percentile {v:.2f} instead of 0.70' for v in (.6,.8,.9)},
        **{f'lookback_{v}':f'Daily range lookback {v} instead of 60' for v in (40,90)},
        'session_12_16':'Session 12:00–16:00 UTC instead of 13:00–16:00',
        'session_13_17':'Session 13:00–17:00 UTC instead of 13:00–16:00',
        'trend_off':'Disable the D1 EMA direction filter; retain the range filter',
    }
    sections=['# Failed2 parameter study, completed 29 September 2026',
        f"Completed {done['replays']} serial replays across {done['options']} configurations, including {done['controls']} exact controls against the corrected review. The search changes one parameter at a time. No DEMO settings, risk, production logic, or MT5 account state changed.",
        '## Recommendation',
        'Keep the current parameters. This bounded search did not establish a convincing improvement. Retain the 4R signal-price target, structure fractal 4, stop fractal 2, 60-day range lookback with a 0.70 blocking threshold, D1 EMA20/50 direction filter, and 13:00–16:00 UTC session. This is a comparison of the tested choices, not proof that the current settings are globally optimal.',
        'Extending the session to 17:00 looked better in broker training, but the following 2024–2025 test fell from +17.28R to +4.28R, with drawdown increasing from 7.09R to 10.53R. Its January–14 July 2026 broker result also fell, from +16.41R to +9.55R. Reject this extension from the current evidence.',
        'A 90-day range lookback is almost identical to 60 days over the full broker history, +53.26R versus +53.29R, and improves the recent broker slice by just 1R over 17 trades. It reduces returns on the longer feeds. That small recent gain is insufficient reason to change the configuration. The 40-day lookback also gives lower full-period and recent broker returns, despite retaining a STRONG training/test ratio. Retention alone does not establish improvement over the current strategy.',
        'The rolling search selected 5R for its first two tests and current settings for the last. Combining those independent test folds gives +98.40R and 16R drawdown, versus +100.79R and 13.04R drawdown with current settings throughout. The selected parameters therefore do not improve this historical comparison.',
        'The 4.5R target led eligible broker training returns, +43.14R versus +36.01R, but its Dukascopy training drawdown was 16R against the predeclared 15R cap. It was screened out before finalist testing. This report does not claim to have disproved untested validation performance for that setting. Removing the trend filter was also screened out; broker training drawdown reached 26.14R with a 25-loss streak.',
        'All finalists remain profitable in the full broker replay with five-point spread and in a separate illustrative financing-debit scenario. The current settings still give the strongest returns in those comparisons. Keep collecting DEMO evidence from the corrected implementation; these reused historical periods do not resolve its weak recent long-feed retention or the earlier weak DEMO sample.',
        '## Tested choices',
        '\n'.join('- '+descriptions[key]+'.' for key in OPTIONS),
        'Session bounds refer to M5 bar-opening labels; the last permitted signal bar closes at the stated ending time. Every alternative changes only the listed parameter. No combinations of winning parameters were constructed after seeing results.',
        '## Selection protocol',
        'The protocol and all options were written and hash-bound before the runs. Training eligibility requires at least 40 closed trades, positive total R, profit factor of at least 1.10, and maximum closed-trade R drawdown no more than 1.5 times current settings in that training period. Eligible choices are ranked by total R, then lower drawdown and option name. These are research screening limits, not account-risk guarantees.',
        'The Dukascopy rolling search selects separately on 2016–2019, 2018–2021, and 2020–2023, then tests the selected choice on the following two years. Broker screening uses 2020–2023. Its top three non-current choices that also pass the Dukascopy 2020–2023 training limits are frozen before finalist evaluation. HistData is used to compare those frozen finalists, not to choose them. Recent evaluation ends on 14 July 2026.',
        'These historical periods were used in earlier development. Training/test separation prevents this sweep from choosing on its test results, but does not make the periods untouched or erase prior selection bias. Dukascopy and HistData have near-identical shared M5 prices, so agreement between them is not independent-feed confirmation.',
        '## Training results, 2020 through 2023']
    for source in ('mt5_icmarkets_utc','dukascopy'):
        cohort=[index[source,option,'fold_2024_train',1] for option in OPTIONS]
        cohort.sort(key=lambda r:-r['metrics']['total_r'])
        baseline=index[source,'current','fold_2024_train',1]
        sections.extend([source,
            table([(r['option']+(' [eligible]' if eligible(r,baseline) else ' [excluded]'),r['metrics']) for r in cohort])])
    sections.extend(['## Frozen finalists',
        '\n'.join('- '+descriptions[key]+'.' for key in finalists) or 'No alternative passed the training screens.',
        'The finalist order is the broker training ranking. It is not a ranking chosen after examining validation.',
        '## Later historical test, 2024 through 2025',
        table([(f'{source}, {option}',index[source,option,'fold_2024_test',1]['metrics'])
               for source in ('mt5_icmarkets_utc','dukascopy','histdata') for option in options])])
    lines=['| Source | Option | Expectancy retention | Verdict |','|---|---|---:|---|']
    for row in validation:
        value='undefined' if row['retention'] is None else f"{row['retention']*100:.1f}%"
        lines.append(f"| {row['source']} | {row['option']} | {value} | {row['verdict']} |")
    sections.extend(['\n'.join(lines),
        'Retention is test R/trade divided by training R/trade. STRONG starts at 70%; MODERATE at 40%; below 40% is WEAK. A losing test fails regardless of retention.',
        '## January through 14 July 2026',
        table([(f'{source}, {option}',index[source,option,'2026_to_july14',1]['metrics'])
               for source in ('mt5_icmarkets_utc','dukascopy','histdata') for option in options]),
        '## Full period, 2020 through 2025',
        table([(f'{source}, {option}',index[source,option,'2020_2025',1]['metrics'])
               for source in ('mt5_icmarkets_utc','dukascopy','histdata') for option in options]),
        'This full-period comparison includes training observations. Do not treat it as independent validation.',
        '## Rolling parameter selection on Dukascopy',
        table([(f"test {row['test_year']}, {option}",index['dukascopy',option,f"fold_{row['test_year']}_test",1]['metrics'])
               for row in rolling['folds'] for option in dict.fromkeys(('current',row['option']))]),
        '\n'.join(f"- Test {r['test_year']}: selected {r['option']} from training only; retention {r['retention']*100:.1f}%, {r['verdict']}." if r['retention'] is not None else
                  f"- Test {r['test_year']}: {r['option']}, retention undefined." for r in rolling['folds']),
        table(list(rolling['stitched'].items())),
        'The stitched table combines closed trades from independent test folds with fresh starting state and balance. Boundary positions remain unclosed and are excluded. It is a historical comparison of the selection rule, not continuous account equity or a deployable rule validated on unseen data.',
        '## Broker spread stress, 2020 through 2025',
        table([(f'{option}, {spread} points',index['mt5_icmarkets_utc',option,'2020_2025',spread]['metrics'])
               for option in options for spread in (1,2,5)])])
    financing=[]
    holds=[]
    for option in options:
        trades=read(f'mt5_icmarkets_utc_{option}_2020_2025_spread1_trades.json')
        holds.append(dict(option=option,median_hours=median(t['duration_hours'] for t in trades),
                          maximum_hours=max(t['duration_hours'] for t in trades)))
        for debit in (0,3,7):
            adjusted=deepcopy(trades)
            for trade in adjusted:
                trade['net_r']-=debit*trade['lot_size']*trade['duration_hours']/24/trade['initial_risk']
            financing.append(dict(option=option,debit_per_lot_day=debit,metrics=metrics(adjusted)))
    write_json(OUT/'financing_sensitivity.json',financing)
    write_json(OUT/'holding_durations.json',holds)
    sections.extend(['## Illustrative broker financing sensitivity',
        table([(f"{r['option']}, ${r['debit_per_lot_day']}/lot/day",r['metrics']) for r in financing]),
        'These are hypothetical uniform debits on the existing trade paths. They do not reconstruct actual swap, credits, triple-swap days, changed sizing, or changed trade paths. Spread stress and this financing sensitivity are separate scenarios, not combined costs.',
        '| Option | Median holding hours | Longest holding hours |\n|---|---:|---:|\n'+
        '\n'.join(f"| {r['option']} | {r['median_hours']:.2f} | {r['maximum_hours']:.2f} |" for r in holds),
        'The strategy has no time exit. Long holds and weekend gap losses remain possible; a nominal 1R stop is not a guaranteed loss limit.',
        '## Data, controls, and limits',
        'All sources use corrected Failed2 market logic, M5 execution, completed H1/H4/D1 inputs, $10,000 starting balance, 0.5% risk, and zero index commission. Default spread is one index point. USA100 and USTEC use the same one-point pip size and $1 per point per lot assumptions. Broker H4 uses the full newer export. HistData passes provenance checks. The manifest records every input, sidecar, and relevant code hash.',
        'D1 warm-up uses up to 250 completed bars; other streams use 180 calendar days, as in the corrected comparison. The first 2016 training window has no earlier history and waits for indicator readiness. Each later replay starts fresh from prior history. No price bars after 14 July 2026 enter the study.',
        'Actual financing, variable spread, extra slippage, news filters, shared-account position limits, and daily-loss gates are excluded from the main tables. Profit factor divides positive net R by absolute negative net R; it can differ from a dollar-based profit factor under changing lot sizes. Drawdown is based on closed-trade R, not floating equity. Broker candle boundaries differ from the UTC-aligned long-history feeds, so source comparisons include session construction as well as price differences.',
        f"All {done['controls']} controls exactly match every trade field and ending exposure saved in the corrected review. Code and metadata hashes remained unchanged during the runs. No strategy implementation was modified for this sweep.",
        '## Period-end exposure',
        '\n'.join(f"- {r['source']} {r['option']} {r['label']} spread {r['spread']}: {len(r['open_exposure'])} open/pending." for r in rows if r['open_exposure']) or 'All replays ended flat.',
        'No future prices are used to close these positions. Different settings can leave different exposure at a cutoff, so closed-trade results are not a complete mark-to-market comparison.',
        '## Reproduction',
        '```powershell\npython research_failed2_parameters.py\npython summarize_failed2_parameters.py\n```',
        'Use the project backtest environment and one worker. The study resumes cached jobs only when its manifest is identical. Results, all trades, frozen selections, rankings, checks, and sensitivity tables are under output/failed2_parameters_20260928/. DEMO configuration is unchanged.'])
    report=ROOT/'strategy_log/failed2_parameters_20260928.md'
    report.write_text('\n\n'.join(sections)+'\n',encoding='utf-8')
    print(report)


if __name__=='__main__':
    main()
