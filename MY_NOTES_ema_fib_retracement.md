
# how it works:
❯ please give me a summary of all the parameters in effect currently and the logic behind framing and placing of a trade using EmaFibRetracementStrategy. i currently have this running on a vps linked to a demo account. its been  a week
without a trade but this might be normal because conditions might not be optimal

● Read 2 files (ctrl+o to expand)

● Here's the full breakdown:

  Live Parameters (from main_live.py lines 80-85)

  ┌──────────────────────────┬─────────────────────┬───────────────────────────────────────────────────────────────────────────────────────────────┐
  │        Parameter         │        Value        │                                         What it does                                          │
  ├──────────────────────────┼─────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────┤
  │ ema_fast                 │ 10 (default)        │ Fast EMA period on both D1 and H1                                                             │
  ├──────────────────────────┼─────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────┤
  │ ema_slow                 │ 20 (default)        │ Slow EMA period on both D1 and H1                                                             │
  ├──────────────────────────┼─────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────┤
  │ fractal_n                │ 3 (default)         │ Swing detection requires the middle bar's high/low to beat 3 bars on each side (7-bar window) │
  ├──────────────────────────┼─────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────┤
  │ fib_entry                │ 0.618 (default)     │ Pending order placed at 61.8% retracement of the swing                                        │
  ├──────────────────────────┼─────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────┤
  │ fib_tp                   │ 2.0 (default)       │ TP at 200% fib extension of the swing range (~3.9R avg)                                       │
  ├──────────────────────────┼─────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────┤
  │ swing_max_age            │ 100 (default)       │ Ignore swings older than 100 H1 bars (~4 days)                                                │
  ├──────────────────────────┼─────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────┤
  │ cooldown_bars            │ 10                  │ After a loss, wait 10 H1 bars before new signals for that symbol                              │
  ├──────────────────────────┼─────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────┤
  │ invalidate_swing_on_loss │ True                │ After a loss, the swing that produced it can't be reused                                      │
  ├──────────────────────────┼─────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────┤
  │ min_swing_pips           │ 15                  │ Swing range must be at least 15 pips                                                          │
  ├──────────────────────────┼─────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────┤
  │ ema_sep_pct              │ 0.0005              │ H1 fast/slow EMA must be at least 0.05% apart (trend strength filter)                         │
  ├──────────────────────────┼─────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────┤
  │ blocked_hours            │ 16-23 UTC (default) │ No new signals during late NY session                                                         │
  ├──────────────────────────┼─────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────┤
  │ min_d1_atr_pips          │ 50 (default)        │ D1 ATR(14) must be at least 50 pips (filters out dead/ranging markets)                        │
  └──────────────────────────┴─────────────────────┴───────────────────────────────────────────────────────────────────────────────────────────────┘

  Plus from config.py:
  - Risk per trade: 0.5% of balance (dynamic lot sizing)
  - R:R: 2.0 (but overridden by strategy's fib TP — actual avg win is ~3.9R)
  - Min SL: 5 pips (signals with tighter SL rejected)
  - Max open trades: 4
  - Max daily loss: 2% of balance
  - Symbols: EURUSD, GBPUSD, AUDUSD, NZDUSD, USDJPY, USDCAD

  Trade Logic Flow (step by step)

  1. D1 bar arrives — updates D1 10/20 EMA and D1 ATR(14). No signal generated.

  2. H1 bar arrives — the strategy runs through this gate sequence:

  H1 bar
    │
    ├─ Update H1 10/20 EMA
    ├─ Update 7-bar fractal window, detect new swing highs/lows
    │
    ├─ If a pending order exists:
    │    ├─ Bar touched entry price? → Mark as filled, done
    │    └─ H1 bias flipped? → Emit CANCEL signal
    │
    ├─ FILTER: In cooldown after a loss? → skip (10 bars)
    ├─ FILTER: Hour is 16-23 UTC? → skip
    ├─ FILTER: D1 ATR < 50 pips? → skip
    ├─ FILTER: D1 bias (10 EMA vs 20 EMA) not ready? → skip
    ├─ FILTER: H1 bias not ready? → skip
    ├─ FILTER: D1 bias ≠ H1 bias? → skip
    ├─ FILTER: H1 EMA separation < 0.05%? → skip (trend too weak)
    ├─ FILTER: No valid swing high or swing low? → skip
    ├─ FILTER: Swing too old (>100 bars)? → skip
    ├─ FILTER: Same swing already lost on (invalidate_swing_on_loss)? → skip
    ├─ FILTER: Swing range < 15 pips? → skip
    │
    └─ ALL CLEAR → Place PENDING order:
         BUY:  entry = swing_high - 0.618 × range, SL = swing_low, TP = swing_low + 2.0 × range
         SELL: entry = swing_low + 0.618 × range, SL = swing_high, TP = swing_high - 2.0 × range

  3. Risk manager validates SL >= 5 pips, calculates lot size from 0.5% risk.

  4. Portfolio manager checks: no existing position on that symbol, <4 open trades, daily loss <2%.

  5. Execution places the pending order on MT5. It sits until price retraces to the 61.8% level, or gets cancelled if bias flips.

  Why a Week With No Trades is Normal

  There are a lot of gates to pass through. Any one of these alone can block trades for days:

  - D1 and H1 bias must agree — if the D1 trend is up but H1 is choppy or turning, no signals. After a trend change it takes ~20 H1 bars (almost a day) just for the H1 EMA to seed a new bias.
  - Blocked hours 16-23 UTC — that's 8 hours per day with zero signals. Only hours 0-15 UTC are active.
  - D1 ATR >= 50 pips — in quiet/ranging markets (common for some pairs), this alone blocks everything.
  - EMA separation 0.05% — even when EMAs agree on direction, if the trend is weak/flat, signals are blocked.
  - Min swing 15 pips — in tight ranges, swings are too small to qualify.
  - Pending order must fill — even when a signal passes all filters, price has to actually retrace to the 61.8% level. In a strong trend, price may never pull back enough.
  - Invalidate swing on loss — if a trade on a particular swing lost, that swing can't produce another trade. Need a new fractal swing to form.
  - One position per symbol — if EURUSD already has an open position, no new EURUSD signals until it closes.

  In backtesting over 10 years across 6 symbols, the strategy averaged ~1,589 trades / ~3,650 days = roughly one trade every 2.3 days. But that's the average — trades cluster around trending periods. Quiet stretches of a week or more with
   zero trades are completely normal, especially if multiple pairs are ranging simultaneously.

  You can check the VPS logs (logs/trading.log) to confirm bars are arriving and the bot is running — as long as you see D1/H1 bar processing, it's just waiting for conditions to align.



# TWEAKS we've done:
## ema_fib_retracement - works for swing, tried intraday but its quite poor
- run against 5 years of data on eu
- 2024 worst year, filters below helped a little
- added filters:
  ┌──────────────────────────┬─────────┬────────────────────────────────────────────────────────┐
  │        Parameter         │ Default │                         Effect                         │
  ├──────────────────────────┼─────────┼────────────────────────────────────────────────────────┤
  │ cooldown_bars            │ 10      │ Skip 10 H1 bars after a stop-out                       │
  ├──────────────────────────┼─────────┼────────────────────────────────────────────────────────┤
  │ invalidate_swing_on_loss │ True    │ Don't re-enter on the same swing levels that just lost │
  ├──────────────────────────┼─────────┼────────────────────────────────────────────────────────┤
  │ min_swing_pips           │ 15.0    │ Reject micro-swings below 15 pips                      │
  ├──────────────────────────┼─────────┼────────────────────────────────────────────────────────┤
  │ ema_sep_pct              │ 0.0005  │ Require 0.05% separation between fast/slow H1 EMA      │
  └──────────────────────────┴─────────┴────────────────────────────────────────────────────────┘
- fitlered out NY Session
  ┌───────────────────┬───────────────┬─────────────────────┐
  │      Metric       │    Before     │ With session filter │
  ├───────────────────┼───────────────┼─────────────────────┤
  │ Trades            │ 139           │ 132                 │
  ├───────────────────┼───────────────┼─────────────────────┤
  │ Win rate          │ 30.9%         │ 31.1%               │
  ├───────────────────┼───────────────┼─────────────────────┤
  │ Total R           │ +70.74R       │ +69.25R             │
  ├───────────────────┼───────────────┼─────────────────────┤
  │ Profit factor     │ 1.74          │ 1.76                │
  ├───────────────────┼───────────────┼─────────────────────┤
  │ Expectancy        │ +0.51R        │ +0.52R              │
  ├───────────────────┼───────────────┼─────────────────────┤
  │ Max drawdown      │ 19.39R (9.8%) │ 10.08R (5.2%)       │
  ├───────────────────┼───────────────┼─────────────────────┤
  │ Worst loss streak │ 13            │ 7                   │
  └───────────────────┴───────────────┴─────────────────────┘
- filtered out sub 50 atr
  ┌─────────┬────────┬─────────┬────────────┬──────┬────────┬────────┐
  │ ATR Min │ Trades │ Total R │ Expectancy │  PF  │ Max DD │ Streak │
  ├─────────┼────────┼─────────┼────────────┼──────┼────────┼────────┤
  │ 0       │ 132    │ +69.25R │ +0.52      │ 1.76 │ 10.08R │ 7      │
  ├─────────┼────────┼─────────┼────────────┼──────┼────────┼────────┤
  │ 50      │ 127    │ +69.30R │ +0.55      │ 1.80 │ 10.08R │ 7      │
  ├─────────┼────────┼─────────┼────────────┼──────┼────────┼────────┤
  │ 55      │ 122    │ +64.58R │ +0.53      │ 1.77 │ 10.08R │ 7      │
  ├─────────┼────────┼─────────┼────────────┼──────┼────────┼────────┤
  │ 65      │ 112    │ +55.23R │ +0.49      │ 1.71 │ 12.98R │ 12     │
  ├─────────┼────────┼─────────┼────────────┼──────┼────────┼────────┤
  │ 70      │ 102    │ +50.86R │ +0.50      │ 1.72 │ 10.08R │ 8      │
  ├─────────┼────────┼─────────┼────────────┼──────┼────────┼────────┤
  │ 80      │ 71     │ +42.58R │ +0.60      │ 1.89 │ 10.08R │ 7      │
  └─────────┴────────┴─────────┴────────────┴──────┴────────┴────────┘

- tested be 1r and 2r - very not worth it
  ┌───────────────┬─────────┬──────────┬──────────┐
  │    Metric     │  No BE  │ BE at 1R │ BE at 2R │
  ├───────────────┼─────────┼──────────┼──────────┤
  │ Trades        │ 127     │ 141      │ 137      │
  ├───────────────┼─────────┼──────────┼──────────┤
  │ Wins          │ 40      │ 21       │ 26       │
  ├───────────────┼─────────┼──────────┼──────────┤
  │ Break-evens   │ —       │ 65       │ 34       │
  ├───────────────┼─────────┼──────────┼──────────┤
  │ Losses        │ 87      │ 55       │ 77       │
  ├───────────────┼─────────┼──────────┼──────────┤
  │ Total R       │ +69.30R │ +26.61R  │ +24.10R  │
  ├───────────────┼─────────┼──────────┼──────────┤
  │ Profit factor │ 1.80    │ 1.48     │ 1.31     │
  ├───────────────┼─────────┼──────────┼──────────┤
  │ Expectancy    │ +0.55R  │ +0.19R   │ +0.18R   │
  ├───────────────┼─────────┼──────────┼──────────┤
  │ Max drawdown  │ 10.08R  │ 11.00R   │ 12.04R   │
  └───────────────┴─────────┴──────────┴──────────┘
- tested 2r and 5r tp, current convincingly the best
  ┌───────────────────┬───────────────┬─────────────────┬──────────────┐
  │      Metric       │     2R TP     │ ~4.2R (current) │    5R TP     │
  ├───────────────────┼───────────────┼─────────────────┼──────────────┤
  │ Trades            │ 141           │ 127             │ 125          │
  ├───────────────────┼───────────────┼─────────────────┼──────────────┤
  │ Win rate          │ 45.4%         │ 31.5%           │ 27.2%        │
  ├───────────────────┼───────────────┼─────────────────┼──────────────┤
  │ Total R           │ +39.65R       │ +69.30R         │ +66.47R      │
  ├───────────────────┼───────────────┼─────────────────┼──────────────┤
  │ Profit factor     │ 1.51          │ 1.80            │ 1.73         │
  ├───────────────────┼───────────────┼─────────────────┼──────────────┤
  │ Expectancy        │ +0.28R        │ +0.55R          │ +0.53R       │
  ├───────────────────┼───────────────┼─────────────────┼──────────────┤
  │ Max drawdown      │ 11.48R (5.8%) │ 10.08R (5.2%)   │ 9.36R (4.8%) │
  ├───────────────────┼───────────────┼─────────────────┼──────────────┤
  │ Best win streak   │ 7             │ 3               │ 3            │
  ├───────────────────┼───────────────┼─────────────────┼──────────────┤
  │ Worst loss streak │ 7             │ 7               │ 9            │
  ├───────────────────┼───────────────┼─────────────────┼──────────────┤
  │ Avg win           │ 1.82R         │ 3.91R           │ 4.63R        │
  └───────────────────┴───────────────┴─────────────────┴──────────────┘
- very solid even with 2pip spread
  ┌───────────────────┬───────────────┬───────────────┬────────────────┐
  │      Metric       │     1 pip     │    2 pips     │     Change     │
  ├───────────────────┼───────────────┼───────────────┼────────────────┤
  │ Total R           │ +737.0R       │ +620.4R       │ -116.6R        │
  ├───────────────────┼───────────────┼───────────────┼────────────────┤
  │ Profit factor     │ 1.96          │ 1.81          │ -0.15          │
  ├───────────────────┼───────────────┼───────────────┼────────────────┤
  │ Expectancy        │ +0.64R        │ +0.54R        │ -0.10R         │
  ├───────────────────┼───────────────┼───────────────┼────────────────┤
  │ Avg win R         │ 3.88R         │ 3.58R         │ -0.30R         │
  ├───────────────────┼───────────────┼───────────────┼────────────────┤
  │ Max drawdown      │ 21.1R (10.5%) │ 22.5R (11.6%) │ slightly worse │
  ├───────────────────┼───────────────┼───────────────┼────────────────┤
  │ Win rate          │ 33.5%         │ 33.5%         │ unchanged      │
  ├───────────────────┼───────────────┼───────────────┼────────────────┤
  │ Worst loss streak │ 14            │ 14            │ unchanged      │
  └───────────────────┴───────────────┴───────────────┴────────────────┘
- walked through all params to make sure we have the optimal settings, we are in the sweet spot:

```
Your current config is already near-optimal. It appears in the top results across all three rankings (Total R, Expectancy, and Profit Factor).

  Key findings:
  1. swing_max_age doesn't matter — 50, 100, and 150 produce identical results. Swings are being used well before they expire.
  2. fractal_n=3 is the winner — every single top result uses fractal_n=3. Values of 2 and 5 didn't make the top 30.
  3. ema_sep_pct=0.0005 is consistently best — the EMA separation filter is doing its job.
  4. cooldown_bars has minimal impact — 0, 10, and 20 all perform similarly. Your choice of 10 is fine.
  5. invalidate_swing_on_loss — marginal difference either way. Your current True gives slightly better drawdown (22.5R vs 23.5-25.0R).
  6. min_swing_pips=10 edges out 15 on raw Total R (+634 vs +620) but with slightly more trades and similar metrics. Your 15 is more conservative and arguably better for live.
  7. min_d1_atr_pips=50 boosts PF (1.81 vs 1.79) by filtering low-volatility periods, with slightly fewer trades. Worth keeping.

  Bottom line: No change needed. Your current parameters (cool=10, inval=Y, min_sw=15, ema_sep=0.0005, atr=50, frac_n=3) sit right in the sweet spot — strong expectancy (+0.54R), best
  drawdown (22.5R), and solid PF (1.81). The strategy is robust across parameter ranges, which is a good sign it's not overfit.
  ```


● Excellent results. Every symbol is profitable over 10 years:

  ┌────────┬────────┬───────┬─────────┬──────┬───────┐
  │ Symbol │ Trades │  WR   │ Total R │  PF  │  Exp  │
  ├────────┼────────┼───────┼─────────┼──────┼───────┤
  │ GBPUSD │ 339    │ 36.9% │ +238R   │ 2.11 │ +0.70 │
  ├────────┼────────┼───────┼─────────┼──────┼───────┤
  │ NZDUSD │ 275    │ 32.0% │ +122R   │ 1.65 │ +0.44 │
  ├────────┼────────┼───────┼─────────┼──────┼───────┤
  │ USDCAD │ 257    │ 32.3% │ +121R   │ 1.69 │ +0.47 │
  ├────────┼────────┼───────┼─────────┼──────┼───────┤
  │ EURUSD │ 227    │ 31.7% │ +100R   │ 1.64 │ +0.44 │
  ├────────┼────────┼───────┼─────────┼──────┼───────┤
  │ USDJPY │ 235    │ 30.6% │ +91R    │ 1.56 │ +0.39 │
  ├────────┼────────┼───────┼─────────┼──────┼───────┤
  │ AUDUSD │ 256    │ 29.7% │ +86R    │ 1.48 │ +0.33 │
  └────────┴────────┴───────┴─────────┴──────┴───────┘

  Every single year profitable except none — even 2019 (the weakest at +1.3R) was positive. GBPUSD is the standout performer by far. AUDUSD is the weakest but still solidly positive.

  No symbol needs to be dropped. The strategy is robust across all 6 pairs over 10 years with Dukascopy data — consistent with the previous MT5 backtest results.
