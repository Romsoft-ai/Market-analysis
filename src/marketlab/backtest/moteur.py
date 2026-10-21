"""Moteur de simulation historique, événementiel et séquentiel.

Il déroule les bougies **une par une, dans l'ordre**, et ne montre jamais à la
stratégie autre chose que le passé. C'est ce qui empêche structurellement le biais
d'anticipation.

CE QUE LE MOTEUR SUPPOSE, ET QUI DOIT ÊTRE SU
---------------------------------------------

1. **Nombre de positions simultanées réglable** (`positions_max`, 1 par défaut).
   Le passer à `None` lève la limite : chaque signal devient un trade.

   Ce réglage n'est pas neutre. Le risque est dimensionné à 0,2 % du capital PAR
   POSITION : avec dix positions ouvertes, 2 % du compte sont exposés en même
   temps, et rien ne borne ce cumul. Le drawdown mesuré n'est donc plus
   comparable d'un réglage à l'autre, alors que le résultat en R, lui, le reste.
   Une limite d'exposition globale relève de la couche de risque, pas du moteur.

2. **Entrée à l'ouverture de la bougie SUIVANTE.** Le signal naît à la clôture de
   la bougie N ; à cet instant la bougie est terminée, on ne peut plus y acheter.
   Entrer au prix de clôture reviendrait à tricher d'une bougie.

3. **Le spread est payé une fois, à l'entrée.** Un achat est rempli au-dessus de
   l'ouverture, une vente en dessous ; les sorties se font aux niveaux nominaux.
   Cela reproduit le coût d'un aller-retour sans compliquer le calcul.

4. **CONVENTION PESSIMISTE.** Quand une même bougie contient le stop ET l'objectif,
   on suppose que le **stop** a été touché en premier. Les bougies ne conservent
   pas l'ordre des événements (voir l'annexe G du plan v2). Ce choix sous-estime
   les résultats, ce qui est le sens sûr : une stratégie qui paraît bonne sous
   cette convention l'est probablement vraiment.

5. **Le break-even s'arme à la fin d'une bougie**, jamais au milieu. Si le prix
   atteint le seuil puis revient au stop dans la même bougie, on ne sait pas dans
   quel ordre : le point 4 s'applique.

5 bis. **Le stop suiveur se déplace aussi à la fin d'une bougie**, pour la même
   raison. La stratégie propose un niveau (`ajuster_stop`), le moteur ne
   l'accepte que s'il RESSERRE le stop et reste du bon côté de la clôture. Une
   stratégie boguée ne peut donc ni éloigner un stop, ni en poser un que le prix
   a déjà franchi, ce qui inventerait une sortie à un prix jamais coté.

6. **Résultats exprimés en R** (multiples du risque pris) autant qu'en euros. Le R
   est indépendant de la taille de position : c'est la mesure honnête pour
   comparer des stratégies. Le montant sert à observer le drawdown.

Le point 4 disparaîtra à l'étape 4, quand le simulateur parcourra les bougies M1
contenues dans chaque bougie de décision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from marketlab.strategies.base import Sens, Signal, Strategie, verifier_bougies


class MotifSortie:
    """Raisons possibles de clôture d'une position."""

    OBJECTIF = "objectif"
    STOP = "stop"
    BREAK_EVEN = "break-even"
    #: Stop atteint après avoir été déplacé par la stratégie. Distingué du stop
    #: initial : la sortie peut se faire en gain, et la confondre avec une perte
    #: fausserait la lecture des résultats.
    STOP_SUIVEUR = "stop suiveur"
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
class _Position:
    """État interne d'une position ouverte. Non exposé à l'extérieur."""

    sens: Sens
    entree: float
    stop: float
    stop_initial: float
    objectif: float
    risque: float
    montant_risque: float
    lots: float
    risque_theorique: float
    date_entree: datetime
    index_entree: int
    raison: str
    break_even_arme: bool = False
    stop_deplace: bool = False


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
                `None` lève la limite. Voir le point 1 de l'en-tête du module :
                lever la limite multiplie l'exposition, pas seulement le nombre
                de trades.
        """
        self.strategie = strategie
        self.spread = spread
        self.capital_initial = capital_initial
        self.risque_par_trade = risque_par_trade
        self.break_even_a = break_even_a
        self.valeur_pip = valeur_pip if valeur_pip > 0 else 1.0
        self.valeur_pip_par_lot = valeur_pip_par_lot if valeur_pip_par_lot > 0 else 1.0
        self.volume_min = volume_min
        self.volume_pas = volume_pas if volume_pas > 0 else 0.01
        self.positions_max = positions_max

    # ------------------------------------------------------------------
    # Boucle principale
    # ------------------------------------------------------------------

    def executer(self, bougies: pd.DataFrame) -> Resultat:
        """Déroule l'historique et retourne les trades effectués.

        Cas limite assumé : un signal émis sur la DERNIÈRE bougie n'a pas de
        bougie suivante où entrer. Il est compté dans `signaux_emis` mais ne
        devient jamais un trade. Cela concerne au plus un signal par simulation,
        et le compter comme une entrée refusée le confondrait avec un refus dû à
        un écart d'ouverture, qui n'a rien à voir.
        """
        verifier_bougies(bougies)
        donnees = self.strategie.preparer(bougies)

        resultat = Resultat(
            capital_initial=self.capital_initial, capital_final=self.capital_initial
        )
        capital = self.capital_initial
        positions: list[_Position] = []
        en_attente: Signal | None = None
        debut = self.strategie.bougies_minimum

        for i in range(len(donnees)):
            bougie = donnees.iloc[i]

            # 1. Exécuter l'entrée décidée à la bougie précédente.
            if en_attente is not None:
                position = self._ouvrir(en_attente, bougie, i, capital)
                if position is None:
                    resultat.entrees_refusees += 1
                else:
                    positions.append(position)
                en_attente = None

            # 2. Gérer les positions ouvertes sur cette bougie.
            # Le capital est mis à jour au fil des clôtures : plusieurs positions
            # peuvent se solder sur la même bougie, et chacune dimensionne la
            # suivante. Les trades sont donc rangés par ordre de SORTIE, ce qui est
            # l'ordre dans lequel le capital a réellement bougé.
            if positions:
                encore_ouvertes: list[_Position] = []
                for position in positions:
                    trade = self._gerer(position, bougie, i, capital)
                    if trade is None:
                        encore_ouvertes.append(position)
                    else:
                        capital = trade.capital_apres
                        resultat.trades.append(trade)
                positions = encore_ouvertes

            # 3. Chercher un signal.
            if i >= debut:
                resultat.bougies_evaluees += 1
                signal = self.strategie.evaluer(donnees.iloc[: i + 1])
                if signal is not None:
                    resultat.signaux_emis += 1
                    if self._place_libre(len(positions)):
                        en_attente = signal
                    else:
                        # Signal valide mais plus de place : on le compte pour
                        # savoir combien d'occasions la limite fait manquer.
                        resultat.signaux_ignores += 1

        # Positions encore ouvertes à la fin : clôture au dernier prix connu.
        if positions:
            derniere = donnees.iloc[-1]
            for position in positions:
                trade = self._cloturer(
                    position,
                    float(derniere["close"]),
                    derniere.name,
                    len(donnees) - 1,
                    MotifSortie.FIN_PERIODE,
                    capital,
                )
                capital = trade.capital_apres
                resultat.trades.append(trade)

        resultat.capital_final = capital
        return resultat

    def _place_libre(self, ouvertes: int) -> bool:
        """Reste-t-il de la place pour une position de plus ?

        Le compte est fait après les clôtures de la bougie courante : une position
        soldée libère donc sa place pour un signal détecté sur la même bougie,
        exactement comme dans la version à position unique.
        """
        return self.positions_max is None or ouvertes < self.positions_max

    # ------------------------------------------------------------------
    # Ouverture
    # ------------------------------------------------------------------

    def _ouvrir(
        self, signal: Signal, bougie: pd.Series, index: int, capital: float
    ) -> _Position | None:
        """Remplit l'ordre à l'ouverture de la bougie, ou renonce.

        Le stop conserve le niveau structurel choisi par la stratégie. L'objectif,
        lui, est recalculé à partir du risque RÉELLEMENT pris : le prix de
        remplissage diffère du prix de référence du signal, et on veut que le
        rapport gain/risque annoncé soit tenu.
        """
        ouverture = float(bougie["open"])

        if signal.sens is Sens.ACHAT:
            entree = ouverture + self.spread
            risque = entree - signal.stop
            objectif = entree + signal.ratio * risque
        else:
            entree = ouverture - self.spread
            risque = signal.stop - entree
            objectif = entree - signal.ratio * risque

        # Un écart d'ouverture (gap) peut placer le prix au-delà du stop : la
        # position serait perdante avant même d'exister. On renonce.
        if risque <= 0:
            return None

        risque_theorique = capital * self.risque_par_trade
        lots, risque_reel = self._dimensionner(risque, risque_theorique)

        return _Position(
            sens=signal.sens,
            entree=entree,
            stop=signal.stop,
            stop_initial=signal.stop,
            objectif=objectif,
            risque=risque,
            montant_risque=risque_reel,
            lots=lots,
            risque_theorique=risque_theorique,
            date_entree=bougie.name,
            index_entree=index,
            raison=signal.raison,
        )

    def _dimensionner(self, risque_prix: float, montant_vise: float) -> tuple[float, float]:
        """Traduit un montant à risquer en volume, puis en risque réellement pris.

        Le courtier n'accepte que des volumes multiples d'un pas. On arrondit vers
        le BAS pour ne jamais dépasser le risque visé, sauf si le résultat tombe
        sous le volume minimum : dans ce cas la position ne peut pas être plus
        petite, et le risque réel dépasse la cible. Le retourner tel quel plutôt
        que de le masquer permet de le voir dans l'inspection.
        """
        risque_pips = risque_prix / self.valeur_pip
        if risque_pips <= 0:
            return 0.0, 0.0

        lots_exacts = montant_vise / (risque_pips * self.valeur_pip_par_lot)
        lots = int(lots_exacts / self.volume_pas) * self.volume_pas
        lots = max(lots, self.volume_min)
        lots = round(lots, 8)

        risque_reel = lots * risque_pips * self.valeur_pip_par_lot
        return lots, risque_reel

    # ------------------------------------------------------------------
    # Gestion en cours de position
    # ------------------------------------------------------------------

    def _gerer(
        self, position: _Position, bougie: pd.Series, index: int, capital: float
    ) -> Trade | None:
        """Applique stop, objectif et break-even sur une bougie."""
        haut = float(bougie["high"])
        bas = float(bougie["low"])

        if position.sens is Sens.ACHAT:
            stop_touche = bas <= position.stop
            objectif_touche = haut >= position.objectif
        else:
            stop_touche = haut >= position.stop
            objectif_touche = bas <= position.objectif

        # CONVENTION PESSIMISTE : le stop est évalué en premier. Si les deux
        # niveaux sont dans la bougie, on suppose le pire.
        if stop_touche:
            if position.stop_deplace:
                motif = MotifSortie.STOP_SUIVEUR
            elif position.break_even_arme:
                motif = MotifSortie.BREAK_EVEN
            else:
                motif = MotifSortie.STOP
            return self._cloturer(
                position, position.stop, bougie.name, index, motif, capital
            )

        if objectif_touche:
            return self._cloturer(
                position, position.objectif, bougie.name, index,
                MotifSortie.OBJECTIF, capital,
            )

        # Aucune sortie : le stop peut se resserrer pour les bougies suivantes.
        self._armer_break_even(position, haut, bas)
        self._suivre(position, bougie)
        return None

    def _suivre(self, position: _Position, bougie: pd.Series) -> None:
        """Applique le stop proposé par la stratégie, s'il est acceptable.

        Deux refus, tous deux silencieux car ils ne sont pas des erreurs :

        * un stop qui s'éloignerait du prix. Un stop suiveur ne recule jamais ;
        * un stop déjà franchi par la clôture. Il déclencherait une sortie à la
          bougie suivante à un niveau que le prix a quitté, donc à un prix fictif.
        """
        propose = self.strategie.ajuster_stop(position.sens, position.stop, bougie)
        if propose is None:
            return
        cloture = float(bougie["close"])
        if position.sens is Sens.ACHAT:
            acceptable = position.stop < propose < cloture
        else:
            acceptable = cloture < propose < position.stop
        if acceptable:
            position.stop = float(propose)
            position.stop_deplace = True

    def _armer_break_even(self, position: _Position, haut: float, bas: float) -> None:
        """Remonte le stop au prix d'entrée dès que le seuil en R est atteint.

        Le stop est placé exactement au prix de remplissage : le spread ayant déjà
        été payé à l'entrée, une sortie à ce niveau donne un résultat nul, ni gain
        ni perte.
        """
        if self.break_even_a is None or position.break_even_arme:
            return

        seuil = self.break_even_a * position.risque
        if position.sens is Sens.ACHAT:
            atteint = haut >= position.entree + seuil
        else:
            atteint = bas <= position.entree - seuil

        if atteint:
            position.stop = position.entree
            position.break_even_arme = True

    # ------------------------------------------------------------------
    # Clôture
    # ------------------------------------------------------------------

    def _cloturer(
        self,
        position: _Position,
        sortie: float,
        date: datetime,
        index: int,
        motif: str,
        capital: float,
    ) -> Trade:
        """Solde la position et calcule son résultat."""
        if position.sens is Sens.ACHAT:
            gain_prix = sortie - position.entree
        else:
            gain_prix = position.entree - sortie

        resultat_r = gain_prix / position.risque
        montant = resultat_r * position.montant_risque

        return Trade(
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
            capital_apres=capital + montant,
            bougies=index - position.index_entree,
            risque_pips=position.risque / self.valeur_pip,
            resultat_pips=gain_prix / self.valeur_pip,
            lots=position.lots,
            risque_theorique=position.risque_theorique,
            risque_reel=position.montant_risque,
            raison_signal=position.raison,
            stop_final=position.stop,
        )
