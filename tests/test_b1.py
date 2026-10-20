"""Vérifie les règles propres à B1 sur des séries construites.

Objectif : s'assurer que chacune des cinq conditions bloque bien un signal quand
elle n'est pas remplie. Une stratégie qui déclenche trop souvent ne se voit pas
dans un backtest : elle produit simplement des résultats faux.

Ce qui vaut pour TOUTES les stratégies (pas de regard vers l'avenir, journal,
cohérence avec ses propres contrôles) est vérifié dans test_contrat_strategies.py.
"""

from __future__ import annotations

import pandas as pd
import pytest
from series import bougies, collecter, marche_aleatoire

from marketlab.strategies.base import Sens
from marketlab.strategies.catalogue.b1_rsi_macd_ema import Parametres, RsiMacdEma

# --------------------------------------------------------------------------
# Structure
# --------------------------------------------------------------------------


def test_bougies_minimum_depend_de_la_plus_longue_periode():
    assert RsiMacdEma(Parametres(periode_ema=200)).bougies_minimum == 201


def test_les_reglages_par_defaut_sont_ceux_de_l_ancienne_b1v3():
    """Les règles sont figées : un changement de valeur par défaut doit se voir ici."""
    p = RsiMacdEma().parametres
    assert (p.periode_ema, p.macd_rapide, p.macd_lente, p.macd_signal) == (200, 12, 26, 9)
    assert (p.periode_rsi, p.rsi_plancher, p.rsi_plafond) == (14, 50.0, 70.0)
    assert (p.bougies_stop, p.ratio_objectif) == (10, 3.0)
    assert p.sessions == ("londres", "new_york")


def test_preparer_ajoute_les_colonnes_attendues():
    donnees = RsiMacdEma().preparer(marche_aleatoire(400))
    for colonne in ("ema", "macd", "macd_signal", "rsi", "croise_haut", "creux", "en_session"):
        assert colonne in donnees.columns


def test_preparer_refuse_des_colonnes_manquantes():
    with pytest.raises(ValueError, match="Colonnes manquantes"):
        RsiMacdEma().preparer(pd.DataFrame({"close": [1.0, 2.0]}))


def test_preparer_refuse_un_ordre_chronologique_inverse():
    with pytest.raises(ValueError, match="chronologique"):
        RsiMacdEma().preparer(marche_aleatoire(300).iloc[::-1])


def test_refuse_des_parametres_d_une_autre_strategie():
    with pytest.raises(TypeError, match="Parametres"):
        RsiMacdEma(object())


# --------------------------------------------------------------------------
# Absence de signal
# --------------------------------------------------------------------------


def test_pas_de_signal_sur_un_marche_plat():
    """Sans mouvement, le MACD ne croise jamais : aucun déclencheur."""
    assert not collecter(RsiMacdEma(), bougies([100.0] * 500))


# --------------------------------------------------------------------------
# Émission de signaux
# --------------------------------------------------------------------------


def test_emet_des_signaux_sur_un_marche_realiste():
    signaux = collecter(RsiMacdEma(), marche_aleatoire())
    assert signaux, "aucun signal émis sur une marche aléatoire de 4000 bougies"


@pytest.mark.parametrize("ratio", [2.0, 3.0, 5.0])
def test_l_objectif_respecte_le_ratio_demande(ratio):
    signaux = collecter(RsiMacdEma(Parametres(ratio_objectif=ratio)), marche_aleatoire())
    assert signaux
    for _, s in signaux:
        assert s.ratio == pytest.approx(ratio)


def test_changer_l_objectif_ne_change_aucune_entree():
    """Seule la sortie gagnante bouge : mêmes bougies, mêmes entrées, mêmes stops.

    Sans cette garantie, comparer deux objectifs reviendrait à comparer deux
    stratégies distinctes, et l'écart observé ne serait plus attribuable au seul
    changement d'objectif.
    """
    donnees = marche_aleatoire()
    a = collecter(RsiMacdEma(), donnees)
    b = collecter(RsiMacdEma(Parametres(ratio_objectif=5.0)), donnees)
    assert a
    assert [(x.name, s.sens, s.entree, s.stop) for x, s in a] == [
        (x.name, s.sens, s.entree, s.stop) for x, s in b
    ]


def test_le_stop_est_l_extreme_des_dernieres_bougies():
    for bougie, s in collecter(RsiMacdEma(), marche_aleatoire()):
        attendu = bougie["creux"] if s.sens is Sens.ACHAT else bougie["sommet"]
        assert s.stop == attendu


# --------------------------------------------------------------------------
# Chaque condition doit bloquer
# --------------------------------------------------------------------------


def test_le_filtre_rsi_bloque_effectivement():
    """Une fenêtre RSI impossible doit supprimer tout signal.

    Si le nombre de signaux ne changeait pas, c'est que le filtre ne serait pas
    réellement appliqué.
    """
    donnees = marche_aleatoire()
    assert collecter(RsiMacdEma(), donnees)
    assert not collecter(RsiMacdEma(Parametres(rsi_plancher=99.0, rsi_plafond=99.5)), donnees)


def test_chaque_signal_respecte_son_filtre_de_tendance():
    """Invariant : jamais d'achat sous l'EMA, jamais de vente au-dessus."""
    for bougie, s in collecter(RsiMacdEma(), marche_aleatoire()):
        if s.sens is Sens.ACHAT:
            assert bougie["close"] > bougie["ema"]
        else:
            assert bougie["close"] < bougie["ema"]


def test_chaque_signal_respecte_sa_fenetre_rsi():
    for bougie, s in collecter(RsiMacdEma(), marche_aleatoire()):
        if s.sens is Sens.ACHAT:
            assert 50.0 < bougie["rsi"] < 70.0
        else:
            assert 30.0 < bougie["rsi"] < 50.0


def test_chaque_signal_correspond_a_un_croisement_macd():
    for bougie, s in collecter(RsiMacdEma(), marche_aleatoire()):
        attendu = "croise_haut" if s.sens is Sens.ACHAT else "croise_bas"
        assert bool(bougie[attendu])


def test_le_croisement_se_fait_du_bon_cote_de_zero():
    """On achète la reprise après un repli, pas un mouvement déjà lancé."""
    for bougie, s in collecter(RsiMacdEma(), marche_aleatoire()):
        if s.sens is Sens.ACHAT:
            assert bougie["macd"] < 0
        else:
            assert bougie["macd"] > 0


def test_aucun_signal_hors_session():
    for bougie, _ in collecter(RsiMacdEma(), marche_aleatoire()):
        assert bool(bougie["en_session"])


def test_le_filtre_de_session_bloque_effectivement():
    """La même série, avec la seule session de Sydney : d'autres heures, d'autres signaux."""
    donnees = marche_aleatoire()
    londres_ny = {b.name for b, _ in collecter(RsiMacdEma(), donnees)}
    sydney = {b.name for b, _ in collecter(RsiMacdEma(Parametres(sessions=("sydney",))), donnees)}
    assert londres_ny
    assert londres_ny != sydney


def test_aucun_achat_en_tendance_baissiere_marquee():
    signaux = collecter(RsiMacdEma(), marche_aleatoire(derive=-0.05))
    assert all(s.sens is Sens.VENTE for _, s in signaux)
