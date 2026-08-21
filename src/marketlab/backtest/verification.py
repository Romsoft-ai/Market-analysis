"""Rejouer les règles d'entrée sur un trade déjà exécuté.

À quoi ça sert. Les tests du moteur vérifient qu'il fait ce qui a été codé ; ils ne
peuvent pas vérifier que le résultat correspond aux règles telles qu'on les a
énoncées. Ce module reprend chaque trade, retrouve la bougie qui l'a déclenché, et
confronte chaque condition à ses valeurs réelles.

Deux usages :

* dans l'inspecteur, pour afficher la vérification à côté du graphique ;
* en test automatique, sur un échantillon de trades réels, pour détecter une
  divergence entre le moteur et les règles.

Ce module ne dépend d'aucune interface : il ne fait que lire et comparer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import pandas as pd

from marketlab.strategies.confluence import (
    STRATEGIES,
    ConfluenceZero,
    FiltreSession,
)

# Tolérance de comparaison des prix. Les flottants issus d'agrégations ne sont
# jamais rigoureusement égaux ; un millionième de pip suffit largement.
_TOLERANCE = 1e-9


def _classe_strategie(parametres: dict[str, Any]) -> type | None:
    """Retrouve la classe de stratégie à partir du code enregistré.

    On interroge le registre plutôt qu'une liste de codes écrite à la main.
    Avec une liste, ajouter une variante obligerait à se souvenir de venir
    modifier ce fichier, et l'oubli ferait sauter un contrôle en silence :
    la vérification annoncerait « tout est conforme » sans avoir rien vérifié.
    """
    code = str(parametres.get("strategie_code", "")).lower()
    for nom, classe in STRATEGIES.items():
        if nom.lower() == code:
            return classe
    return None


def decimales(parametres: dict[str, Any]) -> int:
    """Nombre de décimales d'affichage d'un prix, déduit de la valeur du point.

    Un point de 0,00001 donne cinq décimales, un point de 0,01 en donne deux.
    Sans cela, un prix de l'or s'afficherait « 2650.00000 » et une paire de
    devises serait arrondie à « 1.23 », ce qui masquerait justement les écarts
    qu'on cherche à contrôler.
    """
    point = float(parametres.get("point", 0.00001))
    if point <= 0:
        return 5
    return max(0, round(-math.log10(point)))


@dataclass
class Controle:
    """Une condition d'entrée, avec ce qui était attendu et ce qui est constaté.

    `cle` identifie la NATURE du contrôle, indépendamment de sa position dans la
    liste. Les contrôles conditionnels font varier cette position d'une stratégie
    à l'autre : nommer les colonnes par rang ferait afficher le libellé d'une
    règle à la place d'une autre, et un rapport de conformité qui désigne la
    mauvaise règle est pire qu'un rapport absent.
    """

    cle: str
    condition: str
    attendu: str
    constate: str
    valide: bool


def bougie_de_signal(
    preparees: pd.DataFrame, date_entree: pd.Timestamp
) -> pd.Series | None:
    """Retrouve la bougie qui a produit le signal.

    L'entrée se fait à l'ouverture de la bougie suivante : la bougie de signal est
    donc la dernière **strictement antérieure** à la date d'entrée.
    """
    anterieures = preparees.index[preparees.index < date_entree]
    if not len(anterieures):
        return None
    return preparees.loc[anterieures[-1]]


def verifier(
    signal: pd.Series, trade: pd.Series, parametres: dict[str, Any]
) -> list[Controle]:
    """Rejoue les cinq règles sur la bougie de signal."""
    achat = trade["sens"] == "achat"
    d = decimales(parametres)

    plancher = float(parametres.get("strat_rsi_plancher", 50.0))
    plafond = float(parametres.get("strat_rsi_plafond", 70.0))
    if not achat:
        # La fenêtre RSI d'une vente est le miroir de celle d'un achat.
        plancher, plafond = 100 - plafond, 100 - plancher

    cloture = float(signal["close"])
    valeur_ema = float(signal["ema"])
    valeur_rsi = float(signal["rsi"])
    niveau_stop = float(signal["creux"] if achat else signal["sommet"])
    nb_bougies = parametres.get("strat_bougies_stop", 10)

    controles = [
        Controle(
            cle="tendance",
            condition="Tendance : clôture du bon côté de l'EMA",
            attendu="clôture > EMA" if achat else "clôture < EMA",
            constate=f"{cloture:.{d}f} vs {valeur_ema:.{d}f}",
            valide=(cloture > valeur_ema) if achat else (cloture < valeur_ema),
        ),
        Controle(
            cle="croisement",
            condition="Déclencheur : croisement du MACD",
            attendu="vers le haut" if achat else "vers le bas",
            constate=f"MACD {signal['macd']:.6f} / signal {signal['macd_signal']:.6f}",
            valide=bool(signal["croise_haut"] if achat else signal["croise_bas"]),
        ),
        Controle(
            cle="rsi",
            condition="Momentum : RSI dans la fenêtre",
            attendu=f"{plancher:.0f} < RSI < {plafond:.0f}",
            constate=f"{valeur_rsi:.1f}",
            valide=plancher < valeur_rsi < plafond,
        ),
        Controle(
            cle="stop",
            condition=f"Stop : extrême des {nb_bougies} dernières bougies",
            attendu=f"{niveau_stop:.{d}f}",
            constate=f"{float(trade['stop_initial']):.{d}f}",
            valide=abs(niveau_stop - float(trade["stop_initial"])) < _TOLERANCE,
        ),
        Controle(
            cle="entree",
            condition="Entrée : à l'ouverture de la bougie suivante",
            attendu="signal en N, entrée en N+1",
            constate=(
                f"signal {signal.name:%d/%m %H:%M} → "
                f"entrée {pd.Timestamp(trade['date_entree']):%d/%m %H:%M}"
            ),
            valide=signal.name < pd.Timestamp(trade["date_entree"]),
        ),
    ]

    # Condition introduite par B1v2 : le croisement doit se produire du bon côté
    # de zéro. Elle n'existe pas dans B1, on ne l'affiche donc que si la stratégie
    # enregistrée en hérite. Toute variante future de B1v2 la reçoit d'office.
    classe = _classe_strategie(parametres)
    if classe is not None and issubclass(classe, ConfluenceZero):
        valeur_macd = float(signal["macd"])
        controles.append(
            Controle(
                cle="ligne_zero",
            condition="Position : croisement du bon côté de zéro",
                attendu="MACD < 0" if achat else "MACD > 0",
                constate=f"{valeur_macd:+.6f}",
                valide=(valeur_macd < 0) if achat else (valeur_macd > 0),
            )
        )

    # Le contrôle horaire se rattache à la BRIQUE de session, pas à une classe
    # particulière : B1v3 la combine avec la ligne zéro, B1v5 sans. Viser
    # ConfluenceZeroSession ferait sauter le contrôle sur B1v5 en silence.
    if (
        classe is not None
        and issubclass(classe, FiltreSession)
        and "en_session" in signal
    ):
        controles.append(
            Controle(
                cle="session",
            condition="Horaire : session de marché ouverte",
                attendu="Londres ou New York",
                constate="dans la session" if bool(signal["en_session"]) else "hors session",
                valide=bool(signal["en_session"]),
            )
        )

    return controles


def verifier_lot(
    preparees: pd.DataFrame, trades: pd.DataFrame, parametres: dict[str, Any]
) -> pd.DataFrame:
    """Vérifie plusieurs trades d'un coup et résume les échecs.

    Retourne un tableau : une ligne par trade, une colonne par condition, plus le
    détail du premier manquement rencontré.
    """
    lignes = []
    for _, trade in trades.iterrows():
        date_entree = pd.Timestamp(trade["date_entree"])
        signal = bougie_de_signal(preparees, date_entree)

        if signal is None:
            lignes.append({"date_entree": date_entree, "tout_valide": False,
                           "manquement": "bougie de signal introuvable"})
            continue

        controles = verifier(signal, trade, parametres)
        echecs = [c for c in controles if not c.valide]
        ligne: dict[str, Any] = {
            "date_entree": date_entree,
            "sens": trade["sens"],
            "tout_valide": not echecs,
            "manquement": "" if not echecs else echecs[0].condition,
        }
        for controle in controles:
            ligne[controle.cle] = controle.valide
        lignes.append(ligne)

    return pd.DataFrame(lignes)
