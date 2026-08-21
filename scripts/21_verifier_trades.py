"""Étape 1, bloc 2 — Vérifier qu'un backtest respecte bien ses propres règles.

Rejoue les conditions d'entrée sur chaque trade d'une expérience enregistrée, et
signale toute divergence entre ce que le moteur a fait et ce que les règles
énoncent.

Pourquoi ce contrôle est distinct des tests unitaires : ceux-ci vérifient que le
moteur fait ce qui a été codé, sur des scénarios fabriqués. Celui-ci vérifie que
le résultat obtenu sur des données réelles correspond aux règles telles qu'on les
a écrites. Une seule divergence suffit à rendre un backtest inexploitable.

Usage :
    python scripts/21_verifier_trades.py                  # dernière expérience
    python scripts/21_verifier_trades.py 20260820_081919_GBPUSD_B1
"""

from __future__ import annotations

import sys

import pandas as pd

from marketlab.backtest import journal
from marketlab.backtest.verification import verifier_lot
from marketlab.data.historique import obtenir
from marketlab.strategies.confluence import STRATEGIES

#: Libellés des contrôles, par NATURE et non par rang. Les contrôles
#: conditionnels changent de position d'une stratégie à l'autre : B1v3 porte la
#: ligne zéro et la session, B1v5 la session seule. Un tableau indexé par rang
#: afficherait alors « ligne zéro » devant le résultat du contrôle horaire.
LIBELLES = {
    "tendance": "Tendance (EMA)",
    "croisement": "Croisement MACD",
    "rsi": "Fenêtre RSI",
    "stop": "Niveau du stop",
    "entree": "Entrée en N+1",
    "ligne_zero": "Côté de la ligne zéro",
    "session": "Session ouverte",
}


def main() -> int:
    identifiants = journal.lister()
    if not identifiants:
        print("Aucune expérience enregistrée. Lancer d'abord scripts/20_backtest.py.")
        return 1

    identifiant = sys.argv[1] if len(sys.argv) > 1 else identifiants[0]
    experience = journal.charger_experience(identifiant)
    trades = journal.charger_trades(identifiant)

    print(f"\n{'=' * 62}")
    print(f"  VÉRIFICATION  {identifiant}")
    print("=" * 62)
    print(f"\n  {experience.parametres.get('strategie', '?')}")
    print(f"  {len(trades):,} trades à contrôler")

    if trades.empty:
        print("\n  Aucun trade.")
        return 0

    parametres = experience.parametres
    print("\n  Reconstruction des bougies et des indicateurs...")
    donnees = obtenir(
        parametres["instrument"],
        parametres["courtier"],
        parametres["echelle"],
        pd.Timestamp(parametres["debut_reel"]).to_pydatetime(),
        pd.Timestamp(parametres["fin_reelle"]).to_pydatetime(),
    )
    classe = STRATEGIES.get(str(parametres.get("strategie_code", "B1")), STRATEGIES["B1"])
    strategie = classe(
        periode_ema=int(parametres["strat_periode_ema"]),
        macd_rapide=int(parametres["strat_macd_rapide"]),
        macd_lente=int(parametres["strat_macd_lente"]),
        macd_signal=int(parametres["strat_macd_signal"]),
        periode_rsi=int(parametres["strat_periode_rsi"]),
        rsi_plancher=float(parametres["strat_rsi_plancher"]),
        rsi_plafond=float(parametres["strat_rsi_plafond"]),
        bougies_stop=int(parametres["strat_bougies_stop"]),
        ratio_objectif=float(parametres["strat_ratio_objectif"]),
    )
    preparees = strategie.preparer(donnees)

    print("  Contrôle des conditions d'entrée...\n")
    rapport = verifier_lot(preparees, trades, parametres)

    conformes = int(rapport["tout_valide"].sum())
    part = conformes / len(rapport) * 100

    print("  RÉSULTAT PAR CONDITION")
    print("  " + "-" * 46)
    inconnues = [
        c for c in rapport.columns
        if c not in LIBELLES and c not in {"date_entree", "sens", "tout_valide", "manquement"}
    ]
    if inconnues:
        print(f"  [!] contrôles sans libellé connu : {', '.join(inconnues)}")
    for colonne, libelle in LIBELLES.items():
        if colonne not in rapport.columns:
            continue
        reussites = int(rapport[colonne].sum())
        marque = "OK " if reussites == len(rapport) else "!! "
        print(f"  {marque}{libelle:<24} {reussites:>6,} / {len(rapport):,}")

    print("\n  " + "-" * 46)
    print(f"  Trades entièrement conformes : {conformes:,} / {len(rapport):,} "
          f"({part:.2f} %)")

    if conformes == len(rapport):
        print("\n  Toutes les entrées respectent les règles énoncées.")
        print("  Le moteur et la stratégie sont cohérents.\n")
        return 0

    echecs = rapport[~rapport["tout_valide"]]
    print(f"\n  {len(echecs)} trade(s) en écart. Répartition des manquements :\n")
    for motif, nombre in echecs["manquement"].value_counts().items():
        print(f"    {nombre:>5,}  {motif}")

    print("\n  Premiers cas à examiner dans l'inspecteur :")
    for _, ligne in echecs.head(5).iterrows():
        print(f"    {ligne['date_entree']:%Y-%m-%d %H:%M}  {ligne['sens']:<6}"
              f"  {ligne['manquement']}")
    print()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
