"""Vérifie le moteur de simulation sur des scénarios entièrement maîtrisés.

Méthode : plutôt que d'utiliser une vraie stratégie, on injecte une stratégie
factice qui émet un signal connu à une bougie connue. Chaque test construit alors
une série de prix dont on connaît le dénouement à l'avance, ce qui permet de
vérifier le chiffre exact plutôt qu'une tendance.

C'est indispensable ici : un moteur de backtest faux ne plante pas, il produit des
résultats plausibles.
"""

from __future__ import annotations

import pandas as pd
import pytest

from marketlab.backtest.metriques import calculer
from marketlab.backtest.moteur import Backtest, MotifSortie
from marketlab.strategies.base import Sens, Signal, Strategie


class StrategieFactice(Strategie):
    """Émet un signal donné, une seule fois, à l'index demandé."""

    nom = "factice"

    def __init__(self, signal: Signal, a_index: int = 3, minimum: int = 3) -> None:
        self.signal = signal
        self.a_index = a_index
        self.minimum = minimum

    @property
    def bougies_minimum(self) -> int:
        return self.minimum

    def preparer(self, bougies: pd.DataFrame) -> pd.DataFrame:
        return bougies.copy()

    def evaluer(self, historique: pd.DataFrame) -> Signal | None:
        if len(historique) - 1 == self.a_index:
            return self.signal
        return None


def serie(lignes: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    """Construit des bougies à partir de quadruplets (open, high, low, close)."""
    index = pd.date_range("2024-01-01", periods=len(lignes), freq="15min", tz="UTC")
    return pd.DataFrame(
        lignes, columns=["open", "high", "low", "close"], index=index
    )


PLAT = (100.0, 100.0, 100.0, 100.0)


# --------------------------------------------------------------------------
# Entrée
# --------------------------------------------------------------------------


def test_entree_a_l_ouverture_de_la_bougie_suivante_avec_spread():
    """Le signal naît en bougie 3 ; l'entrée se fait à l'ouverture de la 4."""
    signal = Signal(Sens.ACHAT, entree=100.0, stop=99.0, objectif=103.0)
    donnees = serie([PLAT] * 4 + [(102.0, 102.0, 102.0, 102.0)] * 6)

    moteur = Backtest(StrategieFactice(signal), spread=0.1, break_even_a=None)
    resultat = moteur.executer(donnees)

    assert len(resultat.trades) == 1
    # Ouverture de la bougie 4 = 102.0, plus le spread de 0.1
    assert resultat.trades[0].entree == pytest.approx(102.1)


def test_entree_refusee_si_l_ecart_place_le_prix_sous_le_stop():
    """Un gap sous le stop rendrait la position perdante avant d'exister."""
    signal = Signal(Sens.ACHAT, entree=100.0, stop=99.0, objectif=103.0)
    # La bougie 4 ouvre à 98, soit sous le stop de 99.
    donnees = serie([PLAT] * 4 + [(98.0, 98.0, 98.0, 98.0)] * 4)

    resultat = Backtest(StrategieFactice(signal), spread=0.0).executer(donnees)

    assert resultat.trades == []
    assert resultat.entrees_refusees == 1


# --------------------------------------------------------------------------
# Sortie
# --------------------------------------------------------------------------


def test_objectif_atteint_donne_le_ratio_annonce():
    """Un objectif à 3R doit rendre exactement +3 R."""
    signal = Signal(Sens.ACHAT, entree=100.0, stop=99.0, objectif=103.0)
    donnees = serie(
        [PLAT] * 4
        + [(100.0, 100.0, 100.0, 100.0)]
        + [(100.0, 103.5, 100.0, 103.0)]  # l'objectif est franchi
        + [PLAT] * 2
    )

    resultat = Backtest(
        StrategieFactice(signal), spread=0.0, break_even_a=None
    ).executer(donnees)

    assert len(resultat.trades) == 1
    trade = resultat.trades[0]
    assert trade.motif == MotifSortie.OBJECTIF
    assert trade.resultat_r == pytest.approx(3.0)


def test_stop_touche_donne_moins_un_r():
    signal = Signal(Sens.ACHAT, entree=100.0, stop=99.0, objectif=103.0)
    donnees = serie(
        [PLAT] * 4
        + [(100.0, 100.0, 100.0, 100.0)]
        + [(100.0, 100.0, 98.5, 99.0)]  # le stop est franchi
        + [PLAT] * 2
    )

    resultat = Backtest(
        StrategieFactice(signal), spread=0.0, break_even_a=None
    ).executer(donnees)

    trade = resultat.trades[0]
    assert trade.motif == MotifSortie.STOP
    assert trade.resultat_r == pytest.approx(-1.0)


def test_convention_pessimiste_quand_les_deux_niveaux_sont_dans_la_bougie():
    """Stop ET objectif dans la même bougie : on suppose le stop en premier.

    C'est le choix méthodologique central du moteur. S'il changeait sans qu'on
    s'en aperçoive, tous les résultats seraient faussés vers le haut.
    """
    signal = Signal(Sens.ACHAT, entree=100.0, stop=99.0, objectif=103.0)
    donnees = serie(
        [PLAT] * 4
        + [(100.0, 100.0, 100.0, 100.0)]
        + [(100.0, 104.0, 98.0, 101.0)]  # les deux niveaux sont traversés
        + [PLAT] * 2
    )

    resultat = Backtest(
        StrategieFactice(signal), spread=0.0, break_even_a=None
    ).executer(donnees)

    trade = resultat.trades[0]
    assert trade.motif == MotifSortie.STOP
    assert trade.resultat_r == pytest.approx(-1.0)


def test_position_encore_ouverte_est_cloturee_en_fin_de_periode():
    signal = Signal(Sens.ACHAT, entree=100.0, stop=99.0, objectif=103.0)
    donnees = serie([PLAT] * 4 + [(100.0, 100.5, 99.5, 100.2)] * 3)

    resultat = Backtest(
        StrategieFactice(signal), spread=0.0, break_even_a=None
    ).executer(donnees)

    assert resultat.trades[0].motif == MotifSortie.FIN_PERIODE


# --------------------------------------------------------------------------
# Break-even
# --------------------------------------------------------------------------


def test_break_even_ramene_le_stop_a_l_entree():
    """Après +1R puis retour sur l'entrée, le résultat doit être nul."""
    signal = Signal(Sens.ACHAT, entree=100.0, stop=99.0, objectif=103.0)
    donnees = serie(
        [PLAT] * 4
        + [(100.0, 100.0, 100.0, 100.0)]
        + [(100.0, 101.2, 100.0, 101.0)]  # +1R atteint : le stop remonte
        + [(101.0, 101.0, 99.5, 99.8)]  # retour sur l'entrée
        + [PLAT] * 2
    )

    resultat = Backtest(
        StrategieFactice(signal), spread=0.0, break_even_a=1.0
    ).executer(donnees)

    trade = resultat.trades[0]
    assert trade.motif == MotifSortie.BREAK_EVEN
    assert trade.resultat_r == pytest.approx(0.0)


def test_sans_break_even_le_meme_scenario_perd_un_r():
    """Contrôle : le break-even change bien le dénouement."""
    signal = Signal(Sens.ACHAT, entree=100.0, stop=99.0, objectif=103.0)
    donnees = serie(
        [PLAT] * 4
        + [(100.0, 100.0, 100.0, 100.0)]
        + [(100.0, 101.2, 100.0, 101.0)]
        + [(101.0, 101.0, 98.5, 99.0)]
        + [PLAT] * 2
    )

    resultat = Backtest(
        StrategieFactice(signal), spread=0.0, break_even_a=None
    ).executer(donnees)

    assert resultat.trades[0].resultat_r == pytest.approx(-1.0)


def test_break_even_ne_s_arme_pas_avant_le_seuil():
    signal = Signal(Sens.ACHAT, entree=100.0, stop=99.0, objectif=103.0)
    donnees = serie(
        [PLAT] * 4
        + [(100.0, 100.0, 100.0, 100.0)]
        + [(100.0, 100.8, 100.0, 100.5)]  # +0,8R seulement
        + [(100.5, 100.5, 98.5, 99.0)]
        + [PLAT] * 2
    )

    resultat = Backtest(
        StrategieFactice(signal), spread=0.0, break_even_a=1.0
    ).executer(donnees)

    trade = resultat.trades[0]
    assert trade.motif == MotifSortie.STOP
    assert trade.resultat_r == pytest.approx(-1.0)


# --------------------------------------------------------------------------
# Vente
# --------------------------------------------------------------------------


def test_vente_objectif_atteint():
    signal = Signal(Sens.VENTE, entree=100.0, stop=101.0, objectif=97.0)
    donnees = serie(
        [PLAT] * 4
        + [(100.0, 100.0, 100.0, 100.0)]
        + [(100.0, 100.0, 96.5, 97.0)]
        + [PLAT] * 2
    )

    resultat = Backtest(
        StrategieFactice(signal), spread=0.0, break_even_a=None
    ).executer(donnees)

    trade = resultat.trades[0]
    assert trade.motif == MotifSortie.OBJECTIF
    assert trade.resultat_r == pytest.approx(3.0)


def test_vente_paie_le_spread_a_l_entree():
    """Une vente est remplie EN DESSOUS de l'ouverture."""
    signal = Signal(Sens.VENTE, entree=100.0, stop=101.0, objectif=97.0)
    donnees = serie([PLAT] * 4 + [(100.0, 100.0, 100.0, 100.0)] * 4)

    resultat = Backtest(
        StrategieFactice(signal), spread=0.2, break_even_a=None
    ).executer(donnees)

    assert resultat.trades[0].entree == pytest.approx(99.8)


# --------------------------------------------------------------------------
# Une position à la fois
# --------------------------------------------------------------------------


class StrategieBavarde(StrategieFactice):
    """Émet le même signal à chaque bougie, pour tester le verrou de position."""

    def evaluer(self, historique: pd.DataFrame) -> Signal | None:
        return self.signal if len(historique) > self.minimum else None


def test_une_seule_position_a_la_fois():
    """Malgré un signal à chaque bougie, jamais deux positions simultanées."""
    signal = Signal(Sens.ACHAT, entree=100.0, stop=99.0, objectif=103.0)
    donnees = serie([PLAT] * 4 + [(100.0, 100.4, 99.6, 100.0)] * 30)

    resultat = Backtest(
        StrategieBavarde(signal), spread=0.0, break_even_a=None
    ).executer(donnees)

    # Un seul trade ouvert et clôturé en fin de période, et des signaux ignorés.
    assert len(resultat.trades) == 1
    assert resultat.signaux_ignores > 0


# --------------------------------------------------------------------------
# Positions simultanées
# --------------------------------------------------------------------------


def test_sans_limite_chaque_signal_devient_un_trade():
    """Invariant de `positions_max=None` : plus aucun signal n'est écarté.

    Tout signal finit soit en trade, soit en entrée refusée pour cause d'écart
    d'ouverture. Seule exception, documentée dans le moteur : un signal émis sur
    la dernière bougie n'a plus de bougie où entrer. Au-delà de ce cas unique, un
    écart signalerait qu'un signal se perd en route sans être compté nulle part.
    """
    signal = Signal(Sens.ACHAT, entree=100.0, stop=99.0, objectif=103.0)
    donnees = serie([PLAT] * 4 + [(100.0, 100.4, 99.6, 100.0)] * 30)

    resultat = Backtest(
        StrategieBavarde(signal), spread=0.0, break_even_a=None, positions_max=None
    ).executer(donnees)

    assert resultat.signaux_ignores == 0
    assert len(resultat.trades) > 1

    perdus = (
        resultat.signaux_emis - len(resultat.trades) - resultat.entrees_refusees
    )
    assert perdus <= 1, f"{perdus} signaux se perdent sans être comptés"


def test_sans_limite_les_positions_se_chevauchent_vraiment():
    """Il ne suffit pas d'avoir plus de trades : ils doivent coexister.

    Sans ce contrôle, un moteur qui ouvrirait simplement plus vite en série
    passerait le test précédent sans jamais empiler quoi que ce soit.
    """
    signal = Signal(Sens.ACHAT, entree=100.0, stop=99.0, objectif=103.0)
    donnees = serie([PLAT] * 4 + [(100.0, 100.4, 99.6, 100.0)] * 30)

    tableau = Backtest(
        StrategieBavarde(signal), spread=0.0, break_even_a=None, positions_max=None
    ).executer(donnees).en_tableau()

    chevauchements = sum(
        1
        for _, a in tableau.iterrows()
        for _, b in tableau.iterrows()
        if a["date_entree"] < b["date_entree"] < a["date_sortie"]
    )
    assert chevauchements > 0


def test_la_limite_est_respectee_a_la_lettre():
    """Avec une limite de deux, jamais trois positions ouvertes en même temps."""
    signal = Signal(Sens.ACHAT, entree=100.0, stop=99.0, objectif=103.0)
    donnees = serie([PLAT] * 4 + [(100.0, 100.4, 99.6, 100.0)] * 30)

    tableau = Backtest(
        StrategieBavarde(signal), spread=0.0, break_even_a=None, positions_max=2
    ).executer(donnees).en_tableau()

    # Comptage par balayage : +1 à chaque entrée, -1 à chaque sortie.
    mouvements = [(d, 1) for d in tableau["date_entree"]]
    mouvements += [(d, -1) for d in tableau["date_sortie"]]
    ouvertes = maximum = 0
    for _, delta in sorted(mouvements, key=lambda m: (m[0], m[1])):
        ouvertes += delta
        maximum = max(maximum, ouvertes)
    assert maximum <= 2


def test_lever_la_limite_ne_change_pas_les_trades_deja_pris():
    """Le premier trade doit être identique avec et sans limite.

    C'est ce qui rend les deux réglages comparables : lever la limite AJOUTE des
    positions, elle ne modifie pas celles qui auraient été prises de toute façon.
    """
    signal = Signal(Sens.ACHAT, entree=100.0, stop=99.0, objectif=103.0)
    donnees = serie([PLAT] * 4 + [(100.0, 100.4, 99.6, 100.0)] * 30)

    def premier(limite):
        r = Backtest(
            StrategieBavarde(signal), spread=0.0, break_even_a=None,
            positions_max=limite,
        ).executer(donnees)
        return r.trades[0]

    avec, sans = premier(1), premier(None)
    assert avec.date_entree == sans.date_entree
    assert avec.entree == sans.entree
    assert avec.stop_initial == sans.stop_initial
    assert avec.objectif == sans.objectif
    assert avec.resultat_r == pytest.approx(sans.resultat_r)


# --------------------------------------------------------------------------
# Métriques
# --------------------------------------------------------------------------


def test_metriques_sur_un_trade_gagnant():
    signal = Signal(Sens.ACHAT, entree=100.0, stop=99.0, objectif=103.0)
    donnees = serie(
        [PLAT] * 4
        + [(100.0, 100.0, 100.0, 100.0)]
        + [(100.0, 103.5, 100.0, 103.0)]
        + [PLAT] * 2
    )

    moteur = Backtest(
        StrategieFactice(signal),
        spread=0.0,
        capital_initial=100_000.0,
        risque_par_trade=0.002,
        break_even_a=None,
    )
    m = calculer(moteur.executer(donnees))

    assert m.trades == 1
    assert m.gagnants == 1
    assert m.taux_reussite == pytest.approx(100.0)
    assert m.total_r == pytest.approx(3.0)
    # 3 R avec 0,2 % risqué sur 100 000 : 3 x 200 = 600
    assert m.capital_final == pytest.approx(100_600.0)
    assert m.rendement_pct == pytest.approx(0.6)


def test_metriques_sans_aucun_trade():
    signal = Signal(Sens.ACHAT, entree=100.0, stop=99.0, objectif=103.0)
    strategie = StrategieFactice(signal, a_index=999)
    m = calculer(Backtest(strategie, spread=0.0).executer(serie([PLAT] * 20)))
    assert m.trades == 0
