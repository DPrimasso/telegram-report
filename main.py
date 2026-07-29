import argparse
import asyncio
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from openai import OpenAI

from report.config import Config, load_config
from report.fetch import SimpleMessage, TopicMessages, fetch_day_messages, get_group_title
from report.newspaper import build_front_page_html, render_html_to_png
from report.report_builder import build_report
from report.send import send_photo_report, send_report
from report.summarize import (
    summarize_overall,
    summarize_topic,
    write_lead_story,
    write_topic_article,
)
from report.telegram_client import build_client


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Genera e invia il gazzettino giornaliero del gruppo Telegram."
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Data da riepilogare in formato YYYY-MM-DD (default: ieri).",
    )
    parser.add_argument(
        "--format",
        choices=["newspaper", "text"],
        default="newspaper",
        help=(
            "Formato del report: 'newspaper' (default) genera una prima "
            "pagina in stile giornale come immagine; 'text' genera il "
            "messaggio testuale con elenchi puntati."
        ),
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help=(
            "Stampa a schermo i dettagli (reply_to grezzo) di ogni messaggio "
            "finito nel topic General, per diagnosticare classificazioni "
            "errate."
        ),
    )
    parser.add_argument(
        "--dump-topic",
        type=str,
        default=None,
        help=(
            "Stampa i messaggi grezzi (non riassunti) di ogni topic il cui "
            "titolo contiene questa stringa, poi esce senza chiamare OpenAI "
            "né inviare nulla. Utile per confrontare 1:1 con Telegram cosa "
            "è stato effettivamente assegnato a un topic."
        ),
    )
    return parser.parse_args()


def _dump_topic(topics: list[TopicMessages], needle: str) -> None:
    needle = needle.lower()
    matches = [t for t in topics if needle in t.title.lower()]
    if not matches:
        print(f"Nessun topic trovato con titolo contenente {needle!r}.")
    for topic in matches:
        print(
            f"\n=== Topic '{topic.title}' (id={topic.topic_id}, "
            f"{len(topic.messages)} messaggi) ==="
        )
        for m in topic.messages:
            print(f"[{m.timestamp:%H:%M}] {m.author}: {m.text}")


async def _run_text_report(
    client,
    config: Config,
    openai_client: OpenAI,
    target_date: date,
    topics: list[TopicMessages],
    all_messages: list[tuple[str, SimpleMessage]],
) -> None:
    if not all_messages:
        print(f"Nessun messaggio trovato per il {target_date.isoformat()}.")
        report_text = build_report(target_date, None, [])
    else:
        topic_summaries = []
        for topic in topics:
            if not topic.messages:
                continue
            print(
                f"Riassumo il topic '{topic.title}' "
                f"({len(topic.messages)} messaggi)..."
            )
            summary = summarize_topic(
                openai_client, config.openai_model, topic.title, topic.messages
            )
            topic_summaries.append((topic.title, len(topic.messages), summary))

        print("Individuo i punti salienti trasversali della giornata...")
        general_summary = summarize_overall(
            openai_client, config.openai_model, all_messages
        )

        report_text = build_report(target_date, general_summary, topic_summaries)

    print("Invio il report su Telegram...")
    await send_report(client, config, report_text)
    print("Fatto.")


async def _run_newspaper_report(
    client,
    config: Config,
    openai_client: OpenAI,
    target_date: date,
    topics: list[TopicMessages],
    all_messages: list[tuple[str, SimpleMessage]],
) -> None:
    if not all_messages:
        print(f"Nessun messaggio trovato per il {target_date.isoformat()}.")
        report_text = build_report(target_date, None, [])
        await send_report(client, config, report_text)
        print("Fatto.")
        return

    articles: list[tuple[str, str, int]] = []
    for topic in topics:
        if not topic.messages:
            continue
        print(
            f"Scrivo l'articolo per '{topic.title}' "
            f"({len(topic.messages)} messaggi)..."
        )
        headline, body = write_topic_article(
            openai_client,
            config.openai_model,
            topic.title,
            topic.messages,
            # Ogni pezzo vede quelli già scritti, così non ne ricalca
            # titoli e attacchi: le chiamate sono altrimenti indipendenti.
            written_so_far=[(h, b) for h, b, _ in articles],
        )
        articles.append((headline, body, len(topic.messages)))
    articles.sort(key=lambda item: item[2], reverse=True)

    print("Scrivo l'articolo di apertura...")
    lead_headline, lead_deck, lead_paragraphs = write_lead_story(
        openai_client,
        config.openai_model,
        all_messages,
        page_headlines=[h for h, _, _ in articles],
    )

    print("Recupero il nome del gruppo per la testata...")
    newspaper_name = config.newspaper_name or await get_group_title(
        client, config.group_id
    )

    html_content = build_front_page_html(
        newspaper_name,
        target_date,
        lead_headline,
        lead_deck,
        lead_paragraphs,
        articles,
    )

    print("Genero l'immagine della prima pagina...")
    with tempfile.TemporaryDirectory() as tmp_dir:
        image_path = str(Path(tmp_dir) / "prima_pagina.png")
        await render_html_to_png(html_content, image_path)

        print("Invio la prima pagina su Telegram...")
        caption = f"📰 {newspaper_name} — {target_date.strftime('%d/%m/%Y')}"
        await send_photo_report(client, config, image_path, caption=caption)

    print("Fatto.")


async def run(
    target_date: date | None,
    debug: bool = False,
    dump_topic: str | None = None,
    report_format: str = "newspaper",
) -> None:
    config = load_config()
    client = build_client(config)
    openai_client = OpenAI(api_key=config.openai_api_key)

    if target_date is None:
        # Senza --date si riassume il giorno precedente nel fuso orario
        # configurato, così il lancio notturno copre la giornata conclusa.
        now = datetime.now(ZoneInfo(config.timezone))
        target_date = (now - timedelta(days=1)).date()
        print(f"Nessuna data indicata: riepilogo il {target_date.isoformat()}.")

    async with client:
        topics = await fetch_day_messages(
            client, config.group_id, target_date, config.timezone, debug=debug
        )

        if dump_topic:
            _dump_topic(topics, dump_topic)
            return

        all_messages = [(t.title, m) for t in topics for m in t.messages]

        if report_format == "text":
            await _run_text_report(
                client, config, openai_client, target_date, topics, all_messages
            )
        else:
            await _run_newspaper_report(
                client, config, openai_client, target_date, topics, all_messages
            )


def main() -> None:
    args = parse_args()
    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        target_date = None
    asyncio.run(
        run(
            target_date,
            debug=args.debug,
            dump_topic=args.dump_topic,
            report_format=args.format,
        )
    )


if __name__ == "__main__":
    main()
