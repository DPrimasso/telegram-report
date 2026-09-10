"""Il conto dell'edizione: quanto è costato scrivere il gazzettino di oggi.

`costo.py` fa una stima a tavolino, su una giornata inventata e senza
chiamare OpenAI: serve a decidere se una scelta di prompt conviene *prima*
di farla. Questo modulo fa l'opposto e non stima niente — conta i token che
l'API dichiara a ogni risposta, mentre il giornale si scrive, e a fine
serata li trasforma in dollari.

I due file guardano lo stesso numero da due parti, quindi il listino sta
scritto una volta sola: qui. Se i prezzi cambiano si cambiano in questo
punto, e la stima e il conto restano d'accordo.

Il tassametro è unico e sta a livello di modulo perché le chiamate al
modello partono da sei posti diversi, in fondo a summarize.py e a
vignetta.py: passarselo di funzione in funzione avrebbe voluto dire un
parametro in più in dieci firme per una nota a margine. Il programma fa
un'edizione per processo, e questo è il conto di quell'edizione.
"""

from __future__ import annotations

import html
import time
from dataclasses import dataclass
from datetime import date

# Listino di gpt-5.6-luna, in dollari per milione di token.
PREZZO_INPUT = 0.20
PREZZO_OUTPUT = 1.20

# Il prefisso di prompt già visto costa un decimo. Qui non lo modelliamo
# come fa costo.py: la cache di OpenAI si attiva da sola e l'API dichiara
# quanti token ha riusato, chiamata per chiamata. Resta solo lo sconto da
# applicare a quelli.
SCONTO_CACHE = 0.10

# I prezzi qui sopra valgono per questa famiglia di modelli, e basta. Se
# OPENAI_MODEL punta altrove i token restano veri e i dollari no: il conto
# lo dice invece di far finta di niente.
FAMIGLIA_A_LISTINO = "gpt-5."


@dataclass(frozen=True)
class Listino:
    """Quanto costano mille chilometri di token."""

    input: float = PREZZO_INPUT
    output: float = PREZZO_OUTPUT
    sconto_cache: float = SCONTO_CACHE

    @property
    def predefinito(self) -> bool:
        """Vero finché nessuno ha corretto i prezzi dall'ambiente. Serve a
        non ripetere ogni notte un avviso a chi lo ha già ascoltato."""
        return self.input == PREZZO_INPUT and self.output == PREZZO_OUTPUT

    def costo(self, ingresso: int, cache: int, uscita: int) -> float:
        # I token letti dalla cache sono un sottoinsieme di quelli in
        # ingresso, non un di più: si pagano scontati, gli altri pieni.
        pieni = max(ingresso - cache, 0)
        return (
            (pieni + cache * self.sconto_cache) / 1e6 * self.input
            + uscita / 1e6 * self.output
        )


@dataclass
class Chiamata:
    fase: str
    modello: str
    ingresso: int
    cache: int
    uscita: int
    # Falso quando la risposta è arrivata senza il blocco `usage`. La
    # chiamata è stata fatta e pagata comunque: contarla come gratis
    # sarebbe il tipo di errore che fa sembrare tutto più economico di
    # quello che è, quindi la si tiene e la si dichiara.
    contata: bool = True


def _cached_tokens(dettagli) -> int:
    """I token riusati dalla cache, comunque l'SDK li rappresenti.

    Nelle versioni recenti `prompt_tokens_details` è un oggetto, in altre
    un dizionario, e in altre ancora non c'è: qui interessa il numero, non
    la forma in cui arriva."""
    if dettagli is None:
        return 0
    if isinstance(dettagli, dict):
        return int(dettagli.get("cached_tokens") or 0)
    return int(getattr(dettagli, "cached_tokens", 0) or 0)


class Tassametro:
    """Tiene il conto delle chiamate al modello di questa edizione."""

    def __init__(self) -> None:
        self.chiamate: list[Chiamata] = []
        # Sotto quale voce del conto finiscono le prossime chiamate. La
        # imposta main.py mentre avanza, negli stessi punti in cui stampa
        # a che punto è: sono le stesse tappe.
        self.fase = "altro"
        self.inizio = time.monotonic()

    def registra(self, modello: str, risposta) -> None:
        uso = getattr(risposta, "usage", None)
        if uso is None:
            self.chiamate.append(Chiamata(self.fase, modello, 0, 0, 0, contata=False))
            return
        ingresso = int(getattr(uso, "prompt_tokens", 0) or 0)
        uscita = int(getattr(uso, "completion_tokens", 0) or 0)
        cache = _cached_tokens(getattr(uso, "prompt_tokens_details", None))
        self.chiamate.append(Chiamata(self.fase, modello, ingresso, cache, uscita))

    @property
    def vuoto(self) -> bool:
        return not self.chiamate

    def totali(self) -> tuple[int, int, int]:
        return (
            sum(c.ingresso for c in self.chiamate),
            sum(c.cache for c in self.chiamate),
            sum(c.uscita for c in self.chiamate),
        )

    def costo(self, listino: Listino) -> float:
        return sum(
            listino.costo(c.ingresso, c.cache, c.uscita) for c in self.chiamate
        )

    def per_fase(self, listino: Listino) -> list[tuple[str, int, float]]:
        """Le voci del conto, dalla più cara alla meno cara."""
        voci: dict[str, list[Chiamata]] = {}
        for chiamata in self.chiamate:
            voci.setdefault(chiamata.fase, []).append(chiamata)
        righe = [
            (
                fase,
                len(gruppo),
                sum(listino.costo(c.ingresso, c.cache, c.uscita) for c in gruppo),
            )
            for fase, gruppo in voci.items()
        ]
        return sorted(righe, key=lambda r: r[2], reverse=True)

    def modelli(self) -> list[str]:
        return sorted({c.modello for c in self.chiamate})

    def non_contate(self) -> int:
        return sum(1 for c in self.chiamate if not c.contata)

    def durata(self) -> float:
        """Secondi dall'avvio del programma, non dalla prima chiamata: chi
        legge il conto vuole sapere quanto ha aspettato l'edizione."""
        return time.monotonic() - self.inizio


# Il tassametro dell'edizione in corso.
tassametro = Tassametro()


def fase(nome: str) -> None:
    """Da qui in avanti le chiamate al modello finiscono sotto questa voce."""
    tassametro.fase = nome


def registra(modello: str, risposta) -> None:
    tassametro.registra(modello, risposta)


def _numero(n: float) -> str:
    """Migliaia col punto, come si scrivono in italiano."""
    return f"{n:,.0f}".replace(",", ".")


def _soldi(valore: float, decimali: int = 4) -> str:
    return "$" + f"{valore:.{decimali}f}".replace(".", ",")


def _durata(secondi: float) -> str:
    minuti, resto = divmod(int(secondi), 60)
    return f"{minuti}m {resto:02d}s" if minuti else f"{resto}s"


def _chiamate(quante: int) -> str:
    return "chiamata" if quante == 1 else "chiamate"


def riga_di_log(tassametro: Tassametro, listino: Listino) -> str:
    """Una riga sola per i log di GitHub Actions, che non sono un giornale."""
    ingresso, cache, uscita = tassametro.totali()
    quante = len(tassametro.chiamate)
    return (
        f"Questa edizione è costata {_soldi(tassametro.costo(listino))}: "
        f"{quante} {_chiamate(quante)}, {_numero(ingresso)} token in "
        f"ingresso (di cui {_numero(cache)} dalla cache), "
        f"{_numero(uscita)} in uscita."
    )


def riepilogo(
    tassametro: Tassametro,
    listino: Listino,
    giorno: date,
    modello: str,
) -> str:
    """Il conto come arriva su Telegram, in HTML."""
    costo = tassametro.costo(listino)
    ingresso, cache, uscita = tassametro.totali()
    quota_cache = f" ({cache / ingresso:.0%} del totale)" if ingresso else ""
    # Il nome del modello è l'unico pezzo di testo libero che finisce nel
    # messaggio: arriva da OPENAI_MODEL, e un carattere sbagliato lì
    # renderebbe l'HTML illeggibile a Telegram, che rifiuterebbe l'invio.
    modello = html.escape(modello)

    righe = [
        f"🧾 <b>Il conto dell'edizione</b> — giornata del "
        f"{giorno.strftime('%d/%m/%Y')}",
        "",
        f"Spesi <b>{_soldi(costo)}</b> per scrivere il gazzettino.",
        f"A questo ritmo sono {_soldi(costo * 30, 2)} al mese, "
        f"{_soldi(costo * 365, 2)} all'anno.",
        "",
    ]

    voci = tassametro.per_fase(listino)
    larghezza = max((len(fase) for fase, _, _ in voci), default=1)
    tabella = "\n".join(
        f"{fase:<{larghezza}}  {quante:>2}  {_soldi(quanto):>8}"
        for fase, quante, quanto in voci
    )
    righe.append(f"<pre>{tabella}</pre>")

    righe += [
        f"{_numero(ingresso)} token in ingresso, di cui "
        f"{_numero(cache)} riletti dalla cache{quota_cache}.",
        f"{_numero(uscita)} token in uscita.",
        f"{len(tassametro.chiamate)} {_chiamate(len(tassametro.chiamate))} a "
        f"<code>{modello}</code> in {_durata(tassametro.durata())}.",
    ]

    # Due avvertenze, quando servono. Un conto che non torna deve dirlo da
    # solo: chi lo legge non ha modo di accorgersene guardando la cifra.
    # La prima vale solo finché i prezzi sono quelli di serie: chi li ha
    # già corretti per il suo modello sa quello che sta facendo, e non ha
    # bisogno di sentirselo ripetere tutte le notti.
    fuori_listino = not any(
        m.startswith(FAMIGLIA_A_LISTINO) for m in tassametro.modelli()
    )
    if fuori_listino and listino.predefinito:
        righe += [
            "",
            f"⚠️ Il listino in <code>report/spesa.py</code> è quello di "
            f"<code>{FAMIGLIA_A_LISTINO}*</code>: con <code>{modello}</code> "
            f"i token sono giusti ma i dollari no. Si correggono con "
            f"<code>PREZZO_INPUT</code> e <code>PREZZO_OUTPUT</code>.",
        ]
    scoperte = tassametro.non_contate()
    if scoperte:
        tornata = "è tornata" if scoperte == 1 else "sono tornate"
        righe += [
            "",
            f"⚠️ {scoperte} {_chiamate(scoperte)} {tornata} senza il "
            f"conteggio dei token: la spesa vera è più alta di così.",
        ]

    return "\n".join(righe)
