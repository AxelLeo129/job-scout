"""Scraper de Trabajos Diarios.

La búsqueda por palabra clave usa rutas tipo /ofertas-trabajo/de-<slug>. El
sitio redirige al sinónimo canónico del puesto (p.ej. "de-desarrollador"
acaba en "de-programador"), así que capturamos la URL final y paginamos sobre
ella con ?page=N.

Ojo: el parámetro GET ?key=... NO filtra (devuelve todo el listado); por eso
usamos la ruta con slug.
"""

from __future__ import annotations

import re
import time
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from ..models import JobOffer
from .base import BaseScraper


class TrabajosDiariosScraper(BaseScraper):
    """Lee ofertas de <país>.trabajosdiarios.com."""

    source_name = "trabajosdiarios"

    def __init__(self, country: str = "gt", request_delay: float = 1.5, debug: bool = False):
        super().__init__(request_delay=request_delay)
        self.country = country
        self.base_url = f"https://{country}.trabajosdiarios.com"
        self.debug = debug

    def search(self, keyword: str, max_pages: int) -> list[JobOffer]:
        offers: list[JobOffer] = []

        slug = quote(keyword.strip().lower().replace(" ", "-"))
        search_url = f"{self.base_url}/ofertas-trabajo/de-{slug}"

        # Primera petición: puede redirigir al slug canónico. Guardamos la URL
        # final para que la paginación no vuelva a pasar por la redirección.
        try:
            time.sleep(self.request_delay)
            response = self.session.get(search_url, timeout=20)
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001 - registramos y seguimos
            print(f"  [trabajosdiarios] Error al leer {search_url}: {exc}")
            return offers

        # Si el sitio nos mandó al listado general (sin "/de-"), la palabra
        # clave no existe como puesto y todo resultado sería ruido.
        if "/de-" not in response.url:
            print(f"  [trabajosdiarios] Sin resultados para '{keyword}' (redirigió a {response.url})")
            return offers

        canonical_url = response.url.split("?")[0]
        html = response.text
        seen_urls: set[str] = set()

        for page in range(1, max_pages + 1):
            if page > 1:
                try:
                    html = self.fetch(f"{canonical_url}?page={page}")
                except Exception as exc:  # noqa: BLE001
                    print(f"  [trabajosdiarios] Error al leer página {page}: {exc}")
                    break

            if self.debug:
                self._dump_html(html, keyword, page)

            page_offers = self._parse_results(html)
            new_offers = [o for o in page_offers if o.url not in seen_urls]
            if not new_offers:
                break
            seen_urls.update(o.url for o in new_offers)
            offers.extend(new_offers)

        return offers

    def _parse_results(self, html: str) -> list[JobOffer]:
        soup = BeautifulSoup(html, "html.parser")
        offers: list[JobOffer] = []

        # Cada oferta es un <a data-enlace-oferta href="/trabajo/<id>/<slug>">.
        for card in soup.select("a[data-enlace-oferta][href*='/trabajo/']"):
            offer = self._parse_card(card)
            if offer is not None:
                offers.append(offer)

        return offers

    def _parse_card(self, card) -> JobOffer | None:
        title_el = card.select_one("h3")
        if title_el is None or not card.get("href"):
            return None

        title = title_el.get_text(strip=True)
        url = urljoin(self.base_url, card["href"])

        company_el = card.select_one("p.text-secondary")
        company = company_el.get_text(strip=True) if company_el else "—"

        # Ubicación: el <span> junto al icono de mapa, en la fila de metadatos.
        location = "—"
        for span in card.select(".row span.text-dark"):
            text = span.get_text(strip=True)
            # Descartamos la fecha (dd/mm/aaaa); lo demás es la ubicación.
            if not re.fullmatch(r"\d{2}/\d{2}/\d{4}", text):
                location = text
                break

        desc_el = card.select_one("p.fw-lighter")
        description = desc_el.get_text(" ", strip=True) if desc_el else ""

        # Salario: si aparece, viene dentro del texto de la tarjeta.
        text = card.get_text(" ", strip=True).replace("\xa0", " ")
        match = re.search(r"(Q|\$)\s?[\d.,]+(\s?-\s?(Q|\$)?\s?[\d.,]+)?", text)
        salary = match.group(0) if match else ""

        return JobOffer(
            title=title,
            company=company,
            location=location,
            url=url,
            source=self.source_name,
            description=description,
            salary=salary,
        )

    def _dump_html(self, html: str, keyword: str, page: int) -> None:
        safe_kw = keyword.replace(" ", "_")
        filename = f"debug_trabajosdiarios_{safe_kw}_p{page}.html"
        with open(filename, "w", encoding="utf-8") as fh:
            fh.write(html)
        print(f"  [debug] HTML guardado en {filename}")
