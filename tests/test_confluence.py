"""Vérifie la stratégie B1 sur des séries construites.

Objectif : s'assurer que chacune des trois conditions bloque bien un signal quand
elle n'est pas remplie. Une stratégie qui déclenche trop souvent ne se voit pas
dans un backtest — elle produit simplement des résultats faux.

Note de méthode. Une première version de ces tests utilisait des séries
parfaitement linéaires. Erreur : sans le moindre repli, le RSI n'a aucune baisse à
comparer et sature à 100 ; il ne traverse jamais la zone que la stratégie exige, et
aucun signal ne sortait. Les séries ci-dessous sont donc des marches aléatoires
avec dérive — bruitées comme un vrai prix — mais à graine fixe, donc reproductibles.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from marketlab.strategies.base import Sens, Signal
from marketlab.strategies.confluence import (
    ConfluenceRsiMacdEma,
    ConfluenceSessionR5,
    ConfluenceZero,
    ConfluenceZeroSession,
    ConfluenceZeroSessionR5,
    FiltreSession,
)


def bougies(closes: list[float]) -> pd.DataFrame:
    """Série de bougies minimale : hauts et bas serrés autour de la clôture."""
    index = pd.date_range("2024-01-01", periods=len(closes), freq="15min", tz="UTC")
    serie = pd.Series(closes, index=index, dtype="float64")
    return pd.DataFrame(
        {
            "open": serie.shift(1).fillna(serie.iloc[0]),
            "high": serie * 1.001,
            "low": serie * 0.999,
            "close": serie,
        },
        index=index,
    )


def marche_aleatoire(
    n: int = 1500, derive: float = 0.03, bruit: float = 0.4, graine: int = 7
) -> pd.DataFrame:
    """Prix bruité avec une dérive : le profil d'un vrai marché.

    `derive` positive = tendance haussière de fond, `bruit` = amplitude des
    oscillations. La graine rend la série identique à chaque exécution.
    """
    generateur = np.random.default_rng(graine)
    variations = generateur.normal(derive, bruit, n)
    return bougies(list(100 + np.cumsum(variations)))


def collecter(
    strategie: ConfluenceRsiMacdEma, donnees: pd.DataFrame
) -> list[tuple[pd.Series, Signal]]:
    """Retourne les couples (bougie de signal, signal) émis sur toute la série."""
    prepare = strategie.preparer(donnees)
    resultats = []
    for i in range(strategie.bougies_minimum, len(prepare)):
        signal = strategie.evaluer(prepare.iloc[: i + 1])
        if signal is not None:
            resultats.append((prepare.iloc[i], signal))
    return resultats


# --------------------------------------------------------------------------
# Structure
# --------------------------------------------------------------------------


def test_bougies_minimum_depend_de_la_plus_longue_periode():
    assert ConfluenceRsiMacdEma(periode_ema=200).bougies_minimum == 201


def test_preparer_ajoute_les_colonnes_attendues():
    donnees = ConfluenceRsiMacdEma().preparer(marche_aleatoire(400))
    for colonne in ("ema", "macd", "macd_signal", "rsi", "croise_haut", "creux"):
        assert colonne in donnees.columns


def test_preparer_refuse_des_colonnes_manquantes():
    with pytest.raises(ValueError, match="Colonnes manquantes"):
        ConfluenceRsiMacdEma().preparer(pd.DataFrame({"close": [1.0, 2.0]}))


def test_preparer_refuse_un_ordre_chronologique_inverse():
    with pytest.raises(ValueError, match="chronologique"):
        ConfluenceRsiMacdEma().preparer(marche_aleatoire(300).iloc[::-1])


# --------------------------------------------------------------------------
# Absence de signal
# --------------------------------------------------------------------------


def test_pas_de_signal_avant_assez_de_bougies():
    """Une EMA 200 n'a aucun sens sur 50 bougies."""
    strategie = ConfluenceRsiMacdEma()
    donnees = strategie.preparer(marche_aleatoire(400))
    assert strategie.evaluer(donnees.iloc[:50]) is None


def test_pas_de_signal_sur_un_marche_plat():
    """Sans mouvement, le MACD ne croise jamais : aucun déclencheur."""
    assert not collecter(ConfluenceRsiMacdEma(), bougies([100.0] * 500))


# --------------------------------------------------------------------------
# Émission de signaux
# --------------------------------------------------------------------------


def test_emet_des_signaux_sur_un_marche_realiste():
    signaux = collecter(ConfluenceRsiMacdEma(), marche_aleatoire())
    assert signaux, "aucun signal émis sur une marche aléatoire de 1500 bougies"


def test_les_signaux_respectent_le_ratio_demande():
    signaux = collecter(ConfluenceRsiMacdEma(ratio_objectif=2.0), marche_aleatoire())
    assert signaux
    for _, s in signaux:
        assert s.ratio == pytest.approx(2.0)


def test_le_ratio_est_configurable():
    signaux = collecter(ConfluenceRsiMacdEma(ratio_objectif=3.0), marche_aleatoire())
    assert signaux
    for _, s in signaux:
        assert s.ratio == pytest.approx(3.0)


def test_geometrie_des_signaux():
    for _, s in collecter(ConfluenceRsiMacdEma(), marche_aleatoire()):
        if s.sens is Sens.ACHAT:
            assert s.stop < s.entree < s.objectif
        else:
            assert s.objectif < s.entree < s.stop


# --------------------------------------------------------------------------
# Chaque filtre doit bloquer
# --------------------------------------------------------------------------


def test_le_filtre_rsi_bloque_effectivement():
    """Une fenêtre RSI impossible doit supprimer tout signal.

    Si le nombre de signaux ne changeait pas, c'est que le filtre ne serait pas
    réellement appliqué.
    """
    donnees = marche_aleatoire()
    assert collecter(ConfluenceRsiMacdEma(), donnees)
    assert not collecter(
        ConfluenceRsiMacdEma(rsi_plancher=99.0, rsi_plafond=99.5), donnees
    )


def test_chaque_signal_respecte_son_filtre_de_tendance():
    """Invariant : jamais d'achat sous l'EMA, jamais de vente au-dessus."""
    for bougie, s in collecter(ConfluenceRsiMacdEma(), marche_aleatoire()):
        if s.sens is Sens.ACHAT:
            assert bougie["close"] > bougie["ema"]
        else:
            assert bougie["close"] < bougie["ema"]


def test_chaque_signal_respecte_son_filtre_rsi():
    """Invariant : le RSI est bien dans la fenêtre exigée au moment du signal."""
    strategie = ConfluenceRsiMacdEma()
    for bougie, s in collecter(strategie, marche_aleatoire()):
        if s.sens is Sens.ACHAT:
            assert strategie.rsi_plancher < bougie["rsi"] < strategie.rsi_plafond
        else:
            assert 30.0 < bougie["rsi"] < 50.0


def test_chaque_signal_correspond_a_un_croisement_macd():
    """Invariant : le déclencheur est toujours présent."""
    for bougie, s in collecter(ConfluenceRsiMacdEma(), marche_aleatoire()):
        attendu = "croise_haut" if s.sens is Sens.ACHAT else "croise_bas"
        assert bool(bougie[attendu])


def test_aucun_achat_en_tendance_baissiere_marquee():
    signaux = collecter(ConfluenceRsiMacdEma(), marche_aleatoire(derive=-0.05))
    assert all(s.sens is Sens.VENTE for _, s in signaux)


# --------------------------------------------------------------------------
# B1v4 : seul l'objectif change
# --------------------------------------------------------------------------


def test_b1v4_vise_cinq_fois_le_risque_la_ou_b1v3_en_vise_trois():
    assert ConfluenceZeroSession().ratio_objectif == 3.0
    assert ConfluenceZeroSessionR5().ratio_objectif == 5.0


def test_b1v4_prend_exactement_les_memes_entrees_que_b1v3():
    """Invariant central : la seule différence est la distance de l'objectif.

    Sans cette garantie, comparer les deux résultats reviendrait à comparer deux
    stratégies distinctes, et l'écart observé ne serait plus attribuable au seul
    changement d'objectif. Ce test protège l'interprétation, pas seulement le code.
    """
    donnees = marche_aleatoire()
    v3 = collecter(ConfluenceZeroSession(), donnees)
    v4 = collecter(ConfluenceZeroSessionR5(), donnees)

    assert v3, "série de test sans aucun signal : le test ne prouverait rien"
    assert len(v3) == len(v4)

    for (bougie3, s3), (bougie4, s4) in zip(v3, v4, strict=True):
        assert bougie3.name == bougie4.name
        assert s3.sens is s4.sens
        assert s3.entree == s4.entree
        assert s3.stop == s4.stop
        assert s3.ratio == pytest.approx(3.0)
        assert s4.ratio == pytest.approx(5.0)


def test_b1v4_est_bien_enregistree_et_conserve_les_filtres():
    """Une variante absente du registre serait invisible des scripts et de l'app."""
    from marketlab.strategies.confluence import STRATEGIES

    assert STRATEGIES["B1v4"] is ConfluenceZeroSessionR5
    assert issubclass(ConfluenceZeroSessionR5, ConfluenceZeroSession)


# --------------------------------------------------------------------------
# B1v5 : retrait de la ligne zéro
# --------------------------------------------------------------------------


def test_b1v5_ne_porte_pas_la_regle_de_la_ligne_zero():
    """B1v5 retire une règle : elle ne doit pas hériter de celle qui la porte.

    Ce contrôle n'est pas cosmétique. La vérification des trades décide des
    contrôles à appliquer par héritage : si B1v5 héritait de B1v2, elle se verrait
    reprocher une condition qu'elle ne s'impose pas, et chaque trade serait
    déclaré non conforme.
    """
    assert not issubclass(ConfluenceSessionR5, ConfluenceZero)
    assert issubclass(ConfluenceSessionR5, FiltreSession)
    assert issubclass(ConfluenceZeroSessionR5, ConfluenceZero)


def test_b1v5_accepte_les_croisements_des_deux_cotes_de_zero():
    """L'inverse de B1v4, qui n'en retient qu'un côté."""
    donnees = marche_aleatoire()
    signaux = collecter(ConfluenceSessionR5(), donnees)
    assert signaux, "série de test sans signal : le test ne prouverait rien"

    cotes = {float(bougie["macd"]) < 0 for bougie, _ in signaux}
    assert cotes == {True, False}, "B1v5 devrait produire des signaux des deux côtés"


def test_tout_signal_de_b1v4_est_aussi_un_signal_de_b1v5():
    """Retirer une condition ne peut qu'ajouter des signaux, jamais en retirer.

    C'est l'invariant qui rend la comparaison interprétable : si B1v5 manquait un
    trade que B1v4 prend, l'écart de résultat ne serait plus attribuable au seul
    retrait de la règle.
    """
    donnees = marche_aleatoire()
    v4 = {bougie.name for bougie, _ in collecter(ConfluenceZeroSessionR5(), donnees)}
    v5 = {bougie.name for bougie, _ in collecter(ConfluenceSessionR5(), donnees)}

    assert v4, "série de test sans signal B1v4"
    assert v4 <= v5, f"{len(v4 - v5)} signaux de B1v4 absents de B1v5"
    assert len(v5) > len(v4), "B1v5 devrait produire strictement plus de signaux"


def test_b1v5_filtre_toujours_par_session():
    """Le retrait porte sur la ligne zéro, pas sur l'horaire."""
    donnees = marche_aleatoire()
    for bougie, _ in collecter(ConfluenceSessionR5(), donnees):
        assert bool(bougie["en_session"])


def test_b1v5_vise_cinq_fois_le_risque():
    assert ConfluenceSessionR5().ratio_objectif == 5.0
    assert ConfluenceSessionR5().sessions == ("londres", "new_york")


def test_le_filtre_de_session_agit_pareil_dans_les_deux_montages():
    """La brique de session doit se comporter identiquement où qu'elle soit posée.

    B1v3 la combine avec la ligne zéro, B1v5 sans. Si la colonne « en_session »
    différait entre les deux, les résultats ne seraient plus comparables.
    """
    donnees = marche_aleatoire()
    a = ConfluenceZeroSession().preparer(donnees)["en_session"]
    b = ConfluenceSessionR5().preparer(donnees)["en_session"]
    assert a.equals(b)
