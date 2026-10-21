"""Bloc 4 — Essai réel de MT5Broker sur le compte démo.

Les tests automatiques vérifient la FORME des requêtes sur un faux terminal. Seul
le vrai serveur dit si elles sont acceptées : mode de remplissage, distance
minimale du stop, arrondis de prix et de volume. Cet essai fait un cycle complet,
celui que le robot répétera en live.

Sans option, il ne fait QUE LIRE : compte, contrat, cotation, positions ouvertes.
Avec --executer, il passe réellement les ordres, sur le volume minimal :

  1. ouvrir un achat, stop à 30 pips et objectif à 60 pips, posés avec l'ordre
  2. relire la position chez le courtier
  3. remonter le stop à 15 pips (ce que fait le stop suiveur)
  4. fermer la position

Usage :
    python scripts/40_essai_mt5.py                    # lecture seule
    python scripts/40_essai_mt5.py --executer         # cycle complet sur GBPUSD
    python scripts/40_essai_mt5.py --instrument XAUUSD --executer
"""

from __future__ import annotations

import argparse

from marketlab.brokers.base import Deplacement, Ordre, OrdreRefuse
from marketlab.brokers.mt5 import MT5Broker
from marketlab.config import ConfigError, courtier_par_defaut
from marketlab.data.mt5_session import MT5Error
from marketlab.strategies.base import Sens


def arguments() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--courtier", default=courtier_par_defaut())
    p.add_argument("--instrument", default="GBPUSD")
    p.add_argument("--executer", action="store_true", help="passer réellement les ordres")
    return p.parse_args()


def main() -> int:
    a = arguments()
    try:
        with MT5Broker.connecter(a.courtier) as broker:
            compte = broker.compte()
            spec = broker.specification(a.instrument)
            prix = broker.cotation(a.instrument, Sens.ACHAT)
            offre = broker.cotation(a.instrument, Sens.VENTE)

            print(f"\n  Compte    : {compte.capital:,.2f} {compte.devise}")
            print(f"  Contrat   : {a.instrument}  point={spec.point}  décimales={spec.decimales}  "
                  f"vol. min={spec.volume_min}  pas={spec.volume_pas}")
            print(f"  Pip       : {spec.valeur_pip}  →  {spec.valeur_pip_par_lot:,.4f} "
                  f"{compte.devise} par pip et par lot")
            print(f"  Cotation  : achat {prix}  vente {offre}")
            print(f"  Positions : {len(broker.positions(a.instrument))} ouverte(s) sur {a.instrument}")

            if not a.executer:
                print("\n  Lecture seule. Ajouter --executer pour le cycle d'ordres.\n")
                return 0
            if prix is None:
                print("\n  [ÉCHEC] Aucune cotation : le marché est-il ouvert ?\n")
                return 1

            pip = spec.valeur_pip
            print(f"\n  1. Ouverture d'un achat de {spec.volume_min} lot...")
            position = broker.ouvrir(Ordre(
                instrument=a.instrument, sens=Sens.ACHAT, volume=spec.volume_min,
                stop=prix - 30 * pip, objectif=prix + 60 * pip, raison="essai bloc 4",
            ))
            print(f"     ticket {position.identifiant}  entrée {position.entree}  "
                  f"stop {position.stop}  objectif {position.objectif}")

            relue = next(p for p in broker.positions(a.instrument)
                         if p.identifiant == position.identifiant)
            print(f"  2. Relue chez le courtier : stop {relue.stop}  objectif {relue.objectif}")

            nouveau = relue.entree - 15 * pip
            broker.modifier_stop(relue, nouveau, Deplacement.SUIVEUR)
            relue = next(p for p in broker.positions(a.instrument)
                         if p.identifiant == position.identifiant)
            print(f"  3. Stop remonté : {relue.stop}  (objectif toujours {relue.objectif})")

            broker.fermer(relue)
            restantes = [p for p in broker.positions(a.instrument)
                         if p.identifiant == position.identifiant]
            print(f"  4. Fermée : {'oui' if not restantes else 'NON, position encore ouverte'}\n")
            return 0 if not restantes else 1

    except (ConfigError, MT5Error, OrdreRefuse) as exc:
        print(f"\n  [ÉCHEC] {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
