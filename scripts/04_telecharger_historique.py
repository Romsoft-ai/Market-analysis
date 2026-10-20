"""Bascule sur IC Markets : télécharger l'historique M1 des instruments du projet.

Les backtests de l'étape 1 tournaient sur les données FTMO. IC Markets devient le
courtier principal (données ET exécution), parce que les comptes démo FTMO
expirent toutes les deux semaines. Backtester sur un courtier et trader sur un
autre recréerait le fossé backtest / réel que le projet cherche à éviter.

Pour chaque instrument, le script :
  1. télécharge les bougies M1 sur la période (ou les relit depuis le cache) ;
  2. vérifie ce qui a été reçu : première et dernière bougie, volume, trous ;
  3. relève les caractéristiques du contrat chez le courtier (taille, volume
     minimal, pas). Elles diffèrent d'un courtier à l'autre et la couche de
     risque en aura besoin pour calculer une taille de position juste.

Lecture seule : aucun ordre, aucune écriture chez le courtier.

Usage :
    python scripts/04_telecharger_historique.py
    python scripts/04_telecharger_historique.py --instruments US30 BTCUSD
    python scripts/04_telecharger_historique.py --debut 2021-01-01 --forcer
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta

import pandas as pd

from marketlab.config import (
    ConfigError,
    courtier_par_defaut,
    get_broker,
    load_instruments,
    symbol_for,
)
from marketlab.data.historique import obtenir_m1
from marketlab.data.mt5_session import MT5Error, mt5_session

# Au-delà de cet écart entre deux bougies consécutives, hors week-end, on le
# signale. Pas une heure pile : US30 et XAUUSD s'arrêtent chaque nuit de 23:59 à
# 01:00 (heure serveur), une pause normale qui produit un écart de 61 à 64
# minutes. Mesuré le 20/10/2026 : ce qui reste au-dessus du seuil correspond aux
# séances écourtées des jours fériés américains et aux 25 décembre / 1er janvier.
_TROU_SIGNALE = timedelta(minutes=90)


def date(texte: str) -> datetime:
    return datetime.strptime(texte, "%Y-%m-%d").replace(tzinfo=UTC)


def arguments() -> argparse.Namespace:
    aujourdhui = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--courtier", default=courtier_par_defaut(), help="DEFAULT_BROKER du .env")
    p.add_argument("--instruments", nargs="*", help="par défaut : tous ceux du projet")
    p.add_argument("--debut", type=date, default=date("2022-01-01"))
    p.add_argument("--fin", type=date, default=aujourdhui)
    p.add_argument("--forcer", action="store_true", help="ignorer le cache et retélécharger")
    return p.parse_args()


def contrats(courtier: str, instruments: list[str]) -> dict[str, dict]:
    """Relève les caractéristiques de contrat de chaque instrument chez le courtier."""
    releves: dict[str, dict] = {}
    with mt5_session(get_broker(courtier)) as api:
        for instrument in instruments:
            symbole = symbol_for(instrument, courtier)
            api.symbol_select(symbole, True)
            info = api.symbol_info(symbole)
            if info is None:
                continue
            releves[instrument] = {
                "symbole": symbole,
                "point": info.point,
                "decimales": info.digits,
                "taille_contrat": info.trade_contract_size,
                "volume_min": info.volume_min,
                "volume_pas": info.volume_step,
                "spread_actuel": info.spread,
            }
    return releves


def trous(m1: pd.DataFrame, sept_jours: bool) -> pd.Series:
    """Écarts anormaux entre deux bougies consécutives, indexés par leur fin.

    Un trou qui contient un samedi est la fermeture normale du marché, sauf pour
    un actif coté sept jours sur sept comme le Bitcoin, où tout écart compte.
    """
    horodatages = m1.index.to_series()
    ecarts = horodatages.diff()
    longs = ecarts[ecarts > _TROU_SIGNALE]
    if sept_jours or longs.empty:
        return longs
    debuts = horodatages.shift()[longs.index]
    contient_samedi = [
        any(jour.weekday() == 5 for jour in pd.date_range(debut.normalize(), fin.normalize()))
        for debut, fin in zip(debuts, longs.index, strict=True)
    ]
    return longs[[not s for s in contient_samedi]]


def main() -> int:
    a = arguments()
    config = load_instruments()["instruments"]
    connus = list(config)
    instruments = a.instruments or connus
    inconnus = [i for i in instruments if i not in connus]
    if inconnus:
        print(f"[ERREUR] Instruments inconnus : {', '.join(inconnus)}")
        return 1

    print(f"\n{'=' * 66}")
    print(f"  HISTORIQUE M1 chez {a.courtier}  ·  {a.debut:%Y-%m-%d} → {a.fin:%Y-%m-%d}")
    print("=" * 66)

    bilan = []
    for instrument in instruments:
        print(f"\n— {instrument}")
        try:
            m1 = obtenir_m1(instrument, a.courtier, a.debut, a.fin, a.forcer)
        except (ConfigError, MT5Error) as exc:
            print(f"  [ÉCHEC] {exc}")
            bilan.append({"instrument": instrument, "bougies": 0})
            continue
        anormaux = trous(m1, sept_jours=config[instrument].get("classe") == "crypto")
        bilan.append(
            {
                "instrument": instrument,
                "bougies": len(m1),
                "premiere": m1.index[0],
                "derniere": m1.index[-1],
                "trous": len(anormaux),
                "plus_long": anormaux.max() if len(anormaux) else timedelta(0),
            }
        )

    print(f"\n{'=' * 66}\n  BILAN\n{'=' * 66}")
    for b in bilan:
        if not b["bougies"]:
            print(f"  {b['instrument']:<7} ÉCHEC")
            continue
        print(
            f"  {b['instrument']:<7} {b['bougies']:>9,} bougies  "
            f"{b['premiere']:%Y-%m-%d} → {b['derniere']:%Y-%m-%d %H:%M}  "
            f"trous hors week-end > 1 h : {b['trous']} "
            f"(le plus long : {b['plus_long']})"
        )

    print(f"\n{'=' * 66}\n  CONTRATS chez {a.courtier}\n{'=' * 66}")
    try:
        for instrument, c in contrats(a.courtier, instruments).items():
            print(
                f"  {instrument:<7} {c['symbole']:<9} point={c['point']:<8} "
                f"décimales={c['decimales']}  contrat={c['taille_contrat']:<9} "
                f"vol. min={c['volume_min']}  pas={c['volume_pas']}  "
                f"spread actuel={c['spread_actuel']} pts"
            )
    except MT5Error as exc:
        print(f"  [ÉCHEC] {exc}")

    return 0 if all(b["bougies"] for b in bilan) else 1


if __name__ == "__main__":
    raise SystemExit(main())
