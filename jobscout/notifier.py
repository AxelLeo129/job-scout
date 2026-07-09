"""Envío de ofertas por Telegram.

Usa la API HTTP de Telegram directamente (sendMessage), que es más simple que
el SDK asíncrono para este caso: solo necesitamos enviar mensajes salientes.
"""

from __future__ import annotations

import html

import requests

from .models import JobOffer

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier:
    """Manda mensajes a un chat de Telegram."""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send(self, text: str) -> None:
        """Envía un mensaje con formato HTML.

        Si Telegram responde con error, levanta una excepción con la
        descripción concreta (p.ej. "chat not found"), que es mucho más útil
        que el genérico "400 Bad Request".
        """
        url = TELEGRAM_API.format(token=self.bot_token)
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }
        response = requests.post(url, data=payload, timeout=20)
        if not response.ok:
            # Telegram devuelve {"ok": false, "description": "..."} en los errores.
            try:
                description = response.json().get("description", response.text)
            except ValueError:
                description = response.text
            raise RuntimeError(f"Telegram {response.status_code}: {description}")

    def send_offer(self, offer: JobOffer) -> None:
        """Formatea y envía una oferta concreta."""
        self.send(self._format_offer(offer))

    @staticmethod
    def _format_offer(offer: JobOffer) -> str:
        """Construye el mensaje HTML de una oferta.

        Se escapan los textos del portal porque Telegram interpreta HTML y un
        '<' o '&' sin escapar rompería el mensaje.
        """
        title = html.escape(offer.title)
        company = html.escape(offer.company)
        location = html.escape(offer.location)
        reason = html.escape(offer.score_reason)
        salary = html.escape(offer.salary) if offer.salary else ""

        lines = [
            f"🎯 <b>{offer.score}/100</b> — {title}",
            f"🏢 {company}",
            f"📍 {location}",
        ]
        if salary:
            lines.append(f"💰 {salary}")
        lines.append(f"💡 {reason}")
        lines.append(f"🔗 <a href=\"{html.escape(offer.url)}\">Ver oferta</a>")
        lines.append(f"<i>vía {offer.source}</i>")
        return "\n".join(lines)
