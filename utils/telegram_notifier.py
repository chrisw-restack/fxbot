import json
import logging
import os
import ssl
import urllib.request
import urllib.error

try:
    import certifi
    _ssl_context = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _ssl_context = ssl.create_default_context()

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Send trading notifications via Telegram Bot API."""

    def __init__(self, bot_token: str | None = None, chat_id: str | None = None):
        self._token = bot_token or os.environ.get('TELEGRAM_BOT_TOKEN', '')
        self._chat_id = chat_id or os.environ.get('TELEGRAM_CHAT_ID', '')
        self._enabled = bool(self._token and self._chat_id)
        if not self._enabled:
            logger.warning("Telegram notifications disabled — missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

    def _send(self, text: str):
        if not self._enabled:
            return
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        payload = json.dumps({
            'chat_id': self._chat_id,
            'text': text,
            'parse_mode': 'HTML',
        }).encode('utf-8')
        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
        try:
            urllib.request.urlopen(req, timeout=10, context=_ssl_context)
        except Exception:
            logger.exception("Failed to send Telegram notification")

    def notify_started(self, symbols: list[str], strategy_names: list[str]):
        lines = [
            "\U0001f7e2 <b>Trading bot started</b>",
            f"Strategies: {', '.join(strategy_names)}",
            f"Symbols: {', '.join(symbols)}",
        ]
        self._send('\n'.join(lines))

    def notify_order_placed(self, symbol: str, direction: str, entry: float,
                            sl: float, tp: float, lots: float, strategy: str):
        emoji = "\U0001f4c8" if direction == 'BUY' else "\U0001f4c9"
        lines = [
            f"{emoji} <b>Order placed — {symbol} {direction}</b>",
            f"Entry: {entry:.5f}",
            f"SL: {sl:.5f}  |  TP: {tp:.5f}",
            f"Lots: {lots}  |  {strategy}",
        ]
        self._send('\n'.join(lines))

    def notify_order_closed(self, symbol: str, direction: str, result: str,
                            r_multiple: float, pnl: float, strategy: str):
        if result == 'WIN':
            emoji = "\u2705"
        elif result == 'BE':
            emoji = "\u2796"
        else:
            emoji = "\u274c"
        lines = [
            f"{emoji} <b>Trade closed — {symbol} {direction}</b>",
            f"Result: {result}  |  R: {r_multiple:+.2f}  |  PnL: ${pnl:+.2f}",
            f"Strategy: {strategy}",
        ]
        self._send('\n'.join(lines))

    def notify_heartbeat(self, balance: float, open_positions: int):
        lines = [
            "\U0001f493 <b>Daily heartbeat</b>",
            f"Balance: ${balance:,.2f}",
            f"Open positions: {open_positions}",
            "Bot is running normally.",
        ]
        self._send('\n'.join(lines))
