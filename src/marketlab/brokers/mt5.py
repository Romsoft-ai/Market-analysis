"""Le courtier réel : MetaTrader 5, relié au compte IC Markets.

Mêmes six opérations que le simulateur, traduites en requêtes `order_send`. Le
pilote ne voit aucune différence ; c'est tout l'intérêt.

STOP ET OBJECTIF POSÉS CHEZ LE COURTIER
---------------------------------------

Chaque ordre part AVEC son stop et son objectif. Ils vivent sur le serveur
d'IC Markets, pas dans ce programme : si le PC s'éteint ou perd la connexion,
la position reste protégée. Le robot ne fait que DÉPLACER le stop (break-even,
stop suiveur), il n'a jamais à surveiller lui-même un niveau de sortie.

LES POSITIONS DU ROBOT
----------------------

Décision du 21 octobre 2026 : aucun identifiant propre au robot. Toute position
ouverte sur l'instrument est donc considérée comme sienne. Il ne faut ni trader
l'instrument à la main pendant que le robot tourne, ni y faire tourner deux
stratégies à la fois.

Le module `MetaTrader5` n'est passé qu'en paramètre (`api`) : les tests lui
substituent un faux terminal, et aucun test ne touche jamais au compte.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from marketlab.brokers.base import (
    Broker,
    Compte,
    Deplacement,
    Ordre,
    OrdreRefuse,
    PositionOuverte,
    Specification,
)
from marketlab.config import get_broker, load_instruments, symbol_for
from marketlab.strategies.base import Sens

#: Écart de prix toléré à l'exécution, en points. Au-delà, le courtier refuse
#: l'ordre plutôt que de le remplir à un prix trop éloigné de la cotation.
ECART_MAX_POINTS = 20

#: Commentaire porté par chaque ordre, visible dans l'historique du terminal.
COMMENTAIRE = "marketlab"


@dataclass
class _Memoire:
    """Ce que MetaTrader ne conserve pas, et que le robot doit retenir lui-même.

    MT5 ne connaît que le stop ACTUEL d'une position. Le stop initial (la mesure
    du 1 R) et la raison des déplacements sont gardés ici, en mémoire : une
    reprise après redémarrage les perdra. Leur persistance relève du bloc 5.
    """

    stop_initial: float
    raison: str = ""
    break_even_arme: bool = False
    stop_deplace: bool = False


class MT5Broker(Broker):
    """Courtier MetaTrader 5, piloté à travers le module Python `MetaTrader5`."""

    def __init__(self, api: Any, courtier: str) -> None:
        """
        Args:
            api: le module `MetaTrader5`, déjà initialisé, ou un substitut de test.
            courtier: nom du courtier dans .env et instruments.yaml (« icmarket »),
                qui sert à traduire un instrument en symbole.
        """
        self.api = api
        self.courtier = courtier
        self._memoire: dict[int, _Memoire] = {}

    @classmethod
    @contextmanager
    def connecter(cls, courtier: str) -> Iterator[MT5Broker]:
        """Ouvre une session MT5 sur le compte du courtier et la referme en sortant."""
        from marketlab.data.mt5_session import mt5_session

        with mt5_session(get_broker(courtier)) as api:
            yield cls(api, courtier)

    # ------------------------------------------------------------------
    # Lecture
    # ------------------------------------------------------------------

    def compte(self) -> Compte:
        info = self.api.account_info()
        if info is None:
            raise OrdreRefuse(f"compte illisible : {self.api.last_error()}")
        return Compte(capital=float(info.balance), devise=str(info.currency))

    def specification(self, instrument: str) -> Specification:
        """Lue chez le courtier, avec la valeur du pip convertie en devise du compte.

        `trade_tick_value` est le gain d'un lot quand le prix bouge d'un tick, déjà
        converti par MT5 dans la devise du compte. C'est plus juste que « taille du
        contrat × pip », qui suppose que l'instrument est coté dans cette devise.
        """
        info = self._symbole_info(instrument)
        pip = float(load_instruments()["instruments"][instrument]["pip"])
        return Specification(
            point=float(info.point),
            decimales=int(info.digits),
            valeur_pip=pip,
            valeur_pip_par_lot=float(info.trade_tick_value) * pip / float(info.trade_tick_size),
            volume_min=float(info.volume_min),
            volume_pas=float(info.volume_step),
        )

    def cotation(self, instrument: str, sens: Sens) -> float | None:
        """Prix demandé pour un achat, prix offert pour une vente : le spread est dedans."""
        tick = self.api.symbol_info_tick(self._symbole(instrument))
        if tick is None:
            return None
        prix = float(tick.ask if sens is Sens.ACHAT else tick.bid)
        return prix if prix > 0 else None

    def positions(self, instrument: str) -> list[PositionOuverte]:
        brutes = self.api.positions_get(symbol=self._symbole(instrument)) or ()
        return [self._traduire(p, instrument) for p in brutes]

    # ------------------------------------------------------------------
    # Ordres
    # ------------------------------------------------------------------

    def ouvrir(self, ordre: Ordre) -> PositionOuverte:
        symbole = self._symbole(ordre.instrument)
        info = self._symbole_info(ordre.instrument)
        prix = self.cotation(ordre.instrument, ordre.sens)
        if prix is None:
            raise OrdreRefuse(f"aucune cotation pour {symbole} : marché fermé ?")

        achat = ordre.sens is Sens.ACHAT
        requete = {
            "action": self.api.TRADE_ACTION_DEAL,
            "symbol": symbole,
            "volume": self._volume(ordre.volume, info),
            "type": self.api.ORDER_TYPE_BUY if achat else self.api.ORDER_TYPE_SELL,
            "price": prix,
            "sl": round(ordre.stop, info.digits),
            "tp": round(ordre.objectif, info.digits),
            "deviation": ECART_MAX_POINTS,
            "type_time": self.api.ORDER_TIME_GTC,
            "type_filling": self._remplissage(info),
            "comment": COMMENTAIRE,
        }
        resultat = self._envoyer(requete, f"ouverture {ordre.sens.value} {symbole}")

        ticket = int(resultat.order)
        self._memoire[ticket] = _Memoire(stop_initial=requete["sl"], raison=ordre.raison)
        return PositionOuverte(
            identifiant=ticket,
            instrument=ordre.instrument,
            sens=ordre.sens,
            volume=float(resultat.volume),
            entree=float(resultat.price),
            stop=requete["sl"],
            stop_initial=requete["sl"],
            objectif=requete["tp"],
            date_entree=datetime.now(UTC),
            raison=ordre.raison,
        )

    def modifier_stop(self, position: PositionOuverte, niveau: float, raison: Deplacement) -> None:
        info = self._symbole_info(position.instrument)
        requete = {
            "action": self.api.TRADE_ACTION_SLTP,
            "position": position.identifiant,
            "symbol": self._symbole(position.instrument),
            "sl": round(niveau, info.digits),
            # L'objectif doit être renvoyé : une requête SLTP sans lui l'effacerait.
            "tp": position.objectif,
        }
        self._envoyer(requete, f"déplacement du stop de {position.identifiant}")

        position.stop = requete["sl"]
        memoire = self._memoire.setdefault(
            position.identifiant, _Memoire(stop_initial=position.stop_initial)
        )
        if raison is Deplacement.BREAK_EVEN:
            position.break_even_arme = memoire.break_even_arme = True
        else:
            position.stop_deplace = memoire.stop_deplace = True

    def fermer(self, position: PositionOuverte) -> None:
        info = self._symbole_info(position.instrument)
        # Fermer un achat, c'est vendre au prix offert, et inversement.
        sens_inverse = Sens.VENTE if position.sens is Sens.ACHAT else Sens.ACHAT
        prix = self.cotation(position.instrument, sens_inverse)
        if prix is None:
            raise OrdreRefuse(f"aucune cotation pour fermer {position.identifiant}")
        requete = {
            "action": self.api.TRADE_ACTION_DEAL,
            "position": position.identifiant,
            "symbol": self._symbole(position.instrument),
            "volume": position.volume,
            "type": self.api.ORDER_TYPE_SELL if position.sens is Sens.ACHAT else self.api.ORDER_TYPE_BUY,
            "price": prix,
            "deviation": ECART_MAX_POINTS,
            "type_time": self.api.ORDER_TIME_GTC,
            "type_filling": self._remplissage(info),
            "comment": COMMENTAIRE,
        }
        self._envoyer(requete, f"fermeture de {position.identifiant}")
        self._memoire.pop(position.identifiant, None)

    # ------------------------------------------------------------------
    # Outils
    # ------------------------------------------------------------------

    def _symbole(self, instrument: str) -> str:
        return symbol_for(instrument, self.courtier)

    def _symbole_info(self, instrument: str) -> Any:
        symbole = self._symbole(instrument)
        self.api.symbol_select(symbole, True)
        info = self.api.symbol_info(symbole)
        if info is None:
            raise OrdreRefuse(f"symbole {symbole} indisponible chez {self.courtier}")
        return info

    @staticmethod
    def _volume(volume: float, info: Any) -> float:
        """Arrondit au pas imposé, sans descendre sous le minimum."""
        pas = float(info.volume_step)
        return round(max(round(volume / pas) * pas, float(info.volume_min)), 8)

    def _remplissage(self, info: Any) -> int:
        """Mode de remplissage accepté par le symbole.

        Chaque courtier n'accepte que certains modes, et un mode refusé fait
        échouer l'ordre (code 10030). `filling_mode` est un champ de bits : 1 pour
        « tout ou rien » (FOK), 2 pour « exécuter ce qui peut l'être » (IOC).
        """
        modes = int(info.filling_mode)
        if modes & 1:
            return self.api.ORDER_FILLING_FOK
        if modes & 2:
            return self.api.ORDER_FILLING_IOC
        return self.api.ORDER_FILLING_RETURN

    def _envoyer(self, requete: dict, action: str) -> Any:
        """Envoie la requête et transforme tout échec en `OrdreRefuse` explicite."""
        resultat = self.api.order_send(requete)
        if resultat is None:
            raise OrdreRefuse(f"{action} : aucune réponse du terminal ({self.api.last_error()})")
        if resultat.retcode != self.api.TRADE_RETCODE_DONE:
            raise OrdreRefuse(f"{action} refusée, code {resultat.retcode} : {resultat.comment}")
        return resultat

    def _traduire(self, brute: Any, instrument: str) -> PositionOuverte:
        """Position MT5 vers position du pilote, complétée par la mémoire du robot."""
        ticket = int(brute.ticket)
        memoire = self._memoire.get(ticket) or _Memoire(stop_initial=float(brute.sl))
        return PositionOuverte(
            identifiant=ticket,
            instrument=instrument,
            sens=Sens.ACHAT if brute.type == self.api.POSITION_TYPE_BUY else Sens.VENTE,
            volume=float(brute.volume),
            entree=float(brute.price_open),
            stop=float(brute.sl),
            stop_initial=memoire.stop_initial,
            objectif=float(brute.tp),
            # Même convention que les bougies : heure serveur étiquetée UTC.
            date_entree=datetime.fromtimestamp(int(brute.time), UTC),
            raison=memoire.raison,
            break_even_arme=memoire.break_even_arme,
            stop_deplace=memoire.stop_deplace,
        )
