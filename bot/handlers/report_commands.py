"""Punto di estensione per comandi che richiamano la pipeline del gazzettino.

Non ancora implementato: quando ci sara' un comando reale (es. un report
"su richiesta"), potra' riusare esattamente quello che main.py fa gia' oggi,
con lo stesso client Telethon a sessione utente (necessario per leggere la
cronologia del gruppo, cosa che un bot con la Bot API non puo' fare):

    from report.config import load_config
    from report.telegram_client import build_client
    from report.fetch import fetch_day_messages
    from report.report_builder import build_report

    config = load_config()
    client = build_client(config)
    async with client:
        messaggi = await fetch_day_messages(client, config, ...)
        testo = build_report(messaggi, ...)
"""

from telegram import Update
from telegram.ext import ContextTypes

from bot.registry import command


@command("report", description="Genera il report su richiesta (non ancora implementato)")
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Comando non ancora implementato.")
