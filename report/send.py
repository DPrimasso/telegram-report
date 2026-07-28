from telethon import TelegramClient

from report.config import Config

TELEGRAM_MESSAGE_LIMIT = 4000


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


async def send_report(client: TelegramClient, config: Config, text: str) -> None:
    if config.report_destination == "me":
        target = "me"
    else:
        target = int(config.report_destination)

    kwargs = {"parse_mode": "html"}
    if config.report_topic_id:
        kwargs["reply_to"] = config.report_topic_id

    for chunk in _split_message(text):
        await client.send_message(target, chunk, **kwargs)
