"""Vérifie la boucle du robot et les garde-fous, sans terminal ni horloge réelle.

Tout est simulé : le flux rend des bougies choisies, l'horloge avance quand on le
lui dit, le courtier n'existe qu'en mémoire. On vérifie ainsi les cas qu'on ne
peut pas provoquer à volonté en live : bougie déjà vue, bougie périmée, coupure
de connexion, journée perdante, spread aberrant.
"""

from __future__ import annotations

import pandas as pd
import pytest

from marketlab.brokers.base import (
    Broker,
    Compte,
    Deplacement,
    Ordre,
    PositionOuverte,
    Specification,
)
from marketlab.data.mt5_session import MT5Error
from marketlab.live.journal import JournalMemoire
from marketlab.live.robot import Etat, Robot
from marketlab.pilote import Issue, Pilote
from marketlab.risk.garde_fous import GardeFous
from marketlab.strategies.base import Sens, Signal

DEBUT = pd.Timestamp("2026-10-21 10:00", tz="UTC")
QUART = pd.Timedelta(minutes=15)


def bougies(n: int, debut: pd.Timestamp = DEBUT) -> pd.DataFrame:
    index = pd.date_range(debut, periods=n, freq="15min")
    return pd.DataFrame({"open": 1.3, "high": 1.301, "low": 1.299, "close": 1.3,
                         "tick_volume": 10, "spread": 10}, index=index)


class FauxFlux:
    """Rend les bougies qu'on lui fixe, avec une heure serveur réglable."""

    echelle = "15min"
    duree = QUART

    def __init__(self) -> None:
        self.donnees = bougies(5)
        self.heure: pd.Timestamp | None = self.donnees.index[-1] + QUART + pd.Timedelta(seconds=5)
        self.panne = 0

    def bougies_cloturees(self, instrument):
        if self.panne:
            self.panne -= 1
            raise MT5Error("terminal déconnecté")
        return self.donnees

    def heure_serveur(self, instrument):
        return self.heure

    def ajouter_bougie(self):
        suivante = self.donnees.index[-1] + QUART
        self.donnees = pd.concat([self.donnees, bougies(1, suivante)])
        self.heure = suivante + QUART + pd.Timedelta(seconds=5)


class FauxCourtier(Broker):
    def __init__(self, capital=100_000.0, ask=1.3001, bid=1.3000) -> None:
        self.capital, self.ask, self.bid = capital, ask, bid
        self.ordres: list[Ordre] = []
        self.ouvertes: list[PositionOuverte] = []

    def compte(self):
        return Compte(self.capital)

    def specification(self, instrument):
        return Specification(point=0.00001, decimales=5, valeur_pip=0.0001,
                             valeur_pip_par_lot=10.0, volume_min=0.01, volume_pas=0.01)

    def cotation(self, instrument, sens):
        return self.ask if sens is Sens.ACHAT else self.bid

    def positions(self, instrument):
        return list(self.ouvertes)

    def ouvrir(self, ordre):
        self.ordres.append(ordre)
        return PositionOuverte(1, ordre.instrument, ordre.sens, ordre.volume, self.ask,
                               ordre.stop, ordre.stop, ordre.objectif, DEBUT)

    def modifier_stop(self, position, niveau, raison):
        position.stop = niveau

    def fermer(self, position):
        self.ouvertes.remove(position)


class Toujours:
    """Stratégie qui achète à chaque bougie et propose toujours de remonter le stop."""

    code = "T"
    parametres = "aucun"
    bougies_minimum = 0

    def __init__(self) -> None:
        self.preparations = 0

    def preparer(self, donnees):
        self.preparations += 1
        return donnees

    def evaluer(self, historique):
        return Signal(Sens.ACHAT, entree=1.3, stop=1.298, objectif=1.306)

    def ajuster_stop(self, sens, stop_actuel, bougie):
        return 1.2995


class FausseHorloge:
    def __init__(self, instant: pd.Timestamp) -> None:
        self.instant = instant
        self.sommes: list[float] = []

    def maintenant(self):
        return self.instant

    def dormir(self, secondes):
        self.sommes.append(secondes)
        self.instant += pd.Timedelta(seconds=secondes)


def robot(flux=None, courtier=None, journal=None, garde=None, **kw):
    return Robot(Toujours(), courtier or FauxCourtier(), flux or FauxFlux(), "GBPUSD",
                 journal or JournalMemoire(), garde=garde,
                 horloge=FausseHorloge(DEBUT), **kw)


# --------------------------------------------------------------------------
# Un cycle
# --------------------------------------------------------------------------


def test_une_nouvelle_bougie_est_traitee_une_seule_fois():
    r = robot()
    assert r.cycle() == Etat.NOUVELLE
    assert r.cycle() == Etat.RIEN
    assert len(r.pilote.broker.ordres) == 1


def test_la_bougie_suivante_est_traitee_a_son_tour():
    flux = FauxFlux()
    r = robot(flux=flux)
    r.cycle()
    flux.ajouter_bougie()
    assert r.cycle() == Etat.NOUVELLE
    assert len(r.pilote.broker.ordres) == 2


def test_une_bougie_perimee_n_est_pas_tradee():
    """Démarré dix minutes après la clôture : entrer maintenant ne serait plus la décision testée."""
    flux = FauxFlux()
    flux.heure += pd.Timedelta(minutes=10)
    r = robot(flux=flux)
    assert r.cycle() == Etat.PERIMEE
    assert not r.pilote.broker.ordres
    assert r.cycle() == Etat.RIEN, "vue une fois, elle n'est plus réexaminée"


def test_un_redemarrage_ne_retraite_pas_la_derniere_bougie():
    journal = JournalMemoire()
    flux = FauxFlux()
    robot(flux=flux, journal=journal).cycle()
    relance = robot(flux=flux, journal=journal)
    assert relance.cycle() == Etat.RIEN


def test_les_bougies_manquees_sont_signalees():
    journal = JournalMemoire()
    flux = FauxFlux()
    r = robot(flux=flux, journal=journal)
    r.cycle()
    for _ in range(3):
        flux.ajouter_bougie()
    r.cycle()
    incidents = [t for n, t in journal.evenements if n == "incident"]
    assert any("2 bougie(s)" in t for t in incidents)


def test_chaque_bougie_evaluee_laisse_une_decision():
    journal = JournalMemoire()
    robot(journal=journal).cycle()
    assert [d.issue for d in journal.decisions] == [Issue.ENTREE]


# --------------------------------------------------------------------------
# La boucle
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("maintenant", "attendu"),
    [
        ("10:15:03", "10:15:05"),  # dans la marge : on lit la clôture de 10:15
        ("10:15:06", "10:30:05"),  # marge passée : clôture suivante
        ("10:22:00", "10:30:05"),
    ],
)
def test_le_reveil_tombe_juste_apres_chaque_cloture(maintenant, attendu):
    r = robot()
    jour = "2026-10-21 "
    assert r.prochain_reveil(pd.Timestamp(jour + maintenant, tz="UTC")) == pd.Timestamp(
        jour + attendu, tz="UTC"
    )


def test_une_panne_ne_tue_pas_la_boucle():
    """Deux échecs de suite : incident journalisé, reconnexion tentée, attente qui double."""
    flux = FauxFlux()
    flux.panne = 2
    journal = JournalMemoire()
    reconnexions = []
    r = robot(flux=flux, journal=journal, reconnecter=lambda: reconnexions.append(1))
    r.tourner(cycles_max=3)

    assert len(reconnexions) == 2
    assert r.horloge.sommes[:2] == [5.0, 10.0]
    assert len(r.pilote.broker.ordres) == 1, "le troisième cycle a fini par passer"


def test_l_arret_demande_arrete_proprement():
    journal = JournalMemoire(arret_voulu=True)
    r = robot(journal=journal)
    r.tourner(cycles_max=5)
    assert not r.pilote.broker.ordres
    assert journal.evenements[-1] == ("arrêt", "arrêt demandé")


# --------------------------------------------------------------------------
# Garde-fous
# --------------------------------------------------------------------------


def pilote_garde(courtier, garde, journal):
    return Pilote(Toujours(), courtier, "GBPUSD", garde=garde, observateur=journal)


def test_la_perte_du_jour_bloque_les_entrees():
    courtier = FauxCourtier(capital=100_000.0)
    journal = JournalMemoire()
    pilote = pilote_garde(courtier, GardeFous(spread_reference_points=10), journal)
    pilote.sur_cloture(bougies(1))  # fixe le capital du matin
    courtier.capital = 98_900.0  # -1,1 %
    pilote.sur_cloture(bougies(1, DEBUT + QUART))

    assert journal.decisions[-1].issue == Issue.BLOQUE
    assert "perte du jour" in journal.decisions[-1].detail
    assert len(courtier.ordres) == 1


def test_le_compteur_de_perte_repart_le_lendemain():
    courtier = FauxCourtier(capital=100_000.0)
    journal = JournalMemoire()
    pilote = pilote_garde(courtier, GardeFous(spread_reference_points=10), journal)
    pilote.sur_cloture(bougies(1))
    courtier.capital = 98_900.0
    pilote.sur_cloture(bougies(1, DEBUT + pd.Timedelta(days=1)))
    assert journal.decisions[-1].issue == Issue.ENTREE


def test_un_spread_aberrant_bloque_les_entrees():
    """Spread de 40 points pour une médiane de 10 : plus de 3 fois la référence."""
    courtier = FauxCourtier(ask=1.30040, bid=1.30000)
    journal = JournalMemoire()
    pilote_garde(courtier, GardeFous(spread_reference_points=10), journal).sur_cloture(bougies(1))
    assert journal.decisions[-1].issue == Issue.BLOQUE
    assert "spread" in journal.decisions[-1].detail


def test_un_garde_fou_ne_bloque_jamais_la_gestion_des_positions():
    """Journée perdante : plus d'entrée, mais le stop suiveur continue de protéger."""
    courtier = FauxCourtier()
    position = PositionOuverte(7, "GBPUSD", Sens.ACHAT, 0.1, 1.2990, 1.2980, 1.2980, 1.3020, DEBUT)
    courtier.ouvertes = [position]
    journal = JournalMemoire()
    garde = GardeFous(spread_reference_points=10, arret_demande=lambda: True)
    pilote = Pilote(Toujours(), courtier, "GBPUSD", positions_max=2, garde=garde,
                    observateur=journal)
    pilote.sur_cloture(bougies(1))

    assert position.stop == 1.2995, "le stop a été remonté"
    assert not courtier.ordres, "mais aucune entrée"
    assert any(n == "stop" for n, _ in journal.evenements)


def test_le_deplacement_de_stop_est_journalise_avec_sa_raison():
    courtier = FauxCourtier()
    position = PositionOuverte(7, "GBPUSD", Sens.ACHAT, 0.1, 1.2990, 1.2980, 1.2980, 1.3020, DEBUT)
    courtier.ouvertes = [position]
    journal = JournalMemoire()
    Pilote(Toujours(), courtier, "GBPUSD", positions_max=2, observateur=journal).sur_cloture(bougies(1))
    assert ("stop", f"7 {Deplacement.SUIVEUR.value} : 1.298 → 1.2995") in journal.evenements
