# EmaFib broker-history extension, 25 September 2026

NZDUSD and USDCHF M5 exports are now available from January 2016. USDCAD M5, H1, and D1 all begin on 1 January 2025 at 22:00 UTC. A successful export means rows were saved; it does not establish coverage of the requested date range. The earlier assumption that existing USDCAD H1/D1 files supplied the full period was incorrect.

## Method

The extended broker result changes the assessment: the six matched pairs lose
20.82R over 2020 through 2025, while Dukascopy and HistData remain profitable on
those same pairs. Broker USDCHF has 23 losing trades and no wins, totaling
-24.76R; NZDUSD adds -7.11R. The seven-pair recent result is only +1.78R across
23 trades. The current settings do not show a dependable historical edge on
the broker data. Differences in candles and coverage require investigation
before treating source agreement as validation. Numeric settings and DEMO
deployment remain unchanged.

The corrected implementation, numeric settings, spread, and commission are unchanged. Ten additional replays run sequentially. Previous compatible results are reused only after checking code, parameter, and input hashes. New orders and ending exposure pass the same strategy/execution consistency checks. Each replay uses 180 days of warm-up, with no trades after 14 July 2026. This is descriptive historical validation, not a new optimization or untouched holdout.

The tables sum independent pair net-R histories in close-time order. They are not pooled account returns or equity drawdowns. They include modeled spread and commission but omit swap, variable spreads, extra slippage, and shared DEMO portfolio/daily-loss gates. Broker D1 session boundaries differ from UTC-day data. HistData and Dukascopy remain highly similar price series, not independent feed confirmation.

## Six matched pairs, 2020 through 2025

Pairs: EURUSD, GBPUSD, AUDUSD, NZDUSD, USDJPY, USDCHF. USDCAD is excluded from every source in this table because its broker history does not cover these years.

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy | 228 | 8.77 | +36.50 | 1.16 | 0.160 | 55.45 | 2 / 31 |
| histdata | 236 | 9.75 | +67.26 | 1.29 | 0.285 | 38.74 | 2 / 28 |
| mt5_icmarkets_utc | 229 | 6.99 | -20.82 | 0.91 | -0.091 | 84.05 | 2 / 46 |

## Seven matched pairs, 1 January through 14 July 2026

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy | 23 | 13.04 | +16.23 | 1.72 | 0.706 | 13.00 | 2 / 11 |
| histdata | 22 | 9.09 | +3.27 | 1.14 | 0.149 | 13.00 | 1 / 11 |
| mt5_icmarkets_utc | 23 | 8.70 | +1.78 | 1.07 | 0.077 | 13.37 | 1 / 11 |

The new M5 exports end at 21:00 UTC on 14 July, as shown by the exporter. The requested end date does not imply complete coverage through UTC midnight. Closed-trade metrics exclude any ending open or pending exposure.

## Added long-history broker pairs

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| NZDUSD | 59 | 6.78 | -7.11 | 0.88 | -0.120 | 26.46 | 2 / 21 |
| USDCHF | 23 | 0.00 | -24.76 | 0.00 | -1.076 | 24.76 | 0 / 23 |

## USDCAD only, 1 July through 31 December 2025

Starting in July permits a full 180-day warm-up in all three broker streams. Starting in January 2025 would not. All three sources start fresh on the same July date.

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy | 0 | n/a | +0.00 | n/a | n/a | 0.00 | 0 / 0 |
| histdata | 0 | n/a | +0.00 | n/a | n/a | 0.00 | 0 / 0 |
| mt5_icmarkets_utc | 0 | n/a | +0.00 | n/a | n/a | 0.00 | 0 / 0 |

## USDCAD only, 2026 through 14 July

| Case | Trades | Win % | Net R | PF | R/trade | Max DD R | Win/loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| dukascopy | 0 | n/a | +0.00 | n/a | n/a | 0.00 | 0 / 0 |
| histdata | 0 | n/a | +0.00 | n/a | n/a | 0.00 | 0 / 0 |
| mt5_icmarkets_utc | 0 | n/a | +0.00 | n/a | n/a | 0.00 | 0 / 0 |

## Accepted coverage limit

The repeated host export returned the same earliest timestamp, 1 January 2025 at 22:00 UTC, for all three USDCAD timeframes. It saved 114,263 M5 bars, 9,527 H1 bars, and 398 D1 bars through 14 July 2026. Treat this as the available history limit for the current broker/terminal setup. This does not prove that every IC Markets server has the same limit. No further download is requested.

The completed scope is six matched pairs over 2020 through 2025 and seven pairs over the recent period. USDCAD is excluded from every source in the long-history comparison. Its shorter tests use adequate warm-up and yielded no closed trades on any source, so they do not establish an edge. A seven-pair long-history broker result is unavailable; this limitation does not prevent using the completed comparisons. No DEMO configuration or risk change was made.

## Artifacts

Run `.venv\Scripts\python.exe research_ema_fib_broker_completion.py` to reproduce this extension. Input coverage, hashes, trades, metrics, and period-end exposure are in `output/ema_fib_broker_completion_20260925/`. The original 134-run study and its outputs remain unchanged.

## Ending exposure

All ten additional runs ended flat.
