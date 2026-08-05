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
- la seconda pagina non dipende più dal numero di articoli ma
  dall'altezza stimata della prima: si spezza solo quando serve davvero.
"""

import base64
import html
import mimetypes
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

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
# torna illeggibile. Sopra la soglia si passa alla seconda pagina.
MAX_PAGE_HEIGHT = 2400

# Anche quando l'altezza lo permetterebbe, la prima pagina non porta più di
# così tante notizie: oltre, la gerarchia si appiattisce.
MAX_ARTICLES_FIRST_PAGE = 3

# Sotto questa soglia una seconda pagina conterrebbe un trafiletto in mezzo
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
    automatico sembra decorazione."""
    path: str
    caption: str = ""


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
  display: inline-flex; align-items: baseline; gap: 8px;
  border: 2px solid {NAVY}; padding: 7px 12px; font-size: 17px; font-weight: 700;
}}
.chip b {{ color: {AZZURRO_DEEP}; }}

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

/* Le fotografie stampano in bianco e nero: una foto da chat, colorata e
   compressa, accanto al navy pieno spezzerebbe la pagina. */
.hero {{ width: 100%; height: 420px; overflow: hidden; margin-bottom: 12px; }}
.hero img {{ width: 100%; height: 100%; object-fit: cover; filter: grayscale(1) contrast(1.08); display: block; }}
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
  background: {AZZURRO}; color: {NAVY}; font-size: 15px; font-weight: 800;
  letter-spacing: 0.12em; text-transform: uppercase; padding: 6px 11px;
}}
.msg-count {{ font-size: 16px; font-weight: 700; color: #5a5a5a; white-space: nowrap; }}
.article h3 {{ font-size: 40px; line-height: 1.1; letter-spacing: -0.02em; margin-bottom: 10px; }}
.article .body {{ font-size: 28px; line-height: 1.45; }}

.quote {{ background: {AZZURRO}; color: {NAVY}; padding: 34px 56px; }}
.quote .section-label {{ display: block; color: {NAVY}; margin-bottom: 14px; }}
.quote p {{ font-size: 46px; line-height: 1.15; font-weight: 800; letter-spacing: -0.02em; margin-bottom: 12px; }}
.quote .attrib {{ font-size: 20px; font-weight: 700; }}

.stats {{
  background: {NAVY}; color: #fff; padding: 28px 56px;
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 24px;
}}
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


def _index_html(entries: list[tuple[str, int]]) -> str:
    if not entries:
        return ""
    chips = "".join(
        f'<span class="chip">{html.escape(topic)} <b>{count}</b></span>'
        for topic, count in entries
    )
    return (
        '<div class="index"><span class="section-label">In questa edizione</span>'
        f'<div class="index-chips">{chips}</div></div>'
    )


def _hero_html(hero: Hero | None) -> str:
    if hero is None:
        return ""
    caption = (
        f'<div class="hero-caption">{html.escape(hero.caption)}</div>'
        if hero.caption
        else ""
    )
    return f'<div class="hero"><img src="{data_uri(hero.path)}" alt=""></div>{caption}'


def _lead_html(lead: Lead, hero: Hero | None) -> str:
    kicker = (
        f'<div class="kicker">Apertura · {html.escape(lead.kicker)}</div>'
        if lead.kicker
        else '<div class="kicker">Apertura</div>'
    )
    deck = f'<p class="deck">{html.escape(lead.deck)}</p>' if lead.deck else ""
    body = "".join(f"<p>{html.escape(p)}</p>" for p in lead.paragraphs) or (
        "<p>Nessun dettaglio disponibile.</p>"
    )
    headline = html.escape(lead.headline) or "Giornata senza articolo di apertura"
    return (
        f'<div class="lead">{kicker}<h2>{headline}</h2>{deck}'
        f'{_hero_html(hero)}<div class="body">{body}</div></div>'
    )


def _articles_html(articles: list[Article], label: str) -> str:
    if not articles:
        return ""
    blocks = []
    for a in articles:
        if not a.headline:
            continue
        unit = "messaggio" if a.count == 1 else "messaggi"
        blocks.append(
            '<div class="article"><div class="article-head">'
            f'<span class="topic-tag">{html.escape(a.topic)}</span>'
            f'<span class="msg-count">{a.count} {unit}</span></div>'
            f"<h3>{html.escape(a.headline)}</h3>"
            f'<p class="body">{html.escape(a.body)}</p></div>'
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


def _stats_html(stats: Stats | None) -> str:
    if stats is None:
        return ""
    cells = [
        (stats.messages, "messaggi"),
        (stats.participants, "partecipanti"),
        (stats.active_topics, "topic attivi"),
        (stats.peak_hour, "ora di punta"),
    ]
    return '<div class="stats">' + "".join(
        f'<div><div class="value">{html.escape(str(v))}</div>'
        f'<div class="label">{label}</div></div>'
        for v, label in cells
    ) + "</div>"


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
_H_INDEX_ROW = 46
_H_HERO = 460
_H_QUOTE = 220
_H_STATS = 120


def _estimate_lead_height(lead: Lead, hero: Hero | None) -> int:
    h = 120  # kicker + padding
    h += _text_height(lead.headline, chars_per_line=26, line_height=68)
    h += _text_height(lead.deck, chars_per_line=52, line_height=41)
    if hero is not None:
        h += _H_HERO
    for p in lead.paragraphs:
        h += _text_height(p, chars_per_line=58, line_height=45) + 16
    return h


def _estimate_article_height(a: Article) -> int:
    h = 90  # tag + contatore + regolo + padding
    h += _text_height(a.headline, chars_per_line=40, line_height=44)
    h += _text_height(a.body, chars_per_line=62, line_height=41)
    return h


def _text_height(text: str, chars_per_line: int, line_height: int) -> int:
    if not text:
        return 0
    lines = max(1, -(-len(text) // chars_per_line))
    return lines * line_height


def split_articles(
    articles: list[Article],
    lead: Lead,
    hero: Hero | None,
    index_rows: int,
) -> tuple[list[Article], list[Article]]:
    """Decide quante notizie restano in prima pagina. La seconda pagina
    nasce solo se ci sono abbastanza pezzi da riempirla E la prima
    sfonderebbe l'altezza utile."""
    usable = [a for a in articles if a.headline]
    if len(usable) < MIN_ARTICLES_FOR_SPLIT:
        return usable, []

    height = (
        _H_CHROME
        + index_rows * _H_INDEX_ROW
        + _estimate_lead_height(lead, hero)
        + _estimate_article_height(usable[0])
    )
    cut = 1
    for a in usable[1:]:
        if cut >= MAX_ARTICLES_FIRST_PAGE:
            break
        nxt = height + _estimate_article_height(a)
        if nxt > MAX_PAGE_HEIGHT:
            break
        height = nxt
        cut += 1

    # Se tutto sta in prima pagina, niente pagina 2.
    tail = usable[cut:]
    if not tail:
        return usable, []
    # Una pagina 2 con un solo trafiletto: meglio tenerlo in prima.
    if len(tail) == 1 and height + _estimate_article_height(tail[0]) < MAX_PAGE_HEIGHT + 500:
        return usable, []
    return usable[:cut], tail


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
) -> list[str]:
    """Compone il gazzettino e restituisce l'HTML di ciascuna pagina (una o
    due). `articles` deve arrivare già ordinata per rilevanza."""
    logo_uri = data_uri(logo_path) if logo_path else None
    index_entries = index_entries or []
    index_rows = -(-len(index_entries) // 4) if index_entries else 0

    first, second = split_articles(articles, lead, hero, index_rows)

    edition = f"Edizione n. {edition_number}" if edition_number else "Edizione quotidiana"
    folio = f"{edition} · Pagina 1 di 2" if second else edition

    page1 = _wrap_page(
        _masthead(logo_uri, newspaper_name)
        + f'<div class="dateline"><span>{html.escape(italian_date(day))}</span>'
        f'<span class="folio">{html.escape(folio)}</span></div>'
        + _index_html(index_entries)
        + _lead_html(lead, hero)
        + _articles_html(first, "Il resto della giornata")
        + (
            '<div class="footer-continue">'
            f'<span class="note">{html.escape(FOOTER_NOTE)}</span>'
            '<span class="next">Continua a pagina 2 ▸</span></div>'
            if second
            else _quote_html(quote) + _stats_html(stats) + _footer_html()
        )
    )

    if not second:
        return [page1]

    brand = (
        f'<img src="{logo_uri}" alt="{html.escape(newspaper_name)}">'
        if logo_uri
        else f'<span class="folio">{html.escape(newspaper_name)}</span>'
    )
    page2 = _wrap_page(
        f'<div class="continuation">{brand}'
        f'<span class="folio">{html.escape(short_italian_date(day))} · Pagina 2</span>'
        '</div><div class="rule-accent"></div>'
        + _articles_html(second, "Segue dalla prima")
        + _quote_html(quote)
        + _stats_html(stats)
        + _footer_html("Fine dell'edizione · pagina 2 di 2")
    )
    return [page1, page2]


async def render_html_to_png(
    html_content: str, output_path: str, width: int = PAGE_WIDTH, scale: int = 2
) -> None:
    """Renderizza a `scale` volte la risoluzione CSS: Telegram ricomprime le
    foto in JPEG e partendo dal doppio della risoluzione il testo resta
    nitido. `networkidle` serve perché il font Archivo arriva da Google
    Fonts: con `load` la pagina a volte viene catturata col fallback."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch()
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
