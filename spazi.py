"""Quanto spazio serve a un'azione, e quanto ne offre un luogo.

Nasce da un difetto vero: abbinando l'azione numero i all'ambientazione
numero i, l'esultanza «tutti e due in ginocchio con le braccia
spalancate» era finita in sella a uno scooter nel traffico. Il disegno
usciva impossibile, e non per colpa del modello.

Tre livelli: 3 si corre e si salta, 2 si sta in piedi con le braccia
larghe, 1 si è seduti o stretti.
"""

from __future__ import annotations

SPAZIO_LUOGO = {
    "salotto": 3, "curva": 3, "vicolo": 3, "lungomare": 3, "pioggia": 3,
    "bar": 2, "balcone": 2, "ufficio": 2, "salumeria": 2,
    "motorino": 1, "pizzeria": 1, "auto": 1, "spogliatoio": 1,
    "computer": 1, "metro": 1, "video": 1,
}

_SALTA = (
    "saltando", "saltano", "corre via", "insegue", "in ginocchio", "issato",
    "di peso", "cammina avanti e indietro", "tira un calcio",
    "si è alzato per andarsene", "sta uscendo di lato", "piegato in due",
    "gamba sollevata",
)
_LARGO = (
    "braccia spalancate", "braccia larghe", "pugni al cielo", "braccia al cielo",
    "cinque in alto", "tirato la maglietta", "mani nei capelli",
    "fronte contro fronte", "si strappano di mano", "mano sul petto",
    "gesticola largo", "indica il cielo", "sopra la testa",
)


def RICHIESTA_AZIONE(azione: str) -> int:
    a = azione.lower()
    if any(p in a for p in _SALTA):
        return 3
    if any(p in a for p in _LARGO):
        return 2
    return 1


def accoppia(azioni: list[str], ambientazioni: list[tuple[str, str]]):
    """Abbina ogni azione a un luogo che la regga davvero.

    Le azioni più esigenti scelgono per prime, e fra i luoghi adatti
    prendono il più stretto che basta: così i pochi spazi ampi restano
    liberi per chi ne ha davvero bisogno. Restituisce le coppie
    (indice azione, indice luogo) nell'ordine dei luoghi.
    """
    liberi = list(range(len(ambientazioni)))
    coppie: list[tuple[int, int]] = []
    for i_azione in sorted(
        range(len(azioni)), key=lambda i: -RICHIESTA_AZIONE(azioni[i])
    ):
        serve = RICHIESTA_AZIONE(azioni[i_azione])
        adatti = [j for j in liberi if SPAZIO_LUOGO[ambientazioni[j][0]] >= serve]
        if not adatti:
            raise SystemExit(
                f"nessun luogo regge questa azione: {azioni[i_azione][:60]}…"
            )
        scelto = min(adatti, key=lambda j: (SPAZIO_LUOGO[ambientazioni[j][0]], j))
        liberi.remove(scelto)
        coppie.append((i_azione, scelto))
    return sorted(coppie, key=lambda c: c[1])
