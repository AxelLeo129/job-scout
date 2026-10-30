"""Tests del flujo de main.py, sin red: scrapers, Claude y Telegram simulados."""

import sqlite3

import pytest

import config
import main
from jobscout import notifier, ranking
from jobscout.models import JobOffer


def offer(title: str, company: str = "c", description: str = "") -> JobOffer:
    return JobOffer(
        title=title,
        company=company,
        location="l",
        url=f"https://x/{title}#lc=1",
        source="computrabajo",
        description=description,
    )


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    cv = tmp_path / "cv.txt"
    cv.write_text("cv", encoding="utf-8")
    db = tmp_path / "seen.db"
    monkeypatch.setattr(config, "SEEN_DB_PATH", str(db))
    monkeypatch.setattr(config, "CV_PATH", str(cv))
    monkeypatch.setattr(config, "LEGACY_SEEN_JSON_PATH", str(tmp_path / "no.json"))
    monkeypatch.setattr(config, "MIN_SCORE_TO_NOTIFY", 60)
    monkeypatch.setattr(config, "EXCLUDE_TERMS", [])
    for var in ("ANTHROPIC_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.setenv(var, "x")
    monkeypatch.setattr("sys.argv", ["main.py"])
    monkeypatch.setattr(main, "load_dotenv", lambda: None)
    monkeypatch.setattr(ranking.Ranker, "__init__", lambda self, **kw: None)
    return db


def test_fallos_no_se_marcan_como_vistos(entorno, monkeypatch):
    offers = [offer("ok_alto"), offer("ok_bajo"), offer("falla_ia"), offer("falla_tg")]
    # La misma oferta con otro fragmento cuenta una sola vez.
    monkeypatch.setattr(
        main, "collect_offers", lambda debug: (offers + [offer("ok_alto")], {"computrabajo": 5})
    )

    def rank(self, o):
        if o.title == "falla_ia":
            raise RuntimeError("sin saldo")
        return ranking.RankResult(score=10 if o.title == "ok_bajo" else 150, reason="r")

    enviados = []

    def send_offer(self, o):
        if o.title == "falla_tg":
            raise RuntimeError("Telegram 429")
        enviados.append(o.title)

    monkeypatch.setattr(ranking.Ranker, "rank", rank)
    monkeypatch.setattr(notifier.TelegramNotifier, "send_offer", send_offer)

    main.main()

    rows = sqlite3.connect(entorno).execute(
        "SELECT title, score, notified FROM seen_offers ORDER BY title"
    ).fetchall()
    assert enviados == ["ok_alto"]
    # falla_ia y falla_tg no se guardan: se reintentan la próxima vez.
    # El puntaje se limita a 100.
    assert rows == [("ok_alto", 100, 1), ("ok_bajo", 10, 0)]


def test_avisa_portal_vacio(entorno, monkeypatch):
    """Tras 3 ejecuciones seguidas sin ofertas se avisa, y luego cada 7."""
    monkeypatch.setattr(config, "PORTAL_ALERT_AFTER_EMPTY_RUNS", 3)
    monkeypatch.setattr(
        main, "collect_offers", lambda debug: ([], {"tecoloco": 0, "computrabajo": 4})
    )
    avisos = []
    monkeypatch.setattr(notifier.TelegramNotifier, "send", lambda self, text: avisos.append(text))

    por_ejecucion = []
    for _ in range(11):
        main.main()  # sin ofertas nuevas: sale temprano, pero igual avisa
        por_ejecucion.append(len(avisos))
        avisos.clear()

    # Avisa en la ejecución 3 y en la 10; computrabajo nunca.
    assert por_ejecucion == [0, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0]


def test_racha_se_corta_con_ofertas(tmp_path):
    from jobscout.storage import SeenStore

    store = SeenStore(str(tmp_path / "seen.db"))
    for n in (0, 0, 7, 0, 0):
        store.record_portal_runs({"tecoloco": n})
    assert store.empty_streak("tecoloco") == 2
    assert store.empty_streak("desconocido") == 0
    store.save()


def test_filtro_de_exclusion(monkeypatch):
    monkeypatch.setattr(config, "EXCLUDE_TERMS", ["banco", "genesis empresarial"])
    offers = [
        offer("Dev", company="Génesis Empresarial"),
        offer("Programador", description="Para BANCO grande"),
        offer("Frontend"),
    ]
    assert [o.title for o in main.filter_excluded(offers)] == ["Frontend"]
