"""Mesurer le spread RÉEL, celui que le robot paie au moment où il entre.

POURQUOI CE SCRIPT EXISTE
-------------------------

Jusqu'au 21 octobre 2026, le backtest prenait la médiane du champ `spread` des
bougies M1. Or MetaTrader y range le spread le PLUS BAS de la minute, pas celui
auquel on traite. Sur un marché liquide, ce minimum est presque nul : le backtest
payait 0,3 point sur GBPUSD quand l'ordre d'essai sur le compte démo en a coûté 9.
La confrontation au live l'a révélé ; ce script corrige la mesure.

CE QUI EST MESURÉ
-----------------

Le spread du premier tick qui suit chaque clôture de bougie M15, pendant les
sessions de Londres et de New York, sur les derniers jours de bourse. C'est
exactement l'instant où le robot envoie un ordre : ni la médiane de tous les
ticks (biaisée vers les moments très actifs, où le spread est serré), ni celle
des bougies (biaisée vers le minimum de chaque minute).

LA MAJORATION DU COMPTE
-----------------------

L'historique de ticks de MetaTrader est le flux BRUT du courtier. Le compte, lui,
exécute avec une majoration : mesuré le 21 octobre 2026 sur le compte démo,
+8 points sur GBPUSD et +10 sur l'or, rien sur US30 ni BTCUSD (compte « Standard »,
sans commission, spread élargi). Le script la mesure en comparant, au même
instant, la cotation du compte et le dernier tick de l'historique.

    spread réel = médiane historique à la clôture + majoration du compte

Lecture seule. Le résultat est à reporter dans config/instruments.yaml
(`spread_reel_points`), avec sa date de mesure.

Usage :
    python scripts/05_mesurer_spread.py
    python scripts/05_mesurer_spread.py --jours 20 --instruments GBPUSD XAUUSD
"""

from __future__ import annotations

import argparse
import time
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from marketlab.config import courtier_par_defaut, get_broker, load_instruments, symbol_for
from marketlab.data.mt5_session import mt5_session
from marketlab.data.temps import dans_sessions, serveur_vers_utc

SESSIONS = ["londres", "new_york"]


def arguments() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--courtier", default=courtier_par_defaut())
    p.add_argument("--instruments", nargs="*")
    p.add_argument("--jours", type=int, default=10, help="jours de bourse mesurés")
    return p.parse_args()


def jours_de_bourse(nombre: int) -> list[datetime]:
    """Les `nombre` derniers jours ouvrés avant aujourd'hui, en dates serveur."""
    jours, jour = [], datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    while len(jours) < nombre:
        jour -= timedelta(days=1)
        if jour.weekday() < 5:
            jours.append(jour)
    return sorted(jours)


def spreads_a_la_cloture(api, symbole: str, point: float, jour: datetime) -> list[float]:
    """Spread du premier tick après chaque clôture M15 en session, sur une journée."""
    brutes = api.copy_ticks_range(symbole, jour, jour + timedelta(days=1), api.COPY_TICKS_INFO)
    if brutes is None or len(brutes) == 0:
        return []
    ticks = pd.DataFrame(brutes)
    temps = pd.to_datetime(ticks["time_msc"], unit="ms", utc=True)
    ecarts = ((ticks["ask"] - ticks["bid"]) / point).to_numpy()

    clotures = pd.date_range(jour, jour + timedelta(days=1), freq="15min", inclusive="left", tz=UTC)
    clotures = clotures[dans_sessions(serveur_vers_utc(clotures), SESSIONS).to_numpy()]
    positions = temps.searchsorted(clotures)
    resultat = []
    for cloture, i in zip(clotures, positions, strict=True):
        # Premier tick dans la minute qui suit la clôture ; au-delà, le marché
        # était inactif et l'échantillon ne représenterait pas une entrée réelle.
        if i < len(temps) and temps.iloc[i] - cloture < pd.Timedelta(minutes=1):
            resultat.append(float(ecarts[i]))
    return resultat


def majoration(api, symbole: str, point: float, mesures: int = 10) -> float:
    """Écart médian entre la cotation du compte et le dernier tick de l'historique brut."""
    ecarts = []
    for _ in range(mesures):
        tick = api.symbol_info_tick(symbole)
        if tick is None:
            break
        fin = datetime.fromtimestamp(tick.time + 5, UTC)
        brutes = api.copy_ticks_range(symbole, fin - timedelta(minutes=2), fin, api.COPY_TICKS_INFO)
        if brutes is not None and len(brutes):
            brut = (brutes[-1]["ask"] - brutes[-1]["bid"]) / point
            ecarts.append((tick.ask - tick.bid) / point - brut)
        time.sleep(0.5)
    return float(np.median(ecarts)) if ecarts else 0.0


def main() -> int:
    a = arguments()
    instruments = a.instruments or list(load_instruments()["instruments"])
    jours = jours_de_bourse(a.jours)
    print(f"\n  Spread à la clôture M15, sessions {' + '.join(SESSIONS)}, "
          f"{jours[0]:%d/%m} → {jours[-1]:%d/%m} ({len(jours)} jours)\n")
    with mt5_session(get_broker(a.courtier)) as api:
        for instrument in instruments:
            symbole = symbol_for(instrument, a.courtier)
            api.symbol_select(symbole, True)
            point = api.symbol_info(symbole).point
            echantillon = np.array(
                [s for jour in jours for s in spreads_a_la_cloture(api, symbole, point, jour)]
            )
            if not len(echantillon):
                print(f"  {instrument:7} aucun tick reçu")
                continue
            ajout = majoration(api, symbole, point)
            print(
                f"  {instrument:7} historique : médiane {np.median(echantillon):6.1f}  "
                f"p95 {np.percentile(echantillon, 95):6.1f}   + majoration {ajout:5.1f}   "
                f"→ SPREAD RÉEL {np.median(echantillon) + ajout:6.1f} pts   ({len(echantillon)} clôtures)"
            )
    print("\n  À reporter dans config/instruments.yaml : spread_reel_points.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
