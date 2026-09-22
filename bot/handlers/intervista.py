"""Intervista settimanale: registrazione dei candidabili, estrazione e invito
proattivo (chiamati dall'endpoint /trigger/intervista), e il flusso guidato
delle domande una volta che la persona scelta scrive /intervista.

Le domande vengono generate e salvate una volta sola al momento
dell'estrazione (vedi bot/domande.py: un'intervista intera con un tono da
vera intervista, grounded sulle conversazioni della settimana quando
disponibili). Durante la chat, dopo ogni risposta il "giornalista" reagisce
con una riga breve prima della domanda successiva, per dare all'intervista
un ritmo di conversazione invece che di questionario. Le risposte restano
solo salvate (tabella `risposte`), pronte per essere lette da chi
comporra' l'inserto settimanale.
"""

import logging
import random
from datetime import date

from telegram import Bot, Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.domande import genera_domande, genera_reazione
from bot.registry import command
from bot.storage import Storage

logger = logging.getLogger(__name__)

IN_DOMANDA = 1


def _settimana_corrente() -> str:
    anno, settimana, _ = date.today().isocalendar()
    return f"{anno}-W{settimana:02d}"


@command("iscriviti", description="Diventa candidabile per l'intervista settimanale")
async def iscriviti(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage: Storage = context.bot_data["storage"]
    utente = update.effective_user
    storage.registra_candidato(utente.id, update.effective_chat.id, utente.username)
    await update.message.reply_text(
        "Fatto: sei tra i candidabili per l'intervista settimanale."
    )


async def avvia_intervista(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    storage: Storage = context.bot_data["storage"]
    utente_id = update.effective_user.id
    aperta = storage.intervista_aperta_per(utente_id)
    if not aperta:
        await update.message.reply_text(
            "Non risulta nessuna intervista in attesa per te questa settimana."
        )
        return ConversationHandler.END

    intervista_id, _stato, nome = aperta
    domande_lista = storage.carica_domande(intervista_id)
    if not domande_lista:
        # Non dovrebbe succedere (scegli_e_invita ne salva sempre almeno
        # di riserva), ma senza domande non c'e' nulla da chiedere.
        await update.message.reply_text(
            "Non ho domande pronte per te: avvisa chi gestisce il bot."
        )
        return ConversationHandler.END

    context.user_data["intervista_id"] = intervista_id
    context.user_data["nome"] = nome
    context.user_data["domande"] = domande_lista
    context.user_data["indice_domanda"] = 0
    storage.aggiorna_stato_intervista(intervista_id, "in corso")
    await update.message.reply_text(f"Grazie per il tuo tempo, {nome}! Iniziamo:\n\n{domande_lista[0]}")
    return IN_DOMANDA


async def ricevi_risposta(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    storage: Storage = context.bot_data["storage"]
    intervista_id = context.user_data["intervista_id"]
    nome = context.user_data["nome"]
    domande_lista = context.user_data["domande"]
    indice = context.user_data["indice_domanda"]
    domanda_corrente = domande_lista[indice]
    risposta_testo = update.message.text
    storage.salva_risposta(intervista_id, indice, domanda_corrente, risposta_testo)

    reazione = genera_reazione(nome, domanda_corrente, risposta_testo)

    indice += 1
    if indice >= len(domande_lista):
        storage.aggiorna_stato_intervista(intervista_id, "completata")
        await update.message.reply_text(f"{reazione}\n\nGrazie mille per il tuo tempo, {nome}!")
        return ConversationHandler.END

    context.user_data["indice_domanda"] = indice
    await update.message.reply_text(f"{reazione}\n\n{domande_lista[indice]}")
    return IN_DOMANDA


intervista_conversation = ConversationHandler(
    entry_points=[CommandHandler("intervista", avvia_intervista)],
    states={
        IN_DOMANDA: [MessageHandler(filters.TEXT & ~filters.COMMAND, ricevi_risposta)],
    },
    fallbacks=[],
)


async def scegli_e_invita(bot: Bot, storage: Storage) -> int:
    """Sceglie un candidato non estratto di recente, apre una nuova intervista
    e gli manda l'invito. Richiamata dall'endpoint /trigger/intervista.
    Ritorna il numero di persone invitate (0 o 1)."""
    settimana = _settimana_corrente()

    esclusi = storage.gia_estratti_recentemente()
    disponibili = storage.candidati_disponibili(esclusi)
    if not disponibili:
        logger.warning("Nessun candidato disponibile per l'intervista di %s.", settimana)
        return 0

    utente_id, chat_id, username = random.choice(disponibili)

    nome = username or f"utente {utente_id}"
    try:
        chat = await bot.get_chat(chat_id)
        nome = chat.first_name or nome
    except Exception:
        pass

    storage.registra_estrazione(settimana, utente_id)
    intervista_id = storage.apri_intervista(utente_id, settimana, nome)

    domande_lista = await genera_domande(nome, utente_id)
    storage.salva_domande(intervista_id, domande_lista)

    await bot.send_message(
        chat_id=chat_id,
        text=(
            "Questa settimana tocca a te! Quando vuoi, scrivi /intervista per "
            "rispondere a qualche domanda per l'inserto settimanale."
        ),
    )
    logger.info("Intervista settimanale proposta a user_id=%s (%s).", utente_id, username)
    return 1
