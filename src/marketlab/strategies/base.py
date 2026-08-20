"""Le contrat commun à toutes les stratégies.

C'est la pièce qui rend les quatre stratégies du projet (trois baselines + SMC)
interchangeables. Une stratégie reçoit des bougies clôturées et renvoie soit rien,
soit un signal. Rien d'autre.

Deux règles inscrites dans le code, pas seulement dans la documentation :

1. **Une stratégie ne calcule JAMAIS la taille d'une position.** Elle dit *où*
   entrer et *où* sortir ; c'est la couche de risque (étape 6) qui dit *combien*.
   Une stratégie a le droit de se tromper — c'est son métier. Le risque, non.

2. **Une stratégie ne voit jamais l'avenir.** La méthode `evaluer` reçoit un
   historique déjà tronqué à la dernière bougie clôturée : les bougies futures sont
   physiquement absentes de l'objet reçu. On ne peut donc pas tricher par
   distraction, ce qui est l'erreur la plus fréquente en backtest.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

import pandas as pd

# Colonnes attendues dans toute série de bougies manipulée par le projet.
COLONNES_BOUGIES = ("open", "high", "low", "close")


class Sens(Enum):
    """Direction d'un signal."""

    ACHAT = "achat"
    VENTE = "vente"


class SignalInvalide(ValueError):
    """Un signal dont les prix sont incohérents avec son sens."""


@dataclass(frozen=True)
class Signal:
    """Une intention de position : où entrer, où sortir en perte, où sortir en gain.

    Volontairement immuable : un signal émis ne se modifie pas. Si les conditions
    changent, la stratégie en émet un autre.
    """

    sens: Sens
    entree: float
    stop: float
    objectif: float
    # Trace lisible de la raison du signal. Sert au journal d'audit et au
    # débogage : sans elle, impossible de comprendre après coup pourquoi le bot
    # a agi.
    raison: str = ""

    def __post_init__(self) -> None:
        """Vérifie la cohérence des prix. Un stop du mauvais côté serait grave.

        Sans ce contrôle, une stratégie boguée pourrait produire une position
        « qui ne peut pas perdre » et gonfler artificiellement un backtest.
        """
        if self.sens is Sens.ACHAT and not (self.stop < self.entree < self.objectif):
            raise SignalInvalide(
                f"Achat incohérent : il faut stop < entrée < objectif, "
                f"or stop={self.stop}, entrée={self.entree}, objectif={self.objectif}"
            )
        if self.sens is Sens.VENTE and not (self.objectif < self.entree < self.stop):
            raise SignalInvalide(
                f"Vente incohérente : il faut objectif < entrée < stop, "
                f"or objectif={self.objectif}, entrée={self.entree}, stop={self.stop}"
            )

    @property
    def risque(self) -> float:
        """Distance entre l'entrée et le stop, en unités de prix.

        C'est la grandeur dont la couche de risque a besoin pour convertir
        « 0,2 % du capital » en une taille de position.
        """
        return abs(self.entree - self.stop)

    @property
    def ratio(self) -> float:
        """Gain visé divisé par le risque pris (le « R »)."""
        return abs(self.objectif - self.entree) / self.risque

    def __str__(self) -> str:
        return (
            f"{self.sens.value.upper()} entrée={self.entree:.5f} "
            f"stop={self.stop:.5f} objectif={self.objectif:.5f} "
            f"({self.ratio:.1f}R) — {self.raison}"
        )


class Strategie(ABC):
    """Contrat que toute stratégie du projet doit respecter."""

    #: Nom lisible, utilisé dans les rapports et les comparaisons.
    nom: str = "sans nom"

    @property
    @abstractmethod
    def bougies_minimum(self) -> int:
        """Nombre de bougies nécessaires avant de pouvoir décider quoi que ce soit.

        Une EMA 200 n'a pas de sens sur 50 bougies. Le moteur de backtest s'en sert
        pour savoir à partir de quand commencer à évaluer.
        """

    @abstractmethod
    def preparer(self, bougies: pd.DataFrame) -> pd.DataFrame:
        """Calcule les indicateurs sur toute la série, en une seule passe.

        Séparé de `evaluer` pour une raison de performance : recalculer une EMA 200
        à chaque bougie donnerait un coût quadratique. Ici on calcule une fois,
        puis on lit.

        Retourne une copie enrichie de colonnes d'indicateurs.
        """

    @abstractmethod
    def evaluer(self, historique: pd.DataFrame) -> Signal | None:
        """Décide à partir de l'historique reçu, dont la dernière ligne est la
        dernière bougie CLÔTURÉE.

        L'appelant fournit une tranche déjà coupée : aucune bougie future n'est
        accessible. Retourne None quand aucune condition n'est réunie — ce qui
        sera le cas la grande majorité du temps.
        """


def verifier_bougies(bougies: pd.DataFrame) -> None:
    """Vérifie qu'une série de bougies est utilisable, ou explique ce qui manque."""
    manquantes = [c for c in COLONNES_BOUGIES if c not in bougies.columns]
    if manquantes:
        raise ValueError(
            f"Colonnes manquantes dans les bougies : {', '.join(manquantes)}. "
            f"Colonnes présentes : {', '.join(map(str, bougies.columns))}"
        )
    if not bougies.index.is_monotonic_increasing:
        raise ValueError(
            "Les bougies ne sont pas triées par ordre chronologique croissant. "
            "Un backtest sur des données désordonnées ne veut rien dire."
        )
