"""Genera l'intervista settimanale: le domande e, durante la chat, una
breve reazione del "giornalista" a ogni risposta.

Le domande escono da UNA sola generazione con un tono da vera intervista
(apertura, corpo, chiusura) invece che da un mix meccanico di domande fisse
+ citazioni: cosi' l'arco risulta coerente, come farebbe un giornalista che
intervista un personaggio pubblico, non un questionario. Sono grounded
sulle conversazioni della settimana quando disponibili (per ogni topic a
cui la persona ha partecipato si passa al modello l'intera conversazione,
non solo le sue righe, cosi' capisce il contesto invece di limitarsi a
citare una frase isolata).

Riusa la stessa pipeline del gazzettino (client Telethon a sessione utente
e report/llm.py): e' l'unico punto in cui il bot a comandi tocca quella
parte, e serve solo qui, non per rispondere ai comandi normali.
"""

import logging
import random
import re
from datetime import date, datetime, timedelta
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

NUM_DOMANDE = 5

# Pool fisso, usato SOLO come ultima rete di sicurezza se l'intera pipeline
# del gazzettino fallisce (config assente, Telegram, OpenAI): meglio
# un'intervista generica che nessuna intervista.
NUM_RISERVA = 4
DOMANDE_DI_RISERVA = [
    "Raccontaci una cosa che ti ha fatto ridere questa settimana, dentro o fuori dal gruppo.",
    "Se potessi riscrivere un solo messaggio che hai mandato questa settimana, quale sarebbe e perche'?",
    "Qual e' il topic del gruppo che segui di piu' in questo periodo?",
    "C'e' un argomento di cui vorresti si parlasse di piu' nel gruppo?",
]

_REAZIONE_DI_RISERVA = "Capito, grazie."

# Quanti topic (i piu' "suoi", per numero di messaggi) portare al modello, e
# quanto lungo al massimo il transcript risultante: un paio di conversazioni
# vivaci bastano per delle buone domande, e tenerlo corto costa meno e
# riduce il rischio che il modello si perda in dettagli marginali.
MAX_TOPIC = 3
MAX_TRASCRITTO_CHARS = 12_000


def _prompt_intervista(
    nome: str, trascritto: str, oggi: date, tema_gruppo: str | None
) -> str:
    if trascritto:
        contesto = (
            f"Sotto trovi le conversazioni dei topic del gruppo a cui {nome} "
            "ha partecipato negli ultimi 7 giorni, con TUTTI i messaggi (non "
            f"solo i suoi) e la data di ciascuno: usali per capire il "
            f"contesto — di cosa si parlava, a chi o cosa si riferiva {nome}, "
            "e se un fatto o un evento citato e' concluso o ancora da "
            "venire rispetto a oggi.\n\n"
            f"Conversazioni:\n{trascritto}"
        )
    else:
        contesto = (
            "Questa settimana non risultano conversazioni sue nel gruppo: "
            "fai comunque un'intervista credibile, con domande piu' generali "
            "sul gruppo e su come vive la settimana, nello stesso tono."
        )
    focus_tematico = (
        f"\nQuesto e' un gruppo di {tema_gruppo}: anche se nelle conversazioni "
        "si parla d'altro, tieni le domande centrate li' quando è pertinente, "
        "invece di seguire argomenti secondari.\n"
        if tema_gruppo
        else ""
    )
    return (
        f"Sei un giornalista che sta intervistando {nome} per il gazzettino "
        "di un gruppo Telegram, protagonista della settimana: scrivi come "
        "se stessi davvero intervistando un personaggio pubblico, non come "
        f"un questionario. Oggi è {oggi.strftime('%d/%m/%Y')}. Prepara "
        f"{NUM_DOMANDE} domande, in un arco naturale da vera intervista:\n"
        "- la prima è una domanda di apertura, che mette a suo agio;\n"
        "- quelle centrali entrano nel merito di episodi concreti della "
        "settimana, formulate come farebbe un giornalista che gia' conosce "
        "il contesto (MAI come una citazione letterale seguita da 'cosa "
        "intendevi': costruisci la domanda intorno al fatto, non intorno "
        "alla frase);\n"
        "- l'ultima è una domanda di chiusura, più ampia o di prospettiva.\n\n"
        "Regole:\n"
        "- Basati ESCLUSIVAMENTE su quello che e' scritto qui sotto: non "
        "inventare fatti, nomi o dettagli che non ci siano.\n"
        "- Attenzione al tempo: se un evento di cui si parla (una partita, "
        "un appuntamento) risulta già accaduto rispetto a oggi, fai la "
        "domanda guardando indietro (com'è andata, cosa ne pensi ora), MAI "
        "come se dovesse ancora succedere.\n"
        f"- Rivolgiti a {nome} in seconda persona, con un tono professionale "
        "ma cordiale, come si farebbe con un ospite d'onore.\n"
        f"{focus_tematico}"
        "- Una domanda per riga, senza numerazione ne' altro testo.\n\n"
        f"{contesto}"
    )


def _prompt_reazione(nome: str, domanda: str, risposta: str, ultima: bool) -> str:
    if ultima:
        istruzione = (
            "E' l'ultima risposta dell'intervista: scrivi una riga di "
            "chiusura naturale a quello che ha appena detto. NON accennare, "
            "alludere o aprire ad altre domande o argomenti: l'intervista "
            "finisce qui, quindi la riga non deve terminare con un punto "
            "di domanda."
        )
    else:
        istruzione = (
            "Scrivi come diresti davvero prima di passare alla prossima "
            "domanda (un commento breve, anche una battuta se ci sta): "
            "niente nuove domande, niente saluti, solo la reazione."
        )
    return (
        f"Sei un giornalista che sta intervistando dal vivo {nome} per il "
        "gazzettino di un gruppo Telegram, con il tono di una vera "
        "intervista a un personaggio pubblico. Ha appena risposto cosi':\n"
        f"Domanda: {domanda}\n"
        f"Risposta: {risposta}\n\n"
        f"Scrivi UNA sola riga di reazione naturale. {istruzione}"
    )


async def _contesto_settimana(
    config: Config, user_id: int
) -> tuple[str, list[TopicMessages], date]:
    tz = ZoneInfo(config.timezone)
    ora = datetime.now(tz)
    since = ora - timedelta(days=7)

    client = build_client(config)
    async with client:
        nome_autore = await resolve_member_name(client, config.group_id, user_id)
        topics = await fetch_messages_between(client, config.group_id, since, ora)
    return nome_autore, topics, ora.date()


def _trascritto_con_contesto(nome_autore: str, topics: list[TopicMessages]) -> str:
    """Un topic per blocco, con la conversazione intera (non solo le righe
    di `nome_autore`): e' il contesto che serve al modello per capire di
    cosa si parlava. Solo i topic a cui ha partecipato, i piu' attivi per
    lui prima, entro un tetto di lunghezza. Ogni riga porta la sua data:
    senza, il modello non ha modo di sapere se un evento citato (una
    partita, un appuntamento) e' gia' successo rispetto a oggi."""
    partecipati = [
        topic for topic in topics if any(m.author == nome_autore for m in topic.messages)
    ]
    partecipati.sort(
        key=lambda t: sum(m.author == nome_autore for m in t.messages), reverse=True
    )

    blocchi = []
    for topic in partecipati[:MAX_TOPIC]:
        righe = "\n".join(
            f"[{m.timestamp.strftime('%d/%m')}] {m.author}: {m.text}" for m in topic.messages
        )
        blocchi.append(f"### {topic.title}\n{righe}")

    return "\n\n".join(blocchi)[:MAX_TRASCRITTO_CHARS]


def _genera_intervista_llm(
    config: Config, nome: str, trascritto: str, oggi: date
) -> list[str]:
    openai_client = OpenAI(api_key=config.openai_api_key)
    risposta = llm.complete(
        openai_client,
        config.openai_model,
        _prompt_intervista(nome, trascritto, oggi, config.tema_gruppo),
        temperature=0.8,
    )
    righe = [_MARCATORE_ELENCO.sub("", riga).strip() for riga in risposta.splitlines()]
    return [riga for riga in righe if riga][:NUM_DOMANDE]


async def genera_domande(nome: str, user_id: int) -> list[str]:
    """Le domande dell'intera intervista a `nome`, generate in un colpo
    solo con un tono da vera intervista (apertura, corpo, chiusura),
    grounded sulle conversazioni della settimana quando disponibili. Se
    l'intera pipeline del gazzettino fallisce (config assente, Telegram,
    OpenAI), ripiega sul pool fisso: l'intervista parte comunque."""
    try:
        config = load_config()
        nome_autore, topics, oggi = await _contesto_settimana(config, user_id)
        trascritto = _trascritto_con_contesto(nome_autore, topics)
        domande = _genera_intervista_llm(config, nome, trascritto, oggi)
        if domande:
            return domande
    except Exception as errore:
        logger.warning(
            "Intervista generata non disponibile (%s): uso le domande di riserva.", errore
        )

    return random.sample(DOMANDE_DI_RISERVA, k=min(NUM_RISERVA, len(DOMANDE_DI_RISERVA)))


def genera_reazione(nome: str, domanda: str, risposta: str, ultima: bool = False) -> str:
    """Una riga di reazione del giornalista alla risposta appena ricevuta,
    per dare all'intervista un ritmo da conversazione vera invece che da
    lista di domande spedite in fila. `ultima=True` per la risposta che
    chiude l'intervista: senza saperlo, il modello tende a chiudere la
    reazione con un accenno a un'altra domanda che poi non arriva mai. Se
    qualcosa non funziona, una riga neutra tiene comunque in piedi
    l'intervista."""
    try:
        config = load_config()
        openai_client = OpenAI(api_key=config.openai_api_key)
        testo = llm.complete(
            openai_client,
            config.openai_model,
            _prompt_reazione(nome, domanda, risposta, ultima),
            temperature=0.8,
        )
        righe = [riga.strip() for riga in testo.splitlines() if riga.strip()]
        return righe[0] if righe else _REAZIONE_DI_RISERVA
    except Exception as errore:
        logger.warning("Reazione non generata (%s): uso una riga neutra.", errore)
        return _REAZIONE_DI_RISERVA


_DECK_DI_RISERVA = "Le risposte della persona scelta questa settimana, per l'inserto del gazzettino."


def _prompt_deck(nome: str, domande_risposte: list[tuple[str, str]]) -> str:
    scambio = "\n".join(f"D: {d}\nR: {r}" for d, r in domande_risposte)
    return (
        "Sei il caporedattore del gazzettino di un gruppo Telegram e devi "
        f"scrivere il sommario (il 'deck') dell'intervista a {nome} di "
        "questa settimana, da mettere sotto il titolo in prima pagina.\n\n"
        "Regole:\n"
        "- Una sola riga, una frase, senza virgolette.\n"
        "- Basati ESCLUSIVAMENTE su quello che e' scritto nello scambio "
        "sotto: non inventare fatti che non ci siano.\n"
        "- Deve aggiungere un'informazione, non ripetere il nome o dire "
        "solo 'un'intervista con...': anticipa di cosa si parla.\n\n"
        f"Scambio:\n{scambio}"
    )


def genera_deck(nome: str, domande_risposte: list[tuple[str, str]]) -> str:
    """Il sommario di apertura dell'inserto (occhiello sotto il titolo):
    una riga che anticipa di cosa parla l'intervista, come richiede lo
    stile del gazzettino (titolo, sommario, testo). Se la generazione
    fallisce, una riga di riserva tiene comunque in piedi l'impaginazione."""
    if not domande_risposte:
        return _DECK_DI_RISERVA
    try:
        config = load_config()
        openai_client = OpenAI(api_key=config.openai_api_key)
        testo = llm.complete(
            openai_client,
            config.openai_model,
            _prompt_deck(nome, domande_risposte),
            temperature=0.7,
        )
        righe = [riga.strip().strip('"').strip("«»") for riga in testo.splitlines() if riga.strip()]
        return righe[0] if righe else _DECK_DI_RISERVA
    except Exception as errore:
        logger.warning("Deck dell'inserto non generato (%s): uso una riga di riserva.", errore)
        return _DECK_DI_RISERVA
