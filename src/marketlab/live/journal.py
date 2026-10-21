"""Le journal du robot : tout ce qu'il voit, décide et envoie, rangé pour être relu.

Le robot ne connaît que ce contrat. Deux implémentations :

* `JournalMemoire`, ici : tout reste en mémoire, et s'affiche dans le terminal si
  on le demande. Sert aux tests, et à faire tourner le robot avant que la base
  existe ;
* `JournalPostgres` (à venir avec Docker) : la même chose dans PostgreSQL, lue
  en direct par la vue Live, et qui survit à un redémarrage.

Pourquoi un journal aussi détaillé. Un robot qui a perdu de l'argent sans laisser
de trace est inexploitable : on ne saura jamais si la stratégie s'est trompée, si
un garde-fou a mal réagi ou si le courtier a refusé un ordre. Chaque bougie
évaluée laisse donc une ligne, même quand il ne se passe rien.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import pandas as pd

from marketlab.brokers.base import Deplacement, PositionOuverte
from marketlab.pilote import Decision


class Journal(Protocol):
    """Ce que le robot écrit et relit. Observateur du pilote par la même occasion."""

    def demarrage(self, description: dict) -> None: ...

    def bougie(self, instrument: str, echelle: str, bougie: pd.Series) -> None: ...

    def decision(self, decision: Decision) -> None: ...

    def deplacement(
        self, position: PositionOuverte, ancien: float, nouveau: float, raison: Deplacement
    ) -> None: ...

    def incident(self, texte: str) -> None: ...

    def battement(self, instant: pd.Timestamp) -> None: ...

    def marquer_traitee(self, instant: pd.Timestamp) -> None: ...

    def derniere_bougie_traitee(self) -> pd.Timestamp | None: ...

    def arret_demande(self) -> bool: ...

    def arret(self, raison: str) -> None: ...


@dataclass
class JournalMemoire:
    """Journal tenu en mémoire, éventuellement recopié dans le terminal."""

    afficher: bool = False
    evenements: list[tuple[str, str]] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    bougies: list[pd.Series] = field(default_factory=list)
    derniere: pd.Timestamp | None = None
    arret_voulu: bool = False

    def _ecrire(self, nature: str, texte: str) -> None:
        self.evenements.append((nature, texte))
        if self.afficher:
            print(f"  {pd.Timestamp.now(tz='UTC'):%Y-%m-%d %H:%M:%S}  {nature:<11} {texte}", flush=True)

    def demarrage(self, description: dict) -> None:
        self._ecrire("démarrage", ", ".join(f"{k}={v}" for k, v in description.items()))

    def bougie(self, instrument: str, echelle: str, bougie: pd.Series) -> None:
        self.bougies.append(bougie)
        self._ecrire("bougie", f"{instrument} {echelle} {bougie.name:%Y-%m-%d %H:%M} "
                               f"close={bougie['close']}")

    def decision(self, decision: Decision) -> None:
        self.decisions.append(decision)
        texte = decision.issue
        if decision.signal is not None:
            texte += f" — {decision.signal}"
        if decision.detail:
            texte += f" ({decision.detail})"
        self._ecrire("décision", texte)

    def deplacement(
        self, position: PositionOuverte, ancien: float, nouveau: float, raison: Deplacement
    ) -> None:
        self._ecrire("stop", f"{position.identifiant} {raison.value} : {ancien} → {nouveau}")

    def incident(self, texte: str) -> None:
        self._ecrire("incident", texte)

    def battement(self, instant: pd.Timestamp) -> None:
        pass

    def marquer_traitee(self, instant: pd.Timestamp) -> None:
        self.derniere = instant

    def derniere_bougie_traitee(self) -> pd.Timestamp | None:
        return self.derniere

    def arret_demande(self) -> bool:
        return self.arret_voulu

    def arret(self, raison: str) -> None:
        self._ecrire("arrêt", raison)
