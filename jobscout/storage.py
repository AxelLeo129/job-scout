"""Base SQLite con las ofertas procesadas y estadísticas por portal.

``seen_offers`` guarda cada oferta puntuada (puntaje, razón, si se notificó)
para no puntuarla ni notificarla dos veces. ``portal_runs`` guarda cuántas
ofertas devolvió cada portal en cada ejecución, para detectar portales que
dejan de funcionar sin dar error.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from types import TracebackType

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
);
CREATE TABLE IF NOT EXISTS portal_runs (
    source  TEXT NOT NULL,
    run_at  TEXT NOT NULL,
    offers  INTEGER NOT NULL
);
"""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SeenStore:
    """Registro persistente de ofertas procesadas.

    Se usa como context manager: al salir confirma los cambios y cierra la
    conexión. Al abrirse aplica las migraciones pendientes (JSON antiguo,
    URLs con fragmento).
    """

    def __init__(self, path: str, legacy_json_path: str | None = None):
        self.path = path
        self._conn = sqlite3.connect(path)
        self._conn.executescript(_SCHEMA)
        if legacy_json_path:
            self._migrate_legacy_json(legacy_json_path)
        self._canonicalize_urls()
        self._seen: set[str] = {
            row[0] for row in self._conn.execute("SELECT fingerprint FROM seen_offers")
        }

    def __enter__(self) -> SeenStore:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def is_new(self, fingerprint: str) -> bool:
        """Indica si no hay ninguna oferta guardada con ``fingerprint``."""
        return fingerprint not in self._seen

    def mark(self, offer: JobOffer, notified: bool = False) -> None:
        """Guarda ``offer`` como procesada. Si la huella ya existe, no la modifica."""
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

    def record_portal_runs(self, counts: dict[str, int]) -> None:
        """Guarda cuántas ofertas devolvió cada portal en esta ejecución."""
        now = _utcnow()
        self._conn.executemany(
            "INSERT INTO portal_runs (source, run_at, offers) VALUES (?, ?, ?)",
            [(source, now, n) for source, n in counts.items()],
        )
        self._conn.commit()

    def empty_streak(self, source: str) -> int:
        """Cantidad de ejecuciones recientes seguidas en que ``source`` devolvió 0 ofertas."""
        streak = 0
        for (offers,) in self._conn.execute(
            "SELECT offers FROM portal_runs WHERE source = ? ORDER BY run_at DESC, rowid DESC",
            (source,),
        ):
            if offers:
                break
            streak += 1
        return streak

    def close(self) -> None:
        """Confirma los cambios pendientes y cierra la conexión."""
        self._conn.commit()
        self._conn.close()

    def _migrate_legacy_json(self, json_path: str) -> None:
        """Importa las huellas del antiguo seen_offers.json y lo renombra a *.migrated."""
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
        """Fusiona las filas guardadas con URL con fragmento en una fila por oferta.

        Antes la huella incluía el fragmento de la URL, así que la misma oferta
        de Computrabajo quedó guardada varias veces. La fila resultante conserva
        el ``first_seen_at`` más antiguo y ``notified=1`` si algún duplicado lo tenía.
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
        # SQLite no achica el archivo al borrar filas.
        self._conn.execute("VACUUM")
        print(f"🧹 Normalizadas {len(rows)} URLs con fragmento en '{self.path}'.")
