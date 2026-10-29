"""Tests de la huella de las ofertas y de la base de ofertas vistas."""

import sqlite3

from jobscout.models import JobOffer, canonical_url, fingerprint_url
from jobscout.storage import SeenStore

BASE = "https://gt.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-x-ABC123"


def offer(url: str) -> JobOffer:
    return JobOffer(title="t", company="c", location="l", url=url, source="computrabajo")


def test_huella_ignora_fragmento():
    a = offer(BASE + "#lc=ListOffers-Score3-6")
    b = offer(BASE + "#lc=ListOffers-Score0-1")
    assert a.fingerprint == b.fingerprint == offer(BASE).fingerprint
    assert canonical_url(BASE + "#x") == BASE


def test_mark_y_is_new(tmp_path):
    path = tmp_path / "seen.db"
    store = SeenStore(str(path))
    o = offer(BASE + "#lc=1")
    assert store.is_new(o.fingerprint)
    store.mark(o, notified=True)
    store.save()

    store = SeenStore(str(path))
    assert not store.is_new(offer(BASE + "#lc=2").fingerprint)
    store.save()
    url, notified = sqlite3.connect(path).execute(
        "SELECT url, notified FROM seen_offers"
    ).fetchone()
    assert url == BASE  # se guarda sin fragmento
    assert notified == 1


def test_migra_filas_con_fragmento(tmp_path):
    """Las filas viejas (huella con #) se fusionan en una por oferta."""
    path = tmp_path / "seen.db"
    SeenStore(str(path)).save()  # crea el esquema
    conn = sqlite3.connect(path)
    conn.executemany(
        "INSERT INTO seen_offers (fingerprint, url, notified, first_seen_at) VALUES (?, ?, ?, ?)",
        [
            # misma oferta vista 3 veces con distinto fragmento; una notificada
            ("old1", BASE + "#lc=a", 0, "2026-07-01T00:00:00+00:00"),
            ("old2", BASE + "#lc=b", 1, "2026-07-02T00:00:00+00:00"),
            ("old3", BASE + "#lc=c", 0, "2026-07-03T00:00:00+00:00"),
            ("other", "https://otra/oferta", 0, "2026-07-01T00:00:00+00:00"),
        ],
    )
    conn.commit()
    conn.close()

    SeenStore(str(path)).save()

    result = sqlite3.connect(path).execute(
        "SELECT fingerprint, url, notified, first_seen_at FROM seen_offers ORDER BY url"
    ).fetchall()
    assert result == [
        (fingerprint_url(BASE), BASE, 1, "2026-07-01T00:00:00+00:00"),
        ("other", "https://otra/oferta", 0, "2026-07-01T00:00:00+00:00"),
    ]
