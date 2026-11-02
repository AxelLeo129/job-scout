"""Modelo de oferta común a todos los portales, usado por scrapers y pipeline."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from urllib.parse import urldefrag


def canonical_url(url: str) -> str:
    """Quita el fragmento de ``url``.

    Computrabajo añade anclas de seguimiento como ``#lc=ListOffers-Score3-6``
    que cambian según la posición de la oferta en el listado.
    """
    return urldefrag(url).url


def fingerprint_url(url: str) -> str:
    """Prefijo de 16 caracteres del SHA-256 de la URL canónica."""
    return hashlib.sha256(canonical_url(url).encode("utf-8")).hexdigest()[:16]


@dataclass
class JobOffer:
    """Oferta de empleo normalizada, venga del portal que venga.

    Attributes:
        title: Título del puesto tal como lo muestra el portal.
        company: Empresa, o "—" si el portal no la muestra.
        location: Ubicación legible, o "—" si se desconoce.
        url: URL de la oferta.
        source: Nombre del scraper (clave en ``SCRAPERS``).
        description: Texto libre que se pasa al ranking; puede estar vacío.
        salary: Salario tal como lo muestra el portal; puede estar vacío.
        score: Puntaje de encaje 0-100, lo asigna el ranking.
        score_reason: Justificación breve de ``score``, la asigna el ranking.
    """

    title: str
    company: str
    location: str
    url: str
    source: str
    description: str = ""
    salary: str = ""
    score: int = 0
    score_reason: str = ""

    @property
    def fingerprint(self) -> str:
        """Identificador estable entre ejecuciones, derivado de la URL canónica."""
        return fingerprint_url(self.url)
