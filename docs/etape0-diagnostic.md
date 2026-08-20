# Étape 0 — Diagnostic des données

*Généré le 19/08/2026 à 08:59 UTC par `scripts/01_diagnostic_donnees.py`.*

> Document produit automatiquement. Il répond à la checklist de l'annexe F du plan v2.

---

## FTMO — `FTMO-Demo`

- **Levier** : 1:100  ·  **Devise** : USD
- **Symboles exposés** : 166
- **Heure serveur** : UTC+3.0 h

| Instrument | Symbole | Déc. | Vol. min | Pas | Spread | Historique M1 | Bougies 7 j | Trous (max) | Incoh. / Doubl. | Ticks 2 j |
|---|---|---|---|---|---|---|---|---|---|---|
| US30 | `US30.cash` | 2 | 0.01 | 0.01 | 210 | 2019-02-08 | 6,810 | 5 (2956 min) | 0 / 0 | 198,891 |
| GBPUSD | `GBPUSD` | 5 | 0.01 | 0.01 | 3 | 2001-09-10 | 7,114 | 7 (2891 min) | 0 / 0 | 207,470 |
| XAUUSD | `XAUUSD` | 2 | 0.01 | 0.01 | 39 | 2004-09-10 | 6,825 | 5 (2956 min) | 0 / 0 | 469,755 |
| BTCUSD | `BTCUSD` | 2 | 0.01 | 0.01 | 100 | 2011-03-24 | 9,842 | 10 (71 min) | 0 / 0 | 325,386 |

---

## ICMARKET — `ICMarketsEU-Demo`

- **Levier** : 1:30  ·  **Devise** : USD
- **Symboles exposés** : 7402
- **Heure serveur** : UTC+3.0 h

| Instrument | Symbole | Déc. | Vol. min | Pas | Spread | Historique M1 | Bougies 7 j | Trous (max) | Incoh. / Doubl. | Ticks 2 j |
|---|---|---|---|---|---|---|---|---|---|---|
| US30 | `US30` | 2 | 0.1 | 0.1 | 120 | 2012-08-06 | 6,891 | 5 (2941 min) | 0 / 0 | 182,203 |
| GBPUSD | `GBPUSD` | 5 | 0.01 | 0.01 | 12 | 2001-09-10 | 7,193 | 1 (2884 min) | 0 / 0 | 185,322 |
| XAUUSD | `XAUUSD` | 2 | 0.01 | 0.01 | 17 | 1998-04-22 | 6,893 | 5 (2944 min) | 0 / 0 | 1,128,888 |
| BTCUSD | `BTCUSD` | 2 | 0.01 | 0.01 | 100 | 2011-03-24 | 10,011 | 1 (64 min) | 0 / 0 | 558,638 |

---

## Conclusions à tirer

- [ ] Reporter les **noms de symboles réels** dans `config/instruments.yaml`
- [ ] Décider de la **profondeur d'historique** retenue pour les backtests
- [ ] Trancher l'usage des **ticks** selon leur disponibilité réelle
- [ ] Documenter le **décalage horaire** de chaque serveur et le normaliser en UTC à l'ingestion
