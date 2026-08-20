# Plateforme Big Data de collecte et d'analyse de données financières en temps réel
## Document de cadrage — v1

**Auteur :** Romuald Noubissi
**Date :** 18 août 2026
**Horizon :** 8 semaines (rendu visé ~18 octobre 2026)
**Statut :** proposition soumise à validation de l'encadrant

---

## 1. Problématique et objectifs

### 1.1 Contexte

Les marchés financiers produisent des flux de données continus, hétérogènes et à forte vélocité. Exploiter ces flux pour en extraire des signaux exploitables suppose une infrastructure capable de **collecter**, **valider**, **stocker** et **analyser** ces données à la fois **en temps réel** (pour la décision) et **en rejeu historique** (pour la validation méthodologique).

### 1.2 Question de recherche

> **Peut-on concevoir une plateforme de données capable d'ingérer des flux financiers hétérogènes en temps réel, d'en garantir la qualité, et d'y appliquer un module d'analyse dont on mesure objectivement la valeur ?**

Le module d'analyse retenu comme cas d'usage est la détection automatique de figures issues du **Smart Money Concept (SMC)** — une méthodologie d'analyse technique aujourd'hui pratiquée de façon **discrétionnaire et visuelle**. La sous-question, mesurable, devient :

> **Ces figures (Order Blocks, Fair Value Gaps, ruptures de structure) sont-elles formalisables en règles strictement mécaniques, et présentent-elles des propriétés statistiques significatives ?**

Cette formulation est importante : **un résultat négatif reste un résultat scientifique valide**. L'évaluation porte sur la plateforme et la rigueur de la démarche, non sur la rentabilité d'une stratégie de trading.

### 1.3 Objectifs

| # | Objectif | Critère de réussite |
|---|---|---|
| O1 | Collecter des données financières multi-sources en temps réel | Pipeline opérationnel 24/7, débit et latence mesurés |
| O2 | Garantir la qualité des données ingérées | Suite de contrôles automatisés + rapport de qualité chiffré |
| O3 | Stocker à deux granularités (historique froid / séries chaudes) | Data lake partitionné + base temps-série requêtable |
| O4 | Produire des analyses financières distribuées | Analyses statistiques + optimisation distribuée mesurée |
| O5 | Restituer via API et visualisations | API documentée + dashboards temps réel et analytiques |
| O6 | Sécuriser la chaîne de bout en bout | Authentification, chiffrement, traçabilité, analyse de risques |

---

## 2. Périmètre assumé

Contrainte structurante : **8 semaines**, avec l'exigence que **l'ensemble du périmètre annoncé soit réellement déployé et fonctionnel**. Le périmètre est donc volontairement resserré autour d'un chemin critique cohérent.

### 2.1 Dans le périmètre

- Collecte temps réel multi-sources (crypto 24/7 + forex/CFD + macro-économique)
- Collecte batch d'historiques (tick et bougies)
- Pipeline de validation qualité avec mise en quarantaine
- Stockage en architecture medallion (data lake + base temps-série)
- Traitement distribué Spark : streaming et batch
- Module d'analyse SMC (détection + statistiques descriptives)
- Moteur de backtest avec coûts réalistes + stratégies de référence
- Optimisation walk-forward distribuée
- API REST + dashboards opérationnels et analytiques
- Sécurisation complète de la chaîne + analyse de risques
- Orchestration et supervision



---

## 3. Axe A — Les données

### 3.1 Sources retenues

| Source | Type | Fréquence | Mode | Rôle |
|---|---|---|---|---|
| **Binance** (WebSocket public) | Trades + carnet L2, BTC/USDT | temps réel, ~ms | Streaming | Banc d'essai vélocité et volume, disponibilité 24/7 |
| **OANDA v20** (compte démo) | Prix GBP/USD, XAU/USD | temps réel, tick | Streaming | Flux forex de référence |
| **Dukascopy / HistData** | Historique tick et M1 | archives | Batch | Backtest et analyses historiques |
| **Finnhub / Trading Economics** | Calendrier économique | événementiel | Batch + polling | Filtre de fenêtres à risque, event studies |
| **CFTC (COT)** | Positionnement institutionnel | hebdomadaire | Batch | Contexte de marché |

**Justification du choix crypto.** Les marchés forex et indices sont fermés le week-end, ce qui rendait impossibles le développement et la démonstration du temps réel hors session de bourse. Le flux Binance apporte simultanément : la disponibilité continue, un **volume échangé réel** et un **carnet d'ordres L2 authentique** — tous deux absents des CFD. Il démontre en outre que la plateforme est agnostique à la classe d'actifs.

### 3.2 Volumétrie estimée

| Jeu de données | Ordre de grandeur | Format cible |
|---|---|---|
| Bougies M1 — 3 instruments x 10 ans | ~11 M lignes, 150–300 Mo | Parquet + zstd |
| Ticks forex — 3 instruments x 5 ans | ~10–25 Go | Parquet partitionné |
| Carnet L2 Binance — flux continu | ~1–5 Go/jour | Parquet partitionné à l'heure |
| Calendrier + COT + news | < 100 Mo | Parquet / JSON |

**Position méthodologique assumée.** Le volume seul ne suffit pas à qualifier ce projet de « big data ». La démonstration s'appuie sur **quatre appuis mesurés**, chacun documenté par des chiffres :

1. **Vélocité** — débit d'ingestion (msg/s), latence bout-en-bout p50/p95/p99 du tick au signal
2. **Volume** — le flux L2 crypto, seule source atteignant le régime de plusieurs Go/jour
3. **Calcul distribué** — l'optimisation walk-forward : N jeux de paramètres x M fenêtres x 3 instruments, soit plusieurs milliers de backtests. C'est ici que la distribution devient nécessaire, non optionnelle
4. **Scalabilité prouvée** — courbe de speedup Spark mesurée sur 1 / 2 / 4 / 8 nœuds

### 3.3 Qualité des données (Véracité)

Six dimensions, chacune outillée par un contrôle automatisé exécuté à l'ingestion :

| Dimension | Contrôle |
|---|---|
| **Complétude** | Bougies manquantes confrontées au calendrier de session ; distinction fermeture normale / anomalie |
| **Validité** | Cohérence OHLC (`low <= open, close <= high`), prix strictement positifs, volumes non négatifs |
| **Unicité** | Absence de doublons sur la clé (instrument, timeframe, timestamp) |
| **Cohérence** | Agrégat M5 recalculé identique à la somme des 5 bougies M1 correspondantes |
| **Exactitude** | Recoupement multi-sources sur périodes communes (OANDA vs Dukascopy) |
| **Fraîcheur** | Latence d'ingestion mesurée en continu, alerte au-delà d'un seuil |

**Outillage :** `pandera` pour les schémas, `Great Expectations` pour les suites d'attentes et les rapports.

**Politique de rejet :** aucune donnée invalide n'est écartée silencieusement. Tout enregistrement en échec part en **quarantaine** — topic Kafka dédié (dead-letter) et table de suivi — puis alimente un rapport de qualité ventilé par instrument et par année, livré comme chapitre du mémoire.

**Difficultés spécifiquement traitées :** conversion et normalisation des fuseaux horaires (heure broker vers UTC), changements d'heure saisonniers, ticks aberrants, discontinuités de week-end, divergences inter-brokers.

### 3.4 Chaîne de traitement

```
Acquisition  ->  Normalisation (UTC, schéma unifié)  ->  Déduplication  ->  Validation qualité
   ->  Agrégation multi-timeframe (M1 vers M5, M15, H1, H4, D)
   ->  Enrichissement (indicateurs, features SMC)
   ->  Publication (data lake + base temps-série)
```

**Décision structurante :** seule la granularité la plus fine est collectée (tick ou M1). **Toutes les timeframes supérieures sont recalculées par la plateforme.** Cela garantit la cohérence inter-timeframes — indispensable à l'analyse multi-échelles — et supprime une source classique de biais d'anticipation (*lookahead bias*).

---

## 4. Axe B — Le stockage

### 4.1 Architecture medallion

```
   BRONZE — brut, immuable                MinIO (S3) / Parquet
   Ce que la source a émis, jamais modifié. Rejouable intégralement.
        |  validation + nettoyage
        v
   SILVER — validé, normalisé             MinIO (S3) / Parquet partitionné
   Bougies multi-timeframes, qualité garantie, schéma stable.
        |  agrégation + calcul de features
        v
   GOLD — prêt à la consommation          TimescaleDB
   Séries requêtables, signaux détectés, métriques, résultats de backtest.
```

Cette organisation épouse le pattern **Lambda** retenu : la couche *batch* reconstruit Silver et Gold depuis Bronze ; la couche *speed* alimente Gold directement depuis le flux.

### 4.2 Choix technologiques et alternatives écartées

| Composant | Retenu | Justification | Écarté |
|---|---|---|---|
| Stockage objet | **MinIO** | Compatible S3, donc portable vers un cloud sans réécriture ; léger à opérer | HDFS : coût d'exploitation disproportionné |
| Format de fichier | **Parquet + zstd** | Colonnaire, compressé, partitionné par `instrument/année/mois` | CSV : volume et temps de lecture prohibitifs |
| Base temps-série | **TimescaleDB** | Extension PostgreSQL : hypertables, agrégats continus, compression native — **et SQL standard**, ce qui branche Grafana et l'API directement. Les entités relationnelles (signaux, backtests) cohabitent dans la même base | InfluxDB : performant en série, faible en relationnel |
| Cache d'état | **Redis** | État chaud de la couche speed : dernier prix, compteurs glissants | — |
| Bus de messages | **Kafka (mode KRaft)** | Découplage producteurs/consommateurs, rejeu, partitionnement, tolérance aux pannes | RabbitMQ : pas de rétention ni de rejeu |

### 4.3 Mesure à produire

Un **benchmark de stockage** comparant, sur un même jeu de données : CSV brut, Parquet non compressé, Parquet + snappy, Parquet + zstd — sur trois métriques (taille disque, temps d'écriture, temps de requête sélective). Résultat chiffré destiné au mémoire.

---

## 5. Axe C — Analyses et visualisations

### 5.1 Analyses produites

| # | Analyse | Nature | Visualisation |
|---|---|---|---|
| A1 | Qualité des données : complétude par année, anomalies détectées | Descriptive | Heatmap année x mois, barres empilées |
| A2 | Volatilité par session (Asie / Londres / New York), ATR, saisonnalité intra-journalière | Descriptive | Heatmap heure x jour, boxplots |
| A3 | Microstructure : spread moyen par heure, slippage estimé | Descriptive | Série temporelle, distribution |
| A4 | **Matrice de corrélation glissante** entre instruments | Multivariée | Matrice animée, série du coefficient |
| A5 | **Statistiques SMC** : fréquence des BOS/CHoCH/OB/FVG par timeframe, **taux de comblement des Fair Value Gaps**, délai avant mitigation | Inférentielle | Histogrammes, courbes de survie, chandeliers annotés |
| A6 | **Event study macro** : réaction du prix à plus ou moins 30 min autour des annonces à fort impact, segmentée par ampleur de surprise | Inférentielle | Courbes moyennes superposées, cône de dispersion |
| A7 | Performance comparée des stratégies : equity, drawdown, distribution des gains, Sharpe / Sortino / Calmar, profit factor — **ventilés par instrument** | Évaluative | Equity curve, underwater plot, tableau comparatif |
| A8 | **Walk-forward** : robustesse des paramètres, in-sample vs out-of-sample | Évaluative | Heatmap de paramètres, courbes appariées |

**A5 et A6 constituent le cœur scientifique du travail.** « Les Fair Value Gaps sont-ils effectivement comblés, dans quelle proportion et à quelle échéance ? » est une hypothèse **falsifiable**, testable statistiquement, et indépendante de toute considération de rentabilité.

### 5.2 Restitution — deux niveaux, deux publics

| Niveau | Outil | Contenu | Public |
|---|---|---|---|
| **Opérationnel** | **Grafana** | Prix live, débit Kafka, latence bout-en-bout, santé des jobs Spark, alertes qualité, taux de rejet | Exploitation — preuve du temps réel |
| **Analytique** | **Streamlit** | Chandeliers avec surimpression des figures SMC, exploration des backtests, comparaison de stratégies | Analyse métier |

Grafana est alimenté directement en SQL depuis TimescaleDB. Streamlit consomme l'API FastAPI. Une évolution vers un front **Next.js + TradingView lightweight-charts** est identifiée comme perspective, hors périmètre des 8 semaines.

**Types de visualisations mobilisés :** chandeliers annotés, séries temporelles multi-échelles, heatmaps, histogrammes et estimations de densité, boxplots, matrices de corrélation, courbes d'equity et underwater plots, nuages de points, jauges et indicateurs clés, diagrammes de flux du pipeline.

---

## 6. Axe D — Sécurité des pipelines

La sécurité est traitée comme une **exigence transverse appliquée dès la première semaine**, non comme une phase terminale. Sept couches, toutes effectivement déployées.

| # | Couche | Mise en œuvre |
|---|---|---|
| 1 | **Gestion des secrets** | Aucune clé en dur. Variables d'environnement hors dépôt + **Docker secrets** ; chiffrement des fichiers sensibles versionnés via **SOPS + age**. Procédure de rotation documentée |
| 2 | **Chiffrement en transit** | TLS de bout en bout : Kafka (SSL), API (HTTPS via reverse proxy), MinIO (TLS), PostgreSQL (SSL) |
| 3 | **Authentification / autorisation** | Kafka : **SASL/SCRAM + ACL par topic** — un collecteur ne dispose que du droit d'écriture sur son propre topic. MinIO : politiques IAM par bucket. PostgreSQL : rôles à moindre privilège (Grafana en lecture seule). API : **OAuth2 / JWT** + limitation de débit |
| 4 | **Chiffrement au repos** | Chiffrement côté serveur des buckets MinIO (SSE), chiffrement du volume de données |
| 5 | **Segmentation réseau** | Réseaux Docker cloisonnés (ingestion / traitement / exposition). Aucun broker ni base exposé publiquement ; reverse proxy unique en frontal ; règles de pare-feu explicites côté VM |
| 6 | **Intégrité du pipeline** | **Schema Registry** (Avro + règles de compatibilité) : une donnée non conforme au contrat ne peut pas entrer. Producteurs idempotents, déduplication, **dead-letter queue**, checkpointing Spark, capacité de rejeu depuis Bronze |
| 7 | **Traçabilité et audit** | Journalisation structurée centralisée, **journal d'audit en ajout seul** des signaux émis (chaînage par empreinte cryptographique), traçabilité de la lignée des données |

### 6.1 Analyse de risques

Une **analyse STRIDE** est conduite sur le pipeline (usurpation, altération, répudiation, divulgation, déni de service, élévation de privilège). Trois menaces spécifiques au domaine sont traitées explicitement :

- **Empoisonnement d'une source de prix** — une source compromise ou défaillante injecte des cotations erronées. *Contre-mesure :* recoupement multi-sources et bornes de plausibilité à l'ingestion.
- **Indisponibilité ou limitation d'une API externe** — dépassement de quota, coupure fournisseur. *Contre-mesure :* limitation de débit côté client, back-off exponentiel, mise en cache, dégradation contrôlée.
- **Dépendance à une source unique** — point de défaillance unique sur la donnée de marché. *Contre-mesure :* redondance des sources sur les instruments critiques.

### 6.2 Chaîne d'approvisionnement logicielle

Images Docker épinglées par version, analyse de vulnérabilités **Trivy**, audit des dépendances Python (`pip-audit`), exécution en conteneur non privilégié et en utilisateur non root.

### 6.3 Conformité

Les données de marché ne constituent pas des données à caractère personnel. La question du **RGPD** est néanmoins traitée dans le mémoire au titre de l'extension NLP envisagée : toute collecte de contenus issus de réseaux sociaux imposerait une anonymisation et une base légale — ce qui participe à la décision de l'écarter.

---

## 7. Architecture cible

```
+-- SOURCES ---------------------------------------------------------------+
|  Binance WS (L2 + trades)   OANDA v20 (tick)   Calendrier éco   COT       |
+----------+-----------------------+-----------------+---------------------+
           |  temps réel           |                 |  batch
           v                       v                 v
+-- INGESTION -------------------------------------------------------------+
|  Producteurs Python  ->  APACHE KAFKA (KRaft, SASL/SCRAM + TLS + ACL)     |
|  Schema Registry (Avro)              Dead-letter topic (quarantaine)      |
+----------+-----------------------------------------+--------------------+
           |                                          |
   +-------v---------+                      +---------v--------+
   | COUCHE SPEED    |                      | COUCHE BATCH     |
   | Spark Streaming |                      | Spark (batch)    |
   | validation      |                      | agrégation       |
   | agrégation live |                      | features SMC     |
   | détection SMC   |                      | backtest         |
   +-------+---------+                      | walk-forward     |
           |                                +---------+--------+
           |        +--- MinIO / Parquet --------------+
           |        |    BRONZE  ->  SILVER            |
           v        v                                  v
+-- STOCKAGE SERVANT ------------------------------------------------------+
|  TimescaleDB (GOLD : séries, signaux, backtests)     Redis (état chaud)   |
+----------+---------------------------------------------------------------+
           v
+-- SERVICE & RESTITUTION -------------------------------------------------+
|  FastAPI (OAuth2/JWT, HTTPS)  ->  Streamlit (analytique)                  |
|  Grafana (opérationnel, temps réel)                                       |
+--------------------------------------------------------------------------+

Transverse :  Prefect (orchestration)  |  Prometheus + Grafana (supervision)
              Docker Compose (déploiement)  |  Trivy / pip-audit (sécurité)
```

### 7.1 Correspondance couches / 5 V

| V | Porté par | Mesure de la démonstration |
|---|---|---|
| **Volume** | Flux L2 Binance, data lake Parquet | Volumétrie cumulée, taux de compression |
| **Vélocité** | Kafka + Spark Structured Streaming | Débit (msg/s), latence p50/p95/p99 |
| **Variété** | 5 familles de sources hétérogènes | Nombre de schémas, formats et fréquences distincts |
| **Véracité** | Pipeline qualité + quarantaine | Taux de conformité, rapport de qualité par instrument |
| **Valeur** | Module SMC + API de signaux + analyses | Résultats statistiques A5/A6, comparatif de stratégies |

### 7.2 Lambda plutôt que Kappa

L'architecture **Lambda** est retenue car le cas d'usage exige de **rejouer l'historique** (backtest, walk-forward, ré-analyse après correction de règles) — une capacité de rejeu massif que l'approche Kappa, centrée sur un flux unique, rend coûteuse. Le surcoût classique de Lambda, à savoir la double implémentation de la logique métier, est ici **fortement atténué** : les couches speed et batch reposent sur le même moteur (Spark) et partagent le même code de détection SMC.

---

## 8. Environnement d'exécution

| Environnement | Ressource | Usage |
|---|---|---|
| **Poste de développement** | 16 Go RAM, Docker Compose par profils | Développement, tests unitaires, itérations |
| **VM GCP `e2-standard-4`** | 4 vCPU / 16 Go, Docker Compose complet | Collecte continue 24/7, démonstration permanente, supervision |
| **GCP Dataproc (éphémère)** | Cluster 2 à 8 nœuds, ~3 h au total | Mesure du speedup du walk-forward distribué, puis destruction |

Le recours à Dataproc est **ponctuel et ciblé** : il sert exclusivement à produire la courbe de scalabilité horizontale, seule preuve empirique de la capacité de la plateforme à passer à l'échelle. Coût estimé : environ 10 €, couvert par les crédits d'essai GCP.

---

## 9. Planning — 8 semaines

| Sem. | Dates | Contenu | Livrable vérifiable |
|---|---|---|---|
| **S1** | 18–24 août | Cadrage : règles SMC formalisées en pseudo-code, téléchargement d'échantillons réels et **mesure de la volumétrie effective**, socle Docker Compose (Kafka, MinIO, TimescaleDB, Grafana), sécurité de base (secrets, réseaux, moindre privilège) | La stack démarre, les sources sont validées |
| **S2** | 25–31 août | **Chaîne temps réel de bout en bout** : producteurs Binance + OANDA vers Kafka, puis Spark Streaming, puis TimescaleDB, puis dashboard Grafana live | **Démonstration temps réel fonctionnelle** |
| **S3** | 1–7 sept | Ingestion batch des historiques vers Bronze/Silver, agrégation multi-timeframe Spark, **pipeline qualité + quarantaine** | Dataset auditable + rapport de qualité |
| **S4** | 8–14 sept | Module de détection SMC, **analyses A1 à A5**, calendrier économique et **event study A6** | Résultats statistiques SMC |
| **S5** | 15–21 sept | Moteur de backtest event-driven (spread, slippage, commissions), stratégies de référence, métriques A7 | Comparatif chiffré des stratégies |
| **S6** | 22–28 sept | **Walk-forward distribué**, campagne Dataproc, **benchmarks** (speedup, débit, latence, stockage), détection SMC en streaming | Courbes de scalabilité |
| **S7** | 29 sept–5 oct | API FastAPI (OAuth2/JWT), Streamlit, **durcissement sécurité complet** (TLS, SASL/ACL, Schema Registry, Trivy), Prefect, Prometheus, **analyse STRIDE** | Plateforme complète et sécurisée |
| **S8** | 6–12 oct | Rédaction du mémoire, préparation de la démonstration, répétition de soutenance | Mémoire + support |
| *Marge* | 13–18 oct | Réserve pour aléas et finitions | — |

**Principes de séquencement :**

1. **Le temps réel est livré en S2.** Il figure dans l'intitulé du sujet : c'est le chemin critique, il est sécurisé au plus tôt.
2. **Chaque semaine produit un livrable présentable isolément.** Un arrêt prématuré laisse un projet cohérent, jamais un chantier ouvert.
3. **La sécurité commence en S1** (secrets, cloisonnement, moindre privilège) ; S7 est une semaine de *durcissement* et de formalisation, non de découverte.
4. **La rédaction est continue**, non concentrée en S8 : chaque semaine alimente la section correspondante du mémoire.

---

## 10. Risques identifiés et mitigations

| Risque | Prob. | Impact | Mitigation |
|---|---|---|---|
| Historique tick indisponible sur US30 (CFD) | Moyenne | Moyen | **Levé en S1** par téléchargement d'échantillons réels avant tout engagement. Repli : GBP/USD et BTC/USDT en instruments principaux |
| Saturation mémoire du poste (16 Go) | Élevée | Moyen | Profils Docker Compose ; exécution continue déportée sur la VM GCP |
| Formalisation SMC plus longue que prévu | Moyenne | Élevé | Périmètre limité à **un seul setup et un seul instrument** en S4 ; extension seulement si avance |
| Instabilité des API externes | Moyenne | Faible | Back-off exponentiel, mise en cache, redondance des sources |
| Glissement du planning | Moyenne | Élevé | Ordre de sacrifice défini à l'avance : raffinement SMC, puis stratégies de référence, puis front analytique. Le pipeline temps réel n'est jamais dégradé |

---

## 11. Points à valider avec l'encadrant

1. **Le périmètre écarté (section 2.2) est-il acceptable ?** Kubernetes et Flink sont exclus au profit d'un livrable intégralement fonctionnel dans le délai imparti.
2. **L'ajout d'une source crypto** comme banc d'essai technique de la plateforme est-il validé ?
3. **La question de recherche (section 1.2)** correspond-elle au niveau d'exigence attendu ?
4. **Le recours au cloud GCP** (VM continue + Dataproc éphémère) est-il compatible avec le cadre de l'école ?
5. **Format et volume attendus du mémoire**, et date exacte de la soutenance.

---

*Document de travail — version 1. Les décisions consignées ici restent révisables jusqu'à la fin de la semaine 1.*
