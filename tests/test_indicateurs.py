"""Vérifie les indicateurs sur des cas dont on connaît la réponse à l'avance.

Un indicateur faux ne provoque pas d'erreur : il produit des chiffres plausibles
et un backtest crédible. C'est pourquoi ces tests s'appuient sur des séries
construites — série constante, hausse pure, baisse pure — où le résultat attendu
est déductible sans calcul.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import numpy as np
import pandas as pd
import pytest

from marketlab.strategies.base import Sens, Signal, SignalInvalide
from marketlab.strategies.indicateurs import (
    croisement_baissier,
    croisement_haussier,
    ema,
    macd,
    plus_bas,
    rsi,
)


def serie(valeurs: list[float]) -> pd.Series:
    return pd.Series(valeurs, dtype="float64")


# --------------------------------------------------------------------------
# EMA
# --------------------------------------------------------------------------


def test_ema_serie_constante_vaut_la_constante():
    """Sur un prix qui ne bouge pas, la moyenne vaut ce prix."""
    resultat = ema(serie([50.0] * 30), periode=10)
    assert np.allclose(resultat, 50.0)


def test_ema_suit_la_hausse_sans_la_depasser():
    """Une moyenne monte avec les prix, mais reste en dessous du dernier prix."""
    prix = serie([float(i) for i in range(1, 51)])
    resultat = ema(prix, periode=10)
    assert resultat.iloc[-1] < prix.iloc[-1]
    assert resultat.is_monotonic_increasing


def test_ema_courte_reagit_plus_vite_que_longue():
    prix = serie([10.0] * 20 + [20.0] * 20)
    courte = ema(prix, periode=5).iloc[25]
    longue = ema(prix, periode=20).iloc[25]
    assert courte > longue


def test_ema_periode_invalide():
    with pytest.raises(ValueError):
        ema(serie([1.0, 2.0]), periode=0)


# --------------------------------------------------------------------------
# MACD
# --------------------------------------------------------------------------


def test_macd_serie_constante_est_nul():
    """Sans mouvement, les deux moyennes coïncident : l'écart est nul."""
    resultat = macd(serie([100.0] * 60))
    assert np.allclose(resultat["macd"], 0.0)
    assert np.allclose(resultat["histogramme"], 0.0)


def test_macd_positif_en_tendance_haussiere():
    prix = serie([float(i) for i in range(1, 101)])
    resultat = macd(prix)
    assert resultat["macd"].iloc[-1] > 0


def test_macd_colonnes_et_coherence():
    resultat = macd(serie([float(i % 7) for i in range(80)]))
    assert list(resultat.columns) == ["macd", "signal", "histogramme"]
    ecart = resultat["macd"] - resultat["signal"]
    assert np.allclose(resultat["histogramme"], ecart)


def test_macd_periodes_incoherentes():
    with pytest.raises(ValueError):
        macd(serie([1.0] * 50), rapide=26, lente=12)


# --------------------------------------------------------------------------
# RSI
# --------------------------------------------------------------------------


def test_rsi_hausse_pure_vaut_cent():
    """Que des hausses : aucune baisse à comparer, le RSI sature à 100."""
    resultat = rsi(serie([float(i) for i in range(1, 60)]), periode=14)
    assert resultat.iloc[-1] == pytest.approx(100.0)


def test_rsi_baisse_pure_vaut_zero():
    resultat = rsi(serie([float(i) for i in range(60, 1, -1)]), periode=14)
    assert resultat.iloc[-1] == pytest.approx(0.0)


def test_rsi_reste_borne_entre_zero_et_cent():
    """Propriété fondamentale : sur n'importe quelle série, le RSI reste borné."""
    generateur = np.random.default_rng(42)
    prix = serie(100 + np.cumsum(generateur.normal(0, 1, 500)))
    resultat = rsi(prix).dropna()
    assert resultat.min() >= 0.0
    assert resultat.max() <= 100.0


def test_rsi_premiere_valeur_indeterminee():
    """Sans bougie précédente, aucune variation n'est calculable."""
    resultat = rsi(serie([10.0, 11.0, 12.0, 11.0, 13.0]), periode=2)
    assert np.isnan(resultat.iloc[0])


# --------------------------------------------------------------------------
# Croisements
# --------------------------------------------------------------------------


def test_croisement_haussier_est_un_evenement_ponctuel():
    """Le croisement ne doit être vrai qu'à la bougie du basculement."""
    rapide = serie([1.0, 2.0, 4.0, 5.0, 6.0])
    lente = serie([3.0, 3.0, 3.0, 3.0, 3.0])
    resultat = croisement_haussier(rapide, lente)
    assert resultat.tolist() == [False, False, True, False, False]


def test_croisement_baissier_est_un_evenement_ponctuel():
    rapide = serie([6.0, 5.0, 2.0, 1.0])
    lente = serie([3.0, 3.0, 3.0, 3.0])
    resultat = croisement_baissier(rapide, lente)
    assert resultat.tolist() == [False, False, True, False]


def test_pas_de_croisement_sans_franchissement():
    rapide = serie([1.0, 1.5, 2.0, 2.5])
    lente = serie([3.0, 3.0, 3.0, 3.0])
    assert not croisement_haussier(rapide, lente).any()


# --------------------------------------------------------------------------
# Plus bas glissant
# --------------------------------------------------------------------------


def test_plus_bas_glissant():
    resultat = plus_bas(serie([5.0, 3.0, 4.0, 6.0, 2.0]), bougies=3)
    assert np.isnan(resultat.iloc[0])
    assert np.isnan(resultat.iloc[1])
    assert resultat.iloc[2] == 3.0
    assert resultat.iloc[4] == 2.0


# --------------------------------------------------------------------------
# Contrat de signal
# --------------------------------------------------------------------------


def test_signal_achat_valide_calcule_risque_et_ratio():
    s = Signal(sens=Sens.ACHAT, entree=1.2700, stop=1.2685, objectif=1.2730)
    assert s.risque == pytest.approx(0.0015)
    assert s.ratio == pytest.approx(2.0)


def test_signal_vente_valide():
    s = Signal(sens=Sens.VENTE, entree=1.2700, stop=1.2715, objectif=1.2670)
    assert s.risque == pytest.approx(0.0015)
    assert s.ratio == pytest.approx(2.0)


def test_signal_achat_avec_stop_du_mauvais_cote_est_refuse():
    """Garde-fou essentiel : ce signal créerait une position qui ne peut pas perdre."""
    with pytest.raises(SignalInvalide):
        Signal(sens=Sens.ACHAT, entree=1.2700, stop=1.2730, objectif=1.2750)


def test_signal_vente_avec_objectif_du_mauvais_cote_est_refuse():
    with pytest.raises(SignalInvalide):
        Signal(sens=Sens.VENTE, entree=1.2700, stop=1.2715, objectif=1.2750)


def test_signal_est_immuable():
    """Un signal émis ne se modifie pas : la stratégie en émet un autre."""
    s = Signal(sens=Sens.ACHAT, entree=1.27, stop=1.26, objectif=1.29)
    with pytest.raises(FrozenInstanceError):
        s.entree = 1.28
