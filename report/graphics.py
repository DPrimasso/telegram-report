"""Elementi grafici del gazzettino.

Tutto quello che sta qui dentro è SVG scritto a mano e incorporato nella
pagina: niente librerie di grafici, niente immagini, niente font di
icone. Il motivo è che il gazzettino viene renderizzato da
Chromium headless dentro una GitHub Action, e ogni dipendenza esterna è
un modo in più di ritrovarsi con una pagina rotta alle tre di notte senza
nessuno che guarda.

La regola di stile che tiene insieme il file è una sola: **un elemento
grafico deve dire qualcosa che il testo non dice**. Il grafico delle ore
racconta il ritmo della giornata, la barretta accanto al contatore dice
quanto pesa quel topic rispetto agli altri, il pittogramma distingue i
topic a colpo d'occhio nell'indice. Il capolettera e il quadratino di
fine articolo sono le uniche due eccezioni ammesse, e sono convenzioni
tipografiche vecchie di secoli, non decorazione.

Tutti i disegni usano la palette del canale (navy, azzurro) e le stesse
forme del layout: tratti pieni, spigoli vivi, nessuna ombra, nessun
gradiente. È quello che separa una pagina che sembra fatta apposta da una
che sembra assemblata con le clipart.
"""

from __future__ import annotations

import html

NAVY = "#0c2340"
AZZURRO = "#17a3e0"
AZZURRO_DEEP = "#0f6fa8"
AZZURRO_PALE = "#8fc9e8"


def hourly_chart_svg(
    hourly: list[int],
    *,
    width: int = 968,
    height: int = 150,
    bar: str = AZZURRO,
    axis: str = AZZURRO_PALE,
) -> str:
    """Le 24 ore della giornata, una colonna per ora.

    È il grafico che si merita più spazio perché è l'unica cosa in pagina
    che racconta *quando* è successo qualcosa: il gazzettino dice cosa si
    è detto, il grafico dice che se ne è parlato tutto d'un fiato dopo
    cena. La statistica "ora di punta" da sola diceva il picco ma non la
    forma.

    `hourly` sono 24 interi, dalle 00 alle 23.
    """
    if not hourly or len(hourly) != 24 or max(hourly) <= 0:
        return ""

    top = max(hourly)
    gap = 5
    slot = (width - gap * 23) / 24
    label_h = 26
    plot_h = height - label_h

    bars = []
    for hour, value in enumerate(hourly):
        x = hour * (slot + gap)
        # Le ore vuote restano visibili come tacca minima: una colonna
        # assente si legge come "dato mancante", una tacca bassa si legge
        # come "silenzio", che è l'informazione vera.
        h = max(2, round(plot_h * value / top))
        opacity = "1" if value else "0.28"
        bars.append(
            f'<rect x="{x:.1f}" y="{plot_h - h}" width="{slot:.1f}" height="{h}" '
            f'fill="{bar}" opacity="{opacity}"/>'
        )

    ticks = []
    for hour in (0, 6, 12, 18, 23):
        x = hour * (slot + gap) + slot / 2
        anchor = "start" if hour == 0 else "end" if hour == 23 else "middle"
        ticks.append(
            f'<text x="{x:.1f}" y="{height - 6}" fill="{axis}" font-size="15" '
            f'font-weight="700" letter-spacing="1.2" text-anchor="{anchor}">'
            f"{hour:02d}</text>"
        )

    return (
        f'<svg class="chart" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Messaggi per ora del giorno">'
        f"{''.join(bars)}"
        f'<line x1="0" y1="{plot_h + 0.5}" x2="{width}" y2="{plot_h + 0.5}" '
        f'stroke="{axis}" stroke-width="1" opacity="0.45"/>'
        f"{''.join(ticks)}"
        "</svg>"
    )


def weight_bar_svg(
    count: int, top: int, *, width: int = 96, height: int = 8
) -> str:
    """Barretta accanto al contatore dei messaggi di un articolo.

    Serve a rendere confrontabili numeri che da soli non lo sono: "54
    messaggi" non dice se è tanto finché non lo metti accanto agli 87 del
    pezzo sopra. Occupa una riga che c'era già, quindi non costa spazio.
    """
    if top <= 0 or count <= 0:
        return ""
    filled = max(3, round(width * min(count / top, 1)))
    return (
        f'<svg class="weight" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" aria-hidden="true">'
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="{NAVY}" opacity="0.12"/>'
        f'<rect x="0" y="0" width="{filled}" height="{height}" fill="{AZZURRO_DEEP}"/>'
        "</svg>"
    )


def share_bar_svg(
    entries: list[tuple[str, int]], *, width: int = 968, height: int = 34
) -> str:
    """Barra unica divisa in proporzione ai messaggi per topic.

    Alternativa (o complemento) all'indice a chip: le chip dicono i numeri
    ma non le proporzioni, la barra dice le proporzioni ma non i numeri.
    Il nome del topic entra nel segmento solo se ci sta davvero: scritte
    ruotate o troncate in una barra sono il modo più rapido di far
    sembrare improvvisata una pagina.
    """
    total = sum(count for _, count in entries)
    if total <= 0:
        return ""

    # Gradazioni della stessa famiglia invece di colori diversi: la barra
    # resta leggibile e la pagina non diventa un grafico a torta di
    # PowerPoint. La coda di topic piccoli finisce tutta sull'ultima
    # gradazione, e lì a separarli è il filetto bianco: due tinte quasi
    # uguali accostate si leggono peggio di due tinte identiche divise.
    shades = [NAVY, AZZURRO_DEEP, AZZURRO, "#5bb8e8", AZZURRO_PALE]
    seam = 2

    parts, x = [], 0.0
    for i, (topic, count) in enumerate(entries):
        w = width * count / total
        color = shades[min(i, len(shades) - 1)]
        drawn = max(w - (seam if i < len(entries) - 1 else 0), 1)
        parts.append(
            f'<rect x="{x:.1f}" y="0" width="{drawn:.1f}" height="{height}" fill="{color}"/>'
        )
        if w > len(topic) * 9 + 20:
            text_color = "#fff" if i < 2 else NAVY
            parts.append(
                f'<text x="{x + 10:.1f}" y="{height / 2 + 5:.0f}" fill="{text_color}" '
                f'font-size="15" font-weight="800" letter-spacing="1.1">'
                f"{html.escape(topic.upper())}</text>"
            )
        x += w

    return (
        f'<svg class="share" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Peso dei topic sulla giornata">{"".join(parts)}</svg>'
    )


# --- Pittogrammi dei topic ----------------------------------------------
#
# Un set disegnato a mano, non una libreria: sono nove segni, tutti sulla
# stessa griglia 24×24, tutti a tratto da 2 e senza riempimenti. La
# coerenza qui conta più del singolo disegno — un set omogeneo di icone
# mediocri sta in pagina, un set di icone belle ma di provenienze diverse
# no. Per lo stesso motivo NON si usano le emoji: hanno colore, volume e
# stile propri, e sono la prima cosa che fa sembrare dilettantesca una
# testata.

_GLYPHS: dict[str, str] = {
    # scambio: mercato, trattative, trasferimenti
    "scambio": '<path d="M3 8h14M13 4l4 4-4 4"/><path d="M21 16H7M11 12l-4 4 4 4"/>',
    # pallone: partita, risultati, campionato
    "pallone": '<circle cx="12" cy="12" r="9"/><path d="M12 7l4.5 3.3-1.7 5.3h-5.6L7.5 10.3z"/>',
    # lavagna: tattica, formazione, moduli
    "lavagna": '<rect x="3" y="4" width="18" height="16"/><path d="M7 9l3 3m0-3l-3 3"/><circle cx="16" cy="15" r="2"/>',
    # riproduzione: video, canale, dirette
    "video": '<rect x="2" y="5" width="20" height="14"/><path d="M10 9.5l5 2.5-5 2.5z"/>',
    # biglietto: stadio, trasferte, prevendite
    "biglietto": '<path d="M3 6h18v4a2 2 0 000 4v4H3v-4a2 2 0 000-4z"/><path d="M12 6v2m0 3v2m0 3v2" stroke-dasharray="2 2"/>',
    # taccuino: fantacalcio, classifiche, liste
    "taccuino": '<rect x="4" y="3" width="16" height="18"/><path d="M8 8h8M8 12h8M8 16h5"/>',
    # gazzetta: news, stampa, rassegna
    "gazzetta": '<path d="M3 5h14v14H3z"/><path d="M17 9h4v8a2 2 0 01-4 0z"/><path d="M6 8h8M6 11h8M6 14h5"/>',
    # nuvoletta: off topic, chiacchiere, varie
    "nuvoletta": '<path d="M3 4h18v12H9l-5 4v-4H3z"/><path d="M8 10h8"/>',
    # segnaposto neutro per tutto il resto
    "punti": '<circle cx="6" cy="12" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="18" cy="12" r="1.6"/>',
}

# Le parole si confrontano in minuscolo sul titolo del topic. L'ordine
# conta: la prima che compare vince, quindi le più specifiche stanno
# sopra. È volutamente un elenco di parole e non una chiamata al modello —
# far scegliere un'icona a un LLM significa che lo stesso topic cambia
# segno da un giorno all'altro, che è esattamente ciò che rende una
# testata poco seria.
_GLYPH_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("mercato", "trattativ", "acquist", "cession", "trasferiment"), "scambio"),
    (("partita", "match", "risultat", "campionat", "gara", "coppa"), "pallone"),
    (("tattic", "formazion", "modul", "analisi", "schema"), "lavagna"),
    (("youtube", "video", "canale", "diretta", "live", "podcast"), "video"),
    (("bigliett", "stadio", "trasfert", "prevendit", "abbonament"), "biglietto"),
    (("fanta", "classific", "lega", "asta", "pronostic"), "taccuino"),
    (("news", "notizi", "stampa", "rassegna", "giornal"), "gazzetta"),
    (("off topic", "offtopic", "varie", "libero", "bar", "chiacchier"), "nuvoletta"),
]


def glyph_name_for_topic(topic: str) -> str:
    lowered = topic.lower()
    for keywords, name in _GLYPH_KEYWORDS:
        if any(k in lowered for k in keywords):
            return name
    return "punti"


def topic_glyph_svg(topic: str, *, size: int = 20, color: str = "currentColor") -> str:
    body = _GLYPHS[glyph_name_for_topic(topic)]
    return (
        f'<svg class="glyph" width="{size}" height="{size}" viewBox="0 0 24 24" '
        f'fill="none" stroke="{color}" stroke-width="2" stroke-linecap="square" '
        f'stroke-linejoin="miter" aria-hidden="true">{body}</svg>'
    )
