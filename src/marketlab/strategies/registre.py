"""Le registre des stratégies : il les trouve seul, dans le dossier `catalogue/`.

C'est ce qui rend l'ajout d'une stratégie fluide. Créer un fichier dans le
catalogue suffit : elle apparaît dans les scripts, dans l'interface et dans les
tests de contrat, sans qu'aucune liste ne soit à compléter à la main. Une liste
écrite à la main finit toujours par être oubliée, et l'oubli ne se voit pas : la
stratégie existe, mais rien ne l'utilise.

Le registre refuse un catalogue incohérent plutôt que de le deviner : deux
stratégies portant le même code, ou une stratégie sans paramètres déclarés,
arrêtent tout avec un message qui dit quoi corriger.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from collections.abc import Mapping
from dataclasses import is_dataclass
from functools import cache
from typing import Any

from marketlab.strategies import catalogue
from marketlab.strategies.base import Strategie


class RegistreError(RuntimeError):
    """Catalogue de stratégies incohérent, ou stratégie introuvable."""


def _verifier(classe: type[Strategie], module: str) -> None:
    """Refuse une stratégie qui ne respecte pas le gabarit d'un fichier du catalogue."""
    if not classe.code:
        raise RegistreError(f"{classe.__name__} ({module}) n'a pas de `code`.")
    if not is_dataclass(classe.Parametres):
        raise RegistreError(
            f"{classe.code} ({module}) : `Parametres` doit être une dataclass "
            f"figée, pour que chaque réglage soit nommé, typé et consigné."
        )
    if not classe.Parametres.__dataclass_params__.frozen:
        raise RegistreError(
            f"{classe.code} ({module}) : `Parametres` doit être figée "
            f"(@dataclass(frozen=True)). Un réglage modifié en cours de route "
            f"rendrait le journal faux."
        )


@cache
def strategies() -> dict[str, type[Strategie]]:
    """Toutes les stratégies du catalogue, par code, dans l'ordre des codes."""
    trouvees: dict[str, type[Strategie]] = {}
    for info in pkgutil.iter_modules(catalogue.__path__):
        module = importlib.import_module(f"{catalogue.__name__}.{info.name}")
        for objet in vars(module).values():
            # Seules comptent les classes DÉFINIES dans ce module : une classe
            # importée d'ailleurs serait sinon enregistrée deux fois.
            if not (
                inspect.isclass(objet)
                and issubclass(objet, Strategie)
                and objet.__module__ == module.__name__
                and not inspect.isabstract(objet)
            ):
                continue
            _verifier(objet, module.__name__)
            if objet.code in trouvees:
                autre = trouvees[objet.code]
                raise RegistreError(
                    f"Deux stratégies portent le code {objet.code!r} : "
                    f"{autre.__module__}.{autre.__name__} et "
                    f"{module.__name__}.{objet.__name__}."
                )
            trouvees[objet.code] = objet
    return dict(sorted(trouvees.items()))


def obtenir(code: str) -> type[Strategie]:
    """La classe de stratégie portant ce code, ou une erreur qui liste les codes connus."""
    catalogue_ = strategies()
    if code not in catalogue_:
        connus = ", ".join(catalogue_) or "(aucun)"
        raise RegistreError(f"Stratégie inconnue : {code!r}. Codes connus : {connus}")
    return catalogue_[code]


def depuis_journal(parametres: Mapping[str, Any]) -> Strategie | None:
    """Reconstruit la stratégie d'une expérience enregistrée, ou None si elle a été retirée.

    La recherche se fait sur le NOM DE CLASSE enregistré, pas sur le code. Un code
    peut changer de sens au fil du projet : « B1 » désignait en août la version à
    trois conditions, il désigne aujourd'hui la version figée. Rejouer une ancienne
    expérience « B1 » avec les règles actuelles produirait une vérification fausse
    sans le moindre avertissement. Le nom de classe, lui, ne ment pas.
    """
    nom_classe = str(parametres.get("strategie_classe", ""))
    for classe in strategies().values():
        if nom_classe == classe.__name__ or nom_classe in classe.anciennes_classes:
            return classe.depuis_journal(parametres)
    return None
