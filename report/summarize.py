from openai import OpenAI

from report.fetch import SimpleMessage

# Soglia approssimativa (in caratteri) oltre la quale si passa a un
# riassunto map-reduce invece di un'unica chiamata.
MAX_TRANSCRIPT_CHARS = 40_000


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
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


def summarize_topic(
    client: OpenAI, model: str, topic_title: str, messages: list[SimpleMessage]
) -> str:
    if not messages:
        return ""

    chunks = _chunk_messages(messages, MAX_TRANSCRIPT_CHARS)

    if len(chunks) == 1:
        transcript = _format_transcript(chunks[0])
        prompt = (
            f'Sei un assistente che scrive il riepilogo giornaliero del topic '
            f'"{topic_title}" di un gruppo Telegram.\n'
            "Di seguito trovi tutti i messaggi scambiati oggi in questo topic, "
            "in ordine cronologico.\n"
            "Scrivi un riepilogo sintetico (massimo 5-6 punti elenco) dei "
            "principali argomenti discussi, in italiano, in tono neutro e "
            "informativo. Sintetizza i temi, non ripetere i messaggi parola "
            "per parola.\n\nMessaggi:\n" + transcript
        )
        return _call_openai(client, model, prompt)

    partial_summaries = []
    for chunk in chunks:
        transcript = _format_transcript(chunk)
        prompt = (
            f'Riassumi in punti elenco sintetici (italiano) i temi discussi in '
            f'questa porzione di conversazione del topic "{topic_title}":\n\n'
            + transcript
        )
        partial_summaries.append(_call_openai(client, model, prompt))

    combined = "\n\n".join(partial_summaries)
    final_prompt = (
        f'Di seguito trovi diversi riassunti parziali della conversazione di '
        f'oggi nel topic "{topic_title}". Unificali in un unico riepilogo '
        "sintetico (massimo 6-7 punti elenco), in italiano, eliminando le "
        "ripetizioni:\n\n" + combined
    )
    return _call_openai(client, model, final_prompt)


def summarize_overall(
    client: OpenAI, model: str, messages_with_topic: list[tuple[str, SimpleMessage]]
) -> str:
    if not messages_with_topic:
        return ""

    ordered = sorted(messages_with_topic, key=lambda pair: pair[1].timestamp)
    all_messages = [m for _, m in ordered]
    chunks = _chunk_messages(all_messages, MAX_TRANSCRIPT_CHARS)

    if len(chunks) == 1:
        lines = [
            _format_line(m, topic)
            for topic, m in ordered
        ]
        transcript = "\n".join(lines)
        prompt = (
            "Sei un assistente che scrive il riepilogo generale della "
            "giornata di un gruppo Telegram organizzato in più topic.\n"
            "Di seguito trovi TUTTI i messaggi scambiati oggi nel gruppo, di "
            "tutti i topic insieme, in ordine cronologico (tra parentesi il "
            "topic di provenienza).\n"
            "Scrivi un riepilogo sintetico (massimo 6-8 punti elenco) dei "
            "temi più discussi nella giornata nel complesso, senza "
            "distinguere per topic, in italiano.\n\nMessaggi:\n" + transcript
        )
        return _call_openai(client, model, prompt)

    topic_by_message = {id(m): t for t, m in ordered}
    partial_summaries = []
    for chunk in chunks:
        lines = [_format_line(m, topic_by_message.get(id(m))) for m in chunk]
        transcript = "\n".join(lines)
        prompt = (
            "Riassumi in punti elenco sintetici (italiano) i temi discussi in "
            "questa porzione della conversazione giornaliera del gruppo "
            "(tra parentesi il topic di provenienza):\n\n" + transcript
        )
        partial_summaries.append(_call_openai(client, model, prompt))

    combined = "\n\n".join(partial_summaries)
    final_prompt = (
        "Di seguito trovi diversi riassunti parziali della conversazione "
        "generale di oggi nel gruppo. Unificali in un unico riepilogo dei "
        "temi più discussi nella giornata (massimo 8 punti elenco), in "
        "italiano, eliminando le ripetizioni:\n\n" + combined
    )
    return _call_openai(client, model, final_prompt)
