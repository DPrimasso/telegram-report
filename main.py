import argparse
import asyncio
from datetime import date, datetime

from openai import OpenAI

from report.config import load_config
from report.fetch import fetch_day_messages
from report.report_builder import build_report
from report.send import send_report
from report.summarize import summarize_overall, summarize_topic
from report.telegram_client import build_client


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Genera e invia il gazzettino giornaliero del gruppo Telegram."
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Data da riepilogare in formato YYYY-MM-DD (default: oggi).",
    )
    return parser.parse_args()


async def run(target_date: date) -> None:
    config = load_config()
    client = build_client(config)
    openai_client = OpenAI(api_key=config.openai_api_key)

    async with client:
        topics = await fetch_day_messages(
            client, config.group_id, target_date, config.timezone
        )

        all_messages = [(t.title, m) for t in topics for m in t.messages]

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
                topic_summaries.append((topic.title, summary))

            print(f"Riassumo la giornata nel complesso ({len(all_messages)} messaggi)...")
            overall_summary = summarize_overall(
                openai_client, config.openai_model, all_messages
            )
            report_text = build_report(target_date, overall_summary, topic_summaries)

        print("Invio il report su Telegram...")
        await send_report(client, config, report_text)
        print("Fatto.")


def main() -> None:
    args = parse_args()
    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        target_date = date.today()
    asyncio.run(run(target_date))


if __name__ == "__main__":
    main()
