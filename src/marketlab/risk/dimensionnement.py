"""Combien acheter : la traduction d'un risque en argent en volume d'ordre.

C'est ici, et nulle part ailleurs, que se décide la taille d'une position. La
stratégie dit où entrer et où sortir ; ce module dit combien. Il sert à
l'identique au backtest et au live, puisque c'est le pilote qui l'appelle.
"""

from __future__ import annotations

from marketlab.brokers.base import Specification


def dimensionner(risque_prix: float, montant_vise: float, spec: Specification) -> tuple[float, float]:
    """Traduit un montant à risquer en volume, puis en risque réellement pris.

    Le courtier n'accepte que des volumes multiples d'un pas. On arrondit vers le
    BAS pour ne jamais dépasser le risque visé, sauf si le résultat tombe sous le
    volume minimum : dans ce cas la position ne peut pas être plus petite, et le
    risque réel dépasse la cible. Le retourner tel quel plutôt que de le masquer
    permet de le voir dans l'inspection.

    Retourne (volume, risque réel en devise du compte).
    """
    risque_pips = risque_prix / spec.valeur_pip
    if risque_pips <= 0:
        return 0.0, 0.0

    lots_exacts = montant_vise / (risque_pips * spec.valeur_pip_par_lot)
    lots = int(lots_exacts / spec.volume_pas) * spec.volume_pas
    lots = max(lots, spec.volume_min)
    lots = round(lots, 8)

    risque_reel = lots * risque_pips * spec.valeur_pip_par_lot
    return lots, risque_reel
