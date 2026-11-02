"""Contrato común y lógica HTTP compartida por todos los scrapers."""

from __future__ import annotations

import re
import time
from abc import ABC, abstractmethod
from typing import ClassVar

import requests

from ..models import JobOffer

# Muchos portales rechazan peticiones sin un User-Agent de navegador.
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

REQUEST_TIMEOUT_SECONDS = 20

# Montos en quetzales o dólares con el símbolo antes ("Q10,000 - Q15,000")
# o después del número ("16,000.00 Q").
_SALARY_RE = re.compile(
    r"(?:Q|\$)\s?\d[\d.,]*(?:\s?-\s?(?:Q|\$)?\s?\d[\d.,]*)?"
    r"|\d[\d.,]*\s?(?:Q|\$)(?!\w)"
)


def find_salary(text: str) -> str:
    """Devuelve el primer monto con forma de salario en ``text``, o cadena vacía."""
    match = _SALARY_RE.search(text.replace("\xa0", " "))
    return match.group(0) if match else ""


class BaseScraper(ABC):
    """Clase base de los scrapers de portales de empleo.

    Las subclases definen ``source_name`` y ``base_url_template`` (se
    formatea con el código de país) e implementan :meth:`search`.
    """

    source_name: ClassVar[str]
    base_url_template: ClassVar[str]

    def __init__(self, country: str = "gt", request_delay: float = 1.5, debug: bool = False):
        self.country = country
        self.base_url = self.base_url_template.format(country=country)
        self.request_delay = request_delay
        self.debug = debug
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Hace una petición HTTP tras la pausa configurada.

        Raises:
            requests.HTTPError: si la respuesta es 4xx/5xx.
        """
        time.sleep(self.request_delay)
        response = self.session.request(method, url, timeout=REQUEST_TIMEOUT_SECONDS, **kwargs)
        response.raise_for_status()
        return response

    def fetch(self, url: str) -> str:
        """Hace GET a ``url`` y devuelve el HTML."""
        return self.request("GET", url).text

    def log(self, message: str) -> None:
        """Imprime un mensaje con el nombre del scraper como prefijo."""
        print(f"  [{self.source_name}] {message}")

    def dump_html(self, html: str, keyword: str, page: int = 1) -> None:
        """Guarda el HTML crudo en ``debug_<portal>_<palabra>_p<página>.html`` (modo debug)."""
        filename = f"debug_{self.source_name}_{keyword.replace(' ', '_')}_p{page}.html"
        with open(filename, "w", encoding="utf-8") as fh:
            fh.write(html)
        self.log(f"HTML guardado en {filename}")

    @abstractmethod
    def search(self, keyword: str, max_pages: int) -> list[JobOffer]:
        """Busca ``keyword`` y devuelve las ofertas de hasta ``max_pages`` páginas.

        Las implementaciones no deben lanzar excepciones por errores de red:
        registran el error y devuelven lo recolectado hasta ese momento.
        """

    def fetch_details(self, offer: JobOffer) -> None:
        """Completa ``offer`` con datos de su página de detalle.

        Por defecto no hace nada. Solo se llama para ofertas nuevas, así que
        cuesta una petición extra por oferta nueva, no por oferta listada.
        """
