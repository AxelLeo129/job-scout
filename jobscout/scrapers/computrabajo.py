"""Scraper de Computrabajo.

URL de búsqueda: ``https://<país>.computrabajo.com/trabajo-de-<slug>?p=<página>``.
Las tarjetas del listado no traen descripción, así que
:meth:`ComputrabajoScraper.fetch_details` la lee de la página de cada oferta.
"""

from __future__ import annotations

from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup, Tag

from ..models import JobOffer, canonical_url
from .base import BaseScraper, find_salary

# Tope del texto de detalle que se pasa al ranking (acota los tokens).
DETAIL_MAX_CHARS = 3000


class ComputrabajoScraper(BaseScraper):
    """Scraper de <país>.computrabajo.com."""

    source_name = "computrabajo"
    base_url_template = "https://{country}.computrabajo.com"

    def search(self, keyword: str, max_pages: int) -> list[JobOffer]:
        offers: list[JobOffer] = []
        for page in range(1, max_pages + 1):
            url = self._build_search_url(keyword, page)
            try:
                html = self.fetch(url)
            except Exception as exc:  # noqa: BLE001 - una página caída no detiene la ejecución
                self.log(f"Error al leer {url}: {exc}")
                break

            if self.debug:
                self.dump_html(html, keyword, page)

            page_offers = self._parse_results(html)
            if not page_offers:
                break
            offers.extend(page_offers)

        return offers

    def fetch_details(self, offer: JobOffer) -> None:
        """Añade a la descripción el texto de la página de detalle (cuerpo,
        requisitos, contrato y jornada)."""
        detail = self._parse_detail(self.fetch(offer.url))
        if detail:
            offer.description = f"{offer.description}\n{detail}".strip()

    def _build_search_url(self, keyword: str, page: int) -> str:
        slug = quote(keyword.strip().lower().replace(" ", "-"))
        url = f"{self.base_url}/trabajo-de-{slug}"
        if page > 1:
            url += f"?p={page}"
        return url

    def _parse_results(self, html: str) -> list[JobOffer]:
        soup = BeautifulSoup(html, "html.parser")
        articles = soup.select("article.box_offer") or soup.select("article")
        return [offer for article in articles if (offer := self._parse_article(article))]

    def _parse_article(self, article: Tag) -> JobOffer | None:
        """Construye un JobOffer a partir de un ``<article>``; None si no tiene enlace."""
        link = (
            article.select_one("h2 a")
            or article.select_one("a.js-o-link")
            or article.select_one("a[href*='/ofertas-de-trabajo/']")
        )
        if link is None or not link.get("href"):
            return None

        # Las empresas confidenciales traen texto suelto en vez de enlace; se
        # prefiere el enlace porque el <p> puede incluir la calificación ("4.4 ★").
        company_el = (
            article.select_one("p.dFlex a")
            or article.select_one("p.dFlex")
            or article.select_one("[class*='company']")
        )
        company = company_el.get_text(" ", strip=True) if company_el else ""

        modality = self._icon_text(article, "i_home_office")

        return JobOffer(
            title=link.get_text(strip=True),
            company=company or "—",
            location=self._extract_location(article),
            url=canonical_url(urljoin(self.base_url, link["href"])),
            source=self.source_name,
            description=f"Modalidad: {modality}" if modality else "",
            salary=self._icon_text(article, "i_salary") or find_salary(article.get_text(" ", strip=True)),
        )

    @staticmethod
    def _icon_text(article: Tag, icon_class: str) -> str:
        """Texto del elemento que contiene ``span.icon.<icon_class>``."""
        icon = article.select_one(f"span.icon.{icon_class}")
        return icon.parent.get_text(" ", strip=True) if icon and icon.parent else ""

    @staticmethod
    def _extract_location(article: Tag) -> str:
        # Empresa y ubicación son ambos p.fs16.fc_base; el de la empresa además lleva .dFlex.
        loc_el = (
            article.select_one("p.fs16.fc_base:not(.dFlex)")
            or article.select_one("[class*='location']")
        )
        return (loc_el.get_text(" ", strip=True) if loc_el else "") or "—"

    @staticmethod
    def _parse_detail(html: str) -> str:
        """Extrae el texto útil de ``div[div-link='oferta']`` en la página de detalle."""
        soup = BeautifulSoup(html, "html.parser")
        box = soup.select_one("div[div-link='oferta']")
        if box is None:
            return ""

        parts: list[str] = []
        for el in box.find_all(["div", "p", "ul"], recursive=False):
            classes = el.get("class") or []
            # Se omiten bloques ocultos, títulos de sección (fwB), fecha y palabras
            # clave (fc_aux) y las filas de botones postular/denunciar (div sin mbB).
            if {"hide", "fwB", "fc_aux"} & set(classes):
                continue
            if el.name == "div" and "mbB" not in classes:
                continue
            if el.name == "ul":
                text = "; ".join(li.get_text(" ", strip=True) for li in el.select("li"))
            else:
                text = el.get_text(" ", strip=True)
            if text:
                parts.append(text)

        return "\n".join(parts)[:DETAIL_MAX_CHARS]
