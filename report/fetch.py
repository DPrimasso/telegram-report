from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from telethon import TelegramClient
from telethon.tl.functions.channels import GetForumTopicsRequest

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


def _topic_id_for_message(message) -> int:
    reply = message.reply_to
    if reply is not None and getattr(reply, "forum_topic", False):
        return reply.reply_to_top_id or reply.reply_to_msg_id
    return GENERAL_TOPIC_ID


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
    client: TelegramClient, group_id: int, day: date, timezone: str
) -> list[TopicMessages]:
    tz = ZoneInfo(timezone)
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = start + timedelta(days=1)

    group = await client.get_entity(group_id)

    try:
        titles = await _fetch_topic_titles(client, group)
    except Exception:
        titles = {GENERAL_TOPIC_ID: "General"}

    sender_cache: dict[int, str] = {}
    buckets: dict[int, list[SimpleMessage]] = {}

    async for message in client.iter_messages(group, offset_date=end):
        if message.date < start:
            break

        text = _message_text(message)
        if text is None:
            continue

        sender_id = message.sender_id
        if sender_id is not None and sender_id not in sender_cache:
            try:
                sender = await message.get_sender()
                sender_cache[sender_id] = _display_name(sender)
            except Exception:
                sender_cache[sender_id] = f"Utente {sender_id}"
        author = sender_cache.get(sender_id, "Sconosciuto")

        topic_id = _topic_id_for_message(message)
        buckets.setdefault(topic_id, []).append(
            SimpleMessage(author=author, timestamp=message.date, text=text)
        )

    topics = []
    for topic_id, messages in buckets.items():
        messages.sort(key=lambda m: m.timestamp)
        title = titles.get(topic_id, f"Topic {topic_id}")
        topics.append(TopicMessages(topic_id=topic_id, title=title, messages=messages))
    topics.sort(key=lambda t: t.topic_id)
    return topics
