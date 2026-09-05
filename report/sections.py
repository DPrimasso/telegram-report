"""Sezioni tematiche del gazzettino.

I topic di Telegram sono l'unità con cui il gruppo scrive; le sezioni
sono l'unità con cui il gazzettino si legge, e non è la stessa cosa. Il
gruppo ha ventinove topic: una pagina ordinata per volume è un elenco in
cui il lettore non sa dove finisce un argomento e ne comincia un altro, e
in cui otto leghe di fantacalcio possono prendersi tutti gli articoli
della giornata.

Tre regole, tutte nate guardando le giornate vere:

- **una sezione si guadagna, non si prenota.** Compare in pagina solo se
  ha qualcosa da metterci; il resto scende in "In breve" con l'etichetta
  della propria sezione. È ciò che impedisce a "Sport" di comparire vuota
  nelle giornate in cui nessuno ne parla, e al Napoli di prendersi una
  testata sopra un trafiletto da due messaggi.
- **l'ordine è quello della giornata.** Le sezioni si ordinano per
  messaggi, come già facevano i topic: la pagina segue quello di cui si è
  parlato davvero, non un menù deciso a tavolino.
- **le famiglie non competono.** Le otto leghe sono otto topic con la
  stessa identica forma: otto articoli uguali non sono un giornale, sono
  una schedina. Una famiglia prende un blocco solo, compatto e
  intitolato, dentro la sua sezione, e i suoi topic non concorrono mai
  agli articoli pieni.

Mappa e famiglie si cambiano senza toccare il codice, con REPORT_SECTIONS
e REPORT_SECTION_FAMILIES (vedi _parse_map): un topic nuovo nel gruppo non
è un motivo per aprire un editor.
"""

import os
from dataclasses import dataclass, field

# Sezione di riserva: ci finisce ogni topic che la mappa non nomina, così
# un topic aperto domani entra in pagina lo stesso invece di sparire.
FALLBACK_SECTION = "Altro"

# La mappa di partenza, sui ventinove topic del gruppo. L'ordine qui
# dentro NON è l'ordine in pagina — quello lo decide il volume della
# giornata — ma è l'ordine in cui si cercano le corrispondenze.
DEFAULT_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Napoli", ("SSC Napoli", "Match Day")),
    (
        "Calcio",
        ("Le Altre Squadre", "CalcioMercato", "Nazionali", "Piccion-aiah"),
    ),
    (
        "FantaCalcio",
        (
            "Mantraskarso",
            "FantaSkarso",
            "FANTAMANAGER",
            "FANTACHAMPIONS",
            "Fanta Mondiale",
            # Le otto leghe: stanno anche in DEFAULT_FAMILIES, che decide
            # come vengono impaginate, ma la sezione è comunque questa.
            "Serie Ah",
            "Serie TvB",
            "Seri eCcí",
            "Serie Marte D",
            "Serie Eh",
            "Serie Flu’",
            "Serie X",
            "Serie B per Davide e Paolo",
        ),
    ),
    ("Sport", ("Altri Sport",)),
    (
        "Canale",
        (
            "Orizzonti Azzurri 🏠",
            "Editoriali Bellini",
            "VOCALI (live)",
            "Pagelle Belline",
            "Ko-Fi (SUPPORTO CANALE)",
        ),
    ),
    ("Altro", ("Spam Off Topic", "Benvenuti!", "Arte 🎵 🎬 🎭", "Sanremo")),
)

# Famiglie: gruppi di topic che hanno la stessa forma e vanno raccontati
# insieme invece che uno per uno.
DEFAULT_FAMILIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Le Serie",
        (
            "Serie Ah",
            "Serie TvB",
            "Seri eCcí",
            "Serie Marte D",
            "Serie Eh",
            "Serie Flu’",
            "Serie X",
            "Serie B per Davide e Paolo",
        ),
    ),
)

# Sotto due topic attivi una famiglia non è una famiglia: il blocco
# resterebbe una riga sola sotto un titolo, cioè un trafiletto con una
# cornice intorno. In quel caso i suoi topic tornano in "In breve".
MIN_FAMILY_TOPICS = 2


def _parse_map(raw: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Legge `Nome=topic,topic;Nome=topic` in una mappa.

    Il punto e virgola separa i gruppi, l'uguale il nome dai suoi topic,
    la virgola i topic fra loro. Le voci malformate si saltano invece di
    far fallire il report: una variabile scritta male non deve costare
    l'edizione del giorno."""
    groups: list[tuple[str, tuple[str, ...]]] = []
    for chunk in raw.split(";"):
        name, sep, members = chunk.partition("=")
        name = name.strip()
        if not sep or not name:
            continue
        topics = tuple(t.strip() for t in members.split(",") if t.strip())
        groups.append((name, topics))
    return tuple(groups)


def _normalize(title: str) -> str:
    """I titoli dei topic arrivano da Telegram e da una variabile
    d'ambiente scritta a mano: le due forme dell'apostrofo (Serie Flu’ e
    Serie Flu') sono lo stesso topic per chi legge, e devono esserlo
    anche qui."""
    flattened = title.replace("’", "'").replace("`", "'")
    return " ".join(flattened.split()).casefold()


@dataclass(frozen=True)
class SectionMap:
    """Da titolo di topic a nome di sezione, più le famiglie."""

    sections: tuple[tuple[str, tuple[str, ...]], ...] = DEFAULT_SECTIONS
    families: tuple[tuple[str, tuple[str, ...]], ...] = DEFAULT_FAMILIES
    _by_topic: dict[str, str] = field(default_factory=dict, repr=False)
    _family_by_topic: dict[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        for name, topics in self.sections:
            for topic in topics:
                self._by_topic.setdefault(_normalize(topic), name)
        for name, topics in self.families:
            for topic in topics:
                self._family_by_topic.setdefault(_normalize(topic), name)

    def section_of(self, topic_title: str) -> str:
        """La sezione di un topic; FALLBACK_SECTION se non è mappato.

        Il confronto è esatto (a meno di maiuscole, spazi e apostrofi): un
        "contiene" farebbe finire in FantaCalcio il primo topic nuovo che
        si chiama "Serie A"."""
        return self._by_topic.get(_normalize(topic_title), FALLBACK_SECTION)

    def family_of(self, topic_title: str) -> str:
        """Il nome della famiglia di un topic, o "" se non ne ha una."""
        return self._family_by_topic.get(_normalize(topic_title), "")


def load_section_map() -> SectionMap:
    sections = _parse_map(os.environ.get("REPORT_SECTIONS") or "") or DEFAULT_SECTIONS
    families = (
        _parse_map(os.environ.get("REPORT_SECTION_FAMILIES") or "") or DEFAULT_FAMILIES
    )
    return SectionMap(sections=sections, families=families)
