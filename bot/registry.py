"""Registro dei comandi semplici (un CommandHandler per comando).

Aggiungere un nuovo comando non richiede toccare bot/app.py: basta scrivere
la funzione in un modulo di bot/handlers/ e decorarla con @command(...); il
modulo va poi importato (per side-effect) in bot/app.py insieme agli altri.

I comandi con un flusso a piu' passaggi (come l'intervista) non passano da
qui: usano un ConversationHandler proprio, registrato a parte.
"""

from dataclasses import dataclass
from typing import Awaitable, Callable

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

HandlerCallback = Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]


@dataclass(frozen=True)
class CommandSpec:
    name: str
    callback: HandlerCallback
    description: str = ""


_REGISTRY: list[CommandSpec] = []


def command(name: str, description: str = "") -> Callable[[HandlerCallback], HandlerCallback]:
    def decorator(func: HandlerCallback) -> HandlerCallback:
        _REGISTRY.append(CommandSpec(name=name, callback=func, description=description))
        return func

    return decorator


def all_commands() -> list[CommandSpec]:
    return list(_REGISTRY)


def all_handlers() -> list[CommandHandler]:
    return [CommandHandler(spec.name, spec.callback) for spec in _REGISTRY]
