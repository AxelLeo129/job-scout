"""Configuración central de JobScout.

Edita aquí tus criterios de búsqueda. Las claves secretas (API keys, tokens)
van en el archivo .env, no aquí.
"""

# Palabras clave a buscar. Cada una genera una búsqueda independiente.
# Se usan tal cual aparecen en los portales de empleo.
SEARCH_KEYWORDS = [
    "desarrollador de software",
    "desarrollador web",
    "desarrollador full stack",
    "frontend",
    "backend",
]

# País para todos los portales. "gt" = Guatemala.
# Ojo: no todos los portales existen en todos los países (Computrabajo sí
# tiene "mx", "co", "pe"...; Tecoloco solo Centroamérica, etc.).
COUNTRY = "gt"

# Portales activos. Cada nombre debe existir en SCRAPERS
# (jobscout/scrapers/__init__.py). Comenta el que quieras desactivar.
ENABLED_SCRAPERS = [
    "computrabajo",
    "tecoloco",
    "unmejorempleo",
    "trabajosdiarios",
    "acciontrabajo",
]

# Cuántas páginas de resultados recorrer por palabra clave (≈20 ofertas por página).
MAX_PAGES_PER_KEYWORD = 2

# Puntaje mínimo (0-100) para que una oferta se notifique por Telegram.
# Subir este número = menos ofertas pero más relevantes.
MIN_SCORE_TO_NOTIFY = 60

# Modelo de Claude usado para el ranking. Haiku es barato y rápido.
RANKING_MODEL = "claude-haiku-4-5"

# Ruta al CV en texto plano (usado por la IA para puntuar).
CV_PATH = "cv.txt"

# Base SQLite donde se guardan las ofertas ya vistas (para no repetir).
SEEN_DB_PATH = "seen_offers.db"

# Archivo antiguo de huellas; si existe, se migra a la base y se renombra.
LEGACY_SEEN_JSON_PATH = "seen_offers.json"

# Pausa (segundos) entre peticiones HTTP, para ser respetuosos con los portales.
REQUEST_DELAY_SECONDS = 1.5
