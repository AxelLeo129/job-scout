# JobScout 🎯

Agregador de ofertas de empleo con **ranking por IA** y notificaciones por
**Telegram**. Busca ofertas en portales (**Computrabajo**, **Tecoloco**,
**Un Mejor Empleo**, **Trabajos Diarios** y **Acción Trabajo**), las puntúa
contra tu CV usando Claude, y te manda las mejores.

```
Portales ──► Scrapers ──► Dedup ──► Ranking IA (Claude) ──► Telegram
```

---

### 👨‍💻 Colaboradores

<table>
  <tr>
    <td align="center"><a style="color: black" href="https://github.com/AxelLeo129"><img src="https://github.com/AxelLeo129.png" width="100" height="100" alt="Axel Leonardo"><br>Axel Leonardo</a></td>
</table>

---

### 🧰 Tecnologías utilizadas

- Python **3.11**
- Requests + BeautifulSoup4 (scraping)
- Anthropic Claude API (ranking por IA)
- SQLite (historial de ofertas vistas)
- Pydantic (modelos de datos)
- Telegram Bot API (notificaciones)
- Dotenv para variables de entorno (.env)
- Venv (entorno virtual)
- GitHub Actions (ejecución diaria automática)

---

### 🔧 Requisitos previos

Antes de comenzar, asegúrate de tener:

- Python **3.11** o superior
- pip (incluido con Python)
- Una clave de API de [Anthropic](https://console.anthropic.com/) (para el ranking)
- Un bot de Telegram (gratis, vía [@BotFather](https://t.me/BotFather))

---

### 📦 Instalación

Sigue estos pasos para configurar el proyecto localmente:

1. 📥 Clonar repositorio
    ```bash
    git clone https://github.com/AxelLeo129/job-scout
    cd job-scout
    ```

2. 🛠 Crear entorno virtual (venv)
    ```bash
    python -m venv .venv
    ```
3. 🛠 Activar el entorno:
      ▶ Windows (PowerShell)
      ```bash
      .\.venv\Scripts\Activate.ps1
      ```
      ▶ Linux / MacOS
      ```bash
      source .venv/bin/activate
      ```
4. 📥 Instalar dependencias
    ```bash
    pip install -r requirements.txt
    ```
5. ⚙️ Variables de entorno
    Crea un archivo .env en la raíz con el siguiente contenido:
    .env
    ```bash
    # Clave de la API de Anthropic (para el ranking con IA)
    ANTHROPIC_API_KEY=sk-ant-...
    # Bot de Telegram (te lo da @BotFather al crear el bot)
    TELEGRAM_BOT_TOKEN=123456:ABC...
    # Tu chat ID de Telegram (escríbele a @userinfobot y te da tu ID)
    TELEGRAM_CHAT_ID=123456789
    ```
6. 📄 Tu CV en texto plano
    Crea un archivo `cv.txt` en la raíz con el contenido de tu CV (lo lee la
    IA para puntuar las ofertas contra tu perfil).
7. ⚙️ Ajusta `config.py` a tu búsqueda:
    - `SEARCH_KEYWORDS` — los puestos que buscas
    - `COUNTRY` — `gt` para Guatemala (aplica a todos los portales)
    - `ENABLED_SCRAPERS` — qué portales usar (por defecto los 5)
    - `MAX_PAGES_PER_KEYWORD` — páginas de resultados por búsqueda (≈20 ofertas/página)
    - `MIN_SCORE_TO_NOTIFY` — puntaje mínimo (0-100) para notificar
    - `RANKING_MODEL` — modelo de Claude para puntuar (por defecto Haiku: barato y rápido)

---

### ▶️ Uso

```bash
# Prueba sin enviar a Telegram (imprime en consola):
python main.py --dry-run

# Ejecución normal (envía a Telegram):
python main.py

# Si un portal cambió su HTML y no encuentra ofertas, guarda el HTML crudo
# (debug_<portal>_<búsqueda>.html) para revisar los selectores:
python main.py --debug
```

#### Automatizarlo (que corra solo cada día)

Ya viene automatizado con **GitHub Actions** (ver
[Despliegue en producción](#-despliegue-en-producción)). Si prefieres
correrlo local, en Windows puedes usar el **Programador de tareas** para
ejecutar `python main.py` una vez al día.

---

### 📁 Estructura

```
jobscout/
├── main.py                  # orquestador del pipeline
├── config.py                # tus criterios de búsqueda
├── cv.txt                   # tu CV en texto (lo lee la IA)
├── .env                     # claves secretas (NO subir a git)
├── .env.example             # plantilla del .env
├── requirements.txt         # dependencias
├── seen_offers.db           # SQLite: historial de ofertas vistas
├── .github/workflows/
│   └── jobscout.yml         # cron diario en GitHub Actions
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

---

### ➕ Añadir más portales

Crea `jobscout/scrapers/tu_portal.py`, hereda de `BaseScraper`, implementa
`search()` devolviendo `JobOffer`, y regístralo en `jobscout/scrapers/__init__.py`.
El resto del pipeline (ranking, Telegram) funciona sin cambios.

---

### 📝 Notas importantes

- **Computrabajo / Tecoloco / Un Mejor Empleo / Trabajos Diarios / Acción
  Trabajo**: el scraping es viable pero su HTML cambia; por eso los selectores
  son tolerantes y existe el modo `--debug`.
- **Trabajos Diarios** busca por "puesto" (redirige al sinónimo canónico:
  p.ej. "desarrollador" → "programador"); si la palabra clave no existe como
  puesto, no devuelve nada en lugar de traer todo el listado.
- **Acción Trabajo** pagina con scroll infinito, así que solo se lee la
  primera página (~20 ofertas por búsqueda).
- **Ofertas vistas**: todas las ofertas nuevas se guardan en `seen_offers.db`
  (SQLite) tras cada ejecución — con título, empresa, puntaje, si se notificó
  y cuándo se vio — incluso las que no superan el umbral, para no gastar
  tokens re-evaluándolas. Si quieres re-evaluar todo, borra `seen_offers.db`.
  (Si vienes de una versión vieja con `seen_offers.json`, se migra solo.)
- Sé respetuoso: hay una pausa entre peticiones (`REQUEST_DELAY_SECONDS`).

---

### 🚀 Despliegue en producción

JobScout corre **gratis en GitHub Actions**: el workflow
[`.github/workflows/jobscout.yml`](.github/workflows/jobscout.yml) ejecuta el
pipeline todos los días a las **07:00 de Guatemala** (13:00 UTC) y commitea la
base `seen_offers.db` de vuelta al repo para recordar las ofertas ya vistas.

Para activarlo:

1. Ve a **Settings → Secrets and variables → Actions** en el repo y crea
   estos secrets:
   - `ANTHROPIC_API_KEY` — clave de la API de Anthropic
   - `TELEGRAM_BOT_TOKEN` — token del bot de Telegram
   - `TELEGRAM_CHAT_ID` — chat ID a donde notificar
   - `CV_TEXT` — el contenido completo de tu `cv.txt` (el archivo no se sube
     al repo por ser dato personal)
2. Haz push a `main`. El cron queda activo automáticamente.
3. Para probarlo sin esperar al día siguiente: pestaña **Actions** →
   *JobScout diario* → **Run workflow**.

> ⚠️ GitHub desactiva los crons si el repo pasa ~60 días sin actividad;
> como el workflow commitea `seen_offers.db` en cada corrida, esto no debería
> ocurrir mientras haya ofertas nuevas.

---

MIT
Free Software, software to learn!
