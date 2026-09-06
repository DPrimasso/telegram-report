import re

from openai import OpenAI

from report import llm
from report.fetch import SimpleMessage

# Soglia approssimativa (in caratteri) oltre la quale si passa a un
# riassunto map-reduce invece di un'unica chiamata.
MAX_TRANSCRIPT_CHARS = 40_000

# Vincolo anti-allucinazione: senza questo, modelli come gpt-4o-mini tendono
# a "riempire" i punti richiesti con dettagli plausibili ma inventati quando
# i messaggi reali sono pochi o generici (osservato empiricamente su topic
# come "Benvenuti", dove il riassunto elaborava contesto mai scritto).
_GROUNDING_CORE = (
    "Basati ESCLUSIVAMENTE sul contenuto dei messaggi riportati sotto. Non "
    "inventare, dedurre o aggiungere nomi, dettagli, decisioni, motivazioni "
    "o eventi che non siano esplicitamente scritti nei messaggi."
)

# La valvola di sfogo contro l'invenzione ("se hai poco materiale, scrivi
# meno") va formulata nell'unità di misura del testo richiesto: parlare di
# "punti elenco" in un articolo in prosa manda un'istruzione contraddittoria.
GROUNDING_RULE = _GROUNDING_CORE + (
    " Se il contenuto è scarso o ripetitivo, scrivi un riepilogo più breve "
    "(anche solo 1-2 punti, o una singola frase) invece di riempire "
    "artificialmente fino al numero massimo di punti indicato."
)

GROUNDING_PROSE_RULE = _GROUNDING_CORE + (
    " Se il materiale è scarso, scrivi un pezzo più corto, anche di una sola "
    "frase, invece di allungarlo con contesto che nei messaggi non c'è."
    # La seconda metà della regola, che mancava. "Non inventare nomi" letta
    # da sola è un'istruzione a evitare i nomi, e infatti il modello
    # scriveva "il centrocampista", "il club", "un esubero" anche quando
    # nei messaggi il nome c'era scritto. Le due cose sono opposte: non
    # aggiungerne di nuovi, e usare tutti quelli che ci sono.
    " Questo però NON vuol dire scrivere vago: i nomi, le cifre e le date "
    "che nei messaggi ci sono vanno usati tutti, e per esteso. Sostituire "
    "un nome presente nel materiale con un'etichetta generica non è "
    "prudenza, è un'informazione buttata via."
)

# La regola che il pezzo dell'esempio violava dall'inizio alla fine: un
# articolo su un trasferimento che non diceva mai chi si trasferiva, da
# dove e verso dove. Il lettore non era nel gruppo — è il punto di tutto
# il gazzettino — quindi non ha nessun modo di riempire i vuoti da sé, e
# un pezzo di etichette generiche gli lascia la sensazione di aver letto
# senza aver capito.
IDENTIFICAZIONE_RULE = (
    "Nomina le cose. Alla prima volta che compaiono, una persona, una "
    "squadra, una lega, una competizione o un torneo si chiamano con il "
    "loro nome, quello scritto nei messaggi; dalla seconda in poi puoi "
    "usare la formula breve ('il centrocampista', 'il club', 'la lega'). "
    "Un pezzo che per tutta la sua lunghezza parla di 'un giocatore', 'una "
    "squadra' o 'un esubero' non si capisce: chi legge non era nel gruppo "
    "e non ha modo di sapere di chi si sta parlando.\n"
    "Vale allo stesso modo per i numeri: le cifre, le date, gli orari e i "
    "risultati vanno scritti, non riassunti in 'una cifra importante' o "
    "'nei prossimi giorni'.\n"
    # Qui c'era la coda sbagliata: "se un nome non c'è, dillo". Il modello
    # ha ubbidito alla lettera e ogni pezzo è diventato in parte l'elenco
    # di quello che non sapeva — "la data e il luogo non sono indicati",
    # "il materiale non precisa". Un giornale non fa l'inventario dei
    # propri buchi: scrive quello che sa e tace il resto. Il lettore non
    # si accorge di una data mancante; si accorge benissimo di un pezzo
    # che gli spiega di non avere la data.
    "Se invece un nome nei messaggi non c'è, non inventarlo e non "
    "segnalarne l'assenza: scrivi la frase senza, o non scriverla. Un "
    "dettaglio che manca si omette in silenzio."
)

# Le cinque domande del giornalismo. Non sono una formula da manuale: sono
# esattamente le cose che mancavano quando un pezzo risultava incompleto —
# chi e dove, quasi sempre.
CINQUE_W_RULE = (
    "L'attacco deve rispondere a: chi, che cosa, quando, dove e — se i "
    "messaggi lo dicono — perché. Quello a cui i messaggi non rispondono "
    "si lascia fuori senza dirlo: un attacco che nomina le proprie "
    "lacune le rende la notizia."
)

# Il testo viene inviato a Telegram in modalità HTML: il markdown (**, #,
# liste numerate) non viene interpretato e comparirebbe come testo grezzo.
# Il codice applica comunque una pulizia difensiva (vedi report_builder.py),
# ma chiediamo il formato giusto direttamente al modello per ridurre il
# lavoro di post-processing.
FORMAT_RULE = (
    "Formatta l'output SOLO come elenco puntato in testo semplice: ogni "
    "punto su una riga propria che inizia con '• '. NON usare markdown "
    "(niente **grassetto**, niente intestazioni con #, niente numerazione "
    "tipo '1.'). Se vuoi evidenziare chi ha detto cosa, scrivilo nella "
    "frase stessa (es. 'Mario ha proposto...'), senza simboli di "
    "formattazione."
)

# I riassunti a punti alimentano gli articoli del giornale quando un topic
# supera la soglia di chunking (vedi write_topic_article): se le formule
# "gli utenti hanno discusso" entrano qui, si propagano in prima pagina.
NO_META_RULE = (
    "Non nominare il mezzo né l'atto di comunicare: niente 'gli utenti "
    "Telegram', 'nel gruppo', 'nel topic', 'nella chat', 'dai messaggi "
    "emerge', 'i partecipanti hanno discusso'. Riporta direttamente il "
    "fatto, la proposta o la posizione, citando le persone per nome quando "
    "i messaggi lo rendono esplicito.\n"
    "Non parlare MAI della tua fonte né di quello che non contiene: "
    "niente 'il materiale', 'il materiale disponibile', 'non è indicato', "
    "'non sono specificati', 'non è precisato', 'non risulta'. Un giornale "
    "non dichiara quello che non ha potuto sapere: scrive quello che sa. "
    "Se un dettaglio manca, la frase che lo conteneva non si scrive."
)


def _topic_point_budget(message_count: int) -> str:
    """Scala il numero massimo di punti richiesti al modello in base al
    volume reale di messaggi, invece di chiedere sempre lo stesso numero
    di punti a un topic con 1 messaggio e a uno con 200."""
    if message_count <= 3:
        return "1-2"
    if message_count <= 10:
        return "2-3"
    if message_count <= 30:
        return "3-5"
    return "5-7"


def _format_line(message: SimpleMessage, with_topic: str | None = None) -> str:
    time_str = message.timestamp.strftime("%H:%M")
    prefix = f"[{time_str}] {message.author}"
    if with_topic:
        prefix = f"[{time_str}] ({with_topic}) {message.author}"
    return f"{prefix}: {message.text}"


def _format_transcript(messages: list[SimpleMessage], topic: str | None = None) -> str:
    return "\n".join(_format_line(m, topic) for m in messages)


def _chunk_messages(
    messages: list[SimpleMessage], max_chars: int
) -> list[list[SimpleMessage]]:
    chunks: list[list[SimpleMessage]] = []
    current: list[SimpleMessage] = []
    current_len = 0
    for message in messages:
        line_len = len(message.text) + 40
        if current and current_len + line_len > max_chars:
            chunks.append(current)
            current = []
            current_len = 0
        current.append(message)
        current_len += line_len
    if current:
        chunks.append(current)
    return chunks


# I riassunti a punti vogliono aderenza massima alla fonte; la prosa del
# giornale con temperatura così bassa diventa invece piatta e ripetitiva,
# perché il modello ricade sempre sulle stesse costruzioni di frase.
# Sui modelli di ragionamento la distinzione decade — non accettano la
# temperatura — e a tenere in riga i pezzi restano le regole del prompt:
# vedi report/llm.py.
FACTUAL_TEMPERATURE = 0.1
PROSE_TEMPERATURE = 0.5


def _call_openai(
    client: OpenAI, model: str, prompt: str, temperature: float = FACTUAL_TEMPERATURE
) -> str:
    return llm.complete(client, model, prompt, temperature)


def summarize_topic(
    client: OpenAI, model: str, topic_title: str, messages: list[SimpleMessage]
) -> str:
    if not messages:
        return ""

    budget = _topic_point_budget(len(messages))
    chunks = _chunk_messages(messages, MAX_TRANSCRIPT_CHARS)

    if len(chunks) == 1:
        transcript = _format_transcript(chunks[0])
        prompt = (
            f'Sei un assistente che scrive il riepilogo giornaliero del topic '
            f'"{topic_title}" di un gruppo Telegram.\n'
            "Di seguito trovi tutti i messaggi scambiati oggi in questo topic, "
            "in ordine cronologico.\n"
            f"Scrivi un riepilogo (massimo {budget} punti elenco: usane di "
            "meno se il contenuto è poco) dei principali argomenti "
            "discussi. Per ciascun punto, se il messaggio lo rende "
            "esplicito, aggiungi il contesto (chi ha detto cosa, decisioni "
            "prese, dubbi sollevati); altrimenti limitati a descrivere "
            "l'argomento senza inventare dettagli mancanti. Italiano, tono "
            f"neutro e informativo. Sintetizza, non ripetere i messaggi "
            f"parola per parola.\n\n{GROUNDING_RULE}\n\n{IDENTIFICAZIONE_RULE}\n\n"
            f"{NO_META_RULE}\n\n{FORMAT_RULE}\n\n"
            f"Messaggi:\n" + transcript
        )
        return _call_openai(client, model, prompt)

    partial_summaries = []
    for chunk in chunks:
        transcript = _format_transcript(chunk)
        prompt = (
            f'Riassumi in punti elenco (massimo 3-4 punti) i temi discussi '
            f'in questa porzione di conversazione del topic "{topic_title}", '
            f'aggiungendo contesto solo se esplicitamente presente nei '
            f'messaggi.\n\n{GROUNDING_RULE}\n\n{IDENTIFICAZIONE_RULE}\n\n'
            f'{NO_META_RULE}\n\n{FORMAT_RULE}\n\n{transcript}'
        )
        partial_summaries.append(_call_openai(client, model, prompt))

    combined = "\n\n".join(partial_summaries)
    final_prompt = (
        f'Di seguito trovi diversi riassunti parziali della conversazione di '
        f'oggi nel topic "{topic_title}". Unificali in un unico riepilogo '
        f"(massimo {budget} punti elenco), eliminando le ripetizioni.\n\n"
        f"{GROUNDING_RULE} Non aggiungere nulla che non sia già presente nei "
        f"riassunti parziali sotto. I nomi propri, le cifre e le date "
        f"presenti nei riassunti parziali vanno riportati tutti.\n\n"
        f"{NO_META_RULE}\n\n{FORMAT_RULE}\n\n" + combined
    )
    return _call_openai(client, model, final_prompt)


def summarize_overall(
    client: OpenAI, model: str, messages_with_topic: list[tuple[str, SimpleMessage]]
) -> str:
    """Sintetizza SOLO ciò che è trasversale a più topic o particolarmente
    rilevante nel complesso della giornata. Il dettaglio topic per topic è
    già coperto da summarize_topic: qui evitiamo di ripeterlo per non
    duplicare contenuto e allungare inutilmente il report."""
    if not messages_with_topic:
        return ""

    ordered = sorted(messages_with_topic, key=lambda pair: pair[1].timestamp)
    all_messages = [m for _, m in ordered]
    chunks = _chunk_messages(all_messages, MAX_TRANSCRIPT_CHARS)

    highlight_rule = (
        "Il dettaglio di ogni singolo topic viene già fornito altrove nel "
        "report: qui NON devi ripetere argomento per argomento. Scrivi al "
        "massimo 3-4 punti elenco molto brevi (una riga ciascuno) che "
        "catturino SOLO temi che attraversano più topic contemporaneamente, "
        "oppure l'evento/argomento singolarmente più rilevante della "
        "giornata. Se non c'è nulla di trasversale o particolarmente "
        "rilevante, scrivi anche un solo punto o una singola frase."
    )

    if len(chunks) == 1:
        lines = [_format_line(m, topic) for topic, m in ordered]
        transcript = "\n".join(lines)
        prompt = (
            "Sei un assistente che individua i punti salienti della "
            "giornata in un gruppo Telegram organizzato in più topic.\n"
            "Di seguito trovi TUTTI i messaggi scambiati oggi nel gruppo, di "
            "tutti i topic insieme, in ordine cronologico (tra parentesi il "
            f"topic di provenienza).\n{highlight_rule}\n\n"
            f"{GROUNDING_RULE}\n\n{IDENTIFICAZIONE_RULE}\n\n"
            f"{NO_META_RULE}\n\n{FORMAT_RULE}\n\nMessaggi:\n" + transcript
        )
        return _call_openai(client, model, prompt)

    topic_by_message = {id(m): t for t, m in ordered}
    partial_summaries = []
    for chunk in chunks:
        lines = [_format_line(m, topic_by_message.get(id(m))) for m in chunk]
        transcript = "\n".join(lines)
        prompt = (
            "Riassumi in punti elenco (massimo 3-4 punti) i temi trasversali "
            "o particolarmente rilevanti in questa porzione della "
            "conversazione giornaliera del gruppo (tra parentesi il topic di "
            f"provenienza).\n\n{GROUNDING_RULE}\n\n{NO_META_RULE}\n\n{FORMAT_RULE}\n\n" + transcript
        )
        partial_summaries.append(_call_openai(client, model, prompt))

    combined = "\n\n".join(partial_summaries)
    final_prompt = (
        "Di seguito trovi diversi riassunti parziali dei punti salienti di "
        f"oggi nel gruppo. Unificali eliminando le ripetizioni.\n{highlight_rule}"
        f"\n\n{GROUNDING_RULE} Non aggiungere nulla che non sia già presente "
        f"nei riassunti parziali sotto.\n\n{FORMAT_RULE}\n\n" + combined
    )
    return _call_openai(client, model, final_prompt)


# --- Modalità "giornale": titolo + articolo in prosa invece di elenchi ---

# Registro giornalistico. Il difetto tipico dei pezzi generati era l'attacco
# "da verbale di riunione" (si nomina il mezzo invece di raccontare il
# fatto): siccome ogni articolo nasce da una chiamata indipendente, senza un
# divieto esplicito tutti convergono sulla stessa formula e la pagina
# risulta ripetitiva.
STYLE_RULE = (
    "Scrivi come un cronista di quotidiano: al centro del pezzo ci sono i "
    f"fatti, le posizioni e le decisioni, non il mezzo. {NO_META_RULE} "
    "Varia la costruzione delle frasi e scegli verbi specifici invece dei "
    "generici 'dire', 'parlare', 'discutere', 'affrontare'. Usa il passato "
    "prossimo o il presente, mai il futuro. Evita il gergo da riassunto "
    "('si segnala', 'da segnalare', 'in conclusione'), le domande "
    "retoriche, i punti esclamativi e i commenti dell'autore. Preferisci "
    "frasi brevi e concrete a periodi lunghi e astratti."
)

# La regola che tiene insieme il pezzo. Senza, le istruzioni delle tre
# parti si respingono a vicenda — il sommario "aggiunge" al titolo, il
# testo "non ripete" nessuno dei due — e il modello, per non ripetersi,
# cambia argomento a ogni riga: titolo su un fatto, sommario su un altro,
# corpo su un terzo. Non ripetersi e restare sullo stesso fatto sono cose
# diverse, e vanno dette entrambe, in quest'ordine.
COHERENCE_RULE = (
    "Il pezzo racconta UN SOLO fatto, dall'inizio alla fine. Prima scegli "
    "qual è — il più concreto e significativo del materiale — poi scrivi "
    "titolo, sommario e testo tutti su quello. Il sommario non introduce un "
    "secondo argomento: sviluppa il fatto del titolo. Il testo non ne "
    "introduce un terzo: racconta lo stesso fatto con i dettagli che nelle "
    "due righe sopra non ci stavano (chi, quando, che cosa è stato deciso, "
    "che cosa resta aperto). Se nel titolo compare un nome, una cifra o "
    "un'ora, sommario e testo devono restare su quella stessa storia, e chi "
    "legge solo il titolo non deve trovare un pezzo che parla d'altro. "
    "Tutto ciò che nel materiale non riguarda quel fatto resta fuori: è "
    "meglio un pezzo corto e coerente che uno che tocca tre argomenti."
)

# L'attacco. Era la regola che mancava, ed era mancata nel modo peggiore:
# il formato chiedeva un testo "che aggiunge i dettagli senza ricopiare le
# parole del titolo o del sommario", cioè esattamente il contrario di come
# si apre un pezzo di cronaca. Un attacco di giornale RIDICE il fatto, per
# esteso e con le parole giuste; quello che non deve fare è ricopiare la
# frase del titolo. Le due cose si assomigliano abbastanza da confondersi,
# e finché non è stato detto il modello apriva i pezzi con una premessa e
# lasciava la notizia al secondo capoverso.
ATTACCO_RULE = (
    "Il primo capoverso è l'attacco, e in un quotidiano l'attacco è già "
    "tutta la notizia: chi legge solo quello deve sapere che cosa è "
    "successo, quando e a quali condizioni. Non introduce e non prepara "
    "il terreno — comincia dal fatto, con il verbo principale nella prima "
    "riga, e si regge da solo anche staccato dal resto del pezzo. Riprende "
    "il fatto del titolo e lo dice per intero: ridire il fatto va bene, "
    "ricopiare la frase del titolo no.\n"
    + CINQUE_W_RULE
)

# La piramide rovesciata: la forma con cui si scrive un pezzo di cronaca da
# un secolo e mezzo, nata perché il tipografo tagliava dal fondo quando il
# pezzo non stava in colonna. Qui il tipografo è l'impaginazione, che fa
# esattamente la stessa cosa.
PIRAMIDE_RULE = (
    "I capoversi dopo l'attacco stanno in ordine di importanza calante: "
    "prima il dettaglio che cambia la sostanza (chi ha deciso, con quali "
    "numeri, contro quale posizione), poi il contorno, e in fondo quello "
    "che resta aperto o deve ancora succedere. Ogni capoverso aggiunge una "
    "cosa sola, e il pezzo deve reggersi in piedi anche se lo si taglia "
    "dall'ultimo capoverso in su."
)

# Il virgolettato. Un pezzo di cronaca dà la parola a chi c'era: è la
# differenza fra raccontare una discussione e riassumerla. Qui il rischio
# è ovvio — una citazione inventata dentro le virgolette, con un nome vero
# accanto — e la difesa non è il prompt ma la verifica che segue: se la
# frase non compare alla lettera in un messaggio, non si stampa.
QUOTE_RULE = (
    "La citazione è una frase scritta da una persona, copiata ESATTAMENTE "
    "come compare nel suo messaggio: non riscritta, non corretta, non "
    "accorciata, virgolette escluse. Scegli quella che dà la posizione più "
    "netta sul fatto del pezzo, non la più divertente e non un commento "
    "generico, e scarta le frasi che fuori contesto non si capiscono. Se "
    "nessun messaggio dice qualcosa di forte su questo fatto, rispondi "
    "NESSUNA: un pezzo senza virgolettato è normale, un virgolettato "
    "inventato no."
)

HEADLINE_RULE = (
    "Il titolo deve essere in stile testata: sintetico e concreto, senza "
    "punto finale, senza virgolette, senza markdown e senza la formula "
    "'Argomento: spiegazione'. Deve dire che cosa è successo, non "
    "annunciare di che cosa si parla, e deve nominare il fatto principale "
    "del pezzo, non un dettaglio di contorno. Massimo 8 parole: preferisci "
    "un verbo forte a un aggettivo, e il dettaglio concreto (un nome, un "
    "numero, un'ora) al giudizio generico. Il tono è quello di un tifoso "
    "che racconta ad altri tifosi: diretto e caldo, mai sguaiato — niente "
    "punti esclamativi, niente maiuscolo urlato."
)

DECK_RULE = (
    "Il sommario è una frase sola sullo STESSO fatto del titolo: ne dà il "
    "dettaglio, la conseguenza o la posizione che nel titolo non ci "
    "stavano. Non riformula il titolo con altre parole e non cambia "
    "argomento: deve poter essere letto di seguito al titolo come la sua "
    "continuazione naturale. Massimo 160 caratteri, senza punto finale."
)

# Il formato posizionale ("RIGA 1: il titolo, dalla RIGA 2 il corpo") era
# fragile nel modo peggiore: quando il modello lo ignorava e rispondeva in
# un blocco unico, il parser prendeva tutto il testo come titolo e l'
# articolo usciva senza corpo, con un paragrafo intero stampato a 40px. Le
# etichette esplicite sono molto più difficili da sbagliare, e quando
# vengono sbagliate il parser se ne accorge (vedi _parse_labeled).
# La riga FATTO non finisce in pagina: serve a far dichiarare al modello
# l'argomento del pezzo PRIMA di scrivere il titolo, così le tre righe che
# seguono hanno un riferimento comune a cui tornare invece di inseguire
# ciascuna un fatto diverso. Costa una riga di output e si butta via.
ARTICLE_FORMAT_RULE = (
    "Rispondi SOLO con queste cinque righe etichettate, senza markdown e "
    "senza aggiungere altro:\n"
    "FATTO: in una riga, il singolo fatto che il pezzo racconta (riga di "
    "lavoro, non viene pubblicata: serve a fissare l'argomento prima di "
    "scrivere)\n"
    "TITOLO: il titolo di quel fatto, massimo 8 parole\n"
    "SOMMARIO: una frase che sviluppa quello stesso fatto\n"
    "TESTO: 3 capoversi separati da una riga vuota, in tutto fra 600 e 900 "
    "caratteri, tutti sullo stesso fatto: il primo è l'attacco, il secondo "
    "il dettaglio che conta, il terzo quello che resta aperto\n"
    "CITAZIONE: una frase copiata alla lettera da un messaggio, poi una "
    "barra verticale, poi il nome di chi l'ha scritta — oppure la sola "
    "parola NESSUNA\n\n"
    f"{HEADLINE_RULE}\n\n{DECK_RULE}\n\n{ATTACCO_RULE}\n\n{PIRAMIDE_RULE}"
    f"\n\n{QUOTE_RULE}"
)

LEAD_FORMAT_RULE = (
    "Rispondi SOLO con queste sei righe etichettate, senza markdown e "
    "senza aggiungere altro:\n"
    "FATTO: in una riga, il singolo fatto che apre l'edizione (riga di "
    "lavoro, non viene pubblicata: serve a fissare l'argomento prima di "
    "scrivere)\n"
    "SEZIONE: {sections}\n"
    "TITOLO: il titolo di quel fatto, massimo 9 parole\n"
    "SOMMARIO: una frase che sviluppa quello stesso fatto\n"
    "TESTO: 4 capoversi separati da una riga vuota, in tutto fra 900 e "
    "1200 caratteri, tutti su quel fatto\n"
    "CITAZIONE: una frase copiata alla lettera da un messaggio, poi una "
    "barra verticale, poi il nome di chi l'ha scritta — oppure la sola "
    "parola NESSUNA\n\n"
    # Il primo capoverso dell'apertura va da solo in prima pagina, sotto
    # il titolone: è l'unico pezzo di testo che il lettore incontra prima
    # di decidere se girare pagina, e se non basta a sé stesso la prima
    # pagina promette una notizia senza darla.
    "Il primo capoverso dell'apertura viene stampato DA SOLO in prima "
    "pagina, e il resto del pezzo riprende alla pagina seguente: deve "
    "quindi contenere la notizia per intero e non rimandare niente ai "
    "capoversi dopo.\n\n"
    f"{HEADLINE_RULE}\n\n{DECK_RULE}\n\n{ATTACCO_RULE}\n\n{PIRAMIDE_RULE}"
    f"\n\n{QUOTE_RULE}"
)

# Risposta attesa nella riga SEZIONE quando l'apertura non appartiene a una
# sezione sola. In pagina l'occhiello resta il solo "Apertura", che è più
# onesto di una sezione presa a caso.
CROSS_SECTION_MARKER = "TRASVERSALE"


def _lead_section_line(sections: list[str]) -> str:
    """Testo della riga SEZIONE, con l'elenco delle sezioni davvero esistenti.

    Il modello non può inventarsi una sezione: o ne sceglie una di quelle
    aperte oggi, o dichiara che il fatto le attraversa."""
    if not sections:
        return (
            f"scrivi {CROSS_SECTION_MARKER} (oggi non ci sono sezioni fra "
            "cui scegliere)"
        )
    listed = "; ".join(sections)
    return (
        "la sezione da cui viene il fatto qui sopra, copiata identica da "
        f"questo elenco: {listed}. Se il fatto attraversa più sezioni, "
        f"scrivi {CROSS_SECTION_MARKER}"
    )


DUPLICATE_MARKER = "DUPLICATO"


def _avoid_repetition_rule(written: list[tuple[str, str]]) -> str:
    """Ogni articolo viene generato da una chiamata separata, che di per sé
    non sa nulla degli altri pezzi della pagina.

    Passargli i pezzi già scritti serve a due cose: non ricalcarne attacchi
    e titoli, e riconoscere quando il fatto è lo stesso. Lo stesso
    argomento discusso in tre topic diversi produceva tre articoli quasi
    identici, uno per topic; qui il modello può dire che il suo pezzo è un
    doppione e non scriverlo affatto. I pezzi arrivano in ordine di topic
    più attivo, quindi a tenersi la notizia è il topic che l'ha discussa
    di più."""
    pieces = [(h, b) for h, b in written if h]
    if not pieces:
        return ""

    already = "\n".join(f"- {h}: {b}" for h, b in pieces)
    return (
        "Questo pezzo comparirà accanto ad altri nella stessa pagina. "
        f"Pezzi già scritti per l'edizione di oggi:\n{already}\n"
        "Non riprendere quei titoli né quegli attacchi: apri con una "
        "costruzione diversa e usa un lessico diverso.\n"
        "Se il fatto principale di questo tema è già raccontato lì sopra — "
        "succede quando lo stesso argomento gira in più topic — non "
        "riscriverlo: racconta soltanto ciò che qui c'è di diverso, cioè un "
        "dettaglio, uno sviluppo o una posizione che lì non compaiono. Se "
        "non c'è nulla di diverso da aggiungere, rispondi con la sola "
        f"parola {DUPLICATE_MARKER}, senza altro testo."
    )


# Oltre questa lunghezza non è un titolo, è un paragrafo: il parser lo
# spezza invece di mandarlo in pagina a caratteri cubitali.
MAX_HEADLINE_CHARS = 90

# Stessa cosa un gradino più giù. Il sommario che si prende tutto
# l'articolo è il modo in cui il difetto del titolo si ripresenta appena
# lo si tappa: il modello riversa il pezzo nell'etichetta successiva e in
# pagina resta un blocco azzurro lungo dieci righe con sotto "Nessun
# dettaglio disponibile".
MAX_DECK_CHARS = 190

# FATTO e SEZIONE sono righe di servizio: FATTO non arriva mai in pagina,
# SEZIONE diventa l'occhiello dell'apertura. Vanno comunque riconosciute
# come etichette, altrimenti il parser le accoderebbe al blocco precedente
# e il testo di lavoro finirebbe stampato dentro il pezzo.
_LABELS = ("FATTO", "SEZIONE", "TITOLO", "SOMMARIO", "OCCHIELLO", "TESTO", "CITAZIONE")

# Le stesse soglie della frase del giorno: sotto, una citazione non dice
# niente ("vero", "esatto"); sopra, non è più un virgolettato ma un
# paragrafo fra virgolette.
_MIN_QUOTE_CHARS = 25
_MAX_QUOTE_CHARS = 130


def _verify_quote(raw: str, messages) -> "Quote | None":
    """Il virgolettato, ma solo se esiste davvero.

    Il modello dichiara la frase e il nome; qui si cerca la frase, alla
    lettera, dentro i messaggi. Se non c'è, non si stampa niente — e non
    è una precauzione teorica: una citazione plausibile fra virgolette,
    con accanto il nome di una persona vera, è la sola cosa che questo
    giornale può stampare e che nessuno saprebbe riconoscere come falsa.

    Il nome in pagina è quello del messaggio trovato, non quello
    dichiarato dal modello: se sbaglia l'attribuzione, il messaggio ha
    ragione."""
    from report.newspaper import Quote

    testo = _clean(raw or "")
    if not testo or testo.upper().startswith("NESSUNA"):
        return None
    # "frase | autore": il nome dichiarato si scarta, serve solo a far
    # capire al modello che deve attribuirla a qualcuno.
    testo = testo.rpartition("|")[0].strip() or testo
    testo = testo.strip().strip('"').strip("«»").strip()
    if not (_MIN_QUOTE_CHARS <= len(testo) <= _MAX_QUOTE_CHARS):
        return None

    cercato = testo.lower()
    for voce in messages:
        topic, m = voce if isinstance(voce, tuple) else ("", voce)
        if cercato in m.text.lower():
            return Quote(
                text=testo,
                author=m.author,
                topic=topic,
                time=m.timestamp.strftime("%H:%M"),
            )
    print(f"Virgolettato scartato, non combacia con nessun messaggio: {testo!r}")
    return None


def _clean(text: str) -> str:
    return text.strip().lstrip("#").strip().strip('"').strip("«»").strip()


def _parse_labeled(raw: str) -> dict[str, str]:
    """Estrae i blocchi etichettati TITOLO/SOMMARIO/TESTO.

    Le etichette possono comparire con o senza due punti, in qualsiasi
    ordine, e il testo può proseguire su più righe: quello che conta è
    riconoscerle. Se non ce n'è nessuna il risultato è vuoto e chi chiama
    ricade sulla divisione a naso."""
    found: dict[str, list[str]] = {}
    current: str | None = None
    for line in raw.splitlines():
        stripped = line.strip()
        label = None
        for name in _LABELS:
            head = stripped.upper()
            if head.startswith(f"{name}:") or head == name:
                label = name
                stripped = stripped[len(name):].lstrip(":").strip()
                break
        if label:
            current = "SOMMARIO" if label == "OCCHIELLO" else label
            found.setdefault(current, [])
            if stripped:
                found[current].append(stripped)
        elif current is not None:
            # Riga vuota dentro TESTO: separa i paragrafi, va conservata.
            found[current].append(stripped)
    return {k: "\n".join(v).strip() for k, v in found.items()}


def _split_sentence_at(text: str, limit: int) -> tuple[str, str]:
    """Taglia alla fine di frase più lontana che sta entro `limit`.

    È la rete di sicurezza quando il modello consegna un blocco unico.
    Si preferisce la frase intera più lunga possibile: tagliare alla
    prima disponibile produceva titoli mozzi tipo «Il Napoli valuta»
    quando il testo cominciava con una frase brevissima."""
    best = 0
    for end in (". ", "! ", "? ", "; "):
        index = 0
        while True:
            index = text.find(end, index)
            if index < 0 or index > limit:
                break
            best = max(best, index + len(end))
            index += len(end)
    if best:
        return text[:best].strip().rstrip(".;"), text[best:].strip()
    if len(text) <= limit:
        return text, ""
    cut = text.rfind(" ", 0, limit)
    cut = cut if cut > 0 else limit
    return text[:cut].strip().rstrip(",;:"), text[cut:].strip()


def _split_sentence(text: str) -> tuple[str, str]:
    return _split_sentence_at(text, MAX_HEADLINE_CHARS)


def _enforce_lengths(headline: str, deck: str, body: str) -> tuple[str, str, str]:
    """Garantisce che titolo e sommario siano tali.

    È l'invariante che il layout dà per scontata: un h3 a 40px con dentro
    un paragrafo non è un difetto di stile, è una pagina rotta, e un
    sommario di dieci righe con sotto un corpo vuoto lo è altrettanto.
    Qualunque cosa faccia il modello, quello che esce di qui sono un
    titolo corto, un sommario di una frase e tutto il resto nel corpo.

    L'eccedenza scala sempre verso il basso — dal titolo al sommario, dal
    sommario al corpo — perché è l'unica direzione che non perde testo."""
    if len(headline) > MAX_HEADLINE_CHARS:
        headline, overflow = _split_sentence(headline)
        if overflow:
            # Quello che avanza dal titolo apre il sommario se è libero.
            # Se un sommario c'è già, l'avanzo scende invece nel corpo:
            # incollarglielo davanti faceva un sommario di due frasi
            # slegate, che è il difetto che si sta correggendo.
            if deck:
                body = f"{overflow} {body}".strip()
            else:
                deck = overflow

    if len(deck) > MAX_DECK_CHARS:
        deck, overflow = _split_sentence_at(deck, MAX_DECK_CHARS)
        if overflow:
            body = f"{overflow} {body}".strip()

    return headline, _drop_echo_deck(headline, deck), body


def _normalized(text: str) -> str:
    return " ".join(
        "".join(c for c in text.lower() if c.isalnum() or c.isspace()).split()
    )


def _drop_echo_deck(headline: str, deck: str) -> str:
    """Scarta il sommario che è il titolo detto due volte.

    È l'altra faccia dell'incoerenza: se il sommario ricopia il titolo, la
    riga azzurra sotto il titolo non aggiunge niente e vale meno dello
    spazio che occupa. Meglio nessun sommario che un'eco."""
    if not deck or not headline:
        return deck
    head, body = _normalized(headline), _normalized(deck)
    if not head or not body:
        return deck
    return "" if head == body or head in body or body in head else deck


def _unlabeled_lines(raw: str) -> list[str]:
    """Righe della risposta senza quelle di servizio già interpretate.

    Serve solo alla ricaduta «prima riga = titolo»: se il modello etichetta
    FATTO e poi prosegue in prosa, senza questo filtro il titolo diventava
    la riga di lavoro, cioè esattamente la frase che non deve andare in
    pagina."""
    kept = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        head = stripped.upper()
        if any(head.startswith(f"{name}:") or head == name for name in _LABELS):
            continue
        kept.append(stripped)
    return kept


# Un pezzo che non nomina niente. Il controllo è grossolano di proposito —
# non sa che cosa sia un nome proprio, sa solo che una maiuscola in mezzo a
# una frase o una cifra sono l'unica traccia che un pezzo contenga qualcosa
# di specifico. Non blocca niente: stampa una riga nel log della giornata,
# perché il difetto è invisibile finché non si legge il giornale, e a
# quel punto è stato già spedito.
_MAIUSCOLA_INTERNA = re.compile(r"(?<![.!?]\s)(?<!^)(?<!\n)\b[A-ZÀÈÉÌÒÙ][a-zà-ù]{2,}")
_CIFRA = re.compile(r"\d")


def _senza_riferimenti(testo: str) -> bool:
    """Vero se nel pezzo non compare nessun nome proprio né nessuna cifra."""
    if not testo:
        return False
    return not _MAIUSCOLA_INTERNA.search(testo) and not _CIFRA.search(testo)


def _segnala_se_generico(etichetta: str, headline: str, body: str) -> None:
    if _senza_riferimenti(f"{headline} {body}"):
        print(
            f"  {etichetta}: il pezzo non nomina nessuno e non porta una "
            "cifra — o i messaggi non dicevano niente di specifico, o è "
            "uscito generico."
        )


# Le frasi che parlano della fonte invece che del fatto. Il prompt ora le
# vieta, ma un divieto nel prompt è una richiesta: questo è il filtro che
# le toglie comunque, ed è l'unica cosa che le tiene fuori dalla pagina in
# modo affidabile.
#
# La forma è sempre la stessa: una negazione impersonale attaccata a un
# verbo di registrazione ("non è indicato", "non sono specificati"), o la
# parola "materiale" usata per dire "quello che ho letto". Nessuna delle
# due appartiene al vocabolario di un giornale.
_META_ASSENZA = re.compile(
    r"(?:"
    # "non è indicato", "non sono stati precisati", "non è stata riportata"
    r"non\s+(?:è|e'|sono)\s+(?:stat[oaie]\s+)?"
    r"(?:indicat|specificat|precisat|riportat|dichiarat|chiarit)"
    # "il materiale non specifica", "il materiale registra soltanto".
    # "materiale" da solo non basta: esiste anche il materiale rotabile
    # della curva, e un filtro che lo scarta è un filtro che si mette a
    # riscrivere le notizie.
    r"|(?:il|nel|dal|sul)\s+materiale(?:\s+disponibile)?\s+"
    r"(?:non\b|registra|indica|riporta|precisa|specifica|contiene|dice|segnala)"
    r"|materiale\s+disponibile\s*[.,;]"
    # "non viene indicato", "non vengono specificate"
    r"|non\s+(?:viene|vengono)\s+(?:indicat|specificat|precisat)"
    r")",
    re.IGNORECASE,
)

# Taglio in frasi: il punto seguito da spazio. Grossolano — non conosce le
# abbreviazioni — ma qui basta, perché le frasi da togliere finiscono
# sempre con un punto vero.
_FINE_FRASE = re.compile(r"(?<=[.!?])\s+")


def _togli_meta(testo: str) -> tuple[str, int]:
    """Toglie le frasi che dichiarano quello che la fonte non dice.

    Restituisce il testo ripulito e quante frasi sono cadute. Lavora per
    frasi intere e non per sostituzione: "La data non è indicata" senza la
    negazione diventerebbe una frase falsa, che è peggio.

    Se di un capoverso non resta niente, il capoverso sparisce; se non
    resta niente di niente si tiene il testo originale, perché un pezzo
    con una frase di troppo è comunque meglio di un pezzo vuoto."""
    if not testo:
        return testo, 0
    tolte = 0
    capoversi = []
    for blocco in re.split(r"\n\s*\n", testo):
        tenute = []
        for frase in _FINE_FRASE.split(blocco):
            if frase.strip() and _META_ASSENZA.search(frase):
                tolte += 1
                continue
            tenute.append(frase)
        unito = " ".join(f.strip() for f in tenute if f.strip())
        if unito:
            capoversi.append(unito)
    pulito = "\n\n".join(capoversi)
    if not pulito:
        return testo, 0
    return pulito, tolte


def _chiudi_virgolette(testo: str) -> str:
    """Chiude un caporale rimasto aperto.

    Un titolo come «Luca: «Il Napoli ha già perso due big match» esce dal
    modello senza la chiusura una volta ogni tanto, e in pagina si vede."""
    if testo.count("«") == testo.count("»") + 1 and not testo.endswith("»"):
        return testo + "»"
    return testo


def _paragraphs_of(testo: str) -> str:
    """I capoversi del corpo, tenuti separati.

    Prima si univa tutto con uno spazio, e un pezzo di quattro capoversi
    arrivava in pagina come un muro unico: la struttura che il prompt
    chiedeva veniva buttata via dal parser subito dopo essere stata
    scritta. Il separatore è la riga vuota, che è anche quello che il
    modello riceve come istruzione."""
    blocchi = [b.strip() for b in re.split(r"\n\s*\n", testo)]
    return "\n\n".join(" ".join(b.split()) for b in blocchi if b.strip())


def _split_article(raw: str) -> tuple[str, str, str, str]:
    """(titolo, sommario, corpo, citazione grezza) da una risposta."""
    parts = _parse_labeled(raw)
    headline = _clean(parts.get("TITOLO", ""))
    deck = _clean(parts.get("SOMMARIO", ""))
    body = _paragraphs_of(parts.get("TESTO", ""))
    citazione = parts.get("CITAZIONE", "")

    if not headline:
        # Nessuna etichetta riconosciuta: si ricade sulla vecchia regola
        # (prima riga = titolo) e poi si applica comunque il vincolo di
        # lunghezza, che è ciò che mancava prima.
        lines = _unlabeled_lines(raw)
        if not lines:
            return "", "", "", ""
        headline = _clean(lines[0])
        body = body or " ".join(lines[1:]).strip()

    headline, deck, body = _enforce_lengths(headline, deck, body)
    headline = _chiudi_virgolette(headline)
    # Il sommario è una frase sola: se è tutta "materiale", sparisce — un
    # sommario è facoltativo, uno che parla della fonte no.
    deck_pulito, _ = _togli_meta(deck)
    deck = "" if not deck_pulito or _META_ASSENZA.search(deck) else deck
    body, tolte = _togli_meta(body)
    if tolte:
        print(f"  tolte {tolte} frasi che parlavano di quello che i messaggi non dicono.")
    return headline, deck, body, citazione


def write_topic_article(
    client: OpenAI,
    model: str,
    topic_title: str,
    messages: list[SimpleMessage],
    written_so_far: list[tuple[str, str]] | None = None,
) -> tuple[str, str, str, "Quote | None"]:
    """Genera (titolo, sommario, corpo, virgolettato) in stile cronaca.
    Per topic molto attivi (oltre la soglia di chunking) riusa il riassunto
    già condensato da summarize_topic come fonte, invece di rifare da zero
    la logica di map-reduce. `written_so_far` contiene i pezzi già scritti
    per la stessa pagina, usati per evitare attacchi e titoli ripetuti."""
    if not messages:
        return "", "", "", None

    chunks = _chunk_messages(messages, MAX_TRANSCRIPT_CHARS)
    if len(chunks) == 1:
        source_text = _format_transcript(chunks[0])
        source_label = (
            "le conversazioni di oggi su questo tema, nel formato "
            "[ora] autore: testo"
        )
    else:
        source_text = summarize_topic(client, model, topic_title, messages)
        source_label = "un riepilogo già pronto dei punti principali del tema"

    avoid_rule = _avoid_repetition_rule(written_so_far or [])
    prompt = (
        f'Sei un cronista di quotidiano e stai scrivendo il pezzo della '
        f'sezione "{topic_title}" per le pagine interne di oggi. Di seguito '
        f"trovi {source_label}.\n"
        "Il pezzo si apre con il fatto più concreto e significativo. Chi lo "
        "legge NON era nella conversazione da cui la notizia arriva e non "
        "sa niente di quello che è successo: deve capire tutto dal pezzo, "
        "senza dover indovinare di chi o di che cosa si sta parlando.\n\n"
        f"{COHERENCE_RULE}\n\n{GROUNDING_PROSE_RULE}\n\n"
        f"{IDENTIFICAZIONE_RULE}\n\n{STYLE_RULE}\n\n"
        + (f"{avoid_rule}\n\n" if avoid_rule else "")
        + f"{ARTICLE_FORMAT_RULE}\n\n"
        + source_text
    )
    raw = _call_openai(client, model, prompt, temperature=PROSE_TEMPERATURE)
    # Doppione di un pezzo già in pagina: si restituisce vuoto e il topic
    # resta nell'indice col suo contatore, senza un articolo che ripete
    # quello che il lettore ha appena letto.
    if raw.strip().upper().startswith(DUPLICATE_MARKER):
        return "", "", "", None
    headline, deck, body, citazione = _split_article(raw)
    _segnala_se_generico(topic_title, headline, body)
    # La verifica gira sui messaggi veri del topic anche quando il pezzo è
    # stato scritto dal riassunto condensato: è la fonte, e il riassunto
    # non lo è.
    return headline, deck, body, _verify_quote(citazione, messages)


def _split_lead(raw: str) -> tuple[str, str, list[str], str, str]:
    """(titolo, sommario, paragrafi, sezione, citazione grezza).

    Stessa logica degli articoli, con in più la divisione del corpo in
    paragrafi sulle righe vuote e la sezione dichiarata dal modello, che
    diventa l'occhiello."""
    parts = _parse_labeled(raw)
    headline = _clean(parts.get("TITOLO", ""))
    deck = _clean(parts.get("SOMMARIO", ""))
    section = _clean(parts.get("SEZIONE", ""))
    text = parts.get("TESTO", "")
    citazione = parts.get("CITAZIONE", "")

    if not headline:
        # Nessuna etichetta: si ricade sul vecchio formato posizionale,
        # prima riga titolo e seconda sommario.
        blocks = [b for b in "\n".join(_unlabeled_lines(raw)).split("\n\n") if b.strip()]
        first_lines = [l.strip() for l in blocks[0].splitlines() if l.strip()] if blocks else []
        if not first_lines:
            return "", "", [], section, citazione
        headline = _clean(first_lines[0])
        deck = deck or (first_lines[1] if len(first_lines) > 1 else "")
        rest = blocks[1:]
        if not rest and len(first_lines) > 2:
            rest = [" ".join(first_lines[2:])]
        text = "\n\n".join(rest)

    headline, deck, text = _enforce_lengths(headline, deck, text)
    headline = _chiudi_virgolette(headline)
    if _META_ASSENZA.search(deck):
        deck = ""
    text, tolte = _togli_meta(text)
    if tolte:
        print(f"  apertura: tolte {tolte} frasi sulla fonte.")
    paragraphs = [
        " ".join(l.strip() for l in block.splitlines() if l.strip())
        for block in text.split("\n\n")
    ]
    return headline, deck, [p for p in paragraphs if p], section, citazione


def _match_section(declared: str, sections: list[str]) -> str:
    """La sezione dichiarata dal modello, ricondotta a una di quelle vere.

    L'occhiello dell'apertura deve nominare la sezione da cui la notizia
    arriva davvero: una sezione inventata o approssimata è di nuovo
    un'etichetta che dice una cosa diversa dal titolo che ha sotto. Quando
    non c'è corrispondenza si torna alla stringa vuota, e in pagina resta
    il solo "Apertura"."""
    name = declared.strip().strip(".").strip()
    if not name or name.upper() == CROSS_SECTION_MARKER:
        return ""
    lowered = name.casefold()
    for section in sections:
        if section.casefold() == lowered:
            return section
    for section in sections:
        # Il modello a volte accorcia ("Mercato estivo" → "Mercato") o
        # allunga il nome della sezione: basta che una contenga l'altra.
        other = section.casefold()
        if other and (other in lowered or lowered in other):
            return section
    return ""


def write_lead_story(
    client: OpenAI,
    model: str,
    messages_with_topic: list[tuple[str, SimpleMessage]],
    page_headlines: list[str] | None = None,
    sections: list[str] | None = None,
) -> tuple[str, str, list[str], str, "Quote | None"]:
    """Genera (titolo, sommario, paragrafi, sezione, virgolettato) per
    l'articolo di apertura, basato sui temi più rilevanti/trasversali
    della giornata. Il primo capoverso resta in prima pagina e gli altri
    riprendono dentro, quindi il pezzo va scritto perché quel primo
    capoverso basti da solo: la regola sta in LEAD_FORMAT_RULE. Per
    giornate molto attive riusa summarize_overall come fonte condensata
    invece di rifare da zero il map-reduce sui messaggi grezzi.
    `page_headlines` sono i titoli degli articoli già in pagina: servono a
    dare all'apertura un taglio diverso invece di ripetere un pezzo che il
    lettore ha già sotto. `sections` sono i topic attivi oggi, fra cui il
    modello sceglie quello da cui l'apertura arriva: è l'occhiello, e
    finché lo decideva il codice (il topic più attivo) poteva annunciare
    una sezione che con la notizia non c'entrava."""
    if not messages_with_topic:
        return "", "", [], "", None

    ordered = sorted(messages_with_topic, key=lambda pair: pair[1].timestamp)
    all_messages = [m for _, m in ordered]
    chunks = _chunk_messages(all_messages, MAX_TRANSCRIPT_CHARS)

    if len(chunks) == 1:
        lines = [_format_line(m, topic) for topic, m in ordered]
        source_text = "\n".join(lines)
        source_label = (
            "le conversazioni di oggi nel formato [ora] (sezione) autore: testo"
        )
    else:
        source_text = summarize_overall(client, model, messages_with_topic)
        source_label = "un riepilogo già pronto dei temi più rilevanti di oggi"

    titles = [t for t in (page_headlines or []) if t]
    angle_rule = (
        "Nella stessa pagina compaiono già questi articoli: "
        + "; ".join(titles)
        + ". L'apertura deve avere un taglio proprio: se il tema più "
        "importante coincide con uno di quelli, trattalo da un'angolazione "
        "più ampia invece di riscrivere lo stesso pezzo."
        if titles
        else ""
    )

    section_list = [s for s in (sections or []) if s]
    format_rule = LEAD_FORMAT_RULE.format(sections=_lead_section_line(section_list))

    prompt = (
        "Sei il caporedattore e stai scrivendo l'articolo di apertura della "
        f"prima pagina di oggi. Di seguito trovi {source_label}.\n"
        "Individua il fatto più rilevante o il filo che attraversa più "
        "sezioni della giornata. Il titolo sia incisivo ma non "
        "sensazionalistico.\n"
        "Chi legge NON era nella conversazione da cui la notizia arriva: "
        "l'apertura deve spiegargli il fatto per intero, nomi compresi.\n\n"
        f"{COHERENCE_RULE}\n\n{GROUNDING_PROSE_RULE}\n\n"
        f"{IDENTIFICAZIONE_RULE}\n\n{STYLE_RULE}\n\n"
        + (f"{angle_rule}\n\n" if angle_rule else "")
        + f"{format_rule}\n\n"
        + source_text
    )
    raw = _call_openai(client, model, prompt, temperature=PROSE_TEMPERATURE)
    headline, deck, paragraphs, declared, citazione = _split_lead(raw)
    _segnala_se_generico("apertura", headline, " ".join(paragraphs))
    return (
        headline,
        deck,
        paragraphs,
        _match_section(declared, section_list),
        _verify_quote(citazione, ordered),
    )
