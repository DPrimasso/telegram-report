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
from report.highlights import (
    build_stats,
    hourly_counts,
    pick_quote,
    section_entries,
)
from report.newspaper import (
    Article,
    Lead,
    build_pages_html,
    render_html_to_png,
    topics_needing_body,
)
from report.summarize import campione_citabile, istogramma_lunghezze
from report.vignetta import (
    DESCRIZIONI,
    Biblioteca,
    componi,
    leggi_battute,
    pick_vignetta,
)
from report.report_builder import build_report
from report.sections import load_section_map
from report.send import send_photo_report, send_report
from report.summarize import (
    summarize_overall,
    write_brief_headlines,
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

    section_map = load_section_map()

    attivi = [t for t in topics if t.messages]
    # Come è fatta la giornata, prima di spendere un token. Serve a
    # tarare la soglia sotto cui un messaggio non porta fatti, e ad
    # accorgersi se il gruppo cambia abitudini.
    print(istogramma_lunghezze([m for _, m in all_messages]))

    # Chi merita un pezzo per esteso si decide PRIMA di scriverlo. In
    # pagina i pezzi pieni sono cinque più i blocchi di famiglia, e tutto
    # il resto esce come una riga di titolo: scrivere quattordici articoli
    # interi per pubblicarne cinque significava pagare nove volte
    # milleottocento token di regole per mostrare otto parole.
    con_corpo = topics_needing_body(
        [
            (t.title, len(t.messages), section_map.family_of(t.title))
            for t in attivi
        ]
    )

    articles: list[Article] = []

    def aggiungi(titolo: str, headline: str, deck: str, body: str, quote, n: int) -> None:
        articles.append(
            Article(
                topic=titolo,
                headline=headline,
                deck=deck,
                body=body,
                count=n,
                section=section_map.section_of(titolo),
                family=section_map.family_of(titolo),
                quote=quote,
            )
        )

    # Si scrive dal topic più attivo al meno attivo, e l'ordine conta: chi
    # ha discusso di più un argomento se lo tiene, mentre i topic che lo
    # hanno solo sfiorato lo riconoscono come già raccontato e si fermano
    # (vedi _avoid_repetition_rule). Scrivendo in ordine di topic_id la
    # notizia sarebbe finita a chi ne ha parlato meno. La lista esce quindi
    # già ordinata per volume: l'ordine con cui i pezzi si LEGGONO lo
    # decide poi arrange_sections, che è un'altra cosa.
    ordinati = sorted(attivi, key=lambda t: len(t.messages), reverse=True)
    for topic in ordinati:
        if topic.title not in con_corpo:
            continue
        print(f"Scrivo l'articolo per '{topic.title}' ({len(topic.messages)} messaggi)...")
        headline, deck, body, virgolettato = write_topic_article(
            openai_client,
            config.openai_model,
            topic.title,
            topic.messages,
            written_so_far=[(a.headline, a.body) for a in articles],
        )
        if not headline:
            print(f"  '{topic.title}': stesso fatto di un pezzo già in pagina, non lo ripeto.")
            continue
        aggiungi(topic.title, headline, deck, body, virgolettato, len(topic.messages))

    # I topic minori, tutti insieme in una chiamata sola.
    minori = [t for t in ordinati if t.title not in con_corpo]
    if minori:
        print(f"Scrivo i titoli delle brevi ({len(minori)} temi) in una chiamata...")
        titoli = write_brief_headlines(
            openai_client,
            config.openai_model,
            [(t.title, t.messages) for t in minori],
            written_so_far=[(a.headline, a.body) for a in articles],
        )
        for topic in minori:
            headline = titoli.get(topic.title)
            if headline:
                aggiungi(topic.title, headline, "", "", None, len(topic.messages))

    print("Scrivo l'articolo di apertura...")
    # L'occhiello dell'apertura lo sceglie chi scrive il pezzo, fra le
    # sezioni davvero attive oggi: prima lo decideva il codice prendendo
    # il topic più attivo, che è un'altra cosa — la notizia di apertura
    # poteva arrivare da un'altra parte, e l'occhiello annunciava un
    # argomento diverso da quello del titolo sotto. Sono le sezioni e non
    # i topic perché è il vocabolario che il lettore trova nelle testate
    # più in basso: l'apertura deve nominare le stesse cose.
    sections = section_entries(topics, section_map)

    biblioteca = Biblioteca(config.vignette_dir)
    (
        lead_headline,
        lead_deck,
        lead_paragraphs,
        lead_section,
        lead_quote,
        lead_tono,
        lead_battute,
    ) = write_lead_story(
        openai_client,
        config.openai_model,
        all_messages,
        page_headlines=[a.headline for a in articles],
        sections=[name for name, _ in sections],
        # L'apertura legge i pezzi delle pagine interne invece di
        # rileggersi la giornata: sono gli stessi fatti, già scelti e già
        # scritti, e costano un ventesimo.
        articoli=[
            (a.topic, a.headline, a.deck, a.body, a.count) for a in articles
        ],
        # La vignetta esce da questa stessa chiamata: è la stessa testa
        # che sceglie il fatto del giorno e le due frasi che lo
        # raccontano. Senza disegni in biblioteca non si chiede nemmeno.
        toni=[(t, DESCRIZIONI[t]) for t in biblioteca.toni] if biblioteca else None,
    )
    lead = Lead(
        kicker=lead_section,
        headline=lead_headline,
        deck=lead_deck,
        paragraphs=lead_paragraphs,
        quote=lead_quote,
    )

    # La vignetta e la frase del giorno sono lo stesso elemento in due
    # forme, e ne esce una sola: si prova prima la vignetta, che dice di
    # più, e si ripiega sulla frase quando non si può fare — biblioteca
    # vuota, nessuno scambio adatto, una battuta che non combacia con
    # nessun messaggio. La frase costa una chiamata, quindi si chiede
    # solo se serve davvero.
    #
    # La vignetta sta in prima pagina accanto all'apertura, quindi deve
    # raccontare quel fatto: i topic della sezione da cui l'apertura
    # arriva sono il recinto entro cui le battute possono essere scelte.
    # Quando l'apertura è trasversale il recinto non c'è, ed è giusto
    # così: il fatto non appartiene a una sezione sola.
    topic_apertura = {
        t.title for t in topics if section_map.section_of(t.title) == lead_section
    } if lead_section else set()

    vignetta = None
    if biblioteca:
        # Prima strada: tono e battute sono già arrivati con l'apertura.
        # Le verifiche sono le stesse — tono esistente in biblioteca,
        # battuta presente alla lettera, due autori diversi — perché è la
        # stessa funzione, con due ingressi.
        if lead_tono and lead_battute:
            tono, battute = leggi_battute(lead_tono, lead_battute, biblioteca.toni)
            vignetta = componi(
                tono,
                battute,
                campione_citabile(all_messages, 10_000, minimo=20, massimo=110),
                target_date,
                biblioteca,
            )
        # Ripiego: se l'apertura non l'ha prodotta, o se le battute non
        # hanno superato la verifica, si torna alla chiamata dedicata.
        if vignetta is None:
            print("Compongo la vignetta del giorno con una chiamata a parte...")
            vignetta = pick_vignetta(
                openai_client,
                config.openai_model,
                all_messages,
                tema=f"{lead.headline} — {lead.deck}",
                giorno=target_date,
                topic_sezione=topic_apertura,
                biblioteca=biblioteca,
            )
        if vignetta:
            print(f"  tono {vignetta.tone}, disegno {vignetta.image_path}")

    quote = None
    if vignetta is None:
        print("Scelgo la frase del giorno...")
        quote = pick_quote(openai_client, config.openai_model, all_messages)

    print("Recupero il nome del gruppo per la testata...")
    newspaper_name = config.newspaper_name or await get_group_title(client, config.group_id)

    with tempfile.TemporaryDirectory() as tmp_dir:
        logo = Path(config.logo_path)
        pages_html = build_pages_html(
            newspaper_name,
            target_date,
            lead,
            articles,
            logo_path=logo if logo.exists() else None,
            index_entries=sections,
            stats=build_stats(all_messages),
            quote=quote,
            vignetta=vignetta,
            hourly=hourly_counts(all_messages),
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
