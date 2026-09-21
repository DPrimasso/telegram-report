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

Sopra la biblioteca c'è poi il disegno generato per l'edizione del
giorno (`generate_ai_drawing`), che la sostituisce quando c'è una chiave
OpenAI e non salta niente quando non c'è. Prende il verso opposto — il
disegno torna a guardare il fatto — ma senza ricadere nell'errore
dell'illustrazione di categoria: il fatto decide DOVE sono i due e COSA
stanno facendo, non che cosa c'è disegnato al posto loro. I due
personaggi restano fissi come in biblioteca, e le parole restano quelle
vere del gruppo; a cambiare da un'edizione all'altra è la scena, che è
precisamente quello che in biblioteca non poteva cambiare.
"""

from __future__ import annotations

import base64
import random
import urllib.request
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from report import inchiostro, llm, spesa
from report.summarize import campione_citabile, trova_alla_lettera
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
        f"L'APERTURA del gazzettino di oggi è questa, e la vignetta le sta "
        f"accanto in prima pagina:\n«{tema}»\n\n"
        "Devi comporre la VIGNETTA del giorno SU QUEL FATTO: una scenetta "
        "con due personaggi che si dicono, alla lettera, cose che il gruppo "
        "ha scritto davvero su quel fatto.\n\n"
        "Le battute devono parlare della notizia qui sopra e di nient'altro. "
        "Una battuta bellissima su un altro argomento è la risposta "
        "sbagliata: in pagina finirebbe sotto quel titolo, e il lettore "
        "leggerebbe due cose che non c'entrano niente fra loro. Se sul "
        "fatto dell'apertura il gruppo non ha detto niente di riportabile, "
        "rispondi NESSUNA — la vignetta salta e non è un problema.\n\n"
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


# Sotto questo numero di candidati la selezione per sezione lascia troppo
# poco da scegliere, e una vignetta pescata fra sei frasi è peggio di una
# vignetta pescata larga: si torna a tutta la giornata.
_MINIMI_PER_SEZIONE = 12


# Quante frasi al massimo finiscono nel prompt della vignetta. Era la
# chiamata col rapporto peggiore di tutto il sistema: novantamila token in
# ingresso, su una giornata di partita, per riceverne ventinove. Il filtro
# di sezione da solo non basta, perché quando l'apertura è del Napoli la
# sezione dell'apertura È la sezione grossa.
_MAX_CANDIDATI = 400


def _candidati(
    messages_with_topic: list[tuple[str, "SimpleMessage"]],
) -> list[tuple[str, "SimpleMessage"]]:
    """Le frasi che possono diventare una battuta, in ordine di tempo."""
    return campione_citabile(
        messages_with_topic,
        tetto=len(messages_with_topic),  # nessun tetto qui: lo mette dopo
        minimo=_MIN_BATTUTA,
        massimo=_MAX_BATTUTA,
    )


def _della_sezione(candidati, topic_sezione) -> list:
    """I candidati che vengono dai topic da cui arriva l'apertura.

    È il vincolo che rende la vignetta il contorno della notizia invece di
    un fumetto qualsiasi in fondo alla pagina. Chiederlo nel prompt non
    basta: quando sul fatto di apertura il gruppo ha detto poco, il
    modello preferisce sempre una bella battuta fuori tema a un NESSUNA, e
    in pagina restano un titolone e due che parlano d'altro.

    Restringere qui è meccanico e non si può aggirare. Se però la sezione
    lascia troppo poco materiale si torna a tutta la giornata: meglio una
    vignetta scelta larga che nessuna vignetta, e a quel punto la
    coerenza torna a dipendere dal prompt."""
    if not topic_sezione:
        return candidati
    stretti = [(t, m) for t, m in candidati if t in topic_sezione]
    if len(stretti) < _MINIMI_PER_SEZIONE:
        print(
            f"Vignetta: solo {len(stretti)} frasi dai topic dell'apertura, "
            "troppo poche per scegliere. Guardo tutta la giornata."
        )
        return candidati
    return stretti


def _leggi(raw: str, toni: list[str]) -> tuple[str, list[str]]:
    """Tono e battute grezze, senza decidere ancora niente.

    La riga della battuta si prende intera, nome compreso: qui non si
    stacca l'autore e non si scarta niente per come è scritto. Prima
    questa funzione pretendeva la barra verticale e buttava in silenzio
    la battuta attribuita con un trattino — un controllo di formato
    travestito da controllo di verità, per giunta su un nome che poi
    nessuno usa: in pagina l'autore del balloon è quello del messaggio
    trovato. A dire di sì o di no è `componi`, e lo fa cercando la frase
    dentro i messaggi."""
    tono = ""
    battute: list[str] = []
    for riga in raw.splitlines():
        riga = riga.strip()
        if riga.upper().startswith("TONO:"):
            scelto = riga.split(":", 1)[1].strip().lower()
            if scelto in toni:
                tono = scelto
        elif riga.upper().startswith("BATTUTA:"):
            corpo = riga.split(":", 1)[1].strip().strip('"').strip("«»").strip()
            if corpo:
                battute.append(corpo)
    return tono, battute[:_MAX_BATTUTE]


def pick_vignetta(
    client,
    model: str,
    messages_with_topic: list[tuple[str, "SimpleMessage"]],
    *,
    tema: str,
    giorno: date,
    topic_sezione: set[str] | None = None,
    biblioteca: Biblioteca | None = None,
) -> Vignetta | None:
    """Sceglie tono e battute, e ci appoggia sopra un disegno.

    `tema` è titolo e sommario dell'apertura: la vignetta sta in prima
    accanto a quel pezzo, e deve raccontare quel fatto. `topic_sezione`
    sono i topic da cui l'apertura arriva, e restringono da dove possono
    venire le battute — è il vincolo vero, mentre il prompt è solo la
    richiesta.

    Restituisce None ogni volta che qualcosa non torna — biblioteca
    vuota, nessuna frase adatta, battute che non combaciano. Chi chiama
    ripiega sulla frase del giorno: il gazzettino esce comunque."""
    biblioteca = biblioteca if biblioteca is not None else Biblioteca()
    if not biblioteca:
        return None
    if not messages_with_topic or not tema:
        return None

    ristretti = _della_sezione(_candidati(messages_with_topic), topic_sezione)
    # Il tetto va per ultimo: prima si sceglie il recinto giusto (la
    # sezione dell'apertura), poi si sfoltisce dentro quel recinto.
    usable = campione_citabile(
        ristretti, _MAX_CANDIDATI, minimo=_MIN_BATTUTA, massimo=_MAX_BATTUTA
    )
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
    return componi(tono, battute, usable, giorno, biblioteca)


def componi(
    tono: str,
    battute: list[str],
    candidati,
    giorno: date,
    biblioteca: "Biblioteca",
) -> Vignetta | None:
    """Da tono e battute grezze alla vignetta, passando dalle verifiche.

    Sta separata dalla chiamata perché le battute possono arrivare da due
    posti: dalla chiamata dedicata, oppure — ed è la strada normale —
    dalla chiamata dell'apertura, che sceglie il fatto del giorno e le
    battute su quel fatto in un colpo solo. Le verifiche sono le stesse
    da qualunque parte arrivino, ed è il punto: non ci sono due strade,
    ce n'è una con due ingressi."""
    if not tono or not battute:
        print("Vignetta saltata: il modello non ha scelto un tono valido.")
        return None

    # Verifica di aderenza, una battuta alla volta. Una battuta inventata
    # non fa saltare la vignetta: sparisce lei, e se ne resta almeno
    # un'altra la scenetta si fa con un balloon solo.
    palloncini: list[Balloon] = []
    topic_scena = ""
    for riga in battute:
        trovato = trova_alla_lettera(riga, candidati)
        if trovato is None:
            print(f"Battuta scartata, non combacia con nessun messaggio: {riga!r}")
            continue
        testo, topic, m = trovato
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


def leggi_battute(raw_tono: str, righe: list[str], toni: list[str]):
    """Tono e battute da quello che ha risposto la chiamata dell'apertura."""
    testo = f"TONO: {raw_tono}\n" + "\n".join(f"BATTUTA: {r}" for r in righe)
    return _leggi(testo, toni)


# ------------------------------------------------------- il disegno del giorno

# I due protagonisti, sempre gli stessi. È l'unica cosa del disegno che
# NON cambia da un'edizione all'altra: se cambiassero anche loro, ogni
# giorno sarebbe un fumetto diverso invece che una striscia che continua.
# La descrizione è la stessa della biblioteca fatta a mano
# (`genera_prompt.py`), tradotta: i modelli di immagini capiscono meglio
# l'inglese, e qui sotto si tratta di dettagli minuti.
_PERSONAGGI = (
    "Always the same two Neapolitan football fans in their mid-thirties, "
    "ordinary people and not athletes: the one on the left is stocky, with "
    "short messy dark hair and a few days' stubble, wearing a plain t-shirt "
    "with no writing and no crest; the one on the right is thinner, dark "
    "hair with a fringe, a hoodie and often a plain scarf round his neck. "
    "Lively, expressive Italian hand gestures."
)

# Lo stile, che è l'unica cosa che tiene insieme due edizioni lontane un
# mese. Il bianco e nero è quello che va in pagina: la pagina ha una
# carta avorio, un inchiostro e un azzurro, e un'illustrazione con
# terracotta e ocra dentro si legge come un ritaglio di un altro
# giornale. Il blocco a colori resta per chi spegne l'interruttore.
_STILE_BIANCO_E_NERO = (
    "Black and white editorial comic illustration, Ligne Claire style, "
    "elegant French-Belgian graphic novel look, like a daily newspaper "
    "strip. STRICTLY MONOCHROME: black ink on warm ivory paper, no colour "
    "at all, no grey washes, no gradients, no digital shading — only black "
    "lines, a few solid black fills and the bare paper. Shadows, where they "
    "are needed, are a few thick parallel hatching lines."
)
_STILE_A_COLORI = (
    "Minimalist modern European comic illustration in Ligne Claire style, "
    "elegant French-Belgian graphic novel look. Clean, crisp black ink "
    "contour lines with plenty of negative space on a warm ivory background "
    "(#f2ece0). Flat solid fills, no gradients and no digital shading, with "
    "a single accent colour — a bright sky blue — used only on shirts and "
    "scarves; everything else is warm black on the bare ivory."
)

# Il tono lo ha già scelto il modello che ha letto la giornata: qui
# diventa il modo in cui i due stanno in scena. Sono sei, quindi sei
# disegni diversi anche a parità di luogo.
_ARIA = {
    "battibecco": (
        "the two are arguing: one holds the other back with an open palm "
        "while the other leans in, still talking over him"
    ),
    "esultanza": (
        "the two are celebrating: arms up, mouths wide open, one grabbing "
        "the other by the shoulders"
    ),
    "sconforto": (
        "the two are crushed: shoulders down, one with his head in his "
        "hands, the other staring at nothing"
    ),
    "complotto": (
        "the two are conspiring: heads close together, one pointing "
        "sideways with a knowing look, both glancing off-frame"
    ),
    "spiegone": (
        "one is lecturing the other, counting his points on his fingers, "
        "while the other listens unconvinced with folded arms"
    ),
    "attesa": (
        "the two are waiting, tense and still, both looking off-frame at "
        "the same point without speaking"
    ),
}

# Dove finiscono i due quando il fatto non suggerisce nessun posto — e
# solo allora. Sono i luoghi della biblioteca fatta a mano: Napoli si
# riconosce dai posti, che non invecchiano, e non dai fatti, che
# invecchiano in un giorno. La rotazione è ancorata alla data, come la
# scelta dei disegni di biblioteca: due edizioni di fila non ripiegano
# sullo stesso posto.
_LUOGHI_DI_RIPIEGO = (
    "in a living room in front of a switched-on television",
    "standing on the terraces of a stadium",
    "on the seafront promenade, leaning on the railing",
    "sitting on a parked scooter at a traffic light, helmets on",
    "at a table in a pizzeria, the wood oven burning behind them",
    "on a balcony at sunset, rooftops behind them",
    "inside a parked car, seen through the windscreen",
    "in an office, one hiding his phone under the desk",
    "in a five-a-side changing room, sitting on a bench",
    "standing in an underground train carriage, holding the bar",
    "outside a stadium in the rain, under umbrellas",
    "in front of a laptop screen in a small study",
)

# Quanto del pezzo di apertura finisce nel prompt della scena.
_MAX_CONTESTO = 1200


def _prompt_scena(tema: str, tono: str, battute: list[str], contesto: str) -> str:
    """Chiede DOVE e COSA, non «una scena».

    La versione precedente chiedeva una frase sola e le dava un esempio —
    due amici al tavolino di un bar con la tazzina — e il modello
    restituiva quell'esempio, giorno dopo giorno, con le parole cambiate.
    Un esempio in un prompt non è un'illustrazione di quello che si
    vuole: è la risposta più facile, e il modello la prende.

    Quindi niente esempio da copiare e una domanda per volta: il luogo
    deve venire dal FATTO — dove quella cosa lì si guarda, si aspetta, si
    subisce — e il bar è vietato per nome, perché è la scena che ogni
    modello propone quando non sa cosa proporre.
    """
    voci = "\n".join(f"- «{b}»" for b in battute if b)
    # Del pezzo di apertura basta l'inizio: il luogo della scena sta nei
    # primi capoversi — dove si è visto, dove si è aspettato — e il resto
    # sono dettagli che pagheremmo senza cambiare il disegno.
    ritaglio = contesto.strip()[:_MAX_CONTESTO]
    extra = f"\nCom'è andata, per esteso:\n{ritaglio}\n" if ritaglio else ""
    return (
        "Sei l'illustratore di un gazzettino sportivo napoletano. Ogni "
        "giorno disegni gli stessi due amici tifosi, e ogni giorno li "
        "disegni ALTROVE: la scena la decide il fatto di giornata, non "
        "l'abitudine.\n\n"
        f"IL FATTO DI OGGI, che è l'apertura del giornale:\n«{tema}»\n"
        f"{extra}\n"
        f"IL TONO con cui il gruppo ne ha parlato: {tono} — "
        f"{DESCRIZIONI.get(tono, '')}.\n"
        f"QUELLO CHE SI SONO DETTI:\n{voci}\n\n"
        "Rispondi con tre righe e nient'altro:\n\n"
        "LUOGO: dove sono i due, in poche parole. Deve nascere DAL FATTO: "
        "il posto da cui quella cosa lì si guarda, si aspetta, si "
        "festeggia o si subisce. Una partita in tv si guarda in salotto o "
        "in un bar dello sport; un'asta di fantacalcio si fa davanti a un "
        "portatile; una trasferta si commenta in auto o in treno; una "
        "notizia di mercato arriva sul telefono mentre si fa altro — in "
        "fila, in ufficio, al mercato, sul motorino. Scegli il posto che "
        "racconta QUESTO fatto, e se il fatto ne ammette più d'uno prendi "
        "il meno scontato: il giornale esce tutti i giorni, e il lettore "
        "il salotto l'ha già visto.\n"
        "VIETATO il tavolino del bar con le tazzine di caffè, a meno che "
        "il fatto non parli proprio di un bar: è la scena che esce "
        "sempre, ed è il motivo per cui questa riga esiste.\n"
        "AZIONE: cosa stanno facendo in quel momento — il gesto e la "
        "posizione dei corpi, non l'emozione raccontata a parole.\n"
        "OGGETTO: un oggetto di scena che viene dal fatto e si può "
        "disegnare senza scriverci sopra niente (una sciarpa, un "
        "telecomando, un ombrello, un borsone, una moka, un pallone "
        "sgonfio). Se non ce n'è uno che c'entra, scrivi: nessuno.\n\n"
        "Vincoli: due personaggi soli, nessuna folla, ambientazione "
        "essenziale, nessuna scritta, nessuno stemma, nessuna persona "
        "reale o riconoscibile."
    )


def _leggi_scena(raw: str) -> tuple[str, str, str]:
    """Luogo, azione e oggetto dalle tre righe etichettate.

    Le etichette sono la stessa scelta del resto del gazzettino (vedi
    `docs/grafica.md`): un formato posizionale sbaglia in silenzio, uno a
    etichette no. Quello che non arriva resta vuoto e lo rimette chi
    chiama, una riga alla volta: una risposta a metà vale comunque più
    del ripiego intero.
    """
    campi = {"LUOGO": "", "AZIONE": "", "OGGETTO": ""}
    for riga in raw.splitlines():
        riga = riga.strip().lstrip("-*• ").replace("**", "")
        for etichetta in campi:
            if riga.upper().startswith(etichetta):
                corpo = riga.split(":", 1)[1].strip() if ":" in riga else ""
                if corpo and not campi[etichetta]:
                    campi[etichetta] = corpo.strip('"').strip("«»").strip()
    oggetto = campi["OGGETTO"]
    if oggetto.lower().rstrip(".") in {"nessuno", "nessun oggetto", "niente", "-"}:
        oggetto = ""
    return campi["LUOGO"], campi["AZIONE"], oggetto


def _prompt_disegno(
    luogo: str, azione: str, oggetto: str, tono: str, bianco_e_nero: bool = True
) -> str:
    """Il prompt dell'immagine: i due fissi, la scena del giorno, la carta.

    Il modello che disegna non sa niente della notizia: riceve la scena
    già ricavata, i personaggi che non cambiano mai e i vincoli della
    pagina. È la difesa di `docs/grafica.md` — il soggetto da un
    passaggio separato — e serve a non far arrivare titoli, nomi e
    numeri dentro un'immagine che non deve contenere scritte.
    """
    aria = _ARIA.get(tono, "")
    scena = ", ".join(p.strip().rstrip(".") for p in (azione, luogo) if p.strip())
    with_oggetto = f" Visible in the scene: {oggetto.rstrip('.')}." if oggetto else ""
    return (
        f"{_STILE_BIANCO_E_NERO if bianco_e_nero else _STILE_A_COLORI} "
        f"THE SCENE OF THE DAY: {scena}."
        f"{with_oggetto} "
        f"{('The mood: ' + aria + '. ') if aria else ''}"
        f"{_PERSONAGGI} "
        "Composition: wide horizontal framing, the two characters together "
        "in the middle of the frame, the setting suggested with few lines "
        "and lots of empty paper around them; the picture will be cropped "
        "to a wide strip, so keep nothing important in the top and bottom "
        "sixth of the image. Few, thick, confident lines: it will be looked "
        "at about six hundred pixels wide on a phone. "
        "MANDATORY: NO text, NO letters, NO numbers, NO speech bubbles or "
        "empty balloons anywhere in the image. NO crowds, NO background "
        "clutter, NO photorealism, NO dense cross-hatching, NO team crests, "
        "logos or official kits, NO real or recognisable people, NO frame, "
        "NO signature."
    )


def generate_ai_drawing(
    client,
    dest_path: Path | str,
    *,
    tema: str,
    tono: str,
    battute: list[str],
    contesto: str = "",
    giorno: date | None = None,
    text_model: str = "gpt-4o-mini",
    image_model: str = "gpt-image-2",
    bianco_e_nero: bool = True,
) -> Path | None:
    """Il disegno dell'edizione: gli stessi due, in una scena che è di oggi.

    Due chiamate, e la divisione conta. La prima legge il fatto del
    giorno e decide DOVE si svolge la scena e COSA stanno facendo i due;
    la seconda disegna e non sa niente della notizia — riceve solo la
    scena, i personaggi fissi e i vincoli della pagina. È la difesa
    vecchia di `docs/grafica.md` (il soggetto da un passaggio separato),
    e serve a non far arrivare titoli, nomi e numeri dentro un'immagine
    che non deve contenere scritte.

    Quello che cambia ogni giorno è la scena; quello che non cambia mai
    sono i due amici e la tavolozza. `contesto` è il pezzo di apertura
    per esteso: senza, il modello ha solo un titolo e un sommario, e da
    due righe il luogo che ne ricava è sempre il più generico che ci sia.
    """
    prompt_scena = _prompt_scena(tema, tono, battute, contesto)
    try:
        # Più alta di prima (era 0.5): qui la varietà È il requisito, e
        # sui modelli di ragionamento la temperatura viene omessa da sola
        # in llm.complete.
        raw = llm.complete(client, text_model, prompt_scena, temperature=0.9)
    except Exception as exc:
        print(f"Descrizione scena vignetta fallita ({exc}).")
        raw = ""

    luogo, azione, oggetto = _leggi_scena(raw)
    if not luogo:
        # Il ripiego non è una scena qualunque: è un luogo della
        # rotazione, diverso da quello di ieri. Un ripiego fisso sarebbe
        # di nuovo lo stesso disegno tutti i giorni, che è il difetto da
        # cui si parte.
        indice = (giorno or date.today()).toordinal() % len(_LUOGHI_DI_RIPIEGO)
        luogo = _LUOGHI_DI_RIPIEGO[indice]
        print(f"  Luogo non ricavato dal fatto, ripiego sulla rotazione: {luogo}")
    if not azione:
        azione = "the two friends are talking about what just happened"

    print(f"  Scena del giorno: {azione} — {luogo}" + (f" [{oggetto}]" if oggetto else ""))

    prompt_disegno = _prompt_disegno(luogo, azione, oggetto, tono, bianco_e_nero)

    sizes_to_try = ["1536x1024", "1024x1024"]
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    for sz in sizes_to_try:
        try:
            print(f"  Chiamo OpenAI Images ({image_model}, {sz})...")
            response = client.images.generate(
                model=image_model,
                prompt=prompt_disegno,
                size=sz,
                quality="medium",
                n=1,
            )
            payload = getattr(response.data[0], "b64_json", None)
            if payload:
                dest.write_bytes(base64.b64decode(payload))
                spesa.registra_immagine(image_model)
                return _sulla_carta(dest, bianco_e_nero)
            url = getattr(response.data[0], "url", None)
            if url:
                urllib.request.urlretrieve(url, dest)
                spesa.registra_immagine(image_model)
                return _sulla_carta(dest, bianco_e_nero)
        except Exception as exc:
            print(f"  Tentativo con size {sz} fallito ({exc}).")
            continue

    print("Generazione disegno vignetta con OpenAI fallita. Ripiego sulla biblioteca.")
    return None


def _sulla_carta(dest: Path, bianco_e_nero: bool) -> Path:
    """L'ultimo passaggio: il disegno diventa inchiostro sulla nostra carta.

    Il prompt il monocromo lo chiede già, ma un prompt è una richiesta e
    un modello di immagini il colore lo rimette — un riflesso azzurro,
    una parete ocra — e in pagina si vede. Qui non si chiede: si
    converte. Fallisce senza conseguenze (Pillow assente, file
    illeggibile): esce il disegno com'è, che vale comunque più di
    nessun disegno.
    """
    if bianco_e_nero:
        inchiostro.stampa_in_bianco_e_nero(dest)
    return dest
