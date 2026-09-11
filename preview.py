"""Anteprima del gazzettino con dati finti, senza rete.

Serve a lavorare sulla grafica senza chiamare Telegram né OpenAI: il
layout è la parte che si itera di più, ed è l'unica che non ha bisogno di
dati veri per essere giudicata. Una giornata di esempio realistica (topic
di un gruppo di tifosi, testi della lunghezza che scrive davvero il
modello) sta in SAMPLE_* qui sotto.

    python preview.py                 # tutte le pagine in preview_out/
    python preview.py --out /tmp/x    # cartella diversa
    python preview.py --plain         # com'era prima degli elementi grafici
    python preview.py --no-glyphs     # spegne un singolo elemento
"""

import argparse
import asyncio
from datetime import date
from pathlib import Path

from report.newspaper import (
    Article,
    GraphicsOptions,
    Lead,
    Quote,
    Stats,
    build_pages_html,
    render_html_to_png,
)

SAMPLE_DATE = date(2026, 8, 5)

SAMPLE_LEAD = Lead(
    kicker="Mercato",
    headline="Il centrocampista arriva in prestito, la firma attesa entro giovedì",
    deck=(
        "Visite mediche fissate per mercoledì mattina, il club valuta anche "
        "l'uscita di un esubero per liberare lo slot in lista"
    ),
    paragraphs=[
        "La trattativa si è chiusa nella tarda serata di lunedì sulla formula "
        "del prestito con diritto di riscatto fissato a dodici milioni. Le "
        "commissioni restano l'ultimo dettaglio da limare, ma le parti si sono "
        "date appuntamento a mercoledì per la firma.",
        "In gruppo la reazione è stata compatta: chi chiedeva un innesto in "
        "mezzo da giugno considera l'operazione chiusa bene, mentre resta il "
        "dubbio su chi lascerà il posto in lista.",
        "Nel pomeriggio è atteso l'annuncio ufficiale, che chiuderebbe la "
        "settimana più movimentata della sessione estiva.",
    ],
)

SAMPLE_ARTICLES = [
    Article(
        topic="Partita",
        headline="L'amichevole finisce in parità, ma la difesa convince",
        deck=(
            "Il rigore sbagliato in coda riapre la discussione sui tiratori designati"
        ),
        body=(
            "Due tempi molto diversi: nel primo la squadra ha tenuto il pallino "
            "senza mai affondare, nel secondo è arrivato il gol su calcio "
            "piazzato. In coda al match il rigore sbagliato ha riaperto la "
            "discussione sui tiratori designati.",
        )[0],
        count=87,
    ),
    Article(
        topic="Tattica",
        headline="Il tridente largo divide: due modi di leggere la stessa mossa",
        deck=(
            "L'esterno destro resta isolato per tutto il primo tempo, e il gruppo si divide"
        ),
        body=(
            "Chi ha visto la partita da fuori area sostiene che l'ampiezza abbia "
            "liberato lo spazio centrale; chi guardava i movimenti senza palla "
            "nota invece che l'esterno destro è rimasto isolato per tutto il "
            "primo tempo. La discussione si è chiusa senza una posizione unica."
        ),
        count=54,
    ),
    Article(
        topic="Canale YouTube",
        headline="Il video sulle statistiche difensive supera le ventimila visualizzazioni",
        deck=(
            "Il montaggio sui dati difensivi raccoglie più commenti di ogni altro video del mese"
        ),
        body=(
            "Pubblicato domenica sera, il montaggio sui dati difensivi della "
            "scorsa stagione ha raccolto più commenti di qualsiasi altro video "
            "del mese. Nel gruppo si è già proposto un seguito sui portieri."
        ),
        count=31,
    ),
    Article(
        topic="Biglietti",
        headline="Prevendita aperta da giovedì, il settore ospiti resta il nodo",
        deck=(
            "Fasi di vendita da giovedì per gli abbonati, sabato per tutti gli altri"
        ),
        body=(
            "Le fasi di vendita partono giovedì alle dieci per gli abbonati e "
            "sabato per tutti gli altri. Sul settore ospiti non c'è ancora "
            "comunicazione ufficiale."
        ),
        count=22,
    ),
    Article(
        topic="Fantacalcio",
        headline="Le aste si concentrano nel weekend, i listini sono già online",
        deck=(
            "Tre leghe fissano l'asta per sabato, il modificatore di difesa resta attivo"
        ),
        body=(
            "Tre leghe hanno fissato l'asta per sabato pomeriggio. I crediti "
            "restano cento, con la solita discussione sul modificatore di "
            "difesa che quest'anno resta attivo."
        ),
        count=18,
    ),
    Article(
        topic="Off topic",
        headline="La classifica dei panini del sabato trova finalmente un vincitore",
        deck=(
            "Tre settimane di ballottaggio si chiudono con una preferenza netta"
        ),
        body=(
            "Dopo tre settimane di voti sparsi, il ballottaggio si è chiuso con "
            "una preferenza netta. Il verbale resta agli atti del gruppo."
        ),
        count=12,
    ),
]

SAMPLE_INDEX = [
    ("Mercato", 112),
    ("Partita", 87),
    ("Tattica", 54),
    ("Canale YouTube", 31),
    ("Biglietti", 22),
    ("Fantacalcio", 18),
    ("Off topic", 12),
]

SAMPLE_STATS = Stats(
    messages=336, participants=41, active_topics=7, peak_hour="22:00"
)

SAMPLE_QUOTE = Quote(
    text="Se lo prendiamo davvero, giovedì mi metto la maglia anche per andare a lavoro",
    author="Ciro",
    topic="Mercato",
    time="23:41",
)

# Distribuzione oraria di esempio: 24 valori, uno per ora. Fa la stessa
# forma che ha una giornata vera — poco di notte, un picco all'ora di
# pranzo e uno molto più alto dopo cena.
SAMPLE_HOURS = [
    2, 0, 0, 0, 0, 0, 1, 4, 9, 14, 11, 13,
    21, 18, 9, 7, 12, 16, 24, 29, 38, 47, 41, 20,
]


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="preview_out", help="cartella di output")
    parser.add_argument(
        "--plain",
        action="store_true",
        help="disattiva tutti gli elementi grafici opzionali",
    )
    parser.add_argument(
        "--scale", type=int, default=1, help="fattore di scala del rendering (default 1)"
    )
    parser.add_argument(
        "--no-glyphs", action="store_true", help="spegne i pittogrammi dei topic"
    )
    parser.add_argument(
        "--no-share", action="store_true", help="spegne la barra delle proporzioni"
    )
    parser.add_argument(
        "--no-brief", action="store_true", help="spegne il box In breve"
    )
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    gfx = GraphicsOptions.none() if args.plain else GraphicsOptions()
    if args.no_glyphs:
        gfx.topic_glyphs = False
    if args.no_share:
        gfx.share_bar = False
    if args.no_brief:
        gfx.brief_box = False

    logo = Path("assets/logo-azzurro.png")
    pages = build_pages_html(
        "Azzurro Fluido",
        SAMPLE_DATE,
        SAMPLE_LEAD,
        SAMPLE_ARTICLES,
        logo_path=logo if logo.exists() else None,
        index_entries=SAMPLE_INDEX,
        stats=SAMPLE_STATS,
        quote=SAMPLE_QUOTE,
        hourly=None if args.plain else SAMPLE_HOURS,
        graphics=gfx,
    )

    for number, page_html in enumerate(pages, start=1):
        target = out / f"pagina_{number}.png"
        await render_html_to_png(page_html, str(target), scale=args.scale)
        print(f"scritto {target}")


if __name__ == "__main__":
    asyncio.run(main())
