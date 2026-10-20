"""Le contrat commun, vérifié sur CHAQUE stratégie du catalogue.

Ces tests ne nomment aucune stratégie : ils parcourent le registre. Une stratégie
ajoutée au catalogue y est donc soumise dès sa création, sans qu'on ait à écrire
une ligne de test. C'est le pendant, côté qualité, du principe « ajouter une
stratégie revient à créer un fichier ».

Ce que le contrat garantit :

* la stratégie ne regarde jamais l'avenir ;
* ses paramètres sortent dans le journal et en reviennent sans perte ;
* ses propres contrôles valident chacun des signaux qu'elle émet ;
* elle ne modifie pas les bougies qu'on lui confie.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest
from series import collecter, marche_aleatoire

from marketlab.backtest.verification import verifier
from marketlab.strategies.registre import (
    RegistreError,
    depuis_journal,
    obtenir,
    strategies,
)

CATALOGUE = list(strategies().values())
CODES = [classe.code for classe in CATALOGUE]


@pytest.fixture(scope="module")
def donnees() -> pd.DataFrame:
    return marche_aleatoire()


# --------------------------------------------------------------------------
# Registre
# --------------------------------------------------------------------------


def test_le_catalogue_n_est_pas_vide():
    assert "B1" in strategies()


def test_une_strategie_inconnue_est_refusee_avec_la_liste_des_codes():
    with pytest.raises(RegistreError, match="Codes connus : .*B1"):
        obtenir("B99")


def test_une_ancienne_experience_b1v3_retrouve_la_strategie_b1():
    """Les expériences d'août restent rejouables malgré le renommage."""
    strategie = depuis_journal({"strategie_classe": "ConfluenceZeroSession",
                                "strat_ratio_objectif": 3.0})
    assert strategie is not None
    assert strategie.code == "B1"


def test_une_strategie_retiree_n_est_pas_confondue_avec_une_autre():
    """L'ancienne B1 à trois conditions portait le code « B1 » : elle ne doit
    surtout pas être rejouée avec les règles de la B1 actuelle."""
    assert depuis_journal({"strategie_classe": "ConfluenceRsiMacdEma",
                           "strategie_code": "B1"}) is None


# --------------------------------------------------------------------------
# Contrat, sur chaque stratégie
# --------------------------------------------------------------------------


@pytest.mark.parametrize("classe", CATALOGUE, ids=CODES)
def test_identite(classe):
    assert classe.code and classe.nom
    assert classe().parametres == classe.Parametres()


@pytest.mark.parametrize("classe", CATALOGUE, ids=CODES)
def test_emet_au_moins_un_signal_sur_un_marche_realiste(classe, donnees):
    """Sans signal, tous les autres tests passeraient sans rien prouver."""
    assert collecter(classe(), donnees)


@pytest.mark.parametrize("classe", CATALOGUE, ids=CODES)
def test_ne_modifie_pas_les_bougies_recues(classe, donnees):
    copie = donnees.copy()
    classe().preparer(donnees)
    pd.testing.assert_frame_equal(donnees, copie)


@pytest.mark.parametrize("classe", CATALOGUE, ids=CODES)
def test_pas_de_decision_avant_assez_de_bougies(classe, donnees):
    strategie = classe()
    prepare = strategie.preparer(donnees)
    assert strategie.evaluer(prepare.iloc[: strategie.bougies_minimum - 1]) is None


@pytest.mark.parametrize("classe", CATALOGUE, ids=CODES)
def test_ne_regarde_jamais_l_avenir(classe, donnees):
    """La décision prise à la bougie N ne dépend pas des bougies postérieures.

    On compare deux façons de décider à la bougie N : avec les indicateurs
    calculés sur TOUTE la série, puis calculés sur la série COUPÉE à N. Un
    indicateur qui lirait l'avenir (fenêtre centrée, décalage dans le mauvais
    sens, normalisation sur la série entière) donnerait deux décisions
    différentes. C'est l'erreur la plus fréquente en backtest, et la plus
    flatteuse pour les résultats.
    """
    strategie = classe()
    complet = strategie.preparer(donnees)
    signaux = [b.name for b, _ in collecter(strategie, donnees)]
    # Les bougies de signal, plus quelques bougies sans signal, pour vérifier
    # aussi qu'aucun signal n'apparaît quand on retire l'avenir.
    temoins = complet.index[strategie.bougies_minimum :: 97][:20]
    for instant in [*signaux[:15], *temoins]:
        n = complet.index.get_loc(instant)
        avec_avenir = strategie.evaluer(complet.iloc[: n + 1])
        sans_avenir = strategie.evaluer(strategie.preparer(donnees.iloc[: n + 1]))
        assert (avec_avenir is None) == (sans_avenir is None), f"divergence à {instant}"
        if avec_avenir is not None:
            assert sans_avenir.sens is avec_avenir.sens
            assert sans_avenir.entree == pytest.approx(avec_avenir.entree)
            assert sans_avenir.stop == pytest.approx(avec_avenir.stop)
            assert sans_avenir.objectif == pytest.approx(avec_avenir.objectif)


@pytest.mark.parametrize("classe", CATALOGUE, ids=CODES)
def test_les_parametres_reviennent_du_journal_sans_perte(classe):
    """Aller-retour complet, y compris par JSON comme le fait le vrai journal."""
    strategie = classe()
    enregistres = json.loads(json.dumps({
        "strategie_classe": classe.__name__,
        **strategie.parametres_journal(),
    }))
    rejouee = depuis_journal(enregistres)
    assert rejouee is not None
    assert type(rejouee) is classe
    assert rejouee.parametres == strategie.parametres


@pytest.mark.parametrize("classe", CATALOGUE, ids=CODES)
def test_ses_controles_valident_chacun_de_ses_signaux(classe, donnees):
    """La stratégie et sa propre vérification disent la même chose.

    Si ce test échoue, c'est que les règles appliquées par `evaluer` et celles
    rejouées par `controles` ont divergé : l'inspecteur déclarerait alors non
    conformes des trades corrects, ou l'inverse.
    """
    strategie = classe()
    prepare = strategie.preparer(donnees)
    signaux = collecter(strategie, donnees)
    for bougie, signal in signaux[:30]:
        suivante = prepare.index[prepare.index.get_loc(bougie.name) + 1]
        trade = pd.Series({
            "sens": signal.sens.value,
            "stop_initial": signal.stop,
            "date_entree": suivante,
        })
        controles = verifier(strategie, bougie, trade, {"point": 0.01})
        echecs = [c.condition for c in controles if not c.valide]
        assert not echecs, f"{bougie.name} : {echecs}"
