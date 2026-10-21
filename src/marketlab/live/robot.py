"""La boucle du robot : se réveiller à chaque clôture, lire, décider, journaliser.

Le robot n'ajoute aucune logique de trading : il appelle le pilote du bloc 4, le
même que celui du backtest. Son travail est de l'appeler au BON MOMENT, sur les
BONNES bougies, et de ne jamais s'arrêter sur un incident.

LES RÈGLES DE LA BOUCLE
-----------------------

* **Réveil 5 secondes après chaque clôture**, le temps que la dernière minute de
  la bougie arrive chez MetaTrader.
* **Jamais deux fois la même bougie.** La dernière bougie traitée est retenue par
  le journal, qui survit à un redémarrage.
* **Jamais une bougie périmée.** Une bougie clôturée depuis plus de deux minutes
  (robot démarré en cours de route, coupure réseau, PC en veille) n'est PAS
  tradée : entrer dix minutes après la clôture, à un autre prix, ne serait plus
  la décision qu'a mesurée le backtest. Elle est notée comme vue, et la
  suivante sera traitée normalement.
* **Un incident ne tue pas la boucle.** Connexion perdue, terminal muet, ordre
  refusé : on journalise, on tente de se reconnecter, on réessaie avec une
  attente qui double à chaque échec (plafonnée à cinq minutes). Pendant ce temps
  les positions restent protégées par leurs stops, posés chez le courtier.
* **L'arrêt est toujours propre** : drapeau levé dans le journal, ou Ctrl+C.
  Rien n'est fermé de force ; les positions gardent leur stop et leur objectif.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import pandas as pd

from marketlab.brokers.base import Broker, OrdreRefuse
from marketlab.data.mt5_session import MT5Error
from marketlab.live.flux import FluxMT5
from marketlab.live.journal import Journal
from marketlab.pilote import Garde, Pilote
from marketlab.strategies.base import Strategie

#: Délai après la clôture avant de lire, pour laisser arriver la dernière minute.
MARGE_REVEIL = pd.Timedelta(seconds=5)

#: Au-delà de ce délai après sa clôture, une bougie n'est plus tradée.
FRAICHEUR_MAX = pd.Timedelta(minutes=2)

#: Attente après un incident : elle double à chaque échec, jusqu'à ce plafond.
ATTENTE_INITIALE = 5.0
ATTENTE_MAX = 300.0

#: Erreurs qui relèvent de l'environnement (réseau, terminal, courtier) et
#: justifient une nouvelle tentative. Une erreur de programmation, elle, doit
#: arrêter le robot : réessayer en boucle un code faux ne le rendrait pas juste.
ERREURS_PASSAGERES = (MT5Error, OrdreRefuse, ConnectionError, TimeoutError, OSError)


class Etat:
    """Résultat d'un cycle, pour le journal et les tests."""

    NOUVELLE = "nouvelle bougie traitée"
    RIEN = "rien de neuf"
    PERIMEE = "bougie périmée, vue sans être tradée"
    SANS_DONNEES = "aucune bougie clôturée"


class Horloge:
    """Le temps du PC, isolé pour que les tests puissent le simuler."""

    def maintenant(self) -> pd.Timestamp:
        return pd.Timestamp.now(tz="UTC")

    def dormir(self, secondes: float) -> None:
        if secondes > 0:
            time.sleep(secondes)


class Robot:
    """Une stratégie, un instrument, un courtier : le pilote appelé à chaque clôture."""

    def __init__(
        self,
        strategie: Strategie,
        broker: Broker,
        flux: FluxMT5,
        instrument: str,
        journal: Journal,
        garde: Garde | None = None,
        horloge: Horloge | None = None,
        reconnecter: Callable[[], None] | None = None,
        risque_par_trade: float = 0.002,
        positions_max: int = 1,
    ) -> None:
        self.strategie = strategie
        self.flux = flux
        self.instrument = instrument
        self.journal = journal
        self.horloge = horloge or Horloge()
        self.reconnecter = reconnecter
        self.pilote = Pilote(
            strategie,
            broker,
            instrument,
            risque_par_trade=risque_par_trade,
            positions_max=positions_max,
            garde=garde,
            observateur=journal,
        )
        self.derniere = journal.derniere_bougie_traitee()

    # ------------------------------------------------------------------
    # Un cycle
    # ------------------------------------------------------------------

    def cycle(self) -> str:
        """Lit les bougies clôturées et réagit à la dernière, si elle est nouvelle et fraîche."""
        bougies = self.flux.bougies_cloturees(self.instrument)
        if bougies.empty:
            return Etat.SANS_DONNEES

        derniere = bougies.index[-1]
        if self.derniere is not None and derniere <= self.derniere:
            return Etat.RIEN

        if self.derniere is not None:
            manquees = int(((bougies.index > self.derniere) & (bougies.index < derniere)).sum())
            if manquees:
                self.journal.incident(
                    f"{manquees} bougie(s) clôturée(s) sans être traitée(s) depuis "
                    f"{self.derniere:%Y-%m-%d %H:%M} : robot arrêté ou déconnecté entre-temps"
                )

        self.journal.bougie(self.instrument, self.flux.echelle, bougies.iloc[-1])

        heure_serveur = self.flux.heure_serveur(self.instrument)
        fin = derniere + self.flux.duree
        if heure_serveur is None or heure_serveur - fin > FRAICHEUR_MAX:
            self._marquer(derniere)
            return Etat.PERIMEE

        self.pilote.sur_cloture(self.strategie.preparer(bougies))
        self._marquer(derniere)
        return Etat.NOUVELLE

    def _marquer(self, instant: pd.Timestamp) -> None:
        self.derniere = instant
        self.journal.marquer_traitee(instant)

    # ------------------------------------------------------------------
    # La boucle
    # ------------------------------------------------------------------

    def prochain_reveil(self, maintenant: pd.Timestamp) -> pd.Timestamp:
        """Prochaine clôture de bougie, plus la marge de réveil.

        Les serveurs sont décalés d'un nombre ENTIER d'heures par rapport à UTC :
        une clôture M15 du serveur tombe donc aussi sur un quart d'heure UTC, et
        l'horloge du PC suffit à savoir QUAND se réveiller. Ce qui est lu au
        réveil, en revanche, est daté par le serveur.
        """
        cloture = maintenant.floor(self.flux.duree) + self.flux.duree
        reveil = cloture + MARGE_REVEIL
        if reveil - self.flux.duree > maintenant:
            # Une clôture vient de passer mais la marge court encore : on se
            # réveille au bout de cette marge pour la lire, pas un quart d'heure plus tard.
            reveil -= self.flux.duree
        return reveil

    def tourner(self, cycles_max: int | None = None) -> None:
        """Tourne jusqu'à l'arrêt demandé (ou `cycles_max` réveils, pour les tests)."""
        self.journal.demarrage({
            "stratégie": self.strategie.code,
            "instrument": self.instrument,
            "échelle": self.flux.echelle,
            "réglages": self.strategie.parametres,
        })
        attente = ATTENTE_INITIALE
        cycles = 0
        while cycles_max is None or cycles < cycles_max:
            cycles += 1
            if self.journal.arret_demande():
                self.journal.arret("arrêt demandé")
                return
            try:
                self.cycle()
                attente = ATTENTE_INITIALE
                self.journal.battement(self.horloge.maintenant())
            except ERREURS_PASSAGERES as erreur:
                self.journal.incident(f"{type(erreur).__name__} : {erreur}")
                self._tenter_reconnexion()
                self.horloge.dormir(attente)
                attente = min(attente * 2, ATTENTE_MAX)
                continue
            maintenant = self.horloge.maintenant()
            self.horloge.dormir((self.prochain_reveil(maintenant) - maintenant).total_seconds())
        self.journal.arret(f"{cycles_max} cycles effectués")

    def _tenter_reconnexion(self) -> None:
        if self.reconnecter is None:
            return
        try:
            self.reconnecter()
        except ERREURS_PASSAGERES as erreur:
            self.journal.incident(f"reconnexion échouée : {erreur}")
