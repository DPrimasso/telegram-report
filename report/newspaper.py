"""Composizione della prima pagina del gazzettino in stile "Azzurro Fluido".

Sostituisce integralmente il vecchio report/newspaper.py. Differenze
principali rispetto alla versione a quotidiano di carta:

- una colonna sola a 1080px invece di due colonne a 1100px: dopo la
  ricompressione JPEG di Telegram un corpo a 17px su colonne da 500px era
  al limite della leggibilità su telefono. Qui il corpo sta a 28-30px.
- palette e marchio del canale (navy #0c2340 / azzurro #17a3e0) al posto
  della carta avorio, così il report si riconosce nello scroll della chat.
- blocchi nuovi: indice dei topic con i contatori, barra statistiche,
  frase del giorno, foto di apertura.
- le pagine non sono più al massimo due: le notizie si distribuiscono su
  quante pagine servono, ognuna sotto la stessa altezza utile, perché con
  molti topic attivi l'ultima pagina raccoglieva tutto il resto e
  diventava una striscia illeggibile.
"""

import base64
import html
import mimetypes
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from report.graphics import (
    hourly_chart_svg,
    share_bar_svg,
    topic_glyph_svg,
    weight_bar_svg,
)

NAVY = "#0c2340"
AZZURRO = "#17a3e0"
AZZURRO_DEEP = "#0f6fa8"
AZZURRO_PALE = "#8fc9e8"
GROUND = "#f4f5f6"
INK = "#101820"
INK_SOFT = "#3d3d3d"

PAGE_WIDTH = 1080

# Oltre questa altezza stimata (in px CSS) la pagina diventa una striscia
# troppo lunga: Telegram la mostra rimpicciolita in anteprima e il testo
# torna illeggibile. Il tetto vale per OGNI pagina: superarlo apre la
# successiva, quante volte serve.
MAX_PAGE_HEIGHT = 2400

# Anche quando l'altezza lo permetterebbe, la prima pagina non porta più di
# così tante notizie: oltre, la gerarchia si appiattisce.
MAX_ARTICLES_FIRST_PAGE = 3

# Sotto questa soglia una pagina in più conterrebbe un trafiletto in mezzo
# al bianco: meglio una pagina sola, anche un po' più lunga. Vale solo se
# quella pagina ci sta davvero — vedi paginate_articles.
MIN_ARTICLES_FOR_SPLIT = 4

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
    kicker: str          # topic di provenienza dell'apertura
    headline: str
    deck: str
    paragraphs: list[str] = field(default_factory=list)


@dataclass
class Article:
    topic: str
    headline: str
    body: str
    count: int
    # Sommario: la riga fra titolo e testo che aggiunge informazione
    # invece di riformulare il titolo. Senza, un pezzo è titolo e blocco
    # di testo — che è quello che rende una pagina un elenco invece di un
    # giornale.
    deck: str = ""


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
    topic_glyphs: bool = True   # pittogramma nei tag e nell'indice
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
  background: {GROUND}; color: {INK};
  font-family: Archivo, 'Helvetica Neue', Arial, sans-serif;
  font-weight: 400;
}}
h1, h2, h3 {{ margin: 0; font-weight: 800; letter-spacing: -0.025em; }}
p {{ margin: 0; }}
/* Nessun angolo arrotondato in tutto il documento: la struttura la fanno
   i regoli e gli allineamenti, non le smussature. */

.masthead {{ background: {NAVY}; padding: 34px 56px 26px 56px; }}
.masthead-row {{ display: flex; align-items: flex-end; justify-content: space-between; gap: 32px; }}
.masthead img {{ width: 520px; display: block; }}
.masthead .tagline {{
  text-align: right; color: {AZZURRO_PALE}; font-size: 15px; font-weight: 600;
  letter-spacing: 0.1em; text-transform: uppercase; line-height: 1.5;
}}
.rule-accent {{ height: 6px; background: {AZZURRO}; }}

.dateline {{
  display: flex; justify-content: space-between; align-items: baseline;
  padding: 16px 56px; background: #fff; border-bottom: 2px solid {NAVY};
  font-size: 17px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase;
}}
.dateline .folio {{ color: {AZZURRO_DEEP}; }}

.section-label {{
  font-size: 15px; font-weight: 800; letter-spacing: 0.14em;
  text-transform: uppercase; color: {AZZURRO_DEEP};
}}

.index {{ padding: 22px 56px 24px 56px; background: #fff; border-bottom: 2px solid {NAVY}; }}
.index .section-label {{ display: block; margin-bottom: 14px; }}
.index-chips {{ display: flex; flex-wrap: wrap; gap: 10px; }}
.chip {{
  display: inline-flex; align-items: center; gap: 8px;
  border: 2px solid {NAVY}; padding: 7px 12px; font-size: 17px; font-weight: 700;
}}
.chip b {{ color: {AZZURRO_DEEP}; }}
.chip .glyph {{ color: {AZZURRO_DEEP}; flex: none; }}
.share {{ display: block; margin-top: 14px; }}

.lead {{ padding: 34px 56px 30px 56px; background: #fff; border-bottom: 6px solid {NAVY}; }}
.kicker {{
  display: inline-block; background: {NAVY}; color: #fff; font-size: 15px;
  font-weight: 800; letter-spacing: 0.14em; text-transform: uppercase;
  padding: 7px 12px; margin-bottom: 18px;
}}
.lead h2 {{ font-size: 66px; line-height: 1.02; letter-spacing: -0.03em; margin-bottom: 18px; }}
.lead .deck {{
  font-size: 30px; line-height: 1.35; color: {AZZURRO_DEEP};
  font-weight: 600; margin-bottom: 26px;
}}
.lead .body {{ font-size: 30px; line-height: 1.5; }}
.lead .body p {{ margin-bottom: 16px; }}
.lead .body p:last-child {{ margin-bottom: 0; color: {INK_SOFT}; }}

/* Capolettera: fa partire l'articolo di apertura da un punto preciso
   invece che dal margine come tutti gli altri paragrafi. È la differenza
   fra una pagina impaginata e un blocco di testo. Il float lo tiene
   allineato alla riga di base della terza riga. */
.lead .body.dropcap > p:first-child::first-letter {{
  float: left; font-size: 104px; line-height: 0.78; font-weight: 800;
  color: {NAVY}; padding: 8px 14px 0 0;
}}

/* Quadratino di fine pezzo: dice dove finisce l'articolo senza bisogno
   di un regolo, che a fine colonna aggiungerebbe una riga di stacco.
   Nel markup è preceduto da uno spazio unificatore, così non può finire
   da solo su una riga tutta sua — che è il modo più veloce di far
   sembrare rotta una pagina altrimenti a posto. */
.end-mark {{
  display: inline-block; width: 15px; height: 15px;
  background: {AZZURRO}; position: relative; top: 1px;
}}

.articles {{ background: {GROUND}; padding: 0 56px; }}
.articles > .section-label {{ display: block; padding: 24px 0 4px 0; }}
.article {{ border-top: 2px solid {NAVY}; padding: 26px 0; }}
.article:last-child {{ padding-bottom: 30px; }}
.article-head {{
  display: flex; justify-content: space-between; align-items: baseline;
  gap: 20px; margin-bottom: 10px;
}}
.topic-tag {{
  display: inline-flex; align-items: center; gap: 8px;
  background: {AZZURRO}; color: {NAVY}; font-size: 15px; font-weight: 800;
  letter-spacing: 0.12em; text-transform: uppercase; padding: 6px 11px;
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
  font-size: 25px; line-height: 1.3; color: {AZZURRO_DEEP};
  font-weight: 600; margin-bottom: 12px;
}}
.article .body {{ font-size: 28px; line-height: 1.45; }}

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
.brief {{ background: #fff; padding: 26px 56px 30px 56px; border-top: 6px solid {NAVY}; }}
.brief > .section-label {{ display: block; margin-bottom: 16px; }}
.brief-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0 40px; }}
.brief-item {{ border-top: 2px solid {NAVY}; padding: 14px 0; }}
.brief-item .head {{
  display: flex; align-items: center; gap: 8px; margin-bottom: 6px;
  font-size: 14px; font-weight: 800; letter-spacing: 0.12em;
  text-transform: uppercase; color: {AZZURRO_DEEP};
}}
.brief-item .head .n {{ color: #8a8a8a; }}
.brief-item p {{ font-size: 25px; line-height: 1.22; font-weight: 700; letter-spacing: -0.015em; }}

.quote {{ background: {AZZURRO}; color: {NAVY}; padding: 34px 56px; }}
.quote .section-label {{ display: block; color: {NAVY}; margin-bottom: 14px; }}
.quote p {{ font-size: 46px; line-height: 1.15; font-weight: 800; letter-spacing: -0.02em; margin-bottom: 12px; }}
.quote .attrib {{ font-size: 20px; font-weight: 700; }}

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
  background: {NAVY}; color: {AZZURRO_PALE}; border-top: 2px solid {AZZURRO};
  padding: 18px 56px; display: flex; justify-content: space-between;
  font-size: 15px; letter-spacing: 0.08em; text-transform: uppercase;
}}
.footer-continue {{
  background: {NAVY}; color: {AZZURRO_PALE}; border-top: 6px solid {AZZURRO};
  padding: 20px 56px; display: flex; justify-content: space-between; align-items: baseline;
}}
.footer-continue .note {{ font-size: 17px; letter-spacing: 0.08em; text-transform: uppercase; }}
.footer-continue .next {{
  font-size: 22px; font-weight: 800; letter-spacing: 0.06em;
  text-transform: uppercase; color: {AZZURRO};
}}

/* Testatina della seconda pagina: più bassa della prima, così si capisce a
   colpo d'occhio che è la continuazione e non un secondo giornale. */
.continuation {{
  background: {NAVY}; padding: 24px 56px; display: flex;
  align-items: center; justify-content: space-between; gap: 24px;
}}
.continuation img {{ width: 340px; display: block; }}
.continuation .folio {{
  color: {AZZURRO_PALE}; font-size: 17px; font-weight: 700;
  letter-spacing: 0.1em; text-transform: uppercase;
}}
"""


def _wrap_page(inner: str) -> str:
    return f"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;600;800&display=swap" rel="stylesheet">
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
        else f'<h1 style="color:#fff;font-size:64px;text-transform:uppercase">'
        f"{html.escape(newspaper_name)}</h1>"
    )
    return (
        f'<div class="masthead"><div class="masthead-row">{brand}'
        '<div class="tagline">Il Gazzettino<br>del gruppo</div>'
        f'</div></div><div class="rule-accent"></div>'
    )


def _index_html(entries: list[tuple[str, int]], gfx: GraphicsOptions) -> str:
    if not entries:
        return ""
    chips = "".join(
        f'<span class="chip">'
        f"{topic_glyph_svg(topic, size=18) if gfx.topic_glyphs else ''}"
        f"{html.escape(topic)} <b>{count}</b></span>"
        for topic, count in entries
    )
    share = share_bar_svg(entries) if gfx.share_bar else ""
    return (
        '<div class="index"><span class="section-label">In questa edizione</span>'
        f'<div class="index-chips">{chips}</div>{share}</div>'
    )


def _lead_html(lead: Lead, gfx: GraphicsOptions) -> str:
    kicker = (
        f'<div class="kicker">Apertura · {html.escape(lead.kicker)}</div>'
        if lead.kicker
        else '<div class="kicker">Apertura</div>'
    )
    deck = f'<p class="deck">{html.escape(lead.deck)}</p>' if lead.deck else ""
    end = END_MARK if gfx.end_mark else ""
    paragraphs = lead.paragraphs or ["Nessun dettaglio disponibile."]
    body = "".join(
        f"<p>{html.escape(p)}{end if i == len(paragraphs) - 1 else ''}</p>"
        for i, p in enumerate(paragraphs)
    )
    headline = html.escape(lead.headline) or "Giornata senza articolo di apertura"
    # Il capolettera va sul primo paragrafo, che dopo la foto è comunque il
    # primo blocco di testo lungo della pagina.
    body_class = "body dropcap" if gfx.drop_cap else "body"
    return (
        f'<div class="lead">{kicker}<h2>{headline}</h2>{deck}'
        f'<div class="{body_class}">{body}</div></div>'
    )


def _articles_html(
    articles: list[Article], label: str, gfx: GraphicsOptions, top_count: int = 0
) -> str:
    if not articles:
        return ""
    blocks = []
    for a in articles:
        if not a.headline:
            continue
        unit = "messaggio" if a.count == 1 else "messaggi"
        glyph = topic_glyph_svg(a.topic, size=17) if gfx.topic_glyphs else ""
        weight = weight_bar_svg(a.count, top_count) if gfx.weight_bars else ""
        end = END_MARK if gfx.end_mark else ""
        deck = f'<p class="deck">{html.escape(a.deck)}</p>' if a.deck else ""
        # Senza corpo il segno di fine pezzo va sul sommario, o resterebbe
        # appeso a un paragrafo vuoto.
        if a.body:
            body = deck + f'<p class="body">{html.escape(a.body)}{end}</p>'
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
    return (
        f'<div class="articles"><span class="section-label">{html.escape(label)}</span>'
        + "".join(blocks)
        + "</div>"
    )


def _number_html(entries: list[tuple[str, int]], stats: Stats | None) -> str:
    """Il dato grande della giornata.

    Non è una statistica in più — quelle stanno già nella fascia navy in
    fondo. È l'unico modo di dare peso visivo alla testa della pagina
    senza un'immagine: un numero grande occupa lo spazio e lo giustifica,
    perché quello spazio lo riempie di informazione."""
    if not entries:
        return ""
    topic, count = entries[0]
    share = ""
    total = sum(c for _, c in entries)
    if total > 0 and stats is not None:
        share = f" — <b>{round(100 * count / total)}%</b> di tutto quello che si è detto"
    return (
        '<div class="number">'
        f'<span class="big">{count}</span>'
        f'<span class="said">messaggi su <b>{html.escape(topic)}</b>{share}</span>'
        "</div>"
    )


def _brief_html(articles: list[Article], gfx: GraphicsOptions) -> str:
    """I topic minori: tag, contatore e titolo, su due colonne."""
    if not articles:
        return ""
    items = []
    for a in articles:
        if not a.headline:
            continue
        glyph = topic_glyph_svg(a.topic, size=15) if gfx.topic_glyphs else ""
        items.append(
            '<div class="brief-item"><div class="head">'
            f"{glyph}<span>{html.escape(a.topic)}</span>"
            f'<span class="n">{a.count}</span></div>'
            f"<p>{html.escape(a.headline)}</p></div>"
        )
    if not items:
        return ""
    return (
        '<div class="brief"><span class="section-label">In breve</span>'
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


def _stats_html(
    stats: Stats | None, hourly: list[int] | None, gfx: GraphicsOptions
) -> str:
    chart = ""
    if gfx.hourly_chart and hourly:
        svg = hourly_chart_svg(hourly)
        if svg:
            chart = (
                '<div class="chart-block">'
                '<span class="section-label">Il ritmo della giornata</span>'
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

# Stime in px CSS ricavate dalle misure reali del layout: servono solo a
# decidere se spezzare la pagina, non a posizionare nulla, quindi
# un'approssimazione grossolana basta.
_H_CHROME = 150 + 60 + 120          # testata + dateline + footer
_H_CONT_CHROME = 90 + 120           # testatina di continuazione + footer
_H_INDEX_ROW = 46
_H_QUOTE = 220
_H_STATS = 120
_H_CHART = 200          # titolo + grafico orario + regolo di separazione
_H_NUMBER = 145         # blocco del dato grande
_H_BRIEF_HEAD = 70      # titolo del box "In breve"
_H_BRIEF_ROW = 108      # una riga del box (due voci affiancate)
_H_SHARE = 48           # barra delle proporzioni sotto l'indice

# Frase del giorno e statistiche stanno sempre in ultima pagina: chi
# impagina deve tenerne lo spazio da parte.
_H_TAIL = _H_QUOTE + _H_STATS


def _estimate_lead_height(lead: Lead) -> int:
    h = 120  # kicker + padding
    h += _text_height(lead.headline, chars_per_line=26, line_height=68)
    h += _text_height(lead.deck, chars_per_line=52, line_height=41)
    for p in lead.paragraphs:
        h += _text_height(p, chars_per_line=58, line_height=45) + 16
    return h


def _estimate_article_height(a: Article) -> int:
    h = 90  # tag + contatore + regolo + padding
    h += _text_height(a.headline, chars_per_line=40, line_height=44)
    h += _text_height(a.deck, chars_per_line=62, line_height=33) + (12 if a.deck else 0)
    h += _text_height(a.body, chars_per_line=62, line_height=41)
    return h


def _text_height(text: str, chars_per_line: int, line_height: int) -> int:
    if not text:
        return 0
    lines = max(1, -(-len(text) // chars_per_line))
    return lines * line_height


def paginate_articles(
    articles: list[Article],
    lead: Lead,
    index_rows: int,
    *,
    tail_height: int = _H_TAIL,
    index_extra: int = 0,
) -> list[list[Article]]:
    """Distribuisce le notizie su quante pagine servono e restituisce una
    lista per pagina; la prima sta sotto l'apertura.

    Il numero di pagine non è fissato: dipende da quanto testo c'è. Con
    dieci topic attivi una seconda pagina unica raccoglieva tutto il resto
    e diventava una striscia che Telegram mostra rimpicciolita, cioè
    illeggibile — che è il motivo per cui il tetto d'altezza vale per ogni
    pagina e non solo per la prima.

    `tail_height` e `index_extra` esistono perché gli elementi grafici
    opzionali cambiano l'altezza dei blocchi fissi: il grafico orario
    allunga la chiusura di circa 200px, e ignorarlo faceva sfondare
    l'ultima pagina proprio nel caso in cui era più piena."""
    usable = [a for a in articles if a.headline]
    first_base = (
        _H_CHROME
        + index_rows * _H_INDEX_ROW
        + index_extra
        + _estimate_lead_height(lead)
    )

    # Con poche notizie una pagina sola è meglio di due, ma solo se ci
    # stanno davvero: da quando la chiusura porta anche il box "In breve"
    # e il provino, la coda pesa quasi mille pixel e tre trafiletti
    # bastavano a mandare la pagina unica ben oltre il tetto. La soglia
    # non è più l'unica condizione: conta anche l'altezza.
    if len(usable) < MIN_ARTICLES_FOR_SPLIT:
        single = (
            first_base
            + sum(_estimate_article_height(a) for a in usable)
            + tail_height
        )
        if single <= MAX_PAGE_HEIGHT or len(usable) < 2:
            return [usable]

    height = first_base
    first: list[Article] = []
    for a in usable:
        if len(first) >= MAX_ARTICLES_FIRST_PAGE:
            break
        nxt = height + _estimate_article_height(a)
        # La prima notizia resta in prima pagina comunque: una prima con la
        # sola apertura lascerebbe vuoto lo spazio sotto il taglio.
        if first and nxt > MAX_PAGE_HEIGHT:
            break
        height = nxt
        first.append(a)

    pages = [first]
    heights = [height]

    rest = usable[len(first):]
    current: list[Article] = []
    height = _H_CONT_CHROME
    for index, a in enumerate(rest):
        # Frase del giorno e statistiche chiudono l'ultima pagina: quando
        # sistemiamo l'ultima notizia vanno contate, o è proprio la coda a
        # far sfondare la pagina finale.
        reserve = tail_height if index == len(rest) - 1 else 0
        h = _estimate_article_height(a)
        if current and height + h + reserve > MAX_PAGE_HEIGHT:
            pages.append(current)
            heights.append(height)
            current, height = [], _H_CONT_CHROME
        current.append(a)
        height += h
    if current:
        pages.append(current)
        heights.append(height)

    # Un'ultima pagina con un solo trafiletto in mezzo al bianco si evita in
    # due modi. Riaccorparla nella precedente vale solo se ci sta davvero:
    # farlo a forza era ciò che rimetteva insieme la striscia lunga. Se non
    # ci sta, si scala giù una notizia dalla penultima, così l'edizione
    # chiude con due pezzi invece che con uno solo.
    if len(pages) > 1 and len(pages[-1]) == 1:
        merged = heights[-2] + _estimate_article_height(pages[-1][0]) + tail_height
        if merged <= MAX_PAGE_HEIGHT:
            pages[-2].extend(pages.pop())
        elif len(pages[-2]) > 1:
            pages[-1].insert(0, pages[-2].pop())

    return _balance_pages(pages, first_base, tail_height)


def _balance_pages(
    pages: list[list[Article]], first_base: int, tail_height: int
) -> list[list[Article]]:
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
    heights = {id(a): _estimate_article_height(a) for a in flat}
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
        limit = MAX_ARTICLES_FIRST_PAGE if page_number == 0 else available
        while index < len(flat) and len(current) < min(limit, available):
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
    edition_number: int | None = None,
    hourly: list[int] | None = None,
    graphics: GraphicsOptions | None = None,
) -> list[str]:
    """Compone il gazzettino e restituisce l'HTML di ciascuna pagina.

    Le pagine sono quante ne servono: una sola quando la giornata è magra,
    tre o quattro quando i topic attivi sono molti. `articles` deve arrivare
    già ordinata per rilevanza.

    `hourly` sono i 24 conteggi orari per il grafico di chiusura; senza,
    la fascia finale resta quella dei soli numeri. `graphics` decide quali
    elementi grafici accendere (default: quelli a rischio zero)."""
    gfx = graphics if graphics is not None else GraphicsOptions()
    logo_uri = data_uri(logo_path) if logo_path else None
    index_entries = index_entries or []
    index_rows = -(-len(index_entries) // 4) if index_entries else 0

    # I topic minori escono dalla colonna e diventano righe del box "In
    # breve": è la separazione che rende visibile la gerarchia.
    usable = [a for a in articles if a.headline]
    brief: list[Article] = []
    if gfx.brief_box and len(usable) > MAX_FULL_ARTICLES:
        brief = usable[MAX_FULL_ARTICLES:]
        articles = usable[:MAX_FULL_ARTICLES]

    # Il contatore più alto fa da fondoscala alle barrette di peso: il
    # confronto è fra i topic della giornata, non con una soglia fissa.
    top_count = max((a.count for a in articles), default=0)

    closing_height = (
        _H_TAIL
        + (_H_CHART if gfx.hourly_chart and hourly else 0)
        + (_H_BRIEF_HEAD + _H_BRIEF_ROW * -(-len(brief) // 2) if brief else 0)
    )
    index_extra = (_H_SHARE if gfx.share_bar and index_entries else 0) + (
        _H_NUMBER if gfx.number_block and index_entries else 0
    )
    chunks = paginate_articles(
        articles,
        lead,
        index_rows,
        tail_height=closing_height,
        index_extra=index_extra,
    )

    first_used = (
        _H_CHROME
        + index_rows * _H_INDEX_ROW
        + index_extra
        + _estimate_lead_height(lead)
    )
    total = len(chunks)
    edition = f"Edizione n. {edition_number}" if edition_number else "Edizione quotidiana"

    brand = (
        f'<img src="{logo_uri}" alt="{html.escape(newspaper_name)}">'
        if logo_uri
        else f'<span class="folio">{html.escape(newspaper_name)}</span>'
    )

    pages: list[str] = []
    for number, chunk in enumerate(chunks, start=1):
        if number == 1:
            folio = f"{edition} · Pagina 1 di {total}" if total > 1 else edition
            head = (
                _masthead(logo_uri, newspaper_name)
                + f'<div class="dateline"><span>{html.escape(italian_date(day))}</span>'
                f'<span class="folio">{html.escape(folio)}</span></div>'
                + _index_html(index_entries, gfx)
                + (_number_html(index_entries, stats) if gfx.number_block else "")
                + _lead_html(lead, gfx)
            )
            label = "Il resto della giornata"
        else:
            head = (
                f'<div class="continuation">{brand}'
                f'<span class="folio">{html.escape(short_italian_date(day))} · '
                f"Pagina {number} di {total}</span>"
                '</div><div class="rule-accent"></div>'
            )
            # "Segue dalla prima" è vero solo a pagina 2: dalla terza in poi
            # si segue la pagina precedente, non la prima.
            label = "Segue dalla prima" if number == 2 else "Segue"

        if number == total:
            note = (
                FOOTER_NOTE
                if total == 1
                else f"Fine dell'edizione · pagina {number} di {total}"
            )
            tail = (
                _brief_html(brief, gfx)
                + _quote_html(quote)
                + _stats_html(stats, hourly, gfx)
                + _footer_html(note)
            )
        else:
            tail = (
                '<div class="footer-continue">'
                f'<span class="note">{html.escape(FOOTER_NOTE)}</span>'
                f'<span class="next">Continua a pagina {number + 1} ▸</span></div>'
            )

        body = head + _articles_html(chunk, label, gfx, top_count) + tail
        pages.append(_wrap_page(body))

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
