"""Journal d'expériences : conserver la trace de chaque simulation.

Pourquoi ce module existe. Deux essais lancés coup sur coup ont déjà détruit les
résultats du premier. Plus grave : sans les conditions exactes d'une exécution, un
chiffre isolé ne veut rien dire. « Cette stratégie fait moins 18 % » n'a de sens
qu'accompagné de l'instrument, de la période, du spread, des paramètres et de la
version du moteur qui a produit le résultat.

Chaque exécution est donc traitée comme une **expérience** : conditions et résultat
conservés ensemble, définitivement.

STRUCTURE SUR LE DISQUE

    data/backtests/
        20260820_1418_GBPUSD_B1/
            parametres.json    tout ce qui définit l'expérience
            metriques.json     tous les résultats
            trades.parquet     le détail des positions
        registre.parquet       une ligne par expérience, pour comparer

DEUX PRÉCAUTIONS QUI PARAISSENT SECONDAIRES ET NE LE SONT PAS

* **La version du code.** Si le moteur change entre deux exécutions, les résultats
  cessent d'être comparables. Sans cette trace, impossible de le savoir plus tard.
  On enregistre aussi si des modifications non validées traînaient au moment du
  lancement, auquel cas la version affichée ne décrit pas exactement le code exécuté.

* **La nature de l'expérience.** Un journal rend facile de lancer cinquante
  variantes et de garder la meilleure : c'est du sur-apprentissage déguisé en
  méthode. Chaque expérience déclare donc si sa question était posée AVANT de voir
  le résultat (« pré-enregistrée », dont on peut conclure quelque chose) ou si elle
  relève de l'exploration (qui produit des pistes, pas des conclusions).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from marketlab.config import DATA_DIR, PROJECT_ROOT

REPERTOIRE = DATA_DIR / "backtests"
REGISTRE = REPERTOIRE / "registre.parquet"


class Nature:
    """Statut épistémique d'une expérience."""

    #: Question posée avant d'en connaître la réponse. Autorise une conclusion.
    PRE_ENREGISTREE = "pré-enregistrée"
    #: Recherche libre. Produit des pistes à valider ensuite, pas des conclusions.
    EXPLORATION = "exploration"


@dataclass
class Experience:
    """Une simulation, avec ses conditions et ses résultats."""

    identifiant: str
    horodatage: str
    nature: str
    note: str
    version_code: str
    code_modifie: bool
    empreinte: str
    parametres: dict[str, Any] = field(default_factory=dict)
    metriques: dict[str, Any] = field(default_factory=dict)

    @property
    def dossier(self) -> Path:
        return REPERTOIRE / self.identifiant


# ---------------------------------------------------------------------------
# Traçabilité du code
# ---------------------------------------------------------------------------


def _git(*arguments: str) -> str | None:
    """Exécute une commande git, ou retourne None si elle échoue."""
    try:
        resultat = subprocess.run(
            ["git", *arguments],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return resultat.stdout.strip() if resultat.returncode == 0 else None


def version_du_code() -> tuple[str, bool]:
    """Retourne (identifiant du commit, des modifications non validées existent).

    Un dépôt sans aucun commit renvoie « aucun commit » : c'est une information
    utile, pas une erreur.
    """
    commit = _git("rev-parse", "--short", "HEAD")
    if commit is None:
        return "aucun commit", True

    etat = _git("status", "--porcelain")
    return commit, bool(etat)


# ---------------------------------------------------------------------------
# Identité d'une expérience
# ---------------------------------------------------------------------------


def empreinte_parametres(parametres: dict[str, Any]) -> str:
    """Condensé court des paramètres, pour reconnaître deux essais identiques.

    Le tri des clés garantit que le même jeu de paramètres donne toujours la même
    empreinte, quel que soit l'ordre de construction du dictionnaire.
    """
    texte = json.dumps(parametres, sort_keys=True, default=str)
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()[:12]


def _identifiant(parametres: dict[str, Any], moment: datetime) -> str:
    instrument = parametres.get("instrument", "?")
    strategie = parametres.get("strategie_code", "?")
    return f"{moment:%Y%m%d_%H%M%S}_{instrument}_{strategie}"


# ---------------------------------------------------------------------------
# Enregistrement
# ---------------------------------------------------------------------------


def _ligne_registre(experience: Experience) -> dict[str, Any]:
    """Aplatit une expérience en une ligne de tableau comparatif.

    Les paramètres et les métriques sont préfixés pour rester distinguables une
    fois côte à côte dans la même ligne.
    """
    ligne: dict[str, Any] = {
        "identifiant": experience.identifiant,
        "horodatage": experience.horodatage,
        "nature": experience.nature,
        "note": experience.note,
        "version_code": experience.version_code,
        "code_modifie": experience.code_modifie,
        "empreinte": experience.empreinte,
    }
    for cle, valeur in experience.parametres.items():
        ligne[f"p_{cle}"] = valeur
    for cle, valeur in experience.metriques.items():
        # Les structures imbriquées ne tiennent pas dans une colonne.
        ligne[f"m_{cle}"] = valeur if not isinstance(valeur, dict) else json.dumps(valeur)
    return ligne


def enregistrer(
    parametres: dict[str, Any],
    metriques: dict[str, Any],
    trades: pd.DataFrame,
    nature: str = Nature.EXPLORATION,
    note: str = "",
) -> Experience:
    """Enregistre une simulation et retourne l'expérience créée."""
    moment = datetime.now(UTC)
    commit, modifie = version_du_code()

    experience = Experience(
        identifiant=_identifiant(parametres, moment),
        horodatage=moment.isoformat(timespec="seconds"),
        nature=nature,
        note=note,
        version_code=commit,
        code_modifie=modifie,
        empreinte=empreinte_parametres(parametres),
        parametres=parametres,
        metriques=metriques,
    )

    dossier = experience.dossier
    dossier.mkdir(parents=True, exist_ok=True)

    (dossier / "parametres.json").write_text(
        json.dumps(parametres, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    (dossier / "metriques.json").write_text(
        json.dumps(metriques, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    (dossier / "experience.json").write_text(
        json.dumps(asdict(experience), indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    if not trades.empty:
        trades.to_parquet(dossier / "trades.parquet", compression="zstd")

    # Le registre est la source de vérité : l'interface et tout inventaire le
    # lisent, lui et pas les dossiers. Un dossier absent du registre serait donc
    # invisible tout en occupant la place, incohérence d'autant plus pernicieuse
    # qu'un journal d'expériences ne vaut que par son exhaustivité. On défait
    # l'écriture plutôt que de la laisser à moitié faite.
    try:
        _ajouter_au_registre(experience)
    except Exception:
        shutil.rmtree(dossier, ignore_errors=True)
        raise

    return experience


def _ajouter_au_registre(experience: Experience) -> None:
    """Ajoute une ligne au tableau comparatif, en le créant au besoin."""
    ligne = pd.DataFrame([_ligne_registre(experience)])

    if REGISTRE.exists():
        ancien = pd.read_parquet(REGISTRE)
        # Un essai peut introduire des colonnes absentes des précédents :
        # la concaténation les aligne en remplissant de valeurs manquantes.
        registre = pd.concat([ancien, ligne], ignore_index=True)
    else:
        registre = ligne

    REGISTRE.parent.mkdir(parents=True, exist_ok=True)
    registre.to_parquet(REGISTRE, compression="zstd")


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------


def charger_registre() -> pd.DataFrame:
    """Le tableau comparatif de toutes les expériences, la plus récente d'abord."""
    if not REGISTRE.exists():
        return pd.DataFrame()
    registre = pd.read_parquet(REGISTRE)
    return registre.sort_values("horodatage", ascending=False).reset_index(drop=True)


def charger_experience(identifiant: str) -> Experience:
    """Recharge une expérience depuis son dossier."""
    fichier = REPERTOIRE / identifiant / "experience.json"
    if not fichier.exists():
        raise FileNotFoundError(f"Expérience introuvable : {identifiant}")
    return Experience(**json.loads(fichier.read_text(encoding="utf-8")))


def charger_trades(identifiant: str) -> pd.DataFrame:
    """Les trades d'une expérience."""
    fichier = REPERTOIRE / identifiant / "trades.parquet"
    if not fichier.exists():
        return pd.DataFrame()
    return pd.read_parquet(fichier)


def lister() -> list[str]:
    """Identifiants de toutes les expériences enregistrées, la plus récente d'abord."""
    if not REPERTOIRE.exists():
        return []
    dossiers = [d.name for d in REPERTOIRE.iterdir() if (d / "experience.json").exists()]
    return sorted(dossiers, reverse=True)
