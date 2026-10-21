"""Les indicateurs techniques du projet, calculés en pandas.

Pourquoi les écrire nous-mêmes plutôt qu'installer une bibliothèque :

* ce sont **des formules de quelques lignes** — la dépendance coûterait plus
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


def atr(bougies: pd.DataFrame, periode: int = 14) -> pd.Series:
    """ATR (Average True Range) : l'amplitude moyenne d'une bougie, écarts de nuit compris.

    Le « vrai range » d'une bougie est le plus grand de trois écarts : haut moins
    bas, et distance de chacun d'eux à la clôture précédente. Ce dernier terme
    capte les écarts d'ouverture qu'un simple haut moins bas ignorerait.

    Lissage de Wilder, comme le RSI et pour la même raison : c'est le calcul des
    plateformes de trading. Les `periode - 1` premières valeurs sont absentes.
    """
    if periode < 1:
        raise ValueError(f"La période doit être positive, reçu {periode}")
    cloture_prec = bougies["close"].shift(1)
    vrai_range = pd.concat(
        [
            bougies["high"] - bougies["low"],
            (bougies["high"] - cloture_prec).abs(),
            (bougies["low"] - cloture_prec).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return vrai_range.ewm(alpha=1 / periode, adjust=False, min_periods=periode).mean()


def supertrend(bougies: pd.DataFrame, periode: int = 10, multiplicateur: float = 3.0) -> pd.DataFrame:
    """SuperTrend : le sens de la tendance, et un stop qui suit la volatilité.

    Deux bandes encadrent le milieu de la bougie à `multiplicateur` ATR. En
    tendance haussière, la ligne est la bande BASSE, qui ne peut que monter ; la
    tendance s'inverse quand une clôture passe sous elle. Symétrique en baisse.

    Le calcul est RÉCURSIF : chaque bande dépend de sa valeur à la bougie
    précédente (une bande basse ne redescend pas tant que la tendance tient). Il
    ne se vectorise pas, d'où la boucle explicite. Chaque valeur ne dépend que du
    passé : aucune anticipation possible.

    Retourne deux colonnes :

    * ``supertrend`` : le niveau de la ligne (bande basse en hausse, haute en baisse) ;
    * ``tendance``   : +1 en tendance haussière, -1 en baissière.
    """
    hauts = bougies["high"].to_numpy(dtype="float64")
    bas = bougies["low"].to_numpy(dtype="float64")
    clotures = bougies["close"].to_numpy(dtype="float64")
    amplitude = atr(bougies, periode).to_numpy()

    milieu = (hauts + bas) / 2
    haute_brute = milieu + multiplicateur * amplitude
    basse_brute = milieu - multiplicateur * amplitude

    n = len(bougies)
    haute = np.full(n, np.nan)
    basse = np.full(n, np.nan)
    tendance = np.full(n, np.nan)
    ligne = np.full(n, np.nan)

    for i in range(n):
        if np.isnan(amplitude[i]):
            continue
        if i == 0 or np.isnan(tendance[i - 1]):
            # Première valeur calculable : on part en tendance haussière, la
            # première inversion corrigera si besoin.
            haute[i], basse[i], tendance[i] = haute_brute[i], basse_brute[i], 1.0
        else:
            # Une bande ne se desserre pas tant que la clôture précédente ne l'a
            # pas franchie : c'est ce qui en fait un stop suiveur.
            haute[i] = (
                haute_brute[i]
                if haute_brute[i] < haute[i - 1] or clotures[i - 1] > haute[i - 1]
                else haute[i - 1]
            )
            basse[i] = (
                basse_brute[i]
                if basse_brute[i] > basse[i - 1] or clotures[i - 1] < basse[i - 1]
                else basse[i - 1]
            )
            if tendance[i - 1] > 0:
                tendance[i] = -1.0 if clotures[i] < basse[i] else 1.0
            else:
                tendance[i] = 1.0 if clotures[i] > haute[i] else -1.0
        ligne[i] = basse[i] if tendance[i] > 0 else haute[i]

    return pd.DataFrame({"supertrend": ligne, "tendance": tendance}, index=bougies.index)


def bollinger(serie: pd.Series, periode: int = 20, ecarts_types: float = 2.0) -> pd.DataFrame:
    """Bandes de Bollinger : une moyenne mobile et deux limites de volatilité.

    Les bandes sont à `ecarts_types` écarts-types de la moyenne simple. L'écart-type
    est celui de la POPULATION (ddof=0), comme dans la définition de Bollinger et
    sur les plateformes de trading ; pandas utilise par défaut l'échantillon, ce
    qui élargirait légèrement les bandes.

    Retourne ``bb_mediane``, ``bb_haute`` et ``bb_basse``.
    """
    if periode < 2:
        raise ValueError(f"La période doit valoir au moins 2, reçu {periode}")
    mediane = serie.rolling(periode, min_periods=periode).mean()
    ecart = serie.rolling(periode, min_periods=periode).std(ddof=0)
    return pd.DataFrame(
        {
            "bb_mediane": mediane,
            "bb_haute": mediane + ecarts_types * ecart,
            "bb_basse": mediane - ecarts_types * ecart,
        },
        index=serie.index,
    )
