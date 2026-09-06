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
    Balloon,
    GraphicsOptions,
    Lead,
    Quote,
    Stats,
    Vignetta,
    build_pages_html,
    render_html_to_png,
)
from report.vignetta import Biblioteca

SAMPLE_DATE = date(2026, 8, 5)

SAMPLE_LEAD = Lead(
    kicker="Calcio",
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
        topic="Mantraskarso",
        headline="Il modificatore di difesa resta, l'asta slitta a sabato",
        deck="Tre leghe su quattro hanno già confermato la data, manca l'accordo sui crediti",
        body=(
            "La discussione si è chiusa sul mantenere il modificatore anche "
            "quest'anno. Sull'asta la data di sabato pomeriggio mette "
            "d'accordo quasi tutti."
        ),
        count=132,
        section="FantaCalcio",
    ),
    Article(
        topic="Le Altre Squadre",
        headline="La rincorsa della seconda in classifica si ferma a Bergamo",
        deck="Il pareggio riapre il discorso sul terzo posto a due giornate dalla sosta",
        body=(
            "Il risultato di Bergamo ha tenuto banco per tutta la sera. Sul "
            "terzo posto le posizioni restano distanti."
        ),
        count=113,
        section="Calcio",
    ),
    Article(
        topic="Spam Off Topic",
        headline="La classifica dei panini trova finalmente un vincitore",
        deck="Tre settimane di ballottaggio si chiudono con una preferenza netta",
        body=(
            "Dopo tre settimane di voti sparsi il ballottaggio si è chiuso "
            "senza ricorsi. Il verbale resta agli atti del gruppo."
        ),
        count=113,
        section="Altro",
    ),
    Article(
        topic="Match Day",
        headline="Il gol al novantesimo ribalta una partita già archiviata",
        deck="Sul secondo giallo le opinioni restano distanti anche a fine serata",
        body=(
            "Il pareggio era stato dato per buono da quasi tutti fino "
            "all'ultimo assalto. Sull'episodio del secondo giallo si è "
            "discusso oltre la mezzanotte."
        ),
        count=87,
        section="Napoli",
    ),
    Article(
        topic="FantaSkarso",
        headline="I listini aggiornati sono online, i crediti restano cento",
        deck="Nessuna modifica ai ruoli rispetto alla scorsa stagione",
        body=(
            "Il file aggiornato è stato condiviso in serata. Sui crediti "
            "nessuno ha chiesto di cambiare il tetto."
        ),
        count=51,
        section="FantaCalcio",
    ),
    # Le otto leghe: stessa forma, stessa famiglia. Non concorrono agli
    # articoli pieni e finiscono nel blocco compatto della loro sezione.
    Article(topic="Serie Flu’", headline="Il recupero della quinta giornata va in scena mercoledì", body="", count=78, section="FantaCalcio", family="Le Serie"),
    Article(topic="Serie TvB", headline="Lo scambio in cima alla classifica passa senza veti", body="", count=64, section="FantaCalcio", family="Le Serie"),
    Article(topic="Serie Eh", headline="Il mercato di riparazione chiude domenica a mezzanotte", body="", count=52, section="FantaCalcio", family="Le Serie"),
    Article(topic="Seri eCcí", headline="Due squadre ancora senza portiere di riserva", body="", count=26, section="FantaCalcio", family="Le Serie"),
    Article(topic="Serie X", headline="Il regolamento sulle panchine lunghe resta invariato", body="", count=21, section="FantaCalcio", family="Le Serie"),
    Article(
        topic="Editoriali Bellini",
        headline="Il video sulle statistiche difensive supera le ventimila visualizzazioni",
        body="",
        count=31,
        section="Canale",
    ),
    Article(
        topic="Ko-Fi (SUPPORTO CANALE)",
        headline="Raccolta del mese sopra l'obiettivo con dieci giorni di anticipo",
        body="",
        count=17,
        section="Canale",
    ),
    Article(
        topic="Altri Sport",
        headline="La finale di basket di domenica sposta l'orario del live",
        body="",
        count=9,
        section="Sport",
    ),
    Article(
        topic="CalcioMercato",
        headline="Nessuna trattativa chiusa nella giornata di ieri",
        body="",
        count=6,
        section="Calcio",
    ),
]

# L'indice del gazzettino: le sezioni attive, dalla più attiva. È la
# mappa dell'edizione, e nomina le stesse cose che si trovano nelle
# testate di sezione più in basso.
SAMPLE_INDEX = [
    ("FantaCalcio", 424),
    ("Calcio", 119),
    ("Altro", 113),
    ("Napoli", 87),
    ("Canale", 48),
    ("Sport", 9),
]

# I topic, che in pagina compaiono nei tag dei pezzi e in "In breve".
# Servono anche a catalogo.py, che mostra pittogrammi e barrette: quelli
# distinguono i topic, non le sezioni.
SAMPLE_TOPICS = [
    ("Mantraskarso", 132),
    ("Le Altre Squadre", 113),
    ("Spam Off Topic", 113),
    ("Match Day", 87),
    ("Serie Flu\u2019", 78),
    ("Serie TvB", 64),
    ("Serie Eh", 52),
    ("FantaSkarso", 51),
    ("Editoriali Bellini", 31),
    ("Seri eCc\u00ed", 26),
    ("Serie X", 21),
    ("Ko-Fi (SUPPORTO CANALE)", 17),
    ("Altri Sport", 9),
    ("CalcioMercato", 6),
]

SAMPLE_STATS = Stats(
    messages=800, participants=41, active_topics=14, peak_hour="22:00"
)

# Le battute della vignetta, una coppia per tono. Sono scritte come le
# scrive il gruppo — minuscole, senza punteggiatura finale, con gli errori
# — perché in pagina ci finiscono copiate alla lettera: una battuta
# ripulita si riconosce subito e fa sembrare finto anche il resto.
SAMPLE_BATTUTE = {
    "battibecco": [
        ("Il secondo giallo non c'era manco a pagarlo, è entrato sul pallone", "Ciro", "23:14"),
        ("Sul pallone dopo che gli ha preso la caviglia, guardatelo un'altra volta", "Gennaro", "23:16"),
    ],
    "esultanza": [
        ("Ragazzi io al novantesimo mi ero già messo il pigiama, giuro", "Peppe", "22:51"),
        ("Ho svegliato tutto il palazzo e non me ne pento", "Ugo", "22:53"),
    ],
    "sconforto": [
        ("Trentotto partite per farci male sempre nello stesso punto", "Salvo", "23:02"),
    ],
    "complotto": [
        ("Vi ricordate chi arbitrava all'andata? Ecco, appunto", "Rino", "23:20"),
        ("E infatti stessa identica cosa, stesso identico minuto", "Tonino", "23:22"),
    ],
    "spiegone": [
        ("Allora ve lo rispiego con calma perché evidentemente non è chiaro", "Mimmo", "21:40"),
        ("Mimmo per favore no, non stasera", "Ciro", "21:41"),
    ],
    "attesa": [
        ("Le visite sono fissate per mercoledì mattina, prima di quello non si sa niente", "Gennaro", "20:12"),
        ("Io il telefono me lo tengo in mano fino a giovedì", "Peppe", "20:15"),
    ],
}

SAMPLE_VIGNETTA_TOPIC = {
    "battibecco": "Match Day — il secondo giallo, dopo la mezzanotte",
    "esultanza": "Match Day — il gol al novantesimo",
    "sconforto": "Match Day — a fine partita",
    "complotto": "Match Day — sull'arbitro, in serata",
    "spiegone": "Mantraskarso — il modificatore di difesa",
    "attesa": "CalcioMercato — in attesa delle visite mediche",
}

SAMPLE_QUOTE = Quote(
    text="Se lo prendiamo davvero, giovedì mi metto la maglia anche per andare a lavoro",
    author="Ciro",
    topic="Mantraskarso",
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
    parser.add_argument(
        "--vignetta",
        nargs="?",
        const="",
        default=None,
        metavar="TONO",
        help="mette in pagina la vignetta al posto della frase del giorno; "
             "senza argomento usa il primo tono che ha disegni",
    )
    parser.add_argument(
        "--biblioteca", default="assets/vignette", help="cartella dei disegni"
    )
    parser.add_argument(
        "--battuta-singola",
        action="store_true",
        help="una voce sola invece dello scambio a due",
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

    vignetta = None
    if args.vignetta is not None:
        biblioteca = Biblioteca(args.biblioteca)
        if not biblioteca:
            raise SystemExit(
                f"Nessun disegno in {args.biblioteca}/: la biblioteca vuole una "
                f"cartella per tono ({', '.join(biblioteca.toni) or 'battibecco, esultanza, …'})"
            )
        tono = args.vignetta or biblioteca.toni[0]
        if tono not in biblioteca.toni:
            raise SystemExit(
                f"Il tono «{tono}» non ha disegni. Disponibili: "
                f"{', '.join(biblioteca.toni)}"
            )
        battute = SAMPLE_BATTUTE[tono][: 1 if args.battuta_singola else 2]
        vignetta = Vignetta(
            image_path=biblioteca.scegli(tono, SAMPLE_DATE),
            balloons=[Balloon(text=t, author=a, time=o) for t, a, o in battute],
            topic=SAMPLE_VIGNETTA_TOPIC[tono],
            tone=tono,
        )
        print(f"vignetta: tono {tono}, disegno {vignetta.image_path}")

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
        vignetta=vignetta,
        hourly=None if args.plain else SAMPLE_HOURS,
        graphics=gfx,
    )

    for number, page_html in enumerate(pages, start=1):
        target = out / f"pagina_{number}.png"
        await render_html_to_png(page_html, str(target), scale=args.scale)
        print(f"scritto {target}")


if __name__ == "__main__":
    asyncio.run(main())
