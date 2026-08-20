# MarketLab — PFE

Plateforme de collecte et d'analyse de données financières, et bot de trading associé.

- **Le plan de référence :** [docs/plan-v2.md](docs/plan-v2.md)
- **Contexte du projet :** [contexte/projet.md](contexte/projet.md)

---

## Installation

```powershell
# 1. Activer l'environnement (à refaire à chaque nouveau terminal)
.\.venv\Scripts\Activate.ps1

# 2. Installer le projet et ses dépendances (une seule fois)
pip install -e ".[dev]"

# 3. Créer son fichier de secrets à partir du modèle
copy .env.example .env
#    puis remplir .env avec ses vrais identifiants
```

> Si l'activation est refusée par Windows :
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

---

## Structure

| Dossier | Rôle | Étape du plan |
|---|---|---|
| `src/marketlab/data/` | Récupération et stockage des données | 0, 2, 5 |
| `src/marketlab/strategies/` | Les stratégies (3 baselines + SMC) | 1, 9 |
| `src/marketlab/backtest/` | Moteur de backtest et métriques | 1 |
| `src/marketlab/brokers/` | Interface broker : simulateur et MT5 | 4 |
| `src/marketlab/risk/` | Couche de risque, garde-fous FTMO | 6 |
| `src/marketlab/utils/` | Outils transverses (temps, journalisation) | — |
| `scripts/` | Scripts exécutables, ponctuels ou planifiés | — |
| `config/` | Configuration **non secrète**, versionnée | — |
| `data/` | Données locales, **jamais versionnées** | — |
| `notebooks/` | Exploration et figures du mémoire | — |
| `tests/` | Tests automatisés | — |
| `docs/` | Plan et documentation du projet | — |

Chaque dossier correspond à une étape du plan : il reste vide jusqu'à ce
qu'on y arrive. C'est volontaire.

---

## Règles de travail

1. **Aucun secret dans le code.** Les identifiants vivent dans `.env`, qui n'est jamais versionné.
2. **Aucun nom de symbole en dur.** Ils passent par `config/instruments.yaml`.
3. **Une stratégie ne calcule jamais la taille d'une position.** C'est le rôle de la couche de risque.
4. **Le même code de stratégie tourne en backtest et en live.** Seul le broker change.
