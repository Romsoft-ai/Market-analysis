"""Les garde-fous du live : ce qui interdit une entrée, quelle que soit la stratégie.

Une stratégie a le droit de se tromper ; c'est son métier. Le compte, lui, ne doit
pas pouvoir être vidé par une série de pertes, un spread aberrant ou un robot que
plus personne ne surveille. Ces règles sont consultées par le pilote avant CHAQUE
entrée, et ne s'appliquent qu'aux entrées : elles ne ferment rien et ne touchent
pas aux stops. Une position ouverte reste protégée par son stop chez le courtier.

Trois règles, réglées le 21 octobre 2026 :

* **perte maximale du jour** : 1 % du capital du début de journée, soit cinq
  pertes consécutives à 0,2 %. Au-delà, plus d'entrée jusqu'au lendemain. Une
  série pareille signale un marché qui ne ressemble pas à celui du backtest ;
* **spread anormal** : plus de 3 fois sa médiane historique. Cela arrive la nuit
  et autour des annonces économiques ; le backtest, qui paie un spread médian, ne
  le voit pas, et entrer à ce moment coûterait bien plus que prévu ;
* **arrêt demandé** : un drapeau levé de l'extérieur (interface, base de données).

Le « jour » est celui du SERVEUR, déduit de l'horodatage de la bougie : c'est la
journée de trading du courtier, et non celle de l'horloge du PC.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import pandas as pd

from marketlab.brokers.base import Broker
from marketlab.strategies.base import Sens


class GardeFous:
    """Les trois règles, consultées par le pilote via `raison_de_bloquer`."""

    def __init__(
        self,
        spread_reference_points: float,
        perte_max_jour: float = 0.01,
        spread_max_multiple: float = 3.0,
        arret_demande: Callable[[], bool] = lambda: False,
    ) -> None:
        """
        Args:
            spread_reference_points: spread médian mesuré sur l'historique, en points.
            perte_max_jour: fraction du capital de début de journée (0.01 = 1 %).
            spread_max_multiple: au-delà de ce multiple de la référence, on n'entre pas.
            arret_demande: interrogé à chaque entrée ; vrai = plus aucune entrée.
        """
        self.spread_reference_points = spread_reference_points
        self.perte_max_jour = perte_max_jour
        self.spread_max_multiple = spread_max_multiple
        self.arret_demande = arret_demande
        self._jour: date | None = None
        self._capital_debut_jour: float | None = None

    def raison_de_bloquer(self, instrument: str, broker: Broker, bougie: pd.Series) -> str | None:
        if self.arret_demande():
            return "arrêt demandé"

        capital = broker.compte().capital
        jour = pd.Timestamp(bougie.name).date()
        if jour != self._jour:
            # Nouvelle journée serveur : le compteur de perte repart du capital actuel.
            self._jour, self._capital_debut_jour = jour, capital
        assert self._capital_debut_jour is not None
        perte = (self._capital_debut_jour - capital) / self._capital_debut_jour
        if perte >= self.perte_max_jour:
            return (
                f"perte du jour {perte:.2%} ≥ {self.perte_max_jour:.2%} "
                f"(capital {capital:,.2f} contre {self._capital_debut_jour:,.2f} ce matin)"
            )

        achat = broker.cotation(instrument, Sens.ACHAT)
        vente = broker.cotation(instrument, Sens.VENTE)
        if achat is not None and vente is not None and self.spread_reference_points > 0:
            point = broker.specification(instrument).point
            spread = (achat - vente) / point if point > 0 else 0.0
            plafond = self.spread_max_multiple * self.spread_reference_points
            if spread > plafond:
                return (
                    f"spread {spread:.0f} pts > {plafond:.0f} pts "
                    f"({self.spread_max_multiple:g} × la médiane de {self.spread_reference_points:.0f})"
                )
        return None
