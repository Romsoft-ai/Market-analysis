"""Le contrat commun à tout courtier : ce que le pilote a le droit de demander.

C'est la pièce qui permet d'écrire la logique de décision UNE seule fois. Le
pilote parle à un `Broker` sans savoir ce qu'il y a derrière : un simulateur qui
rejoue l'historique, ou le terminal MetaTrader relié à un vrai compte. Le
backtest et le live exécutent donc le même code, et l'écart entre les deux se
réduit à ce que le simulateur ne sait pas reproduire (glissement, spread
variable), au lieu de s'étendre à tout ce qu'on aurait recodé différemment.

Le contrat est volontairement étroit : six opérations, celles dont le pilote a
besoin et aucune autre. Chaque opération ajoutée ici devrait être réécrite pour
chaque courtier.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from marketlab.strategies.base import Sens


class Deplacement(Enum):
    """Raison d'un déplacement de stop, conservée pour qualifier la sortie."""

    BREAK_EVEN = "break-even"
    SUIVEUR = "stop suiveur"


class OrdreRefuse(RuntimeError):
    """Le courtier a refusé l'ordre. Le message dit pourquoi, tel que reçu."""


@dataclass(frozen=True)
class Compte:
    """État du compte utile au dimensionnement."""

    capital: float
    devise: str = "USD"


@dataclass(frozen=True)
class Specification:
    """Caractéristiques de contrat d'un instrument, telles que le courtier les impose.

    `valeur_pip_par_lot` est le gain ou la perte, en devise du compte, d'un pip
    sur un lot. C'est la grandeur qui convertit un risque en prix (distance au
    stop) en risque en argent, donc en volume.
    """

    point: float
    decimales: int
    valeur_pip: float
    valeur_pip_par_lot: float
    volume_min: float
    volume_pas: float


@dataclass(frozen=True)
class Ordre:
    """Une demande d'ouverture au marché, entièrement dimensionnée par le pilote.

    Le courtier n'invente rien : volume, stop et objectif sont décidés en amont.
    `risque_vise` est le montant que le pilote voulait risquer ; il ne sert qu'à
    l'audit, pour comparer au risque réellement pris après arrondi du volume.
    """

    instrument: str
    sens: Sens
    volume: float
    stop: float
    objectif: float
    raison: str = ""
    risque_vise: float = 0.0


@dataclass
class PositionOuverte:
    """Une position ouverte, vue par le pilote.

    Mutable : son stop se déplace pendant sa vie. Les deux indicateurs de
    déplacement servent à nommer correctement la sortie (stop initial, break-even
    ou stop suiveur), ce qui change la lecture d'un résultat.
    """

    identifiant: int
    instrument: str
    sens: Sens
    volume: float
    entree: float
    stop: float
    stop_initial: float
    objectif: float
    date_entree: datetime
    raison: str = ""
    break_even_arme: bool = False
    stop_deplace: bool = False

    @property
    def risque(self) -> float:
        """Distance initiale entre l'entrée et le stop, en prix : la mesure du « 1 R »."""
        return abs(self.entree - self.stop_initial)


class Broker(ABC):
    """Ce que tout courtier doit savoir faire pour être piloté."""

    @abstractmethod
    def compte(self) -> Compte:
        """Capital disponible pour dimensionner la prochaine position."""

    @abstractmethod
    def specification(self, instrument: str) -> Specification:
        """Caractéristiques du contrat chez ce courtier."""

    @abstractmethod
    def cotation(self, instrument: str, sens: Sens) -> float | None:
        """Prix auquel un ordre au marché serait rempli maintenant, spread compris.

        None si aucun prix n'est disponible (marché fermé, fin d'historique).
        Le pilote en a besoin pour calculer la distance au stop, donc le volume,
        AVANT d'envoyer l'ordre.
        """

    @abstractmethod
    def positions(self, instrument: str) -> list[PositionOuverte]:
        """Positions ouvertes sur cet instrument."""

    @abstractmethod
    def ouvrir(self, ordre: Ordre) -> PositionOuverte:
        """Ouvre une position au marché, stop et objectif posés chez le courtier.

        Lève `OrdreRefuse` si le courtier refuse.
        """

    @abstractmethod
    def modifier_stop(self, position: PositionOuverte, niveau: float, raison: Deplacement) -> None:
        """Déplace le stop d'une position ouverte. Lève `OrdreRefuse` si refusé."""

    @abstractmethod
    def fermer(self, position: PositionOuverte) -> None:
        """Ferme une position au marché. Lève `OrdreRefuse` si refusé."""
