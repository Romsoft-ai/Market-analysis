"""Étape 1, bloc 2 — Lancer une simulation historique et l'enregistrer.

Enchaîne les opérations qui transforment un historique en résultat mesuré :

  1. récupérer les bougies M1 (téléchargées une fois, puis relues depuis le cache)
  2. les agréger à l'échelle de décision
  3. restreindre la période à celle où les cotations sont propres au courtier
  4. MESURER le spread réel sur la période, au lieu de le supposer
  5. dérouler la stratégie
  6. ENREGISTRER l'expérience : conditions, résultats et trades conservés ensemble

Les points 4 et 6 sont les garde-fous. Le premier supprime une hypothèse
arbitraire du calcul ; le second garantit qu'un chiffre reste interprétable des
semaines plus tard, puisqu'il ne quitte jamais ses conditions.

Le break-even est DÉSACTIVÉ par défaut : un trade se solde par son objectif ou par
son stop. L'option existe encore pour pouvoir refaire la comparaison.

Usage :
    python scripts/20_backtest.py
    python scripts/20_backtest.py --instrument XAUUSD --debut 2021-01-01
    python scripts/20_backtest.py --avec-break-even --note "comparaison BE"
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime

from marketlab.backtest import journal
from marketlab.backtest.metriques import calculer, formater
from marketlab.backtest.moteur import Backtest
from marketlab.config import ConfigError, courtier_par_defaut, load_instruments
from marketlab.data.historique import obtenir, periode_fiable
from marketlab.data.mt5_session import MT5Error
from marketlab.strategies.registre import obtenir as strategie_du_catalogue
from marketlab.strategies.registre import strategies


def date(texte: str) -> datetime:
    return datetime.strptime(texte, "%Y-%m-%d").replace(tzinfo=UTC)


def arguments() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    catalogue = strategies()
    p.add_argument(
        "--strategie",
        choices=list(catalogue),
        default="B1",
        help=" ; ".join(f"{code} = {classe.nom}" for code, classe in catalogue.items()),
    )
    p.add_argument("--instrument", default="GBPUSD")
    p.add_argument("--courtier", default=courtier_par_defaut(), help="DEFAULT_BROKER du .env")
    p.add_argument("--echelle", default="15min", help="échelle de décision")
    p.add_argument("--debut", type=date, default=date("2022-01-01"))
    p.add_argument("--fin", type=date, default=date("2025-12-31"))
    p.add_argument("--capital", type=float, default=100_000.0)
    p.add_argument("--risque", type=float, default=0.002, help="fraction par trade")
    p.add_argument("--avec-break-even", action="store_true")
    p.add_argument(
        "--positions",
        type=int,
        default=1,
        help="positions ouvertes simultanément ; 0 lève la limite "
        "(attention : le risque de 0,2 %% s'applique à CHACUNE)",
    )
    p.add_argument("--forcer", action="store_true", help="ignorer le cache de données")
    p.add_argument(
        "--nature",
        choices=[journal.Nature.PRE_ENREGISTREE, journal.Nature.EXPLORATION],
        default=journal.Nature.EXPLORATION,
        help="« pré-enregistrée » si la question était posée AVANT de voir le résultat",
    )
    p.add_argument("--note", default="", help="ce que cet essai cherche à savoir")
    return p.parse_args()


def main() -> int:
    a = arguments()

    try:
        conf = load_instruments()["instruments"][a.instrument]
    except (ConfigError, KeyError):
        print(f"[ERREUR] Instrument inconnu : {a.instrument}")
        return 1

    print(f"\n{'=' * 62}")
    print(f"  BACKTEST  {a.instrument}  {a.echelle}  chez {a.courtier}")
    print("=" * 62)

    # --- Période exploitable -------------------------------------------------
    fiable = periode_fiable(a.instrument)
    debut = max(a.debut, fiable)
    if debut > a.debut:
        print(f"\n  Début repoussé à {debut:%Y-%m-%d} : avant cette date, les")
        print("  cotations ne sont pas propres au courtier (mesuré à l'étape 0).")

    # --- Données -------------------------------------------------------------
    print(f"\n  Données {debut:%Y-%m-%d} → {a.fin:%Y-%m-%d}")
    try:
        bougies = obtenir(a.instrument, a.courtier, a.echelle, debut, a.fin, a.forcer)
    except (ConfigError, MT5Error) as exc:
        print(f"\n[ÉCHEC] {exc}")
        return 1

    if bougies.empty:
        print("\n[ÉCHEC] Aucune bougie sur la période.")
        return 1

    print(f"  Période réelle : {bougies.index[0]:%Y-%m-%d} → {bougies.index[-1]:%Y-%m-%d}")
    print("  (horodatages en heure serveur, décalée de 2 à 3 h par rapport à UTC)")

    # --- Spread mesuré, non supposé -----------------------------------------
    point = float(conf["point"])
    if "spread" in bougies.columns:
        spread_points = float(bougies["spread"].median())
        source = "médiane mesurée sur la période"
    else:
        spread_points = 3.0
        source = "valeur de repli, colonne absente"
    spread = spread_points * point
    print(f"\n  Spread : {spread_points:.1f} points ({source})")

    # --- Simulation ----------------------------------------------------------
    strategie = strategie_du_catalogue(a.strategie)()
    break_even = 1.0 if a.avec_break_even else None
    # 0 en ligne de commande signifie « pas de limite » : plus lisible qu'une
    # chaîne à interpréter, et impossible à confondre avec un nombre valide.
    positions_max = None if a.positions <= 0 else a.positions
    moteur = Backtest(
        strategie=strategie,
        spread=spread,
        capital_initial=a.capital,
        risque_par_trade=a.risque,
        break_even_a=break_even,
        valeur_pip=float(conf["pip"]),
        valeur_pip_par_lot=float(conf["taille_contrat"]) * float(conf["pip"]),
        volume_min=float(conf["volume_min"]),
        volume_pas=float(conf["volume_pas"]),
        positions_max=positions_max,
    )

    print(f"\n  Stratégie : {strategie.nom}")
    print(f"  Réglages  : {strategie.parametres}")
    print(f"  Risque    : {a.risque * 100:.2f} % du capital par trade")
    print(f"  Break-even: {'à +1 R' if break_even else 'désactivé (objectif ou stop)'}")
    if positions_max is None:
        print("  Positions : SANS LIMITE (chaque signal est pris)")
        print(f"  Exposition: non bornée, {a.risque * 100:.2f} % par position ouverte")
    else:
        print(f"  Positions : {positions_max} à la fois")
    print(f"\n  Simulation sur {len(bougies):,} bougies...")

    resultat = moteur.executer(bougies)
    mesures = calculer(resultat)

    titre = (
        f"  {strategie.nom}  |  {a.instrument} {a.echelle}  |  "
        f"{bougies.index[0]:%Y-%m} → {bougies.index[-1]:%Y-%m}"
    )
    print(formater(mesures, titre))

    # --- Enregistrement de l'expérience --------------------------------------
    # Tout ce qui a influencé le résultat doit figurer ici, y compris ce qui
    # semble évident aujourd'hui : dans six semaines, plus rien ne l'est.
    parametres = {
        "instrument": a.instrument,
        "courtier": a.courtier,
        "echelle": a.echelle,
        "debut_demande": a.debut.date(),
        "debut_reel": bougies.index[0],
        "fin_reelle": bougies.index[-1],
        "bougies": len(bougies),
        "fuseau_horodatages": "heure serveur (UTC+2 ou +3 selon la saison)",
        "strategie": strategie.nom,
        "strategie_code": strategie.code,
        "strategie_classe": type(strategie).__name__,
        **strategie.parametres_journal(),
        "point": point,
        "pip": float(conf["pip"]),
        "taille_contrat": float(conf["taille_contrat"]),
        "valeur_pip_par_lot": float(conf["taille_contrat"]) * float(conf["pip"]),
        "volume_min": float(conf["volume_min"]),
        "volume_pas": float(conf["volume_pas"]),
        "spread_points": spread_points,
        "spread_prix": spread,
        "capital_initial": a.capital,
        "risque_par_trade": a.risque,
        "break_even_a": break_even,
        # Absence de valeur = absence de limite. Une sentinelle numérique serait
        # un piège : « 0 position simultanée » se lirait comme le contraire de
        # ce qu'elle veut dire, et une chaîne casserait le type de la colonne
        # dans le registre, où les autres lignes portent un entier.
        "positions_simultanees": positions_max,
        "convention_intra_bougie": "pessimiste (stop avant objectif)",
        "moment_entree": "ouverture de la bougie suivante",
    }

    experience = journal.enregistrer(
        parametres=parametres,
        metriques=asdict(mesures),
        trades=resultat.en_tableau(),
        nature=a.nature,
        note=a.note,
    )

    print(f"  Expérience enregistrée : {experience.identifiant}")
    print(f"  Nature   : {experience.nature}")
    print(f"  Code     : {experience.version_code}", end="")
    print("  (modifications non validées)" if experience.code_modifie else "")
    print(f"  Empreinte: {experience.empreinte}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
