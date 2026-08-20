"""Conversion de l'heure serveur MetaTrader en UTC réel, et sessions de marché.

LA RÈGLE, MESURÉE ET NON SUPPOSÉE

MetaTrader renvoie l'heure du serveur sous forme d'horodatage Unix, comme si le
serveur était en UTC. Il ne l'est pas. Sur quatre ans de données GBPUSD, la
dernière bougie du vendredi tombe à 23:54 et la première du lundi à 00:05,
**identiquement en hiver et en été**.

Or le marché des changes ferme le vendredi à 17:00 à New York. Une heure au cadran
constante toute l'année signifie donc que le serveur suit le changement d'heure
américain, avec un décalage fixe par rapport à New York :

    heure serveur = heure de New York + 7 heures

Soit UTC+2 en hiver et UTC+3 en été. Le +3 mesuré en direct le 19 août 2026 le
confirme.

POURQUOI NE PAS APPLIQUER UN DÉCALAGE CONSTANT

Retrancher trois heures serait juste six mois par an et faux les six autres. Une
erreur d'une heure suffit à décaler un filtre de session, à mal aligner une
annonce économique, ou à ranger une bougie dans la mauvaise journée de bourse.

LES SESSIONS

Elles sont définies en **heure locale de leur place**, jamais en UTC. Londres
ouvre à 08:00 heure de Londres toute l'année ; en UTC cela vaut 08:00 en hiver et
07:00 en été. Définir les sessions en heure locale et laisser la bibliothèque de
fuseaux faire la conversion évite de recoder soi-même les changements d'heure.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

import pandas as pd

#: Le serveur MetaTrader vit à l'heure de New York, décalée de sept heures.
FUSEAU_REFERENCE = ZoneInfo("America/New_York")
DECALAGE_REFERENCE_HEURES = 7

#: Sessions de marché, en heure LOCALE de leur place financière.
SESSIONS: dict[str, tuple[str, float, float]] = {
    "sydney": ("Australia/Sydney", 8.0, 17.0),
    "tokyo": ("Asia/Tokyo", 9.0, 18.0),
    "londres": ("Europe/London", 8.0, 17.0),
    "new_york": ("America/New_York", 8.0, 17.0),
}


def serveur_vers_utc(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Convertit un index d'heures serveur en UTC réel.

    L'index reçu porte l'étiquette UTC alors qu'il contient de l'heure serveur :
    c'est ainsi que MetaTrader le fournit. On retire d'abord cette étiquette
    trompeuse, on recule de sept heures pour obtenir l'heure au cadran de
    New York, puis on laisse le fuseau de New York résoudre le décalage réel de
    cette date-là.

    Les instants ambigus ou inexistants des changements d'heure tombent un
    dimanche matin, marché fermé : aucune bougie n'y figure. Les options passées
    à `tz_localize` ne servent donc qu'à ne pas lever d'exception.
    """
    if index.tz is None:
        cadran_serveur = index
    else:
        cadran_serveur = index.tz_localize(None)

    cadran_new_york = cadran_serveur - pd.Timedelta(hours=DECALAGE_REFERENCE_HEURES)
    localise = cadran_new_york.tz_localize(
        FUSEAU_REFERENCE, ambiguous=True, nonexistent="shift_forward"
    )
    return localise.tz_convert("UTC")


def convertir_bougies(bougies: pd.DataFrame) -> pd.DataFrame:
    """Retourne une copie des bougies dont l'index est en UTC réel."""
    converties = bougies.copy()
    converties.index = serveur_vers_utc(converties.index)
    converties.index.name = "temps_utc"
    return converties


def dans_session(index_utc: pd.DatetimeIndex, session: str) -> pd.Series:
    """Vrai pour chaque instant situé dans la session nommée, jours ouvrés seulement.

    La comparaison se fait en heure locale de la place : la bibliothèque de
    fuseaux applique le changement d'heure de l'année considérée, sans qu'on ait
    à le coder.
    """
    if session not in SESSIONS:
        connues = ", ".join(sorted(SESSIONS))
        raise ValueError(f"Session inconnue : {session!r}. Connues : {connues}")

    nom_fuseau, ouverture, fermeture = SESSIONS[session]
    local = index_utc.tz_convert(ZoneInfo(nom_fuseau))
    heures = local.hour + local.minute / 60

    ouvert = (heures >= ouverture) & (heures < fermeture)
    # Le marché des changes ignore les jours fériés locaux, mais pas le week-end.
    jour_ouvre = local.dayofweek < 5
    return pd.Series(ouvert & jour_ouvre, index=index_utc)


def dans_sessions(index_utc: pd.DatetimeIndex, sessions: list[str]) -> pd.Series:
    """Vrai si l'instant appartient à AU MOINS UNE des sessions demandées."""
    resultat = pd.Series(False, index=index_utc)
    for session in sessions:
        resultat = resultat | dans_session(index_utc, session)
    return resultat
