"""Tests for offer fingerprints and the SQLite store."""

import sqlite3

from jobscout.models import JobOffer, canonical_url, fingerprint_url
from jobscout.storage import SeenStore

BASE = "https://gt.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-x-ABC123"


def make_offer(url: str) -> JobOffer:
    return JobOffer(title="t", company="c", location="l", url=url, source="computrabajo")


def test_fingerprint_ignores_fragment():
    a = make_offer(BASE + "#lc=ListOffers-Score3-6")
    b = make_offer(BASE + "#lc=ListOffers-Score0-1")
    assert a.fingerprint == b.fingerprint == make_offer(BASE).fingerprint
    assert canonical_url(BASE + "#x") == BASE


def test_mark_and_is_new(tmp_path):
    path = tmp_path / "seen.db"
    with SeenStore(str(path)) as store:
        offer = make_offer(BASE + "#lc=1")
        assert store.is_new(offer.fingerprint)
        store.mark(offer, notified=True)

    with SeenStore(str(path)) as store:
        assert not store.is_new(make_offer(BASE + "#lc=2").fingerprint)

    url, notified = sqlite3.connect(path).execute("SELECT url, notified FROM seen_offers").fetchone()
    assert url == BASE
    assert notified == 1


def test_merges_rows_with_fragment(tmp_path):
    path = tmp_path / "seen.db"
    SeenStore(str(path)).close()  # create the schema
    conn = sqlite3.connect(path)
    conn.executemany(
        "INSERT INTO seen_offers (fingerprint, url, notified, first_seen_at) VALUES (?, ?, ?, ?)",
        [
            # Same offer stored three times with different fragments; one notified.
            ("old1", BASE + "#lc=a", 0, "2026-07-01T00:00:00+00:00"),
            ("old2", BASE + "#lc=b", 1, "2026-07-02T00:00:00+00:00"),
            ("old3", BASE + "#lc=c", 0, "2026-07-03T00:00:00+00:00"),
            ("other", "https://other/offer", 0, "2026-07-01T00:00:00+00:00"),
        ],
    )
    conn.commit()
    conn.close()

    SeenStore(str(path)).close()

    result = sqlite3.connect(path).execute(
        "SELECT fingerprint, url, notified, first_seen_at FROM seen_offers ORDER BY url"
    ).fetchall()
    assert result == [
        (fingerprint_url(BASE), BASE, 1, "2026-07-01T00:00:00+00:00"),
        ("other", "https://other/offer", 0, "2026-07-01T00:00:00+00:00"),
    ]
