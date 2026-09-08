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

# Nomi e squadre dell'esempio sono inventati di sana pianta. Il gazzettino
# vero userà quelli che il gruppo scrive davvero; qui servono nomi finti
# perché nessuno scambi un'anteprima per una notizia.
# L'apertura non ha un corpo suo: in prima pagina va l'INIZIO
# dell'articolo che apre l'edizione, e il resto continua alla sua pagina.
# Qui l'apertura è la presentazione del pezzo su Match Day (vedi
# SAMPLE_LEAD_TOPIC più sotto): titolo e sommario sono scritti per la
# prima pagina, il testo lo mette build_pages_html prendendolo dal pezzo.
#
# Un'anteprima con un corpo scritto a mano mostrerebbe una pagina che il
# giornale non stampa più, ed è esattamente il modo di non accorgersi che
# la stessa notizia usciva due volte.
SAMPLE_LEAD = Lead(
    kicker="Napoli",
    headline="Ruggiero al 90' ribalta una partita archiviata",
    deck=(
        "Il pareggio era dato per buono da venti minuti: sul secondo "
        "giallo a Marino le opinioni restano distanti anche a fine serata"
    ),
    quote=Quote(
        text="Ho urlato così forte che si è svegliata mezza palazzina",
        author="Peppe",
        topic="Match Day",
        time="22:52",
    ),
)

# Il tema da cui l'apertura nasce: il suo articolo comincia in prima e
# continua dentro.
SAMPLE_LEAD_TOPIC = "Match Day"

SAMPLE_ARTICLES = [
    Article(
        topic="Mantraskarso",
        headline="Il modificatore di difesa resta, l'asta slitta a sabato",
        deck="Tre leghe su quattro hanno già confermato la data, manca l'accordo sui crediti",
        body=(
            "Nel Mantraskarso il modificatore di difesa resta anche "
            "quest'anno e l'asta si farà sabato 12 alle 15: la doppia "
            "decisione è arrivata lunedì sera, al termine di una "
            "discussione cominciata subito dopo cena e chiusa poco prima "
            "di mezzanotte.\n\n"
            "Sul modificatore la spaccatura era netta. Gennaro e Salvo "
            "chiedevano di toglierlo, sostenendo che premia solo chi "
            "compra tre difensori della stessa squadra; Peppe e Rino hanno "
            "risposto che senza il modificatore i difensori si svalutano "
            "al punto da rendere inutile metà del listino. Ha prevalso la "
            "seconda posizione, senza voto formale.\n\n"
            "Sulla data l'accordo è arrivato più in fretta: Serie Flu', "
            "Serie TvB e Serie Eh avevano già bloccato sabato pomeriggio, "
            "e la Serie X si è adeguata. Resta aperto il tetto crediti, "
            "che nessuno ha ancora proposto di cambiare."
        ),
        count=132,
        section="FantaCalcio",
        quote=Quote(
            text="Togliere il modificatore adesso significa buttare metà listino",
            author="Peppe",
            time="22:38",
        ),
    ),
    Article(
        topic="Le Altre Squadre",
        headline="La rincorsa del Vallesana si ferma a Bergamo, 1-1",
        deck="Il pareggio lascia i punti di distacco a quattro a due giornate dalla sosta",
        body=(
            "Il Vallesana ha pareggiato 1-1 a Bergamo domenica pomeriggio "
            "e resta a quattro punti dalla vetta, con due giornate da "
            "giocare prima della sosta.\n\n"
            "Il gol del pareggio è arrivato al 71', su rigore, cinque "
            "minuti dopo il vantaggio ospite. A far discutere in serata "
            "non è stata però la partita: è stato il calendario che resta, "
            "due trasferte consecutive e una sola gara in casa.\n\n"
            "Sulle possibilità di rimonta le posizioni sono rimaste "
            "distanti fino a tardi, e nessuno ha cambiato idea."
        ),
        count=113,
        section="Calcio",
    ),
    Article(
        topic="Spam Off Topic",
        headline="La classifica dei panini incorona la Rosticceria Aurora",
        deck="Tre settimane di ballottaggio si chiudono 14 voti a 9, nessun ricorso",
        body=(
            "La classifica dei panini si è chiusa martedì sera con la "
            "vittoria della Rosticceria Aurora, 14 voti contro i 9 del bar "
            "di via Chiaia, dopo tre settimane di votazioni.\n\n"
            "Il ballottaggio era fermo da giorni sui due nomi, con i voti "
            "che arrivavano alla spicciolata e si annullavano a vicenda. La "
            "svolta è arrivata lunedì, quando Ugo ha proposto di contare "
            "solo i voti espressi entro la mezzanotte.\n\n"
            "Il verbale resta agli atti del gruppo. La prossima classifica, "
            "annunciata da Tonino, sarà sulle pizzerie d'asporto."
        ),
        count=113,
        section="Altro",
    ),
    Article(
        topic="Match Day",
        headline="Il gol di Ruggiero al 90' ribalta una partita archiviata",
        deck="Sul secondo giallo a Marino le opinioni restano distanti anche a fine serata",
        body=(
            "Il gol di Ruggiero al 90' ha ribaltato una partita che quasi "
            "tutti avevano già archiviato come pareggio, e la discussione "
            "è andata avanti oltre la mezzanotte.\n\n"
            "Fino all'ultimo assalto l'1-1 era stato dato per buono senza "
            "troppe discussioni. Il capovolgimento ha riportato tutti "
            "sull'episodio precedente: il secondo giallo a Marino, al 70', "
            "che aveva lasciato la squadra in dieci per venti minuti.\n\n"
            "Su quell'intervento le posizioni sono rimaste distanti anche a "
            "fine serata, con il replay guardato e riguardato senza che "
            "nessuno cambiasse idea."
        ),
        count=87,
        section="Napoli",
        quote=Quote(
            text="Il secondo giallo a Marino non c'era manco a pagarlo, è entrato sul pallone",
            author="Ciro",
            time="23:14",
        ),
    ),
    Article(
        topic="FantaSkarso",
        headline="Listini aggiornati online, i crediti restano cento",
        deck="Nessuna modifica ai ruoli rispetto alla scorsa stagione",
        body=(
            "I listini aggiornati del FantaSkarso sono stati condivisi "
            "martedì sera da Mimmo: i crediti restano cento e i ruoli non "
            "cambiano rispetto alla scorsa stagione.\n\n"
            "Sul tetto di spesa nessuno ha chiesto modifiche, nemmeno Rino, "
            "che l'anno scorso aveva proposto di portarlo a centoventi. Sui "
            "ruoli la scelta di non toccare niente è passata senza commenti."
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

# Le battute della vignetta, una coppia per tono. Tutte sullo STESSO
# fatto — quello dell'apertura — perché è il punto: a cambiare da un
# giorno all'altro non è l'argomento della vignetta, che è sempre la
# notizia principale, ma il tono con cui il gruppo l'ha presa.
#
# Sono scritte come le scrive il gruppo (minuscole, senza punteggiatura
# finale, con gli errori) perché in pagina ci finiscono copiate alla
# lettera: una battuta ripulita si riconosce subito e fa sembrare finto
# anche il resto.
SAMPLE_BATTUTE = {
    "battibecco": [
        ("Il secondo giallo a Marino non c'era manco a pagarlo", "Ciro", "23:14"),
        ("Era entrato con i tacchetti alti, dai, guardatela un'altra volta", "Gennaro", "23:16"),
    ],
    "esultanza": [
        ("Ruggiero al novantesimo, mi sono messo a urlare da solo in cucina", "Peppe", "22:51"),
        ("Tre punti che ieri sera nessuno di noi avrebbe firmato", "Ugo", "22:53"),
    ],
    "sconforto": [
        ("Venti minuti in dieci per un giallo che non c'era, ogni domenica uguale", "Salvo", "23:02"),
    ],
    "complotto": [
        ("Il secondo giallo a Marino al settanta, poi guarda caso il recupero era di sei minuti", "Rino", "23:20"),
        ("Certo, l'espulsione la danno sempre a noi e mai a loro", "Tonino", "23:22"),
    ],
    "spiegone": [
        ("Allora, il secondo giallo si dà se il fallo è tattico, e quello sul pallone non lo era", "Mimmo", "21:40"),
        ("Mimmo lo sappiamo tutti quando si dà il secondo giallo", "Ciro", "21:41"),
    ],
    "attesa": [
        ("Se il replay lo fanno vedere da dietro si capisce, prima di quello non si sa", "Gennaro", "20:12"),
        ("Io aspetto la moviola di stasera e poi ne riparliamo", "Peppe", "20:15"),
    ],
}

# La didascalia dice dove è stato detto e quando: il CHE COSA lo dice già
# il titolo sopra, ed è la stessa notizia.
SAMPLE_VIGNETTA_TOPIC = {
    "battibecco": "Match Day — sul secondo giallo a Marino, dopo le undici di sera",
    "esultanza": "Match Day — al gol di Ruggiero al novantesimo",
    "sconforto": "Match Day — sui venti minuti in dieci",
    "complotto": "Match Day — sul recupero, in tarda serata",
    "spiegone": "Match Day — su quando si dà il secondo giallo",
    "attesa": "Match Day — in attesa della moviola",
}

SAMPLE_QUOTE = Quote(
    text="Il secondo giallo a Marino non c'era manco a pagarlo, è entrato sul pallone",
    author="Ciro",
    topic="Match Day",
    time="23:14",
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

    logo = Path("assets/logo-carta.png")
    firma = Path("assets/logo-dprimo17-gerenza.png")
    pages = build_pages_html(
        "Azzurro Fluido",
        SAMPLE_DATE,
        SAMPLE_LEAD,
        SAMPLE_ARTICLES,
        logo_path=logo if logo.exists() else None,
        firma_path=firma if firma.exists() else None,
        index_entries=SAMPLE_INDEX,
        stats=SAMPLE_STATS,
        quote=SAMPLE_QUOTE,
        vignetta=vignetta,
        hourly=None if args.plain else SAMPLE_HOURS,
        graphics=gfx,
        lead_topic=SAMPLE_LEAD_TOPIC,
    )

    for number, page_html in enumerate(pages, start=1):
        target = out / f"pagina_{number}.png"
        await render_html_to_png(page_html, str(target), scale=args.scale)
        print(f"scritto {target}")


if __name__ == "__main__":
    asyncio.run(main())
