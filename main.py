import argparse
import asyncio
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from openai import OpenAI

from report.config import Config, load_config
from report.fetch import (
    SimpleMessage,
    TopicMessages,
    fetch_day_messages,
    get_group_title,
    list_topics,
)
from report.highlights import build_stats, hourly_counts, index_entries, pick_quote
from report.newspaper import Article, Lead, build_pages_html, render_html_to_png
from report.photo import pick_day_photos
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
        "--list-topics",
        action="store_true",
        help=(
            "Stampa l'elenco dei topic del gruppo con il relativo ID, poi "
            "esce senza chiamare OpenAI né inviare nulla. Serve a ricavare "
            "il valore da mettere in REPORT_TOPIC_ID."
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

    articles: list[Article] = []
    # Si scrive dal topic più attivo al meno attivo, e l'ordine conta: chi
    # ha discusso di più un argomento se lo tiene, mentre i topic che lo
    # hanno solo sfiorato lo riconoscono come già raccontato e si fermano
    # (vedi _avoid_repetition_rule). Scrivendo in ordine di topic_id la
    # notizia sarebbe finita a chi ne ha parlato meno. La lista esce quindi
    # già ordinata per rilevanza, come build_pages_html si aspetta.
    for topic in sorted(topics, key=lambda t: len(t.messages), reverse=True):
        if not topic.messages:
            continue
        print(f"Scrivo l'articolo per '{topic.title}' ({len(topic.messages)} messaggi)...")
        headline, body = write_topic_article(
            openai_client,
            config.openai_model,
            topic.title,
            topic.messages,
            written_so_far=[(a.headline, a.body) for a in articles],
        )
        if not headline:
            print(f"  '{topic.title}': stesso fatto di un pezzo già in pagina, non lo ripeto.")
            continue
        articles.append(
            Article(topic=topic.title, headline=headline, body=body, count=len(topic.messages))
        )

    print("Scrivo l'articolo di apertura...")
    lead_headline, lead_deck, lead_paragraphs = write_lead_story(
        openai_client,
        config.openai_model,
        all_messages,
        page_headlines=[a.headline for a in articles],
    )
    # L'apertura non è un topic: il kicker prende il topic più attivo, che è
    # quello da cui la giornata è stata trascinata.
    lead_topic = articles[0].topic if articles else ""
    lead = Lead(
        kicker=lead_topic,
        headline=lead_headline,
        deck=lead_deck,
        paragraphs=lead_paragraphs,
    )

    print("Scelgo la frase del giorno...")
    quote = pick_quote(openai_client, config.openai_model, all_messages)

    print("Recupero il nome del gruppo per la testata...")
    newspaper_name = config.newspaper_name or await get_group_title(client, config.group_id)

    with tempfile.TemporaryDirectory() as tmp_dir:
        print("Cerco le foto della giornata...")
        photos = await pick_day_photos(
            client,
            config.group_id,
            target_date,
            config.timezone,
            tmp_dir,
            preferred_topic=lead_topic,
            youtube_channel_id=config.youtube_channel_id,
        )
        hero = photos.hero
        # Le foto dei pezzi si assegnano per topic: se quel topic non ne
        # ha una, l'articolo resta di solo testo, che è il caso normale.
        for article in articles:
            article.picture = photos.by_topic.get(article.topic)
        if photos.by_topic:
            print("Foto anche per: " + ", ".join(sorted(photos.by_topic)))
        if photos.strip:
            print(f"Fascia di chiusura: {len(photos.strip)} immagini.")
        if hero is None and not photos.by_topic and not photos.strip:
            print("Nessuna immagine utilizzabile: edizione tipografica.")

        logo = Path(config.logo_path)
        pages_html = build_pages_html(
            newspaper_name,
            target_date,
            lead,
            articles,
            logo_path=logo if logo.exists() else None,
            hero=hero,
            index_entries=index_entries(topics),
            stats=build_stats(all_messages),
            quote=quote,
            hourly=hourly_counts(all_messages),
            strip=photos.strip,
        )

        print(f"Genero le immagini del giornale ({len(pages_html)} pagine)...")
        image_paths = []
        for number, page_html in enumerate(pages_html, start=1):
            image_path = str(Path(tmp_dir) / f"pagina_{number}.png")
            await render_html_to_png(page_html, image_path)
            image_paths.append(image_path)

        print("Invio il giornale su Telegram...")
        caption = f"📰 {newspaper_name} — {target_date.strftime('%d/%m/%Y')}"
        await send_photo_report(client, config, image_paths, caption=caption)

    print("Fatto.")


async def _run_list_topics(client, config: Config) -> None:
    topics = await list_topics(client, config.group_id)
    print("\nID\tTopic  (usa l'ID come REPORT_TOPIC_ID)\n")
    for topic_id, title in topics:
        print(f"{topic_id}\t{title}")
    print(
        "\nImposta REPORT_TOPIC_ID con l'ID scelto: la destinazione diventa "
        "automaticamente il gruppo che contiene il topic."
    )


async def run(
    target_date: date | None,
    debug: bool = False,
    dump_topic: str | None = None,
    report_format: str = "newspaper",
    list_topics_only: bool = False,
) -> None:
    config = load_config()
    client = build_client(config)

    if list_topics_only:
        async with client:
            await _run_list_topics(client, config)
        return

    openai_client = OpenAI(api_key=config.openai_api_key)

    if target_date is None:
        # Senza --date si riassume il giorno precedente nel fuso orario
        # configurato, così il lancio notturno copre la giornata conclusa.
        now = datetime.now(ZoneInfo(config.timezone))
        target_date = (now - timedelta(days=1)).date()
        print(f"Nessuna data indicata: riepilogo il {target_date.isoformat()}.")

    async with client:
        topics = await fetch_day_messages(
            client,
            config.group_id,
            target_date,
            config.timezone,
            debug=debug,
            scribe_names=config.scribe_names,
            summary_markers=config.scribe_summary_markers,
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
            list_topics_only=args.list_topics,
        )
    )


if __name__ == "__main__":
    main()
