from telegram import Update
from telegram.ext import ContextTypes

from bot.registry import command


@command("start", description="Messaggio di benvenuto")
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Ciao! Sono il bot del gruppo.\n\n"
        "Ogni settimana scelgo a caso una persona tra chi si è iscritto e le "
        "faccio qualche domanda sulla sua settimana nel gruppo. Le risposte "
        "diventano l'inserto settimanale del gazzettino, nello stesso stile "
        "dell'edizione di tutti i giorni.\n\n"
        "Comandi:\n"
        "/iscriviti — entra tra i candidabili all'intervista\n"
        "/intervista — rispondi alle domande, solo se questa settimana è "
        "toccato a te\n"
        "/ping — prova rapida di funzionamento"
    )


@command("ping", description="Prova di funzionamento")
async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("pong")
