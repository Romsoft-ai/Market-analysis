"""Vérifie les règles propres à B2 et B3 sur des séries construites.

Ce qui vaut pour toutes les stratégies (pas de regard vers l'avenir, journal,
cohérence avec leurs propres contrôles) est déjà couvert par le test de contrat.
On ne vérifie ici que ce qui fait la singularité de chacune.
"""

from __future__ import annotations

import pytest
from series import collecter, marche_aleatoire

from marketlab.backtest.moteur import Backtest, MotifSortie
from marketlab.strategies.base import Sens
from marketlab.strategies.catalogue.b2_bollinger_macd import BollingerMacd
from marketlab.strategies.catalogue.b2_bollinger_macd import Parametres as ParametresB2
from marketlab.strategies.catalogue.b3_supertrend_rsi import Parametres as ParametresB3
from marketlab.strategies.catalogue.b3_supertrend_rsi import SupertrendRsi

# --------------------------------------------------------------------------
# B2 : retour à la moyenne
# --------------------------------------------------------------------------


def test_b2_entre_avant_la_moyenne_et_vise_la_bande_opposee():
    """Achat sous la moyenne, objectif sur la bande haute ; vente symétrique."""
    signaux = collecter(BollingerMacd(), marche_aleatoire())
    assert signaux
    for bougie, s in signaux:
        if s.sens is Sens.ACHAT:
            assert s.entree < bougie["bb_mediane"]
            assert s.objectif == bougie["bb_haute"]
        else:
            assert s.entree > bougie["bb_mediane"]
            assert s.objectif == bougie["bb_basse"]


def test_b2_ne_prend_aucun_trade_sous_le_ratio_minimal():
    for _, s in collecter(BollingerMacd(), marche_aleatoire()):
        assert s.ratio >= 1.0


def test_b2_le_ratio_minimal_filtre_effectivement():
    donnees = marche_aleatoire()
    tous = collecter(BollingerMacd(ParametresB2(ratio_minimum=0.0)), donnees)
    filtres = collecter(BollingerMacd(), donnees)
    assert len(filtres) < len(tous)


def test_b2_exige_un_contact_avec_la_bande():
    for bougie, s in collecter(BollingerMacd(), marche_aleatoire()):
        assert bool(bougie["contact_bas" if s.sens is Sens.ACHAT else "contact_haut"])


def test_b2_une_fenetre_de_contact_plus_large_donne_plus_de_signaux():
    """Le contact sur la seule bougie du croisement est bien plus rare : c'est ce
    qui justifie la fenêtre de cinq bougies."""
    donnees = marche_aleatoire()
    une = collecter(BollingerMacd(ParametresB2(bougies_contact=1)), donnees)
    cinq = collecter(BollingerMacd(), donnees)
    assert len(cinq) > len(une)


# --------------------------------------------------------------------------
# B3 : bascule SuperTrend et stop suiveur
# --------------------------------------------------------------------------


def test_b3_n_entre_que_sur_une_bascule():
    for bougie, s in collecter(SupertrendRsi(), marche_aleatoire()):
        attendu = 1.0 if s.sens is Sens.ACHAT else -1.0
        assert bougie["tendance"] == attendu
        assert bougie["tendance_prec"] == -attendu


def test_b3_stop_initial_sur_la_ligne_et_objectif_a_trois_r():
    for bougie, s in collecter(SupertrendRsi(), marche_aleatoire()):
        assert s.stop == bougie["supertrend"]
        assert s.ratio == pytest.approx(3.0)


def test_b3_propose_la_ligne_tant_que_la_tendance_tient():
    strategie = SupertrendRsi()
    prepare = strategie.preparer(marche_aleatoire())
    haussiere = prepare[prepare["tendance"] == 1.0].iloc[50]
    assert strategie.ajuster_stop(Sens.ACHAT, 0.0, haussiere) == haussiere["supertrend"]
    # Contre la tendance, aucune proposition : la ligne est de l'autre côté du prix.
    assert strategie.ajuster_stop(Sens.VENTE, 1e9, haussiere) is None


def test_b3_en_backtest_le_stop_suit_vraiment():
    """Sur une vraie simulation, des sorties par stop suiveur existent, et leur
    stop final est toujours plus serré que le stop initial."""
    resultat = Backtest(SupertrendRsi(), spread=0.0, break_even_a=None).executer(
        marche_aleatoire()
    )
    suivis = [t for t in resultat.trades if t.motif == MotifSortie.STOP_SUIVEUR]
    assert suivis, "aucune sortie par stop suiveur : le suivi ne s'applique pas"
    for t in suivis:
        if t.sens is Sens.ACHAT:
            assert t.stop_final > t.stop_initial
        else:
            assert t.stop_final < t.stop_initial


def test_b3_sans_filtre_de_session_accepte_toute_heure():
    donnees = marche_aleatoire()
    avec = collecter(SupertrendRsi(), donnees)
    sans = collecter(SupertrendRsi(ParametresB3(sessions=())), donnees)
    assert len(sans) > len(avec)
