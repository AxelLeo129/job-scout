"""Modelo de datos común para las ofertas de empleo.

Todos los scrapers, sin importar el portal, devuelven objetos JobOffer. Así el
resto del pipeline (deduplicación, ranking, notificación) no necesita saber de
qué portal vino cada oferta.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


@dataclass
class JobOffer:
    """Una oferta de empleo normalizada."""

    # Campos identificadores
    title: str
    company: str
    location: str
    url: str
    source: str  # nombre del portal, p.ej. "computrabajo"

    # Campos opcionales
    description: str = ""
    salary: str = ""

    # Campos calculados por el pipeline (no por el scraper)
    score: int = 0
    score_reason: str = ""

    @property
    def fingerprint(self) -> str:
        """Huella única de la oferta, para deduplicar y recordar las vistas.

        Se basa en la URL porque es lo más estable entre ejecuciones.
        """
        return hashlib.sha256(self.url.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict:
        """Serializa la oferta a un diccionario (para guardar en JSON)."""
        return {
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "url": self.url,
            "source": self.source,
            "description": self.description,
            "salary": self.salary,
            "score": self.score,
            "score_reason": self.score_reason,
        }
