from datetime import date


def build_report(
    day: date,
    overall_summary: str | None,
    topic_summaries: list[tuple[str, str]],
) -> str:
    header = f"<b>📰 Gazzettino del {day.strftime('%d/%m/%Y')}</b>"

    if overall_summary is None:
        return f"{header}\n\nNessun messaggio scambiato oggi nel gruppo."

    lines = [header, "", "<b>📋 Riepilogo generale della giornata</b>", overall_summary]

    for title, summary in topic_summaries:
        if not summary:
            continue
        lines.append("")
        lines.append(f"<b>🗂 {title}</b>")
        lines.append(summary)

    return "\n".join(lines).strip()
