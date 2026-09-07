"""Composizione del gazzettino in stile "Azzurro Fluido".

Scelte che reggono tutto il resto del file:

- **la prima pagina è una vetrina, non la prima puntata.** Porta gli
  strilli, l'apertura fino al primo capoverso, la spalla e il sommario
  dell'edizione; gli articoli per intero cominciano da pagina 2. È la
  differenza fra un giornale e un rotolo di testo: chi apre la prima
  deve sapere che cosa c'è dentro e a che pagina, e per saperlo non deve
  scorrere fino in fondo.
- **il testo va su due colonne**, corpo 24-26px su una misura di ~40
  caratteri. Nessun altro mezzo impagina così: è il segno che l'occhio
  riconosce come "giornale" prima di leggere una parola. Sotto queste
  misure la ricompressione JPEG di Telegram comincia a mangiare le
  grazie, e sopra le colonne diventano due elenchi.
- palette e marchio del canale (navy #0c2340 / azzurro #17a3e0), così il
  report si riconosce nello scroll della chat.
- **nessuna immagine** oltre al logo della testata e alla vignetta: il
  peso visivo lo fanno la tipografia e i dati. Il perché sta in
  docs/grafica.md.
- ogni pezzo ha tre gradini — titolo, sommario, testo — più un
  virgolettato di chi c'era, e i topic minori finiscono nel box "In
  breve" invece di avere un articolo ciascuno: con tredici topic attivi,
  tredici pezzi uguali sono una schedina.
- le pagine sono quante ne servono, sotto la stessa altezza utile e
  ridistribuite perché vengano simili fra loro.

I rimandi ("a pagina 3") impongono di impaginare in due passate: prima si
distribuiscono gli articoli sulle pagine interne, poi si costruisce la
prima con i numeri che ne sono usciti. Vedi build_pages_html.
"""

import base64
import html
import mimetypes
import os
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from report.graphics import (
    hourly_chart_svg,
    share_bar_svg,
    topic_glyph_svg,
    weight_bar_svg,
)

# La carta prima dell'inchiostro.
#
# Un quotidiano non è stampato su bianco: la Gazzetta è rosa, il Foglio è
# avorio, e il colore della carta è la prima cosa che si riconosce da
# lontano, prima di qualunque titolo. Qui è avorio, quella da edicola.
#
# Il primo tentativo era una carta azzurrina, per portare sul fondo
# l'azzurro tolto dal testo. Era l'idea più elegante e non ha retto la
# prova: al tono giusto per essere elegante non si vedeva — tre varianti
# messe una accanto all'altra erano indistinguibili — e alzato quanto
# serviva a vederlo, finiva per fare concorrenza all'azzurro del marchio
# e delle vignette. Due azzurri diversi nella stessa pagina.
#
# L'avorio li lascia parlare: l'azzurro resta uno solo, quello del
# Napoli, e sta dove serve — il marchio, il filetto della testata, i
# rimandi di pagina.
#
# Perché quello che conta è comunque il contrario di prima: l'azzurro
# brillante stava nei sommari, nelle etichette e nei rimandi, cioè sul
# testo, e una pagina di testo azzurro somiglia a un sito.
PAPER = "#f2ece0"
PAPER_DEEP = "#e6dcc9"      # il fondo dei riquadri, mezzo tono più giù
RULE = "#c3b9a4"            # il filetto sottile, quello che fa la griglia

# Il fondo scuro: piede di pagina e fascia dei numeri, non più la
# testata. È un blu quasi nero — deve leggersi come inchiostro.
NAVY = "#0a1c2b"

# L'azzurro da stampa, per gli accenti. Più profondo e più sporco di
# quello del marchio: quello brillante regge su fondo scuro, su carta
# chiara diventa il colore di un collegamento.
AZZURRO = "#0d6f9f"
AZZURRO_DEEP = "#0a4b6d"
AZZURRO_BRIGHT = "#17a3e0"  # solo il filetto della testata e il fine pezzo
AZZURRO_PALE = "#8fc9e8"    # solo sopra il fondo scuro

GROUND = PAPER_DEEP  # nel giornale non si usa più: lo tiene catalogo.py
# Su carta calda l'inchiostro freddo stona: il nero dei giornali tira al
# bruno, non al blu. Sono due punti di tinta, e sono la differenza fra
# una pagina stampata e una pagina bianca colorata di beige.
INK = "#181612"
INK_SOFT = "#544d42"

PAGE_WIDTH = 1080

# Il pannello della vignetta: la colonna intera meno i due margini da 56.
# L'altezza non è il 3:2 dell'originale ma un formato più basso e largo —
# una striscia, non un quadro — e costa un ritaglio del 13% sopra e sotto.
# È il compromesso che tiene i balloon lontani dalle teste: i disegni
# della biblioteca hanno le teste sotto la metà dell'immagine, e quello
# che si perde nel ritaglio è il cielo vuoto che sta sopra.
# Da quando l'apertura sta su una colonna e non sulla pagina intera, il
# disegno prende la larghezza di quella colonna: è la foto dell'articolo,
# e una foto che sborda dalla colonna del pezzo non è impaginazione, è
# un banner.
_VIGNETTA_WIDTH = 616
_VIGNETTA_HEIGHT = 356

# Oltre questa altezza stimata (in px CSS) la pagina diventa una striscia
# troppo lunga: Telegram la mostra rimpicciolita in anteprima e il testo
# torna illeggibile. Il tetto vale per OGNI pagina: superarlo apre la
# successiva, quante volte serve.
MAX_PAGE_HEIGHT = 2400

# Margine di sicurezza sulla coda dell'ultima pagina. Le stime dei blocchi
# fissi sono misurate una per una, ma si sommano: sull'ultima pagina se ne
# accumulano cinque o sei, e bastano pochi pixel di scarto ciascuno perché
# il totale scavalchi il tetto. Un margine è più onesto che gonfiare le
# singole costanti fino a farle mentire.
_MARGINE_CODA = 60

# Da quando la prima pagina è una vetrina, il tetto di notizie che poteva
# portare non serve più: non ne porta nessuna. La gerarchia la fa la
# scala degli elementi — apertura, spalla, strilli, sommario — e non più
# il conteggio dei pezzi sopra il taglio.

# Oltre questa posizione in classifica un topic non ha un articolo suo ma
# una riga nel box "In breve". Con tredici topic attivi, tredici articoli
# della stessa forma sono una schedina, non un giornale: la gerarchia si
# vede solo se qualcosa è grande e qualcos'altro è piccolo.
MAX_FULL_ARTICLES = 5

_IT_WEEKDAYS = [
    "Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"
]
_IT_MONTHS = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]

FOOTER_NOTE = "Azzurro Fluido · gazzettino automatico del gruppo"
CHANNEL_LINK = "youtube.com/@AzzurroFluido"

# Lo spazio unificatore lega il quadratino all'ultima parola: senza, quando
# la riga finale è piena, il segno di chiusura scende da solo su una riga
# tutta sua e sembra un errore di impaginazione.
END_MARK = '&#160;<span class="end-mark"></span>'


@dataclass
class Lead:
    # Sezione da cui arriva la notizia di apertura, dichiarata da chi
    # scrive il pezzo. Vuota quando il fatto ne attraversa più d'una: in
    # pagina resta il solo "Apertura", che è meglio di una sezione che non
    # c'entra con il titolo che le sta sotto.
    kicker: str
    headline: str
    deck: str
    paragraphs: list[str] = field(default_factory=list)
    quote: "Quote | None" = None

    # Quanti capoversi dell'apertura restano in prima. Due e non uno: con
    # uno solo il titolone resta sospeso su tre righe di testo e la prima
    # pagina sembra un manifesto, non un giornale. Con tutti, non è più
    # una vetrina.
    CAPOVERSI_IN_PRIMA = 2

    @property
    def attacco(self) -> list[str]:
        """I capoversi che stanno in prima pagina.

        Un'apertura di giornale non si esaurisce sotto la testata: dà la
        notizia e rimanda al servizio dentro. Il taglio regge perché il
        primo capoverso è scritto per bastare da solo — vedi la regola
        dell'attacco in summarize.py."""
        return self.paragraphs[: self.CAPOVERSI_IN_PRIMA]

    @property
    def seguito(self) -> list[str]:
        """Il resto dell'apertura, che riprende sulla pagina dopo."""
        return self.paragraphs[self.CAPOVERSI_IN_PRIMA :]


@dataclass
class Article:
    topic: str
    headline: str
    body: str
    count: int
    # Il virgolettato: una frase di un membro del gruppo, riportata alla
    # lettera dentro il pezzo. È quello che distingue un articolo da un
    # riassunto — un pezzo di cronaca dà la parola a chi c'era — e passa
    # dalla stessa verifica di aderenza della frase del giorno.
    quote: "Quote | None" = None
    # Sommario: la riga fra titolo e testo che aggiunge informazione
    # invece di riformulare il titolo. Senza, un pezzo è titolo e blocco
    # di testo — che è quello che rende una pagina un elenco invece di un
    # giornale.
    deck: str = ""
    # Sezione tematica e famiglia del topic (vedi report/sections.py). La
    # sezione decide dove il pezzo va in pagina, la famiglia se il pezzo
    # concorre agli articoli pieni o finisce nel blocco compatto dei suoi
    # simili.
    section: str = ""
    family: str = ""


@dataclass
class FamilyBlock:
    """Un gruppo di topic della stessa forma, impaginati insieme.

    Espone `headline`, `count` e `topic` perché la paginazione lo tratti
    come un pezzo qualsiasi: il blocco occupa spazio in colonna come un
    articolo, e non c'è motivo di insegnare due tipi diversi a chi
    distribuisce le notizie sulle pagine."""

    label: str
    section: str
    items: list[Article] = field(default_factory=list)

    @property
    def headline(self) -> str:
        return self.label

    @property
    def topic(self) -> str:
        return self.label

    @property
    def count(self) -> int:
        return sum(i.count for i in self.items)


@dataclass
class Stats:
    messages: int
    participants: int
    active_topics: int
    peak_hour: str


@dataclass
class Quote:
    text: str
    author: str
    topic: str = ""
    time: str = ""


@dataclass
class Balloon:
    """Una battuta della vignetta: parole del gruppo, alla lettera.

    `text` non viene mai riscritto né accorciato: è la stessa difesa
    della frase del giorno, e qui conta di più, perché un fumetto sembra
    per sua natura una cosa inventata. Se le parole non sono vere, la
    vignetta è una barzelletta con dei nomi veri sotto."""

    text: str
    author: str
    time: str = ""


@dataclass
class Vignetta:
    """La scenetta del giorno: un disegno della biblioteca più le battute.

    Assorbe la frase del giorno invece di aggiungersi: sono la stessa
    cosa detta in due forme — uno scambio a due voci quando la giornata
    ne ha uno, un balloon solo quando la frase è rimasta senza risposta.

    Il disegno non illustra il fatto (non può: è stato disegnato prima),
    illustra il tono con cui il gruppo ne ha parlato. A legarlo alla
    giornata sono le parole nei balloon, che invece di quel giorno sono."""

    image_path: str | Path
    balloons: list[Balloon] = field(default_factory=list)
    # Da dove arriva lo scambio: topic e ora. Sta sotto il pannello come
    # una didascalia di giornale, non dentro il disegno.
    topic: str = ""
    # Il tono che ha scelto il disegno. In pagina non compare: serve a
    # chi legge i log a capire perché è uscito quel disegno lì.
    tone: str = ""


@dataclass
class GraphicsOptions:
    """Quali elementi grafici accendere.

    Sono separati uno per uno perché non hanno lo stesso rischio: il
    capolettera è una convenzione tipografica e non può stonare, i
    pittogrammi sui topic sì — bastano due segni che non c'entrano niente
    con il titolo e la pagina sembra fatta con le clipart. Tenerli
    distinti permette di spegnere il singolo elemento senza tornare alla
    pagina di solo testo.
    """

    drop_cap: bool = True       # capolettera sull'apertura
    end_mark: bool = True       # quadratino di fine articolo
    hourly_chart: bool = True   # andamento orario nella fascia di chiusura
    weight_bars: bool = True    # barretta di peso accanto al contatore messaggi
    topic_glyphs: bool = True   # pittogramma nei tag dei pezzi e in breve
    share_bar: bool = True      # barra delle proporzioni sotto l'indice
    number_block: bool = True   # il dato grande sotto l'indice
    brief_box: bool = True      # i topic minori raccolti in un box "In breve"

    @classmethod
    def none(cls) -> "GraphicsOptions":
        """Il gazzettino com'era prima di questo modulo."""
        return cls(
            drop_cap=False,
            end_mark=False,
            hourly_chart=False,
            weight_bars=False,
            topic_glyphs=False,
            share_bar=False,
            number_block=False,
            brief_box=False,
        )


def italian_date(day: date) -> str:
    return f"{_IT_WEEKDAYS[day.weekday()]} {day.day} {_IT_MONTHS[day.month - 1]} {day.year}"


def short_italian_date(day: date) -> str:
    return f"{_IT_WEEKDAYS[day.weekday()][:3]} {day.day} {_IT_MONTHS[day.month - 1][:3]} {day.year}"


def giorno_e_mese(day: date) -> str:
    """Il giorno per le rubriche: senza l'anno e in minuscolo.

    Le rubriche lo portano dentro una frase — «le notizie di sabato 6
    settembre» — e in maiuscoletto spaziato l'anno sarebbe una riga più
    lunga per dire una cosa che nessuno si sta chiedendo: il giornale ha
    già la data completa in testata."""
    return f"{_IT_WEEKDAYS[day.weekday()].lower()} {day.day} {_IT_MONTHS[day.month - 1]}"


def data_uri(path: str | Path) -> str:
    """Playwright riceve l'HTML con set_content: i percorsi relativi non
    hanno una base da cui risolvere, quindi le immagini vanno incorporate."""
    path = Path(path)
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


CSS = f"""
* {{ box-sizing: border-box; }}
body {{
  margin: 0; width: {PAGE_WIDTH}px;
  background: {PAPER}; color: {INK};
  /* Titoli e testo in graziato. È il cambio che si vede da più lontano
     di tutti: nessun quotidiano al mondo titola in bastoni, e il bastone
     era la ragione per cui questa pagina somigliava a un sito. */
  font-family: Newsreader, 'Times New Roman', Georgia, serif;
  font-weight: 400;
}}
h1, h2, h3 {{ margin: 0; font-weight: 800; letter-spacing: -0.015em; }}
p {{ margin: 0; }}

/* Il bastone resta, ma solo per gli arredi: occhielli, etichette di
   sezione, data, rimandi, numeri di pagina. È il contrasto che hanno
   tutti i giornali veri — la notizia in graziato, le indicazioni di
   servizio in bastoni — e serve a distinguere a colpo d'occhio quello
   che è scritto da quello che è segnaletica. */
.kicker, .section-label, .dateline, .rimando, .folio, .chip,
.strillo .sez, .strillo .pag, .dentro-row .sez, .dentro-row .pag,
.band, .brief-head, .footer, .footer-continue, .stats, .numero,
.continuation, .vignetta .didascalia, .balloon .chi {{
  font-family: Archivo, 'Helvetica Neue', Arial, sans-serif;
}}
/* Nessun angolo arrotondato in tutto il documento: la struttura la fanno
   i regoli e gli allineamenti, non le smussature. */

/* La testata sta sulla carta, non su un blocco di colore, ed è centrata
   fra due filetti. È la forma che ha la testata di qualunque quotidiano,
   e il blocco scuro era la cosa che più di ogni altra faceva leggere
   questa pagina come l'intestazione di un sito.

   Ha richiesto una seconda versione del marchio: quello originale ha il
   contorno bianco, fatto per il fondo scuro, e su carta chiara le lettere
   si sfaldavano. In assets/logo-carta.png il contorno è di inchiostro. */
.masthead {{
  background: {PAPER}; padding: 24px 56px 14px 56px; text-align: center;
  border-top: 3px solid {INK};
}}
.masthead-row {{ display: block; }}
.masthead img {{ width: 600px; display: block; margin: 0 auto; }}
.masthead .tagline {{
  text-align: center; color: {INK_SOFT}; font-size: 13px; font-weight: 800;
  letter-spacing: 0.3em; text-transform: uppercase; margin-top: 12px;
  line-height: 1.4;
}}
.rule-accent {{ height: 5px; background: {AZZURRO_BRIGHT}; }}

.dateline {{
  display: flex; justify-content: space-between; align-items: baseline;
  padding: 14px 56px; background: {PAPER};
  border-top: 1px solid {INK}; border-bottom: 3px solid {INK};
  font-size: 17px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase;
}}
.dateline .folio {{ color: {AZZURRO}; }}

.section-label {{
  font-size: 15px; font-weight: 800; letter-spacing: 0.14em;
  text-transform: uppercase; color: {AZZURRO};
}}

.index {{ padding: 22px 56px 24px 56px; background: {PAPER}; border-bottom: 2px solid {INK}; }}
.index .section-label {{ display: block; margin-bottom: 14px; }}
.index-chips {{ display: flex; flex-wrap: wrap; gap: 10px; }}
/* Le chip dell'indice sono le sezioni dell'edizione, non i topic: sono
   in maiuscoletto spaziato come le testate di sezione più in basso,
   perché sono la stessa cosa vista da due distanze. */
.chip {{
  display: inline-flex; align-items: center; gap: 10px;
  border: 2px solid {NAVY}; padding: 7px 13px; font-size: 17px; font-weight: 800;
  letter-spacing: 0.08em; text-transform: uppercase;
}}
.chip b {{ color: {AZZURRO_DEEP}; }}
.chip .glyph {{ color: {AZZURRO_DEEP}; flex: none; }}
.share {{ display: block; margin-top: 14px; }}

.lead {{ padding: 30px 56px 26px 56px; background: {PAPER}; }}
.kicker {{
  display: inline-block; background: {NAVY}; color: #fff; font-size: 15px;
  font-weight: 800; letter-spacing: 0.14em; text-transform: uppercase;
  padding: 7px 12px; margin-bottom: 18px;
}}
.lead h2 {{ font-size: 66px; line-height: 1.02; letter-spacing: -0.03em; margin-bottom: 18px; }}
.lead .deck {{
  font-size: 27px; line-height: 1.32; color: {INK_SOFT};
  font-weight: 500; font-style: italic; margin-bottom: 20px;
  padding-bottom: 18px; border-bottom: 1px solid {RULE};
}}
/* Il testo su due colonne è la firma di un giornale stampato: nessun
   altro mezzo impagina così, e il colpo d'occhio la riconosce prima di
   leggere una parola. Costa corpo — 26px invece di 30 — ma su una
   colonna da 456px sono quaranta caratteri per riga, che è esattamente
   la misura di una colonna di quotidiano. */
.lead .body {{
  font-size: 26px; line-height: 1.46;
  column-count: 2; column-gap: 40px;
  /* Il filetto fra le colonne: in tipografia si chiama filetto di
     separazione e serve all'occhio per non saltare da una colonna
     all'altra a metà riga. */
  column-rule: 1px solid {RULE};
}}
.lead .body p {{ margin-bottom: 14px; }}
.lead .body p:last-child {{ margin-bottom: 0; }}

/* Capolettera: fa partire l'articolo di apertura da un punto preciso
   invece che dal margine come tutti gli altri paragrafi. È la differenza
   fra una pagina impaginata e un blocco di testo. Il float lo tiene
   allineato alla riga di base della terza riga. */
.lead .body.dropcap > p:first-child::first-letter {{
  float: left; font-size: 80px; line-height: 0.76; font-weight: 800;
  color: {NAVY}; padding: 6px 11px 0 0;
}}

/* --- Prima pagina: la griglia -----------------------------------------
   Una prima pagina di quotidiano non è una pila di fasce larghe quanto la
   pagina: è una griglia di colonne di larghezza diversa. L'occhio
   riconosce quello prima di leggere una parola, ed è la ragione per cui
   la vecchia prima pagina — apertura a tutta pagina, poi un riquadro
   grigio a tutta pagina, poi una tabella a tutta pagina — somigliava a un
   sito anche quando quello che c'era scritto era giusto.

   La griglia è quella classica dei quotidiani italiani: la notizia di
   apertura sulla colonna larga, e a destra la colonna stretta con i
   richiami al resto del giornale. Fra le due un filetto verticale, che è
   il segno che fa la griglia. */
.vetrina {{
  display: flex; align-items: stretch;
  padding: 26px 56px 24px 56px; background: {PAPER};
  border-bottom: 3px solid {INK};
}}
.vetrina-main {{ flex: 1; min-width: 0; padding-right: 30px; }}
.vetrina-side {{
  flex: none; width: 292px; padding-left: 30px;
  border-left: 1px solid {INK};
}}
/* Dentro la griglia l'apertura non ha più margini suoi: i margini li dà
   la colonna. */
.vetrina .lead {{ padding: 0; background: transparent; border: none; }}
.vetrina .lead h2 {{ font-size: 58px; }}
.vetrina .lead .body {{ font-size: 22px; line-height: 1.44; column-gap: 30px; }}
.vetrina .lead .body.dropcap > p:first-child::first-letter {{
  font-size: 68px; padding: 5px 9px 0 0; color: {INK};
}}

/* --- Prima pagina: la vetrina -----------------------------------------
   Una prima pagina non è la prima puntata del giornale, è la sua vetrina:
   dice che cosa c'è dentro e dove. Da qui gli strilli in alto, la spalla
   accanto all'apertura e il sommario dell'edizione in fondo — tutti e tre
   rimandano a una pagina, e nessuno dei tre esaurisce il pezzo. */

/* Gli strilli (in gergo: le civette) sono le tre righe sopra la testata
   che annunciano il resto del giornale. Stanno su fondo navy perché
   appartengono alla testata, non alla notizia sotto. */
/* I richiami stanno in colonna, uno sotto l'altro, separati da un
   filetto: è la forma che hanno su qualunque prima pagina. Prima erano
   tre caselle affiancate su fondo scuro sopra la testata — una fascia da
   sito di notizie, non una colonna di giornale. */
.strilli {{ background: transparent; padding: 0; display: block; }}
.strillo {{
  padding: 0 0 15px 0; margin-bottom: 15px;
  border-left: none; border-bottom: 1px solid {RULE};
}}
.strillo:last-child {{ border-bottom: none; margin-bottom: 0; padding-bottom: 0; }}
.strillo .sez {{
  display: block; font-size: 12px; font-weight: 800; letter-spacing: 0.14em;
  text-transform: uppercase; color: {AZZURRO}; margin-bottom: 6px;
}}
.strillo p {{
  font-size: 22px; line-height: 1.14; font-weight: 700; color: {INK};
  letter-spacing: -0.015em;
}}
.strillo .pag {{
  display: block; margin-top: 7px; font-size: 12px; font-weight: 800;
  letter-spacing: 0.1em; text-transform: uppercase; color: {INK_SOFT};
}}

/* Il rimando in coda all'apertura: dove continua il pezzo. */
.rimando {{
  margin-top: 18px; padding-top: 14px; border-top: 1px solid {INK};
  font-size: 18px; font-weight: 800; letter-spacing: 0.06em;
  text-transform: uppercase; color: {AZZURRO};
}}

/* La spalla: la seconda notizia della giornata, in prima ma sotto
   l'apertura e visibilmente più piccola. Il fondo grigio la stacca senza
   bisogno di un riquadro. */
/* La seconda notizia sta sotto il taglio, a tutta pagina e su tre
   colonne: la larghezza e il numero di colonne sono il modo in cui una
   pagina dice che questo pezzo conta meno di quello sopra e più di un
   richiamo. Niente fondo grigio — a separarla basta il filetto spesso. */
.spalla {{
  background: {PAPER}; border-bottom: 3px solid {INK};
  padding: 24px 56px 24px 56px;
}}
.spalla .section-label {{ display: block; margin-bottom: 12px; }}
.spalla h3 {{ font-size: 36px; line-height: 1.06; letter-spacing: -0.015em; margin-bottom: 10px; }}
.spalla .deck {{
  font-size: 23px; line-height: 1.3; color: {INK_SOFT}; font-weight: 500;
  font-style: italic; margin-bottom: 14px;
}}
.spalla .body {{ font-size: 23px; line-height: 1.46; column-count: 3; column-gap: 32px;
  column-rule: 1px solid {RULE}; }}
.spalla .rimando {{ margin-top: 16px; padding-top: 13px; font-size: 19px; }}

/* Il sommario dell'edizione: una riga per sezione, con il titolo migliore
   e la pagina. Prende il posto delle chip dell'indice, che dicevano
   quanti messaggi e non che cosa c'era scritto. */
.dentro {{ background: {PAPER}; padding: 26px 56px 28px 56px; }}
.dentro .section-label {{ display: block; margin-bottom: 16px; }}
.dentro-row {{
  display: flex; align-items: baseline; gap: 20px;
  padding: 13px 0; border-top: 1px solid #d6dade;
}}
.dentro-row:first-of-type {{ border-top: 2px solid {NAVY}; }}
.dentro-row .sez {{
  flex: none; width: 190px; font-size: 16px; font-weight: 800;
  letter-spacing: 0.11em; text-transform: uppercase; color: {NAVY};
}}
/* La riga di mezzo dice quanto pesa la sezione, non che cosa c'è scritto:
   i titoli li hanno già gli strilli, e ripeterli qui farebbe della prima
   pagina un indice. Corpo e peso sono quelli di una nota, non di un
   titolo. */
.dentro-row p {{ flex: 1; font-size: 19px; line-height: 1.25; font-weight: 600;
  color: {INK_SOFT}; letter-spacing: 0.02em; }}
/* Nella colonna stretta il sommario perde la riga di mezzo: sezione e
   pagina bastano, ed è esattamente quello che dice un "Dentro il
   giornale" vero. */
.vetrina-side .dentro {{
  padding: 0; margin-top: 22px; padding-top: 16px;
  border-top: 2px solid {INK}; background: transparent;
}}
.vetrina-side .dentro-row {{ padding: 8px 0; gap: 10px; border-top: 1px solid {RULE}; }}
.vetrina-side .dentro-row:first-of-type {{ border-top: none; }}
.vetrina-side .dentro-row .sez {{ width: auto; flex: 1; font-size: 14px; color: {INK}; }}
.vetrina-side .dentro-row p {{ display: none; }}
.vetrina-side .dentro-row .pag {{ font-size: 13px; }}

.dentro-row .pag {{
  flex: none; font-size: 14px; font-weight: 800; letter-spacing: 0.08em;
  text-transform: uppercase; color: {AZZURRO};
}}

/* Il seguito dell'apertura in apertura di pagina 2. Ripete il titolo in
   piccolo — chi ha girato pagina deve ritrovare il pezzo che stava
   leggendo — e non ripete occhiello né sommario. */
.segue {{ background: {PAPER}; padding: 30px 56px 28px 56px; border-bottom: 3px solid {INK}; }}
.segue .section-label {{ display: block; margin-bottom: 10px; }}
.segue h3 {{ font-size: 34px; line-height: 1.08; margin-bottom: 18px; }}
.segue .body {{ font-size: 25px; line-height: 1.5; column-count: 2; column-gap: 40px;
  column-rule: 1px solid {RULE}; }}
.segue .body p {{ margin-bottom: 14px; }}
.segue .body p:last-child {{ margin-bottom: 0; }}

/* Quadratino di fine pezzo: dice dove finisce l'articolo senza bisogno
   di un regolo, che a fine colonna aggiungerebbe una riga di stacco.
   Nel markup è preceduto da uno spazio unificatore, così non può finire
   da solo su una riga tutta sua — che è il modo più veloce di far
   sembrare rotta una pagina altrimenti a posto. */
.end-mark {{
  display: inline-block; width: 15px; height: 15px;
  background: {AZZURRO}; position: relative; top: 1px;
}}

/* La colonna delle notizie sta sulla carta come tutto il resto.
   Il fondo più scuro qui era il residuo di quando la pagina era grigia e
   i blocchi erano riquadri bianchi appoggiati sopra — un modo di
   impaginare che è dei siti e non dei giornali. Da quando il fondo è
   carta, quel mezzo tono di differenza non separa più niente: fa
   sembrare la colonna un pannello incollato sulla pagina, con una
   giuntura visibile là dove finisce. */
.articles {{ background: {PAPER}; padding: 0 56px; }}
.articles > .section-label {{ display: block; padding: 24px 0 4px 0; }}

/* Testata di sezione. Il regolo azzurro a 6px è lo stesso stacco che la
   pagina usa già sotto la testata e sopra "In breve": la sezione non
   introduce un linguaggio nuovo, riusa quello che c'è. Il nome a 30px si
   infila fra il tag del pezzo (15px) e il titolo (40px), così la
   gerarchia resta quella di prima con un gradino in più.
   Prende il posto dell'etichetta generica "Il resto della giornata", che
   occupava spazio senza dire niente: stesso ingombro, un'informazione. */
.band {{ padding-top: 28px; }}
.band:first-child {{ padding-top: 20px; }}
.band-rule {{ height: 5px; background: {INK}; }}
.band-row {{
  display: flex; justify-content: space-between; align-items: baseline;
  gap: 20px; padding: 14px 0 10px 0;
}}
.band-row h2 {{
  font-size: 30px; letter-spacing: 0.06em; text-transform: uppercase; color: {NAVY};
}}
.band-meta {{
  font-size: 16px; font-weight: 700; color: #5a5a5a;
  letter-spacing: 0.08em; text-transform: uppercase; white-space: nowrap;
}}
.band + .article, .band + .family {{ border-top: none; padding-top: 4px; }}

/* Blocco di famiglia: otto leghe di fantacalcio sono otto topic con la
   stessa forma, e otto articoli uguali non sono un giornale. Una forma
   ripetuta sola dice le stesse cose in un quinto dello spazio. */
.family {{ border-top: 2px solid {NAVY}; padding: 22px 0 26px 0; }}
.family > .section-label {{ display: block; margin-bottom: 14px; }}
.family-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 40px; }}
.family-item {{ border-top: 2px solid rgba(12, 35, 64, 0.22); padding: 12px 0; }}
.family-item .head {{
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  margin-bottom: 5px; font-size: 14px; font-weight: 800; letter-spacing: 0.12em;
  text-transform: uppercase; color: {AZZURRO_DEEP};
}}
.family-item .head .n {{ color: #8a8a8a; }}
.family-item p {{ font-size: 24px; line-height: 1.22; font-weight: 700; letter-spacing: -0.015em; }}

.article {{ border-top: 2px solid {NAVY}; padding: 26px 0; }}
.article:last-child {{ padding-bottom: 30px; }}
.article-head {{
  display: flex; justify-content: space-between; align-items: baseline;
  gap: 20px; margin-bottom: 10px;
}}
.topic-tag {{
  display: inline-flex; align-items: center; gap: 8px;
  background: {INK}; color: {PAPER}; font-size: 14px; font-weight: 800;
  letter-spacing: 0.12em; text-transform: uppercase; padding: 5px 10px;
}}
.topic-tag .glyph {{ flex: none; }}
.msg-count {{
  display: inline-flex; align-items: center; gap: 12px;
  font-size: 16px; font-weight: 700; color: #5a5a5a; white-space: nowrap;
}}
.article h3 {{ font-size: 40px; line-height: 1.08; letter-spacing: -0.02em; margin-bottom: 10px; }}
/* Sommario del pezzo: stessa funzione dell'occhiello dell'apertura, una
   scala sotto. È il gradino che mancava — titolo, sommario, testo — e
   senza il quale ogni articolo era un blocco unico. */
.article .deck {{
  font-size: 24px; line-height: 1.3; color: {INK_SOFT};
  font-weight: 500; font-style: italic; margin-bottom: 12px;
}}
.article .body {{
  font-size: 24px; line-height: 1.45;
  column-count: 2; column-gap: 40px; column-rule: 1px solid {RULE};
}}
.article .body p {{ margin-bottom: 13px; }}
.article .body p:last-child {{ margin-bottom: 0; }}

/* Il virgolettato. In un pezzo di cronaca la citazione non è un ornamento:
   è la sola riga in cui parla qualcuno che c'era, e il resto del pezzo la
   racconta. Sta dentro la colonna, staccata da un filetto azzurro sul
   fianco, e non attraversa la pagina come farebbe un blocco isolato. */
.virgolettato {{
  break-inside: avoid; margin: 4px 0 13px 0;
  border-left: 5px solid {AZZURRO}; padding: 3px 0 3px 16px;
}}
.virgolettato p {{
  font-size: 25px; line-height: 1.24; font-weight: 700; color: {NAVY};
  letter-spacing: -0.015em; margin-bottom: 6px;
}}
.virgolettato .chi {{
  display: block; font-size: 14px; font-weight: 800; letter-spacing: 0.1em;
  text-transform: uppercase; color: {AZZURRO_DEEP};
}}

/* Il dato grande: il numero che descrive la giornata, alla scala a cui i
   numeri si guardano invece di leggerli. È l'elemento che dà peso visivo
   alla testa della pagina senza chiedere niente a un'immagine. */
.number {{
  background: {NAVY}; color: #fff; padding: 26px 56px;
  display: flex; align-items: baseline; gap: 26px;
}}
.number .big {{
  font-size: 92px; font-weight: 800; letter-spacing: -0.04em;
  line-height: 0.9; color: {AZZURRO};
}}
.number .said {{ font-size: 26px; line-height: 1.25; font-weight: 600; max-width: 620px; }}
.number .said b {{ color: {AZZURRO_PALE}; }}

/* In breve: i topic minori in due colonne, titolo e basta. Un trafiletto
   di quattro righe per un topic da sei messaggi è una promessa che il
   contenuto non mantiene. */
.brief {{ background: {PAPER}; padding: 26px 56px 30px 56px; border-top: 3px solid {INK}; }}
.brief > .section-label {{ display: block; margin-bottom: 16px; }}
.brief-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0 40px; }}
.brief-item {{ border-top: 2px solid {NAVY}; padding: 14px 0; }}
.brief-item .head {{
  display: flex; align-items: center; gap: 8px; margin-bottom: 6px;
  font-size: 14px; font-weight: 800; letter-spacing: 0.12em;
  text-transform: uppercase; color: {AZZURRO_DEEP};
}}
.brief-item .head .n {{ color: #8a8a8a; }}
/* La sezione davanti al topic: è ciò che tiene "In breve" agganciato al
   resto della pagina invece di farne un elenco a parte. */
.brief-item .head .sez {{ color: {NAVY}; }}
.brief-item p {{ font-size: 25px; line-height: 1.22; font-weight: 700; letter-spacing: -0.015em; }}

.quote {{
  background: {PAPER_DEEP}; color: {INK}; padding: 30px 56px;
  border-top: 3px solid {INK}; border-bottom: 3px solid {INK};
}}
.quote .section-label {{ display: block; color: {AZZURRO}; margin-bottom: 14px; }}
.quote p {{ font-size: 46px; line-height: 1.15; font-weight: 800; letter-spacing: -0.02em; margin-bottom: 12px; }}
.quote .attrib {{ font-size: 20px; font-weight: 700; }}

/* La vignetta. Il pannello è largo quanto la colonna (1080 meno i due
   margini da 56) e il disegno lo riempie con object-fit: cover, quindi
   viene tagliato sopra e sotto — è il motivo per cui i disegni della
   biblioteca tengono le teste sotto la metà dell'immagine.
   Niente angoli arrotondati e niente ombre nemmeno qui: il fumetto è un
   rettangolo con un bordo, come il resto della pagina. */
.vignetta {{ background: {PAPER}; padding: 0 0 22px 0; }}
.vignetta .section-label {{ display: block; margin-bottom: 16px; }}
/* Dentro l'apertura il blocco non porta margini suoi: quelli della
   colonna ce li ha già la prima pagina. */
.lead .vignetta {{ padding: 0; margin-bottom: 22px; }}
.pannello {{
  position: relative; width: {_VIGNETTA_WIDTH}px; height: {_VIGNETTA_HEIGHT}px;
  border: 2px solid {INK}; overflow: hidden; background: {PAPER};
}}
.pannello img {{
  position: absolute; inset: 0; width: 100%; height: 100%;
  object-fit: cover; display: block;
}}
/* I balloon stanno nella metà alta, dove il disegno è sfondo e basta. */
.battute {{
  position: absolute; left: 16px; right: 16px; top: 14px;
  display: flex; flex-direction: column; gap: 9px;
}}
.balloon {{
  position: relative; border: 2px solid {INK}; background: {PAPER};
  padding: 8px 12px 7px 12px; max-width: 74%;
}}
.balloon.sx {{ align-self: flex-start; }}
.balloon.dx {{ align-self: flex-end; text-align: right; }}
.balloon p {{ font-size: 19px; line-height: 1.24; font-weight: 600; letter-spacing: -0.01em; }}
.balloon .firma {{
  display: block; margin-top: 5px; font-size: 11px; font-weight: 800;
  letter-spacing: 0.09em; text-transform: uppercase; color: {INK_SOFT};
}}
/* La codina: due triangoli sovrapposti, quello bianco più piccolo, così
   il bordo resta continuo. Ce l'ha solo l'ultimo balloon di chi parla —
   con due balloon di fila la codina del primo finisce coperta. */
.balloon.coda::before, .balloon.coda::after {{
  content: ""; position: absolute; width: 0; height: 0; border-style: solid;
}}
.balloon.sx.coda::before {{
  left: 24px; bottom: -15px; border-width: 15px 16px 0 0;
  border-color: {INK} transparent transparent transparent;
}}
.balloon.sx.coda::after {{
  left: 27px; bottom: -10px; border-width: 11px 12px 0 0;
  border-color: {PAPER} transparent transparent transparent;
}}
.balloon.dx.coda::before {{
  right: 24px; bottom: -15px; border-width: 15px 0 0 16px;
  border-color: {INK} transparent transparent transparent;
}}
.balloon.dx.coda::after {{
  right: 27px; bottom: -10px; border-width: 11px 0 0 12px;
  border-color: {PAPER} transparent transparent transparent;
}}
/* La didascalia di una foto, in un giornale, è piccola e in bastoni:
   non è un titolo, è una nota di servizio. */
.vignetta figcaption {{
  margin-top: 10px; font-size: 14px; font-weight: 600; color: {INK_SOFT};
  letter-spacing: 0.01em; line-height: 1.3;
  font-family: Archivo, 'Helvetica Neue', Arial, sans-serif;
}}

.stats {{ background: {NAVY}; color: #fff; padding: 28px 56px; }}
.stats-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 24px; }}
/* Il grafico e i quattro numeri stanno nella stessa fascia navy perché
   dicono la stessa cosa da due lati: il grafico la forma della giornata,
   i numeri le sue misure. Separarli in due blocchi li faceva leggere
   come due sezioni scollegate. */
.chart-block {{
  margin-bottom: 24px; padding-bottom: 22px;
  border-bottom: 1px solid rgba(143, 201, 232, 0.32);
}}
.chart-block .section-label {{ display: block; color: {AZZURRO_PALE}; margin-bottom: 16px; }}
.chart {{ display: block; }}
.stats .value {{ font-size: 44px; font-weight: 800; letter-spacing: -0.02em; line-height: 1; }}
.stats .label {{
  font-size: 15px; letter-spacing: 0.1em; text-transform: uppercase;
  color: {AZZURRO_PALE}; margin-top: 6px;
}}

.footer {{
  background: {NAVY}; color: {AZZURRO_PALE}; border-top: 3px solid {AZZURRO_BRIGHT};
  padding: 18px 56px; display: flex; justify-content: space-between;
  font-size: 15px; letter-spacing: 0.08em; text-transform: uppercase;
}}
.footer-continue {{
  background: {NAVY}; color: {AZZURRO_PALE}; border-top: 3px solid {AZZURRO_BRIGHT};
  padding: 20px 56px; display: flex; justify-content: space-between; align-items: baseline;
}}
.footer-continue .note {{ font-size: 17px; letter-spacing: 0.08em; text-transform: uppercase; }}
.footer-continue .next {{
  font-size: 20px; font-weight: 800; letter-spacing: 0.06em;
  text-transform: uppercase; color: #fff;
}}

/* Testatina della seconda pagina: più bassa della prima, così si capisce a
   colpo d'occhio che è la continuazione e non un secondo giornale. */
/* Le pagine interne non ripetono il marchio: portano una riga di folio,
   nome del giornale a sinistra e pagina a destra, come si usa. Ripetere
   la testata intera a ogni pagina faceva sembrare ogni pagina l'inizio di
   un giornale nuovo. */
.continuation {{
  background: {PAPER}; padding: 14px 56px; display: flex;
  align-items: baseline; justify-content: space-between; gap: 24px;
  border-top: 3px solid {INK}; border-bottom: 1px solid {INK};
  font-size: 15px; font-weight: 800; letter-spacing: 0.14em;
  text-transform: uppercase;
}}
.continuation .testata {{ color: {INK}; }}
.continuation .folio {{ color: {AZZURRO}; font-size: 15px; }}
"""


def _wrap_page(inner: str) -> str:
    return f"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@600;800&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;0,6..72,700;0,6..72,800;1,6..72,400;1,6..72,500&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
{inner}
</body>
</html>"""


def _masthead(logo_uri: str | None, newspaper_name: str) -> str:
    brand = (
        f'<img src="{logo_uri}" alt="{html.escape(newspaper_name)}">'
        if logo_uri
        else f'<h1 style="font-size:64px;text-transform:uppercase">'
        f"{html.escape(newspaper_name)}</h1>"
    )
    return (
        f'<div class="masthead"><div class="masthead-row">{brand}'
        '<div class="tagline">Il Gazzettino<br>del gruppo</div>'
        f'</div></div><div class="rule-accent"></div>'
    )


def _numeri_html(entries: list[tuple[str, int]], gfx: GraphicsOptions) -> str:
    """Le proporzioni della giornata, in coda all'edizione.

    Stavano in testa alla prima pagina, dove occupavano il posto che in un
    giornale è della notizia: chi compra un quotidiano non trova sopra
    l'apertura un istogramma di quanto si è parlato di che cosa. Sono
    misure sul gruppo, non notizie, e stanno bene accanto alle altre
    misure — nella fascia di chiusura."""
    if not entries:
        return ""
    share = share_bar_svg(entries) if gfx.share_bar else ""
    numero = _number_html(entries) if gfx.number_block else ""
    if not share and not numero:
        return ""
    barra = (
        '<div class="index"><span class="section-label">Le proporzioni della '
        f"giornata</span>{share}</div>"
        if share
        else ""
    )
    return barra + numero


def _pick_spalla(chunks: list[list]):
    """La seconda notizia dell'edizione, quella che va in prima accanto
    all'apertura.

    È il primo pezzo in ordine di lettura: le notizie arrivano già
    ordinate per sezione e per peso, quindi il primo è quello che il
    giornale ha deciso di mettere davanti. I blocchi di famiglia non
    possono fare da spalla — non sono un pezzo, sono un elenco."""
    for chunk in chunks:
        for a in chunk:
            if not isinstance(a, FamilyBlock) and a.headline:
                return a
    return None


def _pick_strilli(
    chunks: list[list], pagina_di: dict[int, int], escludi=None, quanti: int = 3
) -> list[tuple[str, str, int]]:
    """Le civette: i titoli che vale la pena annunciare sopra la testata.

    Uno per sezione, per non spendere tutte e tre le caselle sulla sezione
    più chiacchierona — che con otto leghe di fantacalcio è esattamente
    quello che succederebbe. La sezione della spalla conta come già
    spesa: la sua notizia sta appena sotto, in prima pagina, e annunciare
    la seconda della stessa sezione toglierebbe la casella a chi non ne
    ha nessuna."""
    viste: set[str] = set()
    if escludi is not None:
        viste.add(getattr(escludi, "section", "") or getattr(escludi, "topic", ""))
    out: list[tuple[str, str, int]] = []
    for chunk in chunks:
        for a in chunk:
            if isinstance(a, FamilyBlock) or not a.headline or a is escludi:
                continue
            sezione = a.section or a.topic
            if sezione in viste:
                continue
            viste.add(sezione)
            out.append((sezione, a.headline, pagina_di.get(id(a), 2)))
            if len(out) == quanti:
                return out
    return out


def _righe_dentro(
    chunks: list[list], stats: dict[str, tuple[int, int]] | None
) -> list[tuple[str, str, int]]:
    """Il sommario: ogni sezione, quanto pesa e a che pagina comincia."""
    ordine: list[str] = []
    pagina: dict[str, int] = {}
    for numero, chunk in enumerate(chunks, start=2):
        for a in chunk:
            sezione = getattr(a, "section", "") or getattr(a, "topic", "")
            if not sezione or sezione in pagina:
                continue
            ordine.append(sezione)
            pagina[sezione] = numero
    righe = []
    for sezione in ordine:
        if stats and sezione in stats:
            pezzi, messaggi = stats[sezione]
            unita = "pezzo" if pezzi == 1 else "pezzi"
            dettaglio = f"{pezzi} {unita} · {messaggi} messaggi"
        else:
            dettaglio = ""
        righe.append((sezione, dettaglio, pagina[sezione]))
    return righe


def _paragraphs(text: str) -> list[str]:
    """Un blocco di testo diviso nei suoi paragrafi.

    Gli articoli arrivano come stringa unica con i paragrafi separati da
    una riga vuota: separarli qui evita che un pezzo di quattro capoversi
    finisca in pagina come un muro."""
    if not text:
        return []
    grezzi = re.split(r"\n\s*\n|\n", text)
    return [p.strip() for p in grezzi if p.strip()]


def _quote_inline_html(quote: "Quote | None") -> str:
    """Il virgolettato dentro il pezzo."""
    if quote is None or not quote.text:
        return ""
    testo = quote.text.strip().strip('"').strip("«»")
    chi = html.escape(quote.author)
    if quote.time:
        chi += f", {html.escape(quote.time)}"
    return (
        f'<div class="virgolettato"><p>«{html.escape(testo)}»</p>'
        f'<span class="chi">{chi}</span></div>'
    )


def _body_html(text: str, quote: "Quote | None", end: str) -> str:
    """Il corpo del pezzo, con il virgolettato dopo il primo capoverso.

    Dopo il primo e non prima: l'attacco deve dare la notizia, e una
    citazione messa sopra ruba il posto al fatto. Dopo l'ultimo, invece,
    la citazione resterebbe fuori dal pezzo come una didascalia."""
    parti = _paragraphs(text)
    if not parti:
        return ""
    citazione = _quote_inline_html(quote)
    pezzi = []
    for i, p in enumerate(parti):
        ultimo = i == len(parti) - 1
        pezzi.append(f"<p>{html.escape(p)}{end if ultimo else ''}</p>")
        if i == 0 and citazione:
            pezzi.append(citazione)
    return "".join(pezzi)


def _lead_html(
    lead: Lead,
    gfx: GraphicsOptions,
    continua_a: int | None = None,
    vignetta_html: str = "",
) -> str:
    """L'apertura in prima pagina: la notizia, non tutto il pezzo.

    `continua_a` è la pagina su cui riprende il resto. Senza, l'apertura
    esce intera: succede quando l'edizione sta in una pagina sola.

    `vignetta_html` è il disegno del giorno, che entra fra il sommario e
    l'attacco — dove in un quotidiano sta la foto d'apertura. È anche il
    solo posto in cui ha senso: la vignetta porta le parole che il gruppo
    ha scritto sul fatto di apertura, quindi è il contorno di QUELLA
    notizia, e in fondo all'edizione stava lontana da ciò che illustra."""
    kicker = (
        f'<div class="kicker">Apertura · {html.escape(lead.kicker)}</div>'
        if lead.kicker
        else '<div class="kicker">Apertura</div>'
    )
    deck = f'<p class="deck">{html.escape(lead.deck)}</p>' if lead.deck else ""
    end = END_MARK if gfx.end_mark else ""
    if continua_a:
        testo = lead.attacco or lead.paragraphs
        coda = f'<div class="rimando">Il servizio a pagina {continua_a}</div>'
        chiusura = ""  # il pezzo non finisce qui: niente segno di fine
    else:
        testo = lead.paragraphs
        coda = ""
        chiusura = end
    if not testo:
        testo = ["Nessun dettaglio disponibile."]
    body = "".join(
        f"<p>{html.escape(p)}{chiusura if i == len(testo) - 1 else ''}</p>"
        for i, p in enumerate(testo)
    )
    headline = html.escape(lead.headline) or "Giornata senza articolo di apertura"
    # Il capolettera va sul primo paragrafo, che è comunque il primo
    # blocco di testo lungo della pagina.
    body_class = "body dropcap" if gfx.drop_cap else "body"
    return (
        f'<div class="lead">{kicker}<h2>{headline}</h2>{deck}'
        f'{vignetta_html}<div class="{body_class}">{body}</div>{coda}</div>'
    )


def _lead_segue_html(lead: Lead, gfx: GraphicsOptions) -> str:
    """Il seguito dell'apertura, in testa alla pagina dopo."""
    resto = lead.seguito
    if not resto:
        return ""
    end = END_MARK if gfx.end_mark else ""
    # Il virgolettato dell'apertura sta dopo il primo capoverso del
    # seguito, non in coda: attaccato in fondo, dopo il segno di fine
    # pezzo, sembrerebbe una didascalia rimasta lì.
    body = _body_html("\n\n".join(resto), lead.quote, end)
    return (
        '<div class="segue">'
        '<span class="section-label">Segue dalla prima pagina</span>'
        f"<h3>{html.escape(lead.headline)}</h3>"
        f'<div class="body">{body}</div></div>'
    )


def _strilli_html(richiami: list[tuple[str, str, int]]) -> str:
    """Le civette sopra la testata: che cosa c'è dentro, e a che pagina."""
    if not richiami:
        return ""
    celle = "".join(
        f'<div class="strillo"><span class="sez">{html.escape(sezione)}</span>'
        f"<p>{html.escape(titolo)}</p>"
        f'<span class="pag">a pagina {pagina}</span></div>'
        for sezione, titolo, pagina in richiami
    )
    return f'<div class="strilli">{celle}</div>'


def _spalla_html(article, pagina: int, gfx: GraphicsOptions) -> str:
    """La seconda notizia in prima pagina.

    Come l'apertura, non si esaurisce qui: dà titolo, sommario e il primo
    capoverso, e manda il lettore alla pagina dove il pezzo sta per
    intero."""
    if article is None or not article.headline:
        return ""
    etichetta = article.section or article.topic
    deck = f'<p class="deck">{html.escape(article.deck)}</p>' if article.deck else ""
    parti = _paragraphs(article.body)
    body = f'<div class="body"><p>{html.escape(parti[0])}</p></div>' if parti else ""
    return (
        '<div class="spalla">'
        f'<span class="section-label">{html.escape(etichetta)}</span>'
        f"<h3>{html.escape(article.headline)}</h3>{deck}{body}"
        f'<div class="rimando">Il servizio a pagina {pagina}</div></div>'
    )


def _dentro_html(righe: list[tuple[str, str, int]]) -> str:
    """Il sommario dell'edizione: dove sta ogni sezione.

    Prende il posto delle chip dell'indice, che dicevano quanti messaggi
    aveva una sezione senza dire dove trovarla. Non ripete i titoli — li
    hanno gli strilli — e risponde alla sola domanda che in prima pagina
    resta senza risposta: a che pagina si va per leggere di che cosa."""
    if not righe:
        return ""
    corpo = "".join(
        f'<div class="dentro-row"><span class="sez">{html.escape(sezione)}</span>'
        f"<p>{html.escape(titolo)}</p>"
        f'<span class="pag">pag. {pagina}</span></div>'
        for sezione, titolo, pagina in righe
    )
    return (
        '<div class="dentro">'
        '<span class="section-label">Dentro il giornale</span>'
        f"{corpo}</div>"
    )


def topics_needing_body(
    entries: list[tuple[str, int, str]],
    *,
    max_full: int = MAX_FULL_ARTICLES,
    margin: int = 1,
) -> set[str]:
    """Quali topic avranno un articolo per esteso, deciso PRIMA di scriverlo.

    arrange_sections taglia a `max_full` pezzi pieni e manda tutto il resto
    fra le voci in breve e i blocchi di famiglia, dove in pagina esce
    soltanto il titolo. Ma quel taglio arriva a valle: fino a ieri si
    scrivevano quattordici articoli interi per pubblicarne cinque, e gli
    altri nove venivano pagati per intero per mostrare una riga.

    Qui la stessa regola si applica prima, perché non dipende da niente
    che non si sappia già: il volume dei messaggi e la famiglia. I topic
    di famiglia non concorrono mai — vanno nel loro blocco compatto — e i
    restanti si ordinano per volume.

    `margin` tiene un pezzo di scorta oltre il taglio: un articolo può
    uscire come DUPLICATO e sparire dalla pagina, promuovendo il
    successivo, che a quel punto un corpo deve averlo. Era due, ed è
    sceso a uno guardando le run vere: il caso DUPLICATO non è mai
    scattato, e intanto ogni edizione pagava due pezzi completi che la
    pagina non stampava. Nel caso peggiore la pagina mostra quattro pezzi
    pieni invece di cinque, che nessuno nota — e resta comunque meglio di
    pagarne due di scorta tutti i giorni.

    `entries` sono (titolo, messaggi, famiglia) in qualunque ordine."""
    candidati = sorted(
        (t for t in entries if not t[2]), key=lambda t: t[1], reverse=True
    )
    return {titolo for titolo, _, _ in candidati[: max_full + margin]}


def arrange_sections(
    articles: list[Article],
    *,
    max_full: int = MAX_FULL_ARTICLES,
    min_family: int = 2,
    brief_box: bool = True,
) -> tuple[list, list[Article]]:
    """Ordina le notizie per sezione e separa quelle che vanno "In breve".

    `articles` arriva ordinata per volume, che è l'ordine con cui i pezzi
    vengono scritti. Qui diventa l'ordine con cui si leggono, che non è lo
    stesso: prima si tolgono di mezzo le famiglie (che non concorrono agli
    articoli pieni), poi si taglia ai primi `max_full` per volume — come
    si faceva già — e solo alla fine si raggruppa per sezione.

    Restituisce (elementi in pagina, voci di "In breve"). Il primo è una
    lista mista di Article e FamilyBlock, nell'ordine definitivo."""
    # Senza il box "In breve" non c'è dove mandare i topic minori, e i
    # blocchi di famiglia sono un modo di riassumerli: si torna al
    # gazzettino di prima, un articolo pieno per topic, con le sole
    # sezioni a dare l'ordine.
    if not brief_box:
        by_section = _group_by_section(articles, [])
        return _flatten(by_section, {}), []

    families: dict[tuple[str, str], list[Article]] = {}
    candidates: list[Article] = []
    for a in articles:
        if a.family:
            families.setdefault((a.family, a.section), []).append(a)
        else:
            candidates.append(a)

    full = candidates[:max_full]
    leftover: list[Article] = list(candidates[max_full:])

    blocks: list[FamilyBlock] = []
    for (label, section), items in families.items():
        # Una famiglia con un topic solo attivo non è una famiglia: il
        # blocco sarebbe una riga sotto un titolo, cioè un trafiletto con
        # una cornice intorno. Meglio in breve, insieme agli altri.
        if len(items) >= min_family:
            blocks.append(FamilyBlock(label=label, section=section, items=items))
        else:
            leftover.extend(items)

    by_section = _group_by_section(full, blocks)
    leftover.sort(key=lambda a: a.count, reverse=True)

    # Il peso di una sezione è tutto quello che le appartiene, comprese le
    # voci finite in breve: altrimenti una sezione può mostrare in testata
    # un numero più grande di quella che la precede, che è il modo più
    # sicuro di far sembrare l'ordine casuale.
    weights: dict[str, int] = {}
    for name, items in by_section.items():
        weights[name] = sum(i.count for i in items)
    for a in leftover:
        if a.section in weights:
            weights[a.section] += a.count
    return _flatten(by_section, weights), leftover


def _group_by_section(
    items: list, blocks: list["FamilyBlock"]
) -> dict[str, list]:
    grouped: dict[str, list] = {}
    for item in items:
        grouped.setdefault(item.section, []).append(item)
    # Il blocco di famiglia chiude la sua sezione: prima i pezzi scritti,
    # poi il riepilogo dei simili.
    for block in blocks:
        grouped.setdefault(block.section, []).append(block)
    return grouped


def _flatten(by_section: dict[str, list], weights: dict[str, int]) -> list:
    ordered = sorted(
        by_section,
        key=lambda name: weights.get(name) or sum(i.count for i in by_section[name]),
        reverse=True,
    )
    return [item for name in ordered for item in by_section[name]]


def _section_stats(items: list, brief: list[Article]) -> dict[str, tuple[int, int]]:
    """Per ogni sezione: quanti topic e quanti messaggi, contando tutto
    quello che finisce in pagina — articoli, blocchi e voci in breve.

    Sono i numeri scritti nella testata di sezione, e devono descrivere la
    sezione com'è stampata: un topic il cui pezzo è stato scartato come
    doppione non compare in pagina e non va contato qui."""
    stats: dict[str, list[int]] = {}

    def add(section: str, topics: int, messages: int) -> None:
        row = stats.setdefault(section or "", [0, 0])
        row[0] += topics
        row[1] += messages

    for item in items:
        if isinstance(item, FamilyBlock):
            add(item.section, len(item.items), item.count)
        elif item.headline:
            add(item.section, 1, item.count)
    for a in brief:
        if a.headline:
            add(a.section, 1, a.count)
    return {name: (row[0], row[1]) for name, row in stats.items()}


def _band_html(
    section: str,
    stats: dict[str, tuple[int, int]],
    total_messages: int,
    continued: bool = False,
) -> str:
    topics, messages = stats.get(section, (0, 0))
    parts = [f"{topics} topic", f"{messages} messaggi"]
    if total_messages > 0:
        parts.append(f"{round(100 * messages / total_messages)}%")
    meta = " · ".join(parts)
    name = html.escape(section) + (" (segue)" if continued else "")
    return (
        f'<div class="band"><div class="band-rule"></div>'
        f'<div class="band-row"><h2>{name}</h2>'
        f'<span class="band-meta">{html.escape(meta)}</span></div></div>'
    )


def _family_html(block: FamilyBlock) -> str:
    items = [i for i in block.items if i.headline]
    if not items:
        return ""
    unit = "voce" if len(items) == 1 else "voci"
    label = f"{block.label} · {len(items)} {unit}, {block.count} messaggi"
    rows = "".join(
        f'<div class="family-item"><div class="head">'
        f"<span>{html.escape(i.topic)}</span>"
        f'<span class="n">{i.count}</span></div>'
        f"<p>{html.escape(i.headline)}</p></div>"
        for i in items
    )
    return (
        f'<div class="family"><span class="section-label">{html.escape(label)}</span>'
        f'<div class="family-grid">{rows}</div></div>'
    )


def _articles_html(
    articles: list,
    label: str,
    gfx: GraphicsOptions,
    top_count: int = 0,
    *,
    stats: dict[str, tuple[int, int]] | None = None,
    total_messages: int = 0,
    continues: str = "",
) -> str:
    """Le notizie di una pagina.

    Con le sezioni attive (`stats` valorizzato) l'etichetta generica
    lascia il posto alle testate di sezione, che dicono la stessa cosa e
    in più dicono quale. Una sezione spezzata fra due pagine ripete la
    testata con "(segue)": è più onesto che far ricominciare il lettore
    senza sapere dove si trova."""
    if not articles:
        return ""
    sectioned = stats is not None
    # None e non `continues`: la prima testata di una pagina va emessa
    # comunque, anche quando la sezione è la stessa con cui finiva la
    # pagina prima — è proprio il caso in cui il lettore ha più bisogno
    # di sapere dove si trova, ed è lì che compare "(segue)".
    current: str | None = None
    blocks = []
    for a in articles:
        if not a.headline:
            continue
        if sectioned and a.section != current:
            blocks.append(
                _band_html(
                    a.section,
                    stats,
                    total_messages,
                    continued=current is None and a.section == continues,
                )
            )
            current = a.section
        if isinstance(a, FamilyBlock):
            blocks.append(_family_html(a))
            continue
        unit = "messaggio" if a.count == 1 else "messaggi"
        glyph = topic_glyph_svg(a.topic, size=17) if gfx.topic_glyphs else ""
        weight = weight_bar_svg(a.count, top_count) if gfx.weight_bars else ""
        end = END_MARK if gfx.end_mark else ""
        deck = f'<p class="deck">{html.escape(a.deck)}</p>' if a.deck else ""
        # Senza corpo il segno di fine pezzo va sul sommario, o resterebbe
        # appeso a un paragrafo vuoto.
        if a.body:
            body = deck + f'<div class="body">{_body_html(a.body, a.quote, end)}</div>'
        elif a.deck:
            body = f'<p class="deck">{html.escape(a.deck)}{end}</p>'
        else:
            body = ""
        blocks.append(
            '<div class="article"><div class="article-head">'
            f'<span class="topic-tag">{glyph}{html.escape(a.topic)}</span>'
            f'<span class="msg-count">{weight}<span>{a.count} {unit}</span></span></div>'
            f"<h3>{html.escape(a.headline)}</h3>{body}</div>"
        )
    if not blocks:
        return ""
    # Con le sezioni la testata generica sparisce: direbbe "Il resto della
    # giornata" sopra una riga che dice già "FANTACALCIO".
    heading = (
        ""
        if sectioned
        else f'<span class="section-label">{html.escape(label)}</span>'
    )
    return f'<div class="articles">{heading}' + "".join(blocks) + "</div>"


def _number_html(entries: list[tuple[str, int]]) -> str:
    """Il dato grande della giornata.

    Non è una statistica in più — quelle stanno già nella fascia navy in
    fondo. È l'unico modo di dare peso visivo alla testa della pagina
    senza un'immagine: un numero grande occupa lo spazio e lo giustifica,
    perché quello spazio lo riempie di informazione."""
    if not entries:
        return ""
    # entries sono le sezioni: il dato grande dice quanto ha pesato la
    # più grossa, che è un'affermazione sulla giornata più forte di
    # quanto abbia pesato il singolo topic più chiacchierato.
    name, count = entries[0]
    total = sum(c for _, c in entries)
    share = (
        f" — <b>{round(100 * count / total)}%</b> di tutto quello che si è detto"
        if total > 0
        else ""
    )
    return (
        '<div class="number">'
        f'<span class="big">{count}</span>'
        f'<span class="said">messaggi su <b>{html.escape(name)}</b>{share}</span>'
        "</div>"
    )


def _brief_html(articles: list[Article], gfx: GraphicsOptions) -> str:
    """I topic minori: tag, contatore e titolo, su due colonne."""
    if not articles:
        return ""
    items = []
    sectioned = False
    for a in articles:
        if not a.headline:
            continue
        glyph = topic_glyph_svg(a.topic, size=15) if gfx.topic_glyphs else ""
        # La sezione davanti al topic: senza, "In breve" è un elenco
        # staccato dal resto della pagina, e il lettore non sa se quella
        # riga appartiene a una sezione che ha già letto o a una che non
        # è mai comparsa.
        section = (
            f'<span class="sez">{html.escape(a.section)}</span>' if a.section else ""
        )
        sectioned = sectioned or bool(a.section)
        items.append(
            '<div class="brief-item"><div class="head">'
            f"{glyph}{section}<span>{html.escape(a.topic)}</span>"
            f'<span class="n">{a.count}</span></div>'
            f"<p>{html.escape(a.headline)}</p></div>"
        )
    if not items:
        return ""
    label = "In breve · quello che non ha fatto sezione" if sectioned else "In breve"
    return (
        f'<div class="brief"><span class="section-label">{html.escape(label)}</span>'
        f'<div class="brief-grid">{"".join(items)}</div></div>'
    )


def _quote_html(quote: Quote | None) -> str:
    if quote is None or not quote.text:
        return ""
    attrib = html.escape(quote.author)
    if quote.topic:
        attrib += f" — topic {html.escape(quote.topic)}"
    if quote.time:
        attrib += f", {html.escape(quote.time)}"
    text = quote.text.strip().strip('"').strip("«»")
    return (
        '<div class="quote"><span class="section-label">La frase del giorno</span>'
        f"<p>«{html.escape(text)}»</p>"
        f'<div class="attrib">{attrib}</div></div>'
    )


def _vignetta_html(vignetta: "Vignetta | None") -> str:
    if vignetta is None or not vignetta.balloons:
        return ""
    try:
        uri = data_uri(vignetta.image_path)
    except OSError:
        # Un disegno che non si apre non è un motivo per non spedire il
        # gazzettino: la vignetta salta, il resto della pagina resta.
        print(f"Vignetta saltata: non riesco a leggere {vignetta.image_path}.")
        return ""

    # Chi parla per primo sta a sinistra. Il lato non dice chi è la
    # persona — i disegni sono sempre gli stessi due — dice solo che le
    # voci sono due e distinte.
    voci: list[str] = []
    for b in vignetta.balloons:
        if b.author not in voci:
            voci.append(b.author)

    pezzi = []
    for i, b in enumerate(vignetta.balloons):
        lato = "sx" if voci.index(b.author) == 0 else "dx"
        # La codina va a chi non ha altre battute dopo dallo stesso lato,
        # altrimenti resta nascosta sotto il balloon successivo.
        ultimo = not any(
            ("sx" if voci.index(x.author) == 0 else "dx") == lato
            for x in vignetta.balloons[i + 1:]
        )
        firma = html.escape(b.author)
        if b.time:
            firma += f" &middot; {html.escape(b.time)}"
        pezzi.append(
            f'<div class="balloon {lato}{" coda" if ultimo else ""}">'
            f"<p>{html.escape(b.text)}</p>"
            f'<span class="firma">{firma}</span></div>'
        )

    didascalia = (
        f"<figcaption>{html.escape(vignetta.topic)}</figcaption>"
        if vignetta.topic
        else ""
    )
    return (
        '<div class="vignetta">'
        '<span class="section-label">La vignetta</span>'
        f'<figure><div class="pannello"><img src="{uri}" alt="">'
        f'<div class="battute">{"".join(pezzi)}</div></div>'
        f"{didascalia}</figure></div>"
    )


def _stats_html(
    stats: Stats | None,
    hourly: list[int] | None,
    gfx: GraphicsOptions,
    giorno: date | None = None,
) -> str:
    chart = ""
    if gfx.hourly_chart and hourly:
        svg = hourly_chart_svg(hourly)
        if svg:
            # Da quando la testata porta la data di uscita, «la
            # giornata» non è più quella scritta in cima alla pagina:
            # tanto vale dire quale.
            quando = f"di {giorno_e_mese(giorno)}" if giorno else "della giornata"
            chart = (
                '<div class="chart-block">'
                f'<span class="section-label">Il ritmo {quando}</span>'
                f"{svg}</div>"
            )
    if stats is None:
        # Il grafico da solo regge la fascia: sono comunque dati della
        # giornata, e senza i numeri resta una chiusura pulita.
        return f'<div class="stats">{chart}</div>' if chart else ""

    cells = [
        (stats.messages, "messaggi"),
        (stats.participants, "partecipanti"),
        (stats.active_topics, "topic attivi"),
        (stats.peak_hour, "ora di punta"),
    ]
    grid = '<div class="stats-grid">' + "".join(
        f'<div><div class="value">{html.escape(str(v))}</div>'
        f'<div class="label">{label}</div></div>'
        for v, label in cells
    ) + "</div>"
    return f'<div class="stats">{chart}{grid}</div>'


def _footer_html(note: str = FOOTER_NOTE) -> str:
    return (
        f'<div class="footer"><span>{html.escape(note)}</span>'
        f"<span>{CHANNEL_LINK}</span></div>"
    )


# --- Impaginazione -------------------------------------------------------

# Stime in px CSS, misurate una per una renderizzando il blocco da solo
# (vedi misura_blocchi.py). Non servono a posizionare niente, solo a
# decidere dove spezzare le pagine — ma l'approssimazione va fatta per
# ECCESSO: una stima bassa non fa una pagina un po' lunga, fa l'ultima
# pagina che sfonda il tetto proprio quando è più piena, perché è lì che
# si accumulano tutti i blocchi fissi insieme.
_H_CHROME = 150 + 60 + 120          # testata + dateline + footer
_H_CONT_CHROME = 90 + 120           # testatina di continuazione + footer
_H_QUOTE = 245
# Etichetta, pannello, didascalia e i due margini del blocco.
_H_VIGNETTA = 40 + _VIGNETTA_HEIGHT + 4 + 28 + 22   # etichetta, pannello, didascalia
_H_STATS = 130
# La prima pagina non è più una pila di fasce: l'apertura e i richiami
# sono due colonne affiancate, e l'altezza della pagina è quella della
# colonna più alta. Sommarle, come si faceva quando erano sovrapposte,
# sovrastimerebbe la pagina di cinque o seicento pixel.
_H_CHROME_PRIMA = 284   # testata, data, margini della griglia, piede
_H_STRILLO = 138        # un richiamo nella colonna di destra
_H_DENTRO_SIDE = 77     # margine, filetto e titolo del sommario stretto
_H_DENTRO_SIDE_ROW = 38 # una riga sezione/pagina nella colonna stretta
_H_RIMANDO = 58         # "Il servizio a pagina N" in coda a un pezzo
_H_VIRGOLETTATO = 120   # la citazione dentro il corpo, su una colonna
_H_DENTRO_HEAD = 62     # titolo del sommario dell'edizione
_H_DENTRO_ROW = 60      # una riga del sommario
_H_CHART = 235          # titolo + grafico orario + regolo di separazione
_H_NUMBER = 165         # blocco del dato grande
_H_BRIEF_HEAD = 80      # titolo del box "In breve"
_H_BRIEF_ROW = 122      # una riga del box (due voci affiancate)
_H_SHARE = 120          # etichetta e barra delle proporzioni
_H_BAND = 88            # testata di sezione: regolo, nome e contatori
_H_FAMILY_HEAD = 84     # titolo del blocco di famiglia + regolo + padding
_H_FAMILY_ROW = 86      # una riga del blocco (due voci affiancate)

# Frase del giorno e statistiche stanno sempre in ultima pagina: chi
# impagina deve tenerne lo spazio da parte.
_H_TAIL = _H_QUOTE + _H_STATS


def _estimate_lead_height(
    lead: Lead, front: bool = True, con_vignetta: bool = False
) -> int:
    """L'apertura in prima. Con `front` conta solo l'attacco: il resto del
    pezzo riprende dentro e lo paga la pagina che lo ospita."""
    h = 47  # occhiello
    h += _text_height(lead.headline, chars_per_line=22, line_height=59)
    h += _text_height(lead.deck, chars_per_line=54, line_height=36) + 39
    if con_vignetta:
        h += _H_VIGNETTA
    # I capoversi si contano insieme, non uno per uno: scorrono in un
    # unico flusso a due colonne, e contarli separatamente faceva pagare
    # a ciascuno l'aria di fine blocco che in pagina non c'è.
    testo = lead.attacco if front else lead.paragraphs
    if testo:
        h += _column_height("\n\n".join(testo), chars_per_line=29, line_height=32) + 14
    if front and lead.seguito:
        h += _H_RIMANDO
    return h


def _estimate_front_height(
    lead: Lead,
    spalla,
    strilli: list,
    dentro: list,
    gfx: GraphicsOptions,
    con_vignetta: bool = False,
) -> int:
    """L'altezza della vetrina.

    Non serve a spezzarla — la prima pagina è una sola e non ha niente da
    passare alla successiva — ma a sapere quando sfonda: è l'unica pagina
    che nessun meccanismo può alleggerire da sé, quindi se cresce troppo
    deve almeno dirlo."""
    colonna_apertura = _estimate_lead_height(lead, con_vignetta=con_vignetta)
    colonna_richiami = _H_STRILLO * len(strilli) + (
        _H_DENTRO_SIDE + _H_DENTRO_SIDE_ROW * len(dentro) if dentro else 0
    )
    return (
        _H_CHROME_PRIMA
        + max(colonna_apertura, colonna_richiami)
        + _estimate_spalla_height(spalla)
    )


def _estimate_segue_height(lead: Lead) -> int:
    """Il seguito dell'apertura in testa alla pagina dopo."""
    resto = lead.seguito
    if not resto:
        return 0
    h = 100  # etichetta + titolino ripetuto + padding
    h += _text_height(lead.headline, chars_per_line=44, line_height=38)
    for p in resto:
        h += _column_height(p, chars_per_line=40, line_height=38) + 14
    if lead.quote:
        h += _H_VIRGOLETTATO
    return h


def _estimate_spalla_height(article) -> int:
    if article is None or not getattr(article, "headline", ""):
        return 0
    # La spalla sta sotto il taglio, a tutta pagina e su TRE colonne: le
    # misure sono quelle, non più quelle di due colonne strette.
    h = 96  # etichetta + margini
    h += _text_height(article.headline, chars_per_line=44, line_height=38)
    h += _text_height(article.deck, chars_per_line=66, line_height=30) + (14 if article.deck else 0)
    parti = _paragraphs(article.body)
    if parti:
        h += _column_height(parti[0], chars_per_line=30, line_height=34, columns=3)
    return h + _H_RIMANDO


def _estimate_article_height(a) -> int:
    """L'altezza stimata di un elemento in colonna, articolo o blocco.

    Il blocco di famiglia occupa spazio come un pezzo, quindi entra nella
    stessa stima: chi distribuisce le notizie sulle pagine non deve
    conoscere due tipi diversi."""
    if isinstance(a, FamilyBlock):
        rows = -(-len([i for i in a.items if i.headline]) // 2)
        return _H_FAMILY_HEAD + _H_FAMILY_ROW * rows

    h = 90  # tag + contatore + regolo + padding
    h += _text_height(a.headline, chars_per_line=40, line_height=44)
    h += _text_height(a.deck, chars_per_line=62, line_height=33) + (12 if a.deck else 0)
    h += _column_height(a.body, chars_per_line=42, line_height=35)
    if a.quote:
        h += _H_VIRGOLETTATO
    return h


def _text_height(text: str, chars_per_line: int, line_height: int) -> int:
    if not text:
        return 0
    lines = max(1, -(-len(text) // chars_per_line))
    return lines * line_height


def _column_height(
    text: str, chars_per_line: int, line_height: int, columns: int = 2
) -> int:
    """Altezza di un testo impaginato su più colonne.

    Le righe sono le stesse — la misura di riga è già quella stretta della
    colonna — ma stanno una accanto all'altra, quindi l'altezza si divide.
    Ogni paragrafo però comincia una riga nuova in una colonna sola, e il
    bilanciamento fra colonne lascia sempre un po' di aria: la mezza riga
    per paragrafo la si paga per intero, arrotondando per eccesso, perché
    sottostimare qui significa sfondare il tetto della pagina."""
    if not text:
        return 0
    paragrafi = _paragraphs(text) or [text]
    righe = sum(max(1, -(-len(p) // chars_per_line)) for p in paragrafi)
    righe_per_colonna = -(-(righe + len(paragrafi)) // columns)
    return righe_per_colonna * line_height


def _item_heights(items: list) -> dict[int, int]:
    """Altezza di ogni elemento, testata di sezione compresa.

    La testata la paga il primo pezzo della sua sezione: è l'unico modo
    di far entrare le sezioni nel conto senza insegnare a chi impagina
    che cosa sia una sezione. La stima resta approssimata per eccesso ai
    salti di pagina — dove la testata si ripete con "(segue)" — ma il
    tetto d'altezza ha già il margine per assorbirlo."""
    heights: dict[int, int] = {}
    previous: str | None = None
    for item in items:
        height = _estimate_article_height(item)
        section = getattr(item, "section", "")
        if section != previous:
            height += _H_BAND
            previous = section
        heights[id(item)] = height
    return heights


def paginate_articles(
    articles: list,
    *,
    segue_height: int = 0,
    tail_height: int = _H_TAIL,
) -> list[list]:
    """Distribuisce le notizie sulle pagine interne, una lista per pagina.

    La prima pagina non ne prende nessuna: è la vetrina dell'edizione, e
    un articolo intero là sotto la trasformerebbe di nuovo nella prima
    puntata del giornale. Le pagine qui restituite sono quindi la 2, la 3
    e così via.

    Il numero di pagine non è fissato: dipende da quanto testo c'è. Con
    dieci topic attivi una pagina unica raccoglieva tutto il resto e
    diventava una striscia che Telegram mostra rimpicciolita, cioè
    illeggibile — che è il motivo per cui il tetto d'altezza vale per ogni
    pagina.

    `segue_height` è il seguito dell'apertura, che apre la prima pagina
    interna; `tail_height` la chiusura, che pesa sull'ultima. Contarli è
    ciò che impedisce di sfondare il tetto proprio dove la pagina è già
    più piena."""
    usable = [a for a in articles if a.headline]
    if not usable:
        return []
    heights = _item_heights(usable)
    prima_base = _H_CONT_CHROME + segue_height

    pages: list[list] = []
    page_heights: list[int] = []
    current: list[Article] = []
    height = prima_base
    for index, a in enumerate(usable):
        # Vignetta e statistiche chiudono l'ultima pagina: quando
        # sistemiamo l'ultima notizia vanno contate, o è proprio la coda a
        # far sfondare la pagina finale.
        reserve = tail_height if index == len(usable) - 1 else 0
        h = heights[id(a)]
        if current and height + h + reserve > MAX_PAGE_HEIGHT:
            pages.append(current)
            page_heights.append(height)
            current, height = [], _H_CONT_CHROME
        current.append(a)
        height += h
    if current:
        pages.append(current)
        page_heights.append(height)

    # Un'ultima pagina con un solo trafiletto in mezzo al bianco si evita in
    # due modi. Riaccorparla nella precedente vale solo se ci sta davvero:
    # farlo a forza era ciò che rimetteva insieme la striscia lunga. Se non
    # ci sta, si scala giù una notizia dalla penultima, così l'edizione
    # chiude con due pezzi invece che con uno solo.
    if len(pages) > 1 and len(pages[-1]) == 1:
        merged = page_heights[-2] + heights[id(pages[-1][0])] + tail_height
        if merged <= MAX_PAGE_HEIGHT:
            pages[-2].extend(pages.pop())
        elif len(pages[-2]) > 1:
            pages[-1].insert(0, pages[-2].pop())

    return _balance_pages(pages, prima_base, tail_height, heights)


def _balance_pages(
    pages: list[list],
    first_base: int,
    tail_height: int,
    heights: dict[int, int],
) -> list[list]:
    """Ridistribuisce le notizie perché le pagine vengano simili fra loro.

    Il riempimento avido decide bene *quante* pagine servono e male *come*
    riempirle: caricando ogni pagina fino al tetto, l'ultima si prende gli
    avanzi e in mezzo restano pagine mezze bianche — misurate 1875, 999 e
    2084 px su tre pagine, cioè una pagina piena, una vuota e una piena.
    A parità di numero di pagine, distribuire verso un'altezza obiettivo
    non costa niente e si vede subito.

    Il numero di pagine non cambia mai: se il ribilanciamento sfonda il
    tetto si tiene il risultato avido, che almeno è sicuro."""
    total_pages = len(pages)
    if total_pages < 2:
        return pages

    flat = [a for page in pages for a in page]
    fixed = first_base + _H_CONT_CHROME * (total_pages - 1) + tail_height
    target = (fixed + sum(heights.values())) / total_pages

    balanced: list[list[Article]] = []
    index = 0
    for page_number in range(total_pages):
        base = first_base if page_number == 0 else _H_CONT_CHROME
        if page_number == total_pages - 1:
            balanced.append(flat[index:])
            break
        current: list[Article] = []
        height = base
        # Ogni pagina lascia almeno una notizia a ciascuna di quelle dopo.
        available = len(flat) - index - (total_pages - page_number - 1)
        while index < len(flat) and len(current) < available:
            h = heights[id(flat[index])]
            # Si supera l'obiettivo solo se la notizia ci sta più dentro
            # che fuori: senza questo, un pezzo lungo apre sempre la
            # pagina dopo e l'obiettivo non viene mai raggiunto.
            if current and height + h > target and height + h / 2 > target:
                break
            current.append(flat[index])
            height += h
            index += 1
        balanced.append(current)

    if any(not page for page in balanced):
        return pages
    for number, page in enumerate(balanced):
        base = first_base if number == 0 else _H_CONT_CHROME
        if number == len(balanced) - 1:
            base += tail_height
        if base + sum(heights[id(a)] for a in page) > MAX_PAGE_HEIGHT:
            return pages
    return balanced


def build_pages_html(
    newspaper_name: str,
    day: date,
    lead: Lead,
    articles: list[Article],
    *,
    logo_path: str | Path | None = None,
    index_entries: list[tuple[str, int]] | None = None,
    stats: Stats | None = None,
    quote: Quote | None = None,
    vignetta: "Vignetta | None" = None,
    edition_number: int | None = None,
    hourly: list[int] | None = None,
    graphics: GraphicsOptions | None = None,
    giorno_raccontato: date | None = None,
) -> list[str]:
    """Compone il gazzettino e restituisce l'HTML di ciascuna pagina.

    Le pagine sono quante ne servono: una sola quando la giornata è magra,
    tre o quattro quando i topic attivi sono molti. `articles` deve arrivare
    già ordinata per rilevanza.

    `hourly` sono i 24 conteggi orari per il grafico di chiusura; senza,
    la fascia finale resta quella dei soli numeri. `graphics` decide quali
    elementi grafici accendere (default: quelli a rischio zero).

    `vignetta` e `quote` occupano lo stesso posto in fondo all'ultima
    pagina, e infatti dicono la stessa cosa: le parole del gruppo messe
    in evidenza. Quando c'è la vignetta la frase del giorno non esce —
    due blocchi di citazioni di fila sarebbero la stessa idea due volte.

    `day` è il giorno in cui il giornale ESCE, che è quello che va in
    testata: un quotidiano si data con l'edizione, non con i fatti.
    `giorno_raccontato` è il giorno di cui parla, e serve alle rubriche
    delle pagine interne e della chiusura, che altrimenti direbbero «la
    giornata» indicando un giorno diverso da quello stampato in cima.
    Senza, vale il giorno prima: è la relazione normale fra le due — il
    gazzettino esce la mattina dopo — e così chi chiama per un'anteprima
    o un controllo non deve saperne niente."""
    gfx = graphics if graphics is not None else GraphicsOptions()
    logo_uri = data_uri(logo_path) if logo_path else None
    index_entries = index_entries or []
    raccontato = giorno_raccontato or day - timedelta(days=1)

    # I topic minori escono dalla colonna e diventano righe del box "In
    # breve": è la separazione che rende visibile la gerarchia. Le
    # sezioni si aggiungono sopra a quella separazione senza cambiarla —
    # decidono l'ordine e le testate, non chi è grande e chi è piccolo.
    usable = [a for a in articles if a.headline]
    laid_out, brief = arrange_sections(usable, brief_box=gfx.brief_box)
    sectioned = any(getattr(i, "section", "") for i in laid_out)
    stats_by_section = _section_stats(laid_out, brief) if sectioned else None
    total_messages = sum(a.count for a in usable)

    # Il contatore più alto fa da fondoscala alle barrette di peso: il
    # confronto è fra i topic della giornata, non con una soglia fissa.
    top_count = max(
        (a.count for a in laid_out if not isinstance(a, FamilyBlock)), default=0
    )

    # La vignetta sta in prima pagina, dentro l'apertura, dove in un
    # quotidiano sta la foto: illustra il tono con cui il gruppo ha
    # parlato del fatto di apertura, e stando in fondo all'edizione era
    # lontana dalla notizia che le dà senso. Assorbe la frase del giorno,
    # che quindi non esce; senza vignetta la frase torna in chiusura.
    #
    # La prima pagina non può però portare tutto: con il disegno dentro
    # l'apertura, la spalla scende alle pagine interne (dove il suo pezzo
    # stava comunque per intero) e resta annunciata dagli strilli. È il
    # baratto giusto — un'immagine grande pesa più di un richiamo — ed è
    # anche l'unico modo di restare sotto il tetto d'altezza.
    vignetta_html = _vignetta_html(vignetta)
    if vignetta_html:
        quote = None
    closing_height = (
        _H_TAIL
        - _H_QUOTE
        + (_H_QUOTE if quote else 0)
        + (_H_CHART if gfx.hourly_chart and hourly else 0)
        + (_H_BRIEF_HEAD + _H_BRIEF_ROW * -(-len(brief) // 2) if brief else 0)
        + (_H_SHARE if gfx.share_bar and index_entries else 0)
        + (_H_NUMBER if gfx.number_block and index_entries else 0)
        + _MARGINE_CODA
    )

    # PRIMA PASSATA: dove finisce ogni pezzo. I rimandi della prima pagina
    # ("a pagina 3") non si possono scrivere prima di saperlo, ed è per
    # questo che l'impaginazione viene prima della composizione e non
    # dopo, come sarebbe naturale.
    segue_height = _estimate_segue_height(lead)
    chunks = paginate_articles(
        laid_out, segue_height=segue_height, tail_height=closing_height
    )
    pagina_di = {
        id(a): numero
        for numero, chunk in enumerate(chunks, start=2)
        for a in chunk
    }
    total = len(chunks) + 1

    # SECONDA PASSATA: la vetrina, con i numeri di pagina in mano.
    # La spalla esce tutti i giorni, vignetta o no. Prima il disegno la
    # cacciava dalla pagina perché occupava una fascia larga quanto la
    # pagina; ora sta dentro la colonna dell'apertura, e sotto il taglio
    # resta lo spazio per la seconda notizia. Una prima pagina con una
    # sola notizia non è una prima pagina.
    spalla = _pick_spalla(chunks)
    strilli = _pick_strilli(chunks, pagina_di, escludi=spalla, quanti=4)
    dentro = _righe_dentro(chunks, stats_by_section)

    alta = _estimate_front_height(
        lead, spalla, strilli, dentro, gfx, con_vignetta=bool(vignetta_html)
    )
    if alta > MAX_PAGE_HEIGHT:
        print(
            f"Prima pagina stimata {alta}px, sopra il tetto di "
            f"{MAX_PAGE_HEIGHT}: l'apertura di oggi è più lunga del solito."
        )

    # La riga sotto la testata è il posto in cui il lettore incontra la
    # data, e da quando la testata porta il giorno di USCITA è anche
    # l'unico posto in cui può leggere di che giorno parla il giornale.
    # "Edizione quotidiana" non diceva niente che la testata non dicesse
    # già; "la giornata di domenica 6" risponde all'unica domanda che
    # resta aperta.
    #
    # L'etichetta generica di _articles_html non serve allo scopo: con le
    # sezioni attive — cioè sempre, in un'edizione vera — le testate di
    # sezione prendono il suo posto e quella riga non si stampa mai.
    edition = (
        f"Edizione n. {edition_number}"
        if edition_number
        else f"La giornata di {giorno_e_mese(raccontato)}"
    )
    testatina = f'<span class="testata">{html.escape(newspaper_name)}</span>'

    def chiusura(numero: int) -> str:
        note = (
            FOOTER_NOTE
            if total == 1
            else f"Fine dell'edizione · pagina {numero} di {total}"
        )
        return (
            _brief_html(brief, gfx)
            # La vignetta ora sta in prima, dentro l'apertura: qui resta
            # solo la frase del giorno, e solo nei giorni senza vignetta.
            + _quote_html(quote)
            + _numeri_html(index_entries, gfx)
            + _stats_html(stats, hourly, gfx, raccontato)
            + _footer_html(note)
        )

    def continua(numero: int) -> str:
        return (
            '<div class="footer-continue">'
            f'<span class="note">{html.escape(FOOTER_NOTE)}</span>'
            f'<span class="next">Continua a pagina {numero + 1} ▸</span></div>'
        )

    folio_prima = f"{edition} · Pagina 1 di {total}" if total > 1 else edition
    # L'ordine è quello di una prima pagina vera: testata, data, e poi la
    # griglia a due colonne — l'apertura sulla larga, i richiami e il
    # sommario sulla stretta. Sotto il taglio, la seconda notizia.
    apertura = _lead_html(
        lead,
        gfx,
        continua_a=2 if chunks and lead.seguito else None,
        vignetta_html=vignetta_html,
    )
    colonna = _strilli_html(strilli) + _dentro_html(dentro)
    vetrina = (
        _masthead(logo_uri, newspaper_name)
        + f'<div class="dateline"><span>{html.escape(italian_date(day))}</span>'
        f'<span class="folio">{html.escape(folio_prima)}</span></div>'
        + '<div class="vetrina">'
        f'<div class="vetrina-main">{apertura}</div>'
        f'<div class="vetrina-side">{colonna}</div>'
        '</div>'
        + _spalla_html(spalla, pagina_di.get(id(spalla), 2), gfx)
    )
    pages = [
        _wrap_page(vetrina + (continua(1) if chunks else chiusura(1)))
    ]

    for indice, chunk in enumerate(chunks):
        numero = indice + 2
        testa = (
            f'<div class="continuation">{testatina}'
            f'<span class="folio">{html.escape(short_italian_date(day))} · '
            f"Pagina {numero} di {total}</span>"
            "</div>"
        )
        # Il seguito dell'apertura apre la prima pagina interna, dove chi
        # ha girato pagina lo sta cercando.
        if indice == 0:
            testa += _lead_segue_html(lead, gfx)

        # Una sezione può finire a cavallo di due pagine: la testata si
        # ripete in cima alla successiva con "(segue)".
        precedente = chunks[indice - 1][-1] if indice > 0 and chunks[indice - 1] else None
        continues = getattr(precedente, "section", "") if precedente is not None else ""

        corpo = (
            testa
            + _articles_html(
                chunk,
                f"Le notizie di {giorno_e_mese(raccontato)}",
                gfx,
                top_count,
                stats=stats_by_section,
                total_messages=total_messages,
                continues=continues,
            )
            + (chiusura(numero) if numero == total else continua(numero))
        )
        pages.append(_wrap_page(corpo))

    return pages


async def render_html_to_png(
    html_content: str, output_path: str, width: int = PAGE_WIDTH, scale: int = 2
) -> None:
    """Renderizza a `scale` volte la risoluzione CSS: Telegram ricomprime le
    foto in JPEG e partendo dal doppio della risoluzione il testo resta
    nitido. `networkidle` serve perché il font Archivo arriva da Google
    Fonts: con `load` la pagina a volte viene catturata col fallback."""
    from playwright.async_api import async_playwright

    # Alcuni ambienti (container di CI, sandbox) hanno già un Chromium
    # installato a mano, con una revisione diversa da quella che Playwright
    # si aspetta: senza questa via d'uscita l'unico modo di renderizzare
    # sarebbe riscaricare il browser.
    executable = os.environ.get("CHROMIUM_EXECUTABLE_PATH") or None

    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=executable)
        try:
            page = await browser.new_page(
                viewport={"width": width, "height": 900},
                device_scale_factor=scale,
            )
            await page.set_content(html_content, wait_until="load")
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass  # senza rete il fallback di sistema va comunque bene
            await page.locator("body").screenshot(path=output_path)
        finally:
            await browser.close()
