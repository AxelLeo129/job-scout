"""Scraper de Un Mejor Empleo.

El buscador del sitio es un formulario POST a /empleos que redirige a una URL
tipo /trabajo-<palabra>.html. Hacemos el POST para la primera página (así no
adivinamos el formato del slug) y seguimos los enlaces de paginación
(?t=...&np=N) que trae la propia página.

El listado no muestra la empresa; sí ubicación, descripción breve y, a veces,
el salario.
"""

from __future__ import annotations

import re
import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import JobOffer
from .base import BaseScraper


class UnMejorEmpleoScraper(BaseScraper):
    """Lee ofertas de unmejorempleo.com.<país>."""

    source_name = "unmejorempleo"

    def __init__(self, country: str = "gt", request_delay: float = 1.5, debug: bool = False):
        super().__init__(request_delay=request_delay)
        self.country = country
        self.base_url = f"https://www.unmejorempleo.com.{country}"
        self.debug = debug

    def search(self, keyword: str, max_pages: int) -> list[JobOffer]:
        offers: list[JobOffer] = []

        # Página 1: POST del formulario de búsqueda (redirige al listado).
        try:
            time.sleep(self.request_delay)
            response = self.session.post(
                f"{self.base_url}/empleos",
                data={"palabra_clave": keyword, "ubicacion": "", "enviado": "1"},
                timeout=20,
            )
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001 - registramos y seguimos
            print(f"  [unmejorempleo] Error al buscar '{keyword}': {exc}")
            return offers

        # URL final tras la redirección; sirve de base para la paginación.
        page_url = response.url
        html = response.text

        for page in range(1, max_pages + 1):
            if self.debug:
                self._dump_html(html, keyword, page)

            soup = BeautifulSoup(html, "html.parser")
            page_offers = self._parse_results(soup, page_url)
            if not page_offers:
                break
            offers.extend(page_offers)

            # ¿Hay enlace a la página siguiente? La paginación son <a> cuyo
            # texto es el número de página (?t=...&np=N).
            next_link = self._find_next_link(soup, page + 1)
            if next_link is None:
                break
            page_url = urljoin(page_url, next_link)
            try:
                html = self.fetch(page_url)
            except Exception as exc:  # noqa: BLE001
                print(f"  [unmejorempleo] Error al leer {page_url}: {exc}")
                break

        return offers

    @staticmethod
    def _find_next_link(soup: BeautifulSoup, next_page: int) -> str | None:
        for a in soup.select("a[href*='np=']"):
            if a.get_text(strip=True) == str(next_page):
                return a["href"]
        return None

    def _parse_results(self, soup: BeautifulSoup, page_url: str) -> list[JobOffer]:
        offers: list[JobOffer] = []

        # Cada oferta es un div.item-destacado o div.item-normal; los bloques
        # de publicidad reutilizan item-normal pero llevan la clase "advert".
        for card in soup.select("div.item-destacado, div.item-normal"):
            if "advert" in card.get("class", []):
                continue
            offer = self._parse_card(card, page_url)
            if offer is not None:
                offers.append(offer)

        return offers

    def _parse_card(self, card, page_url: str) -> JobOffer | None:
        link = card.select_one("h3 a")
        if link is None or not link.get("href"):
            return None

        title = link.get_text(strip=True)
        url = urljoin(page_url, link["href"])

        # Ubicación: "Ubicación: X | Departamento : Y" → "X, Y"
        loc_el = card.select_one("li.text-primary")
        location = "—"
        if loc_el:
            text = re.sub(r"\s+", " ", loc_el.get_text(" ", strip=True))
            match = re.search(r"Ubicación:\s*(.*?)\s*\|\s*Departamento\s*:\s*(.*)", text)
            if match:
                city, dept = match.group(1).strip(), match.group(2).strip()
                location = city if city == dept else f"{city}, {dept}"
            else:
                location = text.replace("Ubicación:", "").strip()

        # Salario: "Publicación: dd/mm/aaaa - Salario: Q10,000 a Q15,000"
        salary = ""
        meta_el = card.select_one("li.text-warning")
        if meta_el:
            match = re.search(r"Salario:\s*(.+)$", meta_el.get_text(" ", strip=True))
            if match:
                salary = match.group(1).strip()
                if set(salary) <= {"-"}:  # el sitio pone "----------" si no hay
                    salary = ""

        # Descripción breve: el <li> sin clase dentro de la lista.
        description = ""
        for li in card.select("ul li"):
            if not li.get("class"):
                description = li.get_text(" ", strip=True)
                break

        return JobOffer(
            title=title,
            company="—",  # el listado no muestra la empresa
            location=location,
            url=url,
            source=self.source_name,
            description=description,
            salary=salary,
        )

    def _dump_html(self, html: str, keyword: str, page: int) -> None:
        safe_kw = keyword.replace(" ", "_")
        filename = f"debug_unmejorempleo_{safe_kw}_p{page}.html"
        with open(filename, "w", encoding="utf-8") as fh:
            fh.write(html)
        print(f"  [debug] HTML guardado en {filename}")
