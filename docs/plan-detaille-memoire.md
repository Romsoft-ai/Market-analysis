# Conception d'une plateforme de big data de collecte et d'analyse de données financières en temps réel

### Projet de Fin d'Études : plan détaillé

**Digital School of Paris**
**Auteur :** Romuald Noubissi
**Date :** 19 août 2026
**Document :** cadrage et sommaire détaillé du mémoire, soumis à validation de l'encadrant

---

## 1. Le projet en une page

### 1.1 Ce que je construis

Une **plateforme de données financières** qui collecte, valide, stocke et analyse des flux de marché, en rejeu historique comme en temps réel. S'y ajoute un **cas d'usage démonstrateur** qui l'exploite pour produire des décisions de marché automatisées.

Le projet comporte donc **deux volets indissociables** :

| | Volet | Nature | Question à laquelle il répond |
|---|---|---|---|
| **A** | **La plateforme** | Infrastructure de données | *Peut-on collecter, fiabiliser et analyser des flux financiers hétérogènes à l'échelle et en continu ?* |
| **B** | **La valeur** | Application décisionnelle | *Cette infrastructure permet-elle de produire des décisions mesurablement meilleures que le hasard ?* |

Le volet A constitue l'objet du mémoire. Le volet B en est la **preuve d'utilité**, car une plateforme de données ne vaut que par ce qu'elle permet de décider.

### 1.2 La direction prise

Le fil conducteur du travail est la **fiabilité de la mesure**, non la performance financière.

En finance quantitative, l'erreur la plus coûteuse n'est pas de se tromper : c'est de produire un résultat **crédible et faux**. Un jeu de données mal compris, un indicateur mal calculé ou une simulation trop optimiste produisent des courbes convaincantes qui ne survivent pas au réel. L'ensemble du projet est construit contre ce risque.

Cela se traduit par trois partis pris.

1. **Mesurer avant de supposer.** Aucun paramètre n'est admis sans vérification sur les données réelles : profondeur d'historique, coûts de transaction, fuseaux horaires, authenticité des cotations.
2. **Rendre la tricherie structurellement impossible.** Les composants sont conçus pour que l'anticipation involontaire du futur (le *lookahead bias*) ne puisse pas se produire par distraction.
3. **Figer avant de tester.** Les règles de décision sont écrites et gelées avant tout test, afin que le résultat mesure une hypothèse plutôt qu'il ne la fabrique.

### 1.3 Positionnement du résultat attendu

Le succès du projet ne se mesure pas à la rentabilité de la stratégie étudiée. **Un résultat négatif rigoureusement établi reste un résultat valide.** Démontrer qu'une méthode d'analyse répandue ne produit pas d'avantage mesurable a autant de valeur scientifique que l'inverse.

---

## 2. Problématique et question de recherche

### 2.1 Contexte

Les marchés financiers produisent des flux continus, hétérogènes et à forte variabilité de débit. Les exploiter suppose une infrastructure capable de traiter simultanément deux régimes : le **temps réel**, pour la décision, et le **rejeu historique**, pour la validation méthodologique. Ces deux régimes ont des contraintes opposées, latence contre exhaustivité, ce qui constitue la difficulté architecturale centrale.

### 2.2 Question de recherche principale

> **Comment concevoir une plateforme capable d'ingérer des flux financiers hétérogènes en temps réel, d'en garantir la qualité de manière mesurable, et d'y appliquer des modules d'analyse dont on puisse évaluer objectivement l'apport ?**

### 2.3 Question secondaire, mesurable

Le cas d'usage retenu est la détection automatique de figures issues du **Smart Money Concept (SMC)**, méthodologie d'analyse technique aujourd'hui pratiquée de manière **discrétionnaire et visuelle**. D'où la question dérivée :

> **Ces figures sont-elles formalisables en règles strictement mécaniques, et présentent-elles des propriétés statistiques significatives une fois formalisées ?**

Cette formulation est falsifiable : les données peuvent l'infirmer.

### 2.4 Démarche

Une démarche **incrémentale à tranches verticales**. Chaque étape produit une chaîne complète et fonctionnelle, de la donnée brute au résultat, plutôt que des composants isolés assemblés en fin de parcours. Cette approche permet de détecter tôt les erreurs de conception, quand elles coûtent encore peu.

---

## 3. Architecture d'ensemble

```
┌── SOURCES ───────────────────────────────────────────────────────────────┐
│  Prix (MetaTrader 5)   Calendrier économique   Actualités   Positionnement│
└──────────┬──────────────────────┬──────────────────────┬─────────────────┘
           │ temps réel           │ événementiel         │ batch
           ▼                      ▼                      ▼
┌── INGESTION & QUALITÉ ───────────────────────────────────────────────────┐
│  Normalisation UTC · Déduplication · Contrôles de validité                │
│  Mise en quarantaine des enregistrements non conformes                    │
└──────────┬───────────────────────────────────────┬──────────────────────┘
           │                                        │
   ┌───────▼────────┐                      ┌────────▼────────┐
   │  COUCHE TEMPS  │                      │  COUCHE BATCH   │
   │      RÉEL      │                      │                 │
   │  agrégation    │                      │  historique     │
   │  détection     │                      │  backtest       │
   │  signaux       │                      │  optimisation   │
   └───────┬────────┘                      └────────┬────────┘
           │                                        │
           ▼                                        ▼
┌── STOCKAGE ──────────────────────────────────────────────────────────────┐
│  Données brutes immuables  →  Données validées  →  Données servies        │
└──────────┬───────────────────────────────────────────────────────────────┘
           ▼
┌── RESTITUTION ───────────────────────────────────────────────────────────┐
│  API de service   Tableaux de bord opérationnels   Interface analytique   │
└──────────┬───────────────────────────────────────────────────────────────┘
           ▼
┌── VALEUR : DÉCISION DE MARCHÉ ───────────────────────────────────────────┐
│  Stratégies  →  Couche de risque  →  Exécution simulée ou réelle          │
└──────────────────────────────────────────────────────────────────────────┘
```

**Le pattern retenu est de type Lambda** : deux chemins de traitement partagent la même logique métier, l'un optimisé pour la latence, l'autre pour l'exhaustivité et la capacité de rejeu. Ce choix est justifié par le besoin de **rejouer l'historique** après correction d'une règle, capacité qu'une architecture à flux unique rend coûteuse.

---

## 4. Sommaire détaillé du mémoire

### Introduction

- Contexte économique et technique
- Problématique
- Question de recherche et hypothèses
- Démarche et structure du document

---

### PARTIE I. LA PLATEFORME : COLLECTER, FIABILISER, STOCKER

#### Chapitre 1. État de l'art et cadrage
- 1.1 Nature des données financières : granularités et formats
  *(tick, bougie OHLC, carnet d'ordres ; ce que chaque représentation conserve et ce qu'elle perd)*
- 1.2 Architectures de données temps réel : comparaison Lambda / Kappa
- 1.3 Contraintes propres au domaine financier : latence, intégrité, auditabilité
- 1.4 Périmètre retenu et éléments écartés, avec justification

#### Chapitre 2. Collecte multi-sources
- 2.1 Cartographie des sources et typologie
- 2.2 Le protocole MetaTrader 5 : architecture client-serveur, capacités, limites
- 2.3 Ingestion par lots : reconstitution de l'historique
- 2.4 Ingestion en continu : flux temps réel
- 2.5 Contrats de données et gestion de l'évolution des schémas
- 2.6 Difficultés rencontrées et solutions apportées

#### Chapitre 3. Qualité des données
- 3.1 Six dimensions retenues : complétude, validité, unicité, cohérence, exactitude, fraîcheur
- 3.2 Instrumentation : contrôles automatisés à l'ingestion
- 3.3 Politique de rejet et mise en quarantaine
- 3.4 **Étude de cas : trois pièges rencontrés et mesurés**
  - 3.4.1 Un plafond de configuration masquant 99 % de l'historique
  - 3.4.2 Une interface renvoyant la donnée la plus proche au lieu d'un résultat vide
  - 3.4.3 Un historique « ancien » ne provenant pas du fournisseur annoncé
- 3.5 Rapport de qualité ventilé par instrument et par année

#### Chapitre 4. Stockage
- 4.1 Architecture en couches : brut immuable, validé, servi
- 4.2 Choix technologiques et alternatives écartées
- 4.3 Modèle de données : séries temporelles, signaux, résultats
- 4.4 Partitionnement, compression et politique de rétention
- 4.5 Évaluation comparative des formats de stockage

---

### PARTIE II. L'ANALYSE : TRANSFORMER LA DONNÉE EN CONNAISSANCE

#### Chapitre 5. Traitement et enrichissement
- 5.1 Normalisation temporelle : fuseaux serveur, UTC, changements d'heure
- 5.2 Agrégation multi-échelles et garantie de cohérence
- 5.3 Calcul d'indicateurs : implémentation maîtrisée et vérifiée
- 5.4 Passage à l'échelle : traitement distribué et parallélisation

#### Chapitre 6. Analyses exploratoires
- 6.1 Structure temporelle de la volatilité : sessions, heures, jours
- 6.2 Microstructure : écart acheteur-vendeur, coûts réels de transaction
- 6.3 Dépendances entre instruments : matrice de corrélation glissante
- 6.4 Étude d'événements : comportement du prix autour des annonces macro-économiques
- 6.5 **Analyse statistique des figures SMC** : fréquence, taux de réalisation, délai
- 6.6 Synthèse : ce que les données disent avant toute stratégie

#### Chapitre 7. Visualisation et restitution
- 7.1 Deux publics, deux niveaux de restitution
- 7.2 Tableaux de bord opérationnels : santé du système, débit, latence, qualité
- 7.3 Interface analytique : exploration des marchés et des résultats
- 7.4 Typologie des représentations retenues et justification
- 7.5 Interface de service : accès programmatique aux données et aux signaux

---

### PARTIE III. LA VALEUR : DÉCIDER SUR LES MARCHÉS

#### Chapitre 8. Formalisation des stratégies
- 8.1 Le contrat de stratégie : rendre les approches interchangeables
- 8.2 Séparation des responsabilités : décider *où*, décider *combien*
- 8.3 Les trois stratégies de référence
- 8.4 Le Smart Money Concept : du discrétionnaire au mécanique
- 8.5 Prévention du sur-apprentissage : figer les règles avant de tester

#### Chapitre 9. Simulation et fidélité
- 9.1 Architecture du moteur : une logique unique, deux modes d'exécution
- 9.2 Modélisation des coûts réels
- 9.3 Le problème de la résolution intra-bougie et sa gestion
- 9.4 Couche de risque : dimensionnement, garde-fous, contraintes réglementaires
- 9.5 Filtre événementiel : exclusion des fenêtres à risque

#### Chapitre 10. Évaluation comparative
- 10.1 Métriques retenues et justification
- 10.2 Protocole expérimental : échantillons, périodes, validation glissante
- 10.3 Délimitation du domaine de validité des données
- 10.4 Résultats comparés
- 10.5 Critères de sélection et décision

#### Chapitre 11. Mise en production
- 11.1 Du rejeu historique au temps réel : ce qui change et ce qui ne change pas
- 11.2 Déploiement, conteneurisation, exploitation continue
- 11.3 Sécurité de la chaîne de traitement
- 11.4 Supervision, journalisation et traçabilité

---

### Conclusion

- Résultats obtenus, volet par volet
- Limites méthodologiques assumées
- Perspectives d'extension

### Annexes

- A. Rapport de qualité des données
- B. Spécification des règles de décision
- C. Mesures de performance de la plateforme
- D. Glossaire

---

## 5. Les données

### 5.1 Sources retenues

| Famille | Contenu | Fréquence | Mode | Rôle |
|---|---|---|---|---|
| **Prix** | Cotations, bougies, ticks | milliseconde | continu et par lots | Donnée principale |
| **Macro-économique** | Calendrier des annonces | événementiel | par lots | Filtre des fenêtres à risque |
| **Actualité** | Flux d'information | horaire | par lots | Contexte |
| **Positionnement** | Engagements institutionnels | hebdomadaire | par lots | Contexte |

Ces quatre familles ont des **structures et des fréquences incompatibles** : une série régulière, des événements ponctuels, du texte, un rapport périodique. Les rapprocher dans une même chronologie constitue une part significative du travail d'ingénierie.

### 5.2 Instruments

Quatre instruments couvrant trois classes d'actifs décorrélées : un **indice actions**, une **paire de devises**, un **métal précieux** et une **crypto-monnaie**. Le choix privilégie des marchés à moteurs distincts plutôt qu'un grand nombre d'instruments redondants.

### 5.3 Volumétrie

| Jeu de données | Ordre de grandeur |
|---|---|
| Bougies fines, 4 instruments, historique complet | 10 à 15 millions de lignes |
| Ticks, fenêtre de validation | plusieurs dizaines de millions d'enregistrements |
| Données de contexte | quelques dizaines de milliers d'enregistrements |
| Cache d'historique déjà constitué localement | **5,3 Go** |

**Position méthodologique assumée.** Le volume seul ne qualifie pas ce travail de « big data », et le mémoire ne le prétendra pas. La justification repose sur quatre appuis **mesurés** :

| Appui | Ce qui est mesuré |
|---|---|
| **Vélocité** | Débit d'ingestion, latence de bout en bout |
| **Variabilité** | Rapport entre débit calme et débit lors d'une annonce macro |
| **Variété** | Nombre de structures et de fréquences distinctes intégrées |
| **Charge de calcul** | Temps d'une campagne d'optimisation, gain apporté par la distribution |

Le deuxième appui est le plus caractéristique du domaine. Le débit n'est pas constant : il **explose lors des annonces économiques**. Un système dimensionné pour la moyenne défaille précisément au moment le plus important, ce qui justifie une architecture capable d'absorber les rafales.

### 5.4 Qualité : dispositif

| Dimension | Contrôle appliqué |
|---|---|
| **Complétude** | Écarts confrontés au calendrier des sessions, avec distinction entre fermeture normale et anomalie |
| **Validité** | Cohérence interne des bougies, positivité des prix |
| **Unicité** | Absence de doublons sur la clé temporelle |
| **Cohérence** | Un agrégat recalculé doit égaler la somme de ses composants |
| **Exactitude** | Recoupement entre deux fournisseurs indépendants |
| **Fraîcheur** | Latence d'ingestion surveillée en continu |

**Aucune donnée non conforme n'est écartée silencieusement.** Tout enregistrement en échec est mis en quarantaine et comptabilisé, alimentant un rapport de qualité qui constitue un livrable à part entière.

---

## 6. Le traitement

### 6.1 Chaîne de transformation

```
   Acquisition
        ↓
   Normalisation temporelle       (heure serveur vers UTC)
        ↓
   Déduplication
        ↓
   Contrôles de validité          (conformes : suite  |  non conformes : quarantaine)
        ↓
   Agrégation multi-échelles      (granularité fine vers échelles supérieures)
        ↓
   Enrichissement                 (indicateurs, figures détectées)
        ↓
   Publication                    (stockage servi, interface de service)
```

### 6.2 Deux décisions structurantes

**Une seule granularité est collectée ; toutes les échelles supérieures sont recalculées.**
Ce choix garantit la cohérence entre échelles, condition indispensable à une analyse multi-échelles, et supprime une source classique de biais d'anticipation. Il impose en contrepartie un coût de calcul, assumé.

**Les indicateurs sont implémentés et vérifiés, non importés.**
Deux bibliothèques du domaine produisent des valeurs différentes pour un même indicateur, selon leur méthode de lissage. Maîtriser ce calcul permet, face à un résultat surprenant, d'exclure l'instrument de mesure. C'est une condition nécessaire à toute démarche expérimentale. Chaque indicateur est validé par des tests sur des séries à réponse connue.

### 6.3 Passage à l'échelle

La charge de calcul dominante n'est pas la lecture des données mais l'**optimisation**. Évaluer plusieurs centaines de jeux de paramètres, sur plusieurs fenêtres temporelles et plusieurs instruments, représente plusieurs milliers d'exécutions complètes. C'est à ce niveau que le traitement distribué devient nécessaire plutôt qu'ornemental, et c'est cette charge qui sera mesurée pour établir la courbe de passage à l'échelle.

---

## 7. Les analyses et leur restitution

### 7.1 Analyses prévues

| # | Analyse | Nature | Ce qu'elle établit |
|---|---|---|---|
| **A1** | Qualité des données par période | Descriptive | La fiabilité du socle |
| **A2** | Volatilité par session et par heure | Descriptive | Quand le marché est exploitable |
| **A3** | Microstructure : coûts de transaction | Descriptive | Le coût réel d'une décision |
| **A4** | Corrélations glissantes entre instruments | Multivariée | Le risque réel d'un portefeuille |
| **A5** | **Statistiques des figures SMC** | Inférentielle | **Si les figures ont une réalité mesurable** |
| **A6** | **Réaction du prix aux annonces macro** | Inférentielle | L'ampleur et la durée de l'effet |
| **A7** | Performance comparée des stratégies | Évaluative | Laquelle est la meilleure, et de combien |
| **A8** | Robustesse hors échantillon | Évaluative | Si le résultat généralise |

**A5 et A6 constituent le cœur scientifique du travail.** La question *« ces figures se réalisent-elles effectivement, dans quelle proportion et à quelle échéance ? »* est une hypothèse testable, indépendante de toute considération de rentabilité, et dont la réponse a une valeur en soi.

### 7.2 Manipulation et exploration

Les données sont manipulées à trois niveaux, selon l'usage.

| Niveau | Moyen | Usage |
|---|---|---|
| **Requête** | Langage de requête structuré | Extraction ciblée, alimentation des tableaux de bord |
| **Analyse** | Manipulation programmatique de tableaux | Exploration, calculs statistiques, production des figures |
| **Traitement lourd** | Traitement distribué | Campagnes d'optimisation, retraitement de l'historique |

### 7.3 Restitution

| Niveau | Contenu | Public |
|---|---|---|
| **Opérationnel** | Prix en direct, débit, latence, santé des traitements, alertes qualité | Exploitation ; preuve du fonctionnement temps réel |
| **Analytique** | Graphiques annotés, exploration des résultats, comparaison des stratégies | Analyse métier |

**Représentations retenues :** graphiques en chandeliers annotés des figures détectées, séries temporelles multi-échelles, cartes de chaleur heure par jour, histogrammes et densités de distribution, boîtes à moustaches, matrices de corrélation, courbes de capital et de perte maximale, courbes de réaction événementielle avec dispersion, indicateurs synthétiques.

Chaque représentation est choisie pour la **question** qu'elle permet de lire, non pour son apparence. Une carte de chaleur convient à une double entrée ; une distribution évite qu'une moyenne ne masque sa dispersion ; une courbe de perte maximale rend visible ce qu'un investisseur subit réellement, à savoir la trajectoire et pas seulement le résultat final.

---

## 8. Les stratégies étudiées

Quatre approches respectent un **contrat commun** qui les rend interchangeables : chacune reçoit les données disponibles jusqu'à l'instant présent et retourne soit rien, soit une intention de position. Aucune ne décide de la taille engagée, car cette responsabilité appartient à la couche de risque.

| | Approche | Principe testé | Rôle |
|---|---|---|---|
| **B1** | Confluence de trois indicateurs | Alignement de signaux indépendants | Référence de démarrage |
| **B2** | Volatilité et momentum | Retour à la moyenne | Comparaison |
| **B3** | Suivi de tendance adaptatif | Persistance des tendances | Comparaison |
| **S** | **Smart Money Concept** | Lecture de la structure de marché | **Objet de l'étude** |

Les trois références sont volontairement de **natures opposées**, car comparer le SMC à trois variantes d'une même idée n'apprendrait rien.

**Précaution méthodologique centrale.** Les règles sont écrites et **gelées avant tout test**. Ajuster un seuil jusqu'à obtenir une courbe satisfaisante ne mesure plus une hypothèse : cela la fabrique, et le résultat ne survit pas au réel. Cette contrainte est documentée et datée.

---

## 9. Sécurité de la chaîne de traitement

La sécurité est traitée comme une exigence **transverse**, appliquée dès la conception et non ajoutée en fin de parcours.

| Couche | Mesures |
|---|---|
| **Secrets** | Aucun identifiant dans le code ni dans le dépôt, séparation stricte entre configuration et secrets |
| **Transport** | Chiffrement de bout en bout entre composants |
| **Accès** | Authentification et autorisation par service, principe du moindre privilège |
| **Intégrité** | Validation à l'entrée, idempotence, file de rejet, capacité de rejeu |
| **Isolation** | Segmentation réseau entre collecte, traitement et exposition |
| **Traçabilité** | Journalisation structurée, historique inaltérable des décisions émises |
| **Chaîne logicielle** | Versions figées, analyse de vulnérabilités des dépendances |

Une **analyse de risques structurée** accompagne ce dispositif. Elle inclut trois menaces propres au domaine : l'altération d'une source de prix, l'indisponibilité d'un fournisseur, et la dépendance à une source unique.

---

## 10. Travaux déjà réalisés

L'étape de cadrage technique est **achevée**. Elle a produit des mesures et non des estimations, et a déjà validé l'utilité de la démarche.

| Vérification | Résultat |
|---|---|
| Connexion aux deux fournisseurs de données | Opérationnelle |
| Identification des symboles réels | Établie ; les noms diffèrent entre fournisseurs |
| Profondeur d'historique disponible | **7 à 28 ans** selon l'instrument |
| Disponibilité des données au tick | Confirmée, plusieurs centaines de milliers par jour |
| Qualité sur période récente | **Aucune incohérence, aucun doublon** |
| Fuseau horaire des serveurs | Décalé de 3 heures, normalisation requise |
| Coûts de transaction réels | Mesurés, et **différents entre fournisseurs** |
| Domaine de validité des données | **Délimité par la mesure** |

**Trois découvertes méthodologiques** en sont issues, qui alimenteront le chapitre 3.

1. Un **paramètre de configuration** limitait l'historique visible à 3 mois au lieu de plusieurs années. La mesure était techniquement correcte et complètement fausse.
2. L'interface de données **ne signale pas l'absence de donnée**. Interrogée sur une période antérieure à son historique, elle retourne l'enregistrement le plus proche. Un test naïf concluait ainsi à vingt ans d'historique sur un instrument récent.
3. L'historique ancien de deux fournisseurs indépendants s'est révélé **rigoureusement identique** sur plus de mille enregistrements. Il provient donc d'une source commune, et non des cotations propres annoncées. La date de bascule a été localisée par encadrement, ce qui **délimite le domaine de validité** des tests décisifs.

Les briques logicielles de formalisation des stratégies sont également en place, couvertes par **36 tests automatisés**.

---

## 11. Planning

| Phase | Contenu | Livrable |
|---|---|---|
| **0** | Cadrage technique et validation des données | ✅ **Terminée** (rapport de diagnostic) |
| **1** | Simulation historique et première évaluation | Résultats comparés |
| **2** | Socle de stockage et pipeline de qualité | Jeu de données auditable, rapport qualité |
| **3** | Analyses exploratoires et restitution | Figures et tableaux de bord |
| **4** | Chaîne temps réel | Démonstration en fonctionnement continu |
| **5** | Sécurisation, déploiement, exploitation | Plateforme opérationnelle |
| **6** | Formalisation du SMC et évaluation finale | Comparaison chiffrée |

**Principe de séquencement.** Chaque phase produit un livrable présentable indépendamment. En cas de retard, le périmètre se réduit sans jamais laisser un chantier ouvert. L'ordre de renoncement est défini à l'avance : le raffinement du cas d'usage cède avant l'infrastructure de données.

---

## 12. Points soumis à validation

1. Le **découpage en trois parties** (plateforme, analyse, valeur) correspond-il aux attentes ?
2. La **question de recherche** est-elle au niveau d'exigence attendu ?
3. Quels sont le **volume et le format** attendus du mémoire ?
4. Quelle est la date exacte de la **soutenance** ?
5. Quel est le degré d'attente sur les **technologies distribuées** : implémentation effective ou conception argumentée ?

---

*Document de cadrage, version 1. Les éléments consignés ici restent révisables jusqu'à validation.*
