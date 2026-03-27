# Next to do

some ideas I am considering in light of your previous response how to mature/make robust what we are doing here, what do you think:
- incorporate adding swap fees to trades where applicable when backtesting, do you need any information from me to start calculating that?
- incorporate adding commissions to backtested trades. ic markets raw spread live account uses commission charges of $3.50 per side / $7.00 round trip per 1 lot.
- clamping to 0.01 lots might be an issue. we could maybe skip placing a trade if the calculated 0.01 lots overrisks. but i think you said previously that the frequency of those overrisked trades is low and also the overrisking is not so big as to cause concern.
- i plan to test the strategies we have against xauusd or come up with new strategies for it, but i need to get data for it. this will help diversify.
- once we have xauusd or maybe nasdaq/us30/ger30 we can add max risk per asset
- i know the fx pairs im using are all usd linked so they do tend to have close correlation. i'll keep an eye on this, if the edge appears across them all it seems like its best to just take the trade. if things start to come apart we might need to implement max risk or max open trades for any usd exposure, but currently it doesnt look like an issue to me.
- i dont know how we would implement dynamic spread testing. could we just set the static spread at 3pips? this should give us a average worst case scenario because most of the time spreads will be less than that. we cant know how much spread will be during nfp for example in order to incorporate that into backtesting can we?
- the results on the testing we have done seems too good i need to manually pull out some trades and analyse them to make sure i understand how its working.


NEVER RR LESS THAN 1, 1:1 IS THE LOWEST



# notes
the strat best performance on all data showed using min sl of 5, but walkforward test shows 15 is better, so ill change it

python run_backtest.py the_strat --start-date 2026-01-01 --end-date 2026-06-30

# telegram bot setup
  Setup steps:
  1. Message @BotFather on Telegram, send /newbot, follow the prompts — you'll get a bot token
  2. Start a chat with your new bot and send it any message
  3. Get your chat ID by visiting https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates in a browser — look for "chat":{"id":123456789}
  4. Add both to your .env:
  TELEGRAM_BOT_TOKEN=your_bot_token
  TELEGRAM_CHAT_ID=your_chat_id

# timezones
all strats and backtesting converts time to utc, ic markets server uses gmt+3, vps timezone doesnt matter

# time zone conversion
  ┌─────────┬──────────────┬─────────────────────┬─────────────────────┐
  │ Session │   NY time    │ UTC (winter, NY=-5) │ UTC (summer, NY=-4) │
  ├─────────┼──────────────┼─────────────────────┼─────────────────────┤
  │ Asian   │ 8PM–midnight │ 01:00–05:00         │ 00:00–04:00         │
  ├─────────┼──────────────┼─────────────────────┼─────────────────────┤
  │ London  │ 2AM–5AM      │ 07:00–10:00         │ 06:00–09:00         │
  ├─────────┼──────────────┼─────────────────────┼─────────────────────┤
  │ NY AM   │ 8AM–11AM     │ 13:00–16:00         │ 12:00–15:00         │
  └─────────┴──────────────┴─────────────────────┴─────────────────────┘
