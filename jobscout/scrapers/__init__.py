"""Scrapers de portales de empleo.

Para añadir un portal, hereda de :class:`~jobscout.scrapers.base.BaseScraper`
y regístralo en :data:`SCRAPERS` con el nombre que se usa en
``config.ENABLED_SCRAPERS``.
"""

from .acciontrabajo import AccionTrabajoScraper
from .base import BaseScraper
from .computrabajo import ComputrabajoScraper
from .tecoloco import TecolocoScraper
from .trabajosdiarios import TrabajosDiariosScraper
from .unmejorempleo import UnMejorEmpleoScraper

SCRAPERS: dict[str, type[BaseScraper]] = {
    "computrabajo": ComputrabajoScraper,
    "tecoloco": TecolocoScraper,
    "unmejorempleo": UnMejorEmpleoScraper,
    "trabajosdiarios": TrabajosDiariosScraper,
    "acciontrabajo": AccionTrabajoScraper,
}
