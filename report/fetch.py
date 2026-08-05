from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from telethon import TelegramClient
from telethon.tl.functions.channels import GetForumTopicsRequest

from report import scribe

GENERAL_TOPIC_ID = 1


@dataclass
class SimpleMessage:
    author: str
    timestamp: datetime
    text: str


@dataclass
class TopicMessages:
    topic_id: int
    title: str
    messages: list[SimpleMessage]


def _display_name(sender) -> str:
    if sender is None:
        return "Sconosciuto"
    first = getattr(sender, "first_name", None) or ""
    last = getattr(sender, "last_name", None) or ""
    full = f"{first} {last}".strip()
    if full:
        return full
    username = getattr(sender, "username", None)
    if username:
        return f"@{username}"
    title = getattr(sender, "title", None)
    return title or "Sconosciuto"


def _message_text(message) -> str | None:
    if message.action is not None:
        return None
    if message.message:
        return message.message
    if message.photo:
        return "[foto]"
    if message.document:
        return "[documento]"
    if message.sticker:
        return "[sticker]"
    if message.poll:
        return "[sondaggio]"
    return "[media]"


def _topic_id_for_message(message, known_topic_ids: set[int]) -> int:
    reply = message.reply_to
    if reply is not None and getattr(reply, "forum_topic", False):
        return reply.reply_to_top_id or reply.reply_to_msg_id
    # Il messaggio che apre un topic non "risponde" a nulla (è lui stesso la
    # radice del thread): il suo message.id coincide con l'ID del topic.
    # Senza questo controllo finirebbe erroneamente nel topic General.
    if message.id in known_topic_ids:
        return message.id
    return GENERAL_TOPIC_ID


async def _author_of(message, sender_cache: dict[int, str]) -> str:
    sender_id = message.sender_id
    if sender_id is not None and sender_id not in sender_cache:
        try:
            sender = await message.get_sender()
            sender_cache[sender_id] = _display_name(sender)
        except Exception:
            sender_cache[sender_id] = f"Utente {sender_id}"
    return sender_cache.get(sender_id, "Sconosciuto")


async def _unwrap_scribe(
    message,
    text: str,
    topic_id: int,
    sender_cache: dict[int, str],
    summary_markers: tuple[str, ...],
) -> tuple[str, str] | None:
    """Traduce un messaggio del bot trascrittore in (autore vero, testo).

    Restituisce None quando il messaggio non deve entrare nel report: è un
    riepilogo su richiesta, oppure una trascrizione di cui non si riesce a
    stabilire chi ha parlato. Attribuirla al bot la farebbe passare per una
    presa di posizione dello "Scribacchino", che non esiste."""
    classified = scribe.classify(text, summary_markers)
    if classified is None:
        return None
    author, text = classified
    # Il nome in testa al testo è la via normale e non costa chiamate.
    if author is not None:
        return author, text

    # Se il bot risponde al vocale invece di citarne l'autore, l'autore è il
    # mittente del messaggio a cui risponde. In un forum reply_to_msg_id
    # vale l'ID del topic anche quando non si sta rispondendo a nessuno:
    # senza questo confronto attribuiremmo tutto a chi ha aperto il topic.
    reply = message.reply_to
    replied_id = getattr(reply, "reply_to_msg_id", None) if reply is not None else None
    if replied_id and replied_id != topic_id:
        try:
            original = await message.get_reply_message()
        except Exception:
            original = None
        if original is not None:
            author = await _author_of(original, sender_cache)
            if author and not scribe.is_scribe(author):
                return author, text

    return None


async def _resolve_group(client: TelegramClient, group_id: int):
    # StringSession non persiste la cache delle entità: un client "fresco"
    # potrebbe non riuscire a risolvere l'ID senza aver prima visto i
    # dialoghi in questa sessione di connessione. Fallback: cerca tra i
    # dialoghi correnti.
    try:
        return await client.get_entity(group_id)
    except ValueError:
        async for dialog in client.iter_dialogs():
            if dialog.id == group_id:
                return dialog.entity
        raise ValueError(
            f"Impossibile trovare il gruppo con ID {group_id}. Verifica che "
            "TELEGRAM_GROUP_ID sia corretto: deve essere negativo (es. "
            "-1001234567890), esattamente come stampato da generate_session.py."
        )


async def get_group_title(client: TelegramClient, group_id: int) -> str:
    group = await _resolve_group(client, group_id)
    return getattr(group, "title", None) or "Gazzettino"


async def list_topics(client: TelegramClient, group_id: int) -> list[tuple[int, str]]:
    """Elenca (id, titolo) dei topic del gruppo, ordinati per id. Serve a
    ricavare il valore di REPORT_TOPIC_ID senza doverlo cercare a mano nei
    link di Telegram."""
    group = await _resolve_group(client, group_id)
    titles = await _fetch_topic_titles(client, group)
    return sorted(titles.items())


async def _fetch_topic_titles(client: TelegramClient, group) -> dict[int, str]:
    result = await client(
        GetForumTopicsRequest(
            channel=group, offset_date=0, offset_id=0, offset_topic=0, limit=100
        )
    )
    titles = {topic.id: topic.title for topic in result.topics}
    titles.setdefault(GENERAL_TOPIC_ID, "General")
    return titles


async def fetch_day_messages(
    client: TelegramClient,
    group_id: int,
    day: date,
    timezone: str,
    debug: bool = False,
    scribe_names: tuple[str, ...] = scribe.DEFAULT_BOT_NAMES,
    summary_markers: tuple[str, ...] = scribe.DEFAULT_SUMMARY_MARKERS,
) -> list[TopicMessages]:
    tz = ZoneInfo(timezone)
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = start + timedelta(days=1)

    group = await _resolve_group(client, group_id)

    try:
        titles = await _fetch_topic_titles(client, group)
    except Exception:
        titles = {GENERAL_TOPIC_ID: "General"}

    known_topic_ids = set(titles.keys()) - {GENERAL_TOPIC_ID}
    if debug:
        print(f"[DEBUG] topic noti: {titles}")
    sender_cache: dict[int, str] = {}
    buckets: dict[int, list[SimpleMessage]] = {}
    skipped_scribe = 0
    reattributed = 0

    async for message in client.iter_messages(group, offset_date=end):
        if message.date < start:
            break

        text = _message_text(message)
        if text is None:
            continue

        author = await _author_of(message, sender_cache)
        topic_id = _topic_id_for_message(message, known_topic_ids)

        if scribe.is_scribe(author, scribe_names):
            unwrapped = await _unwrap_scribe(
                message, text, topic_id, sender_cache, summary_markers
            )
            if unwrapped is None:
                skipped_scribe += 1
                if debug:
                    print(f"[DEBUG] scartato dal bot | msg_id={message.id} testo={text[:80]!r}")
                continue
            author, text = unwrapped
            reattributed += 1

        if debug and topic_id == GENERAL_TOPIC_ID:
            reply = message.reply_to
            reply_info = reply.to_dict() if reply is not None else None
            print(
                f"[DEBUG] -> General | msg_id={message.id} data={message.date} "
                f"autore={author!r} reply_to={reply_info} "
                f"testo={text[:80]!r}"
            )

        buckets.setdefault(topic_id, []).append(
            SimpleMessage(author=author, timestamp=message.date, text=text)
        )

    if reattributed or skipped_scribe:
        print(
            f"Bot trascrittore: {reattributed} vocali riattribuiti a chi ha "
            f"parlato, {skipped_scribe} messaggi ignorati (riepiloghi o non "
            "attribuibili)."
        )

    topics = []
    for topic_id, messages in buckets.items():
        messages.sort(key=lambda m: m.timestamp)
        title = titles.get(topic_id, f"Topic {topic_id}")
        topics.append(TopicMessages(topic_id=topic_id, title=title, messages=messages))
    topics.sort(key=lambda t: t.topic_id)
    return topics
