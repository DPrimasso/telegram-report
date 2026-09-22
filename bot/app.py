"""Entry point del bot a comandi (Bot API, separato dalla sessione utente
Telethon usata dal gazzettino). Modalita' polling in locale (comoda per lo
sviluppo), webhook in produzione su Render: il servizio "dorme" se inattivo,
e si risveglia alla prima richiesta HTTP in arrivo (dal webhook o dal
trigger settimanale dell'intervista).

Non si usa Application.run_webhook(): quello aprirebbe un server dedicato
solo alla rotta di Telegram, senza modo comodo di aggiungere l'endpoint
/trigger/intervista sullo stesso servizio. Si segue invece il pattern
"custom webhook" documentato da python-telegram-bot: un server ASGI
(Starlette + uvicorn) con piu' rotte, che smista gli update di Telegram
sulla coda della Application.
"""

import asyncio
import logging

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route
from telegram import Update
from telegram.ext import Application

from bot.config import BotConfig, load_bot_config
from bot.handlers import basics, intervista, report_commands  # noqa: F401 (side-effect: registrazione comandi)
from bot.registry import all_handlers
from bot.storage import Storage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WEBHOOK_PATH = "/telegram/webhook"
TRIGGER_PATH = "/trigger/intervista"


def build_application(config: BotConfig, storage: Storage) -> Application:
    application = Application.builder().token(config.bot_token).build()
    application.bot_data["storage"] = storage

    for handler in all_handlers():
        application.add_handler(handler)
    application.add_handler(intervista.intervista_conversation)

    return application


def create_starlette_app(
    application: Application, config: BotConfig, storage: Storage
) -> Starlette:
    async def telegram_webhook(request: Request) -> Response:
        if config.webhook_secret:
            header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
            if header != config.webhook_secret:
                return Response(status_code=401)
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.update_queue.put(update)
        return Response(status_code=200)

    async def trigger_intervista(request: Request) -> Response:
        if not config.trigger_secret:
            return Response(status_code=404)
        header = request.headers.get("X-Trigger-Secret")
        if header != config.trigger_secret:
            return Response(status_code=401)
        invitati = await intervista.scegli_e_invita(application.bot, storage)
        return PlainTextResponse(f"invitati: {invitati}")

    async def health(request: Request) -> Response:
        return PlainTextResponse("ok")

    return Starlette(
        routes=[
            Route(WEBHOOK_PATH, telegram_webhook, methods=["POST"]),
            Route(TRIGGER_PATH, trigger_intervista, methods=["POST"]),
            Route("/", health, methods=["GET"]),
        ]
    )


async def _run_webhook(application: Application, starlette_app: Starlette, config: BotConfig) -> None:
    import uvicorn

    async with application:
        await application.bot.set_webhook(
            url=f"{config.webhook_url}{WEBHOOK_PATH}",
            secret_token=config.webhook_secret,
        )
        await application.start()
        server = uvicorn.Server(
            uvicorn.Config(starlette_app, host="0.0.0.0", port=config.port, log_level="info")
        )
        try:
            await server.serve()
        finally:
            await application.stop()


def main() -> None:
    config = load_bot_config()
    storage = Storage(config.db_path)
    application = build_application(config, storage)

    if config.webhook_url:
        starlette_app = create_starlette_app(application, config, storage)
        asyncio.run(_run_webhook(application, starlette_app, config))
    else:
        logger.info("TELEGRAM_BOT_WEBHOOK_URL non impostata: avvio in polling.")
        application.run_polling()


if __name__ == "__main__":
    main()
