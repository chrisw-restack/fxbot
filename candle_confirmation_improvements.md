recommendations, in priority order:

  1. Stop testing all major pairs together
     The strategy likely behaves differently by pair. First split results by symbol. If one or two pairs are close to break-even and the rest are dragging, optimize only those. The current
     aggregate may be hiding pair-specific edge.
  2. Add a trend/bias filter
     Only take bullish setups when price is above a higher-timeframe EMA, and bearish setups below it. I’d test:
      - H4 EMA 20/50
      - D1 EMA 20/50
      - minimum EMA separation, e.g. 0.05%, 0.10%, 0.15%
  3. Avoid low-quality HTF engulf candles
     Right now the engulf is very loose. Add quality filters:
      - minimum H1 candle range in pips
      - close must be in top/bottom 25% of the candle
      - candle body must be at least 50-70% of its range
      - optionally require candle color in the engulf direction
  4. Change the entry trigger
     M5 swing break after retrace is producing too many noisy entries. Test:
      - require M5 candle close beyond swing by at least 1-2 pips
      - require displacement candle body size
      - require the FVG to form after the 50% retrace, not anywhere in the leg
      - require entry candle close to be outside the FVG/displacement leg, not just above the swing
  5. Use a better TP model
     The engulfing extreme is too nearby/noisy for many trades. Test:
      - partial TP at extreme, runner to 1.5R or 2R
      - fixed 1.5R/2R instead of engulf extreme
      - skip trades where target is less than e.g. 8-12 pips
  6. Add a minimum stop/target distance
     The logs showed many tiny trades. Even with the 5-pip minimum, spread hurts. I’d test:
      - min SL: 8, 10, 12, 15 pips
      - min TP: 8, 10, 12, 15 pips
      - maybe block trades where spread-to-target is too large
  7. Test fewer, cleaner sessions
     Session filtering helped slightly but did not fix it. I’d test narrower windows:
      - London open: 07:00-10:00 UTC
      - NY open: 13:00-16:00 UTC
      - London/NY overlap only: 13:00-16:00 UTC
      - block Friday late and Monday open

  Most pragmatic next step: run a diagnostic by symbol and hour first. If no pair/hour bucket is close to profitable, don’t add complexity. If there is a promising bucket, then test HTF
  candle-quality filters and trend filters one at a time.
