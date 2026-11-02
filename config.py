"""Configuración de JobScout.

Los secretos (API keys, tokens) van en el archivo .env, no aquí.
"""

# Cada palabra clave es una búsqueda independiente en cada portal, tal cual.
SEARCH_KEYWORDS = [
    "desarrollador de software",
    "desarrollador web",
    "desarrollador full stack",
    "frontend",
    "backend",
    "programador",
]

# Código de país para todos los portales ("gt" = Guatemala). No todos los
# portales existen en todos los países (Tecoloco solo en Centroamérica, p.ej.).
COUNTRY = "gt"

# Portales a consultar; cada nombre debe ser una clave de SCRAPERS (jobscout/scrapers/__init__.py).
ENABLED_SCRAPERS = [
    "computrabajo",
    "tecoloco",
    "unmejorempleo",
    "trabajosdiarios",
    # "acciontrabajo",  # bloqueado por el anti-bots de Cloudflare (403)
]

# Páginas de resultados por palabra clave (~20 ofertas por página).
MAX_PAGES_PER_KEYWORD = 2

# Se descartan antes del ranking las ofertas cuya empresa o título (y la
# descripción, ver abajo) contienen alguno de estos términos. Ignora
# mayúsculas y acentos.
EXCLUDE_TERMS = [
    "banca",
    "banco",
    "bancari",  # cubre "bancario" / "bancaria"
    "genesis empresarial",
]

# Buscar también los EXCLUDE_TERMS en la descripción. Con True se descartan
# ofertas que solo mencionan un término de pasada ("experiencia en banca deseable").
EXCLUDE_SEARCH_DESCRIPTION = False

# Modalidades que el ranking debe favorecer. Las demás puntúan más bajo, no se descartan.
PREFERRED_MODALITIES = [
    "remoto",
    "híbrido",
]

# Puntaje mínimo (0-100) para enviar una oferta por Telegram.
MIN_SCORE_TO_NOTIFY = 60

# Avisar por Telegram cuando un portal devuelve 0 ofertas en esta cantidad de
# ejecuciones seguidas (suele ser un cambio de HTML o un bloqueo). 0 lo desactiva.
PORTAL_ALERT_AFTER_EMPTY_RUNS = 3

# Modelo de Claude usado para el ranking.
RANKING_MODEL = "claude-haiku-4-5"

# CV en texto plano que lee el ranking.
CV_PATH = "cv.txt"

# Base SQLite con las ofertas procesadas y las ofertas por portal en cada ejecución.
SEEN_DB_PATH = "seen_offers.db"

# Archivo de huellas anterior a SQLite; si existe, se migra a SEEN_DB_PATH.
LEGACY_SEEN_JSON_PATH = "seen_offers.json"

# Pausa (segundos) entre peticiones HTTP a los portales.
REQUEST_DELAY_SECONDS = 1.5
