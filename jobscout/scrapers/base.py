"""Clase base para todos los scrapers.

Define el contrato común: dada una palabra clave, devolver una lista de
JobOffer. También centraliza la sesión HTTP con headers de navegador y la
pausa entre peticiones para no saturar los portales.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

import requests

from ..models import JobOffer

# Headers que imitan a un navegador real. Muchos portales rechazan peticiones
# sin un User-Agent creíble.
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class BaseScraper(ABC):
    """Contrato común para los scrapers de empleo."""

    # Variables
    source_name: str = "base"

    def __init__(self, request_delay: float = 1.5):
        self.request_delay = request_delay
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def fetch(self, url: str) -> str:
        """Descarga el HTML de una URL respetando la pausa configurada."""
        time.sleep(self.request_delay)
        response = self.session.get(url, timeout=20)
        response.raise_for_status()
        return response.text

    @abstractmethod
    def search(self, keyword: str, max_pages: int) -> list[JobOffer]:
        """Busca ofertas para una palabra clave y las devuelve normalizadas."""
        raise NotImplementedError
