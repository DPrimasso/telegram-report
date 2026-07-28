"""
Script one-shot da eseguire in LOCALE per generare la StringSession di
Telethon e ottenere l'ID del gruppo Telegram.

Va eseguito una sola volta (o ogni volta che la sessione scade/viene
revocata). Richiede il numero di telefono dell'account e il codice di
accesso che Telegram invierà via messaggio.

La StringSession stampata a schermo va salvata come secret GitHub
TELEGRAM_SESSION: chi la possiede ha accesso completo al tuo account
Telegram, va trattata come una password e non va MAI committata nel repo.
"""

import asyncio
import os

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession

load_dotenv()


async def main() -> None:
    api_id_raw = os.environ.get("TELEGRAM_API_ID") or input(
        "API ID (da https://my.telegram.org): "
    ).strip()
    api_hash = os.environ.get("TELEGRAM_API_HASH") or input(
        "API Hash (da https://my.telegram.org): "
    ).strip()

    client = TelegramClient(StringSession(), int(api_id_raw), api_hash)
    await client.start()

    session_string = client.session.save()
    print("\n=== TELEGRAM_SESSION (salvala come secret, non condividerla) ===")
    print(session_string)
    print("=================================================================\n")

    print("Gruppi e canali disponibili (usa l'ID per TELEGRAM_GROUP_ID):\n")
    async for dialog in client.iter_dialogs():
        if dialog.is_group or dialog.is_channel:
            print(f"{dialog.id}\t{dialog.name}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
