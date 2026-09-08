"""Prepara il marchio di chi fa il giornale per la fascia di chiusura.

La gerenza — il blocchetto in fondo all'ultima pagina con la nota e
l'indirizzo del canale — sta su un fondo blu quasi nero. Il marchio
originale è di inchiostro nero: lì dentro non si vedrebbe. Questo script
ne ricava la versione che va in pagina.

    python firma.py                                  # solo il referto
    python firma.py --applica                        # scrive il file
    python firma.py assets/logo-dprimo17.png --applica

È lo stesso problema che ha già avuto la testata, e la stessa soluzione:
in assets/ convivono logo-azzurro.png, fatto per il fondo scuro, e
logo-carta.png, fatto per la carta chiara. Qui il verso è quello: un
marchio nato per la carta che deve tornare sul fondo scuro.

Serve solo quando il marchio cambia. Il gazzettino a regime legge il PNG
già pronto e non ha bisogno di Pillow per girare.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Serve Pillow: pip install Pillow")

sys.path.insert(0, str(Path(__file__).parent))
from report.newspaper import AZZURRO_PALE  # noqa: E402


def _rgb(colore: str) -> tuple[int, int, int]:
    colore = colore.lstrip("#")
    return tuple(int(colore[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def per_la_fascia(marchio: Image.Image, inchiostro: str = AZZURRO_PALE) -> Image.Image:
    """Il marchio ridipinto per il fondo scuro della gerenza.

    Una regola sola, applicata a ogni pixel:

        alpha_nuovo = alpha × (1 − luma/255),  colore = inchiostro

    Il nero pieno diventa inchiostro opaco: è la sagoma. Il bianco pieno
    sparisce, e a fare il «17» resta la fascia stessa che traspare — che
    è esattamente il ruolo che la carta ha nel marchio originale. Il
    grigio dei bordi antialiasati finisce a mezz'aria fra i due, quindi
    il contorno resta morbido invece di scalettarsi.

    La regola non ha bisogno di sapere com'è fatto il file di partenza:
    se il «17» è bianco opaco viene ritagliato, se è già trasparente
    resta trasparente. In tutti e due i casi il risultato è lo stesso.
    """
    marchio = marchio.convert("RGBA")
    r, g, b, a = marchio.split()
    # Luma percettiva, non media dei canali: su un segno in bianco e nero
    # cambia poco, ma su un marchio a colori è la differenza fra ritagliare
    # il giallo (chiaro) e ritagliare il blu (scuro).
    luma = Image.merge("RGB", (r, g, b)).convert("L")
    coperta = Image.frombytes(
        "L",
        marchio.size,
        bytes(
            alpha * (255 - chiaro) // 255
            for alpha, chiaro in zip(a.tobytes(), luma.tobytes())
        ),
    )
    # L'inchiostro sta su tutta la tela, anche sotto le parti trasparenti:
    # così i pixel di bordo mezzo opachi sfumano verso il colore giusto
    # invece di tirarsi dietro un alone del colore che c'era prima.
    fuori = Image.new("RGBA", marchio.size, _rgb(inchiostro) + (0,))
    fuori.putalpha(coperta)
    return fuori


def referto(originale: Path, uscita: Path, immagine: Image.Image) -> None:
    dentro = immagine.convert("RGBA").split()[3]
    opachi = sum(1 for v in dentro.tobytes() if v > 200)
    totali = immagine.size[0] * immagine.size[1]
    print(f"marchio   {originale}  {immagine.size[0]}×{immagine.size[1]}")
    print(f"sagoma    {opachi * 100 // totali}% della tela, il resto traspare")
    print(f"uscita    {uscita}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("marchio", nargs="?", default="assets/logo-dprimo17.png")
    p.add_argument("--uscita", default="", help="default: <marchio>-gerenza.png")
    p.add_argument("--applica", action="store_true", help="scrivi davvero il file")
    args = p.parse_args()

    origine = Path(args.marchio)
    if not origine.exists():
        sys.exit(f"Non trovo {origine}")
    destinazione = (
        Path(args.uscita)
        if args.uscita
        else origine.with_name(f"{origine.stem}-gerenza.png")
    )

    fatta = per_la_fascia(Image.open(origine))
    referto(origine, destinazione, fatta)
    if not args.applica:
        print("\n(niente scritto: rilancia con --applica)")
        return
    fatta.save(destinazione, optimize=True)
    print(f"\nscritto {destinazione} ({destinazione.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
