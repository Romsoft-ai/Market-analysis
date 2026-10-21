"""Vérifie le flux live sur un faux terminal : bougies clôturées seulement, fabriquées comme en backtest."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd

from marketlab.data.historique import agreger
from marketlab.live.flux import FluxMT5

DEBUT = pd.Timestamp("2026-10-21 10:00", tz="UTC")


class FauxTerminal:
    TIMEFRAME_M1 = 1

    def __init__(self, minutes: int, heure: pd.Timestamp) -> None:
        generateur = np.random.default_rng(1)
        prix = 1.3 + np.cumsum(generateur.normal(0, 0.0002, minutes))
        temps = pd.date_range(DEBUT, periods=minutes, freq="1min")
        self.m1 = [
            {"time": int(t.timestamp()), "open": p, "high": p + 0.0003, "low": p - 0.0003,
             "close": p + 0.0001, "tick_volume": 5, "spread": 8, "real_volume": 0}
            for t, p in zip(temps, prix, strict=True)
        ]
        self.heure = heure
        self.demandes: list[int] = []

    def symbol_select(self, symbole, actif):
        return True

    def symbol_info_tick(self, symbole):
        return SimpleNamespace(time=int(self.heure.timestamp()))

    def copy_rates_from_pos(self, symbole, echelle, depart, nombre):
        self.demandes.append(nombre)
        return self.m1[-nombre:]

    def last_error(self):
        return (0, "")


def test_une_bougie_en_cours_de_formation_n_est_jamais_rendue():
    """À 10:52, la bougie de 10:45 n'est pas finie : seules 10:00, 10:15 et 10:30 sortent."""
    terminal = FauxTerminal(minutes=53, heure=DEBUT + pd.Timedelta(minutes=52))
    bougies = FluxMT5(terminal, "icmarket").bougies_cloturees("GBPUSD")
    assert list(bougies.index.strftime("%H:%M")) == ["10:00", "10:15", "10:30"]


def test_la_bougie_est_rendue_des_que_sa_fin_est_passee_selon_le_serveur():
    terminal = FauxTerminal(minutes=60, heure=DEBUT + pd.Timedelta(minutes=60, seconds=5))
    bougies = FluxMT5(terminal, "icmarket").bougies_cloturees("GBPUSD")
    assert bougies.index[-1] == DEBUT + pd.Timedelta(minutes=45)


def test_les_bougies_live_sont_celles_du_backtest():
    """Même recette de fabrication : agréger les M1 avec la fonction du backtest."""
    terminal = FauxTerminal(minutes=120, heure=DEBUT + pd.Timedelta(minutes=120, seconds=5))
    flux = FluxMT5(terminal, "icmarket")
    live = flux.bougies_cloturees("GBPUSD")
    backtest = agreger(flux.m1("GBPUSD"), "15min")
    pd.testing.assert_frame_equal(live, backtest)


def test_sans_heure_serveur_rien_n_est_rendu():
    terminal = FauxTerminal(minutes=60, heure=DEBUT)
    terminal.symbol_info_tick = lambda symbole: None
    assert FluxMT5(terminal, "icmarket").bougies_cloturees("GBPUSD").empty


def test_le_prechauffage_demande_assez_de_minutes():
    """2 000 bougies M15 de préchauffage : 30 000 bougies M1 demandées au terminal."""
    terminal = FauxTerminal(minutes=60, heure=DEBUT + pd.Timedelta(hours=1))
    FluxMT5(terminal, "icmarket").bougies_cloturees("GBPUSD")
    assert terminal.demandes == [30_000]
