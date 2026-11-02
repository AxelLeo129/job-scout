"""Scraper de Trabajos Diarios.

URL de búsqueda: ``https://<país>.trabajosdiarios.com/ofertas-trabajo/de-<slug>``.
El sitio redirige al puesto canónico (``de-desarrollador`` ->
``de-programador``), así que la paginación (``?page=N``) usa la URL final.
El parámetro ``?key=`` no filtra resultados; por eso se usa la ruta con slug.
"""

from __future__ import annotations

import re
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup, Tag

from ..models import JobOffer
from .base import BaseScraper, find_salary

_DATE_RE = re.compile(r"\d{2}/\d{2}/\d{4}")


class TrabajosDiariosScraper(BaseScraper):
    """Scraper de <país>.trabajosdiarios.com."""

    source_name = "trabajosdiarios"
    base_url_template = "https://{country}.trabajosdiarios.com"

    def search(self, keyword: str, max_pages: int) -> list[JobOffer]:
        offers: list[JobOffer] = []
        slug = quote(keyword.strip().lower().replace(" ", "-"))
        search_url = f"{self.base_url}/ofertas-trabajo/de-{slug}"

        try:
            response = self.request("GET", search_url)
        except Exception as exc:  # noqa: BLE001 - una búsqueda caída no detiene la ejecución
            self.log(f"Error al leer {search_url}: {exc}")
            return offers

        # Los puestos desconocidos redirigen al listado general (sin "/de-").
        if "/de-" not in response.url:
            self.log(f"Sin resultados para '{keyword}' (redirigió a {response.url})")
            return offers

        canonical_url = response.url.split("?")[0]
        html = response.text
        seen_urls: set[str] = set()

        for page in range(1, max_pages + 1):
            if page > 1:
                try:
                    html = self.fetch(f"{canonical_url}?page={page}")
                except Exception as exc:  # noqa: BLE001
                    self.log(f"Error al leer la página {page}: {exc}")
                    break

            if self.debug:
                self.dump_html(html, keyword, page)

            # Las páginas después de la última repiten resultados en vez de venir vacías.
            new_offers = [o for o in self._parse_results(html) if o.url not in seen_urls]
            if not new_offers:
                break
            seen_urls.update(o.url for o in new_offers)
            offers.extend(new_offers)

        return offers

    def _parse_results(self, html: str) -> list[JobOffer]:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("a[data-enlace-oferta][href*='/trabajo/']")
        return [offer for card in cards if (offer := self._parse_card(card))]

    def _parse_card(self, card: Tag) -> JobOffer | None:
        """Construye un JobOffer a partir de una tarjeta (la tarjeta es el propio ``<a>``)."""
        title_el = card.select_one("h3")
        if title_el is None or not card.get("href"):
            return None

        company_el = card.select_one("p.text-secondary")
        desc_el = card.select_one("p.fw-lighter")

        # La fila de metadatos trae la ubicación y la fecha de publicación.
        location = next(
            (
                text
                for span in card.select(".row span.text-dark")
                if (text := span.get_text(strip=True)) and not _DATE_RE.fullmatch(text)
            ),
            "—",
        )

        return JobOffer(
            title=title_el.get_text(strip=True),
            company=company_el.get_text(strip=True) if company_el else "—",
            location=location,
            url=urljoin(self.base_url, card["href"]),
            source=self.source_name,
            description=desc_el.get_text(" ", strip=True) if desc_el else "",
            salary=find_salary(card.get_text(" ", strip=True)),
        )
