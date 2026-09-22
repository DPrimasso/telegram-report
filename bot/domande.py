"""Genera le domande dell'intervista settimanale: un mix di domande
generiche (fisse, scelte a rotazione) e specifiche, ricavate dai messaggi
che la persona scelta ha scritto davvero nel gruppo negli ultimi 7 giorni.

Riusa la stessa pipeline del gazzettino (client Telethon a sessione utente
e report/llm.py): e' l'unico punto in cui il bot a comandi tocca quella
parte, e serve solo qui, non per rispondere ai comandi normali.
"""

import logging
import random
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from openai import OpenAI

from report import llm
from report.config import Config, load_config
from report.fetch import fetch_user_messages
from report.telegram_client import build_client

logger = logging.getLogger(__name__)

# Toglie un eventuale marcatore di elenco iniziale ("- ", "* ", "1.", "2)")
# dalle righe che il modello restituisce, anche se gli e' stato chiesto di
# non usarli: i modelli li aggiungono comunque abbastanza spesso.
_MARCATORE_ELENCO = re.compile(r"^\s*(?:[-*]|\d+[.)])\s*")

NUM_GENERICHE = 2
NUM_SPECIFICHE = 3

DOMANDE_GENERICHE = [
    "Raccontaci una cosa che ti ha fatto ridere questa settimana, dentro o fuori dal gruppo.",
    "Se potessi riscrivere un solo messaggio che hai mandato questa settimana, quale sarebbe e perche'?",
    "Qual e' il topic del gruppo che segui di piu' in questo periodo?",
    "C'e' un argomento di cui vorresti si parlasse di piu' nel gruppo?",
]


def _prompt_domande_specifiche(nome: str, trascritto: str) -> str:
    return (
        "Sei un cronista simpatico che scrive per il gazzettino di un gruppo Telegram.\n"
        f"Prepara fino a {NUM_SPECIFICHE} domande per un'intervista a {nome}, basate "
        "ESCLUSIVAMENTE sui messaggi che ha scritto nel gruppo negli ultimi 7 giorni, "
        "riportati sotto. Non inventare argomenti, nomi o dettagli che non siano "
        "scritti li'.\n\n"
        "Regole:\n"
        f"- Le domande devono riprendere argomenti o frasi che {nome} ha davvero scritto.\n"
        "- Tono leggero e curioso, come un'intervista simpatica per la rubrica del gruppo.\n"
        "- Una domanda per riga, senza numerazione ne' altro testo.\n"
        "- Se il materiale e' scarso o ripetitivo, scrivi meno domande (anche zero) "
        "invece di inventare argomenti.\n\n"
        f"Messaggi di {nome} di questa settimana:\n{trascritto}"
    )


async def _messaggi_settimana(config: Config, user_id: int) -> list[str]:
    tz = ZoneInfo(config.timezone)
    ora = datetime.now(tz)
    since = ora - timedelta(days=7)

    client = build_client(config)
    async with client:
        messaggi = await fetch_user_messages(client, config.group_id, user_id, since, ora)
    return [m.text for m in messaggi]


def _domande_specifiche(config: Config, nome: str, testi: list[str]) -> list[str]:
    if not testi:
        return []
    trascritto = "\n".join(f"- {testo}" for testo in testi)
    openai_client = OpenAI(api_key=config.openai_api_key)
    risposta = llm.complete(
        openai_client,
        config.openai_model,
        _prompt_domande_specifiche(nome, trascritto),
        temperature=0.7,
    )
    righe = [_MARCATORE_ELENCO.sub("", riga).strip() for riga in risposta.splitlines()]
    return [riga for riga in righe if riga][:NUM_SPECIFICHE]


async def genera_domande(nome: str, user_id: int) -> list[str]:
    """Un mix di domande generiche e specifiche per l'intervista di `nome`.

    Le specifiche vengono dai suoi messaggi della settimana; se non ne ha
    scritti abbastanza, o qualcosa nella pipeline del gazzettino fallisce
    (config assente, Telegram, OpenAI), restano solo le generiche:
    l'intervista parte comunque."""
    generiche = random.sample(DOMANDE_GENERICHE, k=min(NUM_GENERICHE, len(DOMANDE_GENERICHE)))

    specifiche: list[str] = []
    try:
        config = load_config()
        testi = await _messaggi_settimana(config, user_id)
        specifiche = _domande_specifiche(config, nome, testi)
    except Exception as errore:
        logger.warning("Domande specifiche non generate (%s): resto sulle generiche.", errore)

    return generiche + specifiche
