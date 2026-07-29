import html
from datetime import date

# Niente dipendenza dal locale di sistema (spesso assente/incompleto sui
# runner GitHub Actions): nomi di giorni/mesi in italiano cablati.
_IT_WEEKDAYS = [
    "Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"
]
_IT_MONTHS = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]

# I corpi del testo sono dimensionati per essere leggibili su uno schermo di
# telefono dopo la ricompressione JPEG di Telegram, non per imitare le
# proporzioni di un quotidiano di carta. Per lo stesso motivo gli articoli
# stanno su due colonne e non su tre: a 17px, tre colonne su 1100px
# lascerebbero righe di cinque o sei parole.
CSS = """
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 44px 58px 32px 58px;
  background: #f4f1e8;
  color: #1a1a1a;
  font-family: Georgia, 'Times New Roman', 'Liberation Serif', serif;
  width: 1100px;
}
.masthead { text-align: center; border-bottom: 4px double #1a1a1a; padding-bottom: 12px; }
.masthead h1 { font-size: 62px; margin: 0; letter-spacing: 2px; text-transform: uppercase; }
.dateline {
  display: flex; justify-content: space-between; font-size: 15px;
  text-transform: uppercase; letter-spacing: 1px;
  border-bottom: 1px solid #1a1a1a; padding: 8px 0 12px 0; margin-bottom: 30px;
}
.lead { border-bottom: 2px solid #1a1a1a; padding-bottom: 26px; margin-bottom: 30px; }
.lead h2 { font-size: 46px; line-height: 1.14; margin: 0 0 14px 0; }
.lead .deck { font-style: italic; font-size: 22px; color: #333; margin: 0 0 20px 0; }
.lead .body { columns: 2; column-gap: 36px; font-size: 19px; line-height: 1.5; text-align: justify; }
.lead .body p { margin: 0 0 12px 0; }
/* Niente float per il capolettera: dentro un contenitore multi-colonna la
   lettera flottante si stacca dal proprio paragrafo e finisce in cima alla
   colonna successiva, lasciando la prima parola mutilata. */
.lead .body p:first-of-type::first-letter {
  font-size: 38px; font-weight: bold; line-height: 1;
}
.articles { columns: 2; column-gap: 36px; }
.article { break-inside: avoid; margin-bottom: 26px; padding-bottom: 20px; border-bottom: 1px solid #ccc4ac; }
.article h3 { font-size: 25px; margin: 0 0 8px 0; line-height: 1.22; }
.article .meta { font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; color: #666; margin-bottom: 8px; }
.article .body { font-size: 17px; line-height: 1.45; text-align: justify; margin: 0; }
.footer {
  margin-top: 14px; border-top: 1px solid #1a1a1a; padding-top: 10px;
  font-size: 13px; text-align: center; color: #666; font-style: italic;
}
/* Testatina delle pagine interne: più bassa della prima, così si capisce
   a colpo d'occhio che è la continuazione e non un secondo giornale. */
.continuation {
  display: flex; justify-content: space-between; align-items: baseline;
  border-bottom: 3px double #1a1a1a; padding-bottom: 10px; margin-bottom: 30px;
}
.continuation .name { font-size: 30px; letter-spacing: 1.5px; text-transform: uppercase; font-weight: bold; }
.continuation .folio { font-size: 15px; text-transform: uppercase; letter-spacing: 1px; color: #444; }
"""


def italian_date(day: date) -> str:
    weekday = _IT_WEEKDAYS[day.weekday()]
    month = _IT_MONTHS[day.month - 1]
    return f"{weekday} {day.day} {month} {day.year}"


# Sotto questa soglia la seconda pagina conterrebbe uno o due trafiletti in
# mezzo al bianco: meglio una pagina sola.
MIN_ARTICLES_FOR_SPLIT = 4

FOOTER_NOTE = "Generato automaticamente da un'analisi dei messaggi del gruppo"


def _articles_html(articles: list[tuple[str, str, int]]) -> str:
    esc = html.escape
    parts = []
    for headline, body, count in articles:
        if not headline:
            continue
        count_label = "messaggio" if count == 1 else "messaggi"
        parts.append(
            f'<div class="article"><h3>{esc(headline)}</h3>'
            f'<div class="meta">{count} {count_label}</div>'
            f"<p class=\"body\">{esc(body)}</p></div>"
        )
    return "".join(parts)


def _split_articles(
    articles: list[tuple[str, str, int]], lead_weight: int
) -> tuple[list[tuple[str, str, int]], list[tuple[str, str, int]]]:
    """Divide gli articoli fra le due pagine bilanciando il volume di testo,
    non il numero di pezzi: la prima pagina parte già carica dell'apertura,
    quindi le tocca una quota minore di articoli."""
    usable = [a for a in articles if a[0]]
    if len(usable) < MIN_ARTICLES_FOR_SPLIT:
        return usable, []

    weights = [len(headline) + len(body) for headline, body, _ in usable]
    target = (sum(weights) + lead_weight) / 2

    running = lead_weight
    cut = 0
    for index, weight in enumerate(weights):
        # Il mezzo peso evita che l'articolo a cavallo del target finisca
        # sempre in prima pagina, sbilanciandola.
        if index > 0 and running + weight / 2 > target:
            break
        running += weight
        cut = index + 1

    cut = max(1, min(cut, len(usable) - 1))
    return usable[:cut], usable[cut:]


def _wrap_page(inner: str) -> str:
    return f"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<style>{CSS}</style>
</head>
<body>
{inner}
</body>
</html>"""


def build_pages_html(
    newspaper_name: str,
    day: date,
    lead_headline: str,
    lead_deck: str,
    lead_paragraphs: list[str],
    articles: list[tuple[str, str, int]],
) -> list[str]:
    """Compone il giornale e restituisce l'HTML di ciascuna pagina (una o
    due). `articles` è una lista di (titolo, corpo, numero_messaggi) già
    ordinata per rilevanza da chi chiama."""
    esc = html.escape

    lead_body_html = "".join(f"<p>{esc(p)}</p>" for p in lead_paragraphs) or (
        "<p>Nessun dettaglio disponibile.</p>"
    )
    lead_weight = len(lead_headline) + len(lead_deck) + sum(
        len(p) for p in lead_paragraphs
    )
    first_articles, second_articles = _split_articles(articles, lead_weight)

    first_footer = (
        "Continua a pagina 2" if second_articles else FOOTER_NOTE
    )
    first_page = _wrap_page(
        f"""  <div class="masthead"><h1>{esc(newspaper_name)}</h1></div>
  <div class="dateline">
    <span>{esc(italian_date(day))}</span>
    <span>Edizione Quotidiana</span>
  </div>
  <div class="lead">
    <h2>{esc(lead_headline) or 'Giornata senza articolo di apertura'}</h2>
    {f'<p class="deck">{esc(lead_deck)}</p>' if lead_deck else ''}
    <div class="body">{lead_body_html}</div>
  </div>
  <div class="articles">{_articles_html(first_articles)}</div>
  <div class="footer">{first_footer}</div>"""
    )

    if not second_articles:
        return [first_page]

    second_page = _wrap_page(
        f"""  <div class="continuation">
    <span class="name">{esc(newspaper_name)}</span>
    <span class="folio">{esc(italian_date(day))} &middot; Pagina 2</span>
  </div>
  <div class="articles">{_articles_html(second_articles)}</div>
  <div class="footer">{FOOTER_NOTE}</div>"""
    )
    return [first_page, second_page]


async def render_html_to_png(
    html_content: str, output_path: str, width: int = 1150, scale: int = 2
) -> None:
    """Renderizza la pagina a `scale` volte la risoluzione CSS. Il fattore 2
    serve perché la prima pagina viene inviata come foto e Telegram
    ricomprime le foto in JPEG: partendo dal doppio della risoluzione, il
    testo dei corpi (12-14px) resta leggibile anche dopo la compressione."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            page = await browser.new_page(
                viewport={"width": width, "height": 900},
                device_scale_factor=scale,
            )
            await page.set_content(html_content, wait_until="load")
            # Ritaglia sull'altezza reale del contenuto: con full_page
            # l'immagine eredita l'altezza del viewport quando la pagina è
            # più corta, lasciando una banda vuota in fondo alla foto.
            await page.locator("body").screenshot(path=output_path)
        finally:
            await browser.close()
