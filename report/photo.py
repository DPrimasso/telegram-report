"""Foto di apertura del gazzettino.

Catena di ricadute, in ordine: (1) una foto scattata e pubblicata nel
gruppo nel giorno riepilogato, (2) l'immagine dell'anteprima di un link
condiviso nel gruppo, (3) la copertina del video YouTube del canale
pubblicato lo stesso giorno, (4) niente foto — l'apertura resta
tipografica, che è comunque una pagina valida (vedi
newspaper._lead_html).

L'ordine non è arbitrario. Le foto dei messaggi valgono più di tutto il
resto: sono materiale del gruppo e sono pertinenti per costruzione. Le
anteprime dei link vengono dopo perché non sono del gruppo — sono della
testata che ha pubblicato l'articolo — ma riguardano il fatto preciso di
cui si parla, che è più di quanto sappia fare qualunque immagine scelta
per argomento. La copertina YouTube serve nei giorni di sola chiacchiera
e lega il report al canale.

Nota su come Telethon espone le due cose: `message.photo` restituisce
anche la foto dell'anteprima di un link, non solo le foto vere (vedi la
sua docstring). Senza distinguere i due casi l'immagine di un quotidiano
finiva in pagina con la didascalia «Foto dal topic Mercato», cioè
attribuita al gruppo. In un riepilogo di cose vere la provenienza
sbagliata è il difetto più grave che possa avere un'immagine, quindi qui
i due casi sono separati e la didascalia dice sempre da dove arriva.
"""

import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from telethon import TelegramClient

from report.fetch import GENERAL_TOPIC_ID, _fetch_topic_titles, _resolve_group, _topic_id_for_message
from report.newspaper import Hero

# Sotto questa larghezza la foto, ingrandita a 1080px, sgrana: meglio
# passare alla ricaduta successiva.
MIN_PHOTO_WIDTH = 600

_YT_FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
_YT_THUMBS = (
    "https://i.ytimg.com/vi/{vid}/maxresdefault.jpg",
    "https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
)
_ATOM = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}


# Una foto vera del gruppo batte sempre l'anteprima di un link, anche se
# l'anteprima ha più reazioni: le reazioni stanno sotto il messaggio, non
# sotto l'immagine, e un link molto commentato non rende quell'immagine
# più del gruppo di quanto sia.
_GROUP_PHOTO_BONUS = 1000


@dataclass
class _Candidate:
    message: object
    topic: str
    score: int
    webpage: object = None  # valorizzato solo per le anteprime dei link


def _photo_width(message) -> int:
    """La foto ha più "size" (thumbnail incluse): guardiamo la più grande."""
    sizes = getattr(getattr(message, "photo", None), "sizes", None) or []
    return max((getattr(s, "w", 0) or 0) for s in sizes) if sizes else 0


def _source_name(webpage) -> str:
    """Come si chiama la testata, per la didascalia.

    `site_name` è quello che Telegram mostra in grassetto nell'anteprima;
    quando manca si ripiega sul dominio, che è comunque una provenienza
    verificabile — meglio «ilmattino.it» di un generico «dal web»."""
    name = (getattr(webpage, "site_name", None) or "").strip()
    if name:
        return name
    url = (getattr(webpage, "url", None) or "").strip()
    if not url:
        return ""
    host = url.split("//", 1)[-1].split("/", 1)[0]
    return host[4:] if host.startswith("www.") else host


def _engagement(message) -> int:
    reactions = getattr(message, "reactions", None)
    total = 0
    if reactions is not None:
        for r in getattr(reactions, "results", None) or []:
            total += getattr(r, "count", 0) or 0
    replies = getattr(message, "replies", None)
    total += (getattr(replies, "replies", 0) or 0) if replies is not None else 0
    return total


async def pick_hero_photo(
    client: TelegramClient,
    group_id: int,
    day: date,
    timezone: str,
    dest_dir: str | Path,
    *,
    preferred_topic: str = "",
    youtube_channel_id: str = "",
) -> Hero | None:
    hero = await _photo_from_group(
        client, group_id, day, timezone, dest_dir, preferred_topic
    )
    if hero is not None:
        return hero
    if youtube_channel_id:
        return _thumbnail_from_youtube(youtube_channel_id, day, dest_dir)
    return None


async def _photo_from_group(
    client: TelegramClient,
    group_id: int,
    day: date,
    timezone: str,
    dest_dir: str | Path,
    preferred_topic: str,
) -> Hero | None:
    tz = ZoneInfo(timezone)
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = start + timedelta(days=1)

    group = await _resolve_group(client, group_id)
    try:
        titles = await _fetch_topic_titles(client, group)
    except Exception:
        titles = {GENERAL_TOPIC_ID: "General"}
    known = set(titles) - {GENERAL_TOPIC_ID}

    candidates: list[_Candidate] = []
    async for message in client.iter_messages(group, offset_date=end):
        if message.date < start:
            break
        if not getattr(message, "photo", None):
            continue
        if _photo_width(message) < MIN_PHOTO_WIDTH:
            continue
        topic = titles.get(_topic_id_for_message(message, known), "")
        score = _engagement(message)
        # La foto del topic dell'apertura vince a pari reazioni: sta accanto
        # a un titolo che parla di quel tema.
        if preferred_topic and topic == preferred_topic:
            score += 3
        # `message.photo` copre entrambi i casi: se c'è un'anteprima, la
        # foto arriva da lì e va attribuita alla testata, non al gruppo.
        webpage = getattr(message, "web_preview", None)
        if webpage is None:
            score += _GROUP_PHOTO_BONUS
        candidates.append(
            _Candidate(message=message, topic=topic, score=score, webpage=webpage)
        )

    if not candidates:
        return None

    best = max(candidates, key=lambda c: (c.score, c.message.date))
    dest = Path(dest_dir) / "hero.jpg"
    path = await client.download_media(best.message, file=str(dest))
    if not path:
        return None

    when = best.message.date.astimezone(tz).strftime("%H:%M")
    where = f"topic {best.topic}" if best.topic else "gruppo"
    if best.webpage is not None:
        source = _source_name(best.webpage)
        caption = (
            f"Da {source} · link condiviso nel {where}, {when}"
            if source
            else f"Anteprima di un link condiviso nel {where} · {when}"
        )
    else:
        caption = f"Foto dal {where} · {when}"
    return Hero(path=path, caption=caption)


def _thumbnail_from_youtube(
    channel_id: str, day: date, dest_dir: str | Path
) -> Hero | None:
    """Il feed Atom del canale è pubblico e non richiede chiavi API: basta
    l'ID del canale. Espone gli ultimi 15 video, più che sufficiente per un
    report che gira il giorno dopo."""
    try:
        with urllib.request.urlopen(
            _YT_FEED.format(channel_id=channel_id), timeout=10
        ) as response:
            feed = ET.fromstring(response.read())
    except Exception as exc:
        print(f"Feed YouTube non raggiungibile ({exc}): apertura senza foto.")
        return None

    for entry in feed.findall("a:entry", _ATOM):
        published = (entry.findtext("a:published", default="", namespaces=_ATOM) or "")[:10]
        if published != day.isoformat():
            continue
        vid = entry.findtext("yt:videoId", default="", namespaces=_ATOM)
        title = entry.findtext("a:title", default="", namespaces=_ATOM) or ""
        if not vid:
            continue
        for template in _YT_THUMBS:
            dest = Path(dest_dir) / "hero.jpg"
            try:
                urllib.request.urlretrieve(template.format(vid=vid), dest)
            except Exception:
                continue  # maxresdefault non esiste per tutti i video
            return Hero(path=str(dest), caption=f"Dal video di ieri · {title}")
    return None
