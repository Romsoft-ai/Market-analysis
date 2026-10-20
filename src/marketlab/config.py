"""Chargement de la configuration du projet.

Deux sources, volontairement séparées :

* ``.env``                  -> les SECRETS (identifiants). Jamais versionné.
* ``config/*.yaml``         -> les PARAMÈTRES (noms de symboles, unités de temps).
                               Versionnés, car ils font partie du projet.

Tout le reste du code passe par ce module : aucun identifiant ni aucun nom de
symbole ne doit apparaître en dur ailleurs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Racine du projet : ce fichier est dans src/marketlab/, donc deux niveaux au-dessus.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"

# Charge .env une seule fois, à l'import du module.
load_dotenv(PROJECT_ROOT / ".env")


class ConfigError(RuntimeError):
    """Configuration absente, incomplète ou invalide."""


@dataclass(frozen=True)
class BrokerConfig:
    """Tout ce qu'il faut pour se connecter à un compte MT5."""

    name: str
    login: int
    password: str
    server: str
    terminal_path: Path

    def __repr__(self) -> str:
        # Volontairement sans le mot de passe : cet objet finira dans des logs.
        return (
            f"BrokerConfig(name={self.name!r}, login={self.login}, "
            f"server={self.server!r})"
        )


def available_brokers() -> list[str]:
    """Liste les courtiers effectivement configurés dans .env.

    Repère les variables de la forme ``<PREFIXE>_LOGIN`` et en déduit les noms
    utilisables avec :func:`get_broker`.
    """
    noms = [
        cle.removesuffix("_LOGIN").lower()
        for cle, valeur in os.environ.items()
        if cle.endswith("_LOGIN") and valeur.strip()
    ]
    return sorted(noms)


def _require(var: str) -> str:
    """Lit une variable d'environnement, ou explique précisément ce qui manque."""
    value = os.getenv(var, "").strip()
    if not value:
        dispo = ", ".join(available_brokers()) or "(aucun)"
        raise ConfigError(
            f"La variable {var} est absente ou vide.\n"
            f"  -> Courtiers effectivement configurés dans .env : {dispo}\n"
            f"  -> Vérifie le préfixe utilisé, et DEFAULT_BROKER."
        )
    return value


def courtier_par_defaut() -> str:
    """Nom du courtier utilisé quand aucun n'est précisé (DEFAULT_BROKER du .env).

    Les scripts et l'interface passent par ici plutôt que d'écrire un nom en dur :
    changer de courtier principal se fait alors dans .env, et nulle part ailleurs.
    """
    return os.getenv("DEFAULT_BROKER", "demo").strip().lower()


def get_broker(name: str | None = None) -> BrokerConfig:
    """Retourne la configuration d'un courtier.

    Args:
        name: ``"icmarket"`` ou ``"ftmo"``. Si omis, on prend DEFAULT_BROKER du .env.

    Le préfixe des variables se déduit du nom : ``ftmo`` -> ``FTMO_LOGIN``, etc.
    C'est ce qui permet de changer de compte sans toucher une ligne de code.
    """
    name = (name or courtier_par_defaut()).strip().lower()
    prefix = name.upper()

    login_raw = _require(f"{prefix}_LOGIN")
    try:
        login = int(login_raw)
    except ValueError as exc:
        raise ConfigError(
            f"{prefix}_LOGIN doit être un nombre (le numéro de compte MT5), "
            f"or j'ai lu : {login_raw!r}"
        ) from exc

    terminal_path = Path(_require(f"{prefix}_TERMINAL_PATH"))
    if not terminal_path.exists():
        raise ConfigError(
            f"Le terminal MT5 est introuvable :\n"
            f"  {terminal_path}\n"
            f"  -> Corrige {prefix}_TERMINAL_PATH dans .env.\n"
            f"  -> Le chemin doit pointer vers terminal64.exe, pas vers le dossier."
        )

    return BrokerConfig(
        name=name,
        login=login,
        password=_require(f"{prefix}_PASSWORD"),
        server=_require(f"{prefix}_SERVER"),
        terminal_path=terminal_path,
    )


def load_instruments() -> dict:
    """Charge config/instruments.yaml."""
    path = CONFIG_DIR / "instruments.yaml"
    if not path.exists():
        raise ConfigError(f"Fichier de configuration manquant : {path}")
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def symbol_for(instrument: str, broker_name: str) -> str:
    """Traduit un nom d'instrument interne en nom de symbole chez un courtier.

    Exemple : ``symbol_for("US30", "ftmo")`` -> ``"US30.cash"``

    C'est la seule façon autorisée d'obtenir un nom de symbole : ça garantit
    qu'un changement de courtier ne casse rien ailleurs.
    """
    instruments = load_instruments().get("instruments", {})
    if instrument not in instruments:
        connus = ", ".join(sorted(instruments)) or "(aucun)"
        raise ConfigError(
            f"Instrument inconnu : {instrument!r}. Connus : {connus}"
        )
    mapping = instruments[instrument]
    if broker_name not in mapping:
        raise ConfigError(
            f"Aucun symbole défini pour {instrument!r} chez le courtier "
            f"{broker_name!r}. Complète config/instruments.yaml."
        )
    return mapping[broker_name]
