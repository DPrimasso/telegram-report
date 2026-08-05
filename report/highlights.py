"""Statistiche della giornata e frase del giorno.

Le statistiche si calcolano dai messaggi già scaricati: nessuna chiamata in
più, né a Telegram né a OpenAI. La frase del giorno invece va scelta, e la
scelta la fa il modello — ma il testo NON lo scrive: gli si chiede di
restituire una citazione presente alla lettera nei messaggi, così in pagina
finisce una frase vera del gruppo e non una parafrasi.
"""

from collections import Counter

from report.fetch import SimpleMessage
from report.newspaper import Quote, Stats

# Le frasi troppo corte non dicono nulla ("vero", "ahahah"), quelle troppo
# lunghe non stanno nel blocco a 46px.
_MIN_QUOTE_CHARS = 25
_MAX_QUOTE_CHARS = 130


def build_stats(messages_with_topic: list[tuple[str, SimpleMessage]]) -> Stats | None:
    if not messages_with_topic:
        return None
    authors = {m.author for _, m in messages_with_topic}
    topics = {topic for topic, _ in messages_with_topic}
    hours = Counter(m.timestamp.hour for _, m in messages_with_topic)
    peak = hours.most_common(1)[0][0]
    return Stats(
        messages=len(messages_with_topic),
        participants=len(authors),
        active_topics=len(topics),
        peak_hour=f"{peak:02d}:00",
    )


def index_entries(topics) -> list[tuple[str, int]]:
    """Voci dell'indice: topic con almeno un messaggio, dal più attivo."""
    entries = [(t.title, len(t.messages)) for t in topics if t.messages]
    entries.sort(key=lambda e: e[1], reverse=True)
    return entries


_QUOTE_PROMPT = (
    "Di seguito i messaggi di oggi di un gruppo Telegram di tifosi, nel "
    "formato [ora] (topic) autore: testo.\n"
    "Scegli UNA frase da mettere in evidenza come «frase del giorno»: la più "
    "memorabile, ironica o rappresentativa dell'umore della giornata. Non "
    "riscriverla e non correggerla: copiala ESATTAMENTE come è scritta nel "
    f"messaggio. Scarta le frasi sotto i {_MIN_QUOTE_CHARS} caratteri, quelle "
    f"sopra i {_MAX_QUOTE_CHARS}, i link, gli insulti e le frasi che non si "
    "capiscono fuori contesto.\n"
    "Rispondi in una sola riga, in questo formato esatto e senza altro testo:\n"
    "FRASE | AUTORE | TOPIC | ORA\n"
    "Se nessuna frase è adatta, rispondi solo: NESSUNA"
)


def pick_quote(
    client, model: str, messages_with_topic: list[tuple[str, SimpleMessage]]
) -> Quote | None:
    if not messages_with_topic:
        return None

    ordered = sorted(messages_with_topic, key=lambda pair: pair[1].timestamp)
    usable = [
        (topic, m)
        for topic, m in ordered
        if _MIN_QUOTE_CHARS <= len(m.text) <= _MAX_QUOTE_CHARS
        and "http" not in m.text
        and not m.text.startswith("[")
    ]
    if not usable:
        return None

    # Al modello bastano i candidati già filtrati: transcript più corto,
    # meno modi di sbagliare.
    transcript = "\n".join(
        f"[{m.timestamp:%H:%M}] ({topic}) {m.author}: {m.text}" for topic, m in usable
    )
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": f"{_QUOTE_PROMPT}\n\n{transcript}"}],
        temperature=0.2,
    )
    raw = (response.choices[0].message.content or "").strip()
    if not raw or raw.upper().startswith("NESSUNA"):
        return None

    parts = [p.strip() for p in raw.split("|")]
    text = parts[0].strip().strip('"').strip("«»")
    if not text:
        return None

    # Verifica di aderenza: la frase deve esistere davvero in un messaggio,
    # altrimenti la scartiamo. È l'unica difesa contro una citazione
    # inventata, che in un blocco a caratteri cubitali sarebbe imbarazzante.
    lowered = text.lower()
    for topic, m in usable:
        if lowered in m.text.lower():
            return Quote(
                text=text,
                author=m.author,
                topic=topic,
                time=m.timestamp.strftime("%H:%M"),
            )
    print("Frase del giorno scartata: non combacia con nessun messaggio.")
    return None
