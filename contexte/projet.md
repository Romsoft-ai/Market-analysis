# Projet hybride — Bot de trading SMC + Plateforme Big Data
### Base de connaissances (handoff pour un autre agent)

> Ce document résume l'ensemble des décisions et concepts établis lors d'une discussion de cadrage.
> Objectif : servir de point de départ à la construction du projet. Il décrit **le but**, **les choix arrêtés**,
> **l'architecture cible**, **la feuille de route**, et **les questions encore ouvertes**.
>
> *Note : rien ici n'est un conseil financier. Tous les chiffres de performance ou taux de réussite issus de
> sources tierces doivent être revérifiés par un backtest propre et personnel.*

---

## 1. Le projet et son but

Le projet a **deux facettes indissociables** qui s'emboîtent :

### 1.1 Volet personnel — Bot de trading
Automatiser une stratégie de trading **déjà pratiquée manuellement depuis des années** par l'utilisateur,
basée sur le **Smart Money Concept (SMC)**. Le but immédiat n'est **pas** de trader en réel tout de suite,
mais de **valider par backtest** si la stratégie est réellement performante, puis, si oui, de l'exécuter
automatiquement sur un **compte de prop firm (FTMO)**.
Motivation : l'utilisateur manque de temps pour suivre ses positions et veut automatiser ce qu'il fait déjà.

### 1.2 Volet académique — Projet de fin d'études
Intitulé : **« Conception d'une plateforme de big data de collecte et d'analyse de données financières en temps réel »**.
C'est l'infrastructure : collecter, stocker et analyser des données financières à grande échelle et en temps réel.

### 1.3 Comment les deux s'articulent
- La **plateforme big data = la fondation** (générique, scalable) → le **livrable académique**.
- Le **bot de trading = une application** qui se branche dessus et la consomme → le **volet perso**.
- **Point de jonction** : la plateforme expose des **données + signaux** via une API ; le bot les consomme.
- Le **moteur de détection SMC** est pile à la frontière : « module d'analyse » côté plateforme,
  « source de signaux » côté bot. C'est le composant partagé, codé une seule fois.
- Le bot apporte au mémoire la **dimension "Valeur"** (une application concrète qui prouve l'utilité de la plateforme).

**Cadrage de soutenance recommandé** : garder le livrable académique centré sur la plateforme et ses propriétés
big data (architecture distribuée, scalabilité, temps réel, qualité des données). Présenter le trading comme
**cas d'usage démonstrateur**, pas comme sujet d'évaluation (ne pas laisser le jury juger la rentabilité de la
stratégie). Laisser l'exécution réelle d'ordres et la gestion d'argent **côté projet perso** pour garder le
mémoire propre et sans zone de risque juridique.

---

## 2. Profil de l'utilisateur (contexte)

- **Trader expérimenté** (plusieurs années), pratique le SMC manuellement.
- **Sait coder correctement** (niveau confirmé).
- Habitué des **prop firms** type FTMO (capital fourni après réussite d'un test/Challenge).
- **Objectif de performance affiché : 5 à 10 % par mois** (noté comme très ambitieux et à variance élevée —
  à confronter à la *distribution* des résultats du backtest, pas seulement à la moyenne).
- Ne risque pas son propre capital en live : l'enjeu est de **réussir les Challenges FTMO**.

---

## 3. La stratégie : Smart Money Concept (SMC)

Approche dérivée d'ICT. Idée centrale : se positionner dans le sens des acteurs institutionnels (« smart money »).

**Concepts clés à mécaniser :**
- **Market structure** : higher highs / higher lows, etc.
- **BOS (Break of Structure)** et **CHoCH (Change of Character)** : continuation / retournement.
- **Order Blocks (OB)** : dernière bougie avant un mouvement impulsif.
- **Liquidity** : zones de stops (liquidity grab, stop hunt, inducement).
- **Fair Value Gaps (FVG)** / imbalances : déséquilibres à combler.
- **Premium / Discount** : acheter en discount, vendre en premium.

**Défi principal** : le SMC est largement **discrétionnaire/visuel**. Tout l'enjeu du projet est de le traduire en
**règles strictement mécaniques et non ambiguës, fixées AVANT le test** (sinon overfitting et backtests trompeurs).

**Approche multi-timeframe (top-down) de l'utilisateur :**
| Timeframe | Rôle |
|---|---|
| **Daily + H4** | Tendance / biais directionnel |
| **H1 + M15** | Structure : BOS, CHoCH, liquidité |
| **M5** | Déclencheur d'entrée — **GBP/USD** |
| **M1** | Déclencheur d'entrée — **US30** |

À coder comme une **cascade de filtres** : biais (D/H4) → structure (H1/M15) → déclencheur (M5/M1).
Chaque étage doit valider avant de descendre. La timeframe d'entrée est **un paramètre par instrument**.

---

## 4. Décisions clés arrêtées durant la discussion

1. **Objectif immédiat = BACKTEST** (valider la rentabilité) avant toute automatisation.
2. **Ce n'est PAS un SaaS**, mais une **application mono-utilisateur** (bot + dashboard de contrôle).
   Le passage en SaaS (multi-tenant, facturation, régulation financière) est repoussé à *plus tard, si ça marche*.
3. **Architecture modulaire et agnostique à l'instrument dès le départ**, mais **périmètre de dev resserré au début**.
   (La flexibilité coûte peu si conçue tôt, cher à rétrofitter.)
4. **Instruments retenus : US30, GBP/USD, XAU/USD** (indice actions + forex + or = 3 moteurs décorrélés).
   NAS100 et GER40 écartés (trop corrélés au US30). **MVP = US30 seul**, extension aux 2 autres au fil de l'eau.
5. **4 stratégies au backtest** : le **SMC (principale)** + **3 baselines à indicateurs** (voir §5) **pour comparaison uniquement**.
6. **En LIVE : UNE seule stratégie par compte FTMO** (attribution de performance propre). Le backtest comparatif
   sert de **mécanisme de sélection** du « gagnant » à déployer. Plusieurs stratégies en réel = **plusieurs comptes FTMO**.
7. **Données : bougies = donnée principale** (logique SMC) ; **tick = couche de précision** (exécution réaliste,
   validation, live). **L2 (carnet d'ordres) = optionnel**, surtout pour l'argument big data (voir §7).
8. **Big data justifié** non par le simple backtest sur bougies (qui tient sur un laptop), mais par :
   temps réel multi-flux (vélocité) + tick/L2 (volume) + optimisation walk-forward distribuée (calcul) + variété (news/sentiment).
9. **Pattern d'architecture : Lambda** (couche *speed* = signaux live ; couche *batch* = backtest sur l'historique).
   Alternative Kappa mentionnée mais Lambda choisi pour le besoin de rejouer l'historique.
10. **Données économiques / sentiment = filtre & contexte, pas signal d'entrée** (voir §8).
11. **Métriques ventilées par instrument** (pas seulement le total du compte).

---

## 5. Les 3 stratégies baselines (benchmark du SMC)

But : répondre à « est-ce que mon SMC bat une approche simple ? ». Toutes codables via `ta` / `pandas-ta` /
indicateurs intégrés de `backtesting.py` / `vectorbt`.

1. **MACD + Bollinger Bands** — momentum + volatilité.
2. **Confluence RSI + MACD + EMA** — momentum + tendance + épuisement (triple confirmation).
3. **SuperTrend (ATR) filtré par QQE ou RSI** — suivi de tendance adaptatif avec trailing stop volatilité-dépendant.

> ⚠️ Les taux de réussite flatteurs (ex. « 77 % ») qui circulent sur ces stratégies viennent de sources
> commerciales/SEO. À traiter avec scepticisme ; seul le backtest propre fait foi.

---

## 6. Architecture technique

### 6.1 Le bot de trading (application)
Flux vertical, la couche de risque est le gardien central :

```
Sources (API broker prix + calendrier éco)
        ↓
Ingestion / normalisation des bougies (+ audit qualité)
        ↓
Moteur de détection SMC  (lib smartmoneyconcepts : OB, FVG, BOS/CHoCH, liquidity)
        ↓
Moteur de stratégie  (règles d'entrée/sortie sur mesure = "le cerveau")
        ↓
Couche de RISQUE & CONFORMITÉ  (gardien : applique règles + contraintes FTMO)   ← Dashboard de contrôle se branche ici
        ↓
Exécution  (backtest simulé  OU  live réel — seule couche qui change entre les 2 modes)
        ↓
Base de données (trades, logs, positions)
```
**Principe clé** : le même code de stratégie + risque tourne en backtest ET en live ; seule la couche
d'exécution diffère. C'est ce qui garantit la fidélité backtest → réel.

### 6.2 La plateforme big data (mémoire) — pile technique
| Couche | Rôle | Outils proposés |
|---|---|---|
| Collecte / Sources | Acquisition multi-sources (variété) | API broker (OANDA/MT5), WebSocket tick, API calendrier éco, news/RSS |
| Ingestion streaming | Bus temps réel haut débit, tolérant aux pannes (vélocité) | **Apache Kafka** + Kafka Connect |
| Traitement distribué | Temps réel (speed) + batch (Lambda) | **Flink** ou **Spark Structured Streaming** (temps réel) ; **Apache Spark** (batch/backtest) |
| Stockage | Historique + requêtes rapides (volume) | Data lake **MinIO/HDFS** (Parquet) + time-series **TimescaleDB/InfluxDB** |
| Service & API | Frontière propre plateforme ↔ consommateurs | **FastAPI** (REST) / gRPC |
| Restitution | Visualisation + application | **Grafana** (dashboards) + **le bot de trading** (consommateur) |
| Socle transverse | Déploiement, scalabilité, orchestration, monitoring | **Docker**, **Kubernetes**, **Airflow**, **Prometheus + Grafana** |

**Fil conducteur de soutenance : les 5 V** — Volume, Vélocité, Variété, Véracité (qualité des données), Valeur (le bot).
Rattacher chaque couche à un ou deux V. Assumer clairement ce qui est **implémenté** vs **conçu** (un cœur
fonctionnel + une architecture cible argumentée est plus solide que prétendre tout avoir déployé).

---

## 7. Couche de risque & conformité FTMO (règles à câbler en dur)

Règles de gestion voulues par l'utilisateur :
- **Risque fixe de 0,2 % du capital par trade.**
- **Maximum 5 trades par jour** (→ ~1 % de risque théorique/jour).
- Marge de sécurité sous le **drawdown journalier de 5 %** (limite FTMO) et le **drawdown max ~10 %**.

Contraintes FTMO à intégrer (vérifiées, ~2026) :
- **EA/bots autorisés** sur Challenge, Verification et comptes financés (pas de pré-approbation).
- **Interdits** : arbitrage, latency arbitrage, tick scalping, exploitation des failles plateforme, HFT.
  (Le SMC en M5/M15/M1 n'est pas concerné.)
- **Filtre news 2 minutes** : pas d'ouverture de trade dans les 2 min avant/après un événement macro à fort
  impact (Challenge/Verification). **Un filtre calendrier économique est donc OBLIGATOIRE.** (Compte *Swing* = exception, mais levier plus faible.)
- **91 % des comptes échoués dépassent le drawdown JOURNALIER** (pas la perte max) → priorité absolue à la
  gestion de la volatilité intra-journalière. Modéliser le **reset du drawdown journalier à l'heure serveur FTMO**.
- **Plafond de 400 000 $ de capital cumulé par stratégie** sur l'ensemble des comptes FTMO.
- **Levier 1:100** (Swing 1:30). Utilisateur en France (pas de restriction US).

> Note portefeuille : avec une seule stratégie par compte, la résolution de conflits entre stratégies disparaît.
> Mais si un compte trade plusieurs instruments, garder une **couche de risque niveau portefeuille** consciente
> des **corrélations** (US30/NAS100/GER40 bougent ensemble ; en crise, toutes les corrélations tendent vers 1).
> Idée valorisable : un **module de matrice de corrélation glissante** calculé en continu.

---

## 8. Données annexes : économique & sentiment

**Peut-on améliorer les perfs avec ces données ? Oui, comme FILTRE/CONTEXTE, pas comme signal d'entrée.**
(Trader la surprise d'annonce en automatique = très difficile : spread explose, slippage, algos institutionnels plus rapides.)

Lecture d'une annonce (calendrier éco) : le marché réagit à la **SURPRISE = Actuel − Prévision** (pas à la valeur absolue).
Vert = meilleur qu'attendu, rouge = moins bon. Colonne « Importance » (★★★) = filtre des événements à fort impact.

Trois usages solides :
1. **Défensif (prioritaire)** : ne pas trader dans la fenêtre dangereuse → règle FTMO 2 min. *Incontournable.*
2. **Contextuel** : pondérer la confiance dans les signaux SMC selon le biais fondamental.
3. **Régime de volatilité** : adapter la taille / resserrer les critères les jours chargés.

**Sources annexes récupérables** (par ordre utilité/effort) : calendrier économique (Trading Economics, Finnhub…),
flux news financières, positionnement/sentiment agrégé (COT de la CFTC, indices de sentiment), puis NLP sur
réseaux sociaux (lourd, incertain).
**Sentiment analysis (NLP)** = module **avancé et optionnel**, excellent pour le « V » de Variété du mémoire,
mais bruité et à ne pas mettre au cœur des décisions. À n'ajouter qu'une fois le cœur SMC validé.

---

## 9. CFD, bougies vs tick, carnet L2 (rappels conceptuels)

- **CFD (Contract For Difference)** : contrat sur la *différence* de prix sans posséder l'actif. Effet de levier,
  prix fabriqué par le broker (donc données différentes selon le broker, pas de vrai L2 central), frais = spread + swap.
  **US30 et GBP/USD chez FTMO sont des CFD** → modéliser spread & swap dans le backtest.
- **Bougie (OHLC)** = compression d'un intervalle en 4 valeurs. **On perd le chemin intra-bougie** → ambiguïté
  « SL ou TP touché en premier ? ». **Le SMC se lit sur les bougies** (donnée principale).
- **Tick-by-tick** = chaque variation de prix, ordre exact préservé. Sert à la **fidélité d'exécution**
  (ordre SL/TP, spread réel, slippage), au **live**, et à **valider** que le backtest sur bougies ne ment pas.
  Astuce éco : descendre d'une timeframe (M1 dans une bougie M5) pour approcher la résolution intra-bougie.
  ⚠️ Les stops serrés (0,2 %) rendent la validation sur tick d'autant plus importante.
- **Carnet d'ordres L2 (Depth of Market)** = profondeur (volumes à chaque niveau de prix, 2 côtés). L1 = meilleur
  bid/ask seulement. **Pas de vrai L2 pour le forex spot (OTC) ni les CFD synthétiques** → n'existe proprement
  que sur marchés centralisés (futures, actions, crypto). **Non nécessaire pour le SMC** ; pertinent surtout
  comme **argument big data** (donnée la plus lourde) si l'on choisit un instrument à vrai carnet.

---

## 10. Le fossé backtest → live

| Backtest (labo idéalisé) | Le FOSSÉ | Live / FTMO (réel) |
|---|---|---|
| Données propres | données imparfaites, latence | Flux temps réel |
| Exécution parfaite | spread variable, slippage | Exécution réelle |
| Coûts supposés | coûts réels (swap, commission) | Argent réel en jeu |
| Tourne une fois, offline | déconnexions, bugs, crashs | 24/5 sans interruption |
| — | **overfitting qui se révèle** | — |

**Le pont = paper trading / forward testing.** Point important : **le Challenge FTMO EST lui-même un forward test**
(on prouve la stratégie en réel sans risquer son argent). Chemin : backtest → paper (démo) → Challenge FTMO → financé.

**Besoins BACKTEST** : données historiques auditées (3 instruments) · 4 modules stratégie (interface commune) ·
moteur event-driven avec coûts réalistes · simulation des contraintes FTMO · risque portefeuille · métriques +
validation anti-overfitting (out-of-sample, walk-forward).

**Besoins LIVE (en plus)** : flux temps réel · connexion plateforme d'exécution · gestion des ordres (rejets,
fills partiels, modif SL/TP) · application du risque en temps réel · persistance d'état + reset journalier ·
infra de fiabilité (VPS 24/5, reconnexion, monitoring, alertes, réconciliation) · dashboard de contrôle.

**Plateformes FTMO (2026)** : MT4, MT5, cTrader, DXtrade.
- **Automatisation** : **MT5** (recommandé — Python natif, DOM, Strategy Tester multi-thread) ou **cTrader** (C#/Python).
- **DXtrade = PAS d'EA/automatisation** → à éviter pour un bot.
- Astuce : broker perso miroir de FTMO (ex. **IC Markets** — mêmes plateformes MT4/MT5/cTrader, VPS gratuit)
  pour développer/paper-trader en conditions quasi identiques → réduit le fossé.

---

## 11. Pièges méthodologiques à surveiller (transverse)

- **Overfitting** : rendre les règles mécaniques *avant* le test ; limiter les degrés de liberté ; viser des
  règles qui **généralisent** entre instruments plutôt que d'optimiser chacun finement.
- **Lookahead bias** (surtout multi-timeframe) : à l'instant T, ne consulter que des bougies de timeframe haute
  **déjà clôturées** (la bougie Daily du jour n'est pas finie → utiliser la dernière clôturée).
- **Survivorship bias** : éviter (raison de plus pour rester sur indices/devises plutôt qu'actions individuelles).
- **Qualité des données (Véracité)** : auditer les trous, classer par année ; les données diffèrent d'un broker
  à l'autre — backtester idéalement sur les données du broker cible.
- **Coûts réalistes** : ne jamais backtester à spread/slippage/commission zéro.
- **Scepticisme** envers les taux de réussite publiés ; **ventiler les métriques par instrument**.

---

## 12. Feuille de route (phases)

| Phase | Contenu | Outils | Groupe |
|---|---|---|---|
| **0 — Cadrage & formalisation** | Règles SMC, instruments, timeframes & risque figés, sans ambiguïté | Notion/Markdown, pseudo-code Python | Valider la stratégie |
| **1 — Prototype & backtest** ⭐ | MVP mono-instrument (US30), backtest offline + contraintes FTMO. *Stratégie + risque branchés ici.* | Python, pandas, smartmoneyconcepts, backtesting.py/vectorbt | Valider la stratégie |
| **2 — Industrialisation données** | Ingestion temps réel + stockage, multi-instruments (Volume/Vélocité/Variété) | Kafka, Kafka Connect, MinIO/Parquet, TimescaleDB | Construire la plateforme |
| **3 — Traitement distribué** | Détection SMC en flux + retraitement batch (Lambda) + dashboards | Spark Streaming/Flink, Spark, Grafana | Construire la plateforme |
| **4 — Service & temps réel** ⭐ | API de signaux + bot en paper trading, risque en direct. *Exécution live branchée ici.* | FastAPI/gRPC, compte démo broker | Intégrer & exécuter |
| **5 — Exécution & déploiement** | Exécution auto (paper → Challenge FTMO) + dashboard de contrôle | Docker, Kubernetes, Airflow, Prometheus | Intégrer & exécuter |

**Principe de séquencement** : tranches verticales, pas de "big bang". On **dé-risque tôt** — si le backtest
(Phase 1) invalide la stratégie, on l'apprend avant de monter la lourde plateforme. On ne construit Kafka/Spark/K8s
qu'une fois la stratégie jugée digne de cet investissement.

---

## 13. Récapitulatif des outils & technologies

- **Langage / analyse** : Python, pandas, `ta` / `pandas-ta`
- **Détection SMC** : `smartmoneyconcepts` (joshyattridge) — détecteurs (OB, FVG, BOS/CHoCH, liquidity),
  PAS une stratégie clé-en-main (il faut coder ses propres règles par-dessus)
- **Backtest** : `backtesting.py` (léger), `vectorbt` (vectorisé, balayage de paramètres), ou moteur
  **event-driven maison** (recommandé pour le SMC, séquentiel/à état, évite le lookahead)
- **Données/broker (dev & data)** : OANDA (API v20, `oandapyV20`, compte démo suffit) ou MT5 (module Python `MetaTrader5`)
- **Live FTMO** : MT5 (ou cTrader) ; broker miroir perso : IC Markets ; VPS pour le 24/5
- **Big data** : Kafka, Spark/Flink, MinIO/HDFS + Parquet, TimescaleDB/InfluxDB, FastAPI, Grafana
- **Infra** : Docker, Kubernetes, Airflow, Prometheus
- **Données annexes** : Trading Economics / Finnhub (calendrier éco), news/RSS, COT (CFTC)

---

## 14. Où continuer à creuser (fils ouverts / prochaines étapes)

Points identifiés mais **pas encore approfondis** :

1. **Phase 0 — Formaliser les règles SMC du US30** en pseudo-code non ambigu (biais D/H4, structure H1/M15,
   déclencheur M1 ; définition exacte de swing, BOS/CHoCH, OB valide, FVG, premium/discount). ← *Fondation, à faire en premier.*
2. **Interface commune de stratégie** (format d'entrée/sortie partagé par SMC + 3 baselines).
3. **Critères de sélection du "gagnant"** au backtest comparatif (rendement, régularité, drawdown,
   taux de réussite au Challenge simulé, distribution des R).
4. **Mécanique de la couche de risque** (position sizing, reset journalier, filtre news 2 min, garde-fous drawdown).
5. **Résolution de l'ordre SL/TP intra-bougie** dans le moteur de backtest.
6. **Pipeline & stockage double granularité** (bougies pour signaux, tick pour exécution/validation).
7. **Module de matrice de corrélation glissante** (risque portefeuille + argument mémoire).
8. **Optimisation walk-forward distribuée** (meilleur argument big data côté calcul).
9. **Filtre calendrier économique** (intégration concrète dans la couche de risque).
10. **Checklist d'ingénierie du passage en live** (VPS, reconnexion, monitoring, réconciliation, 24/5).
11. **Module de sentiment analysis (NLP)** pour le mémoire (V de Variété) — optionnel/avancé.
12. **Rédaction de la section architecture du mémoire** (mapping couches ↔ 5 V ; Lambda vs Kappa argumenté).

---
