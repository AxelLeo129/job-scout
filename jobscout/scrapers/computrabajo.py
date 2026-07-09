"""Scraper de Computrabajo.

Computrabajo no tiene API pública, así que leemos el HTML de las páginas de
resultados. La estructura del sitio cambia cada cierto tiempo; por eso los
selectores se prueban en orden (varias alternativas) y, si todo falla, se puede
volcar el HTML crudo con el modo debug para ajustar los selectores.

URL de búsqueda (Guatemala):
    https://gt.computrabajo.com/trabajo-de-desarrollador-de-software
    ...y para paginar:  ?p=2
"""

from __future__ import annotations

import re
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from ..models import JobOffer
from .base import BaseScraper


class ComputrabajoScraper(BaseScraper):
    """Lee ofertas de Computrabajo para un país concreto."""

    source_name = "computrabajo"

    def __init__(self, country: str = "gt", request_delay: float = 1.5, debug: bool = False):
        super().__init__(request_delay=request_delay)
        self.country = country
        self.base_url = f"https://{country}.computrabajo.com"
        self.debug = debug

    def _build_search_url(self, keyword: str, page: int) -> str:
        """Construye la URL de búsqueda para una palabra clave y página.

        Computrabajo usa rutas tipo "/trabajo-de-<slug>" donde el slug es la
        palabra clave con guiones en lugar de espacios.
        """
        slug = quote(keyword.strip().lower().replace(" ", "-"))
        url = f"{self.base_url}/trabajo-de-{slug}"
        if page > 1:
            url += f"?p={page}"
        return url

    def search(self, keyword: str, max_pages: int) -> list[JobOffer]:
        offers: list[JobOffer] = []
        for page in range(1, max_pages + 1):
            url = self._build_search_url(keyword, page)
            try:
                html = self.fetch(url)
            except Exception as exc:  # noqa: BLE001 - registramos y seguimos
                print(f"  [computrabajo] Error al leer {url}: {exc}")
                break

            if self.debug:
                self._dump_html(html, keyword, page)

            page_offers = self._parse_results(html)
            if not page_offers:
                # Si una página no trae resultados, no tiene sentido seguir.
                break
            offers.extend(page_offers)

        return offers

    def _parse_results(self, html: str) -> list[JobOffer]:
        """Extrae las ofertas de una página de resultados."""
        soup = BeautifulSoup(html, "html.parser")
        offers: list[JobOffer] = []

        # Cada oferta vive en un <article>. Probamos varias clases conocidas.
        articles = soup.select("article.box_offer") or soup.select("article")

        for article in articles:
            offer = self._parse_article(article)
            if offer is not None:
                offers.append(offer)

        return offers

    def _parse_article(self, article) -> JobOffer | None:
        """Convierte un <article> de Computrabajo en un JobOffer.

        Devuelve None si no se encuentra un título/enlace válido.
        """
        # Título y enlace: el <a> dentro del encabezado de la oferta.
        link = (
            article.select_one("h2 a")
            or article.select_one("a.js-o-link")
            or article.select_one("a[href*='/ofertas-de-trabajo/']")
        )
        if link is None or not link.get("href"):
            return None

        title = link.get_text(strip=True)
        url = urljoin(self.base_url, link["href"])

        # Empresa: suele ser un enlace o párrafo con la clase de empresa.
        company_el = (
            article.select_one("a.fc_base.t_word_wrap")
            or article.select_one("p.dFlex a")
            or article.select_one("[class*='company']")
        )
        company = company_el.get_text(strip=True) if company_el else "—"

        # Ubicación: párrafo con la clase de base, normalmente el último.
        location = self._extract_location(article)

        # Salario: si aparece, suele tener un símbolo de moneda.
        salary = self._extract_salary(article)

        # Descripción breve: el resumen que muestra el listado.
        desc_el = article.select_one("p.fs16") or article.select_one("[class*='descrip']")
        description = desc_el.get_text(" ", strip=True) if desc_el else ""

        return JobOffer(
            title=title,
            company=company,
            location=location,
            url=url,
            source=self.source_name,
            description=description,
            salary=salary,
        )

    @staticmethod
    def _extract_location(article) -> str:
        """Intenta encontrar la ubicación dentro del <article>."""
        loc_el = article.select_one("p.fs16.fc_base") or article.select_one("[class*='location']")
        if loc_el:
            return loc_el.get_text(" ", strip=True)
        return "—"

    @staticmethod
    def _extract_salary(article) -> str:
        """Busca un texto que parezca un salario (con Q, $ o 'mensual')."""
        text = article.get_text(" ", strip=True)
        match = re.search(r"(Q|\$)\s?[\d.,]+(\s?-\s?(Q|\$)?\s?[\d.,]+)?", text)
        return match.group(0) if match else ""

    def _dump_html(self, html: str, keyword: str, page: int) -> None:
        """Guarda el HTML crudo en modo debug para revisar los selectores."""
        safe_kw = keyword.replace(" ", "_")
        filename = f"debug_computrabajo_{safe_kw}_p{page}.html"
        with open(filename, "w", encoding="utf-8") as fh:
            fh.write(html)
        print(f"  [debug] HTML guardado en {filename}")
