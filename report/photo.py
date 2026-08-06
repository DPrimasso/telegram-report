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

# Sotto questa larghezza la foto, ingrandita a 968px, sgrana: meglio
# passare alla ricaduta successiva.
MIN_PHOTO_WIDTH = 600

# La fascia in fondo mostra le immagini a un quarto di larghezza, quindi
# regge sorgenti molto più piccole. È la soglia che rende utilizzabili i
# fotogrammi dei video: Telegram allega ai video miniature da 320px, che a
# tutta pagina sarebbero impresentabili e in una fascia da quattro no.
MIN_STRIP_WIDTH = 260

# Quante immagini possono andare ai pezzi secondari, oltre a quella di
# apertura. Da quando le sorgenti piccole stanno in un colonnino accanto
# al testo invece che a piena larghezza, un pezzo illustrato non schiaccia
# più gli altri: il limite serve solo a non trasformare l'edizione in un
# album, e ci pensa comunque l'impaginatore a togliere le foto che non
# stanno nella pagina.
MAX_ARTICLE_PHOTOS = 4

# Le immagini della fascia di chiusura. Quattro riempiono esattamente la
# larghezza utile e restano abbastanza grandi da riconoscere un soggetto.
MAX_STRIP_PHOTOS = 4

_YT_FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
# Le dimensioni sono note per costruzione. maxresdefault è un 16:9 pieno,
# quindi si può dare al riquadro le sue proporzioni. hqdefault è invece un
# 480x360 con il video 16:9 incassato dentro e due bande nere sopra e
# sotto: lì le proporzioni vere sarebbero quelle sbagliate da usare, e si
# lascia 0 — il riquadro di default ritaglia via proprio le bande.
_YT_THUMBS = (
    ("https://i.ytimg.com/vi/{vid}/maxresdefault.jpg", 1280, 720),
    ("https://i.ytimg.com/vi/{vid}/hqdefault.jpg", 0, 0),
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
    width: int = 0
    height: int = 0
    webpage: object = None  # valorizzato solo per le anteprime dei link
    kind: str = "foto"      # "foto" oppure "video"
    thumb: object = None    # la PhotoSize da scaricare, per i video


def _photo_size(message) -> tuple[int, int]:
    """Dimensioni della versione più grande della foto.

    Telegram allega più "size" allo stesso scatto (miniature comprese):
    quella buona è la più larga. Le dimensioni servono due volte — per
    scartare le foto troppo piccole e per dare al riquadro in pagina le
    proporzioni giuste — e arrivano gratis con il messaggio, senza
    bisogno di aprire il file scaricato."""
    sizes = getattr(getattr(message, "photo", None), "sizes", None) or []
    best_w, best_h = 0, 0
    for size in sizes:
        w = getattr(size, "w", 0) or 0
        h = getattr(size, "h", 0) or 0
        # Le PhotoStrippedSize non hanno w/h: si saltano da sole.
        if w > best_w:
            best_w, best_h = w, h
    return best_w, best_h


def _largest_thumb(document):
    """La miniatura più grande di un video, saltando quelle senza
    dimensioni (le "stripped", che sono venti byte di anteprima sfocata)."""
    best, best_w = None, 0
    for thumb in getattr(document, "thumbs", None) or []:
        w = getattr(thumb, "w", 0) or 0
        h = getattr(thumb, "h", 0) or 0
        if w > best_w and h > 0:
            best, best_w = thumb, w
    return best


def _visual_of(message) -> tuple[str, int, int, object] | None:
    """Che immagine si può ricavare da un messaggio: (tipo, w, h, miniatura).

    I video contano quanto le foto. In un gruppo di tifosi la maggior
    parte del materiale visivo sono clip — il gol, l'intervista, il
    momento della partita — e ignorarle lasciava il gazzettino con una
    sola immagine al giorno anche nelle giornate piene. Di un video si
    prende il fotogramma di copertina, che Telegram allega già.

    Gli sticker restano fuori: hanno un loro linguaggio grafico, colori e
    contorni propri, e in pagina sarebbero la cosa più fuori posto di
    tutte."""
    if getattr(message, "sticker", None) is not None:
        return None
    if getattr(message, "photo", None):
        width, height = _photo_size(message)
        return ("foto", width, height, None)
    document = getattr(message, "video", None) or getattr(message, "gif", None)
    if document is None:
        return None
    thumb = _largest_thumb(document)
    if thumb is None:
        return None
    return ("video", getattr(thumb, "w", 0) or 0, getattr(thumb, "h", 0) or 0, thumb)


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


@dataclass
class DayPhotos:
    """Le immagini della giornata: quella di apertura, quelle dei pezzi
    secondari (al più una per topic) e quelle della fascia di chiusura."""

    hero: Hero | None = None
    by_topic: dict[str, Hero] = None  # type: ignore[assignment]
    strip: list[Hero] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.by_topic is None:
            self.by_topic = {}
        if self.strip is None:
            self.strip = []


async def pick_day_photos(
    client: TelegramClient,
    group_id: int,
    day: date,
    timezone: str,
    dest_dir: str | Path,
    *,
    preferred_topic: str = "",
    youtube_channel_id: str = "",
    max_article_photos: int = MAX_ARTICLE_PHOTOS,
    max_strip_photos: int = MAX_STRIP_PHOTOS,
) -> DayPhotos:
    """Sceglie le foto del giorno in un passaggio solo sui messaggi.

    Un secondo giro sulla stessa giornata costerebbe altrettante chiamate
    a Telegram — in un gruppo da millesettecento messaggi al giorno non è
    trascurabile — quindi i candidati si raccolgono una volta e si
    smistano dopo: il migliore in assoluto apre, i migliori dei topic
    rimasti vanno ai pezzi secondari, il resto alla fascia di chiusura."""
    tz = ZoneInfo(timezone)
    dest_dir = Path(dest_dir)
    candidates = await _collect_candidates(
        client, group_id, day, tz, preferred_topic
    )

    if not candidates:
        # Senza niente nel gruppo resta la copertina del canale, che però
        # apre e basta: non ha un topic a cui appartenere.
        hero = (
            _thumbnail_from_youtube(youtube_channel_id, day, dest_dir)
            if youtube_channel_id
            else None
        )
        return DayPhotos(hero=hero)
    ordered = sorted(candidates, key=lambda c: (c.score, c.message.date), reverse=True)

    used: set[int] = set()
    used_topics: set[str] = set()

    # L'apertura può portare SOLO un'immagine del suo topic. L'immagine
    # sotto un titolo si legge come illustrazione di quel titolo: una foto
    # di un altro topic lì sopra è un'attribuzione sbagliata, non una
    # decorazione — è il difetto visto sul gazzettino vero, con la foto di
    # un topic qualunque sotto l'apertura sul mercato. Se il topic
    # dell'apertura non ha un'immagine abbastanza grande, l'apertura resta
    # tipografica e le immagini vanno ai pezzi a cui appartengono.
    hero = None
    hero_pool = [
        c
        for c in ordered
        if c.width >= MIN_PHOTO_WIDTH
        and (not preferred_topic or c.topic == preferred_topic)
    ]
    if hero_pool:
        hero = await _download(client, hero_pool[0], dest_dir / "hero.jpg", tz)
        if hero is not None:
            used.add(hero_pool[0].message.id)
            used_topics.add(hero_pool[0].topic)
    # La copertina YouTube entra solo quando il gruppo non ha prodotto
    # nessuna immagine (vedi il ramo `not candidates` sopra): usarla qui
    # ricreerebbe lo stesso problema, un'immagine slegata dal titolo.

    # Ai pezzi va l'immagine del loro topic. Qui vanno bene anche le
    # miniature dei video: il layout le mostra come colonnino accanto al
    # testo, non a piena larghezza, quindi la sorgente piccola regge.
    by_topic: dict[str, Hero] = {}
    for candidate in ordered:
        if len(by_topic) >= max_article_photos:
            break
        # Una foto per topic: due immagini sotto lo stesso titolo non
        # raccontano il doppio, riempiono il doppio. E il topic
        # dell'apertura ha già la sua.
        if candidate.message.id in used:
            continue
        if not candidate.topic or candidate.topic in used_topics:
            continue
        picture = await _download(
            client, candidate, dest_dir / f"topic-{len(by_topic)}.jpg", tz
        )
        if picture is None:
            continue
        by_topic[candidate.topic] = picture
        used.add(candidate.message.id)
        used_topics.add(candidate.topic)

    # La fascia raccoglie il resto, comprese le miniature dei video: sono
    # piccole ma in una griglia da quattro reggono, e sono il grosso di
    # quello che il gruppo ha davvero pubblicato.
    strip: list[Hero] = []
    strip_topics: set[str] = set()
    for candidate in ordered:
        if len(strip) >= max_strip_photos:
            break
        if candidate.message.id in used:
            continue
        # Preferire topic diversi rende la fascia un riassunto della
        # giornata invece di quattro fotogrammi della stessa clip.
        if candidate.topic and candidate.topic in strip_topics:
            continue
        picture = await _download(
            client, candidate, dest_dir / f"strip-{len(strip)}.jpg", tz
        )
        if picture is None:
            continue
        strip.append(picture)
        used.add(candidate.message.id)
        strip_topics.add(candidate.topic)

    return DayPhotos(hero=hero, by_topic=by_topic, strip=strip)


async def _collect_candidates(
    client: TelegramClient,
    group_id: int,
    day: date,
    tz: ZoneInfo,
    preferred_topic: str,
) -> list[_Candidate]:
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
        visual = _visual_of(message)
        if visual is None:
            continue
        kind, width, height, thumb = visual
        # La soglia bassa è quella della fascia: chi vuole un'immagine a
        # tutta larghezza filtra dopo, con MIN_PHOTO_WIDTH.
        if width < MIN_STRIP_WIDTH:
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
            _Candidate(
                message=message,
                topic=topic,
                score=score,
                width=width,
                height=height,
                webpage=webpage,
                kind=kind,
                thumb=thumb,
            )
        )
    return candidates


def _caption_for(candidate: _Candidate, tz: ZoneInfo) -> str:
    when = candidate.message.date.astimezone(tz).strftime("%H:%M")
    where = f"topic {candidate.topic}" if candidate.topic else "gruppo"
    if candidate.webpage is not None:
        source = _source_name(candidate.webpage)
        if source:
            return f"Da {source} · link condiviso nel {where}, {when}"
        return f"Anteprima di un link condiviso nel {where} · {when}"
    if candidate.kind == "video":
        # Dire che è un fotogramma evita la domanda "e perché è mossa?":
        # una copertina di video non ha la nitidezza di uno scatto.
        return f"Fotogramma da un video nel {where} · {when}"
    return f"Foto dal {where} · {when}"


async def _download(
    client: TelegramClient, candidate: _Candidate, dest: Path, tz: ZoneInfo
) -> Hero | None:
    # Per i video si scarica la sola miniatura: il file intero pesa
    # decine di megabyte e di quel materiale ci serve un fotogramma.
    path = await client.download_media(
        candidate.message, file=str(dest), thumb=candidate.thumb
    )
    if not path:
        return None
    return Hero(
        path=path,
        caption=_caption_for(candidate, tz),
        width=candidate.width,
        height=candidate.height,
        label=candidate.topic or "Dal gruppo",
    )


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
        for template, width, height in _YT_THUMBS:
            dest = Path(dest_dir) / "hero.jpg"
            try:
                urllib.request.urlretrieve(template.format(vid=vid), dest)
            except Exception:
                continue  # maxresdefault non esiste per tutti i video
            return Hero(
                path=str(dest),
                caption=f"Dal video di ieri · {title}",
                width=width,
                height=height,
            )
    return None
