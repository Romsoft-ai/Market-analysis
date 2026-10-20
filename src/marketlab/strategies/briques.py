"""Pièces réutilisables par plusieurs stratégies.

Une règle qui sert à deux stratégies n'est écrite qu'une fois, ici. Deux copies
d'une même règle finissent toujours par diverger, et la comparaison entre les
stratégies qui les portent cesse alors d'être honnête sans que rien ne le signale.

Ces fonctions ne décident rien : elles calculent une colonne ou assemblent un
signal. La décision reste dans le fichier de chaque stratégie.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from marketlab.data.temps import dans_sessions, serveur_vers_utc
from marketlab.strategies.base import Sens, Signal


def colonne_session(index_serveur: pd.DatetimeIndex, sessions: Sequence[str]) -> np.ndarray:
    """Vrai pour chaque bougie située dans l'une des sessions demandées.

    Les sessions sont évaluées en heure LOCALE de chaque place, après conversion
    des horodatages serveur en UTC réel. Un filtre appliqué directement à l'heure
    serveur serait décalé d'une heure la moitié de l'année.

    Pourquoi filtrer par session. Un backtest sans ce filtre prend des positions à
    deux heures du matin, moment où l'opérateur dort et ne passerait aucun ordre.
    Une simulation qui exécute des trades impossibles ne mesure pas la stratégie.
    """
    utc = serveur_vers_utc(index_serveur)
    return dans_sessions(utc, list(sessions)).to_numpy()


def signal_a_ratio(
    sens: Sens, entree: float, stop: float, ratio: float, raison: str
) -> Signal | None:
    """Assemble un signal dont l'objectif est un multiple fixe du risque.

    Renonce si la géométrie est dégénérée. Cas réel : la clôture coïncide avec le
    creux qui sert de stop. La distance au stop est alors nulle, et la taille de
    position calculée par la couche de risque exploserait.
    """
    risque = abs(entree - stop)
    if risque <= 0:
        return None

    if sens is Sens.ACHAT:
        objectif = entree + ratio * risque
    else:
        objectif = entree - ratio * risque

    return Signal(sens=sens, entree=entree, stop=stop, objectif=objectif, raison=raison)
