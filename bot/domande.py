"""Genera le domande dell'intervista settimanale: un mix di domande
generiche (fisse, scelte a rotazione) e specifiche, ricavate da cosa la
persona scelta ha scritto davvero nel gruppo negli ultimi 7 giorni.

Le specifiche non si basano sulle sue frasi isolate (risultavano anonime,
scollegate dal motivo per cui erano state scritte): per ogni topic a cui ha
partecipato si passa al modello l'intera conversazione di quel topic nella
settimana, cosi' puo' capire il contesto (di cosa si parlava, a chi/cosa ci
si riferiva) e fare una domanda naturale invece di citare una riga a caso.

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
from report.fetch import TopicMessages, fetch_messages_between, resolve_member_name
from report.telegram_client import build_client

logger = logging.getLogger(__name__)

# Toglie un eventuale marcatore di elenco iniziale ("- ", "* ", "1.", "2)")
# dalle righe che il modello restituisce, anche se gli e' stato chiesto di
# non usarli: i modelli li aggiungono comunque abbastanza spesso.
_MARCATORE_ELENCO = re.compile(r"^\s*(?:[-*]|\d+[.)])\s*")

NUM_GENERICHE = 2
NUM_SPECIFICHE = 3

# Quanti topic (i piu' "suoi", per numero di messaggi) portare al modello, e
# quanto lungo al massimo il transcript risultante: un paio di conversazioni
# vivaci bastano per delle buone domande, e tenerlo corto costa meno e
# riduce il rischio che il modello si perda in dettagli marginali.
MAX_TOPIC = 3
MAX_TRASCRITTO_CHARS = 12_000

DOMANDE_GENERICHE = [
    "Raccontaci una cosa che ti ha fatto ridere questa settimana, dentro o fuori dal gruppo.",
    "Se potessi riscrivere un solo messaggio che hai mandato questa settimana, quale sarebbe e perche'?",
    "Qual e' il topic del gruppo che segui di piu' in questo periodo?",
    "C'e' un argomento di cui vorresti si parlasse di piu' nel gruppo?",
]


def _prompt_domande_specifiche(nome: str, trascritto: str) -> str:
    return (
        "Sei un cronista simpatico che scrive per il gazzettino di un gruppo Telegram.\n"
        f"Prepara fino a {NUM_SPECIFICHE} domande per un'intervista a {nome}.\n\n"
        f"Sotto trovi le conversazioni dei topic del gruppo a cui {nome} ha "
        "partecipato negli ultimi 7 giorni, con TUTTI i messaggi (non solo i "
        f"suoi): usali per capire il contesto — di cosa si parlava, a chi o "
        f"cosa si riferiva {nome} — ma le domande devono riguardare cose "
        f"scritte da {nome} in prima persona, non dagli altri.\n\n"
        "Regole:\n"
        "- Basati ESCLUSIVAMENTE su quello che e' scritto qui sotto: non "
        "inventare fatti, nomi o dettagli che non ci siano.\n"
        "- Usa il contesto per fare domande naturali e precise, invece di "
        "citare alla lettera una frase isolata fuori contesto.\n"
        "- Tono leggero e curioso, come un'intervista simpatica per la rubrica del gruppo.\n"
        "- Una domanda per riga, senza numerazione ne' altro testo.\n"
        "- Se il materiale e' scarso o ripetitivo, scrivi meno domande (anche zero) "
        "invece di inventare argomenti.\n\n"
        f"Conversazioni:\n{trascritto}"
    )


async def _contesto_settimana(config: Config, user_id: int) -> tuple[str, list[TopicMessages]]:
    tz = ZoneInfo(config.timezone)
    ora = datetime.now(tz)
    since = ora - timedelta(days=7)

    client = build_client(config)
    async with client:
        nome_autore = await resolve_member_name(client, config.group_id, user_id)
        topics = await fetch_messages_between(client, config.group_id, since, ora)
    return nome_autore, topics


def _trascritto_con_contesto(nome_autore: str, topics: list[TopicMessages]) -> str:
    """Un topic per blocco, con la conversazione intera (non solo le righe
    di `nome_autore`): e' il contesto che serve al modello per capire di
    cosa si parlava. Solo i topic a cui ha partecipato, i piu' attivi per
    lui prima, entro un tetto di lunghezza."""
    partecipati = [
        topic for topic in topics if any(m.author == nome_autore for m in topic.messages)
    ]
    partecipati.sort(
        key=lambda t: sum(m.author == nome_autore for m in t.messages), reverse=True
    )

    blocchi = []
    for topic in partecipati[:MAX_TOPIC]:
        righe = "\n".join(f"{m.author}: {m.text}" for m in topic.messages)
        blocchi.append(f"### {topic.title}\n{righe}")

    return "\n\n".join(blocchi)[:MAX_TRASCRITTO_CHARS]


def _domande_specifiche(config: Config, nome: str, trascritto: str) -> list[str]:
    if not trascritto:
        return []
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

    Le specifiche vengono dalle conversazioni della settimana a cui ha
    partecipato; se non ne ha (o qualcosa nella pipeline del gazzettino
    fallisce: config assente, Telegram, OpenAI), restano solo le
    generiche: l'intervista parte comunque."""
    generiche = random.sample(DOMANDE_GENERICHE, k=min(NUM_GENERICHE, len(DOMANDE_GENERICHE)))

    specifiche: list[str] = []
    try:
        config = load_config()
        nome_autore, topics = await _contesto_settimana(config, user_id)
        trascritto = _trascritto_con_contesto(nome_autore, topics)
        specifiche = _domande_specifiche(config, nome, trascritto)
    except Exception as errore:
        logger.warning("Domande specifiche non generate (%s): resto sulle generiche.", errore)

    return generiche + specifiche
