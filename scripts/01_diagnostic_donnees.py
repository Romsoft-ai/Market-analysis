"""Étape 0, bloc 2 — Diagnostic des données disponibles chez chaque courtier.

Répond à la checklist de l'annexe F du plan :
  * quels sont les vrais noms des symboles ?
  * jusqu'où remonte l'historique M1 ?
  * les ticks sont-ils disponibles ?
  * les bougies récentes ont-elles des trous ?
  * de combien le serveur est-il décalé par rapport à UTC ?

Lecture seule : aucun ordre, aucune écriture chez le courtier.
Le rapport est affiché à l'écran ET écrit dans docs/etape0-diagnostic.md.

Usage :
    python scripts/01_diagnostic_donnees.py                 # tous les courtiers
    python scripts/01_diagnostic_donnees.py ftmo
    python scripts/01_diagnostic_donnees.py icmarket ftmo
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime

from marketlab.config import (
    PROJECT_ROOT,
    ConfigError,
    available_brokers,
    get_broker,
    load_instruments,
)
from marketlab.data.explore import (
    RapportInstrument,
    decalage_serveur_heures,
    diagnostiquer_instrument,
    lister_symboles,
)
from marketlab.data.mt5_session import MT5Error, mt5_session

RAPPORT = PROJECT_ROOT / "docs" / "etape0-diagnostic.md"


def _fmt(valeur: object, defaut: str = "—") -> str:
    return defaut if valeur is None else str(valeur)


def diagnostiquer_courtier(nom_courtier: str, instruments: dict) -> dict:
    """Ouvre une session et mesure tout ce qui est mesurable pour un courtier."""
    broker = get_broker(nom_courtier)
    resultat: dict = {"courtier": nom_courtier, "rapports": []}

    with mt5_session(broker) as api:
        compte = api.account_info()
        resultat["serveur"] = compte.server
        resultat["levier"] = compte.leverage
        resultat["devise"] = compte.currency
        resultat["nb_symboles"] = api.symbols_total()

        noms = lister_symboles(api)
        print(f"  {len(noms)} symboles exposés")

        for instrument, conf in instruments.items():
            motifs = conf.get("recherche", [instrument])
            print(f"  · {instrument} ...", end="", flush=True)
            rapport = diagnostiquer_instrument(api, instrument, motifs, noms)
            resultat["rapports"].append(rapport)
            print(f" {_fmt(rapport.symbole_retenu, 'INTROUVABLE')}")

        # Le décalage horaire se mesure sur un symbole liquide et présent.
        reference = next(
            (r.symbole_retenu for r in resultat["rapports"] if r.symbole_retenu), None
        )
        if reference:
            decalage, heure_tick = decalage_serveur_heures(api, reference)
            resultat["decalage_utc_h"] = decalage
            resultat["heure_dernier_tick"] = heure_tick
            resultat["symbole_reference"] = reference

    return resultat


def afficher(resultat: dict) -> None:
    """Affiche le résultat d'un courtier à l'écran."""
    print(f"\n{'=' * 78}")
    print(f"  {resultat['courtier'].upper()}  —  {resultat['serveur']}"
          f"  (levier 1:{resultat['levier']}, {resultat['devise']})")
    print("=" * 78)

    decalage = resultat.get("decalage_utc_h")
    if decalage is not None:
        signe = "+" if decalage >= 0 else ""
        print(f"\n  Heure serveur : UTC{signe}{decalage} h"
              f"   (dernier tick {resultat['heure_dernier_tick']:%Y-%m-%d %H:%M} UTC"
              f" sur {resultat['symbole_reference']})")

    for r in resultat["rapports"]:
        print(f"\n  ── {r.instrument} " + "─" * (68 - len(r.instrument)))

        if not r.candidats:
            print("     Aucun symbole correspondant chez ce courtier.")
            continue

        autres = r.candidats[1:6]
        print(f"     Symbole retenu   : {r.symbole_retenu}")
        if autres:
            suite = " ..." if len(r.candidats) > 6 else ""
            print(f"     Autres candidats : {', '.join(autres)}{suite}"
                  f"   ({len(r.candidats)} au total)")

        if r.infos and r.infos.erreur:
            print(f"     [!] {r.infos.erreur}")
            continue

        if r.infos:
            i = r.infos
            print(f"     Contrat          : {i.decimales} décimales, point {i.point}, "
                  f"taille {i.taille_contrat}, profit en {i.devise_profit}")
            print(f"     Volume           : min {i.volume_min}, pas {i.volume_pas}, "
                  f"max {i.volume_max}")
            print(f"     Spread actuel    : {i.spread_points} points")

        debut = r.debut_historique_m1
        print("     Historique M1    : depuis "
              + (f"{debut:%Y-%m-%d}" if debut else "INTROUVABLE"))

        q = r.qualite
        if q is None or q.erreur:
            print(f"     Qualité 7 jours  : {_fmt(q.erreur if q else None, 'non mesurée')}")
        else:
            print(f"     Qualité 7 jours  : {q.bougies:,} bougies "
                  f"({q.premiere:%d/%m %H:%M} → {q.derniere:%d/%m %H:%M} UTC)")
            print(f"                        {q.trous} trous > 5 min "
                  f"(plus grand : {q.plus_grand_trou_min:.0f} min), "
                  f"{q.incoherences_ohlc} incohérences OHLC, {q.doublons} doublons")

        ticks = r.nb_ticks_2j
        if ticks is None:
            print("     Ticks (2 jours)  : NON DISPONIBLES")
        else:
            print(f"     Ticks (2 jours)  : {ticks:,}")


def _ligne_md(r: RapportInstrument) -> str:
    """Construit une ligne de tableau markdown.

    Les cellules sont assemblées dans une liste plutôt que par concaténation de
    chaînes : une expression conditionnelle au milieu d'une concaténation
    implicite avale silencieusement la suite de la ligne.
    """
    q = r.qualite
    q_ok = q is not None and not q.erreur
    debut = r.debut_historique_m1

    cellules = [
        r.instrument,
        f"`{_fmt(r.symbole_retenu, 'introuvable')}`",
        _fmt(r.infos.decimales if r.infos else None),
        _fmt(r.infos.volume_min if r.infos else None),
        _fmt(r.infos.volume_pas if r.infos else None),
        _fmt(r.infos.spread_points if r.infos else None),
        f"{debut:%Y-%m-%d}" if debut else "**introuvable**",
        f"{q.bougies:,}" if q_ok else "—",
        f"{q.trous} ({q.plus_grand_trou_min:.0f} min)" if q_ok else "—",
        f"{q.incoherences_ohlc} / {q.doublons}" if q_ok else "—",
        f"{r.nb_ticks_2j:,}" if r.nb_ticks_2j is not None else "**non**",
    ]
    return "| " + " | ".join(cellules) + " |"


def ecrire_rapport(resultats: list[dict]) -> None:
    """Écrit le rapport markdown, livrable de l'étape 0."""
    lignes = [
        "# Étape 0 — Diagnostic des données",
        "",
        (
            f"*Généré le {datetime.now(UTC):%d/%m/%Y à %H:%M} UTC "
            "par `scripts/01_diagnostic_donnees.py`.*"
        ),
        "",
        (
            "> Document produit automatiquement. Il répond à la checklist de "
            "l'annexe F du plan v2."
        ),
        "",
    ]

    for res in resultats:
        decalage = res.get("decalage_utc_h")
        signe = "+" if (decalage or 0) >= 0 else ""
        lignes += [
            "---",
            "",
            f"## {res['courtier'].upper()} — `{res['serveur']}`",
            "",
            f"- **Levier** : 1:{res['levier']}  ·  **Devise** : {res['devise']}",
            f"- **Symboles exposés** : {res['nb_symboles']}",
            "- **Heure serveur** : "
            + (f"UTC{signe}{decalage} h" if decalage is not None else "non mesurée"),
            "",
            (
                "| Instrument | Symbole | Déc. | Vol. min | Pas | Spread "
                "| Historique M1 | Bougies 7 j | Trous (max) "
                "| Incoh. / Doubl. | Ticks 2 j |"
            ),
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        lignes += [_ligne_md(r) for r in res["rapports"]]
        lignes.append("")

    lignes += [
        "---",
        "",
        "## Conclusions à tirer",
        "",
        "- [ ] Reporter les **noms de symboles réels** dans `config/instruments.yaml`",
        "- [ ] Décider de la **profondeur d'historique** retenue pour les backtests",
        "- [ ] Trancher l'usage des **ticks** selon leur disponibilité réelle",
        (
            "- [ ] Documenter le **décalage horaire** de chaque serveur "
            "et le normaliser en UTC à l'ingestion"
        ),
        "",
    ]

    RAPPORT.parent.mkdir(parents=True, exist_ok=True)
    RAPPORT.write_text("\n".join(lignes), encoding="utf-8")


def main() -> int:
    courtiers = sys.argv[1:] or available_brokers()
    if not courtiers:
        print("[CONFIGURATION] Aucun courtier trouvé dans .env.")
        return 1

    try:
        instruments = load_instruments()["instruments"]
    except (ConfigError, KeyError) as exc:
        print(f"[CONFIGURATION] {exc}")
        return 1

    resultats = []
    for nom in courtiers:
        print(f"\nDiagnostic « {nom} »...")
        try:
            resultats.append(diagnostiquer_courtier(nom, instruments))
        except (ConfigError, MT5Error) as exc:
            print(f"  [ÉCHEC] {exc}")

    if not resultats:
        return 1

    for res in resultats:
        afficher(res)

    ecrire_rapport(resultats)
    print(f"\n\nRapport écrit dans {RAPPORT.relative_to(PROJECT_ROOT)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
