"""Étape 0, bloc 3 — Les deux courtiers servent-ils les mêmes prix ?

Contrôle d'EXACTITUDE, une des six dimensions de qualité du plan : on compare
les mêmes bougies M1 chez deux courtiers, sur plusieurs époques.

Pourquoi c'est important. Le diagnostic a montré que FTMO et IC Markets
démarrent leur historique GBPUSD et BTCUSD exactement le même jour. Or il
n'existait aucun CFD Bitcoin chez un courtier en mars 2011. Soupçon : l'historique
ancien n'est pas constitué des cotations propres de chaque courtier, mais d'un jeu
de données commun fourni en amont.

Comment on tranche :
  * prix identiques au centième  -> même source, données non spécifiques au courtier
  * prix différents              -> chaque courtier a bien ses propres cotations

Conséquence pratique. Si l'historique ancien est commun, backtester dessus ne dit
rien de ce que l'exécution aurait été chez FTMO. Il faut alors réserver les
périodes récentes aux tests décisifs, et l'historique profond aux seuls contrôles
de robustesse.

Lecture seule.

Usage :
    python scripts/02_comparer_courtiers.py
    python scripts/02_comparer_courtiers.py GBPUSD XAUUSD
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

import pandas as pd

from marketlab.config import ConfigError, get_broker, load_instruments, symbol_for
from marketlab.data.explore import charger_m1
from marketlab.data.mt5_session import MT5Error, mt5_session

COURTIERS = ("ftmo", "icmarket")

# Une journée par époque : assez pour comparer ~1400 bougies, sans transfert lourd.
EPOQUES = [
    ("ancienne", datetime(2002, 6, 12, tzinfo=UTC)),
    ("intermédiaire", datetime(2015, 6, 10, tzinfo=UTC)),
    ("récente", datetime(2026, 6, 10, tzinfo=UTC)),
]


def collecter(instruments: list[str]) -> dict[tuple[str, str, str], pd.DataFrame]:
    """Charge une journée de M1 par (courtier, instrument, époque)."""
    donnees: dict[tuple[str, str, str], pd.DataFrame] = {}

    for courtier in COURTIERS:
        print(f"\nLecture chez « {courtier} »...")
        with mt5_session(get_broker(courtier)) as api:
            for instrument in instruments:
                symbole = symbol_for(instrument, courtier)
                for etiquette, jour in EPOQUES:
                    df = charger_m1(api, symbole, jour, jour + timedelta(days=1))
                    donnees[(courtier, instrument, etiquette)] = df
                    print(f"  {instrument:<8} {etiquette:<14} {len(df):>5} bougies")
    return donnees


def comparer(
    a: pd.DataFrame, b: pd.DataFrame
) -> tuple[int, float | None, float | None]:
    """Compare deux séries de bougies alignées sur l'horodatage.

    Retourne (bougies communes, % de clôtures identiques, écart absolu moyen).
    """
    if a.empty or b.empty:
        return 0, None, None

    communs = a.index.intersection(b.index)
    if len(communs) == 0:
        return 0, None, None

    ca, cb = a.loc[communs, "close"], b.loc[communs, "close"]
    identiques = (ca == cb).sum() / len(communs) * 100
    ecart = (ca - cb).abs().mean()
    return len(communs), float(identiques), float(ecart)


def main() -> int:
    try:
        toutes = load_instruments()["instruments"]
    except (ConfigError, KeyError) as exc:
        print(f"[CONFIGURATION] {exc}")
        return 1

    instruments = sys.argv[1:] or list(toutes)
    inconnus = [i for i in instruments if i not in toutes]
    if inconnus:
        print(f"[ERREUR] Instruments inconnus : {', '.join(inconnus)}")
        return 1

    try:
        donnees = collecter(instruments)
    except (ConfigError, MT5Error) as exc:
        print(f"\n[ÉCHEC] {exc}")
        return 1

    print(f"\n{'=' * 78}")
    print("  FTMO contre IC MARKETS — clôtures M1 sur une journée")
    print("=" * 78)
    print(f"\n  {'Instrument':<10} {'Époque':<15} {'Communes':>9} "
          f"{'Identiques':>11} {'Écart moyen':>13}   Verdict")
    print("  " + "-" * 74)

    for instrument in instruments:
        for etiquette, _ in EPOQUES:
            n, pct, ecart = comparer(
                donnees[("ftmo", instrument, etiquette)],
                donnees[("icmarket", instrument, etiquette)],
            )
            if n == 0:
                print(f"  {instrument:<10} {etiquette:<15} {'—':>9} "
                      f"{'—':>11} {'—':>13}   pas de recouvrement")
                continue

            if pct is not None and pct > 99:
                verdict = "MÊME SOURCE"
            elif pct is not None and pct > 50:
                verdict = "sources proches"
            else:
                verdict = "cotations propres"

            print(f"  {instrument:<10} {etiquette:<15} {n:>9,} "
                  f"{pct:>10.1f}% {ecart:>13.5f}   {verdict}")

    print("\n  Lecture : « MÊME SOURCE » signifie que l'historique n'est pas propre")
    print("  au courtier — il ne reflète donc pas son exécution réelle.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
