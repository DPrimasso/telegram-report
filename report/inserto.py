"""Impaginazione dell'inserto settimanale: l'intervista alla persona
scelta dal bot (bot/handlers/intervista.py), nello stesso stile del
gazzettino.

Riusa gli arredi di report/newspaper.py (CSS, testata, dateline, piede
pagina) invece di duplicarli, ma non passa da build_pages_html: quella
funzione impagina una griglia di notizie diverse da bilanciare fra loro,
mentre qui c'e' un solo pezzo lineare (domanda, risposta, domanda,
risposta, ...). L'impaginazione e' percio' volutamente piu' semplice: un
riempimento pagina per pagina finche' c'e' spazio sotto MAX_PAGE_HEIGHT,
senza rimandi "a pagina N" fra un pezzo e l'altro (non servono, e' un
pezzo solo).

La domanda e la risposta non riusano semplicemente h3+virgolettato del
gazzettino: in un articolo normale il virgolettato e' una citazione
dentro un pezzo scritto da altri, quindi piccola apposta. Qui la
risposta E' tutto il contenuto del blocco, quindi ha bisogno di un corpo
grande e leggibile; la domanda e' solo il rilancio che introduce chi
parla, quindi resta leggera (corsivo, come un occhiello). Le classi
`.intervista-domanda`/`.intervista-risposta` in _CSS_EXTRA sono
apposta per questo, e vengono iniettate pagina per pagina.

L'accento cromatico e' un rosso terracotta invece dell'azzurro del
gazzettino quotidiano: stessa carta, stesso navy, stessa impaginazione —
resta la stessa testata — ma un colpo d'occhio basta per capire che
questa pagina e' l'inserto e non l'edizione del giorno.
"""

import html
from datetime import date
from pathlib import Path

from report.newspaper import (
    INK,
    MAX_PAGE_HEIGHT,
    NAVY,
    _dateline_html,
    _footer_html,
    _masthead,
    _text_height,
    _wrap_page,
    data_uri,
)

# Il rosso dell'inserto: stesso ruolo dell'azzurro nel gazzettino
# quotidiano (accento, bordo della citazione, etichette), ma un colore
# diverso perche' la pagina si distingua a colpo d'occhio pur restando
# evidentemente la stessa pubblicazione (carta, navy e testata uguali).
_ROSSO = "#9c3b2e"
_ROSSO_DEEP = "#7a2e23"

# Stime in px CSS, sullo stesso principio di report/newspaper.py: per
# eccesso, perche' un'ultima pagina che sfonda il tetto e' peggio di una
# pagina un po' corta.
_H_CHROME_PRIMA = 150 + 60 + 40  # testata + dateline + margine sotto l'intro
_H_CHROME_CONT = 60 + 20  # dateline sulle pagine successive
_H_FOOTER = 120
_H_INTRO_BASE = 90  # occhiello + titolo + margini, il deck si stima a parte
_H_FOTO = 156  # riga foto+testo quando c'e' l'immagine profilo
_H_DOMANDA_BASE = 90  # etichetta "DOMANDA N", regolo e margini del blocco
_H_RISPOSTA_BASE = 60  # bordo, "chi", margini del blocco risposta

EDIZIONE_LABEL = "Inserto settimanale"

_CSS_EXTRA = f"""
/* Gli stessi ruoli del gazzettino (bordo testata, folio, occhiello), ma
   in rosso: e' quello che rende l'inserto riconoscibile a colpo d'occhio. */
.rule-accent {{ background: {_ROSSO}; }}
.dateline .folio {{ color: {_ROSSO}; }}
.kicker {{ background: {_ROSSO}; }}

.intervista-domanda {{
  font-size: 26px; line-height: 1.3; font-weight: 500; font-style: italic;
  color: {INK}; margin-bottom: 12px;
}}
.intervista-risposta {{
  border-left: 5px solid {_ROSSO}; padding: 3px 0 3px 16px; margin: 4px 0 0 0;
}}
.intervista-risposta p {{
  font-size: 27px; line-height: 1.3; font-weight: 700; color: {NAVY};
  letter-spacing: -0.015em; margin-bottom: 6px;
}}
.intervista-risposta .chi {{
  display: block; font-size: 14px; font-weight: 800; letter-spacing: 0.1em;
  text-transform: uppercase; color: {_ROSSO_DEEP};
}}
.intervista-intro-row {{ display: flex; align-items: flex-start; gap: 24px; }}
.intervista-foto {{
  width: 140px; height: 140px; object-fit: cover; border: 2px solid {NAVY};
  flex: none;
}}
"""
_STYLE_EXTRA = f"<style>{_CSS_EXTRA}</style>"


def _stima_intro(deck: str, con_foto: bool) -> int:
    h = _H_INTRO_BASE
    if deck:
        h += _text_height(deck, chars_per_line=62, line_height=33) + 12
    if con_foto:
        h = max(h, _H_FOTO)
    return h


def _stima_domanda(domanda: str, risposta: str) -> int:
    h = _H_DOMANDA_BASE
    h += _text_height(domanda, chars_per_line=58, line_height=34)
    h += _H_RISPOSTA_BASE
    h += _text_height(risposta, chars_per_line=58, line_height=36)
    return h


def _intro_html(nome_intervistato: str, deck: str, foto_uri: str | None) -> str:
    deck_html = f'<p class="deck">{html.escape(deck)}</p>' if deck else ""
    testo_html = f"<h2>{html.escape(nome_intervistato)}</h2>{deck_html}"
    if foto_uri:
        corpo = (
            '<div class="intervista-intro-row">'
            f'<img class="intervista-foto" src="{foto_uri}" alt="">'
            f"<div>{testo_html}</div></div>"
        )
    else:
        corpo = testo_html
    return f'<div class="lead"><div class="kicker">Intervista della settimana</div>{corpo}</div>'


def _domanda_html(numero: int, domanda: str, risposta: str, nome_intervistato: str) -> str:
    return (
        '<div class="article"><div class="article-head">'
        f'<span class="topic-tag">DOMANDA {numero}</span></div>'
        f'<p class="intervista-domanda">{html.escape(domanda)}</p>'
        f'<div class="intervista-risposta"><p>«{html.escape(risposta)}»</p>'
        f'<span class="chi">{html.escape(nome_intervistato)}</span></div></div>'
    )


def build_intervista_pages_html(
    newspaper_name: str,
    day: date,
    nome_intervistato: str,
    domande_risposte: list[tuple[str, str]],
    *,
    logo_path: str | Path | None = None,
    firma_path: str | Path | None = None,
    foto_path: str | Path | None = None,
    deck: str = "",
) -> list[str]:
    """Le pagine dell'inserto: intro (occhiello, foto se disponibile, nome,
    sommario) seguita dalla sequenza di domande e risposte, impaginate
    nello stile del gazzettino. Ritorna una pagina HTML completa per ogni
    pagina, pronta per render_html_to_png."""
    logo_uri = data_uri(logo_path) if logo_path and Path(logo_path).exists() else None
    firma_uri = data_uri(firma_path) if firma_path and Path(firma_path).exists() else None
    foto_uri = data_uri(foto_path) if foto_path and Path(foto_path).exists() else None

    blocchi = [
        (_stima_domanda(domanda, risposta), _domanda_html(i, domanda, risposta, nome_intervistato))
        for i, (domanda, risposta) in enumerate(domande_risposte, start=1)
    ]

    pagine_blocchi: list[list[str]] = [[]]
    altezza_corrente = _H_CHROME_PRIMA + _stima_intro(deck, bool(foto_uri)) + _H_FOOTER
    for altezza, blocco_html in blocchi:
        supera_tetto = altezza_corrente + altezza > MAX_PAGE_HEIGHT
        if pagine_blocchi[-1] and supera_tetto:
            pagine_blocchi.append([])
            altezza_corrente = _H_CHROME_CONT + _H_FOOTER
        pagine_blocchi[-1].append(blocco_html)
        altezza_corrente += altezza

    totale = len(pagine_blocchi)
    pagine_html = []
    for numero, blocchi_pagina in enumerate(pagine_blocchi, start=1):
        corpo = f'<div class="articles">{"".join(blocchi_pagina)}</div>'
        dateline = _dateline_html(day, EDIZIONE_LABEL, numero, totale)
        if numero == 1:
            interno = (
                _STYLE_EXTRA
                + _masthead(logo_uri, newspaper_name)
                + dateline
                + _intro_html(nome_intervistato, deck, foto_uri)
                + corpo
            )
        else:
            interno = _STYLE_EXTRA + dateline + corpo
        interno += _footer_html(numero, totale, firma_uri)
        pagine_html.append(_wrap_page(interno))
    return pagine_html
