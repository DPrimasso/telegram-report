import os
from dataclasses import dataclass

from dotenv import load_dotenv

from report import scribe

load_dotenv()


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Variabile d'ambiente mancante: {name}")
    return value


def _csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    """Lista separata da virgole, con ricaduta sul default. Serve per il
    nome del bot trascrittore e per i marcatori dei suoi riepiloghi: sono
    l'unica parte che dipende da come è configurato quel bot, e cambiarli
    non deve richiedere una modifica al codice."""
    raw = os.environ.get(name) or ""
    values = tuple(part.strip() for part in raw.split(",") if part.strip())
    return values or default


@dataclass(frozen=True)
class Config:
    api_id: int
    api_hash: str
    session: str
    group_id: int
    openai_api_key: str
    openai_model: str
    openai_image_model: str
    illustration_fallback: bool
    report_destination: str
    report_topic_id: int | None
    timezone: str
    newspaper_name: str | None
    youtube_channel_id: str
    logo_path: str
    scribe_names: tuple[str, ...]
    scribe_summary_markers: tuple[str, ...]


def load_config() -> Config:
    # os.environ.get(name, default) non basta: in GitHub Actions una env var
    # referenziata da una "vars" non impostata arriva come stringa vuota
    # (variabile presente ma vuota), non assente. Usiamo "or" per ricadere
    # sul default anche in quel caso.
    destination = os.environ.get("REPORT_DESTINATION") or ""
    topic_id = os.environ.get("REPORT_TOPIC_ID") or None
    group_id = int(_require("TELEGRAM_GROUP_ID"))

    # Un topic esiste solo dentro il suo gruppo: se REPORT_TOPIC_ID è
    # impostato, la destinazione è per forza quel gruppo. Ricavarla da sola
    # evita di far riscrivere l'ID del gruppo in una seconda variabile, dove
    # per giunta va nella forma marcata (-100...) e non in quella grezza che
    # compare nei link t.me. "group" resta accettato come alias esplicito.
    if not destination:
        destination = str(group_id) if topic_id else "me"
    elif destination == "group":
        destination = str(group_id)

    return Config(
        api_id=int(_require("TELEGRAM_API_ID")),
        api_hash=_require("TELEGRAM_API_HASH"),
        session=_require("TELEGRAM_SESSION"),
        group_id=group_id,
        openai_api_key=_require("OPENAI_API_KEY"),
        openai_model=os.environ.get("OPENAI_MODEL") or "gpt-4o-mini",
        openai_image_model=os.environ.get("OPENAI_IMAGE_MODEL") or "gpt-image-2",
        # Spenta di default: aggiunge un costo e una latenza al job
        # notturno, e l'apertura senza immagine è comunque una pagina
        # valida. Vedi docs/grafica.md.
        illustration_fallback=(os.environ.get("ILLUSTRATION_FALLBACK") or "").strip()
        in {"1", "true", "True", "si", "sì", "yes"},
        report_destination=destination,
        report_topic_id=int(topic_id) if topic_id else None,
        timezone=os.environ.get("REPORT_TIMEZONE") or "Europe/Rome",
        newspaper_name=os.environ.get("NEWSPAPER_NAME") or None,
        youtube_channel_id=os.environ.get("YOUTUBE_CHANNEL_ID") or "UCrXpaY2E4glX7Syy9xQiDIg",
        logo_path=os.environ.get("LOGO_PATH") or "assets/logo-azzurro.png",
        scribe_names=_csv("SCRIBE_BOT_NAMES", scribe.DEFAULT_BOT_NAMES),
        scribe_summary_markers=_csv(
            "SCRIBE_SUMMARY_MARKERS", scribe.DEFAULT_SUMMARY_MARKERS
        ),
    )
