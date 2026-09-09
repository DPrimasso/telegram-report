from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

from openai import OpenAI

from report import llm

if TYPE_CHECKING:
    # Solo per le annotazioni. report.fetch tira dentro Telethon, e da
    # quando la vignetta importa campione_citabile da qui, importarlo
    # davvero impediva a preview.py e a biblioteca.py di partire dove
    # Telegram non serve.
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

# Il blocco che non cambia mai fra una chiamata e l'altra. Sta tutto
# insieme e va messo IN TESTA a ogni prompt di prosa, prima di qualunque
# parte variabile: sono 1.800 token identici ripetuti a ogni articolo, e
# quando sono un prefisso comune la cache dei prompt può fatturarli a
# tariffa ridotta invece che pieni quattordici volte. Se restano in mezzo
# al prompt, dopo il nome del topic, il prefisso condiviso è lungo zero.
REGOLE_DI_PROSA = (
    f"{COHERENCE_RULE}\n\n{GROUNDING_PROSE_RULE}\n\n"
    f"{IDENTIFICAZIONE_RULE}\n\n{STYLE_RULE}"
)


# La vignetta si compone nella stessa chiamata dell'apertura. Non è solo
# una chiamata risparmiata: è la stessa testa che sceglie il fatto del
# giorno e le due frasi che lo raccontano, mentre prima erano due
# chiamate a un minuto di distanza tenute insieme da un recinto di
# sezione e da una richiesta nel prompt. La coerenza fra il disegno e il
# titolo che gli sta sopra smette di essere una speranza.
VIGNETTA_FORMAT_RULE = (
    "In fondo, dopo il pezzo, componi anche la VIGNETTA che andrà in "
    "prima pagina accanto a questa apertura: due personaggi che si dicono, "
    "alla lettera, cose che il gruppo ha scritto DAVVERO SU QUESTO STESSO "
    "FATTO.\n"
    "Le battute le prendi dall'elenco di frasi in coda al materiale, e "
    "devono parlare del fatto dell'apertura e di nient'altro: una battuta "
    "bellissima su un altro argomento è la risposta sbagliata, perché in "
    "pagina finisce sotto questo titolo.\n"
    "Ogni battuta è UNA SOLA riga di quell'elenco, copiata dal primo "
    "all'ultimo carattere. Non unire due frasi in una, non ripetere un "
    "pezzo due volte, non correggere gli errori, non accorciare. Una "
    "battuta che non compare identica in una di quelle righe viene "
    "scartata, e nella prova sul campo è successo proprio perché il "
    "modello ne aveva fuse due.\n"
    "Due battute se c'è uno scambio vero fra due persone diverse, una "
    "sola se la frase migliore è rimasta senza risposta. Se sul fatto "
    "dell'apertura non c'è niente di riportabile, scrivi NESSUNA come "
    "tono: la vignetta salta e non è un problema.\n"
    "TONO: {toni_elenco}\n"
    "BATTUTA: la frase copiata alla lettera | il nome di chi l'ha scritta\n"
    "BATTUTA: la seconda, solo se serve"
)

LEAD_FORMAT_RULE = (
    "Rispondi SOLO con queste sei righe etichettate, senza markdown e "
    "senza aggiungere altro:\n"
    "FATTO: in una riga, il singolo fatto che apre l'edizione (riga di "
    "lavoro, non viene pubblicata: serve a fissare l'argomento prima di "
    "scrivere)\n"
    "SEZIONE: {sections}\n"
    "FONTE: il titolo di UNO dei temi qui sotto, copiato identico: "
    "quello di cui parla il fatto che apre\n"
    "TITOLO: il titolo di quel fatto, massimo 9 parole\n"
    "SOMMARIO: una frase che sviluppa quello stesso fatto\n"
    "CITAZIONE: una frase copiata alla lettera da un messaggio, poi una "
    "barra verticale, poi il nome di chi l'ha scritta — oppure la sola "
    "parola NESSUNA\n\n"
    # Il corpo dell'apertura non si scrive: è l'inizio dell'articolo che
    # sta dentro, stampato in prima e continuato alla sua pagina. Su un
    # giornale funziona così, e il testo non compare mai due volte.
    # Scriverne uno nuovo voleva dire raccontare in prima la stessa cosa
    # che l'articolo racconta dopo, con altre parole.
    "NON scrivere il corpo del pezzo: in prima pagina va l'inizio "
    "dell'articolo che hai davanti, e il resto continua alla sua pagina. "
    "Tu scegli quale notizia apre e le dai il titolo e il sommario che "
    "merita in prima pagina.\n\n"
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


def _prima_frase(testo: str, massimo: int = 200) -> str:
    """L'attacco di un pezzo: la prima frase, o quello che ci sta.

    Serve solo a far vedere agli altri articoli come questo comincia, per
    non farlo ricalcare."""
    testo = " ".join(testo.split())
    if not testo:
        return ""
    taglio = _FINE_FRASE.split(testo, maxsplit=1)[0]
    if len(taglio) <= massimo:
        return taglio
    return taglio[:massimo].rsplit(" ", 1)[0] + "…"


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

    # Del pezzo già scritto bastano il titolo e l'attacco. Il titolo dice
    # qual è il fatto, ed è su quello che si riconosce un doppione;
    # l'attacco è la sola frase che serve non ricalcare, perché è quella
    # che il modello sta per scrivere. Il resto del corpo non aggiunge
    # niente a nessuna delle due decisioni e costava, con i corpi da 900
    # caratteri, trentamila token cumulativi per edizione: quasi un quarto
    # dell'ingresso di una giornata normale, speso per rileggere quello
    # che avevamo appena scritto.
    already = "\n".join(
        f"- {h}: {_prima_frase(b)}" if b else f"- {h}" for h, b in pieces
    )
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
_LABELS = (
    "FATTO", "SEZIONE", "FONTE", "TITOLO", "SOMMARIO", "OCCHIELLO",
    "TESTO", "CITAZIONE", "TONO", "BATTUTA",
)

# Le stesse soglie della frase del giorno: sotto, una citazione non dice
# niente ("vero", "esatto"); sopra, non è più un virgolettato ma un
# paragrafo fra virgolette.
# Quante frasi grezze accompagnano i pezzi nel prompt dell'apertura: le
# bastano per scegliere un virgolettato vero senza rileggere la giornata.
_CITABILI_PER_APERTURA = 200

# Quando l'apertura compone anche la vignetta, il campione le serve per
# due mestieri: se ne manda un po' di più, e si scende alla lunghezza
# minima di una battuta, che è più corta di un virgolettato.
_CITABILI_CON_VIGNETTA = 400
_MIN_BATTUTA_APERTURA = 20

_MIN_QUOTE_CHARS = 25
_MAX_QUOTE_CHARS = 130


# Sotto questa lunghezza un messaggio non porta fatti: porta tono.
#
# Il numero viene dall'istogramma del 5 settembre, non dal buon senso:
#   0-10: 12%   10-20: 30%   20-40: 28%   40-80: 19%   80-160: 7%   160+: 4%
#
# Tagliare a venti prenderebbe il 42% dei messaggi, ed è troppo: a undici
# caratteri ci sta "esce Lucca", che è un fatto. A dieci ci stanno "ahah",
# "dai", "gol" e le emoji, e nient'altro. Quel 12% si può buttare senza
# guardarlo.
#
# Il grosso del risparmio comunque non lo fa la soglia, lo fa il tetto:
# la soglia serve a rendere più denso il campione che il tetto sceglie.
SOGLIA_RUMORE = 10

# Oltre questo numero di messaggi un topic non si legge tutto: si
# campiona. Il tetto è alto di proposito — serve a fermare le giornate
# fuori scala, non a potare quelle normali.
MAX_MESSAGGI_PER_ARTICOLO = 1_200


def istogramma_lunghezze(messaggi) -> str:
    """Come sono lunghi i messaggi di oggi, in una riga di log.

    Serve a decidere SOGLIA_RUMORE guardando i dati invece che a occhio,
    e a riaccorgersene se il gruppo cambia abitudini: un gruppo che passa
    ai vocali o alle foto ha una distribuzione diversa, e la soglia di
    ieri non è più quella giusta."""
    if not messaggi:
        return ""
    tagli = [(0, 10), (10, 20), (20, 40), (40, 80), (80, 160), (160, 10**9)]
    totale = len(messaggi)
    pezzi = []
    for basso, alto in tagli:
        quanti = sum(1 for m in messaggi if basso <= len(m.text) < alto)
        etichetta = f"{basso}-{alto}" if alto < 10**9 else f"{basso}+"
        pezzi.append(f"{etichetta}: {quanti} ({100 * quanti / totale:.0f}%)")
    return "  lunghezze dei messaggi — " + ", ".join(pezzi)


def campione_per_articolo(
    messaggi, soglia: int | None = None, tetto: int | None = None
):
    """I messaggi da cui si scrive un articolo, tolto il rumore.

    Due filtri, in quest'ordine. Il primo toglie i messaggi troppo corti
    per contenere un fatto. Il secondo, se ne restano ancora troppi,
    campiona a passo fisso lungo la giornata invece di prendere i primi:
    un articolo che perde la fine della partita è un articolo sbagliato,
    non un articolo corto, e i messaggi arrivano in ordine di tempo."""
    # None vuol dire "usa il valore predefinito", zero vuol dire "spento":
    # con `soglia or SOGLIA_RUMORE` le due cose si confondevano e il
    # filtro non si poteva più disattivare per una prova.
    soglia = SOGLIA_RUMORE if soglia is None else soglia
    tetto = MAX_MESSAGGI_PER_ARTICOLO if tetto is None else tetto
    tenuti = [m for m in messaggi if len(m.text) >= soglia] if soglia else list(messaggi)
    if not tenuti:
        return list(messaggi)
    if not tetto or len(tenuti) <= tetto:
        return tenuti
    passo = len(tenuti) / tetto
    campione = [tenuti[int(i * passo)] for i in range(tetto)]
    print(f"  {len(messaggi)} messaggi, ne leggo {len(campione)}.")
    return campione


def campione_citabile(
    messages_with_topic,
    tetto: int,
    minimo: int = 0,
    massimo: int = 0,
):
    """Le frasi da cui si può ricavare una citazione, al massimo `tetto`.

    Serve a chi deve scegliere UNA frase vera dentro una giornata intera:
    l'apertura per il suo virgolettato, la vignetta per le sue battute.
    Mandare tutti i messaggi del giorno per ricavarne una riga è la
    chiamata col rapporto peggiore di tutto il sistema — novantamila token
    in ingresso per ventinove in uscita.

    Il filtro di lunghezza è quello della frase del giorno: sotto il minimo
    un messaggio non dice niente, sopra il massimo non è una citazione ma
    un paragrafo. Se dentro la fascia i candidati restano troppi, si
    tengono i più lunghi — dentro una fascia stretta, più lungo vuol dire
    più contenuto — e si rimettono in ordine di tempo, perché uno scambio
    a due voci deve restare leggibile come scambio."""
    minimo = minimo or _MIN_QUOTE_CHARS
    massimo = massimo or _MAX_QUOTE_CHARS
    candidati = [
        (topic, m)
        for topic, m in messages_with_topic
        if minimo <= len(m.text) <= massimo
        and "http" not in m.text
        and not m.text.startswith("[")
    ]
    candidati.sort(key=lambda coppia: coppia[1].timestamp)
    if len(candidati) <= tetto:
        return candidati
    scelti = sorted(candidati, key=lambda coppia: len(coppia[1].text), reverse=True)[:tetto]
    scelti.sort(key=lambda coppia: coppia[1].timestamp)
    print(f"  {len(candidati)} frasi candidate, ne mando {tetto}.")
    return scelti


# Con che cosa il modello attribuisce una frase a qualcuno. Il prompt
# chiede la barra verticale; il 5 settembre ha risposto "— Antonio", e
# _verify_quote è andato a cercare nei messaggi una frase con il nome
# attaccato in fondo. Non l'ha trovata, e la prima pagina è uscita senza
# il suo virgolettato.
#
# La frase c'era. A mancare era solo il carattere con cui il modello
# avrebbe dovuto staccarla dal nome.
_SEPARATORI_AUTORE = ("—", "–", " - ")

# Un nome è corto e non è una frase. Sopra questa misura, o con dentro
# una punteggiatura da discorso, quello che segue il trattino è il
# seguito di quello che uno stava dicendo, non la firma.
_MAX_NOME_CHARS = 30
_MAX_NOME_PAROLE = 4


def _spoglia(testo: str) -> str:
    return (testo or "").strip().strip('"').strip("«»").strip()


def _sembra_un_nome(coda: str) -> bool:
    nome = _spoglia(coda)
    if not nome or len(nome) > _MAX_NOME_CHARS:
        return False
    if len(nome.split()) > _MAX_NOME_PAROLE:
        return False
    return not any(segno in nome for segno in ".,;:!?")


def _varianti_senza_autore(riga: str) -> list[str]:
    """La frase così com'è, e poi — se in coda c'è una firma — senza.

    L'ordine conta, ed è tutta la prudenza di questa funzione: prima si
    cerca la riga intera, e solo se quella non compare in nessun
    messaggio si prova a togliere la coda. Così una frase che finisce
    davvero per "— mi sa" non viene accorciata perché somiglia a una
    firma: viene trovata intera al primo colpo."""
    testo = _spoglia(riga)
    if not testo:
        return []
    varianti = [testo]
    # La barra verticale è quella che il prompt chiede e non capita mai
    # dentro un messaggio: se c'è, quello che segue è il nome e basta.
    testa, barra, _coda = testo.rpartition("|")
    if barra and _spoglia(testa):
        varianti.append(_spoglia(testa))
        return varianti
    for separatore in _SEPARATORI_AUTORE:
        testa, trattino, coda = testo.rpartition(separatore)
        if trattino and _spoglia(testa) and _sembra_un_nome(coda):
            varianti.append(_spoglia(testa))
            break
    return varianti


# Le differenze che non si vedono ma bloccano il confronto: un a capo
# dentro un messaggio, due spazi invece di uno, l'apostrofo tipografico
# al posto di quello dritto. Il modello ricopia la frase e la normalizza
# senza accorgersene, e la ricerca alla lettera fallisce su qualcosa che
# in pagina nessuno distinguerebbe.
_SPAZI = re.compile(r"\s+")
_SEGNI_EQUIVALENTI = str.maketrans({
    "\u2019": "'", "\u2018": "'", "\u02bc": "'",
    "\u201c": '"', "\u201d": '"',
    "\u2013": "-", "\u2014": "-", "\u2212": "-",
    "\u00a0": " ",
})


def _normalizza(testo: str) -> str:
    """La forma su cui si confronta: la stessa frase, senza le differenze
    che l'occhio non vede."""
    piatto = unicodedata.normalize("NFKC", testo or "").translate(_SEGNI_EQUIVALENTI)
    return _SPAZI.sub(" ", piatto).strip().lower()


def trova_alla_lettera(riga: str, voci):
    """La frase dentro i messaggi, alla lettera, oppure niente.

    È la difesa su cui poggiano le due cose che questo giornale stampa
    fra virgolette — il virgolettato della prima e le battute della
    vignetta — quindi vale la pena dire che cosa NON fa: non allenta la
    verifica di una virgola. La frase deve continuare a comparire dentro
    un messaggio vero, dal primo all'ultimo carattere. L'unica cosa che
    tollera è che il modello le abbia appiccicato in fondo il nome di chi
    l'ha detta invece di staccarlo come gli era stato chiesto — che è una
    questione di formato, non di verità.

    Restituisce (testo, topic, messaggio), dove `testo` è la frase che ha
    combaciato, cioè quella che va stampata."""
    elenco = []
    for voce in voci:
        topic, m = voce if isinstance(voce, tuple) else ("", voce)
        elenco.append((topic, m, _normalizza(m.text)))
    for candidato in _varianti_senza_autore(riga):
        cercato = _normalizza(candidato)
        if not cercato:
            continue
        for topic, m, testo in elenco:
            if cercato in testo:
                return candidato, topic, m
    return None


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

    trovato = trova_alla_lettera(testo, messages)
    if trovato is None:
        print(f"Virgolettato scartato, non combacia con nessun messaggio: {testo!r}")
        return None

    # La misura si prende su quello che finisce in pagina, non su quello
    # che ha risposto il modello: con il nome ancora attaccato in coda una
    # citazione buona poteva sforare il tetto e sparire senza una riga di
    # log, che è il modo peggiore di perdere qualcosa.
    testo, topic, m = trovato
    if not (_MIN_QUOTE_CHARS <= len(testo) <= _MAX_QUOTE_CHARS):
        return None
    return Quote(
        text=testo,
        author=m.author,
        topic=topic,
        time=m.timestamp.strftime("%H:%M"),
    )


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

    utili = campione_per_articolo(messages)
    chunks = _chunk_messages(utili, MAX_TRANSCRIPT_CHARS)
    if len(chunks) == 1:
        source_text = _format_transcript(chunks[0])
        source_label = (
            "le conversazioni di oggi su questo tema, nel formato "
            "[ora] autore: testo"
        )
    else:
        source_text = summarize_topic(client, model, topic_title, utili)
        source_label = "un riepilogo già pronto dei punti principali del tema"

    avoid_rule = _avoid_repetition_rule(written_so_far or [])
    prompt = (
        # Invariante per prima: è il prefisso che tutte le chiamate
        # dell'edizione hanno in comune.
        "Sei un cronista di quotidiano e stai scrivendo un pezzo per le "
        "pagine interne del gazzettino di oggi. Chi lo legge NON era nella "
        "conversazione da cui la notizia arriva e non sa niente di quello "
        "che è successo: deve capire tutto dal pezzo, senza dover "
        "indovinare di chi o di che cosa si sta parlando. Il pezzo si apre "
        "con il fatto più concreto e significativo.\n\n"
        f"{REGOLE_DI_PROSA}\n\n{ARTICLE_FORMAT_RULE}\n\n"
        # Da qui in giù cambia a ogni chiamata.
        f'Il pezzo di adesso è quello della sezione "{topic_title}". Di '
        f"seguito trovi {source_label}.\n\n"
        + (f"{avoid_rule}\n\n" if avoid_rule else "")
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


# Quanti messaggi di un topic minore bastano per cavarne un titolo. Sono
# pezzi che in pagina escono come una riga sola: mandare duecento messaggi
# per ricavarne otto parole è lo stesso spreco, in piccolo, che si sta
# togliendo in grande.
_MESSAGGI_PER_TITOLO = 60


def write_brief_headlines(
    client: OpenAI,
    model: str,
    topics: list[tuple[str, list[SimpleMessage]]],
    written_so_far: list[tuple[str, str]] | None = None,
) -> dict[str, str]:
    """Un titolo per ciascuno dei topic minori, in UNA chiamata sola.

    In pagina queste voci — le righe di "In breve" e quelle dei blocchi di
    famiglia — mostrano soltanto il titolo. Scriverle con lo stesso prompt
    degli articoli pieni voleva dire pagare milleottocento token di regole
    e la lista dei pezzi già scritti per ogni riga, nove volte su una
    giornata normale.

    Una chiamata sola costa meno e decide meglio: vede tutti i topic
    minori insieme, quindi può evitare che due righe dicano la stessa
    cosa, cosa che nove chiamate separate potevano fare solo passandosi
    una lista che cresceva.

    Restituisce {titolo del topic: titolo del pezzo}. I topic per cui il
    modello non risponde restano fuori, e in pagina non compaiono."""
    attivi = [(t, m) for t, m in topics if m]
    if not attivi:
        return {}

    blocchi = []
    for numero, (titolo, messaggi) in enumerate(attivi, start=1):
        # Degli ultimi si tiene la coda: in una discussione la conclusione
        # sta in fondo, e per un titolo è quello che serve.
        campione = messaggi[-_MESSAGGI_PER_TITOLO:]
        blocchi.append(f"### {numero}. {titolo}\n" + _format_transcript(campione))

    gia = ""
    scritti = [h for h, _ in (written_so_far or []) if h]
    if scritti:
        gia = (
            "Nella stessa edizione compaiono già questi titoli:\n"
            + "\n".join(f"- {h}" for h in scritti)
            + "\nNon ripeterli e non ripetere lo stesso fatto.\n\n"
        )

    prompt = (
        "Sei un cronista di quotidiano. Per ognuno dei temi qui sotto "
        "scrivi UN SOLO titolo, quello che andrà nel riquadro delle brevi "
        "del gazzettino di oggi. Non scrivere articoli: solo il titolo.\n\n"
        f"{HEADLINE_RULE}\n\n{IDENTIFICAZIONE_RULE}\n\n"
        f"{GROUNDING_PROSE_RULE}\n\n{NO_META_RULE}\n\n"
        "Rispondi con una riga per tema, in questo formato esatto e senza "
        "altro testo:\n"
        "NUMERO DEL TEMA | il titolo\n"
        "Il numero è quello che compare qui sotto dopo '###'. Se di un "
        "tema non c'è niente da titolare, salta la sua riga.\n\n"
        + gia
        + "\n\n".join(blocchi)
    )
    raw = _call_openai(client, model, prompt, temperature=PROSE_TEMPERATURE)

    # La chiave della risposta è il numero, non il nome. Il nome resta
    # scritto dentro il blocco perché serve al modello per capire di che
    # cosa parla, ma pretendere che lo ricopiasse identico era una
    # richiesta destinata a fallire: i topic di Telegram si chiamano
    # anche "Seri eCcí", e il 5 settembre quella breve è rimasta senza
    # titolo per un accento. Un numero si ricopia.
    per_numero = {str(n): t for n, (t, _) in enumerate(attivi, start=1)}
    out: dict[str, str] = {}
    for riga in (raw or "").splitlines():
        chiave, barra, titolo = riga.partition("|")
        if not barra:
            continue
        chiave = _clean(chiave).strip("# ").strip().rstrip(".").strip()
        titolo = _chiudi_virgolette(_clean(titolo))
        nome = per_numero.get(chiave)
        if nome and titolo:
            out[nome] = _enforce_lengths(titolo, "", "")[0]
    mancanti = set(per_numero.values()) - set(out)
    if mancanti:
        print(f"  brevi senza titolo: {', '.join(sorted(mancanti))}")
    return out


def _split_lead(
    raw: str,
) -> tuple[str, str, list[str], str, str, str, list[str], str]:
    """(titolo, sommario, paragrafi, sezione, citazione, tono, battute, fonte).

    Stessa logica degli articoli, con in più la divisione del corpo in
    paragrafi sulle righe vuote e la sezione dichiarata dal modello, che
    diventa l'occhiello."""
    parts = _parse_labeled(raw)
    headline = _clean(parts.get("TITOLO", ""))
    deck = _clean(parts.get("SOMMARIO", ""))
    section = _clean(parts.get("SEZIONE", ""))
    text = parts.get("TESTO", "")
    citazione = parts.get("CITAZIONE", "")
    tono = _clean(parts.get("TONO", ""))
    battute = [r.strip() for r in parts.get("BATTUTA", "").splitlines() if r.strip()]
    # Da quale pezzo nasce l'apertura. Serve a mandare il rimando della
    # prima pagina alla pagina giusta; vuota quando il fatto viene da più
    # temi insieme, che nelle giornate grosse è la norma.
    fonte = _clean(parts.get("FONTE", ""))

    if not headline:
        # Nessuna etichetta: si ricade sul vecchio formato posizionale,
        # prima riga titolo e seconda sommario.
        blocks = [b for b in "\n".join(_unlabeled_lines(raw)).split("\n\n") if b.strip()]
        first_lines = [l.strip() for l in blocks[0].splitlines() if l.strip()] if blocks else []
        if not first_lines:
            return "", "", [], section, citazione, tono, battute, fonte
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
    return (
        headline, deck, [p for p in paragraphs if p], section, citazione,
        tono, battute, fonte,
    )


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
    articoli: list[tuple[str, str, str, str, int]] | None = None,
    toni: list[tuple[str, str]] | None = None,
) -> tuple[
    str, str, list[str], str, "Quote | None", str, list[str], str, list
]:
    """Genera (titolo, sommario, paragrafi, sezione, virgolettato) per
    l'articolo di apertura, basato sui temi più rilevanti/trasversali
    della giornata. Sta tutto in prima pagina e non riprende dentro:
    l'ultimo elemento è il TEMA da cui nasce, che serve a mandare il
    rimando della prima pagina alla pagina dove quel pezzo sta per
    intero. Vuoto quando l'apertura mette insieme più temi.

    Per giornate molto attive riusa summarize_overall come fonte condensata
    invece di rifare da zero il map-reduce sui messaggi grezzi.
    `page_headlines` sono i titoli degli articoli già in pagina: servono a
    dare all'apertura un taglio diverso invece di ripetere un pezzo che il
    lettore ha già sotto. `sections` sono i topic attivi oggi, fra cui il
    modello sceglie quello da cui l'apertura arriva: è l'occhiello, e
    finché lo decideva il codice (il topic più attivo) poteva annunciare
    una sezione che con la notizia non c'entrava.

    L'ultimo elemento è il campione di frasi che il modello ha davanti:
    esce di qui perché chi verifica le battute della vignetta deve
    cercarle esattamente lì dentro. Finché il campione veniva rifatto
    fuori con altri parametri, una battuta autentica presa da una frase
    che il secondo campione non conteneva risultava inventata e finiva
    scartata — il 7 settembre è successo con una riga di 114 caratteri,
    dentro la fascia mostrata (fino a 130) e fuori da quella ricostruita
    per la verifica (fino a 110)."""
    if not messages_with_topic:
        return "", "", [], "", None, "", [], "", []

    ordered = sorted(messages_with_topic, key=lambda pair: pair[1].timestamp)
    citabili: list = []

    if articoli:
        # L'apertura si scrive leggendo i pezzi delle pagine interne, che
        # è come lavora un caporedattore vero — e che qui è anche l'unica
        # cosa sensata: quando arriva il suo turno ogni topic è già stato
        # riassunto e scritto, e rileggere la giornata da capo significa
        # pagare due volte lo stesso lavoro. Su una giornata di partita
        # erano centomila token e dieci chiamate, contro i quattromila
        # dei pezzi già in mano.
        pezzi = "\n\n".join(
            f"### {topic} ({conteggio} messaggi)\n{headline}\n{deck}\n{body}".strip()
            for topic, headline, deck, body, conteggio in articoli
        )
        # Il virgolettato dell'apertura deve comunque essere una frase
        # vera: senza messaggi grezzi nel prompt non potrebbe esserlo, e
        # _verify_quote lo scarterebbe sempre.
        # Con la vignetta nella stessa chiamata il campione serve a due
        # cose, quindi si allarga e si apre alla fascia più stretta delle
        # battute: una frase da balloon può essere più corta di una da
        # virgolettato. La fascia è l'unione delle due — dal minimo della
        # battuta al massimo del virgolettato — e questo elenco esce dalla
        # funzione: chi verifica le battute cerca qui dentro, non in un
        # campione ricostruito con altri numeri.
        citabili = campione_citabile(
            ordered,
            _CITABILI_CON_VIGNETTA if toni else _CITABILI_PER_APERTURA,
            minimo=_MIN_BATTUTA_APERTURA if toni else 0,
        )
        frasi = "\n".join(_format_line(m, topic) for topic, m in citabili)
        source_text = (
            f"LE NOTIZIE DI OGGI, GIÀ SCRITTE:\n{pezzi}\n\n"
            f"FRASI DETTE OGGI, PER IL VIRGOLETTATO:\n{frasi}"
        )
        source_label = (
            "i pezzi già scritti per le pagine interne di oggi, e in coda "
            "un elenco di frasi vere del gruppo fra cui scegliere il "
            "virgolettato"
        )
    else:
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
    if toni:
        elenco = "; ".join(f"{nome} ({desc})" for nome, desc in toni)
        format_rule += "\n\n" + VIGNETTA_FORMAT_RULE.format(toni_elenco=elenco)

    prompt = (
        "Sei il caporedattore e stai scrivendo l'articolo di apertura della "
        "prima pagina di oggi. Individua il fatto più rilevante o il filo "
        "che attraversa più sezioni della giornata. Il titolo sia incisivo "
        "ma non sensazionalistico. Chi legge NON era nella conversazione da "
        "cui la notizia arriva: l'apertura deve spiegargli il fatto per "
        "intero, nomi compresi.\n\n"
        f"{REGOLE_DI_PROSA}\n\n"
        # format_rule porta dentro le sezioni attive oggi, quindi cambia
        # ogni giorno e sta sotto la parte invariante.
        f"{format_rule}\n\n"
        f"Di seguito trovi {source_label}.\n\n"
        + (f"{angle_rule}\n\n" if angle_rule else "")
        + source_text
    )
    raw = _call_openai(client, model, prompt, temperature=PROSE_TEMPERATURE)
    (
        headline, deck, paragraphs, declared, citazione, tono, battute, fonte,
    ) = _split_lead(raw)
    _segnala_se_generico("apertura", headline, " ".join(paragraphs))
    # La fonte vale solo se è davvero uno dei temi che abbiamo passato:
    # un titolo storpiato manderebbe il rimando della prima pagina su una
    # pagina a caso, ed è meglio nessun rimando che uno sbagliato.
    # Il confronto passa dalla stessa normalizzazione con cui si verificano
    # i virgolettati: accenti composti in due modi, spazi doppi, apostrofi
    # tipografici. Sono differenze che l'occhio non vede e che qui
    # costavano care — una fonte buttata via significa una prima pagina
    # senza attacco, e il gruppo ha titoli come "Ko-Fi (SUPPORTO CANALE)"
    # e "Seri eCcí", fatti apposta per non essere ricopiati identici.
    noti = [t for t, *_ in (articoli or [])]
    if fonte and fonte not in noti:
        cercata = _normalizza(fonte)
        vicini = [t for t in noti if _normalizza(t) == cercata]
        if not vicini:
            print(f"  fonte dell'apertura non riconosciuta: {fonte!r}")
        fonte = vicini[0] if vicini else ""
    return (
        headline,
        deck,
        paragraphs,
        _match_section(declared, section_list),
        _verify_quote(citazione, ordered),
        tono,
        battute,
        fonte,
        citabili,
    )
