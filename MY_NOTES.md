# Next to do
- test fib strat with all max data


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
