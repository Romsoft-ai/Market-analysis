"""Bloc 5 — Lancer le robot : une stratégie, un instrument, sur le compte du courtier.

Le robot se réveille à chaque clôture de bougie M15, lit les bougies chez
MetaTrader, appelle le pilote (le même qu'en backtest) et journalise tout.
Ctrl+C l'arrête proprement : les positions ouvertes gardent leur stop et leur
objectif chez le courtier.

DEUX MODES
----------

* **observation** (--observation) : le robot lit, décide et journalise, mais
  N'ENVOIE AUCUN ORDRE. Chaque entrée apparaît comme refusée « mode
  observation ». C'est le mode pour vérifier la boucle en conditions réelles ;
* **réel** (par défaut) : les ordres partent sur le compte configuré dans .env.

Sans base de données pour l'instant (bloc 5 en cours), le journal s'affiche dans
le terminal et n'est pas conservé.

Usage :
    python scripts/50_robot.py --strategie B3 --instrument GBPUSD --observation
    python scripts/50_robot.py --strategie B1 --instrument XAUUSD
"""

from __future__ import annotations

import argparse

from marketlab.brokers.base import Ordre, OrdreRefuse, PositionOuverte
from marketlab.brokers.mt5 import MT5Broker
from marketlab.config import ConfigError, courtier_par_defaut, get_broker, load_instruments
from marketlab.data.mt5_session import MT5Error, reconnecter
from marketlab.live.flux import FluxMT5
from marketlab.live.journal import JournalMemoire
from marketlab.live.robot import Robot
from marketlab.risk.garde_fous import GardeFous
from marketlab.strategies.registre import obtenir as strategie_du_catalogue
from marketlab.strategies.registre import strategies


class Observation(MT5Broker):
    """Le vrai courtier en lecture, mais qui refuse d'envoyer le moindre ordre."""

    def ouvrir(self, ordre: Ordre) -> PositionOuverte:
        raise OrdreRefuse(f"mode observation : {ordre.sens.value} {ordre.volume} lot(s) non envoyé")

    def modifier_stop(self, position, niveau, raison) -> None:
        raise OrdreRefuse("mode observation : stop non déplacé")

    def fermer(self, position) -> None:
        raise OrdreRefuse("mode observation : position non fermée")


def arguments() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--strategie", choices=list(strategies()), required=True)
    p.add_argument("--instrument", required=True)
    p.add_argument("--courtier", default=courtier_par_defaut())
    p.add_argument("--observation", action="store_true", help="décider sans envoyer d'ordre")
    p.add_argument("--risque", type=float, default=0.002, help="fraction du capital par trade")
    p.add_argument("--perte-max-jour", type=float, default=0.01)
    p.add_argument("--spread-max", type=float, default=3.0, help="multiple du spread médian")
    return p.parse_args()


def main() -> int:
    a = arguments()
    strategie = strategie_du_catalogue(a.strategie)()
    try:
        with MT5Broker.connecter(a.courtier) as reel:
            broker = Observation(reel.api, a.courtier) if a.observation else reel
            flux = FluxMT5(broker.api, a.courtier)
            # Même référence que le backtest : le spread réel mesuré à l'entrée.
            # Celle des bougies M1 (le minimum de chaque minute) bloquerait tout.
            conf = load_instruments()["instruments"][a.instrument]
            reference = float(conf.get("spread_reel_points") or flux.spread_median(a.instrument))
            journal = JournalMemoire(afficher=True)

            print(f"\n  ROBOT  {strategie.nom}  ·  {a.instrument}  ·  {a.courtier}"
                  f"  ·  {'OBSERVATION (aucun ordre)' if a.observation else 'RÉEL'}")
            print(f"  Garde-fous : perte max {a.perte_max_jour:.1%} par jour, spread max "
                  f"{a.spread_max:g} × {reference:.0f} pts (spread réel mesuré à l'entrée)")
            print("  Ctrl+C pour arrêter.\n")

            robot = Robot(
                strategie,
                broker,
                flux,
                a.instrument,
                journal,
                garde=GardeFous(reference, a.perte_max_jour, a.spread_max),
                reconnecter=lambda: reconnecter(get_broker(a.courtier)),
                risque_par_trade=a.risque,
            )
            try:
                robot.tourner()
            except KeyboardInterrupt:
                journal.arret("Ctrl+C : arrêt propre, les positions gardent leurs stops")
    except (ConfigError, MT5Error) as exc:
        print(f"\n  [ÉCHEC] {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
