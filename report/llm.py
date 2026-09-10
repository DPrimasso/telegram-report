"""Unico punto di contatto con l'API OpenAI.

Qui sta la sola cosa che cambia da un modello all'altro e che il resto del
report non deve sapere: quali parametri il modello di turno accetta. I
modelli di ragionamento (la famiglia gpt-5, le serie o*) rifiutano con un
400 qualunque `temperature` diverso dal default, mentre gpt-4o e gpt-4.1 la
accettano. Chi chiama continua quindi a dichiarare la temperatura che
vorrebbe — resta l'intenzione giusta se un domani si torna a un modello che
la regola — e qui si decide se ha senso spedirla davvero.
"""

from openai import BadRequestError

from report import spesa

# Prefissi dei modelli che accettano solo la temperatura di default. Il
# confronto è per prefisso perché i nomi portano suffissi di ogni tipo
# (gpt-5.6-luna, o4-mini, ...). Sbagliare per eccesso qui non fa danni: si
# rinuncia a una regolazione, non si rompe la chiamata.
_FIXED_TEMPERATURE_PREFIXES = ("gpt-5", "o1", "o3", "o4")

# Modelli che hanno rifiutato la temperatura pur non comparendo nell'elenco
# qui sopra: un elenco di nomi invecchia, un 400 no. Vedi complete().
_rejected_temperature: set[str] = set()


def accepts_temperature(model: str) -> bool:
    name = model.strip().lower()
    return name not in _rejected_temperature and not name.startswith(
        _FIXED_TEMPERATURE_PREFIXES
    )


def _create(client, model: str, prompt: str, temperature: float | None):
    extra = {} if temperature is None else {"temperature": temperature}
    return client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        **extra,
    )


def complete(
    client, model: str, prompt: str, temperature: float | None = None
) -> str:
    """Manda un prompt al modello e restituisce il testo della risposta."""
    with_temperature = temperature is not None and accepts_temperature(model)
    try:
        response = _create(
            client, model, prompt, temperature if with_temperature else None
        )
    except BadRequestError as error:
        # Rete di sicurezza per i modelli usciti dopo questo codice: se il
        # rifiuto riguarda proprio la temperatura, la si toglie e si riprova
        # una volta sola. Il modello finisce fra quelli che non la vogliono,
        # perché di chiamate il report ne fa una per topic e non ha senso
        # sbagliare tutte allo stesso modo.
        if not with_temperature or "temperature" not in str(error).lower():
            raise
        _rejected_temperature.add(model.strip().lower())
        response = _create(client, model, prompt, None)
    # Qui passa ogni chiamata del gazzettino, ed è l'unico posto in cui la
    # risposta esiste ancora intera: da lì in su torna solo il testo, e i
    # token che è costato si perderebbero. Il 400 di sopra non si registra
    # perché una chiamata rifiutata non si paga.
    spesa.registra(model, response)
    return (response.choices[0].message.content or "").strip()
