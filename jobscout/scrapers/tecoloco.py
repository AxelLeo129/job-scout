"""Scraper de Tecoloco.

URL de búsqueda: ``https://www.tecoloco.com.<país>/empleos?Keywords=<palabra>&Page=<n>``.
Las tarjetas traen título, empresa y ubicación; no salario ni descripción.
"""

from __future__ import annotations

from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup, Tag

from ..models import JobOffer
from .base import BaseScraper


class TecolocoScraper(BaseScraper):
    """Scraper de tecoloco.com.<país>."""

    source_name = "tecoloco"
    base_url_template = "https://www.tecoloco.com.{country}"

    def search(self, keyword: str, max_pages: int) -> list[JobOffer]:
        offers: list[JobOffer] = []
        seen_urls: set[str] = set()

        for page in range(1, max_pages + 1):
            url = self._build_search_url(keyword, page)
            try:
                html = self.fetch(url)
            except Exception as exc:  # noqa: BLE001 - una página caída no detiene la ejecución
                self.log(f"Error al leer {url}: {exc}")
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

    def _build_search_url(self, keyword: str, page: int) -> str:
        url = f"{self.base_url}/empleos?Keywords={quote_plus(keyword.strip())}"
        if page > 1:
            url += f"&Page={page}"
        return url

    def _parse_results(self, html: str) -> list[JobOffer]:
        soup = BeautifulSoup(html, "html.parser")
        # div.job-card es el diseño actual; div.module.job-result el anterior.
        cards = soup.select("div.job-card, div.module.job-result")
        return [offer for card in cards if (offer := self._parse_card(card))]

    def _parse_card(self, card: Tag) -> JobOffer | None:
        """Construye un JobOffer a partir de una tarjeta; None si no tiene enlace."""
        link = (
            card.select_one("h2[itemprop='title'] a")
            or card.select_one(".job-result-title a")
            or card.select_one("a.show-more")
        )
        if link is None or not link.get("href"):
            return None

        company_el = (
            card.select_one(".job-card__content-info span.subtitle")
            or card.select_one("li[itemprop='employerName']")
            or card.select_one("li.name")
        )

        map_icon = card.select_one(".job-card__info-location i.map-point")
        loc_el = (
            (map_icon.parent if map_icon else None)
            or card.select_one("li[itemprop='jobLocation']")
            or card.select_one("li.location")
        )

        return JobOffer(
            title=link.get_text(strip=True),
            company=company_el.get_text(strip=True) if company_el else "—",
            location=loc_el.get_text(" ", strip=True).replace(" ,", ",") if loc_el else "—",
            url=urljoin(self.base_url, link["href"]),
            source=self.source_name,
        )
