"""Il banco di prova del disegno del giorno: una notizia, un'immagine.

Serve a guardare la vignetta senza far uscire un'edizione. Il gazzettino
vero legge Telegram, scrive quindici pezzi e poi disegna: per giudicare
il disegno è un giro lunghissimo e costoso, e il disegno è la parte che
si itera di più — il prompt lo si ritocca dieci volte prima che la scena
convinca.

Qui la notizia è un dato d'ingresso e il resto non c'è. La funzione che
disegna è la STESSA che usa il gazzettino (`generate_ai_drawing`): se
funziona qui funziona in edizione, e se qui esce storto è storto anche
lì.

    python prova_vignetta.py --solo-prompt      # gratis: stampa i prompt
    python prova_vignetta.py                    # un disegno sul fatto d'esempio
    python prova_vignetta.py --tutti            # i tre fatti, tre scene diverse
    python prova_vignetta.py --tema "..." --tono esultanza --battuta "..."
    python prova_vignetta.py --colore           # com'era prima del bianco e nero

I file finiscono in `prova_vignette/<tono>/`, che è la forma di una
biblioteca: per vederli in pagina, alla misura vera e con i balloon
sotto, basta

    python preview.py --vignetta <tono> --biblioteca prova_vignette

Serve OPENAI_API_KEY nell'ambiente o nel .env (tranne con --solo-prompt).
Ogni disegno si paga: vedi PREZZO_IMMAGINE in report/spesa.py.
"""

from __future__ import annotations

import argparse
import os
import re
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from report import spesa
from report.vignetta import (
    TONI,
    _prompt_disegno,
    _prompt_scena,
    generate_ai_drawing,
)

load_dotenv()

# Tre fatti di tre giornate diverse, scelti perché non hanno lo stesso
# posto: uno si guarda in tv, uno si aspetta sul telefono, uno si gioca
# davanti a un portatile. È il modo più corto di vedere se la scena la
# decide il fatto o l'abitudine — se tornano tre disegni che si
# somigliano, il prompt non sta funzionando.
FATTI = {
    "partita": dict(
        tema=(
            "Ruggiero al 90' ribalta una partita archiviata — Il pareggio era "
            "dato per buono da venti minuti"
        ),
        tono="esultanza",
        battute=[
            "Ruggiero al novantesimo, mi sono messo a urlare da solo in cucina",
            "Tre punti che ieri sera nessuno di noi avrebbe firmato",
        ],
        contesto=(
            "Il gol arriva al 90' su una partita che tutti avevano già "
            "archiviato come pareggio. Il gruppo la stava guardando in tv e la "
            "discussione è andata avanti oltre la mezzanotte."
        ),
    ),
    "mercato": dict(
        tema=(
            "Il rinnovo slitta ancora — La firma attesa entro giovedì non è "
            "arrivata e la fiducia comincia a mancare"
        ),
        tono="attesa",
        battute=[
            "Ogni giorno una data nuova, alla fine non firma piu' nessuno",
            "Aggiorno la pagina da stamattina e non cambia niente",
        ],
        contesto=(
            "La notizia è arrivata sul telefono a metà pomeriggio, mentre "
            "quasi tutti erano al lavoro. Nessun annuncio ufficiale fino a "
            "sera, e il gruppo ha passato la giornata a rilanciare voci."
        ),
    ),
    "fantacalcio": dict(
        tema=(
            "L'asta si ferma sul portiere — Duecento crediti su un solo nome e "
            "la lega si spacca a metà"
        ),
        tono="battibecco",
        battute=[
            "Duecento crediti per un portiere, ti sei giocato l'asta in venti minuti",
            "Meglio uno buono che tre che non parano niente, l'anno scorso ho vinto cosi'",
        ],
        contesto=(
            "L'asta si è giocata online, ognuno davanti al proprio portatile, "
            "ed è rimasta ferma quaranta minuti sullo stesso nome."
        ),
    ),
}

# Una scena d'esempio, che serve solo a --solo-prompt: senza chiamare
# niente non c'è nessuna scena da mostrare, e il prompt del disegno senza
# la scena dentro non si legge.
SCENA_DI_ESEMPIO = (
    "in salotto davanti alla tv accesa, a tarda sera",
    "uno in piedi con le braccia al cielo, l'altro che si alza dal divano",
    "una sciarpa buttata sullo schienale",
)


def _nome_file(tema: str) -> str:
    """Un nome di file che dice quale fatto è: il disegno si giudica in
    fila con gli altri, e `prova_1.png` non aiuta a ricordare quale era."""
    parole = re.findall(r"[a-zà-ù0-9]+", tema.lower())[:5]
    return "-".join(parole) or "prova"


def disegna(args, fatto: dict, cartella: Path) -> Path | None:
    tono = args.tono or fatto["tono"]
    battute = args.battuta or fatto["battute"]
    tema = args.tema or fatto["tema"]
    contesto = args.contesto if args.contesto is not None else fatto["contesto"]

    print(f"\n{'—' * 72}\nFATTO: {tema}\nTONO:  {tono}")

    if args.solo_prompt:
        luogo, azione, oggetto = SCENA_DI_ESEMPIO
        print("\n--- PROMPT DELLA SCENA (prima chiamata) ---")
        print(_prompt_scena(tema, tono, battute, contesto))
        print("\n--- PROMPT DEL DISEGNO (seconda chiamata) ---")
        print("(su una scena d'esempio: la vera la ricava la prima chiamata)")
        print(_prompt_disegno(luogo, azione, oggetto, tono, not args.colore))
        return None

    chiave = os.environ.get("OPENAI_API_KEY")
    if not chiave:
        raise SystemExit(
            "Manca OPENAI_API_KEY (nell'ambiente o nel .env). Senza chiave "
            "resta --solo-prompt, che non chiama niente."
        )

    destinazione = cartella / tono / f"{_nome_file(tema)}.png"
    return generate_ai_drawing(
        OpenAI(api_key=chiave),
        destinazione,
        tema=tema,
        tono=tono,
        battute=battute,
        contesto=contesto,
        giorno=date.today(),
        text_model=args.modello_testo,
        image_model=args.modello_immagine,
        bianco_e_nero=not args.colore,
    )


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--tema", help="titolo e sommario dell'apertura")
    p.add_argument("--contesto", help="il pezzo di apertura per esteso")
    p.add_argument("--tono", choices=list(TONI), help=f"uno fra: {', '.join(TONI)}")
    p.add_argument(
        "--battuta", action="append",
        help="una battuta del gruppo (ripetibile, al massimo due contano)",
    )
    p.add_argument(
        "--fatto", choices=list(FATTI), default="partita",
        help="quale fatto d'esempio usare (default: partita)",
    )
    p.add_argument(
        "--tutti", action="store_true",
        help="prova tutti i fatti d'esempio: tre notizie, tre scene",
    )
    p.add_argument(
        "--colore", action="store_true",
        help="lascia la tavolozza del modello invece del bianco e nero",
    )
    p.add_argument(
        "--solo-prompt", action="store_true",
        help="stampa i due prompt e non chiama niente (gratis)",
    )
    p.add_argument("--out", default="prova_vignette", help="cartella di uscita")
    p.add_argument(
        "--modello-testo", default=os.environ.get("OPENAI_MODEL") or "gpt-5.6-luna",
    )
    p.add_argument(
        "--modello-immagine",
        default=os.environ.get("OPENAI_IMAGE_MODEL") or "gpt-image-2",
    )
    args = p.parse_args()

    cartella = Path(args.out)
    scelti = list(FATTI.values()) if args.tutti else [FATTI[args.fatto]]

    fatti_fuori: list[Path] = []
    for fatto in scelti:
        uscita = disegna(args, fatto, cartella)
        if uscita:
            fatti_fuori.append(uscita)

    if not fatti_fuori:
        return

    print(f"\n{'—' * 72}")
    for percorso in fatti_fuori:
        print(f"scritto {percorso}")
    toni = sorted({p.parent.name for p in fatti_fuori})
    print(
        f"\nSpesa: {spesa.tassametro.costo_immagini():.2f}$ di immagini "
        f"({len(fatti_fuori)}) piu' le chiamate di testo.\n"
        "Per vederli in pagina, alla misura vera e con i balloon sotto:\n"
        + "\n".join(
            f"  python preview.py --vignetta {t} --biblioteca {cartella}"
            for t in toni
        )
    )


if __name__ == "__main__":
    main()
