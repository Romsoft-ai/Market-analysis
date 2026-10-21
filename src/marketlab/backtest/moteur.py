"""Le backtest : le pilote branché sur le courtier simulé, bougie après bougie.

Depuis le bloc 4, ce module ne contient plus aucune logique de décision ni
d'exécution. Il assemble trois pièces :

* le **pilote** (`marketlab.pilote`) décide, exactement comme il le fera en live ;
* le **courtier simulé** (`marketlab.brokers.simulation`) remplit les ordres et
  applique stops et objectifs sur l'historique ;
* le **rejeu** ci-dessous fait avancer le temps : pour chaque bougie, le courtier
  la traverse d'abord (sorties éventuelles), puis le pilote réagit à sa clôture.

Il déroule les bougies **une par une, dans l'ordre**, et ne montre jamais à la
stratégie autre chose que le passé. Les conventions d'exécution (entrée à
l'ouverture suivante, spread payé à l'entrée, convention pessimiste) sont
documentées dans le simulateur ; les règles de gestion de position (stop qui ne
fait que se resserrer, break-even) dans le pilote.

UN RÉGLAGE QUI N'EST PAS NEUTRE : `positions_max`
--------------------------------------------------

Une position à la fois par défaut. `None` lève la limite : chaque signal devient
un trade. Le risque étant dimensionné à 0,2 % du capital PAR POSITION, dix
positions ouvertes exposent 2 % du compte en même temps, et rien ne borne ce
cumul. Le drawdown mesuré n'est donc plus comparable d'un réglage à l'autre,
alors que le résultat en R, lui, le reste.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from marketlab.brokers.base import Specification
from marketlab.brokers.simulation import BacktestBroker, MotifSortie, Trade
from marketlab.pilote import Pilote
from marketlab.strategies.base import Strategie, verifier_bougies

__all__ = ["Backtest", "MotifSortie", "Resultat", "Trade"]

#: Le simulateur ne connaît qu'un instrument : celui des bougies rejouées.
_INSTRUMENT_SIMULE = "historique"


@dataclass
class Resultat:
    """Sortie complète d'une simulation."""

    trades: list[Trade] = field(default_factory=list)
    capital_initial: float = 0.0
    capital_final: float = 0.0
    bougies_evaluees: int = 0
    signaux_emis: int = 0
    signaux_ignores: int = 0
    entrees_refusees: int = 0

    def en_tableau(self) -> pd.DataFrame:
        """Les trades sous forme de tableau, pour analyse et export."""
        if not self.trades:
            return pd.DataFrame()
        return pd.DataFrame(
            [
                {
                    "sens": t.sens.value,
                    "date_entree": t.date_entree,
                    "date_sortie": t.date_sortie,
                    "entree": t.entree,
                    "stop_initial": t.stop_initial,
                    "stop_final": t.stop_final,
                    "objectif": t.objectif,
                    "sortie": t.sortie,
                    "motif": t.motif,
                    "risque_pips": t.risque_pips,
                    "resultat_pips": t.resultat_pips,
                    "lots": t.lots,
                    "risque_theorique": t.risque_theorique,
                    "risque_reel": t.risque_reel,
                    "resultat_r": t.resultat_r,
                    "resultat_montant": t.resultat_montant,
                    "capital_apres": t.capital_apres,
                    "bougies": t.bougies,
                }
                for t in self.trades
            ]
        )


class Backtest:
    """Simulation d'une stratégie sur un historique de bougies."""

    def __init__(
        self,
        strategie: Strategie,
        spread: float,
        capital_initial: float = 100_000.0,
        risque_par_trade: float = 0.002,
        break_even_a: float | None = 1.0,
        valeur_pip: float = 1.0,
        valeur_pip_par_lot: float = 1.0,
        volume_min: float = 0.01,
        volume_pas: float = 0.01,
        positions_max: int | None = 1,
    ) -> None:
        """
        Args:
            spread: coût en unités de prix, mesuré chez le courtier cible.
            risque_par_trade: fraction du capital risquée (0.002 = 0,2 %).
            break_even_a: seuil en R où le stop remonte à l'entrée.
                None désactive le break-even.
            valeur_pip: écart de prix correspondant à un pip, propre à l'instrument.
            valeur_pip_par_lot: gain ou perte en devise du compte pour un pip et
                un lot, soit taille du contrat multipliée par la valeur du pip.
            volume_min: plus petit volume acceptable chez le courtier.
            volume_pas: incrément de volume imposé par le courtier.
            positions_max: nombre de positions ouvertes simultanément.
                `None` lève la limite (voir l'en-tête du module).
        """
        self.strategie = strategie
        self.spread = spread
        self.capital_initial = capital_initial
        self.risque_par_trade = risque_par_trade
        self.break_even_a = break_even_a
        self.positions_max = positions_max
        self.specification = Specification(
            point=0.0,
            decimales=0,
            valeur_pip=valeur_pip if valeur_pip > 0 else 1.0,
            valeur_pip_par_lot=valeur_pip_par_lot if valeur_pip_par_lot > 0 else 1.0,
            volume_min=volume_min,
            volume_pas=volume_pas if volume_pas > 0 else 0.01,
        )

    def executer(self, bougies: pd.DataFrame) -> Resultat:
        """Déroule l'historique et retourne les trades effectués.

        Cas limite assumé : un signal émis sur la DERNIÈRE bougie n'a pas de
        bougie suivante où entrer. Il est compté dans `signaux_emis` mais ne
        devient jamais un trade, sans être compté comme une entrée refusée.
        """
        verifier_bougies(bougies)
        donnees = self.strategie.preparer(bougies)

        broker = BacktestBroker(donnees, self.spread, self.specification, self.capital_initial)
        pilote = Pilote(
            self.strategie,
            broker,
            _INSTRUMENT_SIMULE,
            risque_par_trade=self.risque_par_trade,
            positions_max=self.positions_max,
            break_even_a=self.break_even_a,
        )

        for i in range(len(donnees)):
            broker.avancer(i)
            pilote.sur_cloture(donnees.iloc[: i + 1])
        broker.terminer()

        c = pilote.compteurs
        return Resultat(
            trades=broker.trades,
            capital_initial=self.capital_initial,
            capital_final=broker.compte().capital,
            bougies_evaluees=c.bougies_evaluees,
            signaux_emis=c.signaux_emis,
            signaux_ignores=c.signaux_ignores,
            entrees_refusees=c.entrees_refusees,
        )
