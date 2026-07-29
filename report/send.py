from telethon import TelegramClient
from telethon.errors import RPCError

from report.config import Config

TELEGRAM_MESSAGE_LIMIT = 4000

# Telegram rifiuta come foto le immagini troppo grandi o sproporzionate
# (limiti su lato massimo e su larghezza+altezza). Una prima pagina con molti
# articoli può superarli: in quel caso ripieghiamo sul documento invece di
# far fallire l'invio. Confrontiamo la stringa dell'errore invece di importare
# le singole classi, che cambiano nome tra le versioni di Telethon.
_PHOTO_REJECTION_HINTS = ("PHOTO_", "IMAGE_PROCESS_FAILED", "MEDIA_EMPTY")


def _split_message(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in text.split("\n"):
        if current and current_len + len(line) + 1 > limit:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += len(line) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks


def _resolve_target(config: Config):
    if config.report_destination == "me":
        return "me"
    return int(config.report_destination)


async def send_report(client: TelegramClient, config: Config, text: str) -> None:
    target = _resolve_target(config)

    kwargs = {"parse_mode": "html"}
    if config.report_topic_id:
        kwargs["reply_to"] = config.report_topic_id

    for chunk in _split_message(text):
        await client.send_message(target, chunk, **kwargs)


async def send_photo_report(
    client: TelegramClient, config: Config, image_paths: list[str], caption: str = ""
) -> None:
    """Invia le pagine del giornale come foto, così sono visibili in
    anteprima nella chat senza doverle scaricare. Con più pagine Telegram le
    raggruppa in un album, quindi arrivano come un unico blocco sfogliabile.
    Telegram ricomprime le foto: le pagine vanno renderizzate a risoluzione
    doppia (vedi newspaper.py) perché il testo resti leggibile."""
    target = _resolve_target(config)

    kwargs = {"parse_mode": "html"}
    if caption:
        # In un album la didascalia va sulla prima immagine: ripeterla su
        # ognuna la farebbe comparire più volte sotto il gruppo.
        kwargs["caption"] = [caption] + [""] * (len(image_paths) - 1)
    if config.report_topic_id:
        kwargs["reply_to"] = config.report_topic_id

    try:
        await client.send_file(target, image_paths, force_document=False, **kwargs)
    except RPCError as exc:
        detail = (getattr(exc, "message", "") or str(exc)).upper()
        if not any(hint in detail for hint in _PHOTO_REJECTION_HINTS):
            raise
        print(
            f"Telegram ha rifiutato l'invio come foto ({detail}): "
            "ripiego sull'invio come documento."
        )
        await client.send_file(target, image_paths, force_document=True, **kwargs)
