"""Ouverture et fermeture d'une session MetaTrader 5.

Rappel de fonctionnement : le module Python ne parle pas au courtier, il pilote
le **terminal MT5 installé localement**. ``initialize()`` lance donc le terminal
s'il n'est pas déjà ouvert, puis s'y connecte avec les identifiants fournis.

Pourquoi un gestionnaire de contexte (``with``) plutôt qu'un simple appel :
si le code plante au milieu d'un traitement, ``shutdown()`` est quand même
appelé. Sans ça, le terminal reste dans un état incohérent et la connexion
suivante échoue avec un message qui n'a rien à voir.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import MetaTrader5 as mt5

from marketlab.config import BrokerConfig

# Le terminal peut mettre du temps à démarrer la première fois.
_TIMEOUT_MS = 60_000


class MT5Error(RuntimeError):
    """Échec d'une opération MetaTrader 5."""


def _fail(action: str) -> MT5Error:
    """Construit une erreur enrichie du dernier message renvoyé par MT5."""
    code, message = mt5.last_error()
    return MT5Error(f"{action} a échoué — code {code} : {message}")


@contextmanager
def mt5_session(broker: BrokerConfig) -> Iterator[type[mt5]]:
    """Ouvre une session MT5 sur le compte décrit par ``broker``.

    Utilisation :
        >>> from marketlab.config import get_broker
        >>> with mt5_session(get_broker("demo")) as api:
        ...     print(api.account_info().balance)
    """
    initialized = mt5.initialize(
        path=str(broker.terminal_path),
        login=broker.login,
        password=broker.password,
        server=broker.server,
        timeout=_TIMEOUT_MS,
    )
    if not initialized:
        raise _fail(f"La connexion au compte {broker.login} ({broker.server})")

    # initialize() peut réussir tout en laissant le terminal déconnecté du serveur.
    terminal = mt5.terminal_info()
    if terminal is None or not terminal.connected:
        mt5.shutdown()
        raise MT5Error(
            f"Le terminal a démarré mais n'est pas connecté au serveur "
            f"{broker.server!r}.\n"
            f"  -> Vérifie le nom du serveur dans .env (il est sensible à la casse).\n"
            f"  -> Vérifie que le compte n'a pas expiré."
        )

    try:
        yield mt5
    finally:
        mt5.shutdown()


def reconnecter(broker: BrokerConfig) -> None:
    """Referme puis rouvre la session, après une perte de connexion.

    Utilisé par la boucle du robot, qui garde le même module `mt5` : les objets
    qui en dépendent (courtier, flux) restent valables après la reconnexion.
    """
    mt5.shutdown()
    if not mt5.initialize(
        path=str(broker.terminal_path),
        login=broker.login,
        password=broker.password,
        server=broker.server,
        timeout=_TIMEOUT_MS,
    ):
        raise _fail(f"La reconnexion au compte {broker.login} ({broker.server})")
    terminal = mt5.terminal_info()
    if terminal is None or not terminal.connected:
        raise MT5Error(f"Reconnecté au terminal, mais pas au serveur {broker.server!r}")
