"""Anteprima del gazzettino con dati finti, senza rete.

Serve a lavorare sulla grafica senza chiamare Telegram né OpenAI: il
layout è la parte che si itera di più, ed è l'unica che non ha bisogno di
dati veri per essere giudicata. Una giornata di esempio realistica (topic
di un gruppo di tifosi, testi della lunghezza che scrive davvero il
modello) sta in SAMPLE_* qui sotto.

    python preview.py                 # tutte le pagine in preview_out/
    python preview.py --out /tmp/x    # cartella diversa
    python preview.py --no-hero       # com'è la pagina senza foto
    python preview.py --plain         # senza gli elementi grafici nuovi

L'immagine di apertura di esempio, se manca, viene generata al volo: non
teniamo una foto nel repo solo per l'anteprima.
"""

import argparse
import asyncio
from datetime import date
from pathlib import Path

from report.graphics import PHOTO_TREATMENTS
from report.newspaper import (
    Article,
    GraphicsOptions,
    Hero,
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


def _sample_hero(dest_dir: Path) -> Hero | None:
    """Foto di apertura finta.

    Non è un disegno decorativo: serve a giudicare il trattamento
    cromatico, quindi deve avere la stessa gamma tonale di una foto vera —
    ombre profonde, mezzitoni, una luce che va a fondo scala — più un po'
    di grana. Un'immagine a tinte piatte farebbe sembrare buono
    qualsiasi filtro.
    """
    import random

    try:
        from PIL import Image, ImageDraw, ImageFilter
    except ImportError:
        # Pillow serve solo qui: senza, l'anteprima gira lo stesso e mostra
        # la pagina nella variante senza foto, che è comunque un caso reale.
        print("Pillow non installato (pip install pillow): anteprima senza foto.")
        return None

    rnd = random.Random(7)
    w, h = 1600, 900
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)

    # Cielo: dal quasi nero in alto al grigio chiaro sull'orizzonte.
    for y in range(h):
        t = y / h
        v = int(26 + 150 * t ** 1.4)
        draw.line([(0, y), (w, y)], fill=(v, int(v * 1.02), int(v * 1.06)))

    # Sorgente di luce: porta le alte luci a fondo scala, dove i duotoni
    # fatti male bruciano.
    for r in range(300, 0, -6):
        v = int(255 - (r / 300) * 120)
        draw.ellipse([1120 - r, 240 - r, 1120 + r, 240 + r], fill=(v, v, min(255, v + 4)))

    # Soggetto in controluce e piano d'appoggio: i mezzitoni.
    draw.polygon([(420, 900), (560, 380), (700, 900)], fill=(58, 60, 66))
    draw.ellipse([520, 300, 640, 420], fill=(96, 94, 98))
    draw.rectangle([0, 720, w, h], fill=(38, 42, 50))

    # Folla: blocchi irregolari che fanno da tessitura nelle ombre.
    for _ in range(900):
        x, y = rnd.randrange(w), rnd.randrange(720, h)
        s = rnd.randrange(6, 26)
        v = rnd.randrange(30, 96)
        draw.rectangle([x, y, x + s, y + s], fill=(v, v, v + 6))

    img = img.filter(ImageFilter.GaussianBlur(1.2))

    # Grana: una foto da telefono ce l'ha sempre, e cambia il modo in cui
    # si legge il duotone nelle ombre.
    pixels = img.load()
    for _ in range(90_000):
        x, y = rnd.randrange(w), rnd.randrange(h)
        r, g, b = pixels[x, y]
        n = rnd.randrange(-16, 17)
        pixels[x, y] = (
            max(0, min(255, r + n)),
            max(0, min(255, g + n)),
            max(0, min(255, b + n)),
        )

    path = dest_dir / "hero-sample.jpg"
    img.save(path, quality=88)
    return Hero(path=str(path), caption="Foto dal topic Mercato · 21:14")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="preview_out", help="cartella di output")
    parser.add_argument("--no-hero", action="store_true", help="pagina senza foto")
    parser.add_argument(
        "--plain",
        action="store_true",
        help="disattiva gli elementi grafici opzionali (capolettera, grafico, pittogrammi)",
    )
    parser.add_argument(
        "--scale", type=int, default=1, help="fattore di scala del rendering (default 1)"
    )
    parser.add_argument(
        "--glyphs", action="store_true", help="accende i pittogrammi dei topic"
    )
    parser.add_argument(
        "--share", action="store_true", help="accende la barra delle proporzioni"
    )
    parser.add_argument(
        "--foto",
        choices=PHOTO_TREATMENTS,
        default=None,
        help="trattamento della foto di apertura",
    )
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    hero = None if args.no_hero else _sample_hero(out)
    logo = Path("assets/logo-azzurro.png")

    gfx = GraphicsOptions.none() if args.plain else GraphicsOptions()
    gfx.topic_glyphs = args.glyphs
    gfx.share_bar = args.share
    if args.foto:
        gfx.photo_treatment = args.foto

    pages = build_pages_html(
        "Azzurro Fluido",
        SAMPLE_DATE,
        SAMPLE_LEAD,
        SAMPLE_ARTICLES,
        logo_path=logo if logo.exists() else None,
        hero=hero,
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
