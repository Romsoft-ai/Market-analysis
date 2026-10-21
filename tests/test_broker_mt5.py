"""Vérifie MT5Broker sur un faux terminal : aucune requête ne quitte ce fichier.

Ce que ces tests garantissent : les requêtes envoyées à MetaTrader ont la bonne
forme (stop et objectif posés AVEC l'ordre, objectif conservé quand on déplace le
stop, fermeture dans le sens inverse), et un refus du courtier devient une
erreur explicite au lieu d'être ignoré.

Ce qu'ils ne garantissent pas : que le vrai serveur accepte ces requêtes. C'est
le rôle de l'essai réel sur le compte démo (scripts/40_essai_mt5.py).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from marketlab.brokers.base import Deplacement, Ordre, OrdreRefuse
from marketlab.brokers.mt5 import MT5Broker
from marketlab.pilote import Pilote
from marketlab.strategies.base import Sens


class FauxMT5:
    """Le strict nécessaire du module MetaTrader5, avec un journal des requêtes."""

    TRADE_ACTION_DEAL = 1
    TRADE_ACTION_SLTP = 6
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    POSITION_TYPE_BUY = 0
    POSITION_TYPE_SELL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_RETURN = 2
    TRADE_RETCODE_DONE = 10009

    def __init__(self, refuser: int | None = None) -> None:
        self.requetes: list[dict] = []
        self.refuser = refuser
        self.ouvertes: list[SimpleNamespace] = []

    def account_info(self):
        return SimpleNamespace(balance=100_000.0, currency="USD")

    def symbol_select(self, symbole, actif):
        return True

    def symbol_info(self, symbole):
        return SimpleNamespace(point=0.00001, digits=5, trade_tick_value=1.0,
                               trade_tick_size=0.00001, volume_min=0.01,
                               volume_step=0.01, filling_mode=2)

    def symbol_info_tick(self, symbole):
        return SimpleNamespace(ask=1.30012, bid=1.30000)

    def positions_get(self, symbol=None):
        return tuple(self.ouvertes)

    def last_error(self):
        return (0, "aucune")

    def order_send(self, requete):
        self.requetes.append(requete)
        if self.refuser is not None:
            return SimpleNamespace(retcode=self.refuser, comment="Invalid stops",
                                   order=0, price=0.0, volume=0.0)
        return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, comment="Request executed",
                               order=4242, price=requete.get("price", 0.0),
                               volume=requete.get("volume", 0.0))


def ordre_achat() -> Ordre:
    return Ordre(instrument="GBPUSD", sens=Sens.ACHAT, volume=0.5,
                 stop=1.29800, objectif=1.30650, raison="test")


def test_l_ordre_part_avec_son_stop_et_son_objectif():
    """Stop et objectif vivent chez le courtier : la position reste protégée si le PC s'éteint."""
    api = FauxMT5()
    position = MT5Broker(api, "icmarket").ouvrir(ordre_achat())

    requete = api.requetes[0]
    assert requete["action"] == api.TRADE_ACTION_DEAL
    assert requete["type"] == api.ORDER_TYPE_BUY
    assert requete["symbol"] == "GBPUSD"
    assert requete["sl"] == 1.298 and requete["tp"] == 1.3065
    assert requete["price"] == 1.30012, "un achat se remplit au prix demandé"
    assert requete["type_filling"] == api.ORDER_FILLING_IOC
    assert position.identifiant == 4242
    assert position.stop_initial == 1.298


def test_une_vente_se_remplit_au_prix_offert():
    api = FauxMT5()
    MT5Broker(api, "icmarket").ouvrir(
        Ordre(instrument="GBPUSD", sens=Sens.VENTE, volume=0.5, stop=1.302, objectif=1.296)
    )
    assert api.requetes[0]["type"] == api.ORDER_TYPE_SELL
    assert api.requetes[0]["price"] == 1.30000


def test_un_refus_du_courtier_devient_une_erreur_explicite():
    api = FauxMT5(refuser=10016)
    with pytest.raises(OrdreRefuse, match="10016"):
        MT5Broker(api, "icmarket").ouvrir(ordre_achat())


def test_deplacer_le_stop_conserve_l_objectif():
    """Une requête SLTP sans objectif l'effacerait chez le courtier."""
    api = FauxMT5()
    broker = MT5Broker(api, "icmarket")
    position = broker.ouvrir(ordre_achat())
    broker.modifier_stop(position, 1.29950, Deplacement.SUIVEUR)

    requete = api.requetes[-1]
    assert requete["action"] == api.TRADE_ACTION_SLTP
    assert requete["position"] == 4242
    assert requete["sl"] == 1.2995
    assert requete["tp"] == 1.3065
    assert position.stop == 1.2995 and position.stop_deplace


def test_fermer_un_achat_c_est_vendre():
    api = FauxMT5()
    broker = MT5Broker(api, "icmarket")
    position = broker.ouvrir(ordre_achat())
    broker.fermer(position)

    requete = api.requetes[-1]
    assert requete["type"] == api.ORDER_TYPE_SELL
    assert requete["position"] == 4242
    assert requete["price"] == 1.30000


def test_les_positions_retrouvent_leur_stop_initial_apres_un_deplacement():
    """MT5 ne connaît que le stop actuel : le stop initial, mesure du 1 R, vient de la mémoire."""
    api = FauxMT5()
    broker = MT5Broker(api, "icmarket")
    position = broker.ouvrir(ordre_achat())
    broker.modifier_stop(position, 1.29950, Deplacement.SUIVEUR)
    api.ouvertes = [SimpleNamespace(ticket=4242, type=0, volume=0.5, price_open=1.30012,
                                    sl=1.2995, tp=1.3065, time=1_760_000_000)]

    [relue] = broker.positions("GBPUSD")
    assert relue.stop == 1.2995
    assert relue.stop_initial == 1.298
    assert relue.stop_deplace


def test_la_valeur_du_pip_est_convertie_en_devise_du_compte():
    """Un pip GBPUSD vaut 10 ticks ; à 1 USD le tick, un lot gagne 10 USD par pip."""
    spec = MT5Broker(FauxMT5(), "icmarket").specification("GBPUSD")
    assert spec.valeur_pip_par_lot == pytest.approx(10.0)


def test_le_pilote_passe_un_ordre_dimensionne_sur_le_vrai_courtier():
    """Le même pilote que le backtest, branché sur MT5 : 0,2 % de 100 000 = 200 USD de risque.

    Stop 21,2 pips sous le prix demandé, 10 USD par pip et par lot : 0,94 lot.
    """
    import pandas as pd

    from marketlab.strategies.base import Signal

    class UnSignal:
        bougies_minimum = 0

        def evaluer(self, historique):
            return Signal(Sens.ACHAT, entree=1.30000, stop=1.29800, objectif=1.30600)

        def ajuster_stop(self, sens, stop_actuel, bougie):
            return None

    api = FauxMT5()
    pilote = Pilote(UnSignal(), MT5Broker(api, "icmarket"), "GBPUSD")
    bougie = pd.DataFrame({"open": [1.3], "high": [1.3], "low": [1.3], "close": [1.3]})
    pilote.sur_cloture(bougie)

    requete = api.requetes[0]
    assert requete["volume"] == pytest.approx(0.94)
    assert requete["sl"] == 1.298
    # Objectif recalculé depuis le prix demandé pour tenir les 3 R annoncés.
    assert requete["tp"] == pytest.approx(round(1.30012 + 3 * (1.30012 - 1.298), 5))
