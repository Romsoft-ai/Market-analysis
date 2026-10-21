"""B3 : SuperTrend + filtre RSI, avec un stop qui suit la tendance.

Le SuperTrend donne à la fois le SENS de la tendance et un STOP qui s'adapte à la
volatilité : large quand le marché s'agite, serré quand il se calme. C'est la
seule baseline dont le stop bouge pendant la vie de la position.

--------------------------------------------------------------------------
Règles, figées le 20 octobre 2026
--------------------------------------------------------------------------

    ACHAT, toutes les conditions vraies sur la bougie clôturée :
        1. le SuperTrend (ATR 10, multiplicateur 3) BASCULE en tendance haussière
           sur cette bougie
        2. RSI (14) > 50 : le momentum confirme la bascule
        3. la bougie est dans la session de Londres ou de New York

    VENTE, symétrique : bascule baissière et RSI < 50.

    Stop initial : la ligne SuperTrend de la bougie de signal.
    Stop suiveur : à chaque clôture, le stop rejoint la ligne SuperTrend tant que
    la tendance tient. Il ne recule jamais (garanti par le moteur).
    Objectif : fixe, à 3 fois le risque initial.

--------------------------------------------------------------------------
Ce qui la distingue
--------------------------------------------------------------------------

Décision du 20 octobre 2026 : stop suiveur ET objectif fixe à 3 R, comme B1. Le
trade a donc deux façons de se terminer en gain : l'objectif, ou un stop remonté
au-dessus de l'entrée puis touché. La part de chacune, visible par le motif de
sortie « stop suiveur », dira si le suivi apporte quelque chose par rapport à un
stop fixe.

Limite connue : quand la tendance s'inverse sur une clôture, le stop n'est plus
déplacé, et la position reste ouverte jusqu'à ce que le prix touche le dernier
niveau suivi. Celui-ci est alors très proche du prix : la sortie suit en général
dès la bougie suivante.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from marketlab.strategies.base import Controle, Sens, Signal, Strategie, verifier_bougies
from marketlab.strategies.briques import colonne_session, signal_a_ratio
from marketlab.strategies.indicateurs import rsi, supertrend

#: Colonnes d'indicateurs qui doivent être calculées avant toute décision.
_REQUISES = ["supertrend", "tendance", "tendance_prec", "rsi"]


@dataclass(frozen=True)
class Parametres:
    """Tous les réglages de B3, et rien qu'ici. Les valeurs par défaut font foi."""

    periode_atr: int = 10
    multiplicateur: float = 3.0
    periode_rsi: int = 14
    #: Seuil de momentum : au-dessus pour un achat, en dessous pour une vente.
    rsi_seuil: float = 50.0
    ratio_objectif: float = 3.0
    sessions: tuple[str, ...] = ("londres", "new_york")


class SupertrendRsi(Strategie):
    """B3 : suivre la bascule de tendance, avec un stop qui suit le SuperTrend."""

    code = "B3"
    nom = "B3 : SuperTrend + RSI (stop suiveur)"
    Parametres = Parametres

    parametres: Parametres

    @property
    def bougies_minimum(self) -> int:
        """L'ATR doit être calculé, et une bascule demande la bougie précédente."""
        p = self.parametres
        return max(p.periode_atr, p.periode_rsi) + 2

    def preparer(self, bougies: pd.DataFrame) -> pd.DataFrame:
        """Calcule SuperTrend, RSI et sessions en une passe."""
        verifier_bougies(bougies)
        p = self.parametres
        donnees = bougies.copy()

        lignes = supertrend(donnees, p.periode_atr, p.multiplicateur)
        donnees["supertrend"] = lignes["supertrend"]
        donnees["tendance"] = lignes["tendance"]
        donnees["tendance_prec"] = lignes["tendance"].shift(1)

        donnees["rsi"] = rsi(donnees["close"], p.periode_rsi)
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

        p = self.parametres
        cloture = float(bougie["close"])
        ligne = float(bougie["supertrend"])
        valeur_rsi = float(bougie["rsi"])

        if self._bascule(bougie, Sens.ACHAT) and valeur_rsi > p.rsi_seuil:
            return signal_a_ratio(
                Sens.ACHAT, cloture, ligne, p.ratio_objectif,
                f"bascule SuperTrend haussière + RSI {valeur_rsi:.1f}",
            )
        if self._bascule(bougie, Sens.VENTE) and valeur_rsi < 100 - p.rsi_seuil:
            return signal_a_ratio(
                Sens.VENTE, cloture, ligne, p.ratio_objectif,
                f"bascule SuperTrend baissière + RSI {valeur_rsi:.1f}",
            )
        return None

    @staticmethod
    def _bascule(bougie: pd.Series, sens: Sens) -> bool:
        """La tendance change-t-elle de sens sur cette bougie, dans le sens voulu ?"""
        vers = 1.0 if sens is Sens.ACHAT else -1.0
        return float(bougie["tendance"]) == vers and float(bougie["tendance_prec"]) == -vers

    # ------------------------------------------------------------------
    # Gestion de position
    # ------------------------------------------------------------------

    def ajuster_stop(self, sens: Sens, stop_actuel: float, bougie: pd.Series) -> float | None:
        """Le stop rejoint la ligne SuperTrend, tant que la tendance va dans le sens du trade.

        Après une inversion, la ligne passe de l'autre côté du prix : la proposer
        n'aurait aucun sens, on cesse donc de suivre.
        """
        if pd.isna(bougie["tendance"]) or pd.isna(bougie["supertrend"]):
            return None
        favorable = 1.0 if sens is Sens.ACHAT else -1.0
        if float(bougie["tendance"]) != favorable:
            return None
        return float(bougie["supertrend"])

    # ------------------------------------------------------------------
    # Vérification
    # ------------------------------------------------------------------

    def controles(self, bougie: pd.Series, trade: pd.Series, decimales: int) -> list[Controle]:
        """Rejoue la bascule, le filtre RSI, l'horaire et le stop initial."""
        p = self.parametres
        achat = trade["sens"] == "achat"
        d = decimales
        valeur_rsi = float(bougie["rsi"])
        ligne = float(bougie["supertrend"])
        stop_trade = float(trade["stop_initial"])

        return [
            Controle(
                cle="bascule",
                condition="Déclencheur : bascule du SuperTrend",
                attendu="baissière → haussière" if achat else "haussière → baissière",
                constate=f"{float(bougie['tendance_prec']):+.0f} → {float(bougie['tendance']):+.0f}",
                valide=self._bascule(bougie, Sens.ACHAT if achat else Sens.VENTE),
            ),
            Controle(
                cle="rsi",
                condition="Momentum : RSI confirme la bascule",
                attendu=f"RSI > {p.rsi_seuil:.0f}" if achat else f"RSI < {100 - p.rsi_seuil:.0f}",
                constate=f"{valeur_rsi:.1f}",
                valide=(valeur_rsi > p.rsi_seuil) if achat else (valeur_rsi < 100 - p.rsi_seuil),
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
                condition="Stop initial : ligne SuperTrend de la bougie de signal",
                attendu=f"{ligne:.{d}f}",
                constate=f"{stop_trade:.{d}f}",
                valide=abs(ligne - stop_trade) < 1e-9,
            ),
        ]
