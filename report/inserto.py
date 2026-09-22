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
"""

import html
from datetime import date
from pathlib import Path

from report.newspaper import (
    MAX_PAGE_HEIGHT,
    _dateline_html,
    _footer_html,
    _masthead,
    _text_height,
    _wrap_page,
    data_uri,
)

# Stime in px CSS, sullo stesso principio di report/newspaper.py: per
# eccesso, perche' un'ultima pagina che sfonda il tetto e' peggio di una
# pagina un po' corta.
_H_CHROME_PRIMA = 150 + 60 + 40  # testata + dateline + margine sotto l'intro
_H_CHROME_CONT = 60 + 20  # dateline sulle pagine successive
_H_FOOTER = 120
_H_INTRO_BASE = 90  # occhiello + titolo + margini, il deck si stima a parte
_H_DOMANDA_BASE = 90  # etichetta "DOMANDA N", regolo e margini del blocco
_H_VIRGOLETTATO_BASE = 60  # bordo, "chi", margini del blocco citazione

EDIZIONE_LABEL = "Inserto settimanale"


def _stima_intro(deck: str) -> int:
    if not deck:
        return _H_INTRO_BASE
    return _H_INTRO_BASE + _text_height(deck, chars_per_line=62, line_height=33) + 12


def _stima_domanda(domanda: str, risposta: str) -> int:
    h = _H_DOMANDA_BASE
    h += _text_height(domanda, chars_per_line=40, line_height=44)
    h += _H_VIRGOLETTATO_BASE
    h += _text_height(risposta, chars_per_line=48, line_height=32)
    return h


def _intro_html(nome_intervistato: str, deck: str) -> str:
    deck_html = f'<p class="deck">{html.escape(deck)}</p>' if deck else ""
    return (
        '<div class="lead"><div class="kicker">Intervista della settimana</div>'
        f"<h2>{html.escape(nome_intervistato)}</h2>{deck_html}</div>"
    )


def _domanda_html(numero: int, domanda: str, risposta: str, nome_intervistato: str) -> str:
    return (
        '<div class="article"><div class="article-head">'
        f'<span class="topic-tag">DOMANDA {numero}</span></div>'
        f"<h3>{html.escape(domanda)}</h3>"
        f'<div class="virgolettato"><p>«{html.escape(risposta)}»</p>'
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
    deck: str = "",
) -> list[str]:
    """Le pagine dell'inserto: intro (occhiello, nome, sommario) seguita
    dalla sequenza di domande e risposte, impaginate come i pezzi del
    gazzettino (stesso `.article`/`.virgolettato`). Ritorna una pagina HTML
    completa per ogni pagina, pronta per render_html_to_png."""
    logo_uri = data_uri(logo_path) if logo_path and Path(logo_path).exists() else None
    firma_uri = data_uri(firma_path) if firma_path and Path(firma_path).exists() else None

    blocchi = [
        (_stima_domanda(domanda, risposta), _domanda_html(i, domanda, risposta, nome_intervistato))
        for i, (domanda, risposta) in enumerate(domande_risposte, start=1)
    ]

    pagine_blocchi: list[list[str]] = [[]]
    altezza_corrente = _H_CHROME_PRIMA + _stima_intro(deck) + _H_FOOTER
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
            interno = _masthead(logo_uri, newspaper_name) + dateline + _intro_html(
                nome_intervistato, deck
            ) + corpo
        else:
            interno = dateline + corpo
        interno += _footer_html(numero, totale, firma_uri)
        pagine_html.append(_wrap_page(interno))
    return pagine_html
