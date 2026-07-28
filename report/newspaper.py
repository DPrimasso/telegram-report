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

CSS = """
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 40px 55px 30px 55px;
  background: #f4f1e8;
  color: #1a1a1a;
  font-family: Georgia, 'Times New Roman', 'Liberation Serif', serif;
  width: 1100px;
}
.masthead { text-align: center; border-bottom: 4px double #1a1a1a; padding-bottom: 10px; }
.masthead h1 { font-size: 52px; margin: 0; letter-spacing: 2px; text-transform: uppercase; }
.dateline {
  display: flex; justify-content: space-between; font-size: 12px;
  text-transform: uppercase; letter-spacing: 1px;
  border-bottom: 1px solid #1a1a1a; padding: 6px 0 10px 0; margin-bottom: 26px;
}
.lead { border-bottom: 2px solid #1a1a1a; padding-bottom: 22px; margin-bottom: 26px; }
.lead h2 { font-size: 36px; line-height: 1.15; margin: 0 0 10px 0; }
.lead .deck { font-style: italic; font-size: 17px; color: #333; margin: 0 0 16px 0; }
.lead .body { columns: 2; column-gap: 32px; font-size: 14.5px; line-height: 1.5; text-align: justify; }
.lead .body p { margin: 0 0 10px 0; }
.lead .body p:first-of-type::first-letter {
  float: left; font-size: 56px; line-height: 0.78; padding: 4px 8px 0 0; font-weight: bold;
}
.articles { columns: 3; column-gap: 28px; }
.article { break-inside: avoid; margin-bottom: 22px; padding-bottom: 16px; border-bottom: 1px solid #ccc4ac; }
.article h3 { font-size: 17px; margin: 0 0 6px 0; line-height: 1.25; }
.article .meta { font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; color: #666; margin-bottom: 6px; }
.article .body { font-size: 12.5px; line-height: 1.42; text-align: justify; margin: 0; }
.footer {
  margin-top: 10px; border-top: 1px solid #1a1a1a; padding-top: 8px;
  font-size: 10px; text-align: center; color: #666; font-style: italic;
}
"""


def italian_date(day: date) -> str:
    weekday = _IT_WEEKDAYS[day.weekday()]
    month = _IT_MONTHS[day.month - 1]
    return f"{weekday} {day.day} {month} {day.year}"


def build_front_page_html(
    newspaper_name: str,
    day: date,
    lead_headline: str,
    lead_deck: str,
    lead_paragraphs: list[str],
    articles: list[tuple[str, str, int]],
) -> str:
    """articles: lista di (titolo, corpo, numero_messaggi), già ordinata
    per rilevanza (chi chiama decide l'ordine)."""
    esc = html.escape

    lead_body_html = "".join(f"<p>{esc(p)}</p>" for p in lead_paragraphs) or (
        "<p>Nessun dettaglio disponibile.</p>"
    )

    articles_html_parts = []
    for headline, body, count in articles:
        if not headline:
            continue
        count_label = "messaggio" if count == 1 else "messaggi"
        articles_html_parts.append(
            f'<div class="article"><h3>{esc(headline)}</h3>'
            f'<div class="meta">{count} {count_label}</div>'
            f"<p class=\"body\">{esc(body)}</p></div>"
        )
    articles_html = "".join(articles_html_parts)

    return f"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<style>{CSS}</style>
</head>
<body>
  <div class="masthead"><h1>{esc(newspaper_name)}</h1></div>
  <div class="dateline">
    <span>{esc(italian_date(day))}</span>
    <span>Edizione Quotidiana</span>
  </div>
  <div class="lead">
    <h2>{esc(lead_headline) or 'Giornata senza articolo di apertura'}</h2>
    {f'<p class="deck">{esc(lead_deck)}</p>' if lead_deck else ''}
    <div class="body">{lead_body_html}</div>
  </div>
  <div class="articles">{articles_html}</div>
  <div class="footer">Generato automaticamente da un'analisi dei messaggi del gruppo</div>
</body>
</html>"""


async def render_html_to_png(html_content: str, output_path: str, width: int = 1150) -> None:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            page = await browser.new_page(viewport={"width": width, "height": 900})
            await page.set_content(html_content, wait_until="load")
            await page.screenshot(path=output_path, full_page=True)
        finally:
            await browser.close()
