# Étape 0 — Conclusions

**Date :** 19 août 2026
**Objet :** ce que les données disponibles permettent réellement de faire, et les décisions qui en découlent.

> Ce document est rédigé, contrairement à `etape0-diagnostic.md` qui est régénéré automatiquement par les scripts. Il conserve les conclusions et les décisions.

---

## 1. Objectif de l'étape

Avant d'écrire la moindre stratégie, répondre à une question : **de quelles données dispose-t-on vraiment ?** Un backtest bâti sur des données mal comprises produit un résultat crédible et faux — c'est le risque le plus coûteux du projet, parce qu'il ne se révèle qu'à la fin.

Quatre scripts, tous en lecture seule, ont été écrits pour y répondre :

| Script | Question |
|---|---|
| `scripts/00_test_connexion.py` | La connexion aux terminaux fonctionne-t-elle ? |
| `scripts/01_diagnostic_donnees.py` | Symboles, profondeur d'historique, ticks, qualité, fuseau |
| `scripts/02_comparer_courtiers.py` | Les deux courtiers servent-ils les mêmes prix ? |
| `scripts/03_date_bascule.py` | À partir de quand FTMO sert-il ses propres cotations ? |

---

## 2. Résultats mesurés

### Comptes

| | FTMO | IC Markets EU |
|---|---|---|
| Serveur | `FTMO-Demo` | `ICMarketsEU-Demo` |
| Type | démo, `$100k FTMO Free Trial 1-Step` | démo, $100k |
| Effet de levier | **1:100** | **1:30** *(plafond réglementaire UE)* |
| Symboles exposés | 166 | 7 402 |
| Fuseau du serveur | **UTC+3** | **UTC+3** |

### Instruments

| Instrument | Symbole FTMO | Symbole IC Markets | Historique M1 FTMO | Spread FTMO | Ticks / 2 j |
|---|---|---|---|---|---|
| US30 | `US30.cash` | `US30` | depuis 2019-02-08 | 210 pts | ~199 000 |
| GBP/USD | `GBPUSD` | `GBPUSD` | depuis 2001-09-10 | 3 pts | ~207 000 |
| XAU/USD | `XAUUSD` | `XAUUSD` | depuis 2004-09-10 | 39 pts | ~470 000 |
| BTC/USD | `BTCUSD` | `BTCUSD` | depuis 2011-03-24 | 100 pts | ~325 000 |

Qualité sur les 7 derniers jours, chez les deux courtiers : **0 incohérence OHLC, 0 doublon**. Les écarts de plus de 5 minutes correspondent aux week-ends (~2 880 min) et, pour BTC/USD, à des fenêtres de maintenance de 60 à 70 minutes.

---

## 3. Les quatre découvertes qui comptent

### ① Un réglage du terminal masquait 99 % de l'historique

Le premier diagnostic annonçait **3 mois** d'historique M1 sur tous les instruments. Cause : le paramètre `MaxBars = 100 000` des terminaux MT5. Or 104 jours d'un instrument ouvert 24/5 produisent ~107 000 bougies — le plafond tombait pile là.

Après passage en « illimité », l'historique réel apparaît : **7 à 28 ans selon l'instrument**.

**Leçon méthodologique :** le code disait la vérité sur ce qu'il voyait, mais ce qu'il voyait était tronqué par une configuration extérieure. Une mesure peut être techniquement correcte et complètement fausse.

### ② MT5 ne renvoie pas « rien » quand la donnée manque

Interrogé sur mars 2006 pour BTC/USD, MT5 a renvoyé **une bougie datée de juin 2026**. Il ne retourne pas un résultat vide quand la période demandée précède l'historique : il retourne la bougie **la plus proche**.

Un test « la réponse n'est pas vide » concluait donc à 20 ans d'historique sur un instrument créé récemment. Le code vérifie désormais que les horodatages reçus tombent **effectivement** dans la fenêtre demandée.

### ③ L'historique ancien n'est pas celui du courtier

Sur GBP/USD, les clôtures M1 de FTMO et d'IC Markets sont **rigoureusement identiques à la cinquième décimale** sur plus de 1 400 bougies, en 2014, 2015, 2016 et jusqu'en mars 2017. Deux sources indépendantes ne peuvent pas coïncider ainsi.

La bascule a été localisée par encadrement :

| Date | Bougies comparées | Clôtures identiques | Conclusion |
|---|---|---|---|
| **2017-03-10** | 1 438 | **100,0 %** | données communes |
| **2017-04-10** | 1 428 | **0,6 %** | cotations FTMO |

La transition est **nette**, pas progressive : le profil d'une mise en service de serveur.

> **Décision :** l'historique se scinde en deux périodes d'usages distincts.
>
> | Période | Nature | Usage autorisé |
> |---|---|---|
> | Avant avril 2017 | Données génériques, sans spread réel | Exploration, vérification statistique de l'existence des figures, test de généralisation des règles |
> | **Depuis avril 2017** | **Cotations authentiques FTMO** | **Tous les tests décisifs** : rentabilité, spreads réels, Challenge simulé |
>
> Soit **~9 ans et 4 mois** de données décisives. Largement suffisant.

*Réserve : la bascule a été mesurée sur GBP/USD. Elle est présumée identique sur XAU/USD et BTC/USD (même serveur), mais reste à confirmer. US30.cash n'est pas concerné : son historique commence en 2019, donc après la bascule.*

### ④ Les conditions diffèrent entre les deux courtiers

| | FTMO | IC Markets |
|---|---|---|
| US30 — spread | 210 pts | **120 pts** |
| US30 — volume minimum | 0.01 | **0.1** |
| GBP/USD — spread | **3 pts** | 12 pts |
| XAU/USD — spread | 39 pts | **17 pts** |

Deux conséquences pratiques :

- **IC Markets impose 0,1 lot minimum sur US30**, contre 0,01 chez FTMO. Avec 0,2 % de risque sur 100 000 $ — soit 200 $ par trade — certaines positions ne seront pas dimensionnables finement chez IC Markets. Le courtier de développement est donc moins précis que la cible.
- **Les spreads diffèrent dans les deux sens.** Confirmation chiffrée qu'il faut backtester sur les données du courtier cible.

---

## 4. Décisions arrêtées

1. **Source de données et d'exécution : MT5**, même API pour le backtest et le live.
2. **Deux courtiers, deux rôles.** FTMO est la référence (conditions réelles, validation de la couche de risque) ; IC Markets est le cheval de trait (connexion permanente, historique long, paper trading sans coupure).
3. **Période décisive : depuis avril 2017**, sur les données FTMO.
4. **Spreads modélisés d'après les mesures**, jamais supposés nuls.
5. **Normalisation en UTC à l'ingestion** — les serveurs sont en UTC+3.
6. **Granularité collectée : M1 uniquement.** Les timeframes supérieures sont recalculées.
7. **Ticks disponibles et abondants** : la validation d'exécution du niveau 3 est faisable.

Ces paramètres sont inscrits dans `config/instruments.yaml`, pas dans le code.

---

## 5. Ce qui reste ouvert

- [ ] Confirmer la date de bascule sur XAU/USD et BTC/USD
- [ ] Les données BTC/USD d'avant 2017 sont nécessairement reconstituées : à ne pas utiliser, même en exploration
- [ ] Activer le trading algorithmique dans les terminaux — fait, à revérifier avant l'étape 6
- [ ] Vérifier la limite du nombre d'essais gratuits FTMO consécutifs

---

## 6. Volumétrie

| Où | Volume |
|---|---|
| Données stockées dans le projet | **0 octet** — tout était lu en mémoire |
| Cache d'historique du terminal FTMO | 2,8 Go |
| Cache d'historique du terminal IC Markets | 2,5 Go |

Le stockage dans le projet commence à l'étape 2, en Parquet compressé — bien plus léger que le cache brut des terminaux.

---

**Étape 0 : terminée.** L'étape 1 (premier backtest) peut démarrer sur une base mesurée : symbole exact, période crédible, spread réel, volume minimum, fuseau connu.
