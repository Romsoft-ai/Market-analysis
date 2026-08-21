"""Stratégies de confluence RSI + MACD + EMA.

Quatre versions coexistent volontairement dans ce fichier. Aucune ne remplace la
précédente : chacune ajoute UNE modification et une seule, et toutes sont
conservées pour que la comparaison reste possible et honnête. Écraser une version
rendrait invérifiable ce que chaque ajout a réellement changé.

Chaque version porte son STATUT, qui commande la façon de lire son résultat :

* **correction de fidélité** : la règle existait déjà dans la méthode appliquée à
  la main, ou la simulation exécutait des trades impossibles. On corrige une
  transcription, le résultat garde sa valeur de prédiction ;
* **exploration** : la question naît APRÈS lecture des résultats précédents. Le
  résultat vaut alors comme un essai parmi d'autres, pas comme une confirmation.

Principe commun : trois informations indépendantes doivent s'aligner.

* **EMA 200** dit dans quel sens on a le droit de travailler (filtre de tendance) ;
* **MACD** dit que le mouvement s'enclenche maintenant (déclencheur) ;
* **RSI** dit que la dynamique est saine, ni molle ni excessive (filtre de qualité).

--------------------------------------------------------------------------
B1, règles gelées le 19 août 2026
--------------------------------------------------------------------------

    ACHAT, les trois conditions vraies sur la même bougie clôturée :
        1. clôture > EMA 200
        2. le MACD croise sa ligne de signal vers le haut
        3. 50 < RSI < 70

    VENTE, symétrique :
        1. clôture < EMA 200
        2. le MACD croise sa ligne de signal vers le bas
        3. 30 < RSI < 50

Résultat mesuré sur GBPUSD M15 de 2022 à 2025 : 1 005 trades, moins 101 R.

--------------------------------------------------------------------------
B1v2, ajout daté du 20 août 2026
--------------------------------------------------------------------------

Une quatrième condition portant sur la POSITION du MACD au moment du croisement :

    ACHAT   : le croisement vers le haut se fait alors que le MACD est SOUS zéro
    VENTE   : le croisement vers le bas se fait alors que le MACD est AU-DESSUS

Raison du changement, à documenter dans le mémoire : cette règle faisait partie de
la méthode appliquée manuellement, mais avait été omise lors de la mise en mots.
Il ne s'agit donc PAS d'un ajustement destiné à améliorer un résultat décevant.

La distinction est essentielle. Modifier un seuil après avoir vu une courbe, c'est
fabriquer un résultat. Compléter une spécification incomplète, c'est corriger une
erreur de transcription. Pour que cette différence reste vérifiable, B1 n'est pas
modifiée : B1v2 est une stratégie distincte, et les deux résultats sont conservés.

Ce que la règle signifie. Un MACD sous zéro indique que la dynamique courte est
passée sous la dynamique moyenne, autrement dit que le marché a reculé. Croiser
vers le haut depuis cette zone marque la fin du recul. Combinée au filtre de
tendance, la règle revient donc à **acheter la reprise après un repli dans une
tendance haussière**, plutôt qu'un mouvement déjà engagé.

Effet mesuré avant implémentation : le filtre ne conserve que 33,5 % des signaux.

--------------------------------------------------------------------------
B1v3, ajout daté du 20 août 2026
--------------------------------------------------------------------------

B1v2, restreinte aux heures d'ouverture de Londres et de New York.

Raison : le backtest prenait des positions à deux heures du matin, moment où
l'opérateur dort et ne passerait aucun ordre. Il ne s'agit donc pas d'affiner une
courbe mais de rendre la simulation FIDÈLE à ce qui serait réellement exécutable.
Un backtest qui prend des trades impossibles ne mesure pas la stratégie étudiée.

--------------------------------------------------------------------------
B1v4, ajout daté du 20 août 2026
--------------------------------------------------------------------------

B1v3, dont l'objectif passe de 3 R à 5 R. Aucune condition d'entrée ne change :
les mêmes signaux donnent les mêmes entrées et les mêmes stops, seul le niveau
de sortie gagnante s'éloigne.

Statut : EXPLORATION, et non correction de fidélité. La question est posée APRÈS
avoir vu les résultats à 3 R, ce qui la distingue par nature des ajouts
précédents. Elle reste légitime, mais son résultat se lit comme celui d'un essai
parmi d'autres, pas comme une prédiction vérifiée.

Ce que le changement implique arithmétiquement. Le seuil de rentabilité tombe de
1/(1+3) = 25 % à 1/(1+5) = 16,7 % de réussite. En contrepartie l'objectif est
67 % plus loin, donc atteint moins souvent. Toute la question est de savoir
laquelle des deux forces l'emporte.

Repère utile pour lire le résultat : sur une marche au hasard sans dérive, la
probabilité d'atteindre 5 R avant 1 R vaut exactement 1/6, soit 16,7 %. Un taux
de réussite nettement supérieur signale un avantage réel ; un taux inférieur
signale que les frais et le comportement du marché jouent contre.

--------------------------------------------------------------------------
B1v5, ajout daté du 20 août 2026
--------------------------------------------------------------------------

B1v4 dont on RETIRE la condition de la ligne zéro. Un croisement du MACD est
accepté des deux côtés de zéro, les autres conditions restant inchangées :
tendance, fenêtre RSI, session de Londres ou de New York, objectif à 5 R.

C'est la première version qui retire une règle au lieu d'en ajouter une. Elle
n'est donc pas un maillon de plus dans la chaîne : elle se rattache directement à
B1, à laquelle elle ajoute le filtre de session et l'objectif éloigné.

Raison invoquée : sur des instruments qui se déplacent vite, comme le US30 et
l'or, le repli qui rendrait le MACD négatif n'a pas toujours lieu. Le mouvement
repart sans que le MACD repasse sous zéro, et le signal est refusé alors que les
trois autres conditions sont réunies. La règle ferait donc manquer des mouvements
valides plutôt que d'écarter des mouvements douteux.

Statut : EXPLORATION. L'observation vient de la lecture des backtests, pas d'une
règle oubliée ni d'une contrainte d'exécution. À la différence de B1v2 et B1v3,
son résultat ne vaut donc pas comme prédiction vérifiée.

À prévoir en lisant le résultat : retirer une condition ne peut qu'AUGMENTER le
nombre de signaux, jamais le diminuer. Tout signal de B1v4 est aussi un signal de
B1v5, et un test verrouille cet ordre d'inclusion. La question n'est pas de savoir
si B1v5 prend plus de trades, c'est certain, mais si les trades ajoutés valent
mieux que ceux que la règle écartait. C'est exactement la question posée sur les
positions simultanées, et la réponse y avait été négative.

--------------------------------------------------------------------------

Aucune de ces règles ne sera ajustée en fonction des résultats obtenus.
"""

from __future__ import annotations

import pandas as pd

from marketlab.data.temps import dans_sessions, serveur_vers_utc
from marketlab.strategies.base import Sens, Signal, Strategie, verifier_bougies
from marketlab.strategies.indicateurs import (
    croisement_baissier,
    croisement_haussier,
    ema,
    macd,
    plus_bas,
    plus_haut,
    rsi,
)

#: Colonnes d'indicateurs qui doivent être calculées avant toute décision.
_REQUISES = ["ema", "macd", "macd_signal", "rsi", "creux", "sommet"]


class ConfluenceRsiMacdEma(Strategie):
    """B1 : trois confirmations alignées."""

    nom = "B1 — RSI + MACD + EMA"
    code = "B1"

    def __init__(
        self,
        periode_ema: int = 200,
        macd_rapide: int = 12,
        macd_lente: int = 26,
        macd_signal: int = 9,
        periode_rsi: int = 14,
        rsi_plancher: float = 50.0,
        rsi_plafond: float = 70.0,
        bougies_stop: int = 10,
        ratio_objectif: float = 3.0,
    ) -> None:
        self.periode_ema = periode_ema
        self.macd_rapide = macd_rapide
        self.macd_lente = macd_lente
        self.macd_signal = macd_signal
        self.periode_rsi = periode_rsi
        self.rsi_plancher = rsi_plancher
        self.rsi_plafond = rsi_plafond
        self.bougies_stop = bougies_stop
        self.ratio_objectif = ratio_objectif

    @property
    def bougies_minimum(self) -> int:
        """Avant ce nombre de bougies, les indicateurs ne veulent rien dire.

        Le « plus un » vient des croisements : détecter un franchissement demande
        de connaître la bougie précédente.
        """
        return (
            max(
                self.periode_ema,
                self.macd_lente + self.macd_signal,
                self.periode_rsi,
                self.bougies_stop,
            )
            + 1
        )

    def preparer(self, bougies: pd.DataFrame) -> pd.DataFrame:
        """Calcule tous les indicateurs en une passe sur la série entière.

        Tout est vectorisé ici, y compris la détection des croisements, si bien que
        `evaluer` n'a plus qu'à lire la dernière ligne. Recalculer une EMA 200 à
        chaque bougie coûterait un temps quadratique.
        """
        verifier_bougies(bougies)
        donnees = bougies.copy()

        donnees["ema"] = ema(donnees["close"], self.periode_ema)

        lignes_macd = macd(
            donnees["close"], self.macd_rapide, self.macd_lente, self.macd_signal
        )
        donnees["macd"] = lignes_macd["macd"]
        donnees["macd_signal"] = lignes_macd["signal"]

        donnees["rsi"] = rsi(donnees["close"], self.periode_rsi)

        donnees["croise_haut"] = croisement_haussier(
            donnees["macd"], donnees["macd_signal"]
        )
        donnees["croise_bas"] = croisement_baissier(
            donnees["macd"], donnees["macd_signal"]
        )

        # Niveaux structurels servant de stop : un creux ou un sommet récent,
        # plutôt qu'une distance arbitraire. Le stop s'adapte ainsi à la
        # volatilité du moment.
        donnees["creux"] = plus_bas(donnees["low"], self.bougies_stop)
        donnees["sommet"] = plus_haut(donnees["high"], self.bougies_stop)

        return donnees

    # ------------------------------------------------------------------
    # Conditions, isolées pour que les variantes n'aient qu'elles à redéfinir
    # ------------------------------------------------------------------

    def conditions_achat(self, bougie: pd.Series) -> bool:
        """Toutes les conditions d'achat sont-elles réunies sur cette bougie ?"""
        return (
            float(bougie["close"]) > float(bougie["ema"])
            and bool(bougie["croise_haut"])
            and self.rsi_plancher < float(bougie["rsi"]) < self.rsi_plafond
        )

    def conditions_vente(self, bougie: pd.Series) -> bool:
        """Toutes les conditions de vente sont-elles réunies sur cette bougie ?"""
        return (
            float(bougie["close"]) < float(bougie["ema"])
            and bool(bougie["croise_bas"])
            and (100 - self.rsi_plafond) < float(bougie["rsi"]) < (100 - self.rsi_plancher)
        )

    # ------------------------------------------------------------------
    # Décision
    # ------------------------------------------------------------------

    def evaluer(self, historique: pd.DataFrame) -> Signal | None:
        """Décide sur la dernière bougie clôturée de `historique`.

        Le prix `entree` porté par le signal est la clôture de référence de la
        bougie de signal, pas le prix d'exécution : l'ordre sera rempli à
        l'ouverture de la bougie suivante. Le stop et l'objectif sont des niveaux
        absolus issus de la structure du marché, et ne bougent pas avec le prix de
        remplissage, exactement comme en trading réel.
        """
        if len(historique) < self.bougies_minimum:
            return None

        bougie = historique.iloc[-1]

        # Un indicateur non encore calculé rend toute décision impossible.
        if bougie[_REQUISES].isna().any():
            return None

        cloture = float(bougie["close"])
        valeur_rsi = float(bougie["rsi"])

        if self.conditions_achat(bougie):
            return self._construire(Sens.ACHAT, cloture, float(bougie["creux"]), valeur_rsi)

        if self.conditions_vente(bougie):
            return self._construire(Sens.VENTE, cloture, float(bougie["sommet"]), valeur_rsi)

        return None

    def _construire(
        self, sens: Sens, entree: float, stop: float, valeur_rsi: float
    ) -> Signal | None:
        """Assemble le signal, ou renonce si la géométrie est dégénérée.

        Cas réel à écarter : la clôture coïncide avec le creux des dix dernières
        bougies. La distance au stop est alors nulle, et la taille de position
        calculée par la couche de risque exploserait.
        """
        risque = abs(entree - stop)
        if risque <= 0:
            return None

        if sens is Sens.ACHAT:
            objectif = entree + self.ratio_objectif * risque
        else:
            objectif = entree - self.ratio_objectif * risque

        return Signal(
            sens=sens,
            entree=entree,
            stop=stop,
            objectif=objectif,
            raison=self._raison(valeur_rsi),
        )

    def _raison(self, valeur_rsi: float) -> str:
        return f"EMA{self.periode_ema} + croisement MACD + RSI {valeur_rsi:.1f}"


class ConfluenceZero(ConfluenceRsiMacdEma):
    """B1v2 : B1, plus la position du MACD par rapport à zéro au croisement.

    Seules les conditions changent. Les indicateurs, le stop, l'objectif et la
    construction du signal sont hérités tels quels, ce qui garantit que la seule
    différence mesurée entre les deux stratégies est bien la règle ajoutée.
    """

    nom = "B1v2 — RSI + MACD + EMA + ligne zéro"
    code = "B1v2"

    def conditions_achat(self, bougie: pd.Series) -> bool:
        # Le croisement doit se produire alors que le MACD est encore SOUS zéro :
        # on achète la fin d'un repli, pas un mouvement déjà lancé.
        return super().conditions_achat(bougie) and float(bougie["macd"]) < 0

    def conditions_vente(self, bougie: pd.Series) -> bool:
        # Symétrique : le croisement baissier doit se produire AU-DESSUS de zéro.
        return super().conditions_vente(bougie) and float(bougie["macd"]) > 0

    def _raison(self, valeur_rsi: float) -> str:
        return f"{super()._raison(valeur_rsi)} + croisement du bon côté de zéro"


class FiltreSession:
    """Brique réutilisable : restreint une stratégie aux sessions ouvertes.

    Pourquoi une brique séparée plutôt qu'une classe de plus dans la chaîne.
    B1v3 combine le filtre horaire avec la règle de la ligne zéro, mais B1v5
    combine ce même filtre horaire SANS elle. Une hiérarchie linéaire ne peut pas
    exprimer les deux : il faudrait recopier le filtre, et deux copies finissent
    toujours par diverger.

    Les sessions sont évaluées en heure LOCALE de chaque place, après conversion
    des horodatages serveur en UTC réel. Un filtre appliqué directement à l'heure
    serveur serait décalé d'une heure la moitié de l'année.

    Cette brique n'est pas une stratégie : elle se combine toujours à l'une
    d'elles, et délègue à `super()` tout ce qui ne concerne pas l'horaire.
    """

    #: Sessions autorisées. Modifiables à la construction pour tester d'autres
    #: fenêtres sans toucher au code.
    sessions_par_defaut = ("londres", "new_york")

    def __init__(self, *args, sessions: tuple[str, ...] | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.sessions = tuple(sessions or self.sessions_par_defaut)

    def preparer(self, bougies: pd.DataFrame) -> pd.DataFrame:
        """Ajoute la colonne d'appartenance à une session ouverte.

        Le calcul est fait une fois pour toute la série, comme les indicateurs :
        `evaluer` n'a plus qu'à lire un booléen.
        """
        donnees = super().preparer(bougies)
        utc = serveur_vers_utc(donnees.index)
        donnees["en_session"] = dans_sessions(utc, list(self.sessions)).to_numpy()
        return donnees

    def conditions_achat(self, bougie: pd.Series) -> bool:
        return bool(bougie.get("en_session", False)) and super().conditions_achat(bougie)

    def conditions_vente(self, bougie: pd.Series) -> bool:
        return bool(bougie.get("en_session", False)) and super().conditions_vente(bougie)

    def _raison(self, valeur_rsi: float) -> str:
        return f"{super()._raison(valeur_rsi)} + session {' ou '.join(self.sessions)}"


class ConfluenceZeroSession(FiltreSession, ConfluenceZero):
    """B1v3 : B1v2, restreinte aux sessions de Londres et de New York.

    Ajout du 20 août 2026. Ce n'est PAS un ajustement destiné à améliorer un
    résultat : c'est une correction de FIDÉLITÉ. Le backtest prenait des positions
    à deux heures du matin, moment où l'opérateur dort et ne passerait aucun ordre.
    Un test qui exécute des trades impossibles ne mesure pas la stratégie étudiée,
    mais celle d'un automate sans contrainte humaine.
    """

    nom = "B1v3 — B1v2 restreinte aux sessions Londres et New York"
    code = "B1v3"


class ConfluenceZeroSessionR5(ConfluenceZeroSession):
    """B1v4 : B1v3 dont l'objectif passe de 3 R à 5 R.

    Rien d'autre ne change. Entrées, stops et filtres sont hérités sans
    modification, si bien que la seule différence mesurable entre B1v3 et B1v4
    est la distance de l'objectif. C'est ce qui rend la comparaison lisible.

    Contrairement à B1v2 et B1v3, cette variante est une EXPLORATION : elle naît
    d'une question posée après lecture des résultats, pas d'une règle oubliée.
    """

    nom = "B1v4 — B1v3 avec objectif à 5 R"
    code = "B1v4"

    def __init__(self, *args, ratio_objectif: float = 5.0, **kwargs) -> None:
        super().__init__(*args, ratio_objectif=ratio_objectif, **kwargs)


class ConfluenceSessionR5(FiltreSession, ConfluenceRsiMacdEma):
    """B1v5 : B1v4 SANS la condition de la ligne zéro.

    Les trois conditions d'origine, le filtre de session et l'objectif à 5 R,
    mais le croisement du MACD est accepté des DEUX côtés de zéro.

    Ce que ça change en pratique. B1v2 n'achetait que la reprise après un repli,
    donc elle attendait que le MACD soit repassé sous zéro avant de valider un
    croisement haussier. Sur un instrument qui se déplace vite, ce recul n'a pas
    toujours lieu : le mouvement repart sans jamais rendre le MACD négatif, et le
    signal est refusé alors que les trois autres conditions sont réunies.

    Noter que B1v5 n'est PAS un maillon de plus dans la chaîne : elle retire ce
    que B1v2 avait ajouté. C'est pourquoi elle hérite directement de B1 et non de
    B1v2, et pourquoi le filtre de session a dû devenir une brique à part.
    """

    nom = "B1v5 — B1 + sessions + objectif 5 R, sans la ligne zéro"
    code = "B1v5"

    def __init__(self, *args, ratio_objectif: float = 5.0, **kwargs) -> None:
        super().__init__(*args, ratio_objectif=ratio_objectif, **kwargs)


#: Stratégies disponibles, par code, pour les scripts et l'interface.
STRATEGIES = {
    ConfluenceRsiMacdEma.code: ConfluenceRsiMacdEma,
    ConfluenceZero.code: ConfluenceZero,
    ConfluenceZeroSession.code: ConfluenceZeroSession,
    ConfluenceZeroSessionR5.code: ConfluenceZeroSessionR5,
    ConfluenceSessionR5.code: ConfluenceSessionR5,
}
