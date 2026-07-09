"""Scrapers de portales de empleo.

Cada portal es un módulo independiente. Para añadir uno nuevo, hereda de
BaseScraper y registra la clase en SCRAPERS.
"""

from .acciontrabajo import AccionTrabajoScraper
from .computrabajo import ComputrabajoScraper
from .tecoloco import TecolocoScraper
from .trabajosdiarios import TrabajosDiariosScraper
from .unmejorempleo import UnMejorEmpleoScraper

# Registro de scrapers disponibles. main.py recorre este diccionario.
SCRAPERS = {
    "computrabajo": ComputrabajoScraper,
    "tecoloco": TecolocoScraper,
    "unmejorempleo": UnMejorEmpleoScraper,
    "trabajosdiarios": TrabajosDiariosScraper,
    "acciontrabajo": AccionTrabajoScraper,
}
