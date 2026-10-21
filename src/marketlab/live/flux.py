"""Le flux live : les bougies clôturées, construites comme celles du backtest.

DEUX GARANTIES, SANS LESQUELLES LE LIVE NE MESURERAIT PAS LA STRATÉGIE TESTÉE
------------------------------------------------------------------------------

1. **Mêmes bougies.** On lit des bougies M1 chez MetaTrader et on les agrège avec
   la fonction `agreger` du backtest, au lieu de demander directement des M15 au
   terminal. Une seule recette de fabrication des bougies pour les deux mondes.

2. **Seulement des bougies CLÔTURÉES.** Une bougie M15 n'est rendue que si sa fin
   est passée selon l'HEURE DU SERVEUR (celle de la dernière cotation), jamais
   selon l'horloge du PC, qui peut dériver. Décider sur une bougie en cours de
   formation reviendrait à décider sur un prix qui va encore changer.

LE PRÉCHAUFFAGE DES INDICATEURS
-------------------------------

On lit environ 2 000 bougies M15, bien plus que les 201 dont B1 a besoin. Les
moyennes exponentielles (EMA, MACD, RSI, ATR) dépendent de leur point de départ :
calculée sur 300 bougies, l'EMA 200 du live différerait de celle du backtest,
calculée sur quatre ans, et le robot ne prendrait pas les mêmes décisions. Après
2 000 bougies, le poids du point de départ dans l'EMA 200 tombe à (1 - 2/201)^2000,
soit environ 0,005 %. Le rapprochement live / backtest le vérifie en pratique.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from marketlab.config import symbol_for
from marketlab.data.historique import agreger
from marketlab.data.mt5_session import MT5Error

#: Colonnes conservées, les mêmes que dans l'historique du backtest.
_COLONNES = ["open", "high", "low", "close", "tick_volume", "spread"]


class FluxMT5:
    """Lit chez MetaTrader les bougies clôturées d'un instrument."""

    def __init__(
        self, api: Any, courtier: str, echelle: str = "15min", bougies_historique: int = 2000
    ) -> None:
        """
        Args:
            api: le module `MetaTrader5` initialisé, ou un substitut de test.
            courtier: nom du courtier, pour traduire l'instrument en symbole.
            echelle: échelle de décision, au format pandas (« 15min », « 1h »).
            bougies_historique: nombre de bougies de décision à reconstituer.
        """
        self.api = api
        self.courtier = courtier
        self.echelle = echelle
        self.duree = pd.Timedelta(echelle)
        minutes = max(1, int(self.duree / pd.Timedelta(minutes=1)))
        self.nb_m1 = bougies_historique * minutes

    def heure_serveur(self, instrument: str) -> pd.Timestamp | None:
        """Heure de la dernière cotation, dans la convention des bougies (serveur étiqueté UTC)."""
        tick = self.api.symbol_info_tick(symbol_for(instrument, self.courtier))
        if tick is None or not tick.time:
            return None
        return pd.Timestamp(int(tick.time), unit="s", tz="UTC")

    def m1(self, instrument: str) -> pd.DataFrame:
        """Les dernières bougies M1, sous la même forme que l'historique du backtest."""
        symbole = symbol_for(instrument, self.courtier)
        self.api.symbol_select(symbole, True)
        brutes = self.api.copy_rates_from_pos(symbole, self.api.TIMEFRAME_M1, 0, self.nb_m1)
        if brutes is None or len(brutes) == 0:
            raise MT5Error(f"aucune bougie M1 reçue pour {symbole} : {self.api.last_error()}")
        donnees = pd.DataFrame(brutes)
        donnees["time"] = pd.to_datetime(donnees["time"], unit="s", utc=True)
        donnees = donnees.set_index("time").sort_index()
        return donnees[[c for c in _COLONNES if c in donnees.columns]]

    def bougies_cloturees(self, instrument: str) -> pd.DataFrame:
        """Les bougies de décision dont la fin est passée selon l'heure du serveur.

        Sans heure serveur (aucune cotation reçue), on ne rend rien plutôt que de
        risquer une bougie inachevée.
        """
        maintenant = self.heure_serveur(instrument)
        if maintenant is None:
            return pd.DataFrame(columns=_COLONNES)
        bougies = agreger(self.m1(instrument), self.echelle)
        return bougies[bougies.index + self.duree <= maintenant]

    def spread_median(self, instrument: str) -> float:
        """Spread médian, en points, sur les bougies M1 lues : la référence des garde-fous."""
        m1 = self.m1(instrument)
        return float(m1["spread"].median()) if "spread" in m1.columns and len(m1) else 0.0
