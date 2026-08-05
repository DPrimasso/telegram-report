from openai import OpenAI

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
    "i messaggi lo rendono esplicito."
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
FACTUAL_TEMPERATURE = 0.1
PROSE_TEMPERATURE = 0.5


def _call_openai(
    client: OpenAI, model: str, prompt: str, temperature: float = FACTUAL_TEMPERATURE
) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    return response.choices[0].message.content.strip()


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
            f"parola per parola.\n\n{GROUNDING_RULE}\n\n{NO_META_RULE}\n\n{FORMAT_RULE}\n\n"
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
            f'messaggi.\n\n{GROUNDING_RULE}\n\n{NO_META_RULE}\n\n{FORMAT_RULE}\n\n{transcript}'
        )
        partial_summaries.append(_call_openai(client, model, prompt))

    combined = "\n\n".join(partial_summaries)
    final_prompt = (
        f'Di seguito trovi diversi riassunti parziali della conversazione di '
        f'oggi nel topic "{topic_title}". Unificali in un unico riepilogo '
        f"(massimo {budget} punti elenco), eliminando le ripetizioni.\n\n"
        f"{GROUNDING_RULE} Non aggiungere nulla che non sia già presente nei "
        f"riassunti parziali sotto.\n\n{NO_META_RULE}\n\n{FORMAT_RULE}\n\n" + combined
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
            f"{GROUNDING_RULE}\n\n{NO_META_RULE}\n\n{FORMAT_RULE}\n\nMessaggi:\n" + transcript
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

HEADLINE_RULE = (
    "Il titolo deve essere in stile testata: sintetico e concreto, senza "
    "punto finale, senza virgolette, senza markdown e senza la formula "
    "'Argomento: spiegazione'. Deve dire che cosa è successo, non "
    "annunciare di che cosa si parla. Massimo 8 parole: preferisci un verbo "
    "forte a un aggettivo, e il dettaglio concreto (un nome, un numero, "
    "un'ora) al giudizio generico. Il tono è quello di un tifoso che "
    "racconta ad altri tifosi: diretto e caldo, mai sguaiato — niente punti "
    "esclamativi, niente maiuscolo urlato."
)

ARTICLE_FORMAT_RULE = (
    "Rispondi SOLO con questo formato, senza markdown:\n"
    f"RIGA 1: il titolo (max 10 parole). {HEADLINE_RULE}\n"
    "Da RIGA 2 in poi: il corpo dell'articolo in prosa (frasi normali, "
    "nessun elenco puntato, nessuna numerazione). Non ripetere il titolo "
    "nel corpo."
)


def _avoid_repetition_rule(written: list[tuple[str, str]]) -> str:
    """Ogni articolo viene generato da una chiamata separata, che di per sé
    non sa nulla degli altri pezzi della pagina. Passandogli i titoli e gli
    attacchi già usati gli diamo il contesto minimo per non ricalcarli."""
    titles = [h for h, _ in written if h]
    openings = [" ".join(b.split()[:7]) for _, b in written if b]
    if not titles and not openings:
        return ""

    parts = ["Questo pezzo comparirà accanto ad altri nella stessa pagina."]
    if titles:
        parts.append("Titoli già presenti: " + "; ".join(titles) + ".")
    if openings:
        parts.append("Prime parole dei pezzi già scritti: " + "; ".join(openings) + ".")
    parts.append(
        "Non riprendere quei titoli né quegli attacchi: apri con una "
        "costruzione diversa e usa un lessico diverso."
    )
    return " ".join(parts)


def _split_headline_body(raw: str) -> tuple[str, str]:
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    if not lines:
        return "", ""
    headline = lines[0].lstrip("#").strip().strip('"')
    body = " ".join(lines[1:]).strip()
    return headline, body


def write_topic_article(
    client: OpenAI,
    model: str,
    topic_title: str,
    messages: list[SimpleMessage],
    written_so_far: list[tuple[str, str]] | None = None,
) -> tuple[str, str]:
    """Genera (titolo, corpo) in stile cronaca giornalistica per un topic.
    Per topic molto attivi (oltre la soglia di chunking) riusa il riassunto
    già condensato da summarize_topic come fonte, invece di rifare da zero
    la logica di map-reduce. `written_so_far` contiene i pezzi già scritti
    per la stessa pagina, usati per evitare attacchi e titoli ripetuti."""
    if not messages:
        return "", ""

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
        f'sezione "{topic_title}" per la prima pagina di oggi. Di seguito '
        f"trovi {source_label}.\n"
        "Scrivi 1-2 frasi (massimo 320 caratteri in totale), che si aprano "
        "con il fatto più "
        "concreto e significativo e si regga da solo, senza presupporre che "
        "il lettore sappia da dove arriva la notizia.\n\n"
        f"{GROUNDING_PROSE_RULE}\n\n{STYLE_RULE}\n\n"
        + (f"{avoid_rule}\n\n" if avoid_rule else "")
        + f"{ARTICLE_FORMAT_RULE}\n\n"
        + source_text
    )
    raw = _call_openai(client, model, prompt, temperature=PROSE_TEMPERATURE)
    return _split_headline_body(raw)


def _split_lead(raw: str) -> tuple[str, str, list[str]]:
    blocks = [b.strip() for b in raw.split("\n\n") if b.strip()]
    if not blocks:
        return "", "", []
    first_lines = [l.strip() for l in blocks[0].splitlines() if l.strip()]
    if not first_lines:
        return "", "", []
    headline = first_lines[0].lstrip("#").strip().strip('"')
    deck = first_lines[1] if len(first_lines) > 1 else ""
    paragraphs = [" ".join(l.strip() for l in b.splitlines() if l.strip()) for b in blocks[1:]]
    if not paragraphs and len(first_lines) > 2:
        paragraphs = [" ".join(first_lines[2:])]
    return headline, deck, [p for p in paragraphs if p]


def write_lead_story(
    client: OpenAI,
    model: str,
    messages_with_topic: list[tuple[str, SimpleMessage]],
    page_headlines: list[str] | None = None,
) -> tuple[str, str, list[str]]:
    """Genera (titolo, occhiello, paragrafi) per l'articolo di apertura,
    basato sui temi più rilevanti/trasversali della giornata. Per giornate
    molto attive riusa summarize_overall come fonte condensata invece di
    rifare da zero il map-reduce sui messaggi grezzi. `page_headlines` sono
    i titoli degli articoli già in pagina: servono a dare all'apertura un
    taglio diverso invece di ripetere un pezzo che il lettore ha già sotto."""
    if not messages_with_topic:
        return "", "", []

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

    prompt = (
        "Sei il caporedattore e stai scrivendo l'articolo di apertura della "
        f"prima pagina di oggi. Di seguito trovi {source_label}.\n"
        "Individua il fatto più rilevante o il filo che attraversa più "
        "sezioni della giornata e scrivi:\n"
        "RIGA 1: il titolo di apertura (max 10 parole), incisivo ma non "
        "sensazionalistico.\n"
        "RIGA 2: un occhiello di una frase, che aggiunga informazione invece "
        "di riformulare il titolo.\n"
        "RIGHE successive: 2 paragrafi brevi (massimo 300 caratteri "
        "ciascuno) separati da una riga vuota. "
        "Il primo apre con il fatto principale, gli altri aggiungono "
        "contesto o conseguenze.\n\n"
        f"{GROUNDING_PROSE_RULE}\n\n{STYLE_RULE}\n\n{HEADLINE_RULE}\n\n"
        + (f"{angle_rule}\n\n" if angle_rule else "")
        + source_text
    )
    raw = _call_openai(client, model, prompt, temperature=PROSE_TEMPERATURE)
    return _split_lead(raw)
