"""B1 : confluence RSI + MACD + EMA, restreinte aux sessions de Londres et New York.

Trois informations indépendantes doivent s'aligner :

* **EMA 200** dit dans quel sens on a le droit de travailler (filtre de tendance) ;
* **MACD** dit que le mouvement s'enclenche maintenant (déclencheur) ;
* **RSI** dit que la dynamique est saine, ni molle ni excessive (filtre de qualité).

--------------------------------------------------------------------------
Règles, figées le 20 octobre 2026
--------------------------------------------------------------------------

    ACHAT, toutes les conditions vraies sur la même bougie clôturée :
        1. clôture > EMA 200
        2. le MACD croise sa ligne de signal vers le haut
        3. 50 < RSI < 70
        4. le croisement se fait alors que le MACD est SOUS zéro
        5. la bougie est dans la session de Londres ou de New York

    VENTE, symétrique : clôture < EMA 200, croisement vers le bas, 30 < RSI < 50,
    MACD AU-DESSUS de zéro, même filtre horaire.

    Stop : le plus bas (achat) ou le plus haut (vente) des 10 dernières bougies.
    Objectif : 3 fois le risque.

--------------------------------------------------------------------------
D'où viennent ces règles
--------------------------------------------------------------------------

Cette version s'appelait B1v3 pendant l'étape 1. Elle a été construite en deux
CORRECTIONS DE FIDÉLITÉ à partir de la version à trois conditions, et non en
ajustant des seuils après lecture des résultats :

* la ligne zéro (ajout du 20 août 2026) faisait partie de la méthode appliquée à
  la main, mais avait été omise lors de la mise en mots. Combinée au filtre de
  tendance, elle revient à acheter la REPRISE après un repli, plutôt qu'un
  mouvement déjà lancé ;
* le filtre de session (même jour) corrige une simulation qui prenait des
  positions à deux heures du matin, impossibles à exécuter pour l'opérateur.

Deux EXPLORATIONS ont été menées ensuite puis écartées : B1v4 (objectif à 5 R) et
B1v5 (5 R sans la ligne zéro). Leurs résultats restent dans le journal
d'expériences, et leur code dans l'historique git.

Aucune de ces règles ne sera ajustée en fonction des résultats obtenus. Pour
essayer un autre réglage, on passe des paramètres différents :
``RsiMacdEma(Parametres(ratio_objectif=5.0))``, et le journal l'enregistre.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from marketlab.strategies.base import Controle, Sens, Signal, Strategie, verifier_bougies
from marketlab.strategies.briques import colonne_session, signal_a_ratio
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


@dataclass(frozen=True)
class Parametres:
    """Tous les réglages de B1, et rien qu'ici. Les valeurs par défaut font foi."""

    periode_ema: int = 200
    macd_rapide: int = 12
    macd_lente: int = 26
    macd_signal: int = 9
    periode_rsi: int = 14
    #: Fenêtre RSI d'un achat ; celle d'une vente en est le miroir (30-50).
    rsi_plancher: float = 50.0
    rsi_plafond: float = 70.0
    #: Le stop se pose sur l'extrême de ce nombre de bougies.
    bougies_stop: int = 10
    ratio_objectif: float = 3.0
    sessions: tuple[str, ...] = ("londres", "new_york")


class RsiMacdEma(Strategie):
    """B1 : cinq conditions alignées sur la bougie clôturée."""

    code = "B1"
    nom = "B1 : RSI + MACD + EMA"
    Parametres = Parametres
    # Nom de classe de cette stratégie quand elle s'appelait B1v3, pour que les
    # expériences d'août restent rejouables dans l'inspecteur.
    anciennes_classes = ("ConfluenceZeroSession",)

    parametres: Parametres

    @property
    def bougies_minimum(self) -> int:
        """Avant ce nombre de bougies, les indicateurs ne veulent rien dire.

        Le « plus un » vient des croisements : détecter un franchissement demande
        de connaître la bougie précédente.
        """
        p = self.parametres
        return max(p.periode_ema, p.macd_lente + p.macd_signal, p.periode_rsi, p.bougies_stop) + 1

    def preparer(self, bougies: pd.DataFrame) -> pd.DataFrame:
        """Calcule tous les indicateurs en une passe sur la série entière.

        Tout est vectorisé ici, y compris les croisements et l'appartenance aux
        sessions, si bien que `evaluer` n'a plus qu'à lire la dernière ligne.
        """
        verifier_bougies(bougies)
        p = self.parametres
        donnees = bougies.copy()

        donnees["ema"] = ema(donnees["close"], p.periode_ema)

        lignes_macd = macd(donnees["close"], p.macd_rapide, p.macd_lente, p.macd_signal)
        donnees["macd"] = lignes_macd["macd"]
        donnees["macd_signal"] = lignes_macd["signal"]

        donnees["rsi"] = rsi(donnees["close"], p.periode_rsi)

        donnees["croise_haut"] = croisement_haussier(donnees["macd"], donnees["macd_signal"])
        donnees["croise_bas"] = croisement_baissier(donnees["macd"], donnees["macd_signal"])

        # Niveaux structurels servant de stop : un creux ou un sommet récent,
        # plutôt qu'une distance arbitraire. Le stop s'adapte ainsi à la
        # volatilité du moment.
        donnees["creux"] = plus_bas(donnees["low"], p.bougies_stop)
        donnees["sommet"] = plus_haut(donnees["high"], p.bougies_stop)

        donnees["en_session"] = colonne_session(donnees.index, p.sessions)
        return donnees

    # ------------------------------------------------------------------
    # Conditions
    # ------------------------------------------------------------------

    def conditions_achat(self, bougie: pd.Series) -> bool:
        p = self.parametres
        return (
            bool(bougie["en_session"])
            and float(bougie["close"]) > float(bougie["ema"])
            and bool(bougie["croise_haut"])
            and p.rsi_plancher < float(bougie["rsi"]) < p.rsi_plafond
            and float(bougie["macd"]) < 0
        )

    def conditions_vente(self, bougie: pd.Series) -> bool:
        p = self.parametres
        return (
            bool(bougie["en_session"])
            and float(bougie["close"]) < float(bougie["ema"])
            and bool(bougie["croise_bas"])
            and (100 - p.rsi_plafond) < float(bougie["rsi"]) < (100 - p.rsi_plancher)
            and float(bougie["macd"]) > 0
        )

    # ------------------------------------------------------------------
    # Décision
    # ------------------------------------------------------------------

    def evaluer(self, historique: pd.DataFrame) -> Signal | None:
        """Décide sur la dernière bougie clôturée de `historique`.

        Le prix `entree` porté par le signal est la clôture de la bougie de
        signal, pas le prix d'exécution : l'ordre sera rempli à l'ouverture de la
        bougie suivante. Le stop et l'objectif sont des niveaux absolus issus de
        la structure du marché, et ne bougent pas avec le prix de remplissage.
        """
        if len(historique) < self.bougies_minimum:
            return None

        bougie = historique.iloc[-1]

        # Un indicateur non encore calculé rend toute décision impossible.
        if bougie[_REQUISES].isna().any():
            return None

        cloture = float(bougie["close"])
        p = self.parametres

        if self.conditions_achat(bougie):
            return signal_a_ratio(
                Sens.ACHAT, cloture, float(bougie["creux"]), p.ratio_objectif,
                self._raison(float(bougie["rsi"])),
            )
        if self.conditions_vente(bougie):
            return signal_a_ratio(
                Sens.VENTE, cloture, float(bougie["sommet"]), p.ratio_objectif,
                self._raison(float(bougie["rsi"])),
            )
        return None

    def _raison(self, valeur_rsi: float) -> str:
        p = self.parametres
        return (
            f"EMA{p.periode_ema} + croisement MACD + RSI {valeur_rsi:.1f}"
            f" + croisement du bon côté de zéro + session {' ou '.join(p.sessions)}"
        )

    # ------------------------------------------------------------------
    # Vérification
    # ------------------------------------------------------------------

    def controles(self, bougie: pd.Series, trade: pd.Series, decimales: int) -> list[Controle]:
        """Rejoue les cinq conditions et le placement du stop sur la bougie de signal."""
        p = self.parametres
        achat = trade["sens"] == "achat"
        d = decimales

        plancher, plafond = p.rsi_plancher, p.rsi_plafond
        if not achat:
            # La fenêtre RSI d'une vente est le miroir de celle d'un achat.
            plancher, plafond = 100 - plafond, 100 - plancher

        cloture = float(bougie["close"])
        valeur_ema = float(bougie["ema"])
        valeur_rsi = float(bougie["rsi"])
        valeur_macd = float(bougie["macd"])
        niveau_stop = float(bougie["creux"] if achat else bougie["sommet"])
        stop_trade = float(trade["stop_initial"])

        return [
            Controle(
                cle="tendance",
                condition="Tendance : clôture du bon côté de l'EMA",
                attendu="clôture > EMA" if achat else "clôture < EMA",
                constate=f"{cloture:.{d}f} vs {valeur_ema:.{d}f}",
                valide=(cloture > valeur_ema) if achat else (cloture < valeur_ema),
            ),
            Controle(
                cle="croisement",
                condition="Déclencheur : croisement du MACD",
                attendu="vers le haut" if achat else "vers le bas",
                constate=f"MACD {valeur_macd:.6f} / signal {float(bougie['macd_signal']):.6f}",
                valide=bool(bougie["croise_haut"] if achat else bougie["croise_bas"]),
            ),
            Controle(
                cle="rsi",
                condition="Momentum : RSI dans la fenêtre",
                attendu=f"{plancher:.0f} < RSI < {plafond:.0f}",
                constate=f"{valeur_rsi:.1f}",
                valide=plancher < valeur_rsi < plafond,
            ),
            Controle(
                cle="ligne_zero",
                condition="Position : croisement du bon côté de zéro",
                attendu="MACD < 0" if achat else "MACD > 0",
                constate=f"{valeur_macd:+.6f}",
                valide=(valeur_macd < 0) if achat else (valeur_macd > 0),
            ),
            Controle(
                cle="session",
                condition="Horaire : session de marché ouverte",
                attendu=" ou ".join(p.sessions),
                constate="dans la session" if bool(bougie["en_session"]) else "hors session",
                valide=bool(bougie["en_session"]),
            ),
            Controle(
                cle="stop",
                condition=f"Stop : extrême des {p.bougies_stop} dernières bougies",
                attendu=f"{niveau_stop:.{d}f}",
                constate=f"{stop_trade:.{d}f}",
                valide=abs(niveau_stop - stop_trade) < 1e-9,
            ),
        ]
