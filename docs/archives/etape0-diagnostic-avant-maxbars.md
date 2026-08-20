# Étape 0 — Diagnostic des données

*Généré le 19/08/2026 à 07:37 UTC par `scripts/01_diagnostic_donnees.py`.*

> Document produit automatiquement. Il répond à la checklist de l'annexe F du plan v2.

---

## FTMO — `FTMO-Demo`

- **Levier** : 1:100  ·  **Devise** : USD
- **Symboles exposés** : 166
- **Heure serveur** : UTC+3.0 h

| Instrument | Symbole | Déc. | Vol. min | Spread | Historique M1 | Bougies 7 j | Trous | Ticks 2 j |
|---|---|---|---|---|---|---|---|---|
| US30 | `US30.cash` | 2 | 0.01 | 210 | 2026-05-07 
| GBPUSD | `GBPUSD` | 5 | 0.01 | 8 | 2026-05-13 
| XAUUSD | `XAUUSD` | 2 | 0.01 | 45 | 2026-05-07 
| BTCUSD | `BTCUSD` | 2 | 0.01 | 100 | 2026-06-08 

---

## ICMARKET — `ICMarketsEU-Demo`

- **Levier** : 1:30  ·  **Devise** : USD
- **Symboles exposés** : 7403
- **Heure serveur** : UTC+3.0 h

| Instrument | Symbole | Déc. | Vol. min | Spread | Historique M1 | Bougies 7 j | Trous | Ticks 2 j |
|---|---|---|---|---|---|---|---|---|
| US30 | `US30` | 2 | 0.1 | 120 | 2026-05-08 
| GBPUSD | `GBPUSD` | 5 | 0.01 | 10 | 2026-05-13 
| XAUUSD | `XAUUSD` | 2 | 0.01 | 21 | 2026-05-08 
| BTCUSD | `BTCUSD` | 2 | 0.01 | 100 | 2026-06-09 

---

## Conclusions à tirer

- [ ] Reporter les **noms de symboles réels** dans `config/instruments.yaml`
- [ ] Décider de la **profondeur d'historique** retenue pour les backtests
- [ ] Trancher l'usage des **ticks** selon leur disponibilité réelle
- [ ] Documenter le **décalage horaire** de chaque serveur et le normaliser en UTC à l'ingestion
