"""JobScout — punto de entrada.

Flujo completo:
  1. Buscar ofertas en los portales según las palabras clave (config.py).
  2. Deduplicar y descartar las ya vistas en ejecuciones anteriores.
  3. Leer la página de detalle de las nuevas (en los portales que lo soportan).
  4. Puntuar cada oferta nueva contra el CV usando Claude.
  5. Enviar por Telegram las que superen el puntaje mínimo.

Uso:
    python main.py            # ejecución normal
    python main.py --debug    # guarda el HTML crudo de los portales
    python main.py --dry-run  # no envía a Telegram, solo imprime en consola
"""

from __future__ import annotations

import argparse
import os
import sys
import unicodedata

from dotenv import load_dotenv

import config
from jobscout.models import JobOffer
from jobscout.notifier import TelegramNotifier
from jobscout.ranking import Ranker
from jobscout.scrapers import SCRAPERS
from jobscout.storage import SeenStore


def collect_offers(debug: bool) -> tuple[list[JobOffer], dict[str, int]]:
    """Recorre los portales y devuelve todas las ofertas encontradas, junto
    con cuántas trajo cada portal (para detectar portales rotos)."""
    all_offers: list[JobOffer] = []
    counts: dict[str, int] = {}

    for name in config.ENABLED_SCRAPERS:
        scraper_cls = SCRAPERS.get(name)
        if scraper_cls is None:
            print(f"⚠️  Scraper desconocido en config.ENABLED_SCRAPERS: '{name}' (se omite).")
            continue
        scraper = scraper_cls(
            country=config.COUNTRY,
            request_delay=config.REQUEST_DELAY_SECONDS,
            debug=debug,
        )
        counts[name] = 0
        for keyword in config.SEARCH_KEYWORDS:
            print(f"🔎 Buscando '{keyword}' en {name} ({config.COUNTRY})...")
            found = scraper.search(keyword, max_pages=config.MAX_PAGES_PER_KEYWORD)
            print(f"   {len(found)} ofertas encontradas.")
            all_offers.extend(found)
            counts[name] += len(found)

    return all_offers, counts


def empty_portal_alerts(store: SeenStore, counts: dict[str, int]) -> list[str]:
    """Registra las ofertas por portal y devuelve los avisos de portales que
    llevan PORTAL_ALERT_AFTER_EMPTY_RUNS ejecuciones seguidas sin ofertas
    (repitiendo el aviso cada 7 ejecuciones mientras sigan vacíos)."""
    store.record_portal_runs(counts)
    threshold = config.PORTAL_ALERT_AFTER_EMPTY_RUNS
    if threshold <= 0:
        return []

    alerts: list[str] = []
    for name in counts:
        streak = store.empty_streak(name)
        if streak >= threshold and (streak - threshold) % 7 == 0:
            alerts.append(
                f"⚠️ <b>{name}</b> lleva {streak} ejecuciones seguidas sin devolver "
                "ofertas. Puede que haya cambiado su HTML o que esté bloqueando "
                "las peticiones; revisa los selectores del scraper."
            )
    return alerts


def deduplicate(offers: list[JobOffer]) -> list[JobOffer]:
    """Elimina ofertas repetidas dentro de esta misma ejecución (por URL)."""
    seen_fps: set[str] = set()
    unique: list[JobOffer] = []
    for offer in offers:
        if offer.fingerprint not in seen_fps:
            seen_fps.add(offer.fingerprint)
            unique.append(offer)
    return unique


def _normalize(text: str) -> str:
    """Pasa a minúsculas y quita acentos, para comparar términos sin tildes."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def excluded_term(offer: JobOffer) -> str | None:
    """Devuelve el término de config.EXCLUDE_TERMS que contiene la oferta
    (en empresa, título y, si se configura, descripción), o None."""
    fields = [offer.company, offer.title]
    if config.EXCLUDE_SEARCH_DESCRIPTION:
        fields.append(offer.description)
    haystack = _normalize(" ".join(fields))
    for term in config.EXCLUDE_TERMS:
        if _normalize(term) in haystack:
            return term
    return None


def filter_excluded(offers: list[JobOffer]) -> list[JobOffer]:
    """Descarta las ofertas que contengan algún término de config.EXCLUDE_TERMS
    (comparación sin mayúsculas ni acentos)."""
    kept = [o for o in offers if excluded_term(o) is None]
    dropped = len(offers) - len(kept)
    if dropped:
        print(f"🚫 {dropped} ofertas descartadas por términos excluidos.")
    return kept


def fetch_details(offers: list[JobOffer], debug: bool) -> None:
    """Completa cada oferta con su página de detalle, en los portales que lo
    implementan. Si falla, la oferta sigue con los datos del listado."""
    scrapers = {}
    for offer in offers:
        if offer.source not in scrapers:
            scraper_cls = SCRAPERS.get(offer.source)
            scrapers[offer.source] = scraper_cls and scraper_cls(
                country=config.COUNTRY,
                request_delay=config.REQUEST_DELAY_SECONDS,
                debug=debug,
            )
        scraper = scrapers[offer.source]
        if scraper is None:
            continue
        try:
            scraper.fetch_details(offer)
        except Exception as exc:  # noqa: BLE001 - seguimos con los datos del listado
            print(f"  [{offer.source}] Error leyendo el detalle de '{offer.title}': {exc}")


def load_cv() -> str:
    """Carga el texto del CV desde el archivo configurado."""
    if not os.path.exists(config.CV_PATH):
        sys.exit(f"❌ No se encontró el CV en '{config.CV_PATH}'. Crea ese archivo.")
    with open(config.CV_PATH, "r", encoding="utf-8") as fh:
        return fh.read()


def main() -> None:
    parser = argparse.ArgumentParser(description="JobScout: agregador de empleos con ranking IA.")
    parser.add_argument("--debug", action="store_true", help="Guarda el HTML crudo de los portales.")
    parser.add_argument("--dry-run", action="store_true", help="No envía a Telegram; imprime en consola.")
    args = parser.parse_args()

    load_dotenv()

    # Validación temprana de credenciales (salvo en dry-run, que no usa Telegram).
    if not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit("❌ Falta ANTHROPIC_API_KEY en el .env (necesaria para el ranking).")
    if not args.dry_run and not (os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID")):
        sys.exit("❌ Faltan TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID en el .env (o usa --dry-run).")

    notifier = None
    if not args.dry_run:
        notifier = TelegramNotifier(
            bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
            chat_id=os.environ["TELEGRAM_CHAT_ID"],
        )

    # 1. Recolectar y deduplicar.
    found, counts = collect_offers(debug=args.debug)
    offers = deduplicate(found)
    print(f"\n📦 {len(offers)} ofertas únicas en total.")

    store = SeenStore(config.SEEN_DB_PATH, legacy_json_path=config.LEGACY_SEEN_JSON_PATH)

    # Avisar de portales que llevan varias ejecuciones sin ofertas. Va antes
    # de cualquier salida temprana para que el aviso llegue aunque no haya
    # nada nuevo que evaluar.
    for alert in empty_portal_alerts(store, counts):
        print(alert.replace("<b>", "").replace("</b>", ""))
        if notifier is not None:
            try:
                notifier.send(alert)
            except Exception as exc:  # noqa: BLE001
                print(f"    ⚠️  Error enviando a Telegram: {exc}")

    # 2. Descartar sectores/empresas vetados (banca, Genesis Empresarial, etc.).
    offers = filter_excluded(offers)

    # 3. Filtrar las ya vistas.
    new_offers = [o for o in offers if store.is_new(o.fingerprint)]
    print(f"🆕 {len(new_offers)} ofertas nuevas (no vistas antes).")

    if not new_offers:
        print("Nada nuevo que evaluar. ¡Hasta la próxima!")
        store.save()
        return

    # 4. Completar las nuevas con su página de detalle (descripción completa)
    #    y volver a aplicar las exclusiones, ahora con más texto. Las que caen
    #    aquí se guardan como vistas para no bajar su detalle cada día.
    print(f"\n📄 Leyendo el detalle de {len(new_offers)} ofertas nuevas...")
    fetch_details(new_offers, debug=args.debug)
    still_new: list[JobOffer] = []
    for offer in new_offers:
        term = excluded_term(offer)
        if term is None:
            still_new.append(offer)
        else:
            offer.score_reason = f"Descartada por término excluido: '{term}'."
            store.mark(offer)
    if len(still_new) < len(new_offers):
        print(f"🚫 {len(new_offers) - len(still_new)} ofertas descartadas tras leer el detalle.")
    new_offers = still_new

    if not new_offers:
        print("Nada nuevo que evaluar. ¡Hasta la próxima!")
        store.save()
        return

    # 5. Puntuar con IA.
    print(f"\n🤖 Puntuando {len(new_offers)} ofertas con {config.RANKING_MODEL}...")
    ranker = Ranker(
        cv_text=load_cv(),
        model=config.RANKING_MODEL,
        preferred_modalities=config.PREFERRED_MODALITIES,
    )
    ranked = ranker.rank_all(new_offers)
    failed = len(new_offers) - len(ranked)
    if failed:
        print(f"⚠️  {failed} ofertas no se pudieron puntuar; se reintentarán la próxima vez.")

    # Ordenar de mayor a menor puntaje.
    ranked.sort(key=lambda o: o.score, reverse=True)

    # 6. Notificar las que superen el umbral.
    to_notify = [o for o in ranked if o.score >= config.MIN_SCORE_TO_NOTIFY]
    print(f"\n📨 {len(to_notify)} ofertas superan el umbral ({config.MIN_SCORE_TO_NOTIFY}).")

    sent: set[str] = set()
    send_failed: set[str] = set()
    for offer in to_notify:
        print(f"  [{offer.score}] {offer.title} — {offer.company}")
        if notifier is not None:
            try:
                notifier.send_offer(offer)
                sent.add(offer.fingerprint)
            except Exception as exc:  # noqa: BLE001
                print(f"    ⚠️  Error enviando a Telegram: {exc}")
                send_failed.add(offer.fingerprint)

    # 7. Marcar como vistas las puntuadas (incluso las que no superaron el
    #    umbral, para no re-evaluarlas y gastar tokens en cada ejecución).
    #    Las que fallaron al puntuar o al enviar no se marcan: se reintentan.
    for offer in ranked:
        if offer.fingerprint not in send_failed:
            store.mark(offer, notified=offer.fingerprint in sent)
    store.save()

    print("\n✅ Listo.")


if __name__ == "__main__":
    main()
