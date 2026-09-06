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
        # L'attacco: sta in prima pagina e deve reggere da solo. Dà la
        # notizia per intero — chi, che cosa, quando, a quali condizioni —
        # senza rimandare niente ai capoversi dopo.
        "Il centrocampista arriverà in prestito con diritto di riscatto "
        "fissato a dodici milioni: la trattativa si è chiusa nella tarda "
        "serata di lunedì, le visite mediche sono in programma mercoledì "
        "mattina e la firma è attesa entro giovedì.",
        # Da qui il pezzo riprende dentro, in ordine di importanza.
        "A far muovere le cose è stata la disponibilità del club di "
        "partenza ad abbassare la richiesta iniziale, ferma a quindici "
        "milioni fino a domenica. Restano da limare le commissioni, "
        "l'ultimo dettaglio ancora aperto: le parti si sono date "
        "appuntamento a mercoledì, subito dopo le visite.",
        "L'operazione apre però un problema di lista. Con l'arrivo del "
        "centrocampista lo slot va liberato, e il nome dell'esubero "
        "destinato a uscire non è ancora stato fatto: è la parte della "
        "giornata su cui il gruppo si è diviso di più, con due candidati "
        "e nessuna indicazione dal club.",
        "L'annuncio ufficiale è atteso nel pomeriggio di giovedì e "
        "chiuderebbe la settimana più movimentata della sessione estiva.",
    ],
    quote=Quote(
        text="Se lo prendiamo davvero, giovedì mi metto la maglia anche per andare a lavoro",
        author="Ciro",
        topic="Mantraskarso",
        time="23:41",
    ),
)

SAMPLE_ARTICLES = [
    Article(
        topic="Mantraskarso",
        headline="Il modificatore di difesa resta, l'asta slitta a sabato",
        deck="Tre leghe su quattro hanno già confermato la data, manca l'accordo sui crediti",
        body=(
            "Il modificatore di difesa resta anche quest'anno e l'asta si "
            "farà sabato pomeriggio: la doppia decisione è arrivata lunedì "
            "sera, dopo una discussione cominciata subito dopo cena e "
            "chiusa poco prima di mezzanotte.\n\n"
            "Sul modificatore la spaccatura era netta. Chi voleva toglierlo "
            "sosteneva che premia chi compra tre difensori della stessa "
            "squadra e nient'altro; chi voleva tenerlo ha fatto notare che "
            "senza, i difensori si svalutano al punto da rendere inutile "
            "metà del listino. Ha prevalso la seconda posizione, senza voto "
            "formale.\n\n"
            "Sulla data l'accordo è arrivato più in fretta: tre leghe su "
            "quattro avevano già bloccato sabato pomeriggio, e la quarta si "
            "è adeguata. Resta aperto il capitolo crediti, su cui nessuno "
            "ha ancora messo un numero."
        ),
        count=132,
        section="FantaCalcio",
        quote=Quote(
            text="Togliere il modificatore adesso significa buttare metà listino",
            author="Gennaro",
            time="22:38",
        ),
    ),
    Article(
        topic="Le Altre Squadre",
        headline="La rincorsa della seconda si ferma a Bergamo",
        deck="Il pareggio riapre il discorso sul terzo posto a due giornate dalla sosta",
        body=(
            "Il pareggio di Bergamo ferma la rincorsa della seconda in "
            "classifica e riapre il discorso sul terzo posto, a due "
            "giornate dalla sosta.\n\n"
            "Il risultato ha tenuto banco per tutta la serata, ma non per "
            "la partita in sé: a far discutere è stato il calendario che "
            "resta, con due trasferte consecutive e una sola gara in casa "
            "prima della pausa.\n\n"
            "Sulle possibilità di rimonta le posizioni sono rimaste "
            "distanti fino a tardi, e nessuno ha cambiato idea."
        ),
        count=113,
        section="Calcio",
    ),
    Article(
        topic="Spam Off Topic",
        headline="La classifica dei panini trova finalmente un vincitore",
        deck="Tre settimane di ballottaggio si chiudono con una preferenza netta",
        body=(
            "Dopo tre settimane di votazioni sparse la classifica dei "
            "panini si è chiusa martedì sera con una preferenza netta e "
            "nessun ricorso.\n\n"
            "Il ballottaggio era fermo da giorni su due nomi, con i voti "
            "che arrivavano alla spicciolata e si annullavano a vicenda. "
            "La svolta è arrivata quando si è deciso di contare solo i "
            "voti espressi entro la mezzanotte di lunedì.\n\n"
            "Il verbale resta agli atti del gruppo, e la prossima "
            "classifica è già stata annunciata."
        ),
        count=113,
        section="Altro",
    ),
    Article(
        topic="Match Day",
        headline="Il gol al novantesimo ribalta una partita già archiviata",
        deck="Sul secondo giallo le opinioni restano distanti anche a fine serata",
        body=(
            "Il gol al novantesimo ha ribaltato una partita che quasi tutti "
            "avevano già archiviato come pareggio, e la discussione è "
            "andata avanti oltre la mezzanotte.\n\n"
            "Fino all'ultimo assalto il risultato era stato dato per buono "
            "senza troppe discussioni. Il capovolgimento ha spostato tutto "
            "sull'episodio precedente: il secondo giallo al difensore, "
            "arrivato a venti minuti dalla fine, che ha lasciato la squadra "
            "in dieci.\n\n"
            "Su quell'intervento le posizioni sono rimaste distanti anche a "
            "fine serata, con il replay guardato e riguardato senza che "
            "nessuno cambiasse idea."
        ),
        count=87,
        section="Napoli",
        quote=Quote(
            text="Il secondo giallo non c'era manco a pagarlo, è entrato sul pallone",
            author="Ciro",
            time="23:14",
        ),
    ),
    Article(
        topic="FantaSkarso",
        headline="I listini aggiornati sono online, i crediti restano cento",
        deck="Nessuna modifica ai ruoli rispetto alla scorsa stagione",
        body=(
            "I listini aggiornati sono stati condivisi in serata: i crediti "
            "restano cento e i ruoli non cambiano rispetto alla scorsa "
            "stagione.\n\n"
            "Sul tetto di spesa nessuno ha chiesto modifiche, nemmeno chi "
            "l'anno scorso aveva proposto di alzarlo. Sui ruoli la scelta "
            "di non toccare niente è passata senza commenti."
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
# Le battute della vignetta, una coppia per tono. Tutte sullo STESSO
# fatto — quello dell'apertura — perché è il punto: a cambiare da un
# giorno all'altro non è l'argomento della vignetta, che è sempre la
# notizia principale, ma il tono con cui il gruppo l'ha presa. Sono
# scritte come le scrive il gruppo (minuscole, senza punteggiatura
# finale, con gli errori) perché in pagina ci finiscono copiate alla
# lettera: una battuta ripulita si riconosce subito.
SAMPLE_BATTUTE = {
    "battibecco": [
        ("Dodici milioni di riscatto per uno che l'anno scorso ha fatto due gol", "Ciro", "23:14"),
        ("Due gol da mediano, e ne ha fatti sei di assist, guardali prima di parlare", "Gennaro", "23:16"),
    ],
    "esultanza": [
        ("Ragazzi è fatta, visite mercoledì e giovedì firma, l'ho letto adesso", "Peppe", "22:51"),
        ("Era da giugno che lo chiedevo, finalmente uno che sa fare due passaggi", "Ugo", "22:53"),
    ],
    "sconforto": [
        ("Un prestito con diritto, cioè fra un anno stiamo di nuovo qua a parlarne", "Salvo", "23:02"),
    ],
    "complotto": [
        ("Le visite mercoledì mattina, quindi la firma era già fatta da domenica", "Rino", "23:20"),
        ("Certo che era fatta, aspettavano solo di piazzare quello che deve uscire", "Tonino", "23:22"),
    ],
    "spiegone": [
        ("Allora, il prestito con diritto funziona che se non lo riscatti torna indietro", "Mimmo", "21:40"),
        ("Mimmo lo sappiamo tutti come funziona il prestito", "Ciro", "21:41"),
    ],
    "attesa": [
        ("Le visite sono fissate per mercoledì mattina, prima di quello non si sa niente", "Gennaro", "20:12"),
        ("Io il telefono me lo tengo in mano fino a giovedì", "Peppe", "20:15"),
    ],
}

# La didascalia dice dove è stato detto e quando: il CHE COSA lo dice già
# il titolo sopra, ed è la stessa notizia.
SAMPLE_VIGNETTA_TOPIC = {
    "battibecco": "CalcioMercato — sul riscatto, dopo le undici di sera",
    "esultanza": "CalcioMercato — alla notizia delle visite mediche",
    "sconforto": "CalcioMercato — sulla formula del prestito",
    "complotto": "CalcioMercato — sulle date, in tarda serata",
    "spiegone": "CalcioMercato — sul diritto di riscatto",
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
