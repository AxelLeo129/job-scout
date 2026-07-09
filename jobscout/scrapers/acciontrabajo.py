"""Scraper de Acción Trabajo.

La búsqueda es un GET simple a /buscar-empleos?q=<palabra>. El sitio pagina
con scroll infinito (AJAX), así que solo leemos la primera página (~20
ofertas por búsqueda); el parámetro max_pages se ignora.

Peculiaridad: el <a> de cada tarjeta apunta a un listado por ciudad con un
ancla (#id), no a la oferta. La URL real de la oferta viene codificada en
base64 en el atributo data-url de la tarjeta.
"""

from __future__ import annotations

import base64
import binascii
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import JobOffer
from .base import BaseScraper


class AccionTrabajoScraper(BaseScraper):
    """Lee ofertas de <país>.acciontrabajo.com."""

    source_name = "acciontrabajo"

    def __init__(self, country: str = "gt", request_delay: float = 1.5, debug: bool = False):
        super().__init__(request_delay=request_delay)
        self.country = country
        self.base_url = f"https://{country}.acciontrabajo.com"
        self.debug = debug

    def search(self, keyword: str, max_pages: int) -> list[JobOffer]:
        url = f"{self.base_url}/buscar-empleos?q={keyword.strip()}&l="
        try:
            html = self.fetch(url)
        except Exception as exc:  # noqa: BLE001 - registramos y seguimos
            print(f"  [acciontrabajo] Error al leer {url}: {exc}")
            return []

        if self.debug:
            self._dump_html(html, keyword)

        return self._parse_results(html)

    def _parse_results(self, html: str) -> list[JobOffer]:
        soup = BeautifulSoup(html, "html.parser")
        offers: list[JobOffer] = []

        # Cada oferta es un <div class="listing_url list_item ...">.
        for card in soup.select("div.listing_url.list_item"):
            offer = self._parse_card(card)
            if offer is not None:
                offers.append(offer)

        return offers

    def _parse_card(self, card) -> JobOffer | None:
        title_el = card.select_one("h2.ttl") or card.select_one("h2")
        if title_el is None:
            return None
        title = title_el.get_text(strip=True)

        url = self._decode_offer_url(card)
        if url is None:
            return None

        company_el = card.select_one("b")
        company = company_el.get_text(strip=True) if company_el else "—"

        # Ciudad: <div id="<id>-city"> con enlaces a ciudad y departamento
        # (a veces repetidos, p.ej. "Guatemala, Guatemala").
        location = "—"
        loc_el = card.select_one("div[id$='-city']")
        if loc_el:
            parts = [a.get_text(strip=True) for a in loc_el.select("a")]
            unique = list(dict.fromkeys(p for p in parts if p))
            if unique:
                location = ", ".join(unique)
            else:
                location = loc_el.get_text(" ", strip=True).strip(" ,")

        desc_el = card.select_one("span.le2")
        description = desc_el.get_text(" ", strip=True) if desc_el else ""

        return JobOffer(
            title=title,
            company=company,
            location=location,
            url=url,
            source=self.source_name,
            description=description,
        )

    def _decode_offer_url(self, card) -> str | None:
        """Obtiene la URL de la oferta desde data-url (base64) o el <a>."""
        data_url = card.get("data-url", "")
        if data_url:
            try:
                # El sitio omite el relleno "=" del base64; lo reponemos.
                padded = data_url + "=" * (-len(data_url) % 4)
                path = base64.b64decode(padded).decode("utf-8")
                return urljoin(self.base_url, path)
            except (binascii.Error, UnicodeDecodeError):
                pass  # caemos al enlace visible

        link = card.select_one("a[href]")
        if link is not None:
            return urljoin(self.base_url, link["href"])
        return None

    def _dump_html(self, html: str, keyword: str) -> None:
        safe_kw = keyword.replace(" ", "_")
        filename = f"debug_acciontrabajo_{safe_kw}.html"
        with open(filename, "w", encoding="utf-8") as fh:
            fh.write(html)
        print(f"  [debug] HTML guardado en {filename}")
