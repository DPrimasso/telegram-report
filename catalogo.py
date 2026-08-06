"""Campionario degli elementi grafici, in un'immagine sola.

Serve a decidere guardando invece che immaginando: ogni elemento è
renderizzato alla dimensione che avrà in pagina, con accanto il motivo per
cui c'è e quanto rischia di stonare. In fondo c'è un anti-esempio, che è
la parte più utile — la differenza fra una pagina sobria e una pacchiana
non si spiega a parole, si vede messa a confronto.

    python catalogo.py            # scrive catalogo.png

Non chiama né Telegram né OpenAI: gira offline, come preview.py.
"""

import argparse
import asyncio
from pathlib import Path

from preview import SAMPLE_HOURS, SAMPLE_INDEX
from report.graphics import (
    _GLYPHS,
    hourly_chart_svg,
    share_bar_svg,
    topic_glyph_svg,
    weight_bar_svg,
)
from report.newspaper import (
    AZZURRO,
    AZZURRO_DEEP,
    AZZURRO_PALE,
    GROUND,
    INK,
    NAVY,
    PAGE_WIDTH,
    render_html_to_png,
)

CSS = f"""
* {{ box-sizing: border-box; }}
body {{
  margin: 0; width: {PAGE_WIDTH}px; background: {GROUND}; color: {INK};
  font-family: Archivo, 'Helvetica Neue', Arial, sans-serif;
}}
h1, h2 {{ margin: 0; font-weight: 800; letter-spacing: -0.025em; }}
p {{ margin: 0; }}

.head {{ background: {NAVY}; color: #fff; padding: 34px 56px 30px 56px; }}
.head h1 {{ font-size: 46px; line-height: 1.05; }}
.head p {{ color: {AZZURRO_PALE}; font-size: 19px; margin-top: 12px; line-height: 1.45; }}
.rule {{ height: 6px; background: {AZZURRO}; }}

.item {{ padding: 30px 56px; border-bottom: 2px solid {NAVY}; background: #fff; }}
.item:nth-child(even) {{ background: {GROUND}; }}
.item-head {{ display: flex; align-items: baseline; gap: 16px; margin-bottom: 6px; }}
.item h2 {{ font-size: 30px; }}
.verdict {{
  font-size: 14px; font-weight: 800; letter-spacing: 0.12em;
  text-transform: uppercase; padding: 5px 10px; white-space: nowrap;
}}
.si {{ background: {NAVY}; color: #fff; }}
.forse {{ background: {AZZURRO}; color: {NAVY}; }}
.no {{ background: #b3261e; color: #fff; }}
.why {{ font-size: 20px; line-height: 1.45; color: #3d3d3d; margin-bottom: 20px; max-width: 900px; }}

.demo {{ padding: 24px; background: #fff; border: 2px solid {NAVY}; }}
.demo.dark {{ background: {NAVY}; }}
.shot-label {{
  font-size: 14px; font-weight: 800; letter-spacing: 0.12em;
  text-transform: uppercase; color: {AZZURRO_DEEP}; margin-top: 10px;
}}

.proof {{ font-size: 28px; line-height: 1.5; }}
.proof.dropcap::first-letter {{
  float: left; font-size: 96px; line-height: 0.78; font-weight: 800;
  color: {NAVY}; padding: 8px 14px 0 0;
}}
.end-mark {{
  display: inline-block; width: 15px; height: 15px;
  background: {AZZURRO}; position: relative; top: 1px;
}}

.row {{ display: flex; align-items: center; gap: 14px; font-size: 16px; font-weight: 700; color: #5a5a5a; }}
.row + .row {{ margin-top: 14px; }}
.row .name {{ width: 190px; color: {INK}; }}

.glyph-grid {{ display: flex; flex-wrap: wrap; gap: 10px; }}
.glyph-cell {{
  display: inline-flex; align-items: center; gap: 8px; border: 2px solid {NAVY};
  padding: 8px 12px; font-size: 16px; font-weight: 700;
}}
.glyph-cell svg {{ color: {AZZURRO_DEEP}; }}

.chart-demo .section-label {{
  display: block; font-size: 15px; font-weight: 800; letter-spacing: 0.14em;
  text-transform: uppercase; color: {AZZURRO_PALE}; margin-bottom: 16px;
}}

/* --- Anti-esempio: tutto quello che il gazzettino non fa ------------- */
.bad {{
  background: linear-gradient(135deg, #1b6ef3, #12d6a0 55%, #ffd400);
  padding: 26px; border-radius: 22px; box-shadow: 0 14px 34px rgba(0,0,0,.35);
  color: #fff; text-align: center; font-family: Georgia, 'Times New Roman', serif;
}}
.bad h3 {{
  margin: 0 0 10px 0; font-size: 40px; font-style: italic;
  text-shadow: 3px 3px 0 rgba(0,0,0,.45);
}}
.bad .sub {{ font-size: 22px; margin-bottom: 16px; }}
.bad .badges {{ display: flex; justify-content: center; gap: 10px; flex-wrap: wrap; }}
.bad .badge {{
  background: rgba(255,255,255,.28); border: 2px dashed #fff; border-radius: 999px;
  padding: 8px 18px; font-size: 20px; font-weight: bold;
}}
"""


def _item(title: str, verdict: str, cls: str, why: str, demo: str) -> str:
    return (
        f'<div class="item"><div class="item-head"><h2>{title}</h2>'
        f'<span class="verdict {cls}">{verdict}</span></div>'
        f'<p class="why">{why}</p>{demo}</div>'
    )


def build_html() -> str:
    items = []

    items.append(_item(
        "Capolettera e fine pezzo",
        "consigliato",
        "si",
        "Due convenzioni tipografiche, non due decorazioni: il capolettera dice dove "
        "comincia il pezzo principale, il quadratino dice dove finisce. Costano zero "
        "spazio, non possono stonare perché non aggiungono un linguaggio nuovo, e sono "
        "la differenza più netta fra «testo impaginato» e «testo incollato».",
        '<div class="demo"><p class="proof dropcap">La trattativa si è chiusa nella '
        "tarda serata di lunedì sulla formula del prestito con diritto di riscatto "
        "fissato a dodici milioni. Le parti si sono date appuntamento a mercoledì "
        'per la firma.&#160;<span class="end-mark"></span></p></div>',
    ))

    rows = "".join(
        f'<div class="row"><span class="name">{topic}</span>'
        f"{weight_bar_svg(count, SAMPLE_INDEX[0][1])}<span>{count} messaggi</span></div>"
        for topic, count in SAMPLE_INDEX[:4]
    )
    items.append(_item(
        "Barretta di peso",
        "consigliato",
        "si",
        "Sta sulla riga del contatore, che c'era già. «54 messaggi» da solo non dice "
        "se è tanto: accanto alla barretta si legge in un colpo d'occhio che quel topic "
        "pesa la metà del primo. Informazione vera, ingombro zero.",
        f'<div class="demo">{rows}</div>',
    ))

    items.append(_item(
        "Andamento orario",
        "consigliato",
        "si",
        "L'unico elemento che racconta <b>quando</b> è successo: il gazzettino dice cosa "
        "si è detto, il grafico dice che se n'è parlato tutto d'un fiato dopo cena. "
        "Sta nella fascia navy di chiusura, insieme ai quattro numeri, e li completa "
        "invece di ripeterli.",
        '<div class="demo dark chart-demo">'
        '<span class="section-label">Il ritmo della giornata</span>'
        f"{hourly_chart_svg(SAMPLE_HOURS, width=920)}</div>",
    ))

    items.append(_item(
        "Barra delle proporzioni",
        "opzionale",
        "forse",
        "Dice quanto ha pesato ogni topic sulla giornata. È corretta e leggibile, ma "
        "l'indice a chip qui sopra dice già i numeri: nelle giornate con un topic "
        "dominante aggiunge poco, in quelle equilibrate diventa una fila di segmenti "
        "tutti uguali. Da tenere spenta di default e accendere se piace.",
        f'<div class="demo">{share_bar_svg(SAMPLE_INDEX, width=920)}</div>',
    ))

    cells = "".join(
        f'<span class="glyph-cell">{topic_glyph_svg(topic, size=20)}{topic}</span>'
        for topic, _ in SAMPLE_INDEX
    )
    extra = "".join(
        f'<span class="glyph-cell">'
        f'<svg width="20" height="20" viewBox="0 0 24 24" fill="none" '
        f'stroke="{AZZURRO_DEEP}" stroke-width="2" stroke-linecap="square">{body}</svg>'
        f"{name}</span>"
        for name, body in _GLYPHS.items()
    )
    items.append(_item(
        "Pittogrammi dei topic",
        "opzionale",
        "forse",
        "Set disegnato a mano, tutto sulla stessa griglia e sullo stesso tratto: è "
        "l'omogeneità che lo salva, non il singolo segno. L'abbinamento topic → segno "
        "è fatto da un elenco di parole chiave, mai dal modello, così lo stesso topic "
        "ha sempre lo stesso segno. Il rischio resta il topic che non c'entra con "
        "nessuna icona: lì il ripiego è tre puntini, cioè niente. "
        "<b>Le emoji al posto di questi segni sono la via più rapida al pacchiano.</b>",
        f'<div class="demo"><div class="glyph-grid">{cells}</div>'
        f'<div class="shot-label">Il set completo</div>'
        f'<div class="glyph-grid" style="margin-top:10px">{extra}</div></div>',
    ))

    items.append(_item(
        "Come si diventa pacchiani",
        "da evitare",
        "no",
        "Non è un esempio inventato per gonfiare il confronto: è la somma di cinque "
        "scorciatoie che si prendono una alla volta senza accorgersene — gradiente al "
        "posto del colore pieno, ombra portata, angoli arrotondati, un secondo (e terzo) "
        "carattere tipografico, emoji al posto dei segni. Ognuna sembra innocua da sola. "
        "La regola che le tiene fuori tutte è una: <b>ogni elemento grafico deve dire "
        "qualcosa che il testo non dice</b>. Nessuna di queste dice niente.",
        '<div class="demo"><div class="bad"><h3>🔥 Le news di oggi! ⚽</h3>'
        '<div class="sub">✨ Tutto quello che ti sei perso ✨</div>'
        '<div class="badges"><span class="badge">🚀 Mercato</span>'
        '<span class="badge">😱 Partita</span>'
        '<span class="badge">💬 Off topic</span></div></div></div>',
    ))

    return f"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;600;800&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<div class="head">
  <h1>Campionario grafico</h1>
  <p>Ogni elemento è mostrato alla dimensione che avrebbe in pagina, con il motivo
  per cui c'è. Il criterio è sempre lo stesso: un elemento grafico si tiene solo se
  dice qualcosa che il testo non dice.</p>
</div>
<div class="rule"></div>
{''.join(items)}
</body>
</html>"""


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="catalogo.png")
    parser.add_argument("--scale", type=int, default=1)
    args = parser.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    await render_html_to_png(build_html(), str(out), scale=args.scale)
    print(f"scritto {out}")


if __name__ == "__main__":
    asyncio.run(main())
