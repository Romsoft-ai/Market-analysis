"""B2 : retour à la moyenne, Bandes de Bollinger + MACD.

Les bandes disent OÙ le prix est anormalement éloigné de sa moyenne ; le MACD dit
QUAND il commence à revenir. C'est la seule baseline qui va CONTRE le mouvement
récent : B1 et B3 suivent la tendance. Les comparer dit donc quelque chose du
comportement de chaque marché, et pas seulement de chaque stratégie.

--------------------------------------------------------------------------
Règles, figées le 20 octobre 2026
--------------------------------------------------------------------------

    ACHAT, toutes les conditions vraies sur la bougie clôturée :
        1. le bas a touché ou percé la bande basse (20, 2σ) dans les 5 dernières
           bougies, celle-ci comprise
        2. le MACD (12, 26, 9) croise sa ligne de signal vers le haut
        3. la clôture est encore SOUS la moyenne : le retour n'est pas entamé
        4. le gain jusqu'à la bande opposée vaut au moins 1 fois le risque
        5. la bougie est dans la session de Londres ou de New York

    VENTE, symétrique : contact avec la bande haute, croisement vers le bas,
    clôture au-dessus de la moyenne.

    Stop : le plus bas (achat) ou le plus haut (vente) des 10 dernières bougies.
    Objectif : la bande OPPOSÉE au moment du signal (bande haute pour un achat).

--------------------------------------------------------------------------
Pourquoi la bande opposée et non la moyenne (décision du 20 octobre 2026)
--------------------------------------------------------------------------

Le plan prévoyait la moyenne comme objectif. Mesure faite AVANT tout backtest
de résultats, sur 2022-2025 en M15 chez IC Markets : au moment du croisement du
MACD, le prix a déjà fait l'essentiel du retour. Le gain jusqu'à la moyenne vaut
0,2 R en médiane, et 4 à 7 % des signaux seulement atteignent 1 R, soit environ
25 trades par instrument en quatre ans : trop peu pour conclure quoi que ce soit.
Vers la bande opposée, le gain médian passe à 1,2 R et 66 à 72 % des signaux
dépassent 1 R.

La décision repose sur la GÉOMÉTRIE des signaux (distances entrée, stop,
objectif), pas sur leurs gains ou leurs pertes, qui n'avaient pas été mesurés.
Ce n'est donc pas une règle ajustée pour améliorer un résultat, mais une règle
corrigée parce qu'elle ne produisait presque aucun trade.

--------------------------------------------------------------------------
Trois choix, validés avant tout backtest
--------------------------------------------------------------------------

* **Contact dans les 5 dernières bougies**, et non sur la bougie du croisement.
  Le prix touche la bande au plus fort de l'excès, et le MACD ne croise que
  quelques bougies plus tard, quand le retour s'amorce. Exiger les deux sur la
  même bougie ne laisserait passer presque aucun signal.
* **Un gain minimal d'1 R.** Risquer 1 pour gagner 0,3 est perdant d'avance une
  fois le spread payé : on renonce plutôt que de prendre le trade.
* **Le même filtre de session que B1**, pour que la comparaison des baselines
  porte sur les règles et non sur les heures de marché autorisées.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from marketlab.strategies.base import Controle, Sens, Signal, Strategie, verifier_bougies
from marketlab.strategies.briques import colonne_session
from marketlab.strategies.indicateurs import (
    bollinger,
    croisement_baissier,
    croisement_haussier,
    macd,
    plus_bas,
    plus_haut,
)

#: Colonnes d'indicateurs qui doivent être calculées avant toute décision.
_REQUISES = ["bb_mediane", "bb_haute", "bb_basse", "macd", "macd_signal", "creux", "sommet"]


@dataclass(frozen=True)
class Parametres:
    """Tous les réglages de B2, et rien qu'ici. Les valeurs par défaut font foi."""

    periode_bollinger: int = 20
    ecarts_types: float = 2.0
    #: Fenêtre, en bougies, dans laquelle le contact avec la bande doit avoir eu lieu.
    bougies_contact: int = 5
    macd_rapide: int = 12
    macd_lente: int = 26
    macd_signal: int = 9
    bougies_stop: int = 10
    #: En dessous de ce rapport gain/risque jusqu'à la bande opposée, le signal est écarté.
    ratio_minimum: float = 1.0
    sessions: tuple[str, ...] = ("londres", "new_york")


class BollingerMacd(Strategie):
    """B2 : acheter l'excès baissier qui se résorbe, vendre l'excès haussier."""

    code = "B2"
    nom = "B2 : Bollinger + MACD (retour à la moyenne)"
    Parametres = Parametres

    parametres: Parametres

    @property
    def bougies_minimum(self) -> int:
        p = self.parametres
        return max(
            p.periode_bollinger + p.bougies_contact,
            p.macd_lente + p.macd_signal,
            p.bougies_stop,
        ) + 1

    def preparer(self, bougies: pd.DataFrame) -> pd.DataFrame:
        """Calcule bandes, MACD, contacts et niveaux de stop en une passe."""
        verifier_bougies(bougies)
        p = self.parametres
        donnees = bougies.copy()

        bandes = bollinger(donnees["close"], p.periode_bollinger, p.ecarts_types)
        donnees[bandes.columns] = bandes

        lignes_macd = macd(donnees["close"], p.macd_rapide, p.macd_lente, p.macd_signal)
        donnees["macd"] = lignes_macd["macd"]
        donnees["macd_signal"] = lignes_macd["signal"]
        donnees["croise_haut"] = croisement_haussier(donnees["macd"], donnees["macd_signal"])
        donnees["croise_bas"] = croisement_baissier(donnees["macd"], donnees["macd_signal"])

        # Contact avec une bande sur la fenêtre glissante qui SE TERMINE à la
        # bougie courante : seul le passé compte.
        touche_bas = (donnees["low"] <= donnees["bb_basse"]).astype(float)
        touche_haut = (donnees["high"] >= donnees["bb_haute"]).astype(float)
        donnees["contact_bas"] = touche_bas.rolling(p.bougies_contact, min_periods=1).max() > 0
        donnees["contact_haut"] = touche_haut.rolling(p.bougies_contact, min_periods=1).max() > 0

        donnees["creux"] = plus_bas(donnees["low"], p.bougies_stop)
        donnees["sommet"] = plus_haut(donnees["high"], p.bougies_stop)

        donnees["en_session"] = colonne_session(donnees.index, p.sessions)
        return donnees

    # ------------------------------------------------------------------
    # Décision
    # ------------------------------------------------------------------

    def evaluer(self, historique: pd.DataFrame) -> Signal | None:
        """Décide sur la dernière bougie clôturée de `historique`."""
        if len(historique) < self.bougies_minimum:
            return None

        bougie = historique.iloc[-1]
        if bougie[_REQUISES].isna().any() or not bool(bougie["en_session"]):
            return None

        cloture = float(bougie["close"])
        mediane = float(bougie["bb_mediane"])

        if bool(bougie["contact_bas"]) and bool(bougie["croise_haut"]) and cloture < mediane:
            return self._construire(
                Sens.ACHAT, cloture, float(bougie["creux"]), float(bougie["bb_haute"])
            )
        if bool(bougie["contact_haut"]) and bool(bougie["croise_bas"]) and cloture > mediane:
            return self._construire(
                Sens.VENTE, cloture, float(bougie["sommet"]), float(bougie["bb_basse"])
            )
        return None

    def _construire(self, sens: Sens, entree: float, stop: float, objectif: float) -> Signal | None:
        """Assemble le signal, ou renonce si le gain visé ne vaut pas le risque."""
        risque = abs(entree - stop)
        if risque <= 0:
            return None
        ratio = abs(objectif - entree) / risque
        if ratio < self.parametres.ratio_minimum:
            return None
        cote = "basse" if sens is Sens.ACHAT else "haute"
        return Signal(
            sens=sens,
            entree=entree,
            stop=stop,
            objectif=objectif,
            raison=f"contact bande {cote} + croisement MACD, bande opposée visée ({ratio:.1f} R)",
        )

    # ------------------------------------------------------------------
    # Vérification
    # ------------------------------------------------------------------

    def controles(self, bougie: pd.Series, trade: pd.Series, decimales: int) -> list[Controle]:
        """Rejoue les cinq conditions et le placement du stop sur la bougie de signal."""
        p = self.parametres
        achat = trade["sens"] == "achat"
        d = decimales

        cloture = float(bougie["close"])
        mediane = float(bougie["bb_mediane"])
        niveau_stop = float(bougie["creux"] if achat else bougie["sommet"])
        opposee = float(bougie["bb_haute"] if achat else bougie["bb_basse"])
        stop_trade = float(trade["stop_initial"])
        risque = abs(cloture - niveau_stop)
        ratio = abs(opposee - cloture) / risque if risque > 0 else 0.0

        return [
            Controle(
                cle="contact",
                condition=f"Excès : contact avec la bande sur {p.bougies_contact} bougies",
                attendu="bande basse touchée" if achat else "bande haute touchée",
                constate="oui" if bool(bougie["contact_bas" if achat else "contact_haut"]) else "non",
                valide=bool(bougie["contact_bas" if achat else "contact_haut"]),
            ),
            Controle(
                cle="croisement",
                condition="Déclencheur : croisement du MACD",
                attendu="vers le haut" if achat else "vers le bas",
                constate=f"MACD {float(bougie['macd']):.6f} / signal {float(bougie['macd_signal']):.6f}",
                valide=bool(bougie["croise_haut"] if achat else bougie["croise_bas"]),
            ),
            Controle(
                cle="cote_moyenne",
                condition="Chemin restant : clôture du bon côté de la moyenne",
                attendu="clôture < moyenne" if achat else "clôture > moyenne",
                constate=f"{cloture:.{d}f} vs {mediane:.{d}f}",
                valide=(cloture < mediane) if achat else (cloture > mediane),
            ),
            Controle(
                cle="ratio",
                condition="Gain visé jusqu'à la bande opposée : au moins le ratio minimal",
                attendu=f"≥ {p.ratio_minimum:.1f} R",
                constate=f"{ratio:.2f} R",
                valide=ratio >= p.ratio_minimum,
            ),
            Controle(
                cle="session",
                condition="Horaire : session de marché ouverte",
                attendu=" ou ".join(p.sessions) or "toute heure",
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
