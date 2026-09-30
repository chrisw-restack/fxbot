# Candle Confirmation GBPUSD review, 2026-09-30

The shared strategy now tracks orders and validates executable stops correctly. Its GBPUSD rules are reproducible and use completed bars, but the current broker edge is too thin to treat as robust. I recommend pausing new GBPUSD DEMO entries and keeping this implementation for further research. This review makes no membership or parameter change.

## Current candidate and meaning

- H1 establishes directional bias when its close breaks the preceding candle body.
- M5 waits for a 50% retracement, a confirmed swing with three bars on each side, and a three-candle price gap somewhere in the selected leg.
- Daily EMA20/50 must agree with direction and be separated by at least 0.1%. H1 range must be at least eight pips, and body at least 60% of its full range.
- TP is at 150% of the H1 range from its opposite extreme. Symmetric SL is derived from the target distance for 2:1 proposed R:R. It is not necessarily beyond a structural swing.
- Minimum proposed and executable stop is eight pips. All UTC entry hours are allowed. Engulf candle color is not required. Global planned account risk is 0.5%.

The name does not imply a textbook full-body engulf. A close beyond the previous body is enough even if the new open does not wrap the body, and color can differ after a gap. A BUY setup expires when price touches its H1 high before entry; SELL expires at its low. It can survive crossing the opposite extreme. In practice this often makes it a trend-following recovery pattern after a sweep through the range, rather than an entry contained within that range.

The code may enter on a later close beyond an already-broken swing if the earlier crossing did not satisfy the gap requirement. This is consistent with the present rule, but differs from requiring a new crossing on the entry candle. Both interpretations were tested separately.

## Correctness checks

The confirmed fractal uses completed right-wing bars before the entry candle. Higher timeframe candles are dispatched at their close, and market fills occur at the next M5 open using bid/ask conventions. Reproductions and accepted-context checks found no future-bar use. Filled trades retain their originating H1 setup and attempt ID. Old closures, partial fills, rejected fills, and restart recovery use the shared lifecycle corrections from the USDJPY work.

Warmup requests 250 D1, 100 H1, and 1,200 M5 completed bars. Each reviewed feed has at least these counts before January 2017. Every corrected filled trade has at least an eight-pip stop and 1:1 filled R:R. Tracking alone matches every economic field of the frozen pre-tracking class on all three feeds. The observation wrapper exactly matches plain production trades and end exposure on all three feeds.

The final MT5 quote is checked before submission. A reported fill is checked after acknowledgement; slippage can still violate the minimum after the order is real. Those positions remain tracked and violations are logged. Missing actual fill prices are unknown. No MT5 connection was attempted in this review.

## Matched current performance

January 1, 2017 through July 14, 2026, after the same completed 2016 warmup. The period matches the corrected USDJPY baseline. Prices after the research cutoff are excluded from replay and parameter decisions. This is standalone replay, with a 0.2-pip spread, configured round-trip commission, and 0.5% planned risk. No news filter, competing strategies, or daily-loss cap is applied. Swap and actual tick slippage are not modeled. Open exposure is never forcibly closed.

Current corrected settings across feeds

| Case | Trades | Win % | Net R | PF | R/trade | Closed DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| Dukascopy | 399 | 38.10 | +27.82 | 1.105 | +0.0697 | 18.87 | 5/11 |
| HistData | 399 | 37.34 | +16.84 | 1.063 | +0.0422 | 19.69 | 8/11 |
| IC Markets | 397 | 36.27 | +4.95 | 1.018 | +0.0125 | 23.28 | 5/10 |

| Feed | Planned-budget R | Account growth | Equity DD | Minimum filled stop |
|---|---:|---:|---:|---:|
| Dukascopy | +27.70 | +13.68% | 8.95% | 8.00 pips |
| HistData | +17.26 | +7.91% | 9.36% | 8.00 pips |
| IC Markets | +5.12 | +1.58% | 11.60% | 8.03 pips |

Net R uses actual filled entry-to-stop risk, including spread and commission. Planned-budget R uses 0.5% of standalone balance for that trade and reconciles to ending balance. Closed R drawdown and marked-to-market percentage drawdown use different units. The broker return is small compared with its drawdown, despite the positive final total.

Effect of the executable stop guard

| Case | Trades | Win % | Net R | PF | R/trade | Closed DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| Dukascopy / before fill guard | 399 | 38.35 | +31.05 | 1.118 | +0.0778 | 18.87 | 5/11 |
| Dukascopy / current corrected | 399 | 38.10 | +27.82 | 1.105 | +0.0697 | 18.87 | 5/11 |
| HistData / before fill guard | 400 | 37.75 | +22.07 | 1.083 | +0.0552 | 19.69 | 8/11 |
| HistData / current corrected | 399 | 37.34 | +16.84 | 1.063 | +0.0422 | 19.69 | 8/11 |
| IC Markets / before fill guard | 397 | 36.27 | +4.95 | 1.018 | +0.0125 | 23.28 | 5/10 |
| IC Markets / current corrected | 397 | 36.27 | +4.95 | 1.018 | +0.0125 | 23.28 | 5/10 |

The guard rejects one undersized fill on Dukascopy and three on HistData. Later decisions can change after a rejection, so the corrected result is a full replay. No current-baseline broker fill breaches eight pips; its results are unchanged by the guard. These controls use today's shared simulator with frozen earlier signal logic. They do not reproduce every simulator version used by the May or August reports.

Isolated rule experiments, 0.2-pip spread

| Case | Trades | Win % | Net R | PF | R/trade | Closed DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| Dukascopy / current corrected | 399 | 38.10 | +27.82 | 1.105 | +0.0697 | 18.87 | 5/11 |
| Dukascopy / fresh crossing only | 376 | 38.03 | +25.55 | 1.102 | +0.0680 | 20.61 | 4/11 |
| Dukascopy / expire opposite extreme | 220 | 35.91 | +1.26 | 1.008 | +0.0057 | 27.92 | 6/11 |
| HistData / current corrected | 399 | 37.34 | +16.84 | 1.063 | +0.0422 | 19.69 | 8/11 |
| HistData / fresh crossing only | 378 | 37.30 | +15.61 | 1.061 | +0.0413 | 21.11 | 6/12 |
| HistData / expire opposite extreme | 218 | 35.78 | -1.54 | 0.990 | -0.0071 | 23.33 | 7/11 |
| IC Markets / current corrected | 397 | 36.27 | +4.95 | 1.018 | +0.0125 | 23.28 | 5/10 |
| IC Markets / fresh crossing only | 373 | 35.66 | -2.16 | 0.992 | -0.0058 | 23.07 | 4/12 |
| IC Markets / expire opposite extreme | 219 | 32.42 | -23.91 | 0.850 | -0.1092 | 36.38 | 7/10 |

Fresh crossing reduces the full-period total on all three feeds and makes the broker result negative. Expiring at the opposite engulf extreme removes much of the positive recovery contribution and also fails. Neither experiment is a validated replacement. The rules were tested individually, never combined or promoted to production.

Broker spread stress, full history

| Case | Trades | Win % | Net R | PF | R/trade | Closed DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0.2 pips / current corrected | 397 | 36.27 | +4.95 | 1.018 | +0.0125 | 23.28 | 5/10 |
| 0.2 pips / fresh crossing only | 373 | 35.66 | -2.16 | 0.992 | -0.0058 | 23.07 | 4/12 |
| 0.2 pips / expire opposite extreme | 219 | 32.42 | -23.91 | 0.850 | -0.1092 | 36.38 | 7/10 |
| 1 pips / current corrected | 397 | 35.26 | -20.53 | 0.925 | -0.0517 | 31.07 | 5/10 |
| 1 pips / fresh crossing only | 374 | 34.76 | -24.50 | 0.906 | -0.0655 | 30.04 | 4/13 |
| 1 pips / expire opposite extreme | 219 | 31.96 | -34.30 | 0.786 | -0.1566 | 40.97 | 7/11 |
| 2 pips / current corrected | 397 | 34.76 | -41.10 | 0.851 | -0.1035 | 43.73 | 5/10 |
| 2 pips / fresh crossing only | 374 | 34.22 | -43.81 | 0.833 | -0.1171 | 46.88 | 4/13 |
| 2 pips / expire opposite extreme | 219 | 31.51 | -45.26 | 0.719 | -0.2067 | 46.64 | 7/11 |

These are constant-spread stress scenarios, not measured historical spreads. They replay fills, stop/target hits, and subsequent decisions at the wider spread. At one pip, current settings lose -20.53R; at two pips, -41.10R. All three rule interpretations fail the wider-spread scenarios.

Broker chronological checks with current settings

| Case | Trades | Win % | Net R | PF | R/trade | Closed DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| July 2020-June 2022 | 83 | 37.35 | +2.85 | 1.051 | +0.0343 | 10.10 | 4/7 |
| July 2022-June 2024 | 81 | 40.74 | +9.77 | 1.183 | +0.1206 | 8.08 | 4/6 |
| July 2024-June 2026 | 68 | 35.29 | -0.47 | 0.990 | -0.0069 | 11.31 | 3/10 |
| Combined July 2020-June 2026 | 232 | 37.93 | +12.15 | 1.078 | +0.0524 | 11.31 | 4/10 |
| Calendar 2020-2025 | 245 | 36.73 | +4.77 | 1.028 | +0.0195 | 23.09 | 4/9 |
| January-July 14, 2026 | 18 | 33.33 | -1.12 | 0.912 | -0.0620 | 4.20 | 3/4 |

These are later historical windows from continuous replay, not a new optimized walk-forward study or untouched holdout. No parameter selection occurs in this review. Training subdivisions start in January 2017 for the first window and span four years thereafter. Earlier training totals are negative, so a simple retention ratio is not a useful validation grade. The old MODERATE label and +41.4R fixed-candidate OOS figure refer to earlier evidence and do not establish robustness under today's broker/cost model.

Broker direction comparison, current settings

| Case | Trades | Win % | Net R | PF | R/trade | Closed DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| BUY | 227 | 37.44 | +7.71 | 1.050 | +0.0340 | 13.37 | 5/8 |
| SELL | 170 | 34.71 | -2.76 | 0.977 | -0.0162 | 17.68 | 3/9 |

Descriptive broker setup groups, current settings

| Case | Trades | Win % | Net R | PF | R/trade | Closed DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| fresh cross true | 337 | 35.91 | +0.09 | 1.000 | +0.0003 | 23.31 | 4/10 |
| fresh cross false | 60 | 38.33 | +4.86 | 1.124 | +0.0809 | 7.90 | 3/5 |
| opposite extreme breached true | 181 | 40.88 | +28.61 | 1.252 | +0.1581 | 8.79 | 4/8 |
| opposite extreme breached false | 216 | 32.41 | -23.66 | 0.850 | -0.1095 | 36.38 | 7/10 |

Broker signals include 60 later crossings out of 397 and 181 setups whose opposite extreme had been breached. The recovery group contributes +28.61R, while the group without that breach contributes -23.66R. This is a useful research lead, not an already-tested recovery-only strategy. Selecting a subgroup changes later setup opportunities; deleting other trades is not a substitute for replay. BUY-only also remains a descriptive split, not an optimized or validated direction filter.

## Data and deployment limitations

Verified HistData sidecars and source/input hashes passed the loader and completion checks. HistData is positive here, with 399 trades and +16.84R, but weaker than Dukascopy's +27.82R. Prices on matching M5 timestamps are more than 99.94% identical in every year from 2019 onward. It is not independent feed confirmation. Earlier 2017-2018 prices differ.

HistData has provider gaps from February through July 2023. April contains 3,924 M5 bars versus 5,796 Dukascopy and 5,778 broker. Only five resampled M5 candles are excluded by the known-conflict policy across the entire converted file, which cannot explain those large gaps. No prices, clocks, or missing rows were changed for this review.

Daily candle boundaries differ. Dukascopy/HistData are aligned to UTC midnight; broker D1 sessions start at 21:00 or 22:00 UTC. The loader preserves genuine broker Sunday-stamped Monday sessions. Thus the D1 trend gate can differ even when M5 prices are similar. A common-session D1 comparison would be a separate controlled experiment.

The broker baseline has 112 trades spanning a UTC date change and a maximum holding time of 130 hours. This is an overnight proxy rather than a precise count of swap charges. Historical swap can materially change a result this close to break-even. Full-suite limits, correlated USD exposure, and varying spread/slippage also remain outside the standalone result.

## Copied DEMO evidence

Five closed GBPUSD trades from July 28 through September 17, 2026 show one win, net -$354.15 after commission/swap, money PF 0.408, closed money drawdown $354.15, and a longest loss streak of two. All five tickets and net profits match the journal. Broker report times remain wall time rather than being guessed into UTC.

The journal records 11 signals, five submitted orders, and six execution rejections from May-July. Two journal diagnostics and two corresponding log entries explicitly show invalid broker-comment arguments; the remaining two failures have incomplete diagnostics. Current MT5 code already uses shortened comments and durable submission identities. These older failures are not new defects introduced by tracking.

The copied history precedes the September 18 restart and the present local corrections. It mixes older versions and sizing and contains too few trades to establish or refute the corrected edge. It is forward evidence after the historical research cutoff and was not used to choose the tested hypotheses.

## Recommendation

Retain the shared tracking, warmup, and executable-stop corrections. They make this strategy suitable for controlled research, but its existing GBPUSD settings have too little broker margin to justify calling the edge robust. I recommend pausing new GBPUSD DEMO entries while investigating a more specific hypothesis. No production membership, risk, symbols, parameters, or host state changed in this analysis.

The strongest lead is an explicit recovery after the opposite engulf extreme is crossed. Test that as one predeclared logic change, compare it with the current control, and select any parameters using training data only. Require stability in later periods and broker costs, rather than optimizing the full-period subgroup. Do not enable the fresh-cross or opposite-extreme-expiry variants from this review.

Before a further DEMO decision, gather current GBPUSD spreads during the actual entry hours, including rollover, and review new fill/stop diagnostics and broker swap. On the Windows trading host, the existing read-only monitor can be run in several sessions with `python measure_spreads.py --symbols GBPUSD --duration 300 --interval 0.5`. A five-minute snapshot alone is not a historical spread model.

## Verification and artifacts

All 228 repository tests pass. Completed 21 sequential research cases plus three additional plain-production replays. Six exact comparisons verify original versus tracking and production versus observer across all three feeds. Source/CSV/sidecar hashes, accepted/closed/rejected counts, attribution, fractal chronology, actual stop distance, and filled R:R are audited.

Frozen inputs, settings, results by year/window/direction, contexts, trade lists, feed audits, synthetic rule reproductions, and copied DEMO reconciliation are under `output/candle_gbpusd_review_20260930/`. Main scripts are `research_candle_gbpusd_review.py`, `audit_candle_gbpusd_review.py`, and `summarize_candle_gbpusd_review.py`. The research runner refuses to overwrite an existing manifest. No MT5 terminal access is required for these replays.
