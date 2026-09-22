# IMS Reversal setup tracking and cancellation comparison

Research date: 2026-09-19. Final verification: 2026-09-21. Status: local implementation, not deployed to DEMO.

The tracking correction improves the six-year broker replay modestly. Keeping target-touch cancellation within the existing entry hours performs better than checking it at all hours. Original and moving targets produce identical trade paths in the tested periods, so the data does not choose between them.

## What changed

- Each H4 setup has a stable identity based on strategy, symbol, timeframe, bias direction, and originating swing timestamp. Extending its range does not create a new setup.
- Signals and accepted orders carry a setup ID and attempt ID. A final losing trade charges its originating setup, even when a newer setup is active. Duplicate close reports and partial exits do not consume extra losses. Rejected proposals and cancelled unfilled orders consume no loss allowance.
- A setup that reaches its loss allowance remains retired when H4 scans again. The scanner can still find another qualifying origin. This changes which trades are eligible even though the numeric entry parameters are unchanged.
- Actual broker order state distinguishes unfilled orders from open positions. Cancellation requests target the originating setup, and cancelling a partially filled remainder preserves the filled position and portfolio slot.
- `logs/setup_ledger.json` keeps account-bound order attribution and final outcomes separately from the strategy checkpoint. A code upgrade can invalidate the checkpoint without erasing the loss history. Pending submission intents survive a lost acknowledgement and are recovered through exact broker comments and entry-deal IDs.
- Journal metadata stays in the existing context column. Existing CSV headers remain compatible.

The four test cases vary two constructor settings. `pending_cancel_hours='entry'` checks target touches during allowed entry hours; `'all'` checks every completed M15 bar. `pending_target_reference='moving'` uses the current H4-derived target; `'submitted'` uses the order's original target. Structural expiry rules still apply outside entry hours in every case. These settings never move an accepted order's TP.

Local defaults retain `entry` and `moving`. Numeric parameters, demo membership, EURUSD-only scope, and 0.5% risk remain unchanged. No server deployment, commit, or push was performed.

## Continuous 2020 to 2025

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | W/L streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| Original code | 114 | 26.3 | +32.54 | 1.36 | +0.285 | 28.98 | 3/23 |
| Corrected, entry hours, moving target | 113 | 27.4 | +37.52 | 1.43 | +0.332 | 25.78 | 3/20 |
| Corrected, entry hours, original target | 113 | 27.4 | +37.52 | 1.43 | +0.332 | 25.78 | 3/20 |
| Corrected, all hours, moving target | 109 | 26.6 | +27.28 | 1.32 | +0.250 | 25.78 | 3/20 |
| Corrected, all hours, original target | 109 | 26.6 | +27.28 | 1.32 | +0.250 | 25.78 | 3/20 |

The correction with entry-hours cancellation adds 4.97R, reduces closed-trade drawdown by 3.20R, and reduces the longest losing streak from 23 to 20. At modeled 0.5% risk, $10,000 ends at $11,980.03 rather than $11,683.98. Maximum marked-to-market equity drawdown falls from 15.06% to 13.94%.

All-hours cancellation gives up 10.24R against corrected entry-hours cancellation and does not reduce its 25.78R closed-trade drawdown. This comparison does not support switching to all-hours cancellation.

The complete correction differs from the September 18 research-only subclass. That experiment attributed losses to whichever bias was active, and discarded the first retired scanner candidate without considering another origin. Its +35.65R and +25.41R results are historical diagnostics, not the results of this implementation.

## Separate two-year replays

Each window starts with fresh state and $10,000. These are consistency checks on previously viewed historical data. They are not new untouched out-of-sample tests.

### 2020 to 2021

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | W/L streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| Original code | 33 | 30.3 | +19.54 | 1.79 | +0.592 | 6.62 | 2/6 |
| Corrected, entry hours, moving target | 32 | 31.2 | +20.58 | 1.87 | +0.643 | 6.62 | 2/6 |
| Corrected, entry hours, original target | 32 | 31.2 | +20.58 | 1.87 | +0.643 | 6.62 | 2/6 |
| Corrected, all hours, moving target | 30 | 26.7 | +8.20 | 1.35 | +0.273 | 6.62 | 2/6 |
| Corrected, all hours, original target | 30 | 26.7 | +8.20 | 1.35 | +0.273 | 6.62 | 2/6 |

### 2022 to 2023

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | W/L streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| Original code | 47 | 14.9 | -3.15 | 0.93 | -0.067 | 28.98 | 1/23 |
| Corrected, entry hours, moving target | 46 | 17.4 | +1.88 | 1.05 | +0.041 | 25.78 | 1/20 |
| Corrected, entry hours, original target | 46 | 17.4 | +1.88 | 1.05 | +0.041 | 25.78 | 1/20 |
| Corrected, all hours, moving target | 44 | 18.2 | +4.03 | 1.10 | +0.092 | 25.78 | 1/20 |
| Corrected, all hours, original target | 44 | 18.2 | +4.03 | 1.10 | +0.092 | 25.78 | 1/20 |

### 2024 to 2025

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | W/L streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| Original code | 34 | 38.2 | +16.15 | 1.71 | +0.475 | 6.40 | 3/6 |
| Corrected, entry hours, moving target | 35 | 37.1 | +15.05 | 1.63 | +0.430 | 6.40 | 3/6 |
| Corrected, entry hours, original target | 35 | 37.1 | +15.05 | 1.63 | +0.430 | 6.40 | 3/6 |
| Corrected, all hours, moving target | 35 | 37.1 | +15.05 | 1.63 | +0.430 | 6.40 | 3/6 |
| Corrected, all hours, original target | 35 | 37.1 | +15.05 | 1.63 | +0.430 | 6.40 | 3/6 |

## January to 14 July 2026

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | W/L streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| Original code | 8 | 0.0 | -8.67 | 0.00 | -1.084 | 8.67 | 0/8 |
| Corrected, entry hours, moving target | 8 | 0.0 | -8.67 | 0.00 | -1.084 | 8.67 | 0/8 |
| Corrected, entry hours, original target | 8 | 0.0 | -8.67 | 0.00 | -1.084 | 8.67 | 0/8 |
| Corrected, all hours, moving target | 8 | 0.0 | -8.67 | 0.00 | -1.084 | 8.67 | 0/8 |
| Corrected, all hours, original target | 8 | 0.0 | -8.67 | 0.00 | -1.084 | 8.67 | 0/8 |

All five cases lose all eight trades. The tracking correction does not solve the recent weak performance or establish a reliable improvement in future returns.

## Spread sensitivity

The following runs use a constant 1.0-pip spread rather than the base 0.1-pip assumption, with commission unchanged.

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | W/L streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| Original code | 113 | 25.7 | +29.58 | 1.33 | +0.262 | 28.97 | 3/23 |
| Corrected, entry hours, moving target | 112 | 26.8 | +34.55 | 1.39 | +0.309 | 25.77 | 3/20 |
| Corrected, entry hours, original target | 112 | 26.8 | +34.55 | 1.39 | +0.309 | 25.77 | 3/20 |
| Corrected, all hours, moving target | 108 | 25.9 | +24.32 | 1.28 | +0.225 | 25.77 | 3/20 |
| Corrected, all hours, original target | 108 | 25.9 | +24.32 | 1.28 | +0.225 | 25.77 | 3/20 |

## Method and limits

Thirty sequential replays use only the fresh EURUSD M5, M15, and H4 exports ending 2026-09-18 under `data/historical/mt5_icmarkets_utc`. Completed candles after 2026-07-14 are excluded, including H4 candles crossing the cutoff. H4 and M15 drive the strategy; M5 supplies fills. Each test gets up to 180 days of prior warm-up without trading.

The old strategy is loaded from local Git commit `4cdc9eb7bc0bcd758d04af9e83f035faaa9bce09`. Its continuous baseline matches the earlier broker study exactly at 114 trades and +32.544732R. The September 18 research scripts now explicitly use this frozen source, preserving their meaning after the production class changes.

All cases keep the frozen numeric parameters. Base costs are 0.1-pip spread and $7 per lot round-trip commission. This is standalone EURUSD simulation, without swaps, portfolio interactions with other strategies, or the demo daily-loss gate. Intrabar fill assumptions and missing historical data remain limitations. All runs finish with zero open exposure.

Net R includes modeled trading costs. Drawdown in the tables uses the sequence of closed-trade net R. Equity drawdown also includes marked-to-market exposure and is reported separately. The widest-spread case is a sensitivity test, not reconstructed historical spreads.

The comparisons are retrospective. They do not provide new walk-forward approval or justify changing the protected forward-demo trial. Retain conservative risk. Any future policy or numeric-parameter promotion needs separate validation and a demo deployment decision.

## Verification and rollout notes

The full local unittest suite passed 114 tests, including 25 new setup tests. These cover loss attribution, repeated close reports, partial exits and fills, cancellation scope, rejected proposals, checkpoint recovery, offline cancellations, atomic ledger failure, account isolation, acknowledgement recovery, and legacy order-to-position transitions. MT5 tests use a fake broker. No terminal connection was attempted here.

After the last cancellation-recovery and partial-fill fixes, all four corrected policies were replayed over 2020 to 2025 again. Their complete trade records matched the original comparison runs exactly. These four verification replays are additional to the 30 comparison runs. Final source hashes and results are in `verification_manifest.json` and `verification_results.json`.

Older orders lack setup IDs. Their broker entry deals can establish order-to-position links, but their setup identity is deliberately left unknown. A legacy close cannot retire the current setup by inference. Before eventual rollout, review any existing IMS Reversal pending order on the server because automatic cancellation by setup requires an attributable origin. Keep `setup_ledger.json` with the trading server's logs and account; do not copy a ledger from a different account or delete it during code updates.

An unresolved submission intent blocks another setup submission for the same symbol and strategy until broker reconciliation resolves it. This avoids duplicating an order after an uncertain acknowledgement.

Reproduce the current study with `python research_ims_setup_policies.py`. Run tests with `python -m unittest discover -s tests -v`. Raw results, complete trades, source/data hashes, and the chart are under `output/ims_setup_tracking_20260919`. That output directory is ignored by Git; this report and the research runner are trackable.

Moving and original target policies produced identical complete trade records within each cancellation-hours choice across all six comparison windows and cost assumptions. Synthetic tests confirm that the policies differ when price touches a moved target but has not reached the original one; that distinction did not change the historical trade paths here.
