import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Variabile d'ambiente mancante: {name}")
    return value


@dataclass(frozen=True)
class BotConfig:
    bot_token: str
    # Vuoto = modalita' polling (comoda in locale). Valorizzato = webhook,
    # con questo come base pubblica del servizio (es. https://xxx.onrender.com).
    webhook_url: str | None
    # Verificato su ogni richiesta al webhook, per scartare chiamate contraffatte.
    webhook_secret: str | None
    port: int
    db_path: str
    # Protegge l'endpoint /trigger/intervista chiamato da GitHub Actions.
    trigger_secret: str | None


def load_bot_config() -> BotConfig:
    return BotConfig(
        bot_token=_require("TELEGRAM_BOT_TOKEN"),
        webhook_url=(os.environ.get("TELEGRAM_BOT_WEBHOOK_URL") or "").rstrip("/") or None,
        webhook_secret=os.environ.get("TELEGRAM_BOT_WEBHOOK_SECRET") or None,
        port=int(os.environ.get("PORT") or 8080),
        db_path=os.environ.get("BOT_DB_PATH") or "bot/data/bot.sqlite3",
        trigger_secret=os.environ.get("TELEGRAM_BOT_TRIGGER_SECRET") or None,
    )
