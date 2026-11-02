"""Tests for the main.py pipeline with boards, Claude and Telegram mocked."""

import sqlite3

import pytest

import config
import main
from jobscout import notifier, ranking
from jobscout.models import JobOffer
from jobscout.storage import SeenStore


def make_offer(title: str, company: str = "c", description: str = "") -> JobOffer:
    return JobOffer(
        title=title,
        company=company,
        location="l",
        url=f"https://x/{title}#lc=1",
        source="computrabajo",
        description=description,
    )


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolated config and credentials; no network. Returns the DB path."""
    cv = tmp_path / "cv.txt"
    cv.write_text("cv", encoding="utf-8")
    db = tmp_path / "seen.db"
    monkeypatch.setattr(config, "SEEN_DB_PATH", str(db))
    monkeypatch.setattr(config, "CV_PATH", str(cv))
    monkeypatch.setattr(config, "LEGACY_SEEN_JSON_PATH", str(tmp_path / "missing.json"))
    monkeypatch.setattr(config, "MIN_SCORE_TO_NOTIFY", 60)
    monkeypatch.setattr(config, "EXCLUDE_TERMS", [])
    for var in ("ANTHROPIC_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.setenv(var, "x")
    monkeypatch.setattr("sys.argv", ["main.py"])
    monkeypatch.setattr(main, "load_dotenv", lambda: None)
    monkeypatch.setattr(ranking.Ranker, "__init__", lambda self, **kw: None)
    monkeypatch.setattr(main, "fetch_details", lambda offers, debug: None)
    return db


def test_failures_are_not_marked_as_seen(env, monkeypatch):
    offers = [make_offer("ok_high"), make_offer("ok_low"), make_offer("ai_fails"), make_offer("tg_fails")]
    # Same offer again (same URL once the fragment is stripped).
    monkeypatch.setattr(
        main, "collect_offers", lambda debug: (offers + [make_offer("ok_high")], {"computrabajo": 5})
    )

    def rank(self, offer):
        if offer.title == "ai_fails":
            raise RuntimeError("no credit")
        return ranking.RankResult(score=10 if offer.title == "ok_low" else 150, reason="r")

    sent = []

    def send_offer(self, offer):
        if offer.title == "tg_fails":
            raise RuntimeError("Telegram 429")
        sent.append(offer.title)

    monkeypatch.setattr(ranking.Ranker, "rank", rank)
    monkeypatch.setattr(notifier.TelegramNotifier, "send_offer", send_offer)

    main.main()

    rows = sqlite3.connect(env).execute(
        "SELECT title, score, notified FROM seen_offers ORDER BY title"
    ).fetchall()
    assert sent == ["ok_high"]
    # ai_fails and tg_fails are retried next run; the score is clamped to 100.
    assert rows == [("ok_high", 100, 1), ("ok_low", 10, 0)]


def test_alerts_on_empty_portal(env, monkeypatch):
    """Alert on the 3rd consecutive empty run, then every 7 runs."""
    monkeypatch.setattr(config, "PORTAL_ALERT_AFTER_EMPTY_RUNS", 3)
    monkeypatch.setattr(main, "collect_offers", lambda debug: ([], {"tecoloco": 0, "computrabajo": 4}))
    alerts = []
    monkeypatch.setattr(notifier.TelegramNotifier, "send", lambda self, text: alerts.append(text))

    alerts_per_run = []
    for _ in range(11):
        main.main()  # nothing new: returns early but still alerts
        alerts_per_run.append(len(alerts))
        alerts.clear()

    assert alerts_per_run == [0, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0]


def test_empty_streak_resets_with_offers(tmp_path):
    with SeenStore(str(tmp_path / "seen.db")) as store:
        for n in (0, 0, 7, 0, 0):
            store.record_portal_runs({"tecoloco": n})
        assert store.empty_streak("tecoloco") == 2
        assert store.empty_streak("unknown") == 0


def test_exclusion_after_details(env, monkeypatch):
    """An offer whose term only appears in its details is not scored and is stored as seen."""
    monkeypatch.setattr(config, "EXCLUDE_TERMS", ["banco"])
    monkeypatch.setattr(config, "EXCLUDE_SEARCH_DESCRIPTION", True)
    monkeypatch.setattr(
        main,
        "collect_offers",
        lambda debug: ([make_offer("dev_client_x"), make_offer("dev_ok")], {"computrabajo": 2}),
    )

    def fetch_details(offers, debug):
        for offer in offers:
            offer.description = "Cliente: Banco Industrial" if offer.title == "dev_client_x" else "SaaS"

    scored = []

    def rank(self, offer):
        scored.append(offer.title)
        return ranking.RankResult(score=10, reason="r")

    monkeypatch.setattr(main, "fetch_details", fetch_details)
    monkeypatch.setattr(ranking.Ranker, "rank", rank)

    main.main()

    assert scored == ["dev_ok"]
    rows = sqlite3.connect(env).execute(
        "SELECT title, score_reason FROM seen_offers ORDER BY title"
    ).fetchall()
    assert rows == [("dev_client_x", "Descartada por término excluido: 'banco'."), ("dev_ok", "r")]


@pytest.mark.parametrize(
    "search_description, expected",
    [(True, ["Frontend"]), (False, ["Programador", "Frontend"])],
)
def test_filter_excluded(monkeypatch, search_description, expected):
    monkeypatch.setattr(config, "EXCLUDE_TERMS", ["banco", "genesis empresarial"])
    monkeypatch.setattr(config, "EXCLUDE_SEARCH_DESCRIPTION", search_description)
    offers = [
        make_offer("Dev", company="Génesis Empresarial"),
        make_offer("Programador", description="Para BANCO grande"),
        make_offer("Frontend"),
    ]
    assert [o.title for o in main.filter_excluded(offers)] == expected
