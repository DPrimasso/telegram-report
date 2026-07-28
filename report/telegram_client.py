from telethon import TelegramClient
from telethon.sessions import StringSession

from report.config import Config


def build_client(config: Config) -> TelegramClient:
    return TelegramClient(
        StringSession(config.session), config.api_id, config.api_hash
    )
