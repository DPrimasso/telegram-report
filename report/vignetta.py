"""La vignetta del giorno: un disegno della biblioteca, le parole del gruppo.

L'idea è vecchia quanto i giornali: una scenetta con due tizi che dicono
la cosa che tutti hanno pensato quel giorno. Qui i due tizi sono sempre gli
stessi e il disegno è fatto in anticipo; a cambiare ogni giorno sono le
battute, che non vengono scritte da nessuno — sono messaggi veri, copiati
alla lettera dal gruppo.

Questo risolve il problema che `docs/grafica.md` aveva lasciato aperto
("un modo di legare l'immagine al fatto e non all'argomento") prendendolo
dal verso opposto: **il disegno non illustra il fatto, illustra il tono**.
Non c'è nessun disegno di "il gol al novantesimo": c'è un disegno di due
che esultano, ed è la battuta sotto a dire di che gol si parla. Il legame
con la giornata lo fanno le parole, che sono di quel giorno per
costruzione.

Da qui discende tutto il resto:

- **la biblioteca è finita e fatta a mano.** Sei toni, una cartella per
  tono, i disegni dentro. Generare un'immagine al giorno costerebbe cento
  euro l'anno e darebbe personaggi diversi ogni volta; una biblioteca
  costa zero e i personaggi restano quelli. Il codice guarda solo il nome
  della cartella: il nome dei file non significa niente per lui, quindi si
  possono aggiungere, togliere e rinominare disegni senza toccare una riga.
- **un tono senza disegni non esce mai.** I toni disponibili si contano
  guardando le cartelle e si passano al modello dentro il prompt: non può
  scegliere un tono che non abbiamo. Se non ne resta nessuno, la vignetta
  salta e torna la frase del giorno.
- **una battuta che non esiste non si stampa.** Vale la stessa verifica
  della frase del giorno, e qui pesa di più: un fumetto sembra per sua
  natura una cosa inventata, e se le parole non fossero vere sarebbe una
  barzelletta con dei nomi veri sotto.
"""

from __future__ import annotations

import random
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from report import llm
from report.newspaper import Balloon, Vignetta

if TYPE_CHECKING:
    # Solo per l'annotazione: report.fetch tira dentro Telethon, e la
    # biblioteca deve potersi aprire anche dove Telegram non serve —
    # preview.py, biblioteca.py, un controllo al volo dei disegni.
    from report.fetch import SimpleMessage

# I sei toni. Sono stati di una discussione, non emozioni: un gruppo che
# commenta una partita litiga, esulta, si dispera, complotta, spiega o
# aspetta, e non fa quasi nient'altro.
TONI: tuple[str, ...] = (
    "battibecco",   # due che non sono d'accordo
    "esultanza",    # è andata bene
    "sconforto",    # è andata male
    "complotto",    # il sospetto, la dietrologia
    "spiegone",     # uno che spiega a chi non ha chiesto
    "attesa",       # deve ancora succedere
)

DESCRIZIONI = {
    "battibecco": "il gruppo si è diviso, due tesi opposte si sono scontrate",
    "esultanza": "è andata bene e il gruppo festeggia",
    "sconforto": "è andata male, il gruppo è affranto o rassegnato",
    "complotto": "sospetto, dietrologia, «lo sapevo che finiva così»",
    "spiegone": "qualcuno spiega la sua teoria a chi non l'aveva chiesta",
    "attesa": "deve ancora succedere qualcosa e c'è tensione",
}

ESTENSIONI = {".png", ".jpg", ".jpeg", ".webp"}

CARTELLA_PREDEFINITA = Path("assets/vignette")

# Come per la frase del giorno: sotto una certa lunghezza un messaggio non
# dice niente, sopra non sta nel balloon senza coprire i disegni.
_MIN_BATTUTA = 20
_MAX_BATTUTA = 110

# Più di due balloon e la metà alta del pannello non basta più: il terzo
# finirebbe sopra le teste.
_MAX_BATTUTE = 2


class Biblioteca:
    """I disegni su disco, indicizzati per tono.

    Non conosce le ambientazioni e non gliene importa: dentro
    `esultanza/` i disegni sono intercambiabili, e quale esca è solo una
    questione di non ripetersi troppo."""

    def __init__(self, base: str | Path = CARTELLA_PREDEFINITA) -> None:
        self.base = Path(base)
        self.per_tono: dict[str, list[Path]] = {}
        for tono in TONI:
            cartella = self.base / tono
            if not cartella.is_dir():
                continue
            trovati = sorted(
                p for p in cartella.iterdir() if p.suffix.lower() in ESTENSIONI
            )
            if trovati:
                self.per_tono[tono] = trovati

    @property
    def toni(self) -> list[str]:
        """Solo i toni che hanno almeno un disegno."""
        return [t for t in TONI if t in self.per_tono]

    def __bool__(self) -> bool:
        return bool(self.per_tono)

    def scegli(self, tono: str, giorno: date) -> Path | None:
        """Un disegno del tono, diverso da quello di ieri.

        La scelta è una rotazione ancorata alla data: senza stato su
        disco (il gazzettino gira in CI, su una copia nuova del
        repository ogni volta) è l'unico modo di garantire che due giorni
        di fila non escano lo stesso disegno. Il mescolamento iniziale è
        fisso per tono, così l'ordine non è quello alfabetico dei nomi
        dei file — che seguirebbe le ambientazioni e farebbe uscire in
        fila tutte quelle al chiuso."""
        disegni = self.per_tono.get(tono)
        if not disegni:
            return None
        ordine = list(disegni)
        random.Random(tono).shuffle(ordine)
        return ordine[giorno.toordinal() % len(ordine)]


def _prompt(toni: list[str], tema: str) -> str:
    elenco = "\n".join(f"- {t}: {DESCRIZIONI[t]}" for t in toni)
    return (
        "Di seguito i messaggi di oggi di un gruppo Telegram di tifosi, nel "
        "formato [ora] (topic) autore: testo.\n\n"
        f"L'apertura del gazzettino di oggi è: «{tema}»\n\n"
        "Devi comporre la VIGNETTA del giorno su questo argomento: una "
        "scenetta con due personaggi che si dicono, alla lettera, cose che "
        "il gruppo ha scritto davvero.\n\n"
        "1) Scegli il TONO della discussione su quell'argomento, fra questi "
        "e solo questi:\n"
        f"{elenco}\n\n"
        "2) Scegli UNA o DUE battute fra i messaggi qui sotto. Due se c'è "
        "uno scambio vero fra due persone diverse — una che dice qualcosa e "
        "un'altra che risponde o ribatte; una sola se la frase migliore è "
        "rimasta senza risposta. Meglio una battuta buona che due tirate "
        "per i capelli.\n\n"
        "REGOLA PIÙ IMPORTANTE: le battute vanno COPIATE ESATTAMENTE come "
        "sono scritte nel messaggio. Non riscriverle, non correggere gli "
        "errori, non accorciarle, non togliere né aggiungere una parola. "
        "Una battuta che non compare identica in un messaggio viene "
        "scartata.\n\n"
        "Scarta i link, gli insulti pesanti e le frasi che fuori contesto "
        "non si capiscono. Le due battute devono essere di due autori "
        "diversi.\n\n"
        "Rispondi in questo formato esatto e senza altro testo:\n"
        "TONO: uno dei toni elencati\n"
        "BATTUTA: testo | autore\n"
        "BATTUTA: testo | autore   (questa riga solo se serve)\n"
        "Se nessuna frase è adatta, rispondi solo: NESSUNA"
    )


def _candidati(
    messages_with_topic: list[tuple[str, "SimpleMessage"]],
) -> list[tuple[str, "SimpleMessage"]]:
    return [
        (topic, m)
        for topic, m in sorted(messages_with_topic, key=lambda pair: pair[1].timestamp)
        if _MIN_BATTUTA <= len(m.text) <= _MAX_BATTUTA
        and "http" not in m.text
        and not m.text.startswith("[")
    ]


def _leggi(raw: str, toni: list[str]) -> tuple[str, list[tuple[str, str]]]:
    tono = ""
    battute: list[tuple[str, str]] = []
    for riga in raw.splitlines():
        riga = riga.strip()
        if riga.upper().startswith("TONO:"):
            scelto = riga.split(":", 1)[1].strip().lower()
            if scelto in toni:
                tono = scelto
        elif riga.upper().startswith("BATTUTA:"):
            corpo = riga.split(":", 1)[1]
            testo, _, autore = corpo.rpartition("|")
            testo = testo.strip().strip('"').strip("«»")
            if testo and autore.strip():
                battute.append((testo, autore.strip()))
    return tono, battute[:_MAX_BATTUTE]


def pick_vignetta(
    client,
    model: str,
    messages_with_topic: list[tuple[str, "SimpleMessage"]],
    *,
    tema: str,
    giorno: date,
    biblioteca: Biblioteca | None = None,
) -> Vignetta | None:
    """Sceglie tono e battute, e ci appoggia sopra un disegno.

    Restituisce None ogni volta che qualcosa non torna — biblioteca
    vuota, nessuna frase adatta, battute che non combaciano. Chi chiama
    ripiega sulla frase del giorno: il gazzettino esce comunque."""
    biblioteca = biblioteca if biblioteca is not None else Biblioteca()
    if not biblioteca:
        return None
    if not messages_with_topic or not tema:
        return None

    usable = _candidati(messages_with_topic)
    if not usable:
        return None

    transcript = "\n".join(
        f"[{m.timestamp:%H:%M}] ({topic}) {m.author}: {m.text}" for topic, m in usable
    )
    raw = llm.complete(
        client, model, f"{_prompt(biblioteca.toni, tema)}\n\n{transcript}",
        temperature=0.3,
    )
    if not raw or raw.strip().upper().startswith("NESSUNA"):
        return None

    tono, battute = _leggi(raw, biblioteca.toni)
    if not tono or not battute:
        print("Vignetta saltata: il modello non ha scelto un tono valido.")
        return None

    # Verifica di aderenza, una battuta alla volta. Una battuta inventata
    # non fa saltare la vignetta: sparisce lei, e se ne resta almeno
    # un'altra la scenetta si fa con un balloon solo.
    palloncini: list[Balloon] = []
    topic_scena = ""
    for testo, _autore in battute:
        cercato = testo.lower()
        trovato = next(
            ((topic, m) for topic, m in usable if cercato in m.text.lower()), None
        )
        if trovato is None:
            print(f"Battuta scartata, non combacia con nessun messaggio: {testo!r}")
            continue
        topic, m = trovato
        topic_scena = topic_scena or topic
        palloncini.append(
            Balloon(text=testo, author=m.author, time=m.timestamp.strftime("%H:%M"))
        )

    # Due battute dello stesso autore non sono uno scambio: sono la
    # stessa persona che parla due volte, e in pagina sembrerebbero due
    # personaggi diversi. Tengo la prima.
    if len(palloncini) == 2 and palloncini[0].author == palloncini[1].author:
        palloncini = palloncini[:1]
    if not palloncini:
        return None

    disegno = biblioteca.scegli(tono, giorno)
    if disegno is None:
        return None

    return Vignetta(
        image_path=disegno,
        balloons=palloncini,
        topic=topic_scena,
        tone=tono,
    )
