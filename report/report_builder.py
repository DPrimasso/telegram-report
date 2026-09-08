import html
import re
from datetime import date, timedelta

SEPARATOR = "─" * 20

# Pulizia difensiva: anche col prompt che chiede solo elenchi puntati in
# testo semplice, i modelli a volte lasciano residui di markdown
# (**grassetto**, ### intestazioni, liste numerate "1."). Telegram in
# modalità HTML non li interpreta: comparirebbero come testo grezzo.
_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
_HEADER_RE = re.compile(r"^\s*#{1,6}\s*")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def _clean_line(raw_line: str) -> str | None:
    line = _HEADER_RE.sub("", raw_line)
    line = _BOLD_RE.sub(r"\1", line)
    line = line.strip()
    if not line:
        return None
    line = _BULLET_RE.sub("", line).strip()
    if not line:
        return None
    return html.escape(line)


def format_summary_html(text: str) -> str:
    if not text:
        return ""
    lines = [cleaned for raw in text.splitlines() if (cleaned := _clean_line(raw))]
    return "\n".join(f"• {line}" for line in lines)


def _section_header(text: str) -> str:
    return f"<b>{html.escape(text)}</b>"


def build_report(
    day: date,
    general_summary: str | None,
    topic_summaries: list[tuple[str, int, str]],
) -> str:
    """Il riepilogo in testo semplice, il formato di ripiego.

    `day` è il giorno raccontato, come per il resto della pipeline. In
    intestazione però ci vanno tutte e due le date, come nel giornale: la
    data di uscita, perché un'edizione si data con l'edizione, e il
    giorno raccontato, perché qui — a differenza delle pagine — non ci
    sono rubriche a dirlo, e senza sparirebbe. Due convenzioni diverse
    fra i due formati sarebbero il modo più rapido di rendere la data
    inaffidabile in tutti e due."""
    from report.newspaper import giorno_e_mese

    uscita = day + timedelta(days=1)
    lines = [
        _section_header(
            f"📰 Gazzettino del {uscita.strftime('%d/%m/%Y')}"
            f" — la giornata di {giorno_e_mese(day)}"
        )
    ]

    if general_summary is None:
        lines.append("")
        lines.append("Nessun messaggio scambiato oggi nel gruppo.")
        return "\n".join(lines)

    if general_summary:
        lines.append("")
        lines.append(SEPARATOR)
        lines.append(_section_header("📌 In evidenza"))
        lines.append(format_summary_html(general_summary))

    active_topics = [(t, c, s) for t, c, s in topic_summaries if s]
    if active_topics:
        active_topics.sort(key=lambda item: item[1], reverse=True)
        lines.append("")
        lines.append(SEPARATOR)
        lines.append(_section_header("🗂 Dettaglio per topic"))
        for topic_title, count, summary in active_topics:
            lines.append("")
            count_label = "messaggio" if count == 1 else "messaggi"
            lines.append(
                f"<b>▸ {html.escape(topic_title)}</b>"
                f" <i>({count} {count_label})</i>"
            )
            lines.append(format_summary_html(summary))

    return "\n".join(lines).strip()
