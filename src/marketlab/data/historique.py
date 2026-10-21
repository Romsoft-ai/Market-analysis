"""Récupération, mise en cache et agrégation de l'historique de bougies.

Principe posé à l'étape 0 : **seule la granularité la plus fine est collectée**
(M1), toutes les échelles supérieures sont recalculées ici. Cela garantit la
cohérence entre échelles et supprime une source classique de biais d'anticipation.

Le cache évite de retélécharger à chaque exécution. Un backtest se relance dix
fois par jour ; attendre le transfert à chaque fois rendrait le travail
impraticable.

ATTENTION AUX HORODATAGES. MetaTrader renvoie l'heure du SERVEUR (décalée de
2 ou 3 heures selon la période de l'année) sous forme d'horodatage Unix, comme si
le serveur était en UTC. Les dates manipulées ici sont donc en **heure serveur**,
pas en UTC réel. La conversion correcte doit tenir compte du changement d'heure ;
elle est traitée à l'étape 2. Appliquer un décalage constant serait faux la moitié
de l'année, ce qui est pire que de ne rien convertir : on garde donc l'heure
serveur, explicitement nommée.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from marketlab.config import DATA_DIR, ConfigError, get_broker, load_instruments, symbol_for
from marketlab.data.mt5_session import mt5_session

CACHE = DATA_DIR / "raw"

# Colonnes conservées parmi celles que renvoie MetaTrader.
_COLONNES = ["open", "high", "low", "close", "tick_volume", "spread"]

# Règles d'agrégation d'une bougie fine vers une bougie plus large.
_AGREGATION = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "tick_volume": "sum",
    "spread": "mean",
}

# Découpage des téléchargements : demander quatre ans d'un coup expose à un
# dépassement de mémoire côté terminal, sans moyen de suivre l'avancement.
_TRANCHE_JOURS = 180


def _nom_cache(instrument: str, courtier: str, debut: datetime, fin: datetime) -> Path:
    return CACHE / f"{instrument}_{courtier}_M1_{debut:%Y%m%d}_{fin:%Y%m%d}.parquet"


def telecharger_m1(
    instrument: str, courtier: str, debut: datetime, fin: datetime, bavard: bool = True
) -> pd.DataFrame:
    """Télécharge les bougies M1 depuis MetaTrader, par tranches successives."""
    symbole = symbol_for(instrument, courtier)
    morceaux: list[pd.DataFrame] = []

    with mt5_session(get_broker(courtier)) as api:
        if not api.symbol_select(symbole, True):
            raise ConfigError(f"Symbole {symbole!r} indisponible chez {courtier}")

        curseur = debut
        while curseur < fin:
            borne = min(curseur + timedelta(days=_TRANCHE_JOURS), fin)
            bougies = api.copy_rates_range(symbole, api.TIMEFRAME_M1, curseur, borne)

            if bougies is not None and len(bougies):
                morceau = pd.DataFrame(bougies)
                morceau["time"] = pd.to_datetime(morceau["time"], unit="s", utc=True)
                morceaux.append(morceau)
                if bavard:
                    print(f"    {curseur:%Y-%m} → {borne:%Y-%m} : {len(morceau):>7,} bougies")
            elif bavard:
                print(f"    {curseur:%Y-%m} → {borne:%Y-%m} :       0 bougie")

            curseur = borne

    if not morceaux:
        return pd.DataFrame(columns=_COLONNES)

    donnees = pd.concat(morceaux, ignore_index=True)
    donnees = donnees.set_index("time").sort_index()

    # Les tranches se recouvrent d'une bougie à la jointure.
    donnees = donnees[~donnees.index.duplicated(keep="first")]

    # On borne strictement : MetaTrader peut déborder de la fenêtre demandée.
    donnees = donnees[(donnees.index >= debut) & (donnees.index <= fin)]

    colonnes = [c for c in _COLONNES if c in donnees.columns]
    return donnees[colonnes]


def _cache_couvrant(
    instrument: str, courtier: str, debut: datetime, fin: datetime
) -> Path | None:
    """Cherche un fichier de cache dont la plage COUVRE celle demandée.

    Sans cette recherche, une demande du 3 janvier créerait un fichier distinct de
    celle du 1er janvier, alors que le second contient déjà le premier. On
    accumulerait des copies de dix-huit mégaoctets à chaque variation de dates.
    """
    if not CACHE.exists():
        return None

    for chemin in sorted(CACHE.glob(f"{instrument}_{courtier}_M1_*.parquet")):
        morceaux = chemin.stem.split("_")
        if len(morceaux) < 5:
            continue
        try:
            couvre_debut = datetime.strptime(morceaux[-2], "%Y%m%d").replace(tzinfo=UTC)
            couvre_fin = datetime.strptime(morceaux[-1], "%Y%m%d").replace(tzinfo=UTC)
        except ValueError:
            continue
        # Un jour de marge : les bornes du cache sont des dates, pas des instants.
        if couvre_debut <= debut and couvre_fin >= fin - timedelta(days=1):
            return chemin
    return None


def obtenir_m1(
    instrument: str,
    courtier: str,
    debut: datetime,
    fin: datetime,
    forcer: bool = False,
) -> pd.DataFrame:
    """Retourne les bougies M1, depuis le cache si possible.

    `forcer=True` ignore le cache et retélécharge.
    """
    chemin = _nom_cache(instrument, courtier, debut, fin)

    if not forcer:
        existant = _cache_couvrant(instrument, courtier, debut, fin)
        if existant is not None:
            print(f"  Cache trouvé : {existant.name}")
            donnees = pd.read_parquet(existant)
            return donnees[(donnees.index >= debut) & (donnees.index <= fin)]

    print(f"  Téléchargement de {instrument} M1 chez {courtier}...")
    donnees = telecharger_m1(instrument, courtier, debut, fin)

    if donnees.empty:
        raise ConfigError(
            f"Aucune bougie M1 récupérée pour {instrument} entre "
            f"{debut:%Y-%m-%d} et {fin:%Y-%m-%d}."
        )

    chemin.parent.mkdir(parents=True, exist_ok=True)
    donnees.to_parquet(chemin, compression="zstd")
    taille = chemin.stat().st_size / 1024 / 1024
    print(f"  Mis en cache : {chemin.name} ({taille:.1f} Mo, {len(donnees):,} bougies)")
    return donnees


def agreger(m1: pd.DataFrame, regle: str) -> pd.DataFrame:
    """Agrège des bougies M1 vers une échelle supérieure (« 15min », « 1h »...).

    `label="left"` et `closed="left"` reproduisent la convention MetaTrader : la
    bougie horodatée 10:00 couvre l'intervalle [10:00, 10:15[. Se tromper de
    convention décalerait toutes les décisions d'une bougie.
    """
    if m1.empty:
        return m1

    agregees = m1.resample(regle, label="left", closed="left").agg(_AGREGATION)

    # Les intervalles sans aucune bougie (nuit, week-end) produisent des lignes
    # vides : on les retire plutôt que de les propager.
    return agregees.dropna(subset=["open", "high", "low", "close"])


def obtenir(
    instrument: str,
    courtier: str,
    regle: str,
    debut: datetime,
    fin: datetime,
    forcer: bool = False,
) -> pd.DataFrame:
    """Point d'entrée : bougies agrégées à l'échelle demandée, cache compris."""
    m1 = obtenir_m1(instrument, courtier, debut, fin, forcer)
    agregees = agreger(m1, regle)
    print(f"  Agrégation en {regle} : {len(agregees):,} bougies")
    return agregees


def fin_de_la_derniere_bougie(parametres: dict) -> datetime:
    """Borne de fin à utiliser pour recharger les données d'une expérience enregistrée.

    Pour rejouer une expérience À L'IDENTIQUE, il faut recharger jusqu'à la même
    date que lors du lancement, `fin_demandee`. Ce n'est pas un détail : une fin
    demandée à minuit coupe la dernière bougie d'un marché ouvert à cette heure
    (GBPUSD) après sa première minute, mais laisse entière celle d'un marché fermé
    (l'or s'arrête à 23:59). Aucune borne déduite après coup ne retrouve les deux.

    Les expériences antérieures au 21 octobre 2026 n'enregistraient pas cette
    date. Pour elles, on recharge jusqu'à la dernière minute de la dernière bougie,
    ce qui peut différer du lancement sur cette seule bougie, donc au plus sur le
    trade soldé en fin de période.
    """
    if parametres.get("fin_demandee"):
        return pd.Timestamp(parametres["fin_demandee"]).to_pydatetime()
    fin = (
        pd.Timestamp(parametres["fin_reelle"])
        + pd.Timedelta(parametres["echelle"])
        - pd.Timedelta(minutes=1)
    )
    return fin.to_pydatetime()


def periode_fiable(instrument: str) -> datetime:
    """Date à partir de laquelle les cotations sont propres au courtier.

    Mesurée à l'étape 0 et consignée dans config/instruments.yaml. Backtester
    avant cette date reviendrait à mesurer un comportement générique, sans lien
    avec l'exécution réelle chez le courtier cible.
    """
    conf = load_instruments()["instruments"].get(instrument, {})
    date = conf.get("cotations_propres_depuis")
    if date is None:
        raise ConfigError(
            f"Aucune date de fiabilité connue pour {instrument}. "
            f"Lancer scripts/03_date_bascule.py pour la mesurer."
        )
    return datetime(date.year, date.month, date.day, tzinfo=UTC)
