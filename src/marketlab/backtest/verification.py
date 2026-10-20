"""Rejouer les règles d'entrée sur un trade déjà exécuté.

À quoi ça sert. Les tests du moteur vérifient qu'il fait ce qui a été codé ; ils ne
peuvent pas vérifier que le résultat correspond aux règles telles qu'on les a
énoncées. Ce module reprend chaque trade, retrouve la bougie qui l'a déclenché, et
confronte chaque condition à ses valeurs réelles.

Deux usages :

* dans l'inspecteur, pour afficher la vérification à côté du graphique ;
* en test automatique, sur un échantillon de trades réels, pour détecter une
  divergence entre le moteur et les règles.

Ce module ne dépend d'aucune interface : il ne fait que lire et comparer. Il ne
connaît AUCUNE règle de stratégie : chacune rejoue les siennes (méthode
`controles`), ce module n'ajoute que ce qui relève du moteur, à savoir le moment
de l'entrée. Une nouvelle stratégie est donc vérifiable dès sa création, sans
que ce fichier ait à la connaître.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from marketlab.strategies.base import Controle, Strategie

__all__ = ["Controle", "bougie_de_signal", "decimales", "verifier", "verifier_lot"]


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
    strategie: Strategie, signal: pd.Series, trade: pd.Series, parametres: dict[str, Any]
) -> list[Controle]:
    """Rejoue les règles de la stratégie, puis celle du moteur, sur la bougie de signal.

    Une stratégie qui ne déclare aucun contrôle reçoit un contrôle en échec
    explicite. Sans lui, la liste se réduirait au moment d'entrée et le trade
    serait déclaré conforme sans qu'aucune de ses règles n'ait été regardée.
    """
    controles = strategie.controles(signal, trade, decimales(parametres))
    if not controles:
        controles = [
            Controle(
                cle="regles",
                condition="Règles de la stratégie",
                attendu="contrôles déclarés par la stratégie",
                constate=f"{strategie.code} ne déclare aucun contrôle",
                valide=False,
            )
        ]

    date_entree = pd.Timestamp(trade["date_entree"])
    controles.append(
        Controle(
            cle="entree",
            condition="Entrée : à l'ouverture de la bougie suivante",
            attendu="signal en N, entrée en N+1",
            constate=f"signal {signal.name:%d/%m %H:%M} → entrée {date_entree:%d/%m %H:%M}",
            valide=signal.name < date_entree,
        )
    )
    return controles


def verifier_lot(
    strategie: Strategie,
    preparees: pd.DataFrame,
    trades: pd.DataFrame,
    parametres: dict[str, Any],
) -> pd.DataFrame:
    """Vérifie plusieurs trades d'un coup et résume les échecs.

    Retourne un tableau : une ligne par trade, une colonne par contrôle (nommée
    par sa clé), plus le détail du premier manquement rencontré. Le libellé de
    chaque clé est rangé dans `rapport.attrs["libelles"]`, pour qu'un affichage
    n'ait pas à tenir sa propre liste, qui serait fausse dès la stratégie suivante.
    """
    lignes = []
    libelles: dict[str, str] = {}
    for _, trade in trades.iterrows():
        date_entree = pd.Timestamp(trade["date_entree"])
        signal = bougie_de_signal(preparees, date_entree)

        if signal is None:
            lignes.append({"date_entree": date_entree, "tout_valide": False,
                           "manquement": "bougie de signal introuvable"})
            continue

        controles = verifier(strategie, signal, trade, parametres)
        echecs = [c for c in controles if not c.valide]
        ligne: dict[str, Any] = {
            "date_entree": date_entree,
            "sens": trade["sens"],
            "tout_valide": not echecs,
            "manquement": "" if not echecs else echecs[0].condition,
        }
        for controle in controles:
            ligne[controle.cle] = controle.valide
            libelles.setdefault(controle.cle, controle.condition)
        lignes.append(ligne)

    rapport = pd.DataFrame(lignes)
    rapport.attrs["libelles"] = libelles
    return rapport
