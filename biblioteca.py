"""Controlla e alleggerisce la biblioteca delle vignette.

Le immagini scaricate da un'app di generazione sono grosse: a piena
risoluzione novantasei file sono facilmente 150-200 MB, che in un
repository git sono troppi — e sono pure sprecati, perché il pannello in
pagina è largo 968px e viene renderizzato al doppio, quindi oltre i
~1900px non serve un pixel.

    python biblioteca.py assets/vignette              # solo il referto
    python biblioteca.py assets/vignette --applica    # ridimensiona e comprime
    python biblioteca.py assets/vignette --applica --jpeg

Senza --applica non tocca niente: stampa cosa farebbe.

Richiede Pillow (pip install Pillow). Serve solo qui: il gazzettino a
regime legge i PNG e basta, non ha bisogno di Pillow per girare.
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError:
    sys.exit("Serve Pillow: pip install Pillow")

# I colori li tiene il giornale. Qui c'erano tre costanti scritte a mano
# — navy, azzurro, bianco — e sono rimaste indietro quando la pagina è
# passata alla carta avorio: la bicromia rimappava ancora su un navy
# freddo e sul bianco puro, due colori che in pagina non esistono più.
from report.newspaper import AZZURRO, INK, PAPER  # noqa: E402

# I toni e le estensioni sono gli stessi che legge il gazzettino: se qui
# ci fosse una seconda lista, prima o poi direbbe una cosa diversa.
from report.vignetta import ESTENSIONI, TONI as _TONI  # noqa: E402

TONI = list(_TONI)

# Il pannello è largo 616px e la pagina si renderizza a scala 2: oltre
# 1232px non serve un pixel.
#
# Era 968 (e quindi 1936) finché l'apertura occupava tutta la pagina. Da
# quando sta su una colonna, il disegno è più stretto di un terzo, e le
# immagini della biblioteca portavano un quarto di byte in più del
# necessario. Prima il default dei modelli — 1536px — stava SOTTO la
# larghezza utile e ridurlo sarebbe stato buttare dettaglio; adesso ci
# sta sopra, e ridurre è gratis.
LARGHEZZA_UTILE = 1232
LARGHEZZA_DEFAULT = LARGHEZZA_UTILE

# Sotto queste soglie la biblioteca si nota che si ripete: vedi la
# simulazione fatta a suo tempo (con 8 varianti per tono un disegno già
# visto nel mese torna 128 volte l'anno, con 16 scende a 16).
VARIANTI_MINIME = 8
VARIANTI_CONSIGLIATE = 16


def _immagini(cartella: Path) -> list[Path]:
    if not cartella.is_dir():
        return []
    return sorted(p for p in cartella.iterdir() if p.suffix.lower() in ESTENSIONI)


def _mb(byte: int) -> str:
    return f"{byte / 1_048_576:.1f} MB"


def referto(base: Path) -> dict[str, list[Path]]:
    """Cosa c'è, cosa manca, quanto pesa."""
    trovate = {tono: _immagini(base / tono) for tono in TONI}
    sconosciute = [
        d.name for d in base.iterdir()
        if d.is_dir() and d.name not in TONI
    ] if base.is_dir() else []

    print(f"Biblioteca in {base}/\n")
    print(f"{'tono':<14}{'immagini':>10}{'peso':>12}   stato")
    print("-" * 60)
    totale_file = totale_peso = 0
    for tono in TONI:
        files = trovate[tono]
        peso = sum(f.stat().st_size for f in files)
        totale_file += len(files)
        totale_peso += peso
        if not files:
            stato = "VUOTO — questo tono non uscirà mai"
        elif len(files) < VARIANTI_MINIME:
            stato = f"scarso (sotto {VARIANTI_MINIME}: si nota la ripetizione)"
        elif len(files) < VARIANTI_CONSIGLIATE:
            stato = "sufficiente"
        else:
            stato = "buono"
        print(f"{tono:<14}{len(files):>10}{_mb(peso):>12}   {stato}")
    print("-" * 60)
    print(f"{'TOTALE':<14}{totale_file:>10}{_mb(totale_peso):>12}")

    if sconosciute:
        print(f"\nCartelle che il gazzettino ignorerà: {', '.join(sconosciute)}")
        print(f"I toni riconosciuti sono: {', '.join(TONI)}")

    vuoti = [t for t in TONI if not trovate[t]]
    if vuoti:
        quanti = (
            "Un tono è vuoto" if len(vuoti) == 1 else f"{len(vuoti)} toni sono vuoti"
        )
        print(
            f"\n{quanti} ({', '.join(vuoti)}): quei toni non vengono nemmeno "
            "proposti al modello, che sceglierà fra quelli pieni. La vignetta "
            "esce lo stesso, ma su una giornata da "
            f"{vuoti[0]} uscirà con l'aria sbagliata."
        )
    return trovate


# Sopra questa soglia di colori distinti l'immagine non è più un disegno a
# campiture piatte e la tavolozza non ha senso.
COLORI_DISEGNO = 40_000
COLORI_TAVOLOZZA = 256


def _e_disegno_piatto(immagine: Image.Image) -> bool:
    return immagine.getcolors(maxcolors=COLORI_DISEGNO) is not None


def _ridimensiona(immagine: Image.Image, larghezza: int, piatto: bool) -> Image.Image:
    """Rimpicciolisce, e sui disegni piatti rimette la tavolozza.

    Il ridimensionamento interpola: ogni contorno netto diventa una rampa
    di sfumature, e un PNG che pesava 20 KB ne pesa 200 — il compressore
    senza perdita non ha più niente da ripetere. Riquantizzare a 256
    colori restituisce la compressione senza che si veda la differenza,
    perché i colori davvero presenti sono quattro più le sfumature dei
    bordi.
    """
    if immagine.width > larghezza:
        altezza = round(immagine.height * larghezza / immagine.width)
        immagine = immagine.resize((larghezza, altezza), Image.LANCZOS)
        if piatto:
            # Senza dithering: il retino simulato è rumore, e il rumore è
            # precisamente ciò che un PNG non sa comprimere.
            immagine = immagine.quantize(
                colors=COLORI_TAVOLOZZA,
                method=Image.Quantize.FASTOCTREE,
                dither=Image.Dither.NONE,
            )
    return immagine


def bicromia(immagine: Image.Image) -> Image.Image:
    """Riporta un'immagine a colori dentro la tavolozza del gazzettino.

    Serve alle illustrazioni realistiche, che arrivano a colori pieni con
    ombre e profondità di campo — cioè tutto quello che le cinque regole
    della grafica vietano. La luminanza viene rimappata sulla rampa
    inchiostro → azzurro → carta: l'immagine resta leggibile e smette di
    essere un corpo estraneo in pagina.

    L'autocontrasto prima della mappatura non è un vezzo: senza, le foto
    con poco contrasto diventano una macchia di azzurro medio e i neri non
    arrivano mai al navy.
    """
    grigi = ImageOps.autocontrast(ImageOps.grayscale(immagine), cutoff=2)
    return ImageOps.colorize(grigi, black=INK, white=PAPER, mid=AZZURRO)


_CARTA_RGB = tuple(int(PAPER[i:i + 2], 16) for i in (1, 3, 5))


def fattori_carta(immagine: Image.Image) -> tuple[float, float, float]:
    """Di quanto va scurito ogni canale perché il fondo diventi carta.

    Il conto è carta diviso fondo VERO, non carta diviso bianco. La
    differenza si è vista quando sono arrivate le novantasei: i prompt
    nuovi chiedono un fondo avorio, il modello lo consegna — ma un avorio
    suo, tredici punti più chiaro del nostro. Moltiplicare per la carta
    dando per scontato un fondo bianco le avrebbe scurite troppo;
    lasciarle stare le lasciava chiare, e in pagina il pannello si vedeva
    come un rettangolo più chiaro dentro la carta.

    Misurato sulle novantasei: quattro erano già a posto (il fondo a due
    punti dalla carta), le altre novantadue a tredici.

    Il fattore non sale mai sopra uno: un fondo già scuro quanto la carta,
    o più scuro, è una tinta del disegno e non il suo supporto —
    schiarirlo vorrebbe dire riscrivere il disegno. Da qui viene anche
    l'idempotenza, senza doverla aggiungere: dopo una passata il fondo È
    la carta, i fattori valgono uno e la seconda passata non fa niente."""
    fondo = _fondo_chiaro(immagine) or (255, 255, 255)
    return tuple(min(1.0, c / f) for c, f in zip(_CARTA_RGB, fondo))


def sulla_carta(immagine: Image.Image) -> Image.Image:
    """Stampa il disegno sulla carta del giornale invece che sul bianco.

    I modelli consegnano su bianco qualunque cosa dica il prompt, e un
    rettangolo bianco dentro una pagina avorio si vede: è la stessa
    giuntura che si vedeva quando la colonna delle notizie aveva un fondo
    suo.

    Il conto è una moltiplicazione, che è precisamente quello che fa
    l'inchiostro sulla carta colorata: il bianco diventa carta, il nero
    resta nero, e l'azzurro si scalda di quel poco che si scalda quando
    lo stampi su avorio invece che su bianco. Non è un filtro sul fondo —
    è il disegno intero che cambia supporto, ed è per questo che non
    lascia aloni sui bordi antialiasati.

    Quanto scurire lo dice `fattori_carta`, che misura il fondo invece di
    darlo per scontato. Un disegno già sulla carta esce identico: è la
    stessa formula, con i fattori a uno.
    """
    if immagine.mode in ("RGBA", "LA") or "transparency" in immagine.info:
        # Il trasparente è già carta: comporlo prima evita che il
        # convert lo appiattisca sul nero.
        rgba = immagine.convert("RGBA")
        fondo = Image.new("RGB", immagine.size, PAPER)
        fondo.paste(rgba, mask=rgba.split()[3])
        immagine = fondo
    immagine = immagine.convert("RGB")
    tavola: list[int] = []
    for fattore in fattori_carta(immagine):
        tavola += [min(255, round(v * fattore)) for v in range(256)]
    return immagine.point(tavola)


def _fondo_chiaro(immagine: Image.Image) -> tuple[int, int, int] | None:
    """Il colore medio del fondo, preso dalla fascia alta dell'immagine.

    Lì per costruzione c'è solo sfondo: i prompt chiedono le teste sotto
    la metà e sopra di loro nient'altro che cielo, muro o acqua. Si
    tengono i pixel chiari e poco saturi — il fondo — e si lascia fuori
    tutto il resto, così un cielo azzurro o una tenda colorata non
    entrano nel conto e non fanno sbagliare la risposta."""
    alto = immagine.convert("RGB").crop(
        (0, 0, immagine.width, max(1, immagine.height // 8))
    )
    grezzi = alto.tobytes()
    passo = 3 * max(1, len(grezzi) // (3 * 4000))
    campioni = [
        p for i in range(0, len(grezzi) - 2, passo)
        for p in (grezzi[i:i + 3],)
        if min(p) >= 170 and max(p) - min(p) <= 45
    ]
    if len(campioni) < 20:
        return None
    n = len(campioni)
    return tuple(sum(c[i] for c in campioni) // n for i in range(3))


def gia_sulla_carta(immagine: Image.Image) -> bool:
    """Se stamparlo sulla carta non cambierebbe niente.

    Non è una domanda sul colore ma sui fattori: se sono tutti uno, il
    fondo è già la carta — oppure è più scuro, e allora è una tinta del
    disegno che non ci riguarda. In entrambi i casi non c'è niente da
    fare, e dirlo serve al referto: "non ha fatto niente" e "ha fatto la
    cosa giusta" avevano lo stesso aspetto."""
    return all(f >= 0.995 for f in fattori_carta(immagine))


# Dove possono cominciare le teste, in percentuale dell'altezza. Il
# pannello in pagina ritaglia il 6,5% sopra, e i balloon scendono fino a
# circa metà pannello: sotto questa soglia il disegno è ancora al sicuro,
# sopra un balloon finisce su una faccia. È l'unico difetto che non si
# vede guardando l'immagine da sola — si vede solo in pagina, quando è
# tardi.
TESTE_MIN = 52


def altezza_teste(immagine: Image.Image) -> float:
    """A che punto dell'altezza comincia la roba disegnata, in percentuale.

    Scende dall'alto e si ferma alla prima riga con abbastanza pixel
    scuri nella fascia centrale, dove stanno i personaggi. I bordi
    laterali sono esclusi apposta: lì passano palazzi, alberi e
    lampioni, che possono stare alti quanto vogliono."""
    grigi = immagine.convert("L")
    larghezza, altezza = grigi.size
    px = grigi.load()
    passo = max(1, larghezza // 200)
    for y in range(altezza):
        scuri = sum(
            1
            for x in range(int(larghezza * 0.18), int(larghezza * 0.82), passo)
            if px[x, y] < 110
        )
        if scuri >= 4:
            return 100 * y / altezza
    return 100.0


def _formato(immagine: Image.Image) -> str:
    larghezza, altezza = immagine.size
    if altezza > larghezza:
        return "verticale"
    if larghezza / altezza < 1.2:
        return "quadrata"
    return "orizzontale"


def ottimizza(
    trovate: dict[str, list[Path]],
    larghezza: int,
    jpeg: bool,
    applica: bool,
    duotone: bool = False,
    carta: bool = False,
) -> None:
    print(f"\n{'—' * 60}")
    print(
        f"{'Ridimensiono' if applica else 'Ridimensionerei'} a {larghezza}px "
        f"di larghezza, formato {'JPEG' if jpeg else 'PNG'}"
        f"{', con la bicromia azzurra' if duotone else ''}"
        f"{', stampandole sulla carta' if carta else ''}."
    )
    if not applica:
        print("(prova a vuoto: aggiungi --applica per scrivere davvero)")
    print()

    prima = dopo = 0
    avvisi: list[str] = []
    for tono, files in trovate.items():
        for percorso in files:
            originale = percorso.stat().st_size
            prima += originale
            with Image.open(percorso) as aperta:
                immagine = aperta.convert("RGB")
                forma = _formato(immagine)
                if forma != "orizzontale":
                    avvisi.append(
                        f"  {tono}/{percorso.name}: immagine {forma} "
                        f"({immagine.width}x{immagine.height}) — il pannello è "
                        "orizzontale, verrà tagliata sopra e sotto"
                    )
                teste = altezza_teste(immagine)
                if teste < TESTE_MIN:
                    avvisi.append(
                        f"  {tono}/{percorso.name}: il disegno comincia al "
                        f"{teste:.0f}% dell'altezza, sopra la soglia del "
                        f"{TESTE_MIN}% — in pagina un balloon finirebbe sulle "
                        "teste. Rigeneralo con l'inquadratura più larga."
                    )
                # La tavolozza si decide sull'originale, non sul
                # ridimensionato: dopo l'interpolazione ogni disegno
                # sembra sfumato.
                intatta = True
                if duotone:
                    immagine = bicromia(immagine)
                    intatta = False
                if carta:
                    if gia_sulla_carta(immagine):
                        avvisi.append(
                            f"  {tono}/{percorso.name}: già stampata sulla "
                            "carta, la lascio com'è"
                        )
                    else:
                        immagine = sulla_carta(immagine)
                        intatta = False
                if immagine.width > larghezza:
                    intatta = False
                piatto = not jpeg and _e_disegno_piatto(immagine)
                immagine = _ridimensiona(immagine, larghezza, piatto)

                destinazione = percorso.with_suffix(".jpg" if jpeg else ".png")
                if intatta and destinazione == percorso:
                    dopo += originale
                    continue
                if applica:
                    if jpeg:
                        immagine.save(destinazione, "JPEG", quality=88, optimize=True,
                                      progressive=True)
                    else:
                        immagine.save(destinazione, "PNG", optimize=True)
                    if destinazione != percorso:
                        percorso.unlink()
                    dopo += destinazione.stat().st_size
                else:
                    # Stima senza scrivere: salva in memoria.
                    buffer = io.BytesIO()
                    if jpeg:
                        immagine.save(buffer, "JPEG", quality=88, optimize=True)
                    else:
                        immagine.save(buffer, "PNG", optimize=True)
                    dopo += buffer.tell()

    if avvisi:
        print("Formati da controllare:")
        print("\n".join(avvisi))
        print()

    if not prima:
        return

    variazione = 100 * (1 - dopo / prima)
    print(f"peso prima:  {_mb(prima)}")
    if variazione >= 0:
        print(f"peso dopo:   {_mb(dopo)}   ({variazione:.0f}% in meno)")
    elif variazione > -15:
        # Differenza trascurabile: le immagini erano già alla misura
        # giusta e già compresse bene. Non c'è niente da consigliare.
        print(f"peso dopo:   {_mb(dopo)}   (sostanzialmente invariato)")
    else:
        # Succede quando l'originale era già compresso meglio di così:
        # tipicamente un JPEG riscritto in PNG. Il PNG conviene sui
        # disegni a campiture piatte, non su tutto.
        print(f"peso dopo:   {_mb(dopo)}   ({-variazione:.0f}% IN PIÙ)")
        if not jpeg:
            print(
                "\nIl PNG qui non conviene: queste immagini hanno troppe "
                "sfumature perché la compressione senza perdita paghi. "
                "Rilancia con --jpeg."
            )
    if dopo > 40 * 1_048_576:
        print(
            "\nSopra i 40 MB il repository comincia a farsi pesante: "
            "prova --jpeg, oppure abbassa --larghezza."
        )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("cartella", nargs="?", default="assets/vignette")
    p.add_argument("--applica", action="store_true", help="scrivi davvero i file")
    p.add_argument("--jpeg", action="store_true", help="converti in JPEG invece che PNG")
    p.add_argument(
        "--carta", action="store_true",
        help="stampa i disegni sulla carta avorio del giornale invece che "
             "sul bianco (i modelli consegnano su bianco comunque)",
    )
    p.add_argument(
        "--duotone", action="store_true",
        help="riporta le immagini nella tavolozza navy/azzurro del gazzettino "
             "(serve alle illustrazioni realistiche)",
    )
    p.add_argument(
        "--larghezza", type=int, default=LARGHEZZA_DEFAULT,
        help=f"larghezza massima in px (default {LARGHEZZA_DEFAULT}, "
             f"che è quanto ne servono in pagina)",
    )
    p.add_argument("--crea", action="store_true", help="crea le cartelle dei toni e esci")
    args = p.parse_args()

    base = Path(args.cartella)
    if args.crea:
        for tono in TONI:
            (base / tono).mkdir(parents=True, exist_ok=True)
        print(f"create {len(TONI)} cartelle in {base}/")
        return

    if not base.exists():
        sys.exit(f"{base} non esiste. Creala con: python biblioteca.py {base} --crea")

    trovate = referto(base)
    if any(trovate.values()):
        ottimizza(
            trovate, args.larghezza, args.jpeg, args.applica,
            args.duotone, args.carta,
        )


if __name__ == "__main__":
    main()
