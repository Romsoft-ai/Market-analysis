"""Les indicateurs techniques du projet, calculés en pandas.

Pourquoi les écrire nous-mêmes plutôt qu'installer une bibliothèque :

* ce sont **trois formules de quelques lignes** — la dépendance coûterait plus
  que le code ;
* la bibliothèque de référence du domaine, TA-Lib, repose sur du C et s'installe
  très mal sous Windows ;
* surtout : **on saura exactement ce qui est calculé.** Deux bibliothèques donnent
  des RSI légèrement différents selon la méthode de lissage. Quand un backtest
  donnera un résultat surprenant, il faudra pouvoir exclure l'indicateur.

Chaque fonction retourne une série alignée sur l'index d'entrée, avec des valeurs
manquantes (NaN) au début — le temps que l'indicateur ait assez d'historique.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def ema(serie: pd.Series, periode: int) -> pd.Series:
    """Moyenne mobile exponentielle.

    Contrairement à une moyenne simple, elle donne plus de poids aux prix récents :
    elle réagit plus vite à un changement de tendance.

    `adjust=False` applique la formule récursive classique du domaine
    (``valeur = alpha * prix + (1 - alpha) * valeur_precedente``), qui est celle
    utilisée par les plateformes de trading. `adjust=True`, le défaut de pandas,
    donnerait des valeurs différentes en début de série.
    """
    if periode < 1:
        raise ValueError(f"La période doit être positive, reçu {periode}")
    return serie.ewm(span=periode, adjust=False).mean()


def macd(
    serie: pd.Series,
    rapide: int = 12,
    lente: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """MACD — mesure du momentum par écart entre deux moyennes.

    Trois séries en sortie :

    * ``macd``      : EMA rapide moins EMA lente. Positif = la dynamique récente
                      est plus forte que la dynamique de fond.
    * ``signal``    : EMA du MACD. Sert de référence de comparaison.
    * ``histogramme``: macd moins signal. Change de signe au croisement.

    C'est le **croisement** du MACD au-dessus de sa ligne de signal qui sert de
    déclencheur, pas la valeur absolue.
    """
    if rapide >= lente:
        raise ValueError(
            f"La période rapide ({rapide}) doit être inférieure à la lente ({lente})"
        )

    ligne = ema(serie, rapide) - ema(serie, lente)
    ligne_signal = ema(ligne, signal)
    return pd.DataFrame(
        {
            "macd": ligne,
            "signal": ligne_signal,
            "histogramme": ligne - ligne_signal,
        },
        index=serie.index,
    )


def rsi(serie: pd.Series, periode: int = 14) -> pd.Series:
    """RSI — indice de force relative, borné entre 0 et 100.

    Principe : sur les `periode` dernières bougies, on compare l'ampleur moyenne
    des hausses à celle des baisses. 100 signifie « que des hausses », 0 « que des
    baisses ». Par convention, sous 30 le marché est dit survendu, au-dessus de 70
    suracheté.

    Le lissage utilisé est celui de **Wilder**, l'auteur de l'indicateur : une
    moyenne exponentielle de coefficient ``1 / periode``. C'est ce que font les
    plateformes de trading. Une moyenne simple donnerait un RSI différent — d'où
    l'intérêt de maîtriser ce calcul plutôt que de le déléguer.
    """
    if periode < 1:
        raise ValueError(f"La période doit être positive, reçu {periode}")

    variation = serie.diff()
    hausses = variation.clip(lower=0)
    baisses = -variation.clip(upper=0)

    moyenne_hausses = hausses.ewm(alpha=1 / periode, adjust=False).mean()
    moyenne_baisses = baisses.ewm(alpha=1 / periode, adjust=False).mean()

    # Aucune baisse sur la période : la force relative est infinie, donc RSI = 100.
    # On évite la division par zéro plutôt que de laisser passer un NaN silencieux.
    force = np.where(
        moyenne_baisses > 0,
        moyenne_hausses / moyenne_baisses.replace(0, np.nan),
        np.inf,
    )
    valeurs = 100 - (100 / (1 + force))

    resultat = pd.Series(valeurs, index=serie.index, dtype="float64")
    # La première variation est indéterminée : pas de bougie précédente.
    resultat.iloc[0] = np.nan
    return resultat


def plus_bas(serie: pd.Series, bougies: int) -> pd.Series:
    """Plus bas atteint sur les `bougies` dernières valeurs, incluse la courante.

    Sert à placer un stop sous un creux récent plutôt qu'à une distance arbitraire :
    le stop s'adapte ainsi à la volatilité du moment.
    """
    return serie.rolling(window=bougies, min_periods=bougies).min()


def plus_haut(serie: pd.Series, bougies: int) -> pd.Series:
    """Plus haut atteint sur les `bougies` dernières valeurs, incluse la courante."""
    return serie.rolling(window=bougies, min_periods=bougies).max()


def croisement_haussier(serie: pd.Series, reference: pd.Series) -> pd.Series:
    """Vrai à la bougie où `serie` passe au-dessus de `reference`.

    Un croisement est un ÉVÉNEMENT, pas un état : il faut donc regarder la bougie
    précédente. Se contenter de « serie > reference » donnerait un signal vrai
    pendant tout le temps où la condition dure, et non au moment du basculement.
    """
    precedent = serie.shift(1) <= reference.shift(1)
    return precedent & (serie > reference)


def croisement_baissier(serie: pd.Series, reference: pd.Series) -> pd.Series:
    """Vrai à la bougie où `serie` passe en dessous de `reference`."""
    precedent = serie.shift(1) >= reference.shift(1)
    return precedent & (serie < reference)
