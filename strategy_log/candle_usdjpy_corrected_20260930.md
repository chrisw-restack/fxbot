# Candle Confirmation USDJPY tracking baseline, 2026-09-30

Implemented the requested attribution, warmup, and executable stop checks locally. The fixed parameters still do not show a consistent edge across the available feeds. This is a baseline for future research, not a parameter promotion or host deployment.

## What changed

- A setup is identified by strategy, symbol, direction, and the originating H1 candle in UTC. Each proposed entry has its own timestamped attempt ID.
- Accepted orders retain ownership until a confirmed cancellation or final close. An old close cannot clear a newer setup. Rejected fills release their own attempt. Partial closes and cancelled remainders preserve filled exposure.
- All final outcomes, including break-even, consume their own originating setup. Duplicate callbacks are harmless. Legacy positions block entries conservatively; their unknown origin is never inferred from the latest bias.
- The existing account-bound durable ledger and code/config-bound checkpoint preserve attribution across restarts. Changed source invalidates old checkpoints; it does not discard the ledger.
- Current D1 EMA20/50 settings request 250 D1, 100 H1, and 1,200 M5 completed bars. The demo runner already enforces the requested counts and chronological replay. CSV backtests and OOS warmup now allow more calendar history when the strategy requires it. Calendar allowance alone cannot guarantee enough bars in a source with gaps.
- The strategy minimum is passed as a price distance through risk and execution. For USDJPY this is 0.08, or eight pips. Simulated market orders check the next-open bid/ask fill before creating exposure. MT5 checks the final rounded request quote before submission, then checks the reported broker fill after acknowledgement.
- Broker slippage can still violate the minimum after submission. Such a real position retains its ticket and is logged as a violation; it is not treated as a rejected order or automatically closed. A missing broker fill price is marked unknown rather than reported as a confirmed pass.
- Signal and order journal context now includes origin/attempt IDs, engulf range and retracement, pivot time and level, previous close, fresh-cross status, opposite-extreme breach, and trend alignment. These are observations. They do not enable new entry filters. MT5 execution context records the fill, stop validation, and price source.
- The shared Candle Confirmation class also gives GBPUSD these lifecycle and minimum-stop checks. GBPUSD performance was not reassessed here. Entry rules, parameters, risk, and DEMO membership remain unchanged.

## Matched comparison

USDJPY only, January 1, 2017 through July 14, 2026. All variants use the same completed 2016 warmup history and unchanged DEMO parameters. Trading starts in 2017 so each feed has at least 250 completed D1 bars. This differs from the preceding July 2016-start review and its totals must not be mixed with these figures. Replay is sequential, with a 0.2-pip spread, configured commission, and 0.5% planned account risk. It has no other strategies, news filter, portfolio competition, or forced end liquidation.

| Feed | Version | Trades | Win % | Net R | PF | R/trade | Closed DD R | Win/loss streak |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Dukascopy | original | 578 | 43.94 | +32.20 | 1.092 | +0.0557 | 21.14 | 9/13 |
| Dukascopy | corrected | 577 | 44.02 | +7.58 | 1.022 | +0.0131 | 29.37 | 9/13 |
| HistData | original | 564 | 43.09 | -7.06 | 0.980 | -0.0125 | 40.33 | 9/13 |
| HistData | corrected | 563 | 43.16 | -6.06 | 0.983 | -0.0108 | 40.33 | 9/13 |
| IC Markets | original | 598 | 42.47 | -16.47 | 0.956 | -0.0275 | 36.40 | 7/10 |
| IC Markets | corrected | 597 | 42.71 | -12.77 | 0.966 | -0.0214 | 35.24 | 7/10 |

Tracking-only runs match every economic trade field of the frozen original class on all three feeds. The corrected version adds the executable stop guard. Each feed rejects four undersized fills; subsequent setup decisions can change, so the effect cannot be estimated by deleting those trades from an old trade list. All nine replays end with no open exposure.

Net R uses actual filled entry-to-stop risk after costs. The old Dukascopy result includes the +27.21R trade with a 0.73-pip filled stop. Removing this distortion lowers the R total substantially, while account growth changes very little.

| Feed | Version | Planned-budget R | Account growth | Equity DD | Minimum filled stop |
|---|---|---:|---:|---:|---:|
| Dukascopy | original | +7.82 | +2.89% | 14.05% | 0.73 pips |
| Dukascopy | corrected | +7.89 | +2.93% | 14.40% | 8.07 pips |
| HistData | original | -7.49 | -4.67% | 19.26% | 7.15 pips |
| HistData | corrected | -6.49 | -4.20% | 19.34% | 8.02 pips |
| IC Markets | original | -15.31 | -8.38% | 16.78% | 2.55 pips |
| IC Markets | corrected | -12.85 | -7.25% | 16.61% | 8.02 pips |

Planned-budget R divides net profit by 0.5% of the account balance for that trade. It is reconstructed here from the sequential single-position balance and reconciles exactly to ending balance. It measures deployment impact more directly than a tiny actual-stop denominator.

## Later periods with corrected execution

| Feed | Period | Trades | Win % | Net R | PF | R/trade | Closed DD R | Win/loss streak |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Dukascopy | 2020 2025 | 412 | 43.69 | +1.73 | 1.007 | +0.0042 | 29.37 | 7/13 |
| Dukascopy | 2026 to july14 | 20 | 45.00 | +0.10 | 1.009 | +0.0052 | 4.92 | 3/4 |
| HistData | 2020 2025 | 406 | 42.86 | -8.10 | 0.968 | -0.0200 | 40.33 | 7/13 |
| HistData | 2026 to july14 | 20 | 45.00 | +0.10 | 1.009 | +0.0052 | 4.92 | 3/4 |
| IC Markets | 2020 2025 | 419 | 42.00 | -17.26 | 0.935 | -0.0412 | 35.24 | 7/8 |
| IC Markets | 2026 to july14 | 25 | 52.00 | +4.63 | 1.351 | +0.1852 | 6.20 | 5/4 |

These are descriptive historical subdivisions, not new untouched OOS validation. No parameters were selected on them. HistData retains documented 2023 provider gaps, and its recent matching prices are nearly identical to Dukascopy. It is not an independent feed confirmation. No forward DEMO results after the research cutoff enter these figures.

## Next research steps

Use the corrected class and these outputs as the control. Change one rule or parameter at a time, declare the training and later test windows first, and retain setup/attempt IDs when comparing trade lists. The existing fresh-cross observation lets us identify trades affected by that proposed rule without changing production behavior. Compare account growth, planned-budget R, costs, and drawdown alongside filled-risk R. Recheck broker spread sensitivity and chronological walk-forward performance before considering a material DEMO parameter change.

## Verification and host update

All 228 tests pass, including 22 focused lifecycle/execution tests. Completed nine sequential replays and three exact tracking-only controls. The audit checks accepted/closed/rejected counts, origin attribution, minimum filled stops, minimum filled R:R, input hashes, and HistData sidecars. A redundant EOF blank line was removed after replay with an identical syntax tree; `postrun_formatting.json` records both source hashes.

Results, accepted setup context, trade lists, manifest, controls, and completion marker are under `output/candle_usdjpy_corrected_20260930/`. The replay script refuses to overwrite an existing manifest; use a new output directory for a future experiment. Earlier review outputs remain historical evidence for earlier code, not the corrected control.

The changes are local and uncommitted. No MT5 connection or host deployment occurred. After committing/pushing the reviewed change, stop the existing bot process on the trading host, pull with `git pull --ff-only`, run `python -m unittest discover -s tests -v`, and restart with `python main_live.py`. Preserve existing ledger and journal files. Expect a cold warmup because the code fingerprint changed, followed by broker reconciliation. Positions created before setup IDs existed remain legacy exposure until confirmed closure.
