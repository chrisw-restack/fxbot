# IMS Reversal feed variance diagnosis, 2 October 2026

Some divergence between broker quotes is expected, but the observed performance
range cannot be treated as harmless price-feed noise. Two controlled replays
show that missing bars and H4 candle construction can reverse the sign of profit
without changing the strategy's parameters. They do not establish a new engine
bug as the cause of the overall performance difference.

## Missing-bar control

Used the same 2022-04-29 22:00 to 2024-12-23 22:00 UTC trading segment and its
180-day warmup from the frozen comparison. Kept Dukascopy prices and all remaining
OHLC values unchanged, but removed any M5/M15/H4 timestamp absent from HistData.
This removes 9,896 M5, 3,299 M15, and 15 H4 records across the loaded segment,
including warmup. No interpolation or parent OHLC reconstruction was performed.

The 2023 closed-trade results below all use the same 1.1-pip spread and zero
commission. Their state evolves through the same segment from 2022.

| Case, 2023 closes | Trades | Win % | Net R | PF | R/trade | Max closed-R DD | W/L streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| Original Dukascopy | 22 | 13.6 | -5.87 | 0.69 | -0.267 | 14.02 | 1/10 |
| Dukascopy prices, HistData availability | 14 | 21.4 | +11.02 | 2.20 | +0.787 | 5.16 | 1/7 |
| Actual repaired HistData | 14 | 35.7 | +19.03 | 3.66 | +1.359 | 3.00 | 1/3 |

Changing bar availability alone produces a +16.88R change in this particular
counterfactual. It does not reproduce the full HistData result. The residual
difference needs individual price and parent-candle investigation, and the
effects cannot be assumed additive in a strategy with persistent state.

HistData lacks 9,799 reference M5 timestamps in the matched 2023 trading windows,
while 99.979% of common M5 OHLC values across the full historical comparison
match Dukascopy to five decimals. Higher HistData returns cannot therefore be
counted as independent confirmation. Removing quotes can skip a trigger, stop,
or cancellation and can alter later setup state. Missing prices are a data
problem; completing UTC provenance did not make quote coverage complete.

The saved HistData replay also contains pending fills after missing-price
intervals where the quoted opening fill is already beyond the attached stop.
Without the omitted prices, that replay cannot establish whether the order
should have filled or stopped earlier. This is another reason to withhold
confidence in the gap-affected trade paths. It is not proof of how a real broker
would execute a pending order across a genuine market gap.

## H4 construction control

Used January to 14 July 2026 with the original 180-day warmup. Kept Dukascopy M5
execution prices, M15 candles, costs, and strategy parameters unchanged. Rebuilt
only H4 OHLC from those same M5 prices using the audited XM H4 opening timestamps.
The experiment also follows XM's observed H4 anchor availability, so it does not
separately quantify clock boundaries versus absent H4 anchors. Partial M5 buckets
remain partial; no prices are invented. Higher-timeframe prices are processed
only after the corresponding four-hour interval is complete.

| Case, January to 14 July 2026 | Trades | Win % | Net R | PF | R/trade | Max closed-R DD | W/L streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| Original Dukascopy H4 | 9 | 22.2 | +3.23 | 1.46 | +0.359 | 4.00 | 2/4 |
| Dukascopy prices, H4 on XM openings | 10 | 0.0 | -10.00 | 0.00 | -1.000 | 10.00 | 0/10 |
| Actual XM | 9 | 0.0 | -9.00 | 0.00 | -1.000 | 9.00 | 0/9 |
| Actual IC Markets | 8 | 0.0 | -8.05 | 0.00 | -1.007 | 8.05 | 0/8 |

Dukascopy H4 candles open at 00/04/08/12/16/20 UTC. XM's accepted recent series
uses 22/02/06/10/14/18 UTC in winter and 21/01/05/09/13/17 UTC in summer. The
different four-hour slices produce different highs, lows, EMA values, fractals,
setup origins, and target levels. Converting timestamps to UTC preserves a
broker candle's actual interval; it does not make that candle equivalent to a
UTC-midnight four-hour bucket. XM and IC Markets also use different DST schedules
in the accepted exports during transition weeks.

In the original Dukascopy 2026 replay, the March 24 and April 10 SELL trades
contribute +6.00R and +4.23R. Neither broker replay has those two winning entries.
The controlled H4 reconstruction loses every closed trade despite retaining
Dukascopy prices. This establishes material sensitivity to H4 construction in
this period, not a complete explanation of every cross-feed trade difference.

## Interpretation and next research steps

The evidence points to incomplete price coverage and a strategy that depends
strongly on candle construction. Profit concentrated in a few large winners
magnifies those differences. Small quote or spread differences can still change
a threshold crossing, but they are not the only causes here.

For a clean cross-price comparison, rebuild M15 and H4 from each feed's M5 on
one prespecified common UTC grid and compare only adequately covered windows.
Keep native broker candles as a separate deployment comparison. Establish the
common grid before reviewing results and do not select the most profitable
session boundary. Investigate or exclude gap-affected HistData trades before
using that source to support a strategy decision. Do not fill its missing prices
from another provider and call the repaired mixture an independent feed.

Then trace the first differing setup/entry/exit for remaining broker differences,
and test small price and spread perturbations with frozen parameters. A strategy
whose profit survives only one particular candle construction remains fragile
even if its implementation matches its documented rules. These controls are
retrospective diagnostics, not a new walk-forward validation or an approval to
alter DEMO membership, migrate brokers, or trade real money.

Both additional controls use one worker, make no MT5 calls, preserve the
2026-07-14 research boundary, and end with zero positions or pending orders.
Reproduce with `python diagnose_ims_reversal_feed_variance.py`. Inputs are checked
against the earlier comparison's SHA256 manifest; raw results, trades, removed
bar counts, aggregation counts, and the diagnostic code hash are saved under
`output/ims_reversal_feed_variance_20261002/`. Two focused tests confirm that later
H4 bucket prices and quotes beyond a missing anchor cannot leak into an earlier
bucket. All production settings and code remain unchanged.

Background on broker price differences is described by the
[BIS discussion of the fragmented FX market](https://www.bis.org/publications/dealer-customer-and-inter-dealer-trading-fragmented-spot-market).
MT5's [price data documentation](https://www.metatrader5.com/en/terminal/help/trading_advanced/price_data)
describes bid-based OTC bars and their aggregation. The numerical conclusions
above come from the local controlled replays, not those general sources.
