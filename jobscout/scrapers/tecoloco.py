"""Scraper de Tecoloco.

Tecoloco usa un dominio por país (tecoloco.com.gt, tecoloco.com.sv, ...). La
búsqueda es un GET simple y la paginación va en el parámetro Page.

URL de búsqueda (Guatemala):
    https://www.tecoloco.com.gt/empleos?Keywords=desarrollador
    ...y para paginar:  &Page=2

El listado no incluye salario ni descripción; solo título, empresa y ubicación.
"""

from __future__ import annotations

from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from ..models import JobOffer
from .base import BaseScraper


class TecolocoScraper(BaseScraper):
    """Lee ofertas de Tecoloco para un país concreto."""

    source_name = "tecoloco"

    def __init__(self, country: str = "gt", request_delay: float = 1.5, debug: bool = False):
        super().__init__(request_delay=request_delay)
        self.country = country
        self.base_url = f"https://www.tecoloco.com.{country}"
        self.debug = debug

    def _build_search_url(self, keyword: str, page: int) -> str:
        url = f"{self.base_url}/empleos?Keywords={quote_plus(keyword.strip())}"
        if page > 1:
            url += f"&Page={page}"
        return url

    def search(self, keyword: str, max_pages: int) -> list[JobOffer]:
        offers: list[JobOffer] = []
        seen_urls: set[str] = set()

        for page in range(1, max_pages + 1):
            url = self._build_search_url(keyword, page)
            try:
                html = self.fetch(url)
            except Exception as exc:  # noqa: BLE001 - registramos y seguimos
                print(f"  [tecoloco] Error al leer {url}: {exc}")
                break

            if self.debug:
                self._dump_html(html, keyword, page)

            page_offers = self._parse_results(html)
            # Si la página no trae nada nuevo (vacía o repite ofertas ya
            # vistas, p.ej. porque pedimos más páginas de las que hay), paramos.
            new_offers = [o for o in page_offers if o.url not in seen_urls]
            if not new_offers:
                break
            seen_urls.update(o.url for o in new_offers)
            offers.extend(new_offers)

        return offers

    def _parse_results(self, html: str) -> list[JobOffer]:
        soup = BeautifulSoup(html, "html.parser")
        offers: list[JobOffer] = []

        # Cada oferta vive en un <div class="module job-result">.
        for card in soup.select("div.module.job-result"):
            offer = self._parse_card(card)
            if offer is not None:
                offers.append(offer)

        return offers

    def _parse_card(self, card) -> JobOffer | None:
        # Título y enlace: <h2 itemprop="title"><a href="/123456/...aspx">
        link = (
            card.select_one("h2[itemprop='title'] a")
            or card.select_one(".job-result-title a")
            or card.select_one("a.show-more")
        )
        if link is None or not link.get("href"):
            return None

        title = link.get_text(strip=True)
        url = urljoin(self.base_url, link["href"])

        company_el = card.select_one("li[itemprop='employerName']") or card.select_one("li.name")
        company = company_el.get_text(strip=True) if company_el else "—"

        loc_el = card.select_one("li[itemprop='jobLocation']") or card.select_one("li.location")
        location = loc_el.get_text(" ", strip=True) if loc_el else "—"

        return JobOffer(
            title=title,
            company=company,
            location=location,
            url=url,
            source=self.source_name,
        )

    def _dump_html(self, html: str, keyword: str, page: int) -> None:
        safe_kw = keyword.replace(" ", "_")
        filename = f"debug_tecoloco_{safe_kw}_p{page}.html"
        with open(filename, "w", encoding="utf-8") as fh:
            fh.write(html)
        print(f"  [debug] HTML guardado en {filename}")
