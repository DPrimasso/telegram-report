from telegram import Update
from telegram.ext import ContextTypes

from bot.registry import command


@command("start", description="Messaggio di benvenuto")
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Ciao! Scrivi /ping per una prova rapida, oppure /iscriviti se vuoi "
        "essere candidabile all'intervista settimanale."
    )


@command("ping", description="Prova di funzionamento")
async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("pong")
