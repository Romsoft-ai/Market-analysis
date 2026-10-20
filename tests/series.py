"""Séries de bougies synthétiques, partagées par les tests de stratégies.

Note de méthode. Une première version des tests utilisait des séries parfaitement
linéaires. Erreur : sans le moindre repli, le RSI n'a aucune baisse à comparer et
sature à 100 ; il ne traverse jamais la zone que la stratégie exige, et aucun
signal ne sortait. Les séries ci-dessous sont donc des marches aléatoires avec
dérive, bruitées comme un vrai prix, mais à graine fixe, donc reproductibles.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from marketlab.strategies.base import Signal, Strategie


def bougies(closes: list[float], debut: str = "2024-01-01") -> pd.DataFrame:
    """Série de bougies M15 minimale : hauts et bas serrés autour de la clôture."""
    index = pd.date_range(debut, periods=len(closes), freq="15min", tz="UTC")
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
    n: int = 4000, derive: float = 0.03, bruit: float = 0.4, graine: int = 7
) -> pd.DataFrame:
    """Prix bruité avec une dérive : le profil d'un vrai marché.

    `derive` positive = tendance haussière de fond, `bruit` = amplitude des
    oscillations. Quatre mille bougies M15 couvrent six semaines, assez pour que
    les filtres de session laissent passer des signaux.
    """
    generateur = np.random.default_rng(graine)
    variations = generateur.normal(derive, bruit, n)
    return bougies(list(100 + np.cumsum(variations)))


def collecter(strategie: Strategie, donnees: pd.DataFrame) -> list[tuple[pd.Series, Signal]]:
    """Retourne les couples (bougie de signal, signal) émis sur toute la série."""
    prepare = strategie.preparer(donnees)
    resultats = []
    for i in range(strategie.bougies_minimum, len(prepare)):
        signal = strategie.evaluer(prepare.iloc[: i + 1])
        if signal is not None:
            resultats.append((prepare.iloc[i], signal))
    return resultats
