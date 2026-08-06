"""Prova di illustrazione generata: la fa, e la mostra dove andrebbe.

Un'immagine generata non si giudica guardandola da sola — si giudica
nello slot in cui finisce, dopo il trattamento cromatico, accanto al
resto della pagina. Questo script fa entrambe le cose: genera N varianti
per un titolo e le mette a confronto grezze e trattate, e su richiesta
compone la prima pagina vera con la prima variante al posto della foto.

    python illustrazione.py                          # titolo di esempio, 3 varianti
    python illustrazione.py --titolo "..." --n 1     # un titolo tuo
    python illustrazione.py --pagina                 # anche la prima pagina completa
    python illustrazione.py --qualita low            # bozze rapide e piu' economiche

Serve OPENAI_API_KEY (le stesse variabili del gazzettino, lette da .env).
Ogni variante e' una chiamata al modello di immagini e si paga: lo script
stampa quante ne sta per fare prima di partire.
"""

import argparse
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from preview import (
    SAMPLE_ARTICLES,
    SAMPLE_DATE,
    SAMPLE_HOURS,
    SAMPLE_INDEX,
    SAMPLE_LEAD,
    SAMPLE_QUOTE,
    SAMPLE_STATS,
)
from report.illustration import (
    ART_DIRECTION,
    CAPTION,
    DEFAULT_SIZE,
    build_prompt,
    describe_subject,
    generate_image,
)
from report.newspaper import (
    AZZURRO_DEEP,
    AZZURRO_PALE,
    GROUND,
    INK,
    NAVY,
    PAGE_WIDTH,
    GraphicsOptions,
    Hero,
    build_pages_html,
    data_uri,
    render_html_to_png,
)
from report.graphics import DUOTONE_FILTER

SHEET_CSS = f"""
* {{ box-sizing: border-box; }}
body {{
  margin: 0; width: {PAGE_WIDTH}px; background: {GROUND}; color: {INK};
  font-family: Archivo, 'Helvetica Neue', Arial, sans-serif;
}}
h1, h2 {{ margin: 0; font-weight: 800; letter-spacing: -0.025em; }}
p {{ margin: 0; }}
.head {{ background: {NAVY}; color: #fff; padding: 34px 56px 30px 56px; }}
.head h1 {{ font-size: 42px; }}
.head p {{ color: {AZZURRO_PALE}; font-size: 18px; margin-top: 12px; line-height: 1.5; }}
.head .subject {{ color: #fff; font-weight: 700; }}
.variant {{ padding: 30px 56px; border-bottom: 2px solid {NAVY}; background: #fff; }}
.variant:nth-child(even) {{ background: {GROUND}; }}
.variant h2 {{ font-size: 26px; margin-bottom: 6px; }}
.variant .subject {{ font-size: 18px; color: #3d3d3d; line-height: 1.45; margin-bottom: 18px; }}
.trio {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }}
.shot {{ height: 190px; overflow: hidden; border: 2px solid {NAVY}; }}
.shot img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
.shot.mono img {{ filter: grayscale(1) contrast(1.08); }}
.shot.duotone img {{ filter: url(#duotone) contrast(1.04); }}
.shot.duotone-soft img {{ filter: url(#duotone-soft) contrast(1.04); }}
.label {{
  font-size: 14px; font-weight: 800; letter-spacing: 0.12em;
  text-transform: uppercase; color: {AZZURRO_DEEP}; margin-top: 10px;
}}
.note {{ padding: 26px 56px; background: {NAVY}; color: {AZZURRO_PALE}; font-size: 17px; line-height: 1.5; }}
"""


def _sheet_html(headline: str, variants: list[tuple[str, str]]) -> str:
    blocks = []
    for i, (subject, path) in enumerate(variants, start=1):
        uri = data_uri(path)
        shots = "".join(
            f'<div><div class="shot {cls}"><img src="{uri}" alt=""></div>'
            f'<div class="label">{label}</div></div>'
            for cls, label in (
                ("raw", "Come esce dal modello"),
                ("duotone-soft", "Bicromia morbida (in pagina)"),
                ("duotone", "Bicromia piena"),
            )
        )
        blocks.append(
            f'<div class="variant"><h2>Variante {i}</h2>'
            f'<p class="subject">Soggetto chiesto al generatore: <b>{subject}</b></p>'
            f'<div class="trio">{shots}</div></div>'
        )

    return f"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;600;800&display=swap" rel="stylesheet">
<style>{SHEET_CSS}</style>
</head>
<body>
{DUOTONE_FILTER}
<div class="head">
  <h1>Prova di illustrazione generata</h1>
  <p>Titolo di partenza: <span class="subject">{headline}</span></p>
  <p>Lo stile non dipende dalla notizia: e' bloccato in una costante, uguale ogni
  giorno. Dalla notizia arriva solo il soggetto, ricavato da un passaggio separato
  che esclude volti, maglie, stemmi e scritte.</p>
</div>
{''.join(blocks)}
<div class="note">In pagina l'immagine sta nello stesso slot della foto, con la stessa
bicromia e la didascalia «{CAPTION}». Se non convince, l'apertura resta tipografica:
e' comunque una pagina valida.</div>
</body>
</html>"""


def _fake_variants(dest_dir: Path, count: int) -> list[tuple[str, str]]:
    """Segnaposto per la prova a secco.

    Non prova a somigliare a quello che uscirebbe dal generatore — sarebbe
    disonesto verso chi guarda il confronto. Riproduce solo le due
    caratteristiche che contano per capire se il trattamento regge: un
    solo inchiostro nero su carta chiara e nessun mezzotono.
    """
    from PIL import Image, ImageDraw

    subjects = [
        "SEGNAPOSTO — nessuna chiamata al modello",
        "SEGNAPOSTO — nessuna chiamata al modello",
        "SEGNAPOSTO — nessuna chiamata al modello",
    ]
    # Stesse proporzioni che si chiedono al generatore, così la prova a
    # secco mostra davvero quanto resta dopo il ritaglio dello slot.
    w, h = (int(part) for part in DEFAULT_SIZE.split("x"))
    ink, paper = (18, 16, 14), (238, 234, 226)

    variants: list[tuple[str, str]] = []
    for i in range(1, count + 1):
        img = Image.new("RGB", (w, h), paper)
        draw = ImageDraw.Draw(img)
        cx, cy = w // 2, h // 2
        r = int(h * 0.32)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=ink, width=22)
        for k in range(-5, 6):
            x = cx + k * (r // 6)
            draw.line([(x, cy - r), (x, cy + r)], fill=ink, width=5 + (k + 5) % 4 * 3)
        draw.rectangle([cx - r * 3 // 2, cy + r + 18, cx + r * 3 // 2, cy + r + 44], fill=ink)
        draw.polygon(
            [(cx - r - i * 24, cy - r - 6), (cx - r + 70, cy - r - 70), (cx - r + 140, cy - r - 6)],
            fill=ink,
        )
        path = dest_dir / f"variante_{i}.png"
        img.save(path)
        variants.append((subjects[(i - 1) % len(subjects)], str(path)))
        print(f"[{i}/{count}] segnaposto scritto in {path}")
    return variants


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--titolo", default=SAMPLE_LEAD.headline)
    parser.add_argument("--occhiello", default=SAMPLE_LEAD.deck)
    parser.add_argument("--n", type=int, default=3, help="quante varianti generare")
    parser.add_argument("--qualita", choices=["low", "medium", "high"], default="medium")
    parser.add_argument("--out", default="preview_out/illustrazione")
    parser.add_argument(
        "--pagina",
        action="store_true",
        help="compone anche la prima pagina completa con la prima variante",
    )
    parser.add_argument(
        "--finto",
        action="store_true",
        help=(
            "prova a secco: non chiama OpenAI e usa un segnaposto disegnato "
            "in locale. Serve a vedere l'impaginazione del confronto senza spendere."
        ),
    )
    parser.add_argument("--scale", type=int, default=1)
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    print(f"Titolo: {args.titolo}")

    if args.finto:
        variants = _fake_variants(out, args.n)
    else:
        load_dotenv()
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise SystemExit("Manca OPENAI_API_KEY: mettila in .env o nell'ambiente.")

        text_model = os.environ.get("OPENAI_MODEL") or "gpt-4o-mini"
        image_model = os.environ.get("OPENAI_IMAGE_MODEL") or "gpt-image-2"
        size = os.environ.get("OPENAI_IMAGE_SIZE") or DEFAULT_SIZE
        client = OpenAI(api_key=key)

        print(
            f"Sto per generare {args.n} immagini con {image_model} "
            f"({size}, qualita' {args.qualita}). Ognuna e' una chiamata a pagamento."
        )

        variants = []
        for i in range(1, args.n + 1):
            # Il soggetto si richiede a ogni giro: la variabilita' fra le
            # varianti deve stare li', non nello stile.
            subject = describe_subject(client, text_model, args.titolo, args.occhiello)
            if not subject:
                print("Nessun soggetto sicuro ricavato dal titolo: mi fermo.")
                break
            print(f"[{i}/{args.n}] soggetto: {subject}")
            path = generate_image(
                client,
                subject,
                out / f"variante_{i}.png",
                model=image_model,
                size=size,
                quality=args.qualita,
            )
            if path:
                variants.append((subject, path))
                print(f"[{i}/{args.n}] scritto {path}")

    if not variants:
        raise SystemExit("Nessuna immagine generata.")

    sheet = out / "confronto.png"
    await render_html_to_png(_sheet_html(args.titolo, variants), str(sheet), scale=args.scale)
    print(f"scritto {sheet}")

    if args.pagina:
        hero = Hero(path=variants[0][1], caption=CAPTION)
        pages = build_pages_html(
            "Azzurro Fluido",
            SAMPLE_DATE,
            SAMPLE_LEAD,
            SAMPLE_ARTICLES,
            logo_path=Path("assets/logo-azzurro.png"),
            hero=hero,
            index_entries=SAMPLE_INDEX,
            stats=SAMPLE_STATS,
            quote=SAMPLE_QUOTE,
            hourly=SAMPLE_HOURS,
            graphics=GraphicsOptions(),
        )
        target = out / "pagina_1.png"
        await render_html_to_png(pages[0], str(target), scale=args.scale)
        print(f"scritto {target}")

    print("\nPrompt di stile usato (uguale per tutte le varianti):")
    print(f"  {ART_DIRECTION}")
    print("\nPrompt completo della prima variante:")
    print(f"  {build_prompt(variants[0][0])}")


if __name__ == "__main__":
    asyncio.run(main())
