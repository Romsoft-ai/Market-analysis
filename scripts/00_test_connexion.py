"""Étape 0, bloc 1 — Vérifier que la connexion au terminal MT5 fonctionne.

Ce script ne télécharge aucune donnée et ne passe aucun ordre.
Il répond à une seule question : est-ce que je suis bien connecté, et à quoi ?

Usage :
    python scripts/00_test_connexion.py            # courtier par défaut (.env)
    python scripts/00_test_connexion.py ftmo
    python scripts/00_test_connexion.py demo
"""

from __future__ import annotations

import sys

from marketlab.config import ConfigError, get_broker
from marketlab.data.mt5_session import MT5Error, mt5_session

# Valeurs de account_info().trade_mode, telles que définies par MT5.
# Ne pas se contenter d'un « != 0 » : confondre démo et réel serait dangereux.
TRADE_MODES = {0: "démo", 1: "concours", 2: "RÉEL — attention"}


def afficher(titre: str, lignes: dict[str, object]) -> None:
    """Affiche un bloc de résultats aligné, pour rester lisible."""
    print(f"\n{titre}")
    print("-" * len(titre))
    largeur = max(len(k) for k in lignes)
    for cle, valeur in lignes.items():
        print(f"  {cle:<{largeur}} : {valeur}")


def main() -> int:
    nom_courtier = sys.argv[1] if len(sys.argv) > 1 else None

    try:
        broker = get_broker(nom_courtier)
    except ConfigError as exc:
        print(f"\n[CONFIGURATION] {exc}")
        return 1

    print(f"\nConnexion au courtier « {broker.name} »...")
    print(f"  terminal : {broker.terminal_path}")

    try:
        with mt5_session(broker) as api:
            version = api.version()
            terminal = api.terminal_info()
            compte = api.account_info()

            afficher(
                "Terminal",
                {
                    "Version": f"{version[0]} (build {version[1]}, {version[2]})",
                    "Société": terminal.company,
                    "Connecté au serveur": "oui" if terminal.connected else "NON",
                    "Trading algo autorisé": (
                        "oui"
                        if terminal.trade_allowed
                        else "NON — à activer avant l'étape 6 "
                        "(Outils > Options > Expert Advisors)"
                    ),
                    "Dossier de données": terminal.data_path,
                },
            )

            afficher(
                "Compte",
                {
                    "Numéro": compte.login,
                    "Nom": compte.name,
                    "Serveur": compte.server,
                    "Type de compte": TRADE_MODES.get(
                        compte.trade_mode, f"inconnu ({compte.trade_mode})"
                    ),
                    "Devise": compte.currency,
                    "Solde": f"{compte.balance:,.2f} {compte.currency}",
                    "Capital (equity)": f"{compte.equity:,.2f} {compte.currency}",
                    "Effet de levier": f"1:{compte.leverage}",
                    "Symboles disponibles": api.symbols_total(),
                },
            )

    except MT5Error as exc:
        print(f"\n[MT5] {exc}")
        return 1

    print("\nConnexion OK — session fermée proprement.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
