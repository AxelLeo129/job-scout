"""Notificaciones por Telegram mediante el endpoint ``sendMessage`` de la Bot API."""

from __future__ import annotations

import html
import time

import requests

from .models import JobOffer

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
REQUEST_TIMEOUT_SECONDS = 20

# Telegram admite ~1 mensaje por segundo en un mismo chat antes de responder 429.
SEND_INTERVAL_SECONDS = 1.1
DEFAULT_RETRY_AFTER_SECONDS = 5


class TelegramNotifier:
    """Envía mensajes con formato HTML a un chat de Telegram."""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._last_sent = 0.0

    def send(self, text: str) -> None:
        """Envía ``text`` (HTML de Telegram); reintenta una vez tras un 429.

        Raises:
            RuntimeError: con la descripción del error de Telegram (p.ej. "chat not found").
        """
        url = TELEGRAM_API.format(token=self.bot_token)
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }
        response = self._post(url, payload)
        if response.status_code == 429:
            time.sleep(self._retry_after(response))
            response = self._post(url, payload)
        if not response.ok:
            try:
                description = response.json().get("description", response.text)
            except ValueError:
                description = response.text
            raise RuntimeError(f"Telegram {response.status_code}: {description}")

    def send_offer(self, offer: JobOffer) -> None:
        """Envía una oferta con el formato de :meth:`format_offer`."""
        self.send(self.format_offer(offer))

    @staticmethod
    def format_offer(offer: JobOffer) -> str:
        """Mensaje HTML de Telegram para ``offer``; el texto del portal se escapa."""
        lines = [
            f"🎯 <b>{offer.score}/100</b> — {html.escape(offer.title)}",
            f"🏢 {html.escape(offer.company)}",
            f"📍 {html.escape(offer.location)}",
        ]
        if offer.salary:
            lines.append(f"💰 {html.escape(offer.salary)}")
        lines.append(f"💡 {html.escape(offer.score_reason)}")
        lines.append(f'🔗 <a href="{html.escape(offer.url)}">Ver oferta</a>')
        lines.append(f"<i>vía {offer.source}</i>")
        return "\n".join(lines)

    def _post(self, url: str, payload: dict) -> requests.Response:
        """Hace el POST dejando al menos SEND_INTERVAL_SECONDS entre mensajes."""
        wait = SEND_INTERVAL_SECONDS - (time.monotonic() - self._last_sent)
        if wait > 0:
            time.sleep(wait)
        try:
            return requests.post(url, data=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        finally:
            self._last_sent = time.monotonic()

    @staticmethod
    def _retry_after(response: requests.Response) -> float:
        """Segundos de espera que pide una respuesta 429."""
        try:
            return response.json().get("parameters", {}).get("retry_after", DEFAULT_RETRY_AFTER_SECONDS)
        except ValueError:
            return DEFAULT_RETRY_AFTER_SECONDS
