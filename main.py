"""JobScout — punto de entrada.

Flujo completo:
  1. Buscar ofertas en los portales según las palabras clave (config.py).
  2. Deduplicar y descartar las ya vistas en ejecuciones anteriores.
  3. Puntuar cada oferta nueva contra el CV usando Claude.
  4. Enviar por Telegram las que superen el puntaje mínimo.

Uso:
    python main.py            # ejecución normal
    python main.py --debug    # guarda el HTML crudo de los portales
    python main.py --dry-run  # no envía a Telegram, solo imprime en consola
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

import config
from jobscout.models import JobOffer
from jobscout.notifier import TelegramNotifier
from jobscout.ranking import Ranker
from jobscout.scrapers import SCRAPERS
from jobscout.storage import SeenStore


def collect_offers(debug: bool) -> list[JobOffer]:
    """Recorre los portales y devuelve todas las ofertas encontradas."""
    all_offers: list[JobOffer] = []

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
        for keyword in config.SEARCH_KEYWORDS:
            print(f"🔎 Buscando '{keyword}' en {name} ({config.COUNTRY})...")
            found = scraper.search(keyword, max_pages=config.MAX_PAGES_PER_KEYWORD)
            print(f"   {len(found)} ofertas encontradas.")
            all_offers.extend(found)

    return all_offers


def deduplicate(offers: list[JobOffer]) -> list[JobOffer]:
    """Elimina ofertas repetidas dentro de esta misma ejecución (por URL)."""
    seen_fps: set[str] = set()
    unique: list[JobOffer] = []
    for offer in offers:
        if offer.fingerprint not in seen_fps:
            seen_fps.add(offer.fingerprint)
            unique.append(offer)
    return unique


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

    # 1. Recolectar y deduplicar.
    offers = deduplicate(collect_offers(debug=args.debug))
    print(f"\n📦 {len(offers)} ofertas únicas en total.")

    # 2. Filtrar las ya vistas.
    store = SeenStore(config.SEEN_DB_PATH, legacy_json_path=config.LEGACY_SEEN_JSON_PATH)
    new_offers = [o for o in offers if store.is_new(o.fingerprint)]
    print(f"🆕 {len(new_offers)} ofertas nuevas (no vistas antes).")

    if not new_offers:
        print("Nada nuevo que evaluar. ¡Hasta la próxima!")
        return

    # 3. Puntuar con IA.
    print(f"\n🤖 Puntuando {len(new_offers)} ofertas con {config.RANKING_MODEL}...")
    ranker = Ranker(cv_text=load_cv(), model=config.RANKING_MODEL)
    ranker.rank_all(new_offers)

    # Ordenar de mayor a menor puntaje.
    new_offers.sort(key=lambda o: o.score, reverse=True)

    # 4. Notificar las que superen el umbral.
    to_notify = [o for o in new_offers if o.score >= config.MIN_SCORE_TO_NOTIFY]
    print(f"\n📨 {len(to_notify)} ofertas superan el umbral ({config.MIN_SCORE_TO_NOTIFY}).")

    notifier = None
    if not args.dry_run:
        notifier = TelegramNotifier(
            bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
            chat_id=os.environ["TELEGRAM_CHAT_ID"],
        )

    sent: set[str] = set()
    for offer in to_notify:
        print(f"  [{offer.score}] {offer.title} — {offer.company}")
        if notifier is not None:
            try:
                notifier.send_offer(offer)
                sent.add(offer.fingerprint)
            except Exception as exc:  # noqa: BLE001
                print(f"    ⚠️  Error enviando a Telegram: {exc}")

    # 5. Marcar como vistas TODAS las nuevas (incluso las que no se notificaron,
    #    para no re-evaluarlas y gastar tokens en cada ejecución).
    for offer in new_offers:
        store.mark(offer, notified=offer.fingerprint in sent)
    store.save()

    print("\n✅ Listo.")


if __name__ == "__main__":
    main()
