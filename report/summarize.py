from openai import OpenAI

from report.fetch import SimpleMessage

# Soglia approssimativa (in caratteri) oltre la quale si passa a un
# riassunto map-reduce invece di un'unica chiamata.
MAX_TRANSCRIPT_CHARS = 40_000

# Vincolo anti-allucinazione: senza questo, modelli come gpt-4o-mini tendono
# a "riempire" i punti richiesti con dettagli plausibili ma inventati quando
# i messaggi reali sono pochi o generici (osservato empiricamente su topic
# come "Benvenuti", dove il riassunto elaborava contesto mai scritto).
GROUNDING_RULE = (
    "Basati ESCLUSIVAMENTE sul contenuto dei messaggi riportati sotto. Non "
    "inventare, dedurre o aggiungere nomi, dettagli, decisioni, motivazioni "
    "o eventi che non siano esplicitamente scritti nei messaggi. Se il "
    "contenuto è scarso o ripetitivo, scrivi un riepilogo più breve (anche "
    "solo 1-2 punti, o una singola frase) invece di riempire artificialmente "
    "fino al numero massimo di punti indicato."
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


def _call_openai(client: OpenAI, model: str, prompt: str) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
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
            f"parola per parola.\n\n{GROUNDING_RULE}\n\n{FORMAT_RULE}\n\n"
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
            f'messaggi.\n\n{GROUNDING_RULE}\n\n{FORMAT_RULE}\n\n{transcript}'
        )
        partial_summaries.append(_call_openai(client, model, prompt))

    combined = "\n\n".join(partial_summaries)
    final_prompt = (
        f'Di seguito trovi diversi riassunti parziali della conversazione di '
        f'oggi nel topic "{topic_title}". Unificali in un unico riepilogo '
        f"(massimo {budget} punti elenco), eliminando le ripetizioni.\n\n"
        f"{GROUNDING_RULE} Non aggiungere nulla che non sia già presente nei "
        f"riassunti parziali sotto.\n\n{FORMAT_RULE}\n\n" + combined
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
            f"{GROUNDING_RULE}\n\n{FORMAT_RULE}\n\nMessaggi:\n" + transcript
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
            f"provenienza).\n\n{GROUNDING_RULE}\n\n{FORMAT_RULE}\n\n" + transcript
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

ARTICLE_FORMAT_RULE = (
    "Rispondi SOLO con questo formato, senza markdown:\n"
    "RIGA 1: il titolo (max 10 parole, niente virgolette, niente punto "
    "finale, niente markdown).\n"
    "Da RIGA 2 in poi: il corpo dell'articolo in prosa (frasi normali, "
    "nessun elenco puntato, nessuna numerazione). Non ripetere il titolo "
    "nel corpo."
)


def _split_headline_body(raw: str) -> tuple[str, str]:
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    if not lines:
        return "", ""
    headline = lines[0].lstrip("#").strip().strip('"')
    body = " ".join(lines[1:]).strip()
    return headline, body


def write_topic_article(
    client: OpenAI, model: str, topic_title: str, messages: list[SimpleMessage]
) -> tuple[str, str]:
    """Genera (titolo, corpo) in stile cronaca giornalistica per un topic.
    Per topic molto attivi (oltre la soglia di chunking) riusa il riassunto
    già condensato da summarize_topic come fonte, invece di rifare da zero
    la logica di map-reduce."""
    if not messages:
        return "", ""

    chunks = _chunk_messages(messages, MAX_TRANSCRIPT_CHARS)
    if len(chunks) == 1:
        source_text = _format_transcript(chunks[0])
        source_label = f'i messaggi di oggi nel topic "{topic_title}"'
    else:
        source_text = summarize_topic(client, model, topic_title, messages)
        source_label = (
            f'questo riepilogo già pronto dei punti principali del topic '
            f'"{topic_title}"'
        )

    prompt = (
        f'Sei un giornalista che scrive un breve pezzo di cronaca sul topic '
        f'"{topic_title}" di un gruppo Telegram, per un articolo nella prima '
        f"pagina di un giornale che riassume la giornata del gruppo. Di "
        f"seguito trovi {source_label}.\n"
        "Scrivi un articolo breve (2-4 frasi), tono da cronaca giornalistica, "
        f"in italiano.\n\n{GROUNDING_RULE}\n\n{ARTICLE_FORMAT_RULE}\n\n"
        + source_text
    )
    raw = _call_openai(client, model, prompt)
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
    client: OpenAI, model: str, messages_with_topic: list[tuple[str, SimpleMessage]]
) -> tuple[str, str, list[str]]:
    """Genera (titolo, occhiello, paragrafi) per l'articolo di apertura,
    basato sui temi più rilevanti/trasversali della giornata. Per giornate
    molto attive riusa summarize_overall come fonte condensata invece di
    rifare da zero il map-reduce sui messaggi grezzi."""
    if not messages_with_topic:
        return "", "", []

    ordered = sorted(messages_with_topic, key=lambda pair: pair[1].timestamp)
    all_messages = [m for _, m in ordered]
    chunks = _chunk_messages(all_messages, MAX_TRANSCRIPT_CHARS)

    if len(chunks) == 1:
        lines = [_format_line(m, topic) for topic, m in ordered]
        source_text = "\n".join(lines)
        source_label = "i messaggi di oggi (tra parentesi il topic di provenienza)"
    else:
        source_text = summarize_overall(client, model, messages_with_topic)
        source_label = "questo riepilogo già pronto dei temi più rilevanti di oggi"

    prompt = (
        "Sei il caporedattore che scrive l'articolo di apertura della prima "
        "pagina di un giornale che riepiloga la giornata di un gruppo "
        f"Telegram organizzato in più topic. Di seguito trovi {source_label}.\n"
        "Individua l'argomento più rilevante o trasversale della giornata e "
        "scrivi:\n"
        "RIGA 1: titolo principale ad effetto ma non clickbait (max 10 "
        "parole), niente virgolette, niente punto finale, niente markdown.\n"
        "RIGA 2: un occhiello di una frase.\n"
        "RIGHE successive: 2-3 paragrafi brevi in prosa giornalistica, in "
        "italiano, separati da una riga vuota.\n\n"
        f"{GROUNDING_RULE}\n\n" + source_text
    )
    raw = _call_openai(client, model, prompt)
    return _split_lead(raw)
