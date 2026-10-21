"""Le courtier simulé : il rejoue l'historique bougie par bougie.

Il ne décide rien. Il remplit les ordres que le pilote lui envoie et dit, à
chaque bougie, si un stop ou un objectif a été touché. Toute la logique de
décision vit dans le pilote, partagée avec le live.

CE QUE LE SIMULATEUR SUPPOSE, ET QUI DOIT ÊTRE SU
---------------------------------------------------

1. **Un ordre décidé à la clôture de la bougie N est rempli à l'ouverture de la
   bougie N+1.** À la clôture, la bougie est terminée, on ne peut plus y acheter.
   Remplir au prix de clôture reviendrait à tricher d'une bougie.

2. **Le spread est payé une fois, à l'entrée.** Un achat est rempli au-dessus de
   l'ouverture, une vente en dessous ; les sorties se font aux niveaux nominaux.
   Cela reproduit le coût d'un aller-retour sans compliquer le calcul.

3. **CONVENTION PESSIMISTE.** Quand une même bougie contient le stop ET
   l'objectif, on suppose que le **stop** a été touché en premier. Les bougies ne
   conservent pas l'ordre des événements (voir l'annexe G du plan v2). Ce choix
   sous-estime les résultats, ce qui est le sens sûr.

4. **Résultats exprimés en R** (multiples du risque pris) autant qu'en argent. Le
   R est indépendant de la taille de position : c'est la mesure honnête pour
   comparer des stratégies. Le montant sert à observer le drawdown.

Ce que le simulateur NE reproduit PAS, et qui sépare encore le backtest du live :
le spread variable (on utilise la médiane mesurée), le glissement à l'exécution,
et le refus d'ordre par le courtier.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from marketlab.brokers.base import (
    Broker,
    Compte,
    Deplacement,
    Ordre,
    OrdreRefuse,
    PositionOuverte,
    Specification,
)
from marketlab.strategies.base import Sens


class MotifSortie:
    """Raisons possibles de clôture d'une position."""

    OBJECTIF = "objectif"
    STOP = "stop"
    BREAK_EVEN = "break-even"
    #: Stop atteint après avoir été déplacé par la stratégie. Distingué du stop
    #: initial : la sortie peut se faire en gain, et la confondre avec une perte
    #: fausserait la lecture des résultats.
    STOP_SUIVEUR = "stop suiveur"
    FERMETURE = "fermeture"
    FIN_PERIODE = "fin de période"


@dataclass
class Trade:
    """Une position clôturée, avec tout ce qu'il faut pour l'auditer."""

    sens: Sens
    date_entree: datetime
    date_sortie: datetime
    entree: float
    stop_initial: float
    objectif: float
    sortie: float
    motif: str
    resultat_r: float
    resultat_montant: float
    capital_apres: float
    bougies: int
    # Distances exprimees dans l'unite d'affichage de l'instrument, plus
    # parlante qu'un ecart de prix brut quand on lit un trade.
    risque_pips: float = 0.0
    resultat_pips: float = 0.0
    # Volume reellement passe et montants correspondants. L'arrondi au pas de
    # volume fait que le risque reel n'egale jamais exactement le risque vise :
    # les deux sont conserves pour que l'ecart reste verifiable trade par trade.
    lots: float = 0.0
    risque_theorique: float = 0.0
    risque_reel: float = 0.0
    raison_signal: str = ""
    # Niveau du stop au moment de la sortie. Égal au stop initial sauf si un
    # break-even ou un stop suiveur l'a déplacé : c'est la trace de ce déplacement.
    stop_final: float = 0.0


@dataclass
class _Suivi:
    """Ce que le simulateur doit savoir d'une position en plus de ce qu'en voit le pilote."""

    position: PositionOuverte
    index_entree: int
    montant_risque: float
    risque_theorique: float


class BacktestBroker(Broker):
    """Courtier simulé sur un historique de bougies déjà préparées.

    Le rejoueur (`Backtest`) appelle `avancer(i)` au début de chaque bougie, puis
    laisse le pilote décider à sa clôture. `terminer()` solde ce qui reste ouvert.
    """

    def __init__(
        self,
        bougies: pd.DataFrame,
        spread: float,
        specification: Specification,
        capital_initial: float,
    ) -> None:
        self._bougies = bougies
        self._ouvertures = bougies["open"].to_numpy(dtype="float64")
        self._spread = spread
        self._spec = specification
        self._capital = capital_initial
        self._index = -1
        self._suivis: list[_Suivi] = []
        self._prochain_id = 1
        self.trades: list[Trade] = []

    # ------------------------------------------------------------------
    # Contrat Broker
    # ------------------------------------------------------------------

    def compte(self) -> Compte:
        return Compte(capital=self._capital)

    def specification(self, instrument: str) -> Specification:
        return self._spec

    def cotation(self, instrument: str, sens: Sens) -> float | None:
        """L'ouverture de la bougie suivante, spread compris : c'est là que l'ordre sera rempli."""
        suivante = self._index + 1
        if suivante >= len(self._ouvertures):
            return None
        ouverture = float(self._ouvertures[suivante])
        return ouverture + self._spread if sens is Sens.ACHAT else ouverture - self._spread

    def positions(self, instrument: str) -> list[PositionOuverte]:
        return [suivi.position for suivi in self._suivis]

    def ouvrir(self, ordre: Ordre) -> PositionOuverte:
        entree = self.cotation(ordre.instrument, ordre.sens)
        if entree is None:
            raise OrdreRefuse("fin de l'historique : aucune bougie où remplir l'ordre")
        suivante = self._index + 1

        position = PositionOuverte(
            identifiant=self._prochain_id,
            instrument=ordre.instrument,
            sens=ordre.sens,
            volume=ordre.volume,
            entree=entree,
            stop=ordre.stop,
            stop_initial=ordre.stop,
            objectif=ordre.objectif,
            date_entree=self._bougies.index[suivante],
            raison=ordre.raison,
        )
        self._prochain_id += 1

        # Même expression que le dimensionnement, pour que le montant risqué
        # enregistré soit exactement celui qui a servi à choisir le volume.
        risque_pips = position.risque / self._spec.valeur_pip
        montant_risque = ordre.volume * risque_pips * self._spec.valeur_pip_par_lot

        self._suivis.append(
            _Suivi(position, suivante, montant_risque, ordre.risque_vise)
        )
        return position

    def modifier_stop(self, position: PositionOuverte, niveau: float, raison: Deplacement) -> None:
        position.stop = float(niveau)
        if raison is Deplacement.BREAK_EVEN:
            position.break_even_arme = True
        else:
            position.stop_deplace = True

    def fermer(self, position: PositionOuverte) -> None:
        """Ferme au prix de clôture de la bougie en cours."""
        suivi = self._suivi_de(position)
        bougie = self._bougies.iloc[self._index]
        self._solder(suivi, float(bougie["close"]), bougie.name, self._index, MotifSortie.FERMETURE)

    # ------------------------------------------------------------------
    # Rejeu
    # ------------------------------------------------------------------

    def avancer(self, index: int) -> None:
        """Passe à la bougie `index` et applique stops et objectifs sur sa durée.

        Le capital est mis à jour au fil des clôtures : plusieurs positions
        peuvent se solder sur la même bougie, et chacune dimensionne la suivante.
        Les trades sont donc rangés par ordre de SORTIE, ce qui est l'ordre dans
        lequel le capital a réellement bougé.
        """
        self._index = index
        if not self._suivis:
            return
        bougie = self._bougies.iloc[index]
        haut = float(bougie["high"])
        bas = float(bougie["low"])

        for suivi in list(self._suivis):
            position = suivi.position
            if position.sens is Sens.ACHAT:
                stop_touche = bas <= position.stop
                objectif_touche = haut >= position.objectif
            else:
                stop_touche = haut >= position.stop
                objectif_touche = bas <= position.objectif

            # CONVENTION PESSIMISTE : le stop est évalué en premier.
            if stop_touche:
                if position.stop_deplace:
                    motif = MotifSortie.STOP_SUIVEUR
                elif position.break_even_arme:
                    motif = MotifSortie.BREAK_EVEN
                else:
                    motif = MotifSortie.STOP
                self._solder(suivi, position.stop, bougie.name, index, motif)
            elif objectif_touche:
                self._solder(suivi, position.objectif, bougie.name, index, MotifSortie.OBJECTIF)

    def terminer(self) -> None:
        """Solde les positions encore ouvertes au dernier prix connu."""
        if not self._suivis:
            return
        derniere = self._bougies.iloc[-1]
        for suivi in list(self._suivis):
            self._solder(
                suivi, float(derniere["close"]), derniere.name,
                len(self._bougies) - 1, MotifSortie.FIN_PERIODE,
            )

    # ------------------------------------------------------------------
    # Clôture
    # ------------------------------------------------------------------

    def _suivi_de(self, position: PositionOuverte) -> _Suivi:
        for suivi in self._suivis:
            if suivi.position is position:
                return suivi
        raise OrdreRefuse(f"position {position.identifiant} inconnue ou déjà fermée")

    def _solder(self, suivi: _Suivi, sortie: float, date: datetime, index: int, motif: str) -> None:
        """Solde la position, calcule son résultat et met le capital à jour."""
        position = suivi.position
        if position.sens is Sens.ACHAT:
            gain_prix = sortie - position.entree
        else:
            gain_prix = position.entree - sortie

        resultat_r = gain_prix / position.risque
        montant = resultat_r * suivi.montant_risque
        self._capital = self._capital + montant

        self.trades.append(
            Trade(
                sens=position.sens,
                date_entree=position.date_entree,
                date_sortie=date,
                entree=position.entree,
                stop_initial=position.stop_initial,
                objectif=position.objectif,
                sortie=sortie,
                motif=motif,
                resultat_r=resultat_r,
                resultat_montant=montant,
                capital_apres=self._capital,
                bougies=index - suivi.index_entree,
                risque_pips=position.risque / self._spec.valeur_pip,
                resultat_pips=gain_prix / self._spec.valeur_pip,
                lots=position.volume,
                risque_theorique=suivi.risque_theorique,
                risque_reel=suivi.montant_risque,
                raison_signal=position.raison,
                stop_final=position.stop,
            )
        )
        self._suivis.remove(suivi)
