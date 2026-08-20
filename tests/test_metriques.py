"""Vérifie le calcul de la significativité statistique.

Un backtest ne produit qu'un échantillon. Sans mesure de l'incertitude, on
conclurait d'une centaine de trades ce qu'ils ne permettent pas d'affirmer. Ces
tests s'appuient sur des séries construites dont on connaît la réponse.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from marketlab.backtest.metriques import Metriques, _renseigner_significativite


def serie(valeurs: list[float]) -> pd.Series:
    return pd.Series(valeurs, dtype="float64")


def mesurer(valeurs: list[float]) -> Metriques:
    resultats = serie(valeurs)
    m = Metriques(trades=len(resultats), esperance_r=float(resultats.mean()))
    _renseigner_significativite(m, resultats)
    return m


def test_echantillon_minuscule_ne_conclut_pas():
    """Trois trades ne permettent aucune conclusion, quel que soit leur résultat."""
    assert not mesurer([3.0, -1.0, -1.0]).significatif


def test_serie_franchement_perdante_et_nombreuse_est_significative():
    """Cinq cents pertes de un R ne laissent aucun doute."""
    m = mesurer([-1.0] * 500)
    # Sans aucune dispersion, l'écart-type est nul : le calcul s'arrête, ce qui
    # est le comportement voulu plutôt qu'une division par zéro.
    assert m.ecart_type_r == 0.0

    # Avec une dispersion réaliste, le verdict tombe.
    valeurs = [3.0] * 50 + [-1.0] * 450
    m = mesurer(valeurs)
    assert m.esperance_r < 0
    assert m.significatif


def test_zero_dans_l_intervalle_signifie_non_concluant():
    """Une espérance nulle ne peut pas être distinguée de zéro."""
    m = mesurer([3.0] * 100 + [-1.0] * 300)
    assert m.esperance_r == pytest.approx(0.0)
    assert m.ic95_bas < 0 < m.ic95_haut
    assert not m.significatif


def test_l_intervalle_encadre_l_esperance():
    m = mesurer([3.0] * 80 + [-1.0] * 320)
    assert m.ic95_bas < m.esperance_r < m.ic95_haut


def test_intervalle_se_resserre_quand_l_echantillon_grandit():
    """Plus de trades, moins d'incertitude : c'est toute l'idée."""
    petit = mesurer([3.0] * 20 + [-1.0] * 80)
    grand = mesurer([3.0] * 200 + [-1.0] * 800)
    largeur_petit = petit.ic95_haut - petit.ic95_bas
    largeur_grand = grand.ic95_haut - grand.ic95_bas
    assert largeur_grand < largeur_petit
    # L'incertitude décroît comme la racine du nombre de trades.
    assert largeur_grand == pytest.approx(largeur_petit / np.sqrt(10), rel=0.05)


def test_trades_necessaires_depasse_l_echantillon_quand_non_concluant():
    """Le nombre annoncé doit être atteignable et cohérent avec le verdict."""
    m = mesurer([3.0] * 22 + [-1.0] * 78)
    assert not m.significatif
    assert m.trades_pour_conclure > m.trades
