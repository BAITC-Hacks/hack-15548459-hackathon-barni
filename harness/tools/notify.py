"""Уведомления наружу. На демо эффектно: агент сам присылает итог в Telegram."""
import requests

from .. import config
from . import tool


@tool(dangerous=True)
def send_telegram(text: str) -> str:
    """Отправляет сообщение в Telegram (чат из настроек). Для уведомлений и отправки итога.

    Args:
        text: Текст сообщения.
    """
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        return f"[Telegram не настроен — сообщение не отправлено]\n{text}"
    resp = requests.post(f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
                         json={"chat_id": config.TELEGRAM_CHAT_ID, "text": text[:4000]}, timeout=15)
    resp.raise_for_status()
    return "Отправлено в Telegram"
