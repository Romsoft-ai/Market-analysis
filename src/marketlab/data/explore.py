"""Exploration, en LECTURE SEULE, de ce qu'un courtier MT5 met à disposition.

Ce module ne passe aucun ordre et n'écrit rien chez le courtier. Il répond aux
questions de l'étape 0 :

* quels sont les vrais noms des symboles ?
* quelles sont les caractéristiques de chaque contrat ?
* jusqu'où remonte l'historique en M1 ?
* les bougies récentes ont-elles des trous ?
* les ticks sont-ils disponibles ?
* de combien le serveur est-il décalé par rapport à UTC ?

Précaution de méthode : on ne demande JAMAIS tout l'historique d'un coup. Le
terminal déclencherait un téléchargement de plusieurs dizaines de minutes avant
de répondre. On sonde de petites fenêtres.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pandas as pd

# Fenêtre de sondage : quelques jours en milieu de mois, pour tomber sur des
# jours ouvrés même si le 1er est férié.
_SONDE_JOURS = 4
_SONDE_JOUR_DEBUT = 10

# MT5 télécharge l'historique manquant en tâche de fond : on laisse une chance
# à la donnée d'arriver avant de conclure qu'elle n'existe pas.
_ESSAIS = 3
_ATTENTE_S = 2.0


# ---------------------------------------------------------------------------
# Recherche de symboles
# ---------------------------------------------------------------------------


def lister_symboles(api) -> list[str]:
    """Retourne tous les noms de symboles exposés par le courtier."""
    symboles = api.symbols_get()
    return sorted(s.name for s in (symboles or ()))


def chercher_symboles(noms: list[str], motifs: list[str]) -> list[str]:
    """Filtre `noms` sur les symboles contenant l'un des `motifs`.

    Le tri place les noms les plus courts d'abord : « GBPUSD » avant
    « GBPUSD.pro », donc le candidat le plus probable en tête.
    """
    motifs_maj = [m.upper() for m in motifs]
    trouves = {n for n in noms if any(m in n.upper() for m in motifs_maj)}
    return sorted(trouves, key=lambda n: (len(n), n))


# ---------------------------------------------------------------------------
# Caractéristiques d'un symbole
# ---------------------------------------------------------------------------


@dataclass
class InfosSymbole:
    """Ce qu'il faut savoir d'un symbole pour pouvoir le trader."""

    nom: str
    decimales: int | None = None
    point: float | None = None
    spread_points: int | None = None
    taille_contrat: float | None = None
    volume_min: float | None = None
    volume_max: float | None = None
    volume_pas: float | None = None
    devise_profit: str | None = None
    erreur: str | None = None


def decrire_symbole(api, symbole: str) -> InfosSymbole:
    """Lit les caractéristiques d'un symbole, en le rendant visible au besoin.

    Un symbole absent du « Market Watch » ne renvoie pas de données : il faut
    d'abord appeler ``symbol_select``.
    """
    if not api.symbol_select(symbole, True):
        return InfosSymbole(nom=symbole, erreur="impossible de sélectionner le symbole")

    info = api.symbol_info(symbole)
    if info is None:
        return InfosSymbole(nom=symbole, erreur="symbol_info() n'a rien renvoyé")

    return InfosSymbole(
        nom=symbole,
        decimales=info.digits,
        point=info.point,
        spread_points=info.spread,
        taille_contrat=info.trade_contract_size,
        volume_min=info.volume_min,
        volume_max=info.volume_max,
        volume_pas=info.volume_step,
        devise_profit=info.currency_profit,
    )


# ---------------------------------------------------------------------------
# Profondeur d'historique
# ---------------------------------------------------------------------------


def _horodatages(
    api, symbole: str, debut: datetime, fin: datetime, essais: int = _ESSAIS
) -> pd.DatetimeIndex:
    """Horodatages des bougies M1 renvoyées pour la fenêtre [debut, fin].

    Pourquoi plusieurs essais : quand la période demandée n'est pas encore dans
    le cache local, MT5 lance le téléchargement EN TÂCHE DE FOND et répond
    immédiatement avec ce qu'il a. Le premier appel revient donc souvent vide,
    et le suivant a les données. Sans réessai, on conclurait à tort à l'absence
    d'historique.

    AUCUN filtrage ici : on retourne ce que MT5 a renvoyé, y compris des bougies
    situées hors de la fenêtre demandée.
    """
    for tentative in range(essais):
        bougies = api.copy_rates_range(symbole, api.TIMEFRAME_M1, debut, fin)
        if bougies is not None and len(bougies):
            horodatages = pd.to_datetime(pd.DataFrame(bougies)["time"], unit="s", utc=True)
            return pd.DatetimeIndex(horodatages)
        if tentative < essais - 1:
            time.sleep(_ATTENTE_S)
    return pd.DatetimeIndex([])


def _a_des_bougies(api, symbole: str, debut: datetime, fin: datetime) -> bool:
    """Vrai seulement si des bougies tombent VRAIMENT dans la fenêtre demandée.

    Piège à connaître : interrogé sur une période antérieure à l'historique
    disponible, MT5 ne renvoie pas un résultat vide — il renvoie la bougie la
    plus PROCHE. Se contenter de « la réponse n'est pas vide » ferait croire
    qu'on dispose de vingt ans d'historique sur un instrument créé l'an dernier.
    """
    t = _horodatages(api, symbole, debut, fin)
    return bool(len(t)) and bool(((t >= debut) & (t <= fin)).any())


def profondeur_m1(api, symbole: str, annees_max: int = 25) -> datetime | None:
    """Retourne la date de la première bougie M1 disponible, ou None.

    Méthode principale, en un seul appel : on interroge une fenêtre volontairement
    très ancienne. Puisque MT5 renvoie alors la bougie la plus proche, celle-ci EST
    le début de l'historique. On vérifie ensuite la cohérence du résultat, et on
    garde un balayage année par année comme repli.
    """
    tres_ancien = datetime(1990, 1, 1, tzinfo=UTC)
    t = _horodatages(api, symbole, tres_ancien, tres_ancien + timedelta(days=_SONDE_JOURS))
    if len(t):
        candidat = t.min().to_pydatetime()
        # Cohérence : la sonde ancienne ne doit pas renvoyer une date antérieure
        # à la fenêtre interrogée, sinon l'hypothèse ne tient pas.
        if candidat > tres_ancien:
            return candidat

    # Repli : balayage annuel, avec vérification que les bougies sont bien dans
    # la fenêtre (voir _a_des_bougies).
    annee_courante = datetime.now(UTC).year
    for annee in range(annee_courante - annees_max, annee_courante + 1):
        for mois in (3, 9):
            debut = datetime(annee, mois, _SONDE_JOUR_DEBUT, tzinfo=UTC)
            fin = debut + timedelta(days=_SONDE_JOURS)
            if _a_des_bougies(api, symbole, debut, fin):
                t = _horodatages(api, symbole, debut, fin)
                dans = t[(t >= debut) & (t <= fin)]
                return dans.min().to_pydatetime()
    return None


# ---------------------------------------------------------------------------
# Qualité des bougies récentes
# ---------------------------------------------------------------------------


@dataclass
class QualiteRecente:
    """Premier aperçu de la véracité des données, sur une fenêtre courte."""

    bougies: int = 0
    premiere: datetime | None = None
    derniere: datetime | None = None
    trous: int = 0
    plus_grand_trou_min: float = 0.0
    incoherences_ohlc: int = 0
    doublons: int = 0
    erreur: str | None = None


def qualite_m1_recente(api, symbole: str, jours: int = 7) -> QualiteRecente:
    """Compte les bougies M1 des derniers jours et cherche les anomalies.

    Un « trou » est un écart de plus de 5 minutes entre deux bougies
    consécutives. Les week-ends en produisent forcément un : c'est normal, et
    c'est justement pourquoi on rapporte le nombre ET la taille du plus grand.
    """
    fin = datetime.now(UTC)
    debut = fin - timedelta(days=jours)

    bougies = api.copy_rates_range(symbole, api.TIMEFRAME_M1, debut, fin)
    if bougies is None or len(bougies) == 0:
        return QualiteRecente(erreur="aucune bougie M1 sur la période")

    df = pd.DataFrame(bougies)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.sort_values("time")

    ecarts = df["time"].diff().dt.total_seconds().div(60)
    trous = ecarts[ecarts > 5]

    incoherences = (
        (df["low"] > df["open"])
        | (df["low"] > df["close"])
        | (df["high"] < df["open"])
        | (df["high"] < df["close"])
        | (df["low"] > df["high"])
    ).sum()

    return QualiteRecente(
        bougies=len(df),
        premiere=df["time"].iloc[0].to_pydatetime(),
        derniere=df["time"].iloc[-1].to_pydatetime(),
        trous=len(trous),
        plus_grand_trou_min=float(trous.max()) if len(trous) else 0.0,
        incoherences_ohlc=int(incoherences),
        doublons=int(df["time"].duplicated().sum()),
    )


# ---------------------------------------------------------------------------
# Ticks
# ---------------------------------------------------------------------------


def ticks_disponibles(api, symbole: str, jours: int = 2) -> int | None:
    """Compte les ticks sur une courte fenêtre, sans déclencher de gros transfert.

    Retourne None si l'appel échoue (ticks non servis par ce courtier).
    """
    fin = datetime.now(UTC)
    debut = fin - timedelta(days=jours)
    ticks = api.copy_ticks_range(symbole, debut, fin, api.COPY_TICKS_ALL)
    return None if ticks is None else len(ticks)


# ---------------------------------------------------------------------------
# Fuseau horaire du serveur
# ---------------------------------------------------------------------------


def decalage_serveur_heures(api, symbole: str) -> tuple[float | None, datetime | None]:
    """Estime le décalage entre l'heure du serveur et UTC.

    MT5 renvoie l'heure du serveur sous forme d'horodatage Unix *comme si* le
    serveur était en UTC. La différence avec l'heure UTC réelle donne donc le
    décalage. Piège : marché fermé, le dernier tick est ancien et la mesure est
    fausse — d'où le renvoi de l'heure du tick, pour pouvoir juger.
    """
    tick = api.symbol_info_tick(symbole)
    if tick is None or not tick.time:
        return None, None

    heure_tick = datetime.fromtimestamp(tick.time, tz=UTC)
    maintenant = datetime.now(UTC)
    decalage = round((heure_tick - maintenant).total_seconds() / 3600, 1)
    return decalage, heure_tick


# ---------------------------------------------------------------------------
# Assemblage
# ---------------------------------------------------------------------------


@dataclass
class RapportInstrument:
    """Tout ce que le diagnostic a appris sur un instrument chez un courtier."""

    instrument: str
    candidats: list[str] = field(default_factory=list)
    symbole_retenu: str | None = None
    infos: InfosSymbole | None = None
    debut_historique_m1: datetime | None = None
    qualite: QualiteRecente | None = None
    nb_ticks_2j: int | None = None


def diagnostiquer_instrument(
    api, instrument: str, motifs: list[str], noms_disponibles: list[str]
) -> RapportInstrument:
    """Enchaîne toutes les mesures pour un instrument."""
    rapport = RapportInstrument(instrument=instrument)
    rapport.candidats = chercher_symboles(noms_disponibles, motifs)

    if not rapport.candidats:
        return rapport

    # Le meilleur candidat est le nom le plus court (voir chercher_symboles).
    symbole = rapport.candidats[0]
    rapport.symbole_retenu = symbole
    rapport.infos = decrire_symbole(api, symbole)

    if rapport.infos.erreur:
        return rapport

    rapport.debut_historique_m1 = profondeur_m1(api, symbole)
    rapport.qualite = qualite_m1_recente(api, symbole)
    rapport.nb_ticks_2j = ticks_disponibles(api, symbole)
    return rapport

# ---------------------------------------------------------------------------
# Chargement de bougies (réutilisé dès l'étape 1)
# ---------------------------------------------------------------------------


def charger_m1(api, symbole: str, debut: datetime, fin: datetime) -> pd.DataFrame:
    """Charge les bougies M1 de [debut, fin] dans un DataFrame indexé par le temps.

    Les bougies hors de la fenêtre demandée sont écartées : rappel que MT5 renvoie
    la bougie la plus proche quand la période précède l'historique disponible.
    Les horodatages sont en heure SERVEUR (UTC+3 chez nos deux courtiers) ; la
    normalisation en UTC réel se fera à l'ingestion, à l'étape 2.
    """
    api.symbol_select(symbole, True)
    horodatages = _horodatages(api, symbole, debut, fin)
    if not len(horodatages):
        return pd.DataFrame()

    bougies = api.copy_rates_range(symbole, api.TIMEFRAME_M1, debut, fin)
    df = pd.DataFrame(bougies)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df[(df["time"] >= debut) & (df["time"] <= fin)]
    return df.set_index("time").sort_index()
