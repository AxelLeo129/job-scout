"""Scraper de Un Mejor Empleo.

El buscador es un formulario POST a ``/empleos`` que redirige a
``/trabajo-<palabra>.html``; enviar el formulario evita adivinar el formato
del slug. Las páginas siguientes se alcanzan con los enlaces de paginación
de cada página (``?t=...&np=N``). La búsqueda es por frase exacta, así que
las palabras clave largas devuelven pocos resultados.

Las tarjetas no muestran la empresa.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from ..models import JobOffer
from .base import BaseScraper

_LOCATION_RE = re.compile(r"Ubicación:\s*(.*?)\s*\|\s*Departamento\s*:\s*(.*)")
_SALARY_RE = re.compile(r"Salario:\s*(.+)$")


class UnMejorEmpleoScraper(BaseScraper):
    """Scraper de unmejorempleo.com.<país>."""

    source_name = "unmejorempleo"
    base_url_template = "https://www.unmejorempleo.com.{country}"

    def search(self, keyword: str, max_pages: int) -> list[JobOffer]:
        offers: list[JobOffer] = []
        try:
            response = self.request(
                "POST",
                f"{self.base_url}/empleos",
                data={"palabra_clave": keyword, "ubicacion": "", "enviado": "1"},
            )
        except Exception as exc:  # noqa: BLE001 - una búsqueda caída no detiene la ejecución
            self.log(f"Error al buscar '{keyword}': {exc}")
            return offers

        page_url = response.url  # tras la redirección; base de los enlaces de paginación
        html = response.text

        for page in range(1, max_pages + 1):
            if self.debug:
                self.dump_html(html, keyword, page)

            soup = BeautifulSoup(html, "html.parser")
            page_offers = self._parse_results(soup, page_url)
            if not page_offers:
                break
            offers.extend(page_offers)

            next_link = self._find_next_link(soup, page + 1)
            if next_link is None:
                break
            page_url = urljoin(page_url, next_link)
            try:
                html = self.fetch(page_url)
            except Exception as exc:  # noqa: BLE001
                self.log(f"Error al leer {page_url}: {exc}")
                break

        return offers

    @staticmethod
    def _find_next_link(soup: BeautifulSoup, next_page: int) -> str | None:
        """Href del enlace de paginación cuyo texto es ``next_page``, si existe."""
        for a in soup.select("a[href*='np=']"):
            if a.get_text(strip=True) == str(next_page):
                return a["href"]
        return None

    def _parse_results(self, soup: BeautifulSoup, page_url: str) -> list[JobOffer]:
        # Los bloques de publicidad reutilizan div.item-normal pero llevan la clase "advert".
        cards = [
            card
            for card in soup.select("div.item-destacado, div.item-normal")
            if "advert" not in card.get("class", [])
        ]
        return [offer for card in cards if (offer := self._parse_card(card, page_url))]

    def _parse_card(self, card: Tag, page_url: str) -> JobOffer | None:
        """Construye un JobOffer a partir de una tarjeta; None si no tiene enlace."""
        link = card.select_one("h3 a")
        if link is None or not link.get("href"):
            return None

        # La palabra buscada viene resaltada en otra etiqueta; unir con " " evita
        # que quede pegada a la siguiente ("DesarrolladorJunior").
        title = re.sub(r"\s+", " ", link.get_text(" ", strip=True))

        description = next(
            (li.get_text(" ", strip=True) for li in card.select("ul li") if not li.get("class")),
            "",
        )

        return JobOffer(
            title=title,
            company="—",
            location=self._extract_location(card),
            url=urljoin(page_url, link["href"]),
            source=self.source_name,
            description=description,
            salary=self._extract_salary(card),
        )

    @staticmethod
    def _extract_location(card: Tag) -> str:
        """``"Ubicación: X | Departamento : Y"`` -> ``"X, Y"`` (o ``"X"`` si son iguales)."""
        loc_el = card.select_one("li.text-primary")
        if loc_el is None:
            return "—"
        text = re.sub(r"\s+", " ", loc_el.get_text(" ", strip=True))
        match = _LOCATION_RE.search(text)
        if not match:
            return text.replace("Ubicación:", "").strip() or "—"
        city, dept = match.group(1).strip(), match.group(2).strip()
        return city if city == dept else f"{city}, {dept}"

    @staticmethod
    def _extract_salary(card: Tag) -> str:
        """Salario de ``"Publicación: dd/mm/aaaa - Salario: Q10,000 a Q15,000"``."""
        meta_el = card.select_one("li.text-warning")
        match = _SALARY_RE.search(meta_el.get_text(" ", strip=True)) if meta_el else None
        if not match:
            return ""
        salary = match.group(1).strip()
        # El sitio muestra "----------" cuando no hay salario.
        return "" if set(salary) <= {"-"} else salary
