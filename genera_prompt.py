"""Scrive i 96 prompt della biblioteca e prepara le cartelle dove salvarle.

La biblioteca è 6 toni × 16 ambientazioni.

Il TONO è l'unica cosa che il gazzettino indicizza: quando la vignetta del
giorno è un litigio, il codice pesca a caso fra le sedici immagini del tono
"battibecco". L'AMBIENTAZIONE non la sceglie nessuno — serve solo a far sì
che sedici disegni dello stesso tono non sembrino sedici volte lo stesso
disegno.

È il motivo per cui le scene NON sono legate agli argomenti del gruppo.
Una scena "l'asta del fantacalcio" illustrerebbe la categoria e non il
fatto — che è precisamente l'errore per cui le illustrazioni generate
erano già state scartate una volta (docs/grafica.md). Qui il fatto sta
nelle parole dei balloon, che sono quelle vere scritte quel giorno; il
disegno porta solo il tono. Le ambientazioni fanno riconoscere il gruppo
dai luoghi, non dai fatti: e i luoghi si ripetono senza invecchiare.

Tre blocchi, indipendenti fra loro:

  MONDO   chi sono i due e come sono vestiti
  STILE   la tecnica del disegno (manga, china, quotidiano)
  TONI    cosa stanno provando

Si cambia uno solo alla volta. Cambiare il mondo lasciando lo stile dà
gli stessi disegni con altra gente dentro; cambiare lo stile lasciando il
mondo dà le stesse persone disegnate in un altro modo.

    python genera_prompt.py                             # stile quotidiano
    python genera_prompt.py --stile china --out china.txt
    python genera_prompt.py --cartelle assets/vignette
"""

from __future__ import annotations

import argparse
from pathlib import Path

from azioni import TONI
from spazi import RICHIESTA_AZIONE, SPAZIO_LUOGO, accoppia

# ---------------------------------------------------------------- il mondo

# I due protagonisti. L'azzurro dice Napoli senza bisogno di uno stemma —
# ed è già la tavolozza del gazzettino, quindi non rompe niente. Gli
# stemmi e le maglie ufficiali sono marchi registrati e restano fuori.
MONDO = (
    "Due amici napoletani sui trentacinque anni, tifosi di calcio, gente "
    "comune e non atleti. Quello a sinistra è robusto, capelli scuri corti "
    "e spettinati, barba di qualche giorno, maglietta azzurra a tinta "
    "unita senza scritte né stemmi. Quello a destra è più magro, capelli "
    "scuri con la frangia, felpa azzurro chiaro, e spesso una sciarpa "
    "azzurra a tinta unita al collo."
)

# -------------------------------------------------------------- gli stili

# Blocchi intercambiabili. Quello scelto finisce identico in tutti e 96 i
# prompt: è la sola cosa che tiene insieme la biblioteca. Mezze immagini
# con uno stile e mezze con un altro si vedono subito in pagina.
STILI = {
    "manga": (
        "STILE: illustrazione in stile manga giapponese, linea chiara. "
        "Contorni netti e di spessore variabile in nero caldo, quasi "
        "bruno; campiture piatte, retino a puntini usato con parsimonia. "
        "Occhi grandi ed espressivi con il riflesso chiaro. Espressioni "
        "marcate, con i segni convenzionali del manga: la vena del "
        "nervoso, la goccia di sudore, le linee cinetiche. Nessuna "
        "sfumatura digitale, nessuna ombra portata, nessun effetto di "
        "luce. Palette limitata a quattro colori: nero caldo per le "
        "linee, azzurro acceso e azzurro chiaro per gli accenti, e "
        "AVORIO CALDO pieno e uniforme per il fondo, il colore della "
        "carta di un quotidiano."
    ),
    "china": (
        "STILE: illustrazione a china, come una vignetta sportiva "
        "d'annata. Tratto spesso e sicuro in nero caldo, quasi bruno; "
        "poche ombre, rese con tratteggio largo e non con campiture "
        "grigie; figure leggermente caricaturali ma non deformi. Un solo "
        "colore oltre al nero: l'azzurro, usato a macchie piatte su "
        "maglie, sciarpe e pochi dettagli. Fondo AVORIO CALDO pieno e "
        "uniforme, il colore della carta di un quotidiano, senza "
        "tratteggio di sfondo. Nessuna sfumatura, nessun effetto digitale."
    ),
    # Il realismo è l'unico stile che NON nasce dentro la tavolozza del
    # gazzettino: arriva a colori pieni, con ombre e profondità di campo,
    # cioè tutto quello che le cinque regole della grafica vietano. Va
    # passato per la bicromia di biblioteca.py --duotone, che lo riporta
    # sulla rampa inchiostro → azzurro → carta; altrimenti in pagina
    # sembra incollato da un altro giornale.
    "realistico": (
        "STILE: illustrazione realistica, resa quasi fotografica. Luce "
        "naturale, volumi e ombre morbide, leggera profondità di campo con "
        "lo sfondo appena sfocato, texture di pelle e tessuti visibili. "
        "Espressioni recitate ma credibili, senza caricatura e senza "
        "deformazioni. Colori naturali e caldi, con l'azzurro delle "
        "maglie e delle sciarpe come unico colore acceso della scena."
    ),
    "quotidiano": (
        "STILE: vignetta satirica da quotidiano italiano. Disegno a penna "
        "con linea decisa e nervosa, poche ombre, figure caricaturali dai "
        "lineamenti espressivi. Colore quasi assente: solo tocchi di "
        "azzurro piatto sulle maglie e sulle sciarpe, tutto il resto in "
        "nero caldo su fondo AVORIO CALDO pieno e uniforme — il colore "
        "della carta di un quotidiano, non bianco. L'aria è quella di una "
        "striscia stampata su carta di giornale, ma la carta è quella su "
        "cui la stampiamo noi: niente texture, niente grana, niente "
        "invecchiamento."
    ),
}

INQUADRATURA = (
    "Inquadratura orizzontale, i due personaggi a mezzo busto o a tre "
    "quarti di figura, uno a sinistra e uno a destra."
)

VINCOLI = (
    "VINCOLI TASSATIVI: nessun testo, nessuna scritta, nessuna lettera e "
    "nessun numero in nessun punto dell'immagine, in nessuna lingua. "
    "Nessun fumetto e nessuna nuvoletta di dialogo, nemmeno vuoti. Nessuno "
    "stemma, logo, marchio o maglia ufficiale di una squadra reale: "
    "l'azzurro è a tinta unita e basta. Nessuna persona reale o "
    "riconoscibile. Se in scena c'è uno schermo — televisore, telefono, "
    "computer — mostra solo forme e colori generici: nessun volto, nessuna "
    "scritta, nessuna partita riconoscibile. Nessuna cornice e nessuna "
    "firma. COMPOSIZIONE, la parte più importante: inquadratura molto "
    "larga, con i due personaggi piccoli e in basso. Le loro TESTE "
    "cominciano sotto la metà esatta dell'immagine, e sopra di loro c'è "
    "solo sfondo vuoto — cielo, muro, acqua — per tutta la metà "
    "superiore. Nessuna testa, nessuna mano e nessun dettaglio "
    "importante nella metà alta. Lo sfondo è essenziale e poco "
    "dettagliato: poche linee, niente tratteggio fitto. "
    "DIMENSIONE FINALE: il disegno sarà guardato largo poco più di "
    "seicento pixel su uno schermo di telefono. Tutto quello che a quella "
    "misura non si legge è peso sprecato: linee poche e spesse, nessun "
    "tratteggio fitto, nessun retino sottile, nessun dettaglio minuto sui "
    "volti o sui vestiti. Meglio dieci linee che si vedono di cento che "
    "diventano una macchia grigia."
)
# La metà, non il terzo: misurato mettendo due balloon veri dentro il
# pannello. Il pannello nel frattempo è passato da 968x560 a 616x356 —
# l'apertura sta su una colonna e non più su tutta la pagina — ma i
# balloon si sono rimpiccioliti insieme a lui, quindi la frazione non
# cambia: sul render di oggi il blocco delle battute finisce al 53%
# dell'altezza, e la soglia di biblioteca.py (TESTE_MIN = 52) regge.

# -------------------------------------------------------- le ambientazioni

# Napoli si riconosce dai luoghi, che non invecchiano, e non dai fatti,
# che invecchiano in un giorno.
AMBIENTAZIONI = [
    ("salotto", "in un salotto di casa davanti a un televisore acceso, una sciarpa azzurra appoggiata sullo schienale del divano"),
    ("curva", "in piedi sugli spalti di uno stadio, in mezzo a un mare di sciarpe azzurre alzate, la folla accennata dietro"),
    ("bar", "al bancone di un bar di quartiere, due tazzine di caffè davanti e la macchina espresso alle spalle"),
    ("vicolo", "in un vicolo stretto del centro, panni stesi fra i balconi e festoni azzurri tirati da un lato all'altro"),
    ("lungomare", "sul lungomare, appoggiati alla ringhiera, il golfo e la sagoma del Vesuvio all'orizzonte"),
    ("motorino", "fermi in sella a uno scooter al semaforo, entrambi col casco, il traffico intorno"),
    ("pizzeria", "seduti a un tavolo di pizzeria, il forno a legna acceso sullo sfondo, piatti vuoti davanti"),
    ("balcone", "su un balcone al tramonto, appoggiati alla ringhiera, i palazzi e il Vesuvio dietro"),
    ("auto", "seduti nell'abitacolo di un'auto ferma, inquadrati dal parabrezza, la mano vicino all'autoradio"),
    ("ufficio", "in un ufficio con scrivanie e monitor, uno dei due tiene lo smartphone nascosto sotto il piano della scrivania"),
    ("spogliatoio", "in uno spogliatoio da calcetto, seduti su una panca, borsoni e appendiabiti alle spalle"),
    ("computer", "davanti allo schermo di un portatile, in una stanza da studio con una libreria dietro"),
    ("salumeria", "in fila in una salumeria di quartiere, salumi appesi e bancone alle spalle"),
    ("metro", "in piedi in una carrozza della metropolitana, aggrappati alla barra, i finestrini scuri dietro"),
    ("video", "chini sullo stesso smartphone tenuto fra loro due, che guardano un video: lo schermo mostra solo forme e colori indistinti"),
    ("pioggia", "sotto la pioggia fuori da uno stadio, ombrelli aperti, giacche bagnate"),
]

APERTURA = "Vignetta a fumetti, senza testo."


def prompt(tono: str, indice: int, ambientazione: str, stile: str) -> str:
    """Un prompt: mondo + aria del tono + azione di quella variante + luogo."""
    aria, azioni = TONI[tono]
    return (
        f"{APERTURA} {MONDO} {aria} Nella scena {azioni[indice]}, "
        f"{ambientazione}. {STILI[stile]} {INQUADRATURA} {VINCOLI}"
    )


def controlla() -> None:
    """Sedici azioni per tono, tutte diverse. Un doppione in biblioteca
    vale come un'immagine in meno, ed e' il difetto che si nota."""
    for tono, (_, azioni) in TONI.items():
        if len(azioni) != len(AMBIENTAZIONI):
            raise SystemExit(
                f"{tono}: {len(azioni)} azioni ma {len(AMBIENTAZIONI)} ambientazioni"
            )
        doppioni = {a for a in azioni if azioni.count(a) > 1}
        if doppioni:
            raise SystemExit(f"{tono}: azioni ripetute -> {doppioni}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default="prompt_vignette.txt")
    # Il predefinito è "quotidiano" perché è l'unico dei quattro che
    # descrive la pagina in cui il disegno finisce davvero: penna, colore
    # quasi assente, aria di striscia stampata. Gli altri restano per
    # provare, ma partire da lì vuol dire generare novantasei immagini
    # che poi in pagina stonano.
    p.add_argument("--stile", default="quotidiano", choices=list(STILI))
    p.add_argument(
        "--cartelle", default=None,
        help="percorso in cui creare le cartelle dei toni (es. assets/vignette)",
    )
    args = p.parse_args()
    controlla()

    righe = [
        f"BIBLIOTECA DELLE VIGNETTE — 96 prompt — stile: {args.stile}",
        "Tarati sulla grafica su carta avorio: fondo avorio, nero caldo,",
        "linee poche e spesse perché in pagina il pannello è largo 616px.",
        "=" * 72,
        "",
        "Come si usa: incolli un prompt alla volta nell'app che preferisce",
        "(ChatGPT, Gemini, quello che è), scarichi l'immagine e la salvi con",
        "il NOME FILE indicato sopra ciascun prompt, dentro la cartella del",
        "suo tono. Poi lanci biblioteca.py, che controlla e ottimizza.",
        "",
        "Le immagini sono indicizzate SOLO per tono: l'ambientazione serve a",
        "non far sembrare sedici disegni la stessa cosa, non la sceglie",
        "nessuno. Se un'immagine non ti convince, non salvarla: una brutta",
        "in biblioteca esce prima o poi in prima pagina.",
        "",
        "Consiglio: fanne quattro o cinque di un tono solo e guardale in",
        "fila prima di andare avanti. Se lo stile non convince si cambia il",
        "blocco STILE e si rigenera — meglio buttare cinque immagini che",
        "novantasei.",
        "",
        "=" * 72,
        "",
    ]

    n = 0
    for tono in TONI:
        righe += ["", "#" * 72,
                  f"### TONO: {tono.upper()}   ({len(AMBIENTAZIONI)} immagini)",
                  "#" * 72]
        # Non l'ordine, ma l'accoppiamento: un'azione che chiede spazio
        # non puo' finire in metropolitana.
        for indice, (i_azione, i_luogo) in enumerate(
            accoppia(TONI[tono][1], AMBIENTAZIONI), start=1
        ):
            nome, ambientazione = AMBIENTAZIONI[i_luogo]
            n += 1
            righe += ["",
                      f"--- {n:02d}/96 --- salva come: {tono}/{indice:02d}-{nome}.png",
                      "",
                      prompt(tono, i_azione, ambientazione, args.stile)]

    Path(args.out).write_text("\n".join(righe) + "\n", encoding="utf-8")
    print(f"scritto {args.out} — {n} prompt, stile «{args.stile}»")

    if args.cartelle:
        base = Path(args.cartelle)
        for tono in TONI:
            (base / tono).mkdir(parents=True, exist_ok=True)
        print(f"create {len(TONI)} cartelle in {base}/")


if __name__ == "__main__":
    main()
