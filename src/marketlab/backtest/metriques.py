"""Mesures de performance d'une simulation.

Deux familles volontairement distinctes :

* **En R** (multiples du risque pris) : indépendantes de la taille de position,
  donc comparables entre stratégies et entre instruments. C'est la mesure honnête.
* **En montant** : dépendantes du dimensionnement, mais seules à révéler le
  drawdown, qui est la contrainte réelle d'un compte de financement.

SIGNIFICATIVITÉ

Un résultat de backtest est une moyenne calculée sur un échantillon. Comme toute
moyenne d'échantillon, il porte une incertitude, et une espérance négative peut
très bien provenir du hasard si les trades sont peu nombreux. On calcule donc,
à côté de chaque résultat, l'intervalle dans lequel se trouve vraisemblablement la
VRAIE espérance. Quand zéro tombe dans cet intervalle, la stratégie n'est pas
distinguable de l'absence d'avantage : on ne peut affirmer ni qu'elle gagne, ni
qu'elle perd.

Deux réserves sur ce calcul, à mentionner dès qu'on s'en sert :

* Il suppose les trades **indépendants**. Des positions successives sur le même
  instrument ne le sont pas tout à fait : elles partagent des régimes de marché.
  La confiance réelle est donc un peu plus faible que celle affichée.
* Il ne dit rien de la stabilité dans le temps. Un résultat significatif sur
  quatre ans peut n'être porté que par une seule année.

Une limite à connaître : le drawdown calculé ici est mesuré **entre deux trades**,
à partir du capital après chaque clôture. Le drawdown réellement subi en cours de
position est plus profond. La mesure fidèle exige de suivre le capital bougie par
bougie ; elle sera traitée avec la couche de risque.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from marketlab.backtest.moteur import Resultat


@dataclass
class Metriques:
    """Résumé chiffré d'une simulation."""

    trades: int = 0
    gagnants: int = 0
    perdants: int = 0
    neutres: int = 0
    taux_reussite: float = 0.0

    total_r: float = 0.0
    esperance_r: float = 0.0
    meilleur_r: float = 0.0
    pire_r: float = 0.0

    profit_factor: float = 0.0

    capital_initial: float = 0.0
    capital_final: float = 0.0
    rendement_pct: float = 0.0
    drawdown_max_pct: float = 0.0

    # Incertitude autour de l'esperance, voir l'en-tete du module.
    ecart_type_r: float = 0.0
    erreur_standard_r: float = 0.0
    ic95_bas: float = 0.0
    ic95_haut: float = 0.0
    statistique_t: float = 0.0
    significatif: bool = False
    trades_pour_conclure: int = 0

    duree_moyenne_bougies: float = 0.0
    repartition_sorties: dict[str, int] | None = None

    signaux_emis: int = 0
    signaux_ignores: int = 0
    entrees_refusees: int = 0


def _drawdown_max(capitaux: pd.Series) -> float:
    """Plus forte baisse depuis un sommet, en pourcentage.

    C'est la mesure qui compte pour un compte de financement : ce n'est pas le
    résultat final qui fait échouer, c'est le creux traversé en chemin.
    """
    if capitaux.empty:
        return 0.0
    sommets = capitaux.cummax()
    baisses = (capitaux - sommets) / sommets
    return float(abs(baisses.min()) * 100)


#: Valeur critique de la loi normale pour un intervalle bilateral a 95 %.
_SEUIL_95 = 1.96


def _renseigner_significativite(m: Metriques, resultats_r: pd.Series) -> None:
    """Calcule l'incertitude autour de l'espérance et le verdict associé.

    `trades_pour_conclure` répond à une question pratique : combien de trades
    faudrait-il, à dispersion et espérance constantes, pour que le résultat
    devienne concluant ? C'est ce qui permet de savoir si un test mérite d'être
    étendu ou si sa conclusion est définitivement hors de portée.
    """
    if len(resultats_r) < 2:
        return

    m.ecart_type_r = float(resultats_r.std(ddof=1))
    if m.ecart_type_r == 0:
        return

    m.erreur_standard_r = m.ecart_type_r / np.sqrt(len(resultats_r))
    m.ic95_bas = m.esperance_r - _SEUIL_95 * m.erreur_standard_r
    m.ic95_haut = m.esperance_r + _SEUIL_95 * m.erreur_standard_r
    m.statistique_t = m.esperance_r / m.erreur_standard_r
    m.significatif = abs(m.statistique_t) > _SEUIL_95

    if m.esperance_r != 0:
        necessaire = (_SEUIL_95 * m.ecart_type_r / abs(m.esperance_r)) ** 2
        m.trades_pour_conclure = int(np.ceil(necessaire))


def calculer(resultat: Resultat) -> Metriques:
    """Calcule toutes les mesures à partir d'une simulation."""
    m = Metriques(
        capital_initial=resultat.capital_initial,
        capital_final=resultat.capital_final,
        signaux_emis=resultat.signaux_emis,
        signaux_ignores=resultat.signaux_ignores,
        entrees_refusees=resultat.entrees_refusees,
        repartition_sorties={},
    )

    if not resultat.trades:
        return m

    tableau = resultat.en_tableau()
    resultats_r = tableau["resultat_r"]

    m.trades = len(tableau)
    m.gagnants = int((resultats_r > 0).sum())
    m.perdants = int((resultats_r < 0).sum())
    m.neutres = int((resultats_r == 0).sum())
    m.taux_reussite = m.gagnants / m.trades * 100

    m.total_r = float(resultats_r.sum())
    m.esperance_r = float(resultats_r.mean())
    m.meilleur_r = float(resultats_r.max())
    m.pire_r = float(resultats_r.min())

    gains = resultats_r[resultats_r > 0].sum()
    pertes = abs(resultats_r[resultats_r < 0].sum())
    # Sans aucune perte, le rapport est infini : on le signale plutôt que de
    # renvoyer une valeur arbitraire.
    m.profit_factor = float(gains / pertes) if pertes > 0 else float(np.inf)

    m.rendement_pct = (m.capital_final / m.capital_initial - 1) * 100
    m.drawdown_max_pct = _drawdown_max(tableau["capital_apres"])

    _renseigner_significativite(m, resultats_r)

    m.duree_moyenne_bougies = float(tableau["bougies"].mean())
    m.repartition_sorties = tableau["motif"].value_counts().to_dict()

    return m


def formater(m: Metriques, titre: str = "Résultats") -> str:
    """Rend les mesures lisibles dans un terminal."""
    if m.trades == 0:
        return f"\n{titre}\n{'=' * 62}\n  Aucun trade exécuté.\n"

    lignes = [
        "",
        titre,
        "=" * 62,
        "",
        "  ACTIVITÉ",
        f"    Signaux émis                {m.signaux_emis:>12,}",
        f"    Ignorés (position ouverte)  {m.signaux_ignores:>12,}",
        f"    Entrées refusées (écart)    {m.entrees_refusees:>12,}",
        f"    Trades exécutés             {m.trades:>12,}",
        "",
        "  RÉSULTAT EN R  (indépendant de la taille de position)",
        f"    Total                       {m.total_r:>12.1f} R",
        f"    Espérance par trade         {m.esperance_r:>12.3f} R",
        f"    Meilleur / pire             {m.meilleur_r:>7.2f} / {m.pire_r:.2f} R",
        f"    Profit factor               {m.profit_factor:>12.2f}",
        "",
        "  SIGNIFICATIVITÉ  (l'espérance se distingue-t-elle de zéro ?)",
        f"    Écart-type des résultats   {m.ecart_type_r:>12.3f} R",
        f"    Intervalle à 95 %          [{m.ic95_bas:>+7.3f} ; {m.ic95_haut:>+7.3f}] R",
        f"    Statistique t              {m.statistique_t:>12.2f}",
        (
            "    VERDICT                     résultat significatif à 95 %"
            if m.significatif
            else "    VERDICT                     NON concluant : zéro est dans l'intervalle"
        ),
        (
            f"    Trades nécessaires          {m.trades_pour_conclure:>12,}"
            if not m.significatif and m.trades_pour_conclure
            else ""
        ),
        "",
        "  RÉUSSITE",
        f"    Gagnants                    {m.gagnants:>8,}  ({m.taux_reussite:.1f} %)",
        f"    Perdants                    {m.perdants:>8,}",
        f"    Neutres (break-even)        {m.neutres:>8,}",
        "",
        "  CAPITAL",
        f"    Initial                     {m.capital_initial:>12,.2f}",
        f"    Final                       {m.capital_final:>12,.2f}",
        f"    Rendement                   {m.rendement_pct:>12.2f} %",
        f"    Drawdown maximum            {m.drawdown_max_pct:>12.2f} %",
        "",
        "  SORTIES",
    ]

    for motif, nombre in sorted(
        (m.repartition_sorties or {}).items(), key=lambda x: -x[1]
    ):
        part = nombre / m.trades * 100
        lignes.append(f"    {motif:<26} {nombre:>8,}  ({part:.1f} %)")

    lignes += [
        "",
        f"  Durée moyenne d'un trade : {m.duree_moyenne_bougies:.1f} bougies",
        "",
    ]
    return "\n".join(lignes)
