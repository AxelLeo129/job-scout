"""Scraper de Acción Trabajo (desactivado por defecto: el sitio está detrás del
anti-bots de Cloudflare y responde 403 a clientes que no son navegadores).

URL de búsqueda: ``https://<país>.acciontrabajo.com/buscar-empleos?q=<palabra>``.
Los resultados cargan con scroll infinito, así que solo se lee la primera
página (~20 ofertas) y ``max_pages`` se ignora. El ``<a>`` de cada tarjeta
apunta a un listado por ciudad; la ruta real de la oferta viene en base64 en
el atributo ``data-url``.
"""

from __future__ import annotations

import base64
import binascii
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup, Tag

from ..models import JobOffer
from .base import BaseScraper


class AccionTrabajoScraper(BaseScraper):
    """Scraper de <país>.acciontrabajo.com."""

    source_name = "acciontrabajo"
    base_url_template = "https://{country}.acciontrabajo.com"

    def search(self, keyword: str, max_pages: int) -> list[JobOffer]:
        url = f"{self.base_url}/buscar-empleos?q={quote_plus(keyword.strip())}&l="
        try:
            html = self.fetch(url)
        except Exception as exc:  # noqa: BLE001 - una búsqueda caída no detiene la ejecución
            self.log(f"Error al leer {url}: {exc}")
            return []

        if self.debug:
            self.dump_html(html, keyword)

        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("div.listing_url.list_item")
        return [offer for card in cards if (offer := self._parse_card(card))]

    def _parse_card(self, card: Tag) -> JobOffer | None:
        """Construye un JobOffer a partir de una tarjeta; None si no tiene título o URL."""
        title_el = card.select_one("h2.ttl") or card.select_one("h2")
        url = self._decode_offer_url(card)
        if title_el is None or url is None:
            return None

        company_el = card.select_one("b")
        desc_el = card.select_one("span.le2")

        return JobOffer(
            title=title_el.get_text(strip=True),
            company=company_el.get_text(strip=True) if company_el else "—",
            location=self._extract_location(card),
            url=url,
            source=self.source_name,
            description=desc_el.get_text(" ", strip=True) if desc_el else "",
        )

    @staticmethod
    def _extract_location(card: Tag) -> str:
        """Enlaces de ciudad y departamento sin repetir ("Guatemala, Guatemala" -> "Guatemala")."""
        loc_el = card.select_one("div[id$='-city']")
        if loc_el is None:
            return "—"
        parts = list(dict.fromkeys(a.get_text(strip=True) for a in loc_el.select("a")))
        parts = [p for p in parts if p]
        if parts:
            return ", ".join(parts)
        return loc_el.get_text(" ", strip=True).strip(" ,") or "—"

    def _decode_offer_url(self, card: Tag) -> str | None:
        """URL de la oferta desde ``data-url`` (base64) o, si falla, desde el enlace visible."""
        data_url = card.get("data-url", "")
        if data_url:
            try:
                padded = data_url + "=" * (-len(data_url) % 4)  # el sitio quita el relleno "="
                return urljoin(self.base_url, base64.b64decode(padded).decode("utf-8"))
            except (binascii.Error, UnicodeDecodeError):
                pass

        link = card.select_one("a[href]")
        return urljoin(self.base_url, link["href"]) if link else None
