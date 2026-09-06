"""Misura quanti token spedisce e riceve un report, senza chiamare OpenAI.

Non stima: intercetta i prompt VERI costruiti da report/summarize.py e da
report/vignetta.py su una giornata simulata, e li conta. Le uniche
approssimazioni sono dichiarate sotto — il rapporto caratteri/token e la
lunghezza delle risposte, che è presa dai limiti scritti nei prompt.

Due profili, perché il gruppo ha due tipi di giornata e costano in modo
molto diverso:

- una giornata normale sta sotto la soglia di chunking e ogni topic è una
  chiamata sola;
- una giornata di partita no. Il 5 settembre Match Day da solo ha fatto
  2801 messaggi: sopra i 40.000 caratteri il riassunto diventa
  map-reduce, e quel topic da solo costa quanto tutto il resto insieme.

    python3 costo.py
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from report import llm, summarize, vignetta
from report.newspaper import topics_needing_body
from report.vignetta import Biblioteca

# Prezzi del modello in uso (gpt-5.6-luna), dollari per milione di token.
# Sono quelli che avevamo assunto: se cambiano, si cambiano qui.
P_IN, P_OUT = 0.20, 1.20

# La cache dei prompt. Su gpt-5.6 il prefisso già visto costa il 10% del
# normale, la prima volta che lo si stabilisce costa il 125%, e sotto i
# 1024 token non si attiva affatto — il prefisso viene riconosciuto a
# scatti di 128. La cache dura più a lungo di una nostra edizione intera,
# quindi dentro una run tutte le chiamate si trovano quella di prima.
CACHE_MINIMA = 1024
CACHE_SCATTO = 128
CACHE_LETTURA = 0.10
CACHE_SCRITTURA = 1.25

# Lunghezza media di un messaggio di chat, in caratteri. Presa alta di
# proposito: sovrastimare il costo è l'errore giusto da fare.
CARATTERI_PER_MESSAGGIO = 62
# Rapporto caratteri/token per l'italiano con i tokenizzatori OpenAI.
CARATTERI_PER_TOKEN = 3.5

AUTORI = ["Ciro", "Gennaro", "Peppe", "Ugo", "Salvo", "Rino", "Tonino", "Mimmo"]

# Giornata normale: i numeri che avevamo guardato a suo tempo.
NORMALE = [
    ("Mantraskarso", 132), ("Le Altre Squadre", 113), ("Spam Off Topic", 113),
    ("Match Day", 87), ("Serie Flu'", 78), ("Serie TvB", 64), ("Serie Eh", 52),
    ("FantaSkarso", 51), ("Editoriali Bellini", 31), ("Seri eCci", 26),
    ("Serie X", 21), ("Ko-Fi (SUPPORTO CANALE)", 17), ("Altri Sport", 9),
    ("CalcioMercato", 6),
]

# Giornata di partita: i numeri VERI del 5 settembre 2026, dal log della
# run di prova.
PARTITA = [
    ("Match Day", 2801), ("Le Altre Squadre", 395), ("SSC Napoli", 68),
    ("VOCALI (live)", 55), ("Serie Ah", 45), ("Pagelle Belline", 35),
    ("Ko-Fi (SUPPORTO CANALE)", 25), ("Mantraskarso", 20),
    ("Spam Off Topic", 16), ("Altri Sport", 10), ("Serie Marte D", 3),
    ("Serie Eh", 3), ("Seri eCci", 1),
]


class Messaggio:
    """Il minimo che summarize.py e vignetta.py leggono di un messaggio."""

    def __init__(self, author, timestamp, text):
        self.author, self.timestamp, self.text = author, timestamp, text


def giornata(topics):
    random.seed(7)
    inizio = datetime(2026, 9, 5, 8, 0)
    out = []
    for titolo, quanti in topics:
        messaggi = []
        for i in range(quanti):
            testo = "".join(
                random.choice("abcdefghilmnopqrstuvz ")
                for _ in range(CARATTERI_PER_MESSAGGIO)
            )
            messaggi.append(
                Messaggio(random.choice(AUTORI), inizio + timedelta(seconds=i * 20), testo)
            )
        out.append((titolo, messaggi))
    return out


def _prefisso_comune(a: str, b: str) -> int:
    """Quanti caratteri iniziali hanno in comune due prompt."""
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


class Contatore:
    """Sostituisce llm.complete: registra il prompt e restituisce una
    risposta della lunghezza che il prompt chiede davvero.

    Tiene anche il conto della cache, che non è un dettaglio: il blocco di
    regole è identico a ogni chiamata, e se le chiamate lo condividono come
    PREFISSO viene fatturato al 10%. Modellarlo qui è l'unico modo di
    misurare quel risparmio invece di dichiararlo."""

    def __init__(self):
        self.chiamate = []
        self.etichetta = "?"
        self._visti: list[str] = []

    def __call__(self, client, model, prompt, temperature=None):
        risposta = self._risposta()
        cache = self._quanto_in_cache(prompt)
        self.chiamate.append(
            (self.etichetta, len(prompt), len(risposta), cache)
        )
        self._visti.append(prompt)
        return risposta

    def _quanto_in_cache(self, prompt: str) -> int:
        """Caratteri di questo prompt già visti come prefisso, oggi.

        Zero quando il prefisso condiviso non arriva alla soglia: è
        esattamente il caso in cui ci trovavamo prima di spostare le
        regole in testa, con tre prefissi diversi e tre cache che non si
        incontravano mai."""
        if not self._visti:
            return 0
        comune = max(_prefisso_comune(prompt, v) for v in self._visti)
        token_comuni = comune / CARATTERI_PER_TOKEN
        if token_comuni < CACHE_MINIMA:
            return 0
        # Il prefisso viene riconosciuto a scatti, non al carattere.
        scatti = int(token_comuni // CACHE_SCATTO) * CACHE_SCATTO
        return int(scatti * CARATTERI_PER_TOKEN)

    def _risposta(self):
        if self.etichetta == "articolo":
            # 3 capoversi, 600-900 caratteri: prendo il tetto.
            return (
                "FATTO: un fatto qualsiasi della giornata\n"
                "TITOLO: " + "x" * 60 + "\n"
                "SOMMARIO: " + "x" * 150 + "\n"
                "TESTO: " + "x" * 900 + "\n"
                "CITAZIONE: " + "x" * 80 + " | Ciro"
            )
        if self.etichetta == "apertura":
            # 4 capoversi, 900-1200 caratteri: idem.
            return (
                "FATTO: il fatto principale\nSEZIONE: Napoli\n"
                "TITOLO: " + "x" * 60 + "\n"
                "SOMMARIO: " + "x" * 150 + "\n"
                "TESTO: " + "x" * 1200 + "\n"
                "CITAZIONE: " + "x" * 80 + " | Ciro\n"
                "TONO: battibecco\n"
                "BATTUTA: " + "x" * 70 + " | Ciro"
            )
        if self.etichetta == "brevi":
            return "\n".join(f"Tema {i} | " + "x" * 60 for i in range(9))
        if self.etichetta == "riassunto":
            return "\n".join("• " + "x" * 120 for _ in range(6))
        if self.etichetta == "vignetta":
            return "TONO: battibecco\nBATTUTA: " + "x" * 70 + " | Ciro"
        return "una frase qualsiasi del gruppo | Ciro"


def token(caratteri: float) -> float:
    return caratteri / CARATTERI_PER_TOKEN


def misura(nome: str, topics) -> tuple[float, float, int]:
    dati = giornata(topics)
    tutti = [(t, m) for t, messaggi in dati for m in messaggi]
    contatore = Contatore()
    originale = llm.complete
    llm.complete = contatore
    summarize.llm.complete = contatore
    vignetta.llm.complete = contatore

    try:
        # Stessa separazione che fa main.py: pezzo pieno solo a chi in
        # pagina ne avrà uno, un titolo agli altri.
        con_corpo = topics_needing_body([(t, len(m), "") for t, m in dati])

        articoli = []
        ordinati = sorted(dati, key=lambda t: len(t[1]), reverse=True)
        for titolo, messaggi in ordinati:
            if titolo not in con_corpo:
                continue
            # I riassunti parziali del map-reduce passano dallo stesso
            # llm.complete: cambio etichetta prima e dopo per distinguerli.
            contatore.etichetta = (
                "riassunto"
                if len("".join(m.text for m in messaggi)) > summarize.MAX_TRANSCRIPT_CHARS
                else "articolo"
            )
            h, d, b, _q = summarize.write_topic_article(
                None, "gpt-5.6-luna", titolo, messaggi,
                written_so_far=[(a[0], a[1]) for a in articoli],
            )
            articoli.append((h, b))

        minori = [(t, m) for t, m in ordinati if t not in con_corpo]
        if minori:
            contatore.etichetta = "brevi"
            summarize.write_brief_headlines(
                None, "gpt-5.6-luna", minori,
                written_so_far=[(a[0], a[1]) for a in articoli],
            )

        contatore.etichetta = "apertura"
        summarize.write_lead_story(
            None, "gpt-5.6-luna", tutti,
            page_headlines=[a[0] for a in articoli],
            sections=["Napoli", "Calcio", "FantaCalcio", "Canale", "Sport", "Altro"],
            articoli=[(f"Topic {i}", h, "un sommario", b, 100)
                      for i, (h, b) in enumerate(articoli)],
            toni=[("battibecco", "due che non sono d'accordo")],
        )

        # La vignetta non ha più una chiamata sua: esce dall'apertura.
    finally:
        llm.complete = originale
        summarize.llm.complete = originale
        vignetta.llm.complete = originale

    per_tipo: dict[str, list] = {}
    for etichetta, entrata, uscita, cache in contatore.chiamate:
        per_tipo.setdefault(etichetta, []).append((entrata, uscita, cache))

    messaggi_totali = sum(q for _, q in topics)
    print(f"\n{nome}: {messaggi_totali} messaggi in {len(topics)} topic attivi\n")
    print(
        f"{'chiamata':<12}{'n':>4}{'token in':>11}{'in cache':>10}"
        f"{'token out':>11}{'costo':>9}"
    )
    print("-" * 57)
    tot_in = tot_cache = tot_out = costo = 0.0
    for etichetta, valori in sorted(per_tipo.items()):
        ti = sum(token(v[0]) for v in valori)
        tc = sum(token(v[2]) for v in valori)
        to = sum(token(v[1]) for v in valori)
        tot_in += ti
        tot_cache += tc
        tot_out += to
        # Il prefisso in cache si paga un decimo; il resto pieno. La
        # scrittura della cache la paga la prima chiamata che stabilisce
        # quel prefisso, ed è già dentro `ti - tc`.
        c = ((ti - tc) + tc * CACHE_LETTURA) / 1e6 * P_IN + to / 1e6 * P_OUT
        costo += c
        print(f"{etichetta:<12}{len(valori):>4}{ti:>11,.0f}{tc:>10,.0f}{to:>11,.0f}{c:>9.4f}")
    # La prima chiamata di ogni famiglia di prefisso paga la scrittura in
    # cache al 125%: la si approssima come un sovrapprezzo sul primo
    # prefisso stabilito.
    prefissi = {e for e, v in per_tipo.items() if any(x[2] for x in v)}
    if prefissi:
        scrittura = token(max(
            (x[2] for v in per_tipo.values() for x in v), default=0
        )) * (CACHE_SCRITTURA - 1) / 1e6 * P_IN
        costo += scrittura
    print("-" * 57)
    print(
        f"{'TOTALE':<12}{len(contatore.chiamate):>4}{tot_in:>11,.0f}"
        f"{tot_cache:>10,.0f}{tot_out:>11,.0f}{costo:>9.4f}"
    )
    return costo, messaggi_totali, len(contatore.chiamate)


def main() -> None:
    costo_n, msg_n, ch_n = misura("GIORNATA NORMALE", NORMALE)
    costo_p, msg_p, ch_p = misura("GIORNATA DI PARTITA (5 settembre, dati veri)", PARTITA)

    print("\n" + "=" * 62)
    print("QUANTO COSTA IL GAZZETTINO")
    print("=" * 62)
    anno = "all'anno"
    print(f"{'':<28}{'per edizione':>14}{'al mese':>10}{anno:>10}")
    print("-" * 62)
    for etichetta, c in (("solo giornate normali", costo_n),
                         ("solo giornate di partita", costo_p)):
        print(f"{etichetta:<28}{c:>14.4f}{c * 30:>10.2f}{c * 365:>10.2f}")

    # Il calendario vero: in Serie A si gioca una-due volte a settimana, e
    # nelle settimane di coppa tre. Prendo due giornate di partita a
    # settimana, cioè circa nove al mese.
    partite_al_mese = 9
    mensile = costo_p * partite_al_mese + costo_n * (30 - partite_al_mese)
    print("-" * 62)
    print(f"{'mix realistico (9 partite/mese)':<28}{'':>14}{mensile:>10.2f}{mensile * 12:>10.2f}")
    print()
    print(f"Chiamate per edizione: {ch_n} in una giornata normale, {ch_p} in una di partita.")
    print(f"Prezzi usati: ${P_IN}/M token in ingresso, ${P_OUT}/M in uscita.")


if __name__ == "__main__":
    main()
