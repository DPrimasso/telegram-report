"""Il trascrittore automatico del gruppo (lo "Scribacchino") non è una
persona: è un bot che converte i vocali in testo e, a richiesta, riepiloga
gli ultimi messaggi.

Le due cose che pubblica vanno trattate in modo opposto.

Una trascrizione sono le parole di chi ha mandato il vocale, e vanno
attribuite a lui: lasciarle a nome del bot lo fa comparire tra i
protagonisti della giornata e gonfia il conteggio dei partecipanti, visto
che le statistiche contano gli autori distinti.

Un riepilogo invece non è un fatto del gruppo, è un commento sul gruppo:
darlo in pasto al report significa fargli riassumere un riassunto, con il
rischio che un tema entri in pagina solo perché qualcuno ha chiesto al bot
di ricapitolarlo.

Il nome del bot e i marcatori dei riepiloghi si configurano da variabili
d'ambiente (vedi config.py): sono l'unica parte che dipende da come è
impostato quel particolare bot, e cambiarli non deve richiedere una patch.
"""

import re

# La trascrizione arriva quasi sempre con l'autore in testa, in una delle
# forme che questi bot usano: "Mario Rossi: testo", "🎤 Mario Rossi: testo",
# "**Mario Rossi** (vocale 0:42): testo". Quello che ci serve è separare il
# nome dal parlato, non riconoscere il singolo bot.
_ATTRIBUTION = re.compile(
    r"""^
    [\s\W]{0,4}                     # emoji o simboli di apertura
    (?:\*\*|__)?                    # eventuale grassetto markdown
    (?P<author>[^\n:]{2,40}?)       # il nome, fino ai due punti
    (?:\*\*|__)?
    \s*
    (?:\((?P<note>[^)]{0,40})\))?   # "(vocale 0:42)", "(audio)"
    \s*[:：]\s+
    (?P<text>.+)                    # il parlato vero e proprio
    $""",
    re.VERBOSE | re.DOTALL,
)

# Un nome plausibile: niente cifre iniziali, niente frasi intere. Serve a
# non scambiare per attribuzione un testo che comincia con "Attenzione:" o
# "Nota: ...".
_PLAUSIBLE_NAME = re.compile(r"^[^\d][\w'’.\-@ ]{1,39}$", re.UNICODE)

DEFAULT_BOT_NAMES = ("scribacchino",)

# Frasi con cui questi bot aprono un riepilogo su richiesta. Il confronto è
# su testo normalizzato e senza accenti, così "sintesi" prende anche
# "Sintesi:" e "SINTESI".
DEFAULT_SUMMARY_MARKERS = (
    "riepilogo",
    "riassunto",
    "recap",
    "sintesi",
    "ecco cosa",
    "ecco un riepilogo",
    "negli ultimi messaggi",
    "ultimi messaggi",
)


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def is_scribe(author: str, bot_names: tuple[str, ...] = DEFAULT_BOT_NAMES) -> bool:
    """Vero se l'autore è il bot trascrittore. Il confronto è per
    sottostringa perché il nome visualizzato cambia spesso di contorno
    ("Scribacchino", "Scribacchino Bot", "@scribacchino_bot")."""
    if not author:
        return False
    needle = _norm(author)
    return any(_norm(name) in needle for name in bot_names if name)


def looks_like_summary(
    text: str, markers: tuple[str, ...] = DEFAULT_SUMMARY_MARKERS
) -> bool:
    """Vero se il messaggio del bot è un riepilogo su richiesta.

    Si guarda solo l'inizio del messaggio: un riepilogo si annuncia in
    apertura, mentre la parola "riassunto" può comparire in mezzo a un
    vocale trascritto senza che quello sia un riepilogo."""
    if not text:
        return False
    head = _norm(text)[:120]
    return any(_norm(m) in head for m in markers if m)


# Parole che hanno la forma di un nome seguito dai due punti ma non lo sono.
# Senza questo filtro "Riepilogo: ..." verrebbe attribuito a un partecipante
# di nome Riepilogo.
_NOT_A_NAME = frozenset(
    {"attenzione", "nota", "avviso", "errore", "info", "aggiornamento"}
    | {m for m in DEFAULT_SUMMARY_MARKERS}
)


def classify(
    text: str, markers: tuple[str, ...] = DEFAULT_SUMMARY_MARKERS
) -> tuple[str | None, str] | None:
    """Decide che cosa è un messaggio del bot. Restituisce:

    - `(autore, testo)` se è una trascrizione che porta il nome di chi ha
      parlato;
    - `(None, testo)` se non è un riepilogo ma l'autore non si ricava dal
      testo: tocca al chiamante risalirci dal messaggio citato;
    - `None` se è un riepilogo, che nel report non deve entrare.

    L'attribuzione si prova per prima, e non è un dettaglio: un vocale in
    cui qualcuno dice "il riassunto della partita era generoso" contiene un
    marcatore da riepilogo pur essendo parlato vero. È il nome in testa a
    dire che quello è un vocale di una persona, e ha la precedenza."""
    attributed = split_attribution(text)
    if attributed is not None and not looks_like_summary(attributed[0], markers):
        return attributed
    if looks_like_summary(text, markers):
        return None
    return None, text


def split_attribution(text: str) -> tuple[str, str] | None:
    """Separa "Mario: ha detto che..." in ("Mario", "ha detto che...").

    Restituisce None quando la prima riga non è un'attribuzione, così il
    chiamante può decidere cosa fare di un messaggio non attribuibile."""
    if not text:
        return None
    first, _, rest = text.partition("\n")
    match = _ATTRIBUTION.match(first.strip())
    if match is None:
        return None

    author = (match.group("author") or "").strip().strip("*_").strip()
    if not author or not _PLAUSIBLE_NAME.match(author):
        return None
    if _norm(author) in _NOT_A_NAME:
        return None

    spoken = match.group("text").strip()
    if rest.strip():
        spoken = f"{spoken}\n{rest.strip()}" if spoken else rest.strip()
    if not spoken:
        return None
    return author, spoken
