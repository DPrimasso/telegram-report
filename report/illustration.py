"""Illustrazione generata per l'apertura, quando non c'è nessuna foto.

È l'ultima ricaduta della catena in report/photo.py, dopo la foto del
gruppo e la copertina YouTube, e resta **spenta di default**: si accende
con ILLUSTRATION_FALLBACK=1. Il motivo per cui non è accesa sta in
docs/grafica.md — un'illustrazione non dice niente che il testo non dica
già — ma se la si vuole, il modo in cui è incorniciata qui è quello che
la rende sopportabile in una testata invece che un adesivo.

Le tre difese, in ordine di importanza:

1. **Uno stile solo, bloccato in una costante.** ART_DIRECTION non si
   compone a runtime e non dipende dalla notizia. Una testata che cambia
   registro grafico ogni giorno non sembra una testata, ed è esattamente
   quello che succede lasciando che sia il modello a scegliere lo stile.
2. **Il soggetto lo decide un passaggio separato.** Prima un modello di
   testo riduce il titolo a un soggetto visivo semplice e sicuro, poi
   quel soggetto entra nel prompt dell'immagine. Buttare il titolo dentro
   il generatore significa ritrovarsi scritte sbagliate, volti di
   giocatori veri e stemmi in prima pagina.
3. **Passa dallo stesso filtro delle foto vere.** L'immagine finisce
   nello slot `Hero`, quindi eredita la bicromia del gazzettino: non
   entra in pagina una seconda tavolozza, e l'illustrazione si accorda
   con le giornate in cui al suo posto c'è una fotografia.

La didascalia dice sempre che è generata. Un'immagine finta senza
etichetta dentro un riepilogo di cose vere è l'unica cosa qui dentro che
sarebbe un problema anche fuori dalla grafica.
"""

import base64
from pathlib import Path

from report.newspaper import Hero

# Lo stile è in inglese perché i generatori di immagini lo seguono in modo
# molto più prevedibile, ed è volutamente monocromo: l'immagine viene poi
# rimappata sulla bicromia del gazzettino, e una sorgente già a un solo
# inchiostro attraversa quel passaggio senza dominanti impreviste.
ART_DIRECTION = (
    "Monochrome linocut print, a single black ink on off-white paper. "
    "Bold carved lines, strong shapes, high contrast, visible gouge texture. "
    "Flat plain background, no gradients, no halftone dots, no colour. "
    "Centred composition with generous empty space around the subject. "
    "Editorial illustration for a newspaper, restrained and graphic. "
    "Absolutely no text, no letters, no numbers, no logos, no signage, "
    "no watermarks, no signatures. No people, no faces, no crowds, "
    "no sports jerseys, no team emblems, no brand marks."
)

# Al modello di testo si chiede un oggetto, non una scena narrativa: gli
# oggetti attraversano bene lo stile a un inchiostro, le scene con più
# soggetti diventano illeggibili una volta ridotte a 1080px di larghezza.
_SUBJECT_PROMPT = (
    "Sei il caporedattore grafico di un gazzettino. Dal titolo qui sotto "
    "ricava UN soggetto visivo per l'illustrazione di apertura.\n\n"
    "Vincoli, tutti obbligatori:\n"
    "- un oggetto singolo o una natura morta di due o tre oggetti, mai una "
    "scena con persone;\n"
    "- niente volti, niente figure umane, niente folla, niente maglie da "
    "gioco, niente stemmi, niente marchi, niente scritte;\n"
    "- concreto e fotografabile: un oggetto che esiste, non un concetto;\n"
    "- deve rimandare al contenuto del titolo in modo riconoscibile, anche "
    "per metafora, senza illustrare persone reali;\n"
    "- deve restare leggibile a un solo inchiostro e in piccolo.\n\n"
    "Rispondi in INGLESE, con la sola descrizione del soggetto, al massimo "
    "venti parole, senza virgolette e senza altro testo.\n"
    "Se dal titolo non si ricava nessun soggetto che rispetti i vincoli, "
    "rispondi solo: NESSUNO"
)

CAPTION = "Illustrazione generata · non è una fotografia"

# Lo slot dell'apertura è 1080x420 (`.hero` in newspaper.py), cioè un
# 2.57:1, e l'immagine ci entra con object-fit: cover. Chiedendo un 16:9
# se ne perde quasi un terzo in altezza, e su una composizione centrata
# come questa il taglio mangia il soggetto: verificato con la prova a
# secco. 1600x624 è il rapporto dello slot con entrambi i lati multipli
# di 16, che è il vincolo dei modelli gpt-image-2.
#
# gpt-image-1 accetta invece solo misure fisse (1024x1024, 1536x1024,
# 1024x1536): con quel modello va impostato OPENAI_IMAGE_SIZE=1536x1024,
# accettando che il taglio sia più aggressivo.
DEFAULT_SIZE = "1600x624"


def describe_subject(client, model: str, headline: str, deck: str = "") -> str:
    """Riduce il titolo a un soggetto visivo. Stringa vuota se non ce n'è
    uno sicuro: è un esito normale, non un errore."""
    if not headline:
        return ""
    source = headline if not deck else f"{headline}\n{deck}"
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": f"{_SUBJECT_PROMPT}\n\nTitolo:\n{source}"}],
        temperature=0.4,
    )
    subject = (response.choices[0].message.content or "").strip().strip('"')
    if not subject or subject.upper().startswith("NESSUNO"):
        return ""
    return subject


def build_prompt(subject: str) -> str:
    """Il soggetto sta davanti e lo stile dietro: invertendoli i modelli
    tendono a trattare lo stile come suggerimento."""
    return f"{subject}. {ART_DIRECTION}"


def generate_image(
    client,
    subject: str,
    dest: str | Path,
    *,
    model: str = "gpt-image-2",
    size: str = DEFAULT_SIZE,
    quality: str = "medium",
) -> str | None:
    """Genera l'immagine e la scrive su `dest`. None se la chiamata
    fallisce: l'apertura tipografica è comunque una pagina valida, quindi
    qui non si solleva niente verso il job notturno."""
    try:
        response = client.images.generate(
            model=model,
            prompt=build_prompt(subject),
            size=size,
            quality=quality,
            n=1,
        )
    except Exception as exc:
        print(f"Illustrazione non generata ({exc}): apertura senza immagine.")
        return None

    payload = getattr(response.data[0], "b64_json", None)
    if not payload:
        print("Illustrazione non generata: risposta senza immagine.")
        return None

    dest = Path(dest)
    dest.write_bytes(base64.b64decode(payload))
    return str(dest)


def illustration_hero(
    client,
    dest_dir: str | Path,
    *,
    headline: str,
    deck: str = "",
    text_model: str = "gpt-4o-mini",
    image_model: str = "gpt-image-2",
    size: str = DEFAULT_SIZE,
    quality: str = "medium",
) -> Hero | None:
    """Catena completa: titolo → soggetto → immagine → Hero."""
    try:
        subject = describe_subject(client, text_model, headline, deck)
    except Exception as exc:
        print(f"Soggetto dell'illustrazione non ricavato ({exc}).")
        return None
    if not subject:
        print("Nessun soggetto sicuro per l'illustrazione: apertura tipografica.")
        return None

    print(f"Soggetto dell'illustrazione: {subject}")
    path = generate_image(
        client,
        subject,
        Path(dest_dir) / "hero-illustrazione.png",
        model=image_model,
        size=size,
        quality=quality,
    )
    if not path:
        return None
    return Hero(path=path, caption=CAPTION)
