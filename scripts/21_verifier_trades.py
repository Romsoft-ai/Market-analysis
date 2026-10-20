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
from marketlab.strategies.registre import depuis_journal


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
    strategie = depuis_journal(parametres)
    if strategie is None:
        print(f"\n  La stratégie {parametres.get('strategie_classe', '?')} a été retirée")
        print("  du catalogue : ses règles ne peuvent plus être rejouées.")
        return 1

    print("\n  Reconstruction des bougies et des indicateurs...")
    donnees = obtenir(
        parametres["instrument"],
        parametres["courtier"],
        parametres["echelle"],
        pd.Timestamp(parametres["debut_reel"]).to_pydatetime(),
        pd.Timestamp(parametres["fin_reelle"]).to_pydatetime(),
    )
    preparees = strategie.preparer(donnees)

    print("  Contrôle des conditions d'entrée...\n")
    rapport = verifier_lot(strategie, preparees, trades, parametres)

    conformes = int(rapport["tout_valide"].sum())
    part = conformes / len(rapport) * 100

    # Les libellés viennent des contrôles eux-mêmes : chaque stratégie déclare
    # les siens, ce script n'a donc aucune liste à tenir à jour.
    print("  RÉSULTAT PAR CONDITION")
    print("  " + "-" * 62)
    for colonne, libelle in rapport.attrs.get("libelles", {}).items():
        reussites = int(rapport[colonne].fillna(False).sum())
        marque = "OK " if reussites == len(rapport) else "!! "
        print(f"  {marque}{libelle:<46} {reussites:>6,} / {len(rapport):,}")

    print("\n  " + "-" * 62)
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
