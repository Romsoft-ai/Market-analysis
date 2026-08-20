"""Étape 0, bloc 4 — À partir de quand FTMO sert-il ses propres cotations ?

Le bloc 3 a montré que sur GBPUSD, FTMO et IC Markets servent des prix
RIGOUREUSEMENT identiques en 2002, 2015 et 2016, mais différents à partir de 2018.
L'historique ancien est donc un jeu de données commun, pas les cotations propres du
courtier.

Ce script encadre la bascule : sonde annuelle, puis affinage mensuel entre les deux
bornes trouvées.

Pourquoi cette date compte : elle sépare la période où un backtest reflète
réellement l'exécution chez FTMO (cotations et spreads authentiques) de celle où il
ne mesure qu'un comportement générique — un jeu de données commun n'a en général
même pas de prix acheteur/vendeur, donc un spread implicitement nul. C'est la
frontière du protocole expérimental du mémoire.

Lecture seule.

Usage :
    python scripts/03_date_bascule.py            # GBPUSD (l'instrument concerné)
    python scripts/03_date_bascule.py XAUUSD
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

import pandas as pd

from marketlab.config import ConfigError, get_broker, load_instruments, symbol_for
from marketlab.data.explore import charger_m1
from marketlab.data.mt5_session import MT5Error, mt5_session

COURTIERS = ("ftmo", "icmarket")

# Au-delà de ce pourcentage de clôtures identiques, on considère que les deux
# courtiers servent la même donnée : deux sources indépendantes ne peuvent pas
# coïncider à ce point sur plus de mille bougies.
#
# À l'inverse, un taux de 10 à 30 % ne signifie PAS « à moitié identique » : deux
# sources indépendantes coïncident parfois par hasard à la cinquième décimale,
# surtout en période calme où le prix repasse par les mêmes valeurs.
SEUIL_IDENTIQUE = 99.0

ANNEE_DEBUT = 2014
JOUR_SONDE = 10  # milieu de mois, à l'écart des jours fériés de début d'année

#: En deçà de ce rapport entre le nombre de bougies des deux courtiers, on
#: considère qu'ils ne servent pas la même granularité. Mesuré sur XAUUSD :
#: avant 2019, IC Markets renvoie des bougies HORAIRES là où FTMO renvoie des
#: M1, soit 23 contre 1 366 sur une même journée.
RAPPORT_GRANULARITE = 0.5


def _sonde(annee: int, mois: int) -> datetime:
    """Jour de sondage, décalé au prochain jour ouvré.

    Le 10 du mois tombe un samedi ou un dimanche environ deux années sur sept.
    Le marché est alors fermé, la comparaison renvoie « pas de données », et
    cette absence se confond visuellement avec un manque d'historique : l'année
    disparaît du diagnostic sans qu'on sache pourquoi.
    """
    jour = datetime(annee, mois, JOUR_SONDE, tzinfo=UTC)
    while jour.weekday() >= 5:
        jour += timedelta(days=1)
    return jour


def collecter(instrument: str, jours: list[datetime]) -> dict:
    """Charge une journée de M1 par (courtier, date), chez les deux courtiers."""
    donnees: dict[tuple[str, datetime], pd.DataFrame] = {}
    for courtier in COURTIERS:
        with mt5_session(get_broker(courtier)) as api:
            symbole = symbol_for(instrument, courtier)
            for jour in jours:
                donnees[(courtier, jour)] = charger_m1(
                    api, symbole, jour, jour + timedelta(days=1)
                )
    return donnees


def taux_identique(a: pd.DataFrame, b: pd.DataFrame) -> tuple[int, float | None]:
    """Retourne (bougies comparables, % de clôtures identiques)."""
    if a.empty or b.empty:
        return 0, None
    communs = a.index.intersection(b.index)
    if len(communs) == 0:
        return 0, None
    egales = (a.loc[communs, "close"] == b.loc[communs, "close"]).sum()
    return len(communs), float(egales / len(communs) * 100)


def analyser(instrument: str, jours: list[datetime], titre: str) -> list[tuple]:
    """Compare les deux courtiers sur chaque jour et affiche le détail."""
    donnees = collecter(instrument, jours)

    print(f"\n  {titre}")
    print("  " + "-" * 62)
    print(f"  {'Date':<12} {'Communes':>9} {'Identiques':>11}   Source")

    resultats = []
    for jour in jours:
        a, b = donnees[("ftmo", jour)], donnees[("icmarket", jour)]
        n, pct = taux_identique(a, b)
        if n == 0 or pct is None:
            print(f"  {jour:%Y-%m-%d} {'—':>9} {'—':>11}   (marché fermé ou pas de données)")
            resultats.append((jour, None))
            continue

        # Granularités différentes : la comparaison n'a plus de sens. Une clôture
        # horaire et une clôture à la minute portant le même horodatage désignent
        # deux choses distinctes, et diffèrent donc MÊME si la source est la même.
        # Sans ce garde-fou, le script conclurait « cotations propres » là où il
        # n'a rien mesuré du tout.
        petit, grand = sorted((len(a), len(b)))
        if grand and petit / grand < RAPPORT_GRANULARITE:
            print(f"  {jour:%Y-%m-%d} {n:>9,} {'—':>11}   "
                  f"(granularités différentes : {len(a):,} vs {len(b):,})")
            resultats.append((jour, None))
            continue

        commune = pct >= SEUIL_IDENTIQUE
        etiquette = "COMMUNE" if commune else "propre à FTMO"
        print(f"  {jour:%Y-%m-%d} {n:>9,} {pct:>10.1f}%   {etiquette}")
        resultats.append((jour, commune))

    return resultats


def bornes(resultats: list[tuple]) -> tuple[datetime | None, datetime | None]:
    """Encadre la bascule : (dernière date commune, première date propre).

    Les dates sans données sont IGNORÉES, pas traitées comme des divergences.
    C'est le défaut de la première version de ce script : elle prenait la première
    divergence *détectée* puis affinait l'année précédente, sautant ainsi les
    années où le téléchargement avait échoué. Il faut encadrer, pas deviner.
    """
    derniere_commune = None
    for jour, commune in resultats:
        if commune is True:
            derniere_commune = jour
        elif commune is False:
            return derniere_commune, jour
    return derniere_commune, None


def mois_entre(debut: datetime, fin: datetime) -> list[datetime]:
    """Une sonde par mois, strictement entre `debut` et `fin`."""
    jours: list[datetime] = []
    annee, mois = debut.year, debut.month
    while True:
        mois += 1
        if mois > 12:
            annee, mois = annee + 1, 1
        sonde = _sonde(annee, mois)
        if sonde >= fin:
            return jours
        jours.append(sonde)


def main() -> int:
    try:
        instruments = load_instruments()["instruments"]
    except (ConfigError, KeyError) as exc:
        print(f"[CONFIGURATION] {exc}")
        return 1

    instrument = sys.argv[1] if len(sys.argv) > 1 else "GBPUSD"
    if instrument not in instruments:
        print(f"[ERREUR] Instrument inconnu : {instrument}")
        return 1

    annee_fin = datetime.now(UTC).year
    print(f"\n{'=' * 66}")
    print(f"  Recherche de la bascule des cotations — {instrument}")
    print("=" * 66)

    try:
        # Passe 1 : une sonde par année.
        annees = [_sonde(a, 6) for a in range(ANNEE_DEBUT, annee_fin + 1)]
        res = analyser(instrument, annees, "Passe 1 — une journée par année")
        commune, propre = bornes(res)

        if propre is None:
            print("\n  Aucune divergence : les données restent communes sur toute")
            print("  la période explorée. Élargir la recherche.")
            return 0
        if commune is None:
            # Deux causes très différentes se cachent derrière l'absence de
            # date commune, et les confondre mène à des conclusions opposées :
            #   - toutes les années mesurées divergent, la bascule est plus
            #     ancienne que la fenêtre explorée ;
            #   - rien n'était mesurable avant, il n'y a donc pas de bascule
            #     à chercher, elle précède le début de l'historique.
            indecidables = [
                jour for jour, statut in res if statut is None and jour < propre
            ]
            print()
            if indecidables:
                print(f'  Aucune comparaison possible avant {propre:%Y-%m} '
                      f'({len(indecidables)} année(s) sans données exploitables).')
                print('  La divergence est établie DÈS la première date mesurable :')
                print("  tout l'historique disponible porte donc les cotations du")
                print("  courtier, et il n'y a pas de bascule à chercher.")
                print()
                print(f'  Date à retenir : {propre:%Y-%m-%d}, ou le début de '
                      "l'historique si celui-ci est postérieur.")
            else:
                print(f'  Divergence dès {ANNEE_DEBUT} : la bascule est ANTÉRIEURE.')
                print('  Relancer avec une année de départ plus ancienne.')
            return 0

        # Passe 2 : affinage mensuel STRICTEMENT entre les deux bornes.
        print(f"\n  Bascule encadrée entre {commune:%Y-%m} (commune) "
              f"et {propre:%Y-%m} (propre).")
        mois = mois_entre(commune, propre)
        if mois:
            print(f"  Affinage sur {len(mois)} mois...")
            res_mois = analyser(instrument, mois, "Passe 2 — une journée par mois")
            commune2, propre2 = bornes(res_mois)
            commune = commune2 or commune
            propre = propre2 or propre

    except (ConfigError, MT5Error) as exc:
        print(f"\n[ÉCHEC] {exc}")
        return 1

    print(f"\n{'=' * 66}")
    print("  RÉSULTAT")
    print(f"\n  Dernière date à données COMMUNES : {commune:%Y-%m-%d}")
    print(f"  Première date à cotations FTMO   : {propre:%Y-%m-%d}")
    print("\n  La bascule se situe entre ces deux dates.")
    print(f"\n  Avant {commune:%Y-%m} : données génériques")
    print("          -> exploration, vérification que les figures existent")
    print(f"  Après {propre:%Y-%m} : cotations propres à FTMO")
    print("          -> tests décisifs, spreads réels, Challenge simulé")
    print("=" * 66 + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
