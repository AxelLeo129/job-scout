"""Memoria de ofertas ya vistas.

Guarda las ofertas ya procesadas en una base SQLite, con su puntaje y
metadatos, para no volver a evaluarlas ni notificarlas en ejecuciones
posteriores. Además de evitar repetidos, la base sirve como historial
consultable (qué se vio, cuándo, qué puntaje sacó y si se notificó).

Si existe el antiguo seen_offers.json (solo huellas), sus datos se migran
automáticamente la primera vez y el archivo se renombra a *.migrated.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone

from .models import JobOffer, canonical_url, fingerprint_url

_SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_offers (
    fingerprint   TEXT PRIMARY KEY,
    title         TEXT NOT NULL DEFAULT '',
    company       TEXT NOT NULL DEFAULT '',
    location      TEXT NOT NULL DEFAULT '',
    url           TEXT NOT NULL DEFAULT '',
    source        TEXT NOT NULL DEFAULT '',
    salary        TEXT NOT NULL DEFAULT '',
    score         INTEGER NOT NULL DEFAULT 0,
    score_reason  TEXT NOT NULL DEFAULT '',
    notified      INTEGER NOT NULL DEFAULT 0,
    first_seen_at TEXT NOT NULL
)
"""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SeenStore:
    """Registro persistente (SQLite) de ofertas ya procesadas."""

    def __init__(self, path: str, legacy_json_path: str | None = None):
        self.path = path
        self._conn = sqlite3.connect(path)
        self._conn.execute(_SCHEMA)
        self._conn.commit()
        if legacy_json_path:
            self._migrate_legacy_json(legacy_json_path)
        self._canonicalize_urls()
        self._seen: set[str] = {
            row[0] for row in self._conn.execute("SELECT fingerprint FROM seen_offers")
        }

    def _migrate_legacy_json(self, json_path: str) -> None:
        """Importa las huellas del viejo seen_offers.json (una sola vez)."""
        if not os.path.exists(json_path):
            return
        try:
            with open(json_path, "r", encoding="utf-8") as fh:
                fingerprints = json.load(fh)
        except (json.JSONDecodeError, OSError):
            return
        now = _utcnow()
        self._conn.executemany(
            "INSERT OR IGNORE INTO seen_offers (fingerprint, first_seen_at) VALUES (?, ?)",
            [(fp, now) for fp in fingerprints],
        )
        self._conn.commit()
        os.replace(json_path, json_path + ".migrated")
        print(f"📦 Migradas {len(fingerprints)} huellas de '{json_path}' a '{self.path}'.")

    def _canonicalize_urls(self) -> None:
        """Fusiona las filas guardadas con URL con fragmento (#...).

        Antes la huella incluía el fragmento, así que la misma oferta de
        Computrabajo quedó guardada varias veces. Se deja una fila por URL
        canónica, con la fecha más antigua y notified=1 si alguna lo tenía.
        """
        rows = self._conn.execute(
            "SELECT fingerprint, url, notified, first_seen_at FROM seen_offers "
            "WHERE url LIKE '%#%' ORDER BY first_seen_at"
        ).fetchall()
        if not rows:
            return
        for old_fp, url, notified, first_seen_at in rows:
            new_fp = fingerprint_url(url)
            existing = self._conn.execute(
                "SELECT notified, first_seen_at FROM seen_offers WHERE fingerprint = ?",
                (new_fp,),
            ).fetchone()
            if existing is None:
                self._conn.execute(
                    "UPDATE seen_offers SET fingerprint = ?, url = ? WHERE fingerprint = ?",
                    (new_fp, canonical_url(url), old_fp),
                )
            else:
                self._conn.execute(
                    "UPDATE seen_offers SET notified = ?, first_seen_at = ? WHERE fingerprint = ?",
                    (max(notified, existing[0]), min(first_seen_at, existing[1]), new_fp),
                )
                self._conn.execute("DELETE FROM seen_offers WHERE fingerprint = ?", (old_fp,))
        self._conn.commit()
        print(f"🧹 Normalizadas {len(rows)} URLs con fragmento en '{self.path}'.")

    def is_new(self, fingerprint: str) -> bool:
        """Devuelve True si la oferta no se había visto antes."""
        return fingerprint not in self._seen

    def mark(self, offer: JobOffer, notified: bool = False) -> None:
        """Registra una oferta como vista, con sus datos y puntaje."""
        self._conn.execute(
            """
            INSERT OR IGNORE INTO seen_offers
                (fingerprint, title, company, location, url, source, salary,
                 score, score_reason, notified, first_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                offer.fingerprint,
                offer.title,
                offer.company,
                offer.location,
                canonical_url(offer.url),
                offer.source,
                offer.salary,
                offer.score,
                offer.score_reason,
                int(notified),
                _utcnow(),
            ),
        )
        self._seen.add(offer.fingerprint)

    def save(self) -> None:
        """Confirma los cambios y cierra la conexión."""
        self._conn.commit()
        self._conn.close()
