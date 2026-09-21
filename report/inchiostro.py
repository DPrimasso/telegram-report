"""L'inchiostro: riporta un'immagine dentro la tavolozza della pagina.

Il gazzettino ha due colori e una carta, e un modello di immagini
consegna i suoi: sky blue, terracotta, ocra, le ombre morbide. In pagina
quel rettangolo si vede come un ritaglio di un altro giornale — che è
esattamente il difetto che `docs/grafica.md` chiama decorazione.

Qui stanno le due rimappature che lo rimettono in riga. Lavorano tutte e
due sulla luminanza e nessuna sul colore di partenza: conta dove il
pixel va a finire, non da dove viene.

  bicromia        inchiostro -> azzurro -> carta, per le illustrazioni
                  che devono restare a colori ma dentro i nostri
  bianco_e_nero   inchiostro -> carta e basta: il disegno diventa una
                  xilografia stampata sulla carta avorio, cioè la stessa
                  materia del resto della pagina

Stavano dentro `biblioteca.py`, che è uno strumento da riga di comando e
importa il gazzettino: il gazzettino non poteva importarlo indietro senza
chiudere il cerchio. Qui le usano tutti e due.

Pillow resta facoltativo. Serve solo a questo ritocco, e un'edizione non
salta perché manca una libreria: se non c'è, il disegno esce come l'ha
consegnato il modello e in coda ai log resta detto perché.
"""

from __future__ import annotations

from pathlib import Path

from report.newspaper import AZZURRO, INK, PAPER

try:
    from PIL import Image, ImageOps
except ImportError:  # vedi il docstring: è un ritocco, non un requisito
    Image = ImageOps = None  # type: ignore[assignment]

# Il pannello in pagina è largo 616px e le pagine si renderizzano a scala
# 2: oltre 1232px non serve un pixel, e i pixel in più diventano base64
# dentro l'HTML della pagina — cioè peso puro.
LARGHEZZA_UTILE = 1232


def disponibile() -> bool:
    """Se Pillow c'è e quindi si può ritoccare."""
    return Image is not None


def bicromia(immagine: "Image.Image") -> "Image.Image":
    """Rimappa la luminanza sulla rampa inchiostro -> azzurro -> carta.

    Serve alle illustrazioni realistiche, che arrivano a colori pieni con
    ombre e profondità di campo — cioè tutto quello che le cinque regole
    della grafica vietano.

    L'autocontrasto prima della mappatura non è un vezzo: senza, le
    immagini con poco contrasto diventano una macchia di azzurro medio e
    i neri non arrivano mai all'inchiostro.
    """
    grigi = ImageOps.autocontrast(ImageOps.grayscale(immagine), cutoff=2)
    return ImageOps.colorize(grigi, black=INK, white=PAPER, mid=AZZURRO)


def bianco_e_nero(immagine: "Image.Image") -> "Image.Image":
    """Come la bicromia, ma senza lo scalo azzurro: solo inchiostro e carta.

    È la stessa rampa con due estremi invece di tre, e la differenza in
    pagina è tutta lì: la bicromia aggiunge un colore, questa non ne
    aggiunge nessuno. Il fondo esce esattamente sul `PAPER` della pagina
    — l'autocontrasto porta l'avorio del modello sul bianco pieno e la
    mappatura lo riporta sulla nostra carta — quindi il pannello non ha
    più un fondo suo e il bordo non è più una giuntura.
    """
    grigi = ImageOps.autocontrast(ImageOps.grayscale(immagine), cutoff=2)
    return ImageOps.colorize(grigi, black=INK, white=PAPER)


def stampa_in_bianco_e_nero(
    percorso: str | Path, larghezza: int = LARGHEZZA_UTILE
) -> bool:
    """Riscrive il file in bianco e nero, alla misura che serve in pagina.

    Il prompt lo chiede già monocromo, ma un prompt è una richiesta: i
    modelli il colore lo rimettono, e basta una sbavatura di terracotta
    perché il pannello smetta di somigliare al resto della pagina. Questo
    passaggio non chiede, converte — e fatto dopo la generazione vale per
    qualunque modello di immagini ci si trovi davanti.

    Torna False quando non ha potuto fare niente (Pillow assente, file
    illeggibile): chi chiama tiene il disegno com'è, che è sempre meglio
    di nessun disegno.
    """
    if not disponibile():
        print(
            "  Disegno lasciato com'è: manca Pillow, non posso portarlo in "
            "bianco e nero (pip install -r requirements.txt)."
        )
        return False
    percorso = Path(percorso)
    try:
        with Image.open(percorso) as aperta:
            immagine = bianco_e_nero(aperta.convert("RGB"))
            if immagine.width > larghezza:
                altezza = round(immagine.height * larghezza / immagine.width)
                immagine = immagine.resize((larghezza, altezza), Image.LANCZOS)
            immagine.save(percorso, "PNG", optimize=True)
            misura = f"{immagine.width}x{immagine.height}"
    except OSError as errore:
        print(f"  Bianco e nero saltato ({errore}): tengo il disegno com'è.")
        return False
    # Detto in positivo apposta: l'unico modo di sapere che era andata
    # bene era che non fosse comparso un errore, e "non ha detto niente"
    # e "ha fatto la cosa giusta" avevano lo stesso aspetto nei log di
    # un'edizione che gira in CI e non si può guardare.
    print(f"  Disegno portato in bianco e nero sulla carta del giornale ({misura}).")
    return True
