"""Le contrat commun à toutes les stratégies.

C'est la pièce qui rend les quatre stratégies du projet (trois baselines + SMC)
interchangeables. Une stratégie reçoit des bougies clôturées et renvoie soit rien,
soit un signal. Rien d'autre.

Deux règles inscrites dans le code, pas seulement dans la documentation :

1. **Une stratégie ne calcule JAMAIS la taille d'une position.** Elle dit *où*
   entrer et *où* sortir ; c'est la couche de risque (étape 6) qui dit *combien*.
   Une stratégie a le droit de se tromper — c'est son métier. Le risque, non.

2. **Une stratégie ne voit jamais l'avenir.** La méthode `evaluer` reçoit un
   historique déjà tronqué à la dernière bougie clôturée : les bougies futures sont
   physiquement absentes de l'objet reçu. On ne peut donc pas tricher par
   distraction, ce qui est l'erreur la plus fréquente en backtest.
"""

from __future__ import annotations

import ast
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields
from enum import Enum
from typing import Any, ClassVar

import pandas as pd

# Colonnes attendues dans toute série de bougies manipulée par le projet.
COLONNES_BOUGIES = ("open", "high", "low", "close")


class Sens(Enum):
    """Direction d'un signal."""

    ACHAT = "achat"
    VENTE = "vente"


class SignalInvalide(ValueError):
    """Un signal dont les prix sont incohérents avec son sens."""


@dataclass(frozen=True)
class Signal:
    """Une intention de position : où entrer, où sortir en perte, où sortir en gain.

    Volontairement immuable : un signal émis ne se modifie pas. Si les conditions
    changent, la stratégie en émet un autre.
    """

    sens: Sens
    entree: float
    stop: float
    objectif: float
    # Trace lisible de la raison du signal. Sert au journal d'audit et au
    # débogage : sans elle, impossible de comprendre après coup pourquoi le bot
    # a agi.
    raison: str = ""

    def __post_init__(self) -> None:
        """Vérifie la cohérence des prix. Un stop du mauvais côté serait grave.

        Sans ce contrôle, une stratégie boguée pourrait produire une position
        « qui ne peut pas perdre » et gonfler artificiellement un backtest.
        """
        if self.sens is Sens.ACHAT and not (self.stop < self.entree < self.objectif):
            raise SignalInvalide(
                f"Achat incohérent : il faut stop < entrée < objectif, "
                f"or stop={self.stop}, entrée={self.entree}, objectif={self.objectif}"
            )
        if self.sens is Sens.VENTE and not (self.objectif < self.entree < self.stop):
            raise SignalInvalide(
                f"Vente incohérente : il faut objectif < entrée < stop, "
                f"or objectif={self.objectif}, entrée={self.entree}, stop={self.stop}"
            )

    @property
    def risque(self) -> float:
        """Distance entre l'entrée et le stop, en unités de prix.

        C'est la grandeur dont la couche de risque a besoin pour convertir
        « 0,2 % du capital » en une taille de position.
        """
        return abs(self.entree - self.stop)

    @property
    def ratio(self) -> float:
        """Gain visé divisé par le risque pris (le « R »)."""
        return abs(self.objectif - self.entree) / self.risque

    def __str__(self) -> str:
        return (
            f"{self.sens.value.upper()} entrée={self.entree:.5f} "
            f"stop={self.stop:.5f} objectif={self.objectif:.5f} "
            f"({self.ratio:.1f}R) — {self.raison}"
        )


@dataclass
class Controle:
    """Une règle d'entrée rejouée sur un trade : ce qui était attendu, ce qui est constaté.

    `cle` identifie la NATURE du contrôle, indépendamment de sa position dans la
    liste. Les contrôles varient d'une stratégie à l'autre : nommer les colonnes
    par rang ferait afficher le libellé d'une règle à la place d'une autre, et un
    rapport de conformité qui désigne la mauvaise règle est pire qu'un rapport
    absent.
    """

    cle: str
    condition: str
    attendu: str
    constate: str
    valide: bool


@dataclass(frozen=True)
class SansParametre:
    """Jeu de paramètres vide, pour une stratégie qui n'en a aucun."""


#: Préfixe des paramètres de stratégie dans le journal d'expériences.
PREFIXE_JOURNAL = "strat_"


class Strategie(ABC):
    """Contrat que toute stratégie du projet doit respecter.

    Une stratégie concrète vit dans son propre fichier du dossier `catalogue/`,
    avec la classe de ses paramètres. Le registre la découvre seule : l'ajouter
    au projet revient à créer ce fichier, sans rien modifier ailleurs.
    """

    #: Identifiant court et unique (« B1 », « B2 »...), utilisé par les scripts,
    #: l'interface et le journal.
    code: ClassVar[str] = ""

    #: Nom lisible, utilisé dans les rapports et les comparaisons.
    nom: ClassVar[str] = "sans nom"

    #: Classe des paramètres : une dataclass figée, dont les valeurs par défaut
    #: SONT les réglages de référence de la stratégie.
    Parametres: ClassVar[type] = SansParametre

    #: Noms de classes sous lesquels cette stratégie a été enregistrée par le
    #: passé. Permet de rejouer d'anciennes expériences après un renommage.
    anciennes_classes: ClassVar[tuple[str, ...]] = ()

    def __init__(self, parametres: Any = None) -> None:
        self.parametres = parametres if parametres is not None else self.Parametres()
        if not isinstance(self.parametres, self.Parametres):
            raise TypeError(
                f"{type(self).__name__} attend des {self.Parametres.__name__}, "
                f"pas des {type(self.parametres).__name__}"
            )

    # ------------------------------------------------------------------
    # Journal : les paramètres sortent et reviennent sans perte
    # ------------------------------------------------------------------

    def parametres_journal(self) -> dict[str, Any]:
        """Paramètres à consigner avec une expérience, préfixés pour le journal."""
        return {f"{PREFIXE_JOURNAL}{cle}": v for cle, v in asdict(self.parametres).items()}

    @classmethod
    def depuis_journal(cls, enregistres: Mapping[str, Any]) -> Strategie:
        """Reconstruit la stratégie avec les paramètres d'une expérience passée.

        Chaque valeur est ramenée au type de la valeur par défaut : le journal
        relit des JSON et des parquet, où un entier peut revenir en flottant et un
        tuple en liste. Un paramètre absent du journal garde sa valeur par défaut,
        ce qui permet de rejouer une expérience antérieure à son ajout.
        """
        valeurs = {}
        for champ in fields(cls.Parametres):
            cle = f"{PREFIXE_JOURNAL}{champ.name}"
            if cle in enregistres and enregistres[cle] is not None:
                defaut = getattr(cls.Parametres(), champ.name)
                valeurs[champ.name] = _au_type_de(defaut, enregistres[cle])
        return cls(cls.Parametres(**valeurs))

    # ------------------------------------------------------------------
    # Gestion de position : facultative
    # ------------------------------------------------------------------

    def ajuster_stop(self, sens: Sens, stop_actuel: float, bougie: pd.Series) -> float | None:
        """Nouveau niveau de stop proposé à la clôture de `bougie`, ou None.

        Appelée à chaque bougie clôturée tant qu'une position est ouverte, par le
        moteur de backtest comme par le robot live : c'est ce qui garantit qu'un
        stop suiveur se comporte de la même façon des deux côtés. `bougie` est une
        ligne déjà préparée (indicateurs compris), jamais une bougie future.

        La stratégie PROPOSE, elle ne décide pas : l'appelant n'accepte qu'un stop
        qui se resserre. Par défaut, aucune proposition : le stop reste fixe.
        """
        return None

    # ------------------------------------------------------------------
    # Vérification : chaque stratégie sait rejouer ses propres règles
    # ------------------------------------------------------------------

    def controles(
        self, bougie: pd.Series, trade: pd.Series, decimales: int
    ) -> list[Controle]:
        """Rejoue les règles d'entrée sur la bougie de signal d'un trade.

        Par défaut aucune : une stratégie qui ne la redéfinit pas ne sera pas
        déclarée conforme, elle sera déclarée non vérifiée.
        """
        return []

    @property
    @abstractmethod
    def bougies_minimum(self) -> int:
        """Nombre de bougies nécessaires avant de pouvoir décider quoi que ce soit.

        Une EMA 200 n'a pas de sens sur 50 bougies. Le moteur de backtest s'en sert
        pour savoir à partir de quand commencer à évaluer.
        """

    @abstractmethod
    def preparer(self, bougies: pd.DataFrame) -> pd.DataFrame:
        """Calcule les indicateurs sur toute la série, en une seule passe.

        Séparé de `evaluer` pour une raison de performance : recalculer une EMA 200
        à chaque bougie donnerait un coût quadratique. Ici on calcule une fois,
        puis on lit.

        Retourne une copie enrichie de colonnes d'indicateurs.
        """

    @abstractmethod
    def evaluer(self, historique: pd.DataFrame) -> Signal | None:
        """Décide à partir de l'historique reçu, dont la dernière ligne est la
        dernière bougie CLÔTURÉE.

        L'appelant fournit une tranche déjà coupée : aucune bougie future n'est
        accessible. Retourne None quand aucune condition n'est réunie — ce qui
        sera le cas la grande majorité du temps.
        """


def _au_type_de(defaut: Any, valeur: Any) -> Any:
    """Convertit une valeur relue du journal vers le type de `defaut`."""
    if isinstance(defaut, tuple):
        if isinstance(valeur, str):
            # Un tuple passé par une colonne texte revient sous sa forme affichée.
            valeur = ast.literal_eval(valeur)
        return tuple(valeur)
    if isinstance(defaut, bool):
        return bool(valeur)
    if isinstance(defaut, int):
        return int(float(valeur))
    if isinstance(defaut, float):
        return float(valeur)
    return valeur


def verifier_bougies(bougies: pd.DataFrame) -> None:
    """Vérifie qu'une série de bougies est utilisable, ou explique ce qui manque."""
    manquantes = [c for c in COLONNES_BOUGIES if c not in bougies.columns]
    if manquantes:
        raise ValueError(
            f"Colonnes manquantes dans les bougies : {', '.join(manquantes)}. "
            f"Colonnes présentes : {', '.join(map(str, bougies.columns))}"
        )
    if not bougies.index.is_monotonic_increasing:
        raise ValueError(
            "Les bougies ne sont pas triées par ordre chronologique croissant. "
            "Un backtest sur des données désordonnées ne veut rien dire."
        )
