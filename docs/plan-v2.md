# Plan v2 — Le chemin, étape par étape

**Date :** 18 août 2026
**Remplace :** `plan-v1.md` (trop dense, technos posées avant d'en avoir le besoin)

---

## 1. Le projet en une page

**Ce que je veux construire :** un robot qui teste des stratégies de trading sur les données du passé, garde la meilleure, puis la joue tout seul en direct sur un compte FTMO.

Le parcours de la donnée, du début à la fin :

```
   Données historiques          Backtest              Sélection
   (forex, index, crypto)  →   2-3 stratégies   →   de la meilleure
                                                          │
                                                          ▼
   Prise de position    ←    Signal d'entrée    ←   Données en direct
   auto sur FTMO             selon mes règles          (temps réel)
```

**Ma stratégie cible** est le Smart Money Concept (SMC), que je pratique déjà à la main. Mais je ne commence **pas** par elle : je fais d'abord marcher toute la chaîne avec une stratégie simple.

---

## 2. La méthode : le squelette qui marche

### 2.1 Pourquoi commencer par une stratégie simple

La tentation naturelle est de construire chaque morceau à la perfection, puis de tout assembler à la fin. C'est la façon n°1 dont les projets meurent : on découvre les vrais problèmes le dernier jour.

L'approche inverse s'appelle le **squelette qui marche** *(walking skeleton)* : on construit d'abord un fil **complet** du début à la fin — même très bête — puis on l'épaissit.

Concrètement : une stratégie à base de **RSI + MACD + EMA**, dont le but n'est pas d'être rentable, mais de **prouver que la chaîne fonctionne**. Le jour où le SMC arrive, il se branche sur une machine déjà rodée.

### 2.2 La règle pour choisir les technos

> **On n'ajoute un outil que le jour où on rencontre le problème qu'il résout.**

Un outil ajouté avant son problème, c'est de la complexité gratuite. Un outil ajouté au bon moment, on le comprend — et on sait l'expliquer en soutenance.

C'est pour ça que Kafka et Spark arrivent à l'étape 8, et pas à l'étape 1.

---

## 3. Les 10 étapes

Chaque étape : **un problème** → **un outil** → **quelque chose qui marche**.

| # | Le problème | L'outil | Durée |
|---|---|---|---|
| 0 | Je n'ai pas encore vu mes données | Python + MetaTrader5 | 2-3 j |
| 1 | Je ne sais pas si une stratégie est bonne | `backtesting.py` | 4-5 j |
| 2 | Mes fichiers deviennent ingérables | PostgreSQL + TimescaleDB | 3-4 j |
| 3 | Des chiffres bruts ne permettent pas de juger | Streamlit | 3 j |
| 4 | ⭐ Backtest et live feraient coder ma stratégie deux fois | L'**interface broker** *(un concept)* | 5-6 j |
| 5 | Je ne sais pas quand il est dangereux de trader | Calendrier économique | 3-4 j |
| 6 | Je veux qu'il décide en direct, sans moi | Boucle live + couche de risque | 5-6 j |
| 7 | Mon PC doit pouvoir être éteint | Docker + serveur | 4-5 j |
| 8 | Plusieurs flux, plusieurs consommateurs, gros calculs | Kafka + Spark | 8-10 j |
| 9 | La baseline n'est pas la stratégie qui m'intéresse | Le travail d'analyse SMC | 6-8 j |

**Les étapes 0 à 7 forment le squelette.** À la fin de la 7, le projet existe vraiment : il tourne seul, il prend des positions. Les étapes 8 et 9 l'épaississent.

---

### Étape 0 — Regarder les données

**Le problème.** Tout le reste dépend de données que je n'ai pas encore vues. Si l'historique du forex chez mon broker s'arrête à 2 ans, ou si les bougies ont des trous, le plan change.

**Ce que je fais.** Je récupère un mois de bougies M1 sur GBP/USD depuis MetaTrader 5, je l'ouvre dans pandas, je regarde : combien de lignes, quelles colonnes, des trous, quel fuseau horaire, jusqu'où remonte l'historique.

**L'outil.** Le module Python `MetaTrader5` (`pip install MetaTrader5`) branché sur un **compte démo gratuit** chez un broker MT5.

**Pourquoi celui-là.** FTMO utilise MT5. En prenant MT5 dès maintenant comme source, mes données de backtest et mes données de live viennent **du même endroit** — c'est ce qui évite qu'un backtest brillant s'effondre en réel. Et je n'ai qu'une seule API à apprendre pour toute la durée du projet.

**C'est fini quand.** J'ai un fichier de vraies bougies ouvert dans pandas, et je sais exactement de quoi je dispose.

*Pour comprendre le rôle respectif de MT5, du courtier et de FTMO, voir l'annexe en fin de document.*

---

### Étape 1 — Le premier backtest

**Le problème.** Je ne sais pas si une stratégie gagne ou perd.

**Ce que je fais.** Je code la stratégie RSI + MACD + EMA et je la teste sur un an d'historique, avec des frais réalistes (spread, commission).

**L'outil.** `backtesting.py`.

**Pourquoi celui-là.** C'est la bibliothèque de backtest la plus simple à lire pour débuter : on écrit une classe, on définit `init()` et `next()`, et elle s'occupe du reste. Elle traite les bougies **une par une, dans l'ordre**, ce qui empêche mécaniquement de tricher en regardant l'avenir — l'erreur la plus fréquente en backtest.

*Alternative écartée : `vectorbt`, plus rapide mais bien plus abstrait. On y viendra peut-être à l'étape 8, quand la vitesse deviendra un vrai besoin.*

**C'est fini quand.** J'obtiens un rendement, un drawdown maximum, un nombre de trades, et je peux regarder chaque trade un par un.

---

### Étape 2 — Ranger les données

**Le problème.** Les fichiers s'accumulent (par instrument, par période, par timeframe). Je veux pouvoir demander « les bougies H1 de GBP/USD entre mars et juin » sans écrire un script à chaque fois. Et bientôt, le collecteur live va **écrire** pendant que le dashboard **lit** — un fichier ne sait pas faire ça proprement.

**Ce que je fais.** Je charge tout mon historique dans une base, avec une table par nature de donnée (bougies, trades, signaux).

**L'outil.** **PostgreSQL** avec l'extension **TimescaleDB**.

**Pourquoi celui-là.** PostgreSQL, c'est du SQL classique — la compétence la plus réutilisable qui existe. TimescaleDB est une simple extension par-dessus : elle découpe automatiquement les grandes tables par tranches de temps, ce qui rend les requêtes sur des dates beaucoup plus rapides. **Je n'apprends pas un nouvel outil, j'active une option sur un outil que je connais.**

*Alternative écartée : InfluxDB, très bon sur les séries temporelles mais avec son propre langage de requête, et incapable de stocker proprement mes trades et mes signaux à côté. Une seule base vaut mieux que deux.*

**C'est fini quand.** Une requête SQL me rend mes bougies, et mon backtest lit depuis la base au lieu d'un fichier.

---

### Étape 3 — Voir ce qui se passe

**Le problème.** Un tableau de chiffres dans un terminal ne permet pas de juger une stratégie. Je dois **voir** où elle est entrée, où elle est sortie, et comment le capital a évolué.

**Ce que je fais.** Une page web locale : graphique en chandeliers, trades affichés dessus, courbe de capital, tableau des indicateurs de performance.

**L'outil.** **Streamlit**.

**Pourquoi celui-là.** C'est du Python pur : pas de HTML, pas de JavaScript, pas de serveur à configurer. Une page se fait en quelques dizaines de lignes. Comme je maîtrise déjà React, je pourrai refaire un vrai front plus tard si le temps le permet — mais **maintenant, je veux voir mes résultats, pas construire une application web**.

**C'est fini quand.** Je lance une commande, une page s'ouvre, et je comprends d'un coup d'œil ce qu'a fait ma stratégie.

---

### Étape 4 ⭐ — L'interface broker

**C'est la seule idée vraiment subtile du projet. Une fois comprise, tout le reste est mécanique.**

**Le problème.** En backtest, ma stratégie reçoit des prix passés et passe des ordres **imaginaires**. En live, elle reçoit des prix réels et passe des ordres **réels** chez MT5. Ce sont deux mondes différents.

Si j'écris deux programmes, ils vont **diverger** : je corrige un bug d'un côté, j'oublie l'autre, j'ajuste une règle ici mais pas là. Résultat : mon backtest ne décrit plus ce que fait mon bot. **Tout le travail de validation devient un mensonge.**

**La solution.** Je remarque que dans les deux cas, ma stratégie fait exactement les trois mêmes choses :

```
                  1. lire le prix actuel
                  2. décider (acheter / vendre / ne rien faire)
                  3. passer l'ordre
```

Alors je définis un **contrat** — une classe abstraite `Broker` avec les méthodes `get_price()`, `buy()`, `sell()`, `close()` — et j'en écris **deux versions** :

```
                    ┌──────────────────────┐
                    │  MA STRATÉGIE        │   ← écrite UNE fois
                    │  (RSI + MACD + EMA)  │
                    └──────────┬───────────┘
                               │  parle au contrat "Broker"
                               │  sans savoir qui est derrière
                 ┌─────────────┴─────────────┐
                 ▼                           ▼
        ┌─────────────────┐         ┌─────────────────┐
        │ BacktestBroker  │         │   MT5Broker     │
        │ ordres simulés  │         │  ordres réels   │
        │ prix du passé   │         │  prix en direct │
        └─────────────────┘         └─────────────────┘
```

Ma stratégie ne sait pas — et n'a pas besoin de savoir — laquelle des deux elle utilise. **Passer du backtest au live devient un changement de configuration, pas une réécriture.**

Ce principe porte un nom en conception logicielle : l'**inversion de dépendance**. C'est aussi ce qui rendra le passage au SMC facile : le SMC sera juste une troisième stratégie branchée sur le même contrat.

**C'est fini quand.** Le même fichier de stratégie, inchangé, tourne en backtest **et** en démo live selon une ligne de configuration.

---

### Étape 5 — Le calendrier économique

**Le problème.** Certaines heures sont dangereuses, et ça n'a rien à voir avec le graphique. Quand tombe une annonce économique majeure — taux directeurs, emploi américain, inflation — le prix saute violemment, l'écart entre achat et vente s'élargit d'un coup, et un ordre s'exécute à un prix très différent de celui affiché. **Une bonne stratégie peut perdre de l'argent simplement parce qu'elle a ouvert au mauvais moment.**

Et ce n'est pas seulement une question de bon sens : **FTMO l'impose**. Interdiction d'ouvrir une position dans les 2 minutes qui précèdent ou qui suivent un événement à fort impact. Sans ce filtre, mon bot viole les règles du Challenge.

**Ce que je fais.**

1. **Un deuxième collecteur** qui récupère le calendrier économique : date et heure de chaque annonce, devise concernée, niveau d'importance (faible / moyen / **fort**), valeur prévue et valeur réelle.
2. **Une table en base**, à côté de mes bougies.
3. **Une seule fonction**, que la couche de risque appellera : `est_ce_que_je_peux_trader(instrument, moment) → oui / non`.

**L'outil.** L'API **Finnhub** (offre gratuite) pour le calendrier. Solution de repli : le calendrier ForexFactory, largement utilisé et récupérable par script.

**Deux points à ne pas rater.**

- **Il me faut aussi l'historique du calendrier**, pas seulement les annonces à venir. Sinon mon backtest ignorerait le filtre alors que mon bot live l'appliquerait — les deux ne feraient plus la même chose, et je retomberais exactement dans le piège que l'étape 4 sert à éviter.
- **Chaque annonce ne concerne pas tous les instruments.** Une annonce britannique affecte GBP/USD, pas US30. Il me faut donc une petite table de correspondance entre devise de l'annonce et instruments concernés.

**Un bonus pour plus tard.** Ce qui fait bouger le marché n'est pas la valeur annoncée, mais l'**écart entre la valeur réelle et la valeur prévue** — la surprise. Comme je stocke les deux, je pourrai plus tard mesurer cet effet. Ce n'est pas nécessaire pour le filtre, mais c'est une analyse intéressante pour le mémoire.

**C'est fini quand.** Mon dashboard affiche les prochaines annonces à fort impact et les créneaux interdits, et ma fonction de filtre répond correctement sur une date passée.

---

### Étape 6 — Le live en démo

**Le problème.** Recevoir les prix en continu, décider en temps réel, et surtout : **ne pas faire n'importe quoi avec l'argent**.

**Ce que je fais.** Deux morceaux :

1. **La boucle live** — un programme qui interroge MT5 à intervalle régulier, met à jour les bougies en base, appelle la stratégie, et transmet sa décision.
2. **La couche de risque** — le garde-fou obligatoire, placé **entre** la stratégie et le broker. Aucun ordre ne passe sans son accord :
   - risque fixe de 0,2 % du capital par trade (calcul automatique de la taille de position)
   - maximum 5 trades par jour
   - arrêt immédiat si le drawdown journalier approche la limite FTMO
   - **appel au filtre de l'étape 5** : refus d'ouvrir dans une fenêtre d'annonce

**Pourquoi la couche de risque est séparée de la stratégie.** Parce qu'une stratégie a le droit d'avoir tort — c'est son métier de se tromper parfois. Le risque, lui, n'a **jamais** le droit d'avoir tort : c'est lui qui empêche de perdre le compte. Deux responsabilités différentes, deux morceaux de code différents, testés séparément.

**C'est fini quand.** Le bot tourne une journée entière sur un compte démo, prend des positions tout seul, et je peux relire dans les logs pourquoi il a agi.

---

### Étape 7 — Le déploiement

**Le problème.** Le marché ne s'arrête pas quand j'éteins mon PC.

**Ce que je fais.** J'emballe chaque composant (base, collecteur, bot, dashboard) dans un conteneur, et je fais tourner l'ensemble sur un serveur distant, en continu.

**L'outil.** **Docker** + **Docker Compose**, sur un serveur loué.

**Pourquoi celui-là.** Docker fige tout ce dont mon programme a besoin (version de Python, bibliothèques, configuration) dans une boîte. Cette boîte tourne à l'identique sur mon PC et sur le serveur — plus de « ça marchait chez moi ». Docker Compose décrit tous mes composants dans **un seul fichier**, et les démarre ensemble.

*Alternative écartée : Kubernetes. C'est l'outil pour gérer des centaines de conteneurs sur des dizaines de machines. J'en ai six sur une machine. Ce serait ajouter des semaines de travail pour résoudre un problème que je n'ai pas.*

**Point de vigilance à trancher ici :** le module Python MetaTrader5 ne fonctionne **que sous Windows**. Voir la section 6.

**C'est fini quand.** J'éteins mon PC, le bot continue, et je consulte le dashboard depuis mon téléphone.

> 🎯 **Le squelette est debout. Le projet existe et fonctionne de bout en bout.**

---

### Étape 8 — La plateforme de données

**Le problème.** Trois besoins apparaissent en même temps, et aucun n'existait avant :

1. **Plusieurs instruments** (forex + index + crypto) et **plusieurs programmes** veulent lire le même flux de prix : le bot, le dashboard, l'archivage, les contrôles de qualité. Si chacun se connecte à MT5 séparément, je multiplie les connexions, et si un plante il perd des données définitivement.
2. **Rejouer.** Quand je corrige une règle, je veux repasser le flux d'hier dans le nouveau code.
3. **Optimiser.** Tester 500 combinaisons de paramètres × 5 périodes × 3 instruments = 7 500 backtests. Sur un seul cœur, c'est plusieurs jours.

**Les outils.**

| Outil | Ce qu'il résout | En une phrase |
|---|---|---|
| **Kafka** | Problèmes 1 et 2 | Un tuyau central où le collecteur **écrit une fois**, et où chacun **lit à son rythme**, sans se gêner. Les messages sont conservés, donc rejouables |
| **Spark** | Problème 3 | Découpe un gros calcul en morceaux répartis sur plusieurs cœurs ou plusieurs machines |
| **Parquet** | Archivage | Un format de fichier compressé et rapide à relire — 10 fois plus léger qu'un CSV |

**Pourquoi maintenant et pas avant.** À l'étape 1, j'avais **un** programme qui lisait **un** fichier. Kafka aurait résolu un problème inexistant. Maintenant que j'ai quatre consommateurs et trois instruments, il résout un vrai problème — et je peux l'expliquer avec mes mots.

**C'est fini quand.** Le collecteur publie dans Kafka, plusieurs consommateurs indépendants lisent le même flux, et une optimisation qui prenait des heures prend des minutes.

---

### Étape 9 — Le SMC

**Le problème.** La baseline a fait son travail : elle a prouvé que la machine fonctionne. Mais ce n'est pas la stratégie qui m'intéresse.

**Ce que je fais.**

1. **Formaliser sur papier** — traduire ce que je fais à l'œil en règles sans aucune ambiguïté : qu'est-ce qu'un swing ? un Order Block valide ? une rupture de structure ? Cette étape se fait **avant** de coder, sinon j'ajusterai les règles jusqu'à ce que le backtest soit joli — et il ne voudra plus rien dire.
2. **Coder les détecteurs** — en m'appuyant sur la bibliothèque `smartmoneyconcepts`, qui fournit les briques de détection (Order Blocks, Fair Value Gaps, ruptures de structure), mais **pas** les règles de décision : celles-là sont mon travail.
3. **Brancher** — le SMC devient une troisième stratégie sur le contrat de l'étape 4. Rien d'autre ne change.
4. **Comparer** — SMC contre les baselines, dans le même backtest, avec les mêmes frais et les mêmes règles de risque.

**C'est fini quand.** J'ai une comparaison chiffrée et honnête. **Et si le SMC ne gagne pas, c'est un résultat valide** — je l'aurai mesuré au lieu de le croire.

---

## 4. Les stratégies à implémenter

### 4.1 Le contrat commun

Les quatre stratégies doivent être **interchangeables**. Elles respectent donc toutes le même contrat, exactement comme les deux brokers de l'étape 4 :

```
   ENTRÉE  :  les bougies disponibles jusqu'à maintenant
              (jamais au-delà — c'est ce qui empêche de tricher)
                              │
                              ▼
                       [ LA STRATÉGIE ]
                              │
                              ▼
   SORTIE  :  rien du tout   OU   un signal :
              { sens : achat/vente , entrée , stop-loss , objectif }
```

**Ce que la stratégie ne décide jamais : la taille de la position.** Elle dit *où* entrer et *où* sortir ; la couche de risque (étape 6) calcule *combien* en fonction des 0,2 % de capital autorisés. Deux responsabilités, deux morceaux de code.

Grâce à ce contrat, ajouter une stratégie ne touche à rien d'autre : ni au backtest, ni au live, ni au dashboard.

### 4.2 Vue d'ensemble

| | Stratégie | Nature testée | Difficulté | Charge | Étape |
|---|---|---|---|---|---|
| **B1** | RSI + MACD + EMA | Confluence / momentum | ⭐ | ~1 j | **1** — le squelette n'a besoin que d'elle |
| **B2** | MACD + Bandes de Bollinger | Retour à la moyenne | ⭐ | ~1 j | Après l'étape 4, quand le contrat existe |
| **B3** | SuperTrend (ATR) + filtre RSI | Suivi de tendance | ⭐⭐ | ~2 j | Après l'étape 4, quand le contrat existe |
| **S** | **Smart Money Concept** | Structure de marché | ⭐⭐⭐⭐ | **2-3 sem.** | 9 |

**Les trois baselines sont volontairement de natures différentes.** Tester trois variantes de la même idée n'apprendrait rien. Ici : une cherche l'alignement de plusieurs signaux, une parie sur le retour à la moyenne, une suit la tendance. Si le SMC bat les trois, le résultat a du poids.

---

### B1 — RSI + MACD + EMA *(la baseline de démarrage)*

**Le principe.** Trois confirmations doivent s'aligner avant d'entrer : la **tendance** dit dans quel sens, le **momentum** dit que le mouvement démarre, le **RSI** dit que le prix n'est pas déjà épuisé.

| Indicateur | Ce qu'il apporte |
|---|---|
| EMA 200 | La tendance de fond |
| MACD (12, 26, 9) | Le déclenchement du mouvement |
| RSI (14) | L'épuisement / le rebond |

**Règles à figer** *(exemple pour un achat)* : prix au-dessus de l'EMA 200 **et** croisement haussier du MACD **et** RSI remontant au-dessus de 30. Stop sous le dernier creux ; objectif à un multiple fixe du risque (2R).

**Son rôle.** Faire fonctionner la chaîne. Sa rentabilité importe peu — c'est le véhicule d'essai.

---

### B2 — MACD + Bandes de Bollinger

**Le principe.** Les bandes disent **où** le prix est anormalement éloigné de sa moyenne ; le MACD dit **quand** il commence à revenir.

| Indicateur | Ce qu'il apporte |
|---|---|
| Bandes de Bollinger (20, 2σ) | Les limites statistiques de la volatilité |
| MACD (12, 26, 9) | Le moment du retournement |

**Règles à figer** *(achat)* : le prix touche ou perce la bande basse **et** le MACD croise à la hausse. Objectif : la bande médiane. Stop sous le plus bas récent.

**Un choix à faire, et un seul.** Cette combinaison peut se jouer en *retour à la moyenne* (acheter le bas) **ou** en *cassure* (acheter la sortie par le haut). Ce sont deux stratégies opposées. **Je retiens le retour à la moyenne**, pour contraster avec B1 et B3 qui suivent la tendance.

---

### B3 — SuperTrend (ATR) + filtre RSI

**Le principe.** Suivre une tendance avec un stop qui **se déplace tout seul** en fonction de la volatilité : large quand le marché s'agite, serré quand il se calme.

| Indicateur | Ce qu'il apporte |
|---|---|
| SuperTrend (ATR 10, mult. 3) | Le sens de la tendance **et** le stop suiveur |
| RSI (14) | Filtre : ne suivre que si le momentum confirme |

**Règles à figer** *(achat)* : le SuperTrend bascule en mode haussier **et** RSI > 50. Le stop **est** la ligne SuperTrend, qui remonte à chaque bougie. Sortie quand le prix la casse.

**Sa particularité.** C'est la seule des trois à **laisser courir les gains** au lieu de viser un objectif fixe. Elle produira peu de trades gagnants mais des gains plus gros — un profil de résultats très différent, intéressant à comparer.

**Point d'attention technique.** Le SuperTrend se calcule de façon récursive (chaque valeur dépend de la précédente). C'est la seule des trois baselines qui demande un peu de soin à implémenter.

---

### S — Le Smart Money Concept

**C'est le gros morceau.** Pas une stratégie à indicateurs, mais une lecture de la **structure** du marché. Elle se décompose en six briques, à construire dans cet ordre — chacune dépend de la précédente.

| # | Brique | Ce qu'il faut définir mécaniquement | Difficulté |
|---|---|---|---|
| 1 | **Swings** (points pivots) | Un sommet est-il « significatif » ? Règle : N bougies plus basses à gauche et à droite. **Le choix de N conditionne tout le reste** | ⭐⭐ |
| 2 | **Structure de marché** | Enchaînement des swings : sommets et creux de plus en plus hauts = tendance haussière | ⭐⭐ |
| 3 | **BOS / CHoCH** | BOS : le prix casse le dernier swing **dans le sens** de la tendance (continuation). CHoCH : il casse **à l'opposé** (retournement possible) | ⭐⭐⭐ |
| 4 | **Order Blocks** | La dernière bougie de sens contraire avant le mouvement impulsif. Il faut définir « impulsif » par des chiffres : combien de bougies, quelle amplitude | ⭐⭐⭐⭐ |
| 5 | **Fair Value Gaps** | Trou entre le haut de la bougie 1 et le bas de la bougie 3. **La plus simple à mécaniser des six** | ⭐ |
| 6 | **Premium / Discount** | Où se situe le prix dans la plage du dernier mouvement : au-dessus de la moitié = premium (vendre), en dessous = discount (acheter) | ⭐ |

**Puis la cascade multi-timeframe** — c'est là que les briques s'assemblent :

```
   Daily + H4   →  quel est le biais directionnel ?
        ↓            (si pas de biais clair : on ne trade pas)
   H1 + M15     →  la structure confirme-t-elle ? (BOS/CHoCH, zone valide)
        ↓            (si non : on attend)
   M5 ou M1     →  le déclencheur d'entrée est-il là ?
        ↓
      SIGNAL
```

Chaque étage doit valider avant de descendre au suivant.

**Deux choses à savoir avant de s'y attaquer :**

1. **La bibliothèque `smartmoneyconcepts` fournit les détecteurs (briques 1 à 5), pas les décisions.** Elle te dit « voici un Order Block ». Elle ne te dit pas « entre maintenant ». La partie difficile — *à quelle condition exacte je prends position ?* — reste entièrement mon travail.
2. **Il faut tout figer par écrit AVANT de lancer le premier backtest.** Sinon j'ajusterai les règles jusqu'à ce que la courbe soit belle, et le résultat ne voudra plus rien dire. C'est le piège n°1 de ce type de projet.

**Charge réelle : 2 à 3 semaines**, pas une. Autant le savoir maintenant.

---

### 4.3 Comment je choisirai la gagnante

Le rendement seul ne suffit pas — une stratégie qui gagne 40 % puis perd tout ne passe aucun Challenge. Les critères, par ordre d'importance :

| Critère | Pourquoi |
|---|---|
| ⭐ **Taux de réussite à un Challenge FTMO simulé** | Le critère le plus proche de mon vrai objectif : sur N périodes différentes, combien de fois la stratégie aurait-elle passé le Challenge ? |
| **Drawdown journalier maximum** | 91 % des comptes FTMO échouent sur cette règle, pas sur la perte totale |
| **Régularité** (Sharpe, Sortino) | Gagner un peu tout le temps vaut mieux que beaucoup une fois |
| **Nombre de trades** | Une stratégie à 15 trades sur 5 ans ne prouve rien statistiquement |
| **Distribution des gains**, pas seulement la moyenne | Une moyenne flatteuse peut cacher un seul coup de chance |
| **Résultats hors échantillon** | Testée sur des données qu'elle n'a jamais vues pendant l'optimisation |
| **Ventilation par instrument** | Une stratégie peut être excellente sur l'or et catastrophique sur le forex |

**Règle de décision :** une seule stratégie part en live par compte FTMO. Le backtest comparatif sert à désigner laquelle.

---

## 5. La pile technique complète

Tout le projet tient en **six briques** :

| Brique | Rôle | Arrive à l'étape |
|---|---|---|
| **Python + pandas** | Le langage, la manipulation de données | 0 |
| **MetaTrader5** | Source des prix + exécution des ordres | 0 |
| **backtesting.py** | Moteur de backtest | 1 |
| **PostgreSQL + TimescaleDB** | Stockage | 2 |
| **Streamlit** | Visualisation | 3 |
| **Finnhub** | Calendrier économique | 5 |
| **Docker** | Déploiement | 7 |

Puis, seulement quand le besoin apparaît : **Kafka**, **Spark**, **Parquet** *(étape 8)*.

Rien d'autre. Pas de Kubernetes, pas de Flink, pas de MinIO, pas d'Airflow, pas de NLP.

---

## 6. Où et comment déployer

### 5.1 Quel type d'hébergement

Tous les hébergeurs ne servent pas à la même chose. Mon bot doit **rester allumé en permanence** et **se souvenir** de ce qu'il a fait (positions ouvertes, nombre de trades du jour, drawdown en cours).

| Type de service | Principe | Convient à mon bot ? |
|---|---|---|
| **Vercel, Netlify** | Exécute du code **quand un visiteur arrive**, quelques secondes, puis s'éteint. Aucune mémoire entre deux visites | ❌ S'éteindrait entre chaque exécution et oublierait tout |
| **VM / serveur** (GCP Compute Engine, Hetzner, OVH) | Une machine allumée en continu, dont je fais ce que je veux | ✅ **C'est ce qu'il me faut** |

*Vercel pourra servir plus tard si je fais un dashboard en Next.js — mais pour l'interface web uniquement, jamais pour le bot.*

### 5.2 Windows ou Linux

**Point important à comprendre :** un conteneur Docker ne contient pas de système d'exploitation, il emprunte celui de la machine hôte. Quand je lance Docker sur mon PC Windows, Docker Desktop démarre en arrière-plan une mini-machine Linux (WSL2) que je ne vois jamais — **je fais donc déjà tourner du Linux sans le savoir**. Déployer sur une VM Linux ne changera presque rien.

Sauf pour une pièce : **le module Python `MetaTrader5` ne fonctionne que sous Windows**, parce qu'il ne fait pas du calcul mais pilote une application Windows (le terminal MT5).

| | Tourne sous Linux ? |
|---|---|
| Mon code Python, pandas, ma stratégie, mon backtest | ✅ |
| PostgreSQL, Streamlit, Kafka, Spark | ✅ |
| Le module `MetaTrader5` | ❌ Windows uniquement |

Trois options, à trancher à l'étape 7 :

| Option | Avantage | Inconvénient |
|---|---|---|
| **A — Un serveur Windows** *(le plus simple pour livrer)* | Tout au même endroit, aucune adaptation | Plus cher (~15-25 €/mois), Docker moins naturel |
| **B — Deux serveurs** : Linux pour la plateforme, Windows pour l'exécution seule | Chaque partie sur son environnement idéal | Deux machines à gérer |
| **C — Un serveur Linux + API OANDA** au lieu de MT5 | Le moins cher, le plus simple à déployer | OANDA n'est pas FTMO : il faudrait réécrire l'exécution pour le passage final |

**Décision reportée à l'étape 7.** L'interface broker de l'étape 4 rend ce choix réversible sans douleur — c'est précisément l'intérêt de l'avoir construite.

---

## 7. Calendrier indicatif

| Semaine | Étapes | Point d'arrivée |
|---|---|---|
| S1 | 0 + 1 | Un backtest de B1 qui donne un résultat |
| S2 | 2 + 3 | Mes données en base, mes résultats à l'écran |
| S3 | 4 (+ B2, B3) | La même stratégie tourne des deux côtés, 3 baselines comparées |
| S4 | 5 + 6 | Filtre d'annonces en place, le bot décide seul en démo |
| S5 | 7 | 🎯 **Ça tourne PC éteint — le squelette est debout** |
| S6-S7 | 8 | Kafka, Spark, multi-instruments |
| S8 | 9 (début) | SMC formalisé et branché |

**Règle en cas de retard :** on décale les étapes 8 et 9, jamais les étapes 0 à 7. Un squelette complet et fonctionnel vaut infiniment mieux qu'une plateforme sophistiquée à moitié finie.

---

## 8. Ce qu'on ne fait pas, et pourquoi

| Écarté | Raison |
|---|---|
| Kubernetes | Conçu pour des centaines de conteneurs sur des dizaines de machines. J'en ai six sur une |
| Apache Flink | Fait la même chose que Spark ici. Un outil suffit |
| MinIO / data lake | Ma base de données suffit tant que je n'ai pas des téraoctets |
| Airflow | Une simple tâche planifiée suffit tant que je n'ai pas des dizaines de traitements enchaînés |
| Analyse de sentiment (NLP) | Beaucoup de travail, résultat incertain, aucun rapport avec le cœur du projet |
| Trading en argent réel | Hors sujet académique. Le projet s'arrête au compte démo et au Challenge FTMO |

Ces choix ne sont pas des renoncements : ce sont des **décisions argumentées**, et elles se défendent très bien en soutenance. Savoir dire pourquoi on n'a **pas** utilisé un outil est un meilleur signe de maîtrise que de l'avoir utilisé sans raison.

---

## 9. Justifier le « big data » sans parler de volume

Mes données ne pèsent pas des téraoctets, et il ne faut pas prétendre le contraire. La bonne définition à poser d'entrée :

> **On parle de big data non pas à partir d'une taille donnée, mais à partir du moment où les méthodes simples cessent de suffire.**

Un fichier lu par un seul programme ne pose aucun problème. Voici les six moments où, dans mon projet, ce n'est plus le cas — chacun mesurable.

### ① Vélocité — les données arrivent en continu

Le marché ne m'envoie pas un fichier, il m'envoie un flux ininterrompu. Je ne peux pas « attendre la fin » : il n'y en a pas.

**Ce que je mesure :** nombre de messages par seconde, et temps écoulé entre la réception d'un prix et la décision du bot.

### ② Variabilité — le débit explose sans prévenir ⭐

C'est mon **meilleur argument**, et il découle directement du calendrier économique de l'étape 5.

À 3 h du matin, le marché est calme. À 14 h 30 lors de l'annonce de l'emploi américain, le débit est **plusieurs dizaines de fois** supérieur pendant quelques secondes. Un système dimensionné pour la moyenne s'effondre exactement au moment le plus important.

C'est précisément ce qu'une file de messages comme **Kafka** résout : elle absorbe la rafale et laisse les consommateurs rattraper à leur rythme.

**Ce que je mesure :** courbe du débit sur 24 h, avec le pic au moment de l'annonce. Un seul graphique, très parlant en soutenance.

### ③ Variété — des données de natures incompatibles

| Source | Forme |
|---|---|
| Bougies | Série temporelle régulière, numérique |
| Calendrier économique | Événements ponctuels, avec texte, prévision et valeur réelle |
| Positionnement institutionnel (COT) | Rapport hebdomadaire, format totalement différent |

Aucune ne se range dans le même tableau. Il faut les rapprocher **dans le temps** alors qu'elles n'ont ni la même fréquence, ni la même structure.

**Ce que je mesure :** nombre de sources, de formats et de fréquences différents réellement intégrés.

### ④ Véracité — les données mentent

Bougies manquantes, doublons, prix aberrants, incohérences (un plus bas supérieur au plus haut), décalages de fuseau horaire, écarts entre deux brokers pour le même instrument au même instant.

**En finance, une donnée fausse ne produit pas une erreur : elle produit un ordre.** D'où un contrôle systématique à l'entrée, avec mise à l'écart de ce qui ne passe pas.

**Ce que je mesure :** pourcentage de données conformes, nombre d'anomalies détectées par instrument et par année.

### ⑤ Le calcul devient le vrai goulot d'étranglement

Chercher les bons paramètres d'une stratégie, sérieusement, c'est : 500 combinaisons × 5 périodes de test × 3 instruments = **7 500 backtests**. Sur un seul cœur, plusieurs jours. C'est ici que le volume ne compte plus du tout — c'est le **nombre d'opérations** qui bloque.

C'est le problème que **Spark** résout : découper le calcul et le répartir.

**Ce que je mesure :** temps du même calcul sur 1, 2, 4 puis 8 cœurs. La courbe obtenue est la preuve empirique la plus solide que je puisse produire.

### ⑥ Rejouer le passé

Quand je corrige une règle, je veux repasser tout l'historique dans le nouveau code et comparer. Cela suppose de conserver les données **brutes et intactes**, et de pouvoir les rediffuser — ce qu'un simple fichier écrasé à chaque mise à jour ne permet pas.

**Ce que je mesure :** capacité à reconstruire un résultat identique à partir des données d'origine.

---

**En résumé, la phrase à retenir pour la soutenance :**

> Ce projet n'est pas big data par la taille, mais parce qu'il combine un flux continu à débit irrégulier, des sources hétérogènes, une exigence de fiabilité à l'entrée, et un besoin de calcul qui dépasse une seule machine. Chaque outil que j'ai retenu répond à l'un de ces points précis — et je peux montrer la mesure qui le prouve.

---

## Annexe — MT5, courtiers et FTMO : qui fait quoi

### A. MT5 n'est pas un courtier, c'est un logiciel

MetaTrader 5 est une **application**, éditée par MetaQuotes. Elle ne détient aucun argent et ne fabrique aucun prix. C'est un client, comme un logiciel de messagerie : il ne te donne pas d'adresse, il se connecte à un serveur qui en gère une.

```
   MT5 (logiciel installé chez moi)  ──►  Serveur du courtier
                                          (prix, exécution, argent)
```

La bonne question n'est donc pas « ai-je un compte MT5 ? » mais **« chez quel courtier ai-je un compte, et propose-t-il MT5 ? »**

Un « compte MT5 » se résume à trois informations fournies par le courtier : un **login** (un numéro), un **mot de passe**, et un **nom de serveur**.

### B. Comment mon code parle au marché

```
   Mon code Python  ──►  Terminal MT5 (installé, ouvert, connecté)  ──►  Courtier
```

Le module Python ne parle **pas** directement au courtier : il pilote l'application MT5 installée localement. D'où deux conséquences :

- C'est la raison pour laquelle il ne fonctionne **que sous Windows** ;
- Sur un serveur, le terminal doit rester **ouvert dans une session active**.

### C. Les trois types de comptes

| Type | L'argent | Obtention | Usage dans le projet |
|---|---|---|---|
| **Démo** | Fictif, prix réels | Gratuit, immédiat | Étapes 0 à 8 |
| **Réel** | Le mien | Dépôt + vérification | Hors projet |
| **Prop firm (FTMO)** | Le leur | Frais + réussite d'un Challenge | Étape 9 et après |

### D. Où FTMO intervient

```
   Frais d'inscription  →  CHALLENGE  →  VERIFICATION  →  COMPTE FINANCÉ
                           (identifiants MT5, compte simulé, règles strictes)
```

À chaque étape, FTMO fournit un login, un mot de passe et un serveur MT5. **Techniquement, rien ne change dans mon code** — c'est un compte MT5 comme un autre.

**Point essentiel : FTMO n'est nécessaire qu'à la toute fin.** Les étapes 0 à 8 se font intégralement sur des comptes démo gratuits. Pour la partie académique, FTMO n'est même pas requis : le mémoire s'arrête au paper trading.

### E. Deux courtiers, et c'est volontaire

| | **FTMO (essai gratuit, ~14 j)** | **Démo permanente** (ex. IC Markets) |
|---|---|---|
| Spreads, calcul des lots et des pips | ✅ ceux de la cible | ≈ proches |
| Noms exacts des symboles | ✅ | ≠ différents |
| Règles de drawdown simulées | ✅ | ❌ |
| Connexion continue | ❌ coupée tous les 14 jours | ✅ |
| Historique profond à télécharger | ? à vérifier | ✅ |

**Rôle de chacun :** FTMO est la **référence** (j'apprends leurs conditions réelles et je valide ma couche de risque contre leurs règles) ; la démo permanente est le **cheval de trait** (développement continu, historique long, paper trading de plusieurs semaines sans coupure).

**Ce que l'expiration ne casse pas.** Mes trades sont enregistrés dans **ma base de données** (étape 2), pas lus depuis le compte du courtier. Un compte remis à zéro ne me fait donc rien perdre.

**Trois bénéfices de cette double source :**

1. Elle m'oblige à externaliser la configuration et à créer ma table de correspondance des symboles dès le début, au lieu de tout coder en dur et de le payer au moment du basculement.
2. Comparer les mêmes bougies chez deux courtiers (écarts de prix, de spread, de fuseau) **est** l'analyse de qualité des données attendue au mémoire — impossible à produire avec une source unique.
3. L'écart mesuré entre les deux quantifie de combien mon backtest peut se tromper une fois chez FTMO.

**La contrainte disparaît d'elle-même :** l'expiration tous les 14 jours ne concerne que la phase de développement. Un compte de Challenge payant, puis un compte financé, sont permanents.

### F. À vérifier pendant l'étape 0

- [ ] Jusqu'où remonte l'historique M1 servi par FTMO ? *(une prop firm n'est pas un fournisseur de données — c'est le point le plus incertain)*
- [ ] Les **ticks** sont-ils disponibles, et sur quelle profondeur ? *(tester sur quelques jours seulement, pas de téléchargement massif)*
- [ ] Les données téléchargées restent-elles en cache local après expiration du compte ?
- [ ] Y a-t-il une limite au nombre d'essais gratuits consécutifs ?
- [ ] Quels sont les noms exacts des symboles chez chaque courtier ?

### G. Ticks et bougies : que faut-il télécharger ?

**Un tick** est un événement : chaque fois que le prix bouge, une ligne est enregistrée (moment, prix acheteur, prix vendeur). C'est la donnée brute.

**Une bougie** est un résumé : tous les ticks d'un intervalle compressés en quatre nombres — premier prix (*open*), plus haut (*high*), plus bas (*low*), dernier prix (*close*).

#### Ce que la compression fait perdre : le chemin

```
   Bougie M5 :  Open 1.2700   High 1.2720   Low 1.2690   Close 1.2715

   Histoire A :  1.2700 → 1.2690 → 1.2720 → 1.2715   (descend d'abord)
   Histoire B :  1.2700 → 1.2720 → 1.2690 → 1.2715   (monte d'abord)
```

**Les deux produisent exactement la même bougie.** Elle dit *où* le prix est allé, jamais *dans quel ordre*.

Conséquence directe : acheteur à 1.2700 avec stop à 1.2692 et objectif à 1.2718, l'histoire A me fait perdre et l'histoire B me fait gagner. Le moteur de backtest doit trancher, et il le fait par **convention** (le plus souvent : le pire cas). Avec un risque de 0,2 % par trade, donc des stops serrés, cette ambiguïté se produira **souvent** — ce n'est pas un cas limite.

Deuxième perte : une bougie repose sur un seul prix, alors qu'un tick contient acheteur **et** vendeur — donc le **spread réel** à chaque instant, qui peut à lui seul déclencher un stop serré.

#### Trois niveaux de précision, à des moments différents

| Niveau | Donnée | Rôle | Quand |
|---|---|---|---|
| **1** | Bougies M5, M15, H1... | **Détecter les signaux** — ce que la stratégie regarde | Étapes 1 à 6 |
| **2** | Bougies M1 dans une bougie M5 | Approcher le chemin intra-bougie **à bas coût** | Étape 1, gratuitement |
| **3** | Ticks | **Vérifier que le backtest ne ment pas** : ordre stop/objectif, spread réel, slippage | Avant le passage en live |

Le **niveau 2** est le meilleur rapport précision/effort du projet : cinq bougies M1 dans une M5 ne donnent pas la vérité, mais divisent l'ambiguïté par cinq — et l'historique M1 est profond et rapide à récupérer.

Le **niveau 3** ne sert qu'une fois, pour répondre à une seule question : *rejoués avec les vrais ticks, mes trades donnent-ils le même résultat ?* Si oui, le backtest est fiable ; sinon, je sais de combien il se trompe.

#### En pratique

MT5 permet bien de télécharger les ticks (`copy_ticks_range`), mais avec trois réserves : l'historique est **beaucoup plus court** que celui des bougies (souvent quelques mois contre plusieurs années), le **volume est massif** (des dizaines de millions de lignes par an et par instrument), et la disponibilité chez une prop firm est **incertaine**.

**Décision : à l'étape 0, on télécharge les bougies M1 en priorité**, et on se contente de *tester* la disponibilité des ticks sur quelques jours.

### H. Coût total

| Quand | Quoi | Prix |
|---|---|---|
| Étapes 0 à 8 | Comptes démo | **Gratuit** |
| Étape 7 | Serveur | ~5 à 25 €/mois |
| Après le PFE, au choix | Challenge FTMO | Quelques centaines d'euros |

---

*Document vivant. Chaque étape terminée peut faire évoluer les suivantes.*
