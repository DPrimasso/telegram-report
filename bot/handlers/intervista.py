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
from datetime import date, datetime, timezone

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

# Il giorno in cui un invito senza risposta decade: 1-3 giorni dopo
# l'estrazione arriva un promemoria, al 4o l'intervista si chiude e ne
# viene estratta subito un'altra al posto di quella rimasta senza risposta.
GIORNI_PRIMA_DI_CHIUDERE = 4


def _settimana_corrente() -> str:
    anno, settimana, _ = date.today().isocalendar()
    return f"{anno}-W{settimana:02d}"


@command("iscriviti", description="Diventa candidabile per l'intervista settimanale")
async def iscriviti(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage: Storage = context.bot_data["storage"]
    utente = update.effective_user
    storage.registra_candidato(utente.id, update.effective_chat.id, utente.username)
    await update.message.reply_text(
        "Fatto: sei tra i candidabili. Ogni lunedì scelgo a caso una persona "
        "tra chi si è iscritto (evitando chi è già stato scelto di recente): "
        "se tocca a te, te lo scrivo qui e potrai rispondere quando vuoi con "
        "/intervista. Le interviste completate escono nell'inserto del "
        "gazzettino la domenica sera."
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

    indice += 1
    ultima = indice >= len(domande_lista)
    reazione = genera_reazione(nome, domanda_corrente, risposta_testo, ultima=ultima)

    if ultima:
        storage.aggiorna_stato_intervista(intervista_id, "completata")
        await update.message.reply_text(
            f"{reazione}\n\nGrazie mille per il tuo tempo, {nome}! La tua "
            "intervista uscirà nel prossimo inserto del gazzettino."
        )
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
            "rispondere a qualche domanda sulla tua settimana nel gruppo. Se "
            "rispondi entro domenica sera la tua intervista esce nell'inserto "
            "di questa settimana, altrimenti in quello della settimana dopo — "
            "nessuna fretta."
        ),
    )
    logger.info("Intervista settimanale proposta a user_id=%s (%s).", utente_id, username)
    return 1


async def sollecita_e_chiudi_scadute(bot: Bot, storage: Storage) -> tuple[int, int]:
    """Da chiamare una volta al giorno (endpoint /trigger/promemoria): manda
    un promemoria a chi ha un'intervista aperta da 1-3 giorni, e chiude
    quella ferma da 4 o piu' giorni — cancellandola del tutto, come se la
    persona non fosse mai stata estratta — estraendo subito un sostituto al
    suo posto. Ritorna (promemoria mandati, interviste chiuse)."""
    oggi = datetime.now(timezone.utc).date()
    promemoria = 0
    chiuse = 0

    for intervista_id, user_id, chat_id, nome, settimana, invitato_il in storage.interviste_aperte():
        giorni = (oggi - datetime.fromisoformat(invitato_il).date()).days

        if giorni >= GIORNI_PRIMA_DI_CHIUDERE:
            storage.annulla_intervista(intervista_id, user_id, settimana)
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=(
                        "Il tempo per rispondere all'intervista di questa "
                        "settimana è scaduto: nessun problema, magari alla "
                        "prossima occasione!"
                    ),
                )
            except Exception:
                logger.warning("Avviso di chiusura non recapitato a %s.", nome)
            chiuse += 1
            continue

        if giorni >= 1:
            giorni_rimasti = GIORNI_PRIMA_DI_CHIUDERE - giorni
            unita = "giorno" if giorni_rimasti == 1 else "giorni"
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"Ciao {nome}! Ti ricordo che questa settimana tocca "
                        "a te per l'intervista del gazzettino: scrivi "
                        "/intervista quando hai un attimo. Hai ancora "
                        f"{giorni_rimasti} {unita} prima che l'invito decada."
                    ),
                )
                promemoria += 1
            except Exception:
                logger.warning("Promemoria non recapitato a %s.", nome)

    if chiuse:
        await scegli_e_invita(bot, storage)

    return promemoria, chiuse
