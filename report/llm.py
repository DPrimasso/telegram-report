"""Unico punto di contatto con l'API OpenAI.

Qui sta la sola cosa che cambia da un modello all'altro e che il resto del
report non deve sapere: quali parametri il modello di turno accetta. I
modelli di ragionamento (la famiglia gpt-5, le serie o*) rifiutano con un
400 qualunque `temperature` diverso dal default e in cambio accettano
`reasoning_effort`; gpt-4o e gpt-4.1 fanno l'opposto. Chi chiama continua
quindi a dichiarare la temperatura che vorrebbe — resta l'intenzione giusta
se un domani si torna a un modello che la regola — e qui si decide che cosa
ha senso spedire davvero.
"""

from openai import BadRequestError

# Prefissi dei modelli di ragionamento. Il confronto è per prefisso perché i
# nomi portano suffissi di ogni tipo (gpt-5.6-luna, o4-mini, ...); per quelli
# che sfuggono all'elenco resta la rete di sicurezza in complete().
_REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")

# Parametri facoltativi: il report funziona anche senza, quindi davanti a un
# rifiuto si tolgono invece di far fallire la giornata.
_OPTIONAL_PARAMS = ("temperature", "reasoning_effort")

# Parametri che un dato modello ha rifiutato: un elenco di nomi invecchia,
# un 400 no. Vedi complete().
_rejected: dict[str, set[str]] = {}

# Quanto far ragionare i modelli che lo permettono. È una proprietà della
# corsa e non della singola chiamata: passarlo per parametro vorrebbe dire
# aggiungerlo alla firma di ogni funzione di summarize.py, nessuna delle
# quali ha motivo di scegliere un valore diverso. Lo imposta main.py
# all'avvio, leggendolo dalla configurazione.
_reasoning_effort: str | None = None


def configure(reasoning_effort: str | None) -> None:
    global _reasoning_effort
    _reasoning_effort = (reasoning_effort or "").strip() or None


def _key(model: str) -> str:
    return model.strip().lower()


def is_reasoning_model(model: str) -> bool:
    return _key(model).startswith(_REASONING_PREFIXES)


def _accepts(model: str, param: str) -> bool:
    if param in _rejected.get(_key(model), ()):
        return False
    reasoning = is_reasoning_model(model)
    # La temperatura è l'unica cosa che i due tipi di modello si contendono:
    # o si regola quella, o si regola quanto ragionano.
    return reasoning if param == "reasoning_effort" else not reasoning


def _create(client, model: str, prompt: str, params: dict):
    return client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        **params,
    )


def _offending_param(error: BadRequestError, sent: dict) -> str | None:
    """Il parametro, fra quelli facoltativi appena spediti, di cui l'API si
    lamenta. None se il 400 parla d'altro (un modello inesistente, per
    dire) e va quindi lasciato risalire."""
    text = str(error).lower()
    return next((p for p in _OPTIONAL_PARAMS if p in sent and p in text), None)


def complete(client, model: str, prompt: str, temperature: float | None = None) -> str:
    """Manda un prompt al modello e restituisce il testo della risposta."""
    params: dict[str, object] = {}
    if temperature is not None and _accepts(model, "temperature"):
        params["temperature"] = temperature
    if _reasoning_effort and _accepts(model, "reasoning_effort"):
        params["reasoning_effort"] = _reasoning_effort

    # Rete di sicurezza per i modelli usciti dopo questo codice: se il
    # rifiuto riguarda un parametro facoltativo lo si toglie e si riprova,
    # ricordandoselo per le chiamate successive (di chiamate il report ne fa
    # una per topic, non ha senso sbagliarle tutte allo stesso modo).
    while True:
        try:
            response = _create(client, model, prompt, params)
            break
        except BadRequestError as error:
            param = _offending_param(error, params)
            if param is None:
                raise
            _rejected.setdefault(_key(model), set()).add(param)
            del params[param]

    return (response.choices[0].message.content or "").strip()
