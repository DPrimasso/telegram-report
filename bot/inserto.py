"""Pubblica l'inserto settimanale: prende l'ultima intervista completata e
non ancora pubblicata (bot/storage.py), la impagina nello stile del
gazzettino (report/inserto.py) e la invia con la stessa pipeline Telethon
del report giornaliero (report/send.py). Richiamata dall'endpoint
/trigger/inserto, su un cron settimanale separato da quello
dell'estrazione: da' il tempo alla persona scelta di rispondere prima che
l'inserto esca.
"""

import logging
import tempfile
from datetime import date
from pathlib import Path

from report.config import load_config
from report.fetch import get_group_title
from report.inserto import build_intervista_pages_html
from report.newspaper import render_html_to_png
from report.send import send_photo_report
from report.telegram_client import build_client

from bot.domande import genera_deck
from bot.storage import Storage

logger = logging.getLogger(__name__)


async def pubblica_inserto_settimanale(storage: Storage) -> bool:
    """Ritorna True se ha pubblicato qualcosa, False se non c'era
    un'intervista completata in attesa o se la pipeline del gazzettino non
    e' disponibile (config assente, Telegram, OpenAI, Playwright): in quel
    caso l'intervista resta in coda e verra' ripresa al prossimo giro."""
    prossima = storage.prossima_intervista_da_pubblicare()
    if prossima is None:
        logger.warning("Nessuna intervista completata in attesa di pubblicazione.")
        return False

    intervista_id, nome = prossima
    domande_risposte = storage.carica_risposte(intervista_id)
    if not domande_risposte:
        logger.warning(
            "Intervista %s completata ma senza risposte salvate: salto.", intervista_id
        )
        return False

    try:
        config = load_config()
        deck = genera_deck(nome, domande_risposte)

        client = build_client(config)
        async with client:
            newspaper_name = config.newspaper_name or await get_group_title(
                client, config.group_id
            )
            with tempfile.TemporaryDirectory() as tmp_dir:
                pagine_html = build_intervista_pages_html(
                    newspaper_name,
                    date.today(),
                    nome,
                    domande_risposte,
                    logo_path=config.logo_path,
                    firma_path=config.firma_path,
                    deck=deck,
                )
                image_paths = []
                for numero, pagina_html in enumerate(pagine_html, start=1):
                    percorso = str(Path(tmp_dir) / f"inserto_{numero}.png")
                    await render_html_to_png(pagina_html, percorso)
                    image_paths.append(percorso)

                caption = f"📰 Inserto settimanale — intervista a {nome}"
                await send_photo_report(client, config, image_paths, caption=caption)
    except Exception:
        logger.exception(
            "Pubblicazione dell'inserto settimanale fallita (intervista %s): "
            "resta in coda per il prossimo giro.",
            intervista_id,
        )
        return False

    storage.segna_pubblicata(intervista_id)
    logger.info("Inserto settimanale pubblicato per l'intervista di %s.", nome)
    return True
