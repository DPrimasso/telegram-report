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
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path

from report.graphics import (
    DUOTONE_FILTER,
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

# Larghezza utile del testo e delle immagini: la pagina meno i 56px di
# margine per lato.
CONTENT_WIDTH = PAGE_WIDTH - 112

# Il riquadro della foto di apertura prende le proporzioni dell'immagine,
# entro questi limiti. Il tetto serve perché una foto verticale a piena
# larghezza sarebbe alta più di mille pixel e spingerebbe l'articolo
# fuori dalla prima schermata; il minimo perché una panoramica molto
# larga diventerebbe una striscia. Fuori da questi limiti si ritaglia,
# ma è il caso raro invece che quello normale.
HERO_MAX_HEIGHT = 620
HERO_MIN_HEIGHT = 240
HERO_DEFAULT_HEIGHT = 420

# Le foto dei pezzi secondari stanno sotto quella di apertura anche in
# altezza: se fossero uguali, la gerarchia della pagina sparirebbe.
ARTICLE_PIC_MAX_HEIGHT = 340
ARTICLE_PIC_MIN_HEIGHT = 180
ARTICLE_PIC_DEFAULT_HEIGHT = 260

# Oltre questa altezza stimata (in px CSS) la pagina diventa una striscia
# troppo lunga: Telegram la mostra rimpicciolita in anteprima e il testo
# torna illeggibile. Il tetto vale per OGNI pagina: superarlo apre la
# successiva, quante volte serve.
MAX_PAGE_HEIGHT = 2400

# Anche quando l'altezza lo permetterebbe, la prima pagina non porta più di
# così tante notizie: oltre, la gerarchia si appiattisce.
MAX_ARTICLES_FIRST_PAGE = 3

# Sotto questa soglia una pagina in più conterrebbe un trafiletto in mezzo
# al bianco: meglio una pagina sola, anche un po' più lunga.
MIN_ARTICLES_FOR_SPLIT = 4

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
    # Foto del pezzo, quando ce n'è una di quel topic. Sta più bassa
    # dell'apertura per non competerci: in pagina la gerarchia la fanno
    # anche le dimensioni delle immagini, non solo quelle dei titoli.
    picture: "Hero | None" = None


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
class Hero:
    """Foto di apertura. `path` è un file locale (già scaricato); `caption`
    dice da dove arriva, perché una foto senza provenienza in un report
    automatico sembra decorazione.

    `width` e `height` sono le dimensioni vere dell'immagine, quando si
    conoscono: servono a dare al riquadro le proporzioni dell'immagine
    invece di imporgliene una fisse. Con un riquadro fisso le foto
    verticali e i fermo immagine dei video — cioè buona parte di quello
    che gira davvero in una chat — venivano tagliati a metà. Zero
    significa "non so", e si ricade sull'altezza di default."""
    path: str
    caption: str = ""
    width: int = 0
    height: int = 0


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

    # "mono" (bianco e nero), "duotone" (navy/azzurro pieno) o
    # "duotone-soft" (navy/grigio-blu). Vedi report.graphics.
    photo_treatment: str = "duotone-soft"
    drop_cap: bool = True       # capolettera sull'apertura
    end_mark: bool = True       # quadratino di fine articolo
    hourly_chart: bool = True   # andamento orario nella fascia di chiusura
    weight_bars: bool = True    # barretta di peso accanto al contatore messaggi
    topic_glyphs: bool = False  # pittogramma nei tag e nell'indice
    share_bar: bool = False     # barra delle proporzioni sotto l'indice

    @classmethod
    def none(cls) -> "GraphicsOptions":
        """Il gazzettino com'era prima di questo modulo."""
        return cls(
            photo_treatment="mono",
            drop_cap=False,
            end_mark=False,
            hourly_chart=False,
            weight_bars=False,
            topic_glyphs=False,
            share_bar=False,
        )

    @property
    def needs_duotone_filter(self) -> bool:
        return self.photo_treatment.startswith("duotone")


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

/* Le fotografie non entrano in pagina come sono: arrivano da una chat,
   con luci e dominanti tutte diverse, e accanto al navy pieno sembrano
   ritagli. Il duotone navy/azzurro le uniforma e le lega alla testata. */
.hero {{ width: 100%; height: {HERO_DEFAULT_HEIGHT}px; overflow: hidden; margin-bottom: 12px; }}
.hero img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
.hero.mono img {{ filter: grayscale(1) contrast(1.08); }}
.hero.duotone img {{ filter: url(#duotone) contrast(1.04); }}
.hero.duotone-soft img {{ filter: url(#duotone-soft) contrast(1.04); }}
.hero-caption {{
  font-size: 15px; letter-spacing: 0.06em; text-transform: uppercase; color: #5a5a5a;
  border-bottom: 2px solid {NAVY}; padding-bottom: 14px; margin-bottom: 22px;
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
.article h3 {{ font-size: 40px; line-height: 1.1; letter-spacing: -0.02em; margin-bottom: 10px; }}
.article .body {{ font-size: 28px; line-height: 1.45; }}

/* La foto del pezzo secondario sta fra titolo e testo, come nell'apertura:
   stessa grammatica, scala diversa. */
.art-pic {{ width: 100%; height: {ARTICLE_PIC_DEFAULT_HEIGHT}px; overflow: hidden; margin: 4px 0 10px 0; }}
.art-pic img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
.art-pic.mono img {{ filter: grayscale(1) contrast(1.08); }}
.art-pic.duotone img {{ filter: url(#duotone) contrast(1.04); }}
.art-pic.duotone-soft img {{ filter: url(#duotone-soft) contrast(1.04); }}
.art-pic-caption {{
  font-size: 15px; letter-spacing: 0.06em; text-transform: uppercase;
  color: #5a5a5a; margin-bottom: 14px;
}}

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


def _wrap_page(inner: str, *, duotone: bool = False) -> str:
    # Il filtro duotone è un <filter> SVG referenziato dal CSS: deve stare
    # nel documento, non nel foglio di stile. Lo includiamo solo quando
    # serve davvero, per non lasciare un nodo inerte in ogni pagina.
    defs = DUOTONE_FILTER if duotone else ""
    return f"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;600;800&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
{defs}
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


def _natural_height(picture: Hero) -> int:
    if picture.width <= 0 or picture.height <= 0:
        return 0
    return round(CONTENT_WIDTH * picture.height / picture.width)


def picture_box_height(
    picture: Hero,
    *,
    default: int = HERO_DEFAULT_HEIGHT,
    minimum: int = HERO_MIN_HEIGHT,
    maximum: int = HERO_MAX_HEIGHT,
) -> int:
    """Altezza del riquadro di un'immagine in pagina.

    Le proporzioni le detta l'immagine: è l'unico modo di non tagliare a
    metà una foto verticale o un fermo immagine di un video, che nelle
    chat sono la maggioranza — un riquadro fisso a 420px su uno scatto da
    telefono ne buttava via due terzi. I limiti restano perché la pagina
    ha una sua economia: vedi HERO_MAX_HEIGHT."""
    natural = _natural_height(picture)
    if natural <= 0:
        return default
    return max(minimum, min(maximum, natural))


def hero_box_height(hero: Hero) -> int:
    return picture_box_height(hero)


def _picture_html(
    picture: Hero | None,
    gfx: GraphicsOptions,
    *,
    box_class: str = "hero",
    default: int = HERO_DEFAULT_HEIGHT,
    minimum: int = HERO_MIN_HEIGHT,
    maximum: int = HERO_MAX_HEIGHT,
) -> str:
    if picture is None:
        return ""
    caption = (
        f'<div class="{box_class}-caption">{html.escape(picture.caption)}</div>'
        if picture.caption
        else ""
    )
    box = picture_box_height(
        picture, default=default, minimum=minimum, maximum=maximum
    )
    # Quando l'immagine è più alta del tetto si ritaglia per forza: si
    # taglia allora dal basso e non dal centro, perché in una foto il
    # soggetto sta quasi sempre nella metà alta — e in un fermo immagine
    # con i sottotitoli impressi, quello che si perde sono i sottotitoli.
    position = "center 22%" if _natural_height(picture) > box else "center"
    return (
        f'<div class="{box_class} {gfx.photo_treatment}" style="height:{box}px">'
        f'<img src="{data_uri(picture.path)}" alt="" style="object-position:{position}">'
        f"</div>{caption}"
    )


def _hero_html(hero: Hero | None, gfx: GraphicsOptions) -> str:
    return _picture_html(hero, gfx)


def _article_picture_html(picture: Hero | None, gfx: GraphicsOptions) -> str:
    return _picture_html(
        picture,
        gfx,
        box_class="art-pic",
        default=ARTICLE_PIC_DEFAULT_HEIGHT,
        minimum=ARTICLE_PIC_MIN_HEIGHT,
        maximum=ARTICLE_PIC_MAX_HEIGHT,
    )


def _lead_html(lead: Lead, hero: Hero | None, gfx: GraphicsOptions) -> str:
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
        f'{_hero_html(hero, gfx)}<div class="{body_class}">{body}</div></div>'
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
        blocks.append(
            '<div class="article"><div class="article-head">'
            f'<span class="topic-tag">{glyph}{html.escape(a.topic)}</span>'
            f'<span class="msg-count">{weight}<span>{a.count} {unit}</span></span></div>'
            f"<h3>{html.escape(a.headline)}</h3>"
            f"{_article_picture_html(a.picture, gfx)}"
            f'<p class="body">{html.escape(a.body)}{end}</p></div>'
        )
    if not blocks:
        return ""
    return (
        f'<div class="articles"><span class="section-label">{html.escape(label)}</span>'
        + "".join(blocks)
        + "</div>"
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
_H_HERO_CAPTION = 52        # didascalia + regolo sotto la foto di apertura
_H_PIC_CAPTION = 40         # didascalia sotto la foto di un pezzo
_H_QUOTE = 220
_H_STATS = 120
_H_CHART = 200          # titolo + grafico orario + regolo di separazione
_H_SHARE = 48           # barra delle proporzioni sotto l'indice

# Frase del giorno e statistiche stanno sempre in ultima pagina: chi
# impagina deve tenerne lo spazio da parte.
_H_TAIL = _H_QUOTE + _H_STATS


def _estimate_lead_height(lead: Lead, hero: Hero | None) -> int:
    h = 120  # kicker + padding
    h += _text_height(lead.headline, chars_per_line=26, line_height=68)
    h += _text_height(lead.deck, chars_per_line=52, line_height=41)
    if hero is not None:
        # Il riquadro non è più alto uguale per tutti: chi impagina deve
        # chiedere quanto misura davvero, o con una foto verticale la
        # stima sbaglia di trecento pixel.
        h += hero_box_height(hero) + _H_HERO_CAPTION
    for p in lead.paragraphs:
        h += _text_height(p, chars_per_line=58, line_height=45) + 16
    return h


def _estimate_article_height(a: Article) -> int:
    h = 90  # tag + contatore + regolo + padding
    h += _text_height(a.headline, chars_per_line=40, line_height=44)
    if a.picture is not None:
        h += (
            picture_box_height(
                a.picture,
                default=ARTICLE_PIC_DEFAULT_HEIGHT,
                minimum=ARTICLE_PIC_MIN_HEIGHT,
                maximum=ARTICLE_PIC_MAX_HEIGHT,
            )
            + _H_PIC_CAPTION
        )
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
    hero: Hero | None,
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
    if len(usable) < MIN_ARTICLES_FOR_SPLIT:
        return [usable]

    height = (
        _H_CHROME
        + index_rows * _H_INDEX_ROW
        + index_extra
        + _estimate_lead_height(lead, hero)
    )
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

    return pages


def _fit_page(chunk: list[Article], used: int) -> list[Article]:
    """Toglie le foto ai pezzi finché la pagina rientra nell'altezza utile.

    Serve perché una notizia in prima pagina ci resta comunque, anche
    quando l'apertura ha già preso quasi tutto lo spazio (vedi
    paginate_articles): senza questo, apertura ingombrante più pezzo
    illustrato mandavano la pagina trecento pixel oltre il tetto. Fra il
    testo di una notizia e la sua foto, la parte a cui si rinuncia è la
    foto — e si comincia dall'ultimo pezzo della pagina, che è il meno
    importante.

    `used` è l'altezza già occupata da testata, indice e apertura."""
    height = used + sum(_estimate_article_height(a) for a in chunk)
    fitted = list(chunk)
    for i in range(len(fitted) - 1, -1, -1):
        if height <= MAX_PAGE_HEIGHT:
            break
        if fitted[i].picture is None:
            continue
        stripped = replace(fitted[i], picture=None)
        height -= _estimate_article_height(fitted[i]) - _estimate_article_height(stripped)
        fitted[i] = stripped
    return fitted


def build_pages_html(
    newspaper_name: str,
    day: date,
    lead: Lead,
    articles: list[Article],
    *,
    logo_path: str | Path | None = None,
    hero: Hero | None = None,
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

    # Il contatore più alto fa da fondoscala alle barrette di peso: il
    # confronto è fra i topic della giornata, non con una soglia fissa.
    top_count = max((a.count for a in articles), default=0)

    closing_height = _H_TAIL + (_H_CHART if gfx.hourly_chart and hourly else 0)
    chunks = paginate_articles(
        articles,
        lead,
        hero,
        index_rows,
        tail_height=closing_height,
        index_extra=_H_SHARE if gfx.share_bar and index_entries else 0,
    )

    index_extra = _H_SHARE if gfx.share_bar and index_entries else 0
    first_used = (
        _H_CHROME
        + index_rows * _H_INDEX_ROW
        + index_extra
        + _estimate_lead_height(lead, hero)
    )
    chunks[0] = _fit_page(chunks[0], first_used)
    for number in range(1, len(chunks)):
        used = _H_CONT_CHROME + (closing_height if number == len(chunks) - 1 else 0)
        chunks[number] = _fit_page(chunks[number], used)

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
                + _lead_html(lead, hero, gfx)
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
                _quote_html(quote)
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
        # Il filtro si include solo nelle pagine che hanno un'immagine:
        # non è più solo la prima, da quando anche i pezzi possono averne.
        has_image = (number == 1 and hero is not None) or any(
            a.picture is not None for a in chunk
        )
        pages.append(
            _wrap_page(body, duotone=gfx.needs_duotone_filter and has_image)
        )

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
