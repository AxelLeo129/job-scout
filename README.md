# JobScout 🎯

Agregador de ofertas de empleo con **ranking por IA** y notificaciones por
**Telegram**. Busca ofertas en portales (**Computrabajo**, **Tecoloco**,
**Un Mejor Empleo**, **Trabajos Diarios** y **Acción Trabajo**), las puntúa
contra tu CV usando Claude, y te manda las mejores.

```
Portales ──► Scrapers ──► Dedup ──► Ranking IA (Claude) ──► Telegram
```

## Requisitos

- Python 3.11+
- Una clave de API de [Anthropic](https://console.anthropic.com/) (para el ranking)
- Un bot de Telegram (gratis, vía [@BotFather](https://t.me/BotFather))

## Instalación

```powershell
# Desde la carpeta jobscout/
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Configuración

1. Copia `.env.example` a `.env` y rellena tus claves:
   - `ANTHROPIC_API_KEY` — de console.anthropic.com
   - `TELEGRAM_BOT_TOKEN` — te lo da @BotFather al crear el bot
   - `TELEGRAM_CHAT_ID` — escríbele a [@userinfobot](https://t.me/userinfobot) y te da tu ID

2. Ajusta `config.py`:
   - `SEARCH_KEYWORDS` — los puestos que buscas
   - `COUNTRY` — `gt` para Guatemala (aplica a todos los portales)
   - `ENABLED_SCRAPERS` — qué portales usar (por defecto los 5)
   - `MIN_SCORE_TO_NOTIFY` — puntaje mínimo (0-100) para notificar

3. Tu CV ya está en `cv.txt`. Edítalo si cambia algo.

## Uso

```powershell
# Prueba sin enviar a Telegram (imprime en consola):
python main.py --dry-run

# Ejecución normal (envía a Telegram):
python main.py

# Si Computrabajo cambió su HTML y no encuentra ofertas, guarda el HTML crudo
# para revisar los selectores:
python main.py --debug
```

### Automatizarlo (que corra solo cada día)

En Windows, usa el **Programador de tareas** para ejecutar
`python main.py` una vez al día. (También puedo ayudarte a configurarlo.)

## Estructura

```
jobscout/
├── main.py                  # orquestador del pipeline
├── config.py                # tus criterios de búsqueda
├── cv.txt                   # tu CV en texto (lo lee la IA)
├── .env                     # claves secretas (NO subir a git)
└── jobscout/
    ├── models.py            # JobOffer: formato común de oferta
    ├── ranking.py           # puntuación con Claude
    ├── notifier.py          # envío a Telegram
    ├── storage.py           # recuerda ofertas ya vistas
    └── scrapers/
        ├── base.py            # clase base de scraper
        ├── computrabajo.py    # scraper de Computrabajo
        ├── tecoloco.py        # scraper de Tecoloco
        ├── unmejorempleo.py   # scraper de Un Mejor Empleo
        ├── trabajosdiarios.py # scraper de Trabajos Diarios
        └── acciontrabajo.py   # scraper de Acción Trabajo
```

## Añadir más portales

Crea `jobscout/scrapers/tu_portal.py`, hereda de `BaseScraper`, implementa
`search()` devolviendo `JobOffer`, y regístralo en `jobscout/scrapers/__init__.py`.
El resto del pipeline (ranking, Telegram) funciona sin cambios.

## Notas importantes

- **Computrabajo / Tecoloco / Un Mejor Empleo / Trabajos Diarios / Acción
  Trabajo**: el scraping es viable pero su HTML cambia; por eso los selectores
  son tolerantes y existe el modo `--debug`.
- **Trabajos Diarios** busca por "puesto" (redirige al sinónimo canónico:
  p.ej. "desarrollador" → "programador"); si la palabra clave no existe como
  puesto, no devuelve nada en lugar de traer todo el listado.
- **Acción Trabajo** pagina con scroll infinito, así que solo se lee la
  primera página (~20 ofertas por búsqueda).
- **LinkedIn**: requiere login y es agresivo baneando bots. Se deja para una
  fase posterior y con cuenta secundaria.
- Sé respetuoso: hay una pausa entre peticiones (`REQUEST_DELAY_SECONDS`).
