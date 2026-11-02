"""JobScout — punto de entrada.

Flujo:
  1. Buscar en cada portal activo cada palabra clave (config.py).
  2. Deduplicar y descartar empresas/títulos excluidos y ofertas ya vistas.
  3. Completar las nuevas con su página de detalle (portales que lo soportan).
  4. Puntuar las nuevas contra el CV con Claude.
  5. Enviar a Telegram las que superan el umbral y guardar todas las puntuadas.

Uso:
    python main.py            # ejecución normal
    python main.py --debug    # además guarda el HTML crudo de los portales
    python main.py --dry-run  # imprime en vez de enviar a Telegram
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
from jobscout.scrapers import SCRAPERS, BaseScraper
from jobscout.storage import SeenStore

# Mientras un portal siga vacío, el aviso se repite cada esta cantidad de ejecuciones.
EMPTY_PORTAL_ALERT_REPEAT_RUNS = 7


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="JobScout: agregador de empleos con ranking IA.")
    parser.add_argument("--debug", action="store_true", help="Guarda el HTML crudo de los portales.")
    parser.add_argument("--dry-run", action="store_true", help="No envía a Telegram; imprime en consola.")
    return parser.parse_args()


def check_credentials(dry_run: bool) -> None:
    """Termina la ejecución si faltan las variables de entorno necesarias."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit("❌ Falta ANTHROPIC_API_KEY en el .env (necesaria para el ranking).")
    if not dry_run and not (os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID")):
        sys.exit("❌ Faltan TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID en el .env (o usa --dry-run).")


def build_scraper(name: str, debug: bool) -> BaseScraper | None:
    """Crea el scraper registrado como ``name``, o None si no existe."""
    scraper_cls = SCRAPERS.get(name)
    if scraper_cls is None:
        return None
    return scraper_cls(country=config.COUNTRY, request_delay=config.REQUEST_DELAY_SECONDS, debug=debug)


def collect_offers(debug: bool) -> tuple[list[JobOffer], dict[str, int]]:
    """Busca cada palabra clave en cada portal activo.

    Returns:
        Todas las ofertas encontradas (puede haber repetidas) y cuántas
        devolvió cada portal.
    """
    offers: list[JobOffer] = []
    counts: dict[str, int] = {}

    for name in config.ENABLED_SCRAPERS:
        scraper = build_scraper(name, debug)
        if scraper is None:
            print(f"⚠️  Scraper desconocido en config.ENABLED_SCRAPERS: '{name}' (se omite).")
            continue
        counts[name] = 0
        for keyword in config.SEARCH_KEYWORDS:
            print(f"🔎 Buscando '{keyword}' en {name} ({config.COUNTRY})...")
            found = scraper.search(keyword, max_pages=config.MAX_PAGES_PER_KEYWORD)
            print(f"   {len(found)} ofertas encontradas.")
            offers.extend(found)
            counts[name] += len(found)

    return offers, counts


def deduplicate(offers: list[JobOffer]) -> list[JobOffer]:
    """Quita las ofertas con huella repetida, conservando la primera aparición."""
    unique: dict[str, JobOffer] = {}
    for offer in offers:
        unique.setdefault(offer.fingerprint, offer)
    return list(unique.values())


def report_empty_portals(
    store: SeenStore, counts: dict[str, int], notifier: TelegramNotifier | None
) -> None:
    """Registra las ofertas por portal de esta ejecución y avisa de los que siguen vacíos.

    Se avisa cuando un portal llega a ``config.PORTAL_ALERT_AFTER_EMPTY_RUNS``
    ejecuciones seguidas sin ofertas y luego cada EMPTY_PORTAL_ALERT_REPEAT_RUNS.
    """
    store.record_portal_runs(counts)
    threshold = config.PORTAL_ALERT_AFTER_EMPTY_RUNS
    if threshold <= 0:
        return

    for name in counts:
        streak = store.empty_streak(name)
        if streak < threshold or (streak - threshold) % EMPTY_PORTAL_ALERT_REPEAT_RUNS:
            continue
        print(f"⚠️  {name} lleva {streak} ejecuciones seguidas sin devolver ofertas.")
        if notifier is None:
            continue
        try:
            notifier.send(
                f"⚠️ <b>{name}</b> lleva {streak} ejecuciones seguidas sin devolver "
                "ofertas. Puede que haya cambiado su HTML o que esté bloqueando "
                "las peticiones; revisa los selectores del scraper."
            )
        except Exception as exc:  # noqa: BLE001 - un aviso no debe detener la ejecución
            print(f"    ⚠️  Error enviando a Telegram: {exc}")


def _normalize(text: str) -> str:
    """Pasa a minúsculas y quita acentos."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def excluded_term(offer: JobOffer) -> str | None:
    """Primer término de ``config.EXCLUDE_TERMS`` que contiene la oferta, o None.

    Busca en empresa y título, y también en la descripción si
    ``config.EXCLUDE_SEARCH_DESCRIPTION`` está activo; ignora mayúsculas y acentos.
    """
    fields = [offer.company, offer.title]
    if config.EXCLUDE_SEARCH_DESCRIPTION:
        fields.append(offer.description)
    haystack = _normalize(" ".join(fields))
    return next((term for term in config.EXCLUDE_TERMS if _normalize(term) in haystack), None)


def filter_excluded(offers: list[JobOffer]) -> list[JobOffer]:
    """Descarta las ofertas que coinciden con ``config.EXCLUDE_TERMS``."""
    kept = [o for o in offers if excluded_term(o) is None]
    if dropped := len(offers) - len(kept):
        print(f"🚫 {dropped} ofertas descartadas por términos excluidos.")
    return kept


def fetch_details(offers: list[JobOffer], debug: bool) -> None:
    """Completa las ofertas con su página de detalle.

    Si la página de detalle falla, la oferta conserva los datos del listado.
    """
    scrapers: dict[str, BaseScraper | None] = {}
    for offer in offers:
        if offer.source not in scrapers:
            scrapers[offer.source] = build_scraper(offer.source, debug)
        scraper = scrapers[offer.source]
        if scraper is None:
            continue
        try:
            scraper.fetch_details(offer)
        except Exception as exc:  # noqa: BLE001 - se sigue con los datos del listado
            print(f"  [{offer.source}] Error leyendo el detalle de '{offer.title}': {exc}")


def drop_excluded_after_details(offers: list[JobOffer], store: SeenStore) -> list[JobOffer]:
    """Vuelve a aplicar las exclusiones tras completar el detalle.

    Las ofertas que solo se excluyen ahora se guardan como vistas, para no
    volver a bajar su página de detalle en cada ejecución.
    """
    kept: list[JobOffer] = []
    for offer in offers:
        term = excluded_term(offer)
        if term is None:
            kept.append(offer)
            continue
        offer.score_reason = f"Descartada por término excluido: '{term}'."
        store.mark(offer)
    if dropped := len(offers) - len(kept):
        print(f"🚫 {dropped} ofertas descartadas tras leer el detalle.")
    return kept


def load_cv() -> str:
    """Lee el CV de ``config.CV_PATH``; termina la ejecución si no existe."""
    if not os.path.exists(config.CV_PATH):
        sys.exit(f"❌ No se encontró el CV en '{config.CV_PATH}'. Crea ese archivo.")
    with open(config.CV_PATH, "r", encoding="utf-8") as fh:
        return fh.read()


def rank_offers(offers: list[JobOffer]) -> list[JobOffer]:
    """Puntúa las ofertas con Claude; devuelve las puntuadas, de mayor a menor puntaje."""
    print(f"\n🤖 Puntuando {len(offers)} ofertas con {config.RANKING_MODEL}...")
    ranker = Ranker(
        cv_text=load_cv(),
        model=config.RANKING_MODEL,
        preferred_modalities=config.PREFERRED_MODALITIES,
    )
    ranked = ranker.rank_all(offers)
    if failed := len(offers) - len(ranked):
        print(f"⚠️  {failed} ofertas no se pudieron puntuar; se reintentarán la próxima vez.")
    return sorted(ranked, key=lambda o: o.score, reverse=True)


def notify(offers: list[JobOffer], notifier: TelegramNotifier | None) -> tuple[set[str], set[str]]:
    """Envía a Telegram las ofertas con puntaje >= ``config.MIN_SCORE_TO_NOTIFY``.

    Returns:
        Huellas de las ofertas enviadas y de las que fallaron al enviarse. Sin
        notifier (dry run) las ofertas solo se imprimen.
    """
    to_notify = [o for o in offers if o.score >= config.MIN_SCORE_TO_NOTIFY]
    print(f"\n📨 {len(to_notify)} ofertas superan el umbral ({config.MIN_SCORE_TO_NOTIFY}).")

    sent: set[str] = set()
    failed: set[str] = set()
    for offer in to_notify:
        print(f"  [{offer.score}] {offer.title} — {offer.company}")
        if notifier is None:
            continue
        try:
            notifier.send_offer(offer)
            sent.add(offer.fingerprint)
        except Exception as exc:  # noqa: BLE001 - se reintenta en la próxima ejecución
            print(f"    ⚠️  Error enviando a Telegram: {exc}")
            failed.add(offer.fingerprint)
    return sent, failed


def main() -> None:
    args = parse_args()
    load_dotenv()
    check_credentials(args.dry_run)

    notifier = None
    if not args.dry_run:
        notifier = TelegramNotifier(
            bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
            chat_id=os.environ["TELEGRAM_CHAT_ID"],
        )

    found, counts = collect_offers(debug=args.debug)
    offers = deduplicate(found)
    print(f"\n📦 {len(offers)} ofertas únicas en total.")

    with SeenStore(config.SEEN_DB_PATH, legacy_json_path=config.LEGACY_SEEN_JSON_PATH) as store:
        # Antes de cualquier salida temprana, para avisar aunque no haya nada nuevo.
        report_empty_portals(store, counts, notifier)

        new_offers = [o for o in filter_excluded(offers) if store.is_new(o.fingerprint)]
        print(f"🆕 {len(new_offers)} ofertas nuevas (no vistas antes).")

        if new_offers:
            print(f"\n📄 Leyendo el detalle de {len(new_offers)} ofertas nuevas...")
            fetch_details(new_offers, debug=args.debug)
            new_offers = drop_excluded_after_details(new_offers, store)

        if not new_offers:
            print("Nada nuevo que evaluar. ¡Hasta la próxima!")
            return

        ranked = rank_offers(new_offers)
        sent, failed = notify(ranked, notifier)

        # Las que no superan el umbral también se guardan para no volver a
        # puntuarlas; las que fallaron al enviarse no, para reintentarlas.
        for offer in ranked:
            if offer.fingerprint not in failed:
                store.mark(offer, notified=offer.fingerprint in sent)

    print("\n✅ Listo.")


if __name__ == "__main__":
    main()
