"""Le pilote : la boucle de décision, unique, commune au backtest et au live.

À chaque bougie clôturée, il fait trois choses, toujours dans cet ordre :

1. **gérer** les positions ouvertes : armer le break-even, appliquer le stop
   suiveur proposé par la stratégie ;
2. **décider** : demander un signal à la stratégie ;
3. **entrer** : dimensionner la position et l'envoyer au courtier.

Il ne sait pas s'il est en simulation ou en réel : il parle à un `Broker`. C'est
ce qui garantit que la stratégie testée est exactement celle qui trade. Si le
backtest et le live avaient chacun leur boucle, rien ne garantirait qu'elles
restent identiques au fil des corrections.

DEUX RÈGLES QUE LE PILOTE IMPOSE, QUELLE QUE SOIT LA STRATÉGIE
----------------------------------------------------------------

* **Un stop ne fait que se resserrer**, et ne se pose jamais au-delà du prix de
  clôture. Une stratégie boguée ne peut ni éloigner un stop, ni en poser un que le
  prix a déjà franchi, ce qui inventerait une sortie à un prix jamais coté.
* **La stratégie ne dimensionne jamais.** Le volume vient de la couche de risque,
  à partir du capital et de la distance réelle au stop.

Le break-even et le stop suiveur s'appliquent à la CLÔTURE d'une bougie, jamais
au milieu : si le prix atteint le seuil puis revient au stop dans la même bougie,
on ne sait pas dans quel ordre, et la convention pessimiste du simulateur joue.

DEUX BRANCHEMENTS OPTIONNELS, UTILISÉS EN LIVE
------------------------------------------------

* un **garde** est consulté avant chaque entrée et peut la bloquer (perte du
  jour, spread anormal, arrêt demandé). Il ne touche jamais aux positions
  ouvertes : un stop suiveur continue de suivre même un jour perdant ;
* un **observateur** reçoit chaque décision et chaque déplacement de stop, pour
  les journaliser. Le pilote ne sait rien de la base de données.

Le backtest ne branche ni l'un ni l'autre : son comportement reste celui prouvé
identique à l'ancien moteur.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pandas as pd

from marketlab.brokers.base import Broker, Deplacement, Ordre, OrdreRefuse, PositionOuverte
from marketlab.risk.dimensionnement import dimensionner
from marketlab.strategies.base import Sens, Signal, Strategie


class Issue:
    """Ce qu'il est advenu d'une bougie évaluée."""

    AUCUN_SIGNAL = "aucun signal"
    ENTREE = "entrée"
    PLACE = "ignoré : positions au maximum"
    BLOQUE = "bloqué par un garde-fou"
    PAS_DE_PRIX = "pas de prix"
    ECART = "refusé : prix au-delà du stop"
    REFUS = "refusé par le courtier"


@dataclass(frozen=True)
class Decision:
    """Une bougie évaluée par le pilote, et ce qui en a résulté."""

    instant: pd.Timestamp
    instrument: str
    issue: str
    signal: Signal | None = None
    detail: str = ""
    position: PositionOuverte | None = None


class Garde(Protocol):
    """Consulté avant chaque entrée. Renvoie la raison du blocage, ou None pour laisser passer."""

    def raison_de_bloquer(self, instrument: str, broker: Broker, bougie: pd.Series) -> str | None: ...


class Observateur(Protocol):
    """Reçoit ce que fait le pilote, pour le journaliser."""

    def decision(self, decision: Decision) -> None: ...

    def deplacement(
        self, position: PositionOuverte, ancien: float, nouveau: float, raison: Deplacement
    ) -> None: ...


@dataclass
class Compteurs:
    """Ce que le pilote a vu passer, pour savoir ce que les limites font manquer."""

    bougies_evaluees: int = 0
    signaux_emis: int = 0
    #: Signal valide, mais plus de place pour une position de plus.
    signaux_ignores: int = 0
    #: Entrée impossible : écart d'ouverture au-delà du stop, ou refus du courtier.
    entrees_refusees: int = 0


class Pilote:
    """Relie une stratégie à un courtier, pour un instrument."""

    def __init__(
        self,
        strategie: Strategie,
        broker: Broker,
        instrument: str,
        risque_par_trade: float = 0.002,
        positions_max: int | None = 1,
        break_even_a: float | None = None,
        garde: Garde | None = None,
        observateur: Observateur | None = None,
    ) -> None:
        """
        Args:
            risque_par_trade: fraction du capital risquée (0.002 = 0,2 %).
            positions_max: positions ouvertes simultanément ; None lève la limite.
                Lever la limite multiplie l'exposition, pas seulement le nombre
                de trades : le risque s'applique à CHAQUE position.
            break_even_a: seuil en R où le stop remonte à l'entrée ; None le désactive.
            garde: garde-fous consultés avant chaque entrée (live).
            observateur: destinataire des décisions, pour le journal (live).
        """
        self.strategie = strategie
        self.broker = broker
        self.instrument = instrument
        self.risque_par_trade = risque_par_trade
        self.positions_max = positions_max
        self.break_even_a = break_even_a
        self.garde = garde
        self.observateur = observateur
        self.compteurs = Compteurs()

    def sur_cloture(self, preparees: pd.DataFrame) -> None:
        """Réagit à la clôture de la dernière bougie de `preparees`.

        `preparees` porte déjà les indicateurs de la stratégie, et s'arrête à la
        bougie qui vient de clôturer : aucune bougie future n'y figure.
        """
        bougie = preparees.iloc[-1]

        # 1. Gérer les positions ouvertes.
        for position in self.broker.positions(self.instrument):
            self._armer_break_even(position, bougie)
            self._suivre(position, bougie)

        # 2. Décider.
        if len(preparees) <= self.strategie.bougies_minimum:
            return
        self.compteurs.bougies_evaluees += 1
        signal = self.strategie.evaluer(preparees)
        if signal is None:
            self._noter(bougie, Issue.AUCUN_SIGNAL)
            return
        self.compteurs.signaux_emis += 1

        # Le compte se fait après les clôtures de cette bougie : une position
        # soldée libère sa place pour un signal détecté sur la même bougie.
        ouvertes = len(self.broker.positions(self.instrument))
        if self.positions_max is not None and ouvertes >= self.positions_max:
            self.compteurs.signaux_ignores += 1
            self._noter(bougie, Issue.PLACE, signal)
            return

        if self.garde is not None:
            raison = self.garde.raison_de_bloquer(self.instrument, self.broker, bougie)
            if raison is not None:
                self._noter(bougie, Issue.BLOQUE, signal, raison)
                return

        # 3. Entrer.
        issue, detail, position = self._entrer(signal)
        self._noter(bougie, issue, signal, detail, position)

    def _noter(
        self,
        bougie: pd.Series,
        issue: str,
        signal: Signal | None = None,
        detail: str = "",
        position: PositionOuverte | None = None,
    ) -> None:
        if self.observateur is not None:
            self.observateur.decision(
                Decision(bougie.name, self.instrument, issue, signal, detail, position)
            )

    # ------------------------------------------------------------------
    # Entrée
    # ------------------------------------------------------------------

    def _entrer(self, signal: Signal) -> tuple[str, str, PositionOuverte | None]:
        """Dimensionne et envoie l'ordre, ou renonce.

        Le stop garde le niveau structurel choisi par la stratégie. L'objectif est
        recalculé à partir du risque RÉELLEMENT pris : le prix de remplissage
        diffère du prix de référence du signal, et le rapport gain/risque annoncé
        doit être tenu.
        """
        prix = self.broker.cotation(self.instrument, signal.sens)
        if prix is None:
            # Pas de prix : fin d'historique, ou marché fermé. Le signal est
            # perdu, sans être compté comme un refus.
            return Issue.PAS_DE_PRIX, "", None

        if signal.sens is Sens.ACHAT:
            risque = prix - signal.stop
            objectif = prix + signal.ratio * risque
        else:
            risque = signal.stop - prix
            objectif = prix - signal.ratio * risque

        # Un écart d'ouverture peut placer le prix au-delà du stop : la position
        # serait perdante avant même d'exister. On renonce.
        if risque <= 0:
            self.compteurs.entrees_refusees += 1
            return Issue.ECART, f"prix {prix} au-delà du stop {signal.stop}", None

        risque_vise = self.broker.compte().capital * self.risque_par_trade
        spec = self.broker.specification(self.instrument)
        volume, _ = dimensionner(risque, risque_vise, spec)

        try:
            position = self.broker.ouvrir(
                Ordre(
                    instrument=self.instrument,
                    sens=signal.sens,
                    volume=volume,
                    stop=signal.stop,
                    objectif=objectif,
                    raison=signal.raison,
                    risque_vise=risque_vise,
                )
            )
        except OrdreRefuse as refus:
            self.compteurs.entrees_refusees += 1
            return Issue.REFUS, str(refus), None
        return Issue.ENTREE, f"{volume} lot(s) à {prix}", position

    # ------------------------------------------------------------------
    # Gestion des positions ouvertes
    # ------------------------------------------------------------------

    def _armer_break_even(self, position: PositionOuverte, bougie: pd.Series) -> None:
        """Remonte le stop au prix d'entrée dès que le seuil en R est atteint.

        Le stop est placé exactement au prix de remplissage : le spread ayant déjà
        été payé à l'entrée, une sortie à ce niveau donne un résultat nul.
        """
        if self.break_even_a is None or position.break_even_arme:
            return

        seuil = self.break_even_a * position.risque
        if position.sens is Sens.ACHAT:
            atteint = float(bougie["high"]) >= position.entree + seuil
        else:
            atteint = float(bougie["low"]) <= position.entree - seuil

        if atteint:
            self._deplacer(position, position.entree, Deplacement.BREAK_EVEN)

    def _suivre(self, position: PositionOuverte, bougie: pd.Series) -> None:
        """Applique le stop proposé par la stratégie, s'il est acceptable.

        Deux refus, silencieux car ce ne sont pas des erreurs : un stop qui
        s'éloignerait du prix, et un stop déjà franchi par la clôture.
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
            self._deplacer(position, float(propose), Deplacement.SUIVEUR)

    def _deplacer(self, position: PositionOuverte, niveau: float, raison: Deplacement) -> None:
        """Demande au courtier de déplacer le stop.

        Un refus n'arrête pas le pilote : la position garde son stop précédent,
        qui la protège toujours, et la prochaine clôture refera la demande.
        """
        ancien = position.stop
        try:
            self.broker.modifier_stop(position, niveau, raison)
        except OrdreRefuse:
            return
        if self.observateur is not None:
            self.observateur.deplacement(position, ancien, niveau, raison)
