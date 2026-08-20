"""Inspecteur de trades : voir chaque position sur le graphique qui l'a produite.

Pourquoi cet écran existe. Les tests automatiques vérifient que le moteur fait ce
qui a été codé. Ils ne peuvent pas vérifier que ce qui a été codé correspond à ce
qu'on voulait. Seul l'œil le peut : une entrée décalée d'une bougie, un stop posé
sur le mauvais creux ou un indicateur qui ne dit pas ce qu'on lirait à la main sont
invisibles dans un tableau de chiffres, et évidents sur un graphique.

Lancement :
    streamlit run app/inspecteur.py    
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from marketlab.backtest import journal
from marketlab.backtest.verification import bougie_de_signal, decimales, verifier
from marketlab.data.historique import obtenir
from marketlab.strategies.confluence import STRATEGIES

st.set_page_config(page_title="Inspecteur de trades", layout="wide")

# Palette : vert et rouge pour les bougies, bleu pour les repères de position.
VERT = "#0e9f6e"
ROUGE = "#e02424"
BLEU = "#1c64f2"
GRIS = "#9ca3af"
ORANGE = "#ff8a4c"


# ---------------------------------------------------------------------------
# Chargement, mis en cache pour ne pas relire à chaque interaction
# ---------------------------------------------------------------------------


@st.cache_data(show_spinner=False)
def bougies_preparees(parametres: dict) -> pd.DataFrame:
    """Reconstruit les bougies AVEC les indicateurs, tels que la simulation les a vus.

    On ne stocke pas ces colonnes avec l'expérience : elles se recalculent à
    l'identique à partir des paramètres enregistrés. C'est aussi une vérification
    en soi, puisqu'un écart signalerait que le code a changé.
    """
    donnees = obtenir(
        parametres["instrument"],
        parametres["courtier"],
        parametres["echelle"],
        pd.Timestamp(parametres["debut_reel"]).to_pydatetime(),
        pd.Timestamp(parametres["fin_reelle"]).to_pydatetime(),
    )
    classe = STRATEGIES.get(str(parametres.get("strategie_code", "B1")), STRATEGIES["B1"])
    strategie = classe(
        periode_ema=int(parametres.get("strat_periode_ema", 200)),
        macd_rapide=int(parametres.get("strat_macd_rapide", 12)),
        macd_lente=int(parametres.get("strat_macd_lente", 26)),
        macd_signal=int(parametres.get("strat_macd_signal", 9)),
        periode_rsi=int(parametres.get("strat_periode_rsi", 14)),
        rsi_plancher=float(parametres.get("strat_rsi_plancher", 50.0)),
        rsi_plafond=float(parametres.get("strat_rsi_plafond", 70.0)),
        bougies_stop=int(parametres.get("strat_bougies_stop", 10)),
        ratio_objectif=float(parametres.get("strat_ratio_objectif", 3.0)),
    )
    return strategie.preparer(donnees)


@st.cache_data(show_spinner=False)
def registre() -> pd.DataFrame:
    return journal.charger_registre()


@st.cache_data(show_spinner=False)
def trades_de(identifiant: str) -> pd.DataFrame:
    return journal.charger_trades(identifiant)


# ---------------------------------------------------------------------------
# Graphique
# ---------------------------------------------------------------------------


def graphique(fenetre: pd.DataFrame, trade: pd.Series, parametres: dict) -> go.Figure:
    """Chandeliers, EMA, MACD et RSI, avec la position tracée par-dessus."""
    figure = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.58, 0.21, 0.21],
        subplot_titles=("Prix", "MACD", "RSI"),
    )

    # --- Prix -------------------------------------------------------------
    figure.add_trace(
        go.Candlestick(
            x=fenetre.index,
            open=fenetre["open"],
            high=fenetre["high"],
            low=fenetre["low"],
            close=fenetre["close"],
            name="Prix",
            increasing_line_color=VERT,
            decreasing_line_color=ROUGE,
        ),
        row=1,
        col=1,
    )
    figure.add_trace(
        go.Scatter(
            x=fenetre.index,
            y=fenetre["ema"],
            name=f"EMA {parametres.get('strat_periode_ema', 200)}",
            line={"color": BLEU, "width": 1.6},
        ),
        row=1,
        col=1,
    )

    # --- Niveaux de la position -------------------------------------------
    niveaux = [
        (trade["entree"], BLEU, "Entrée"),
        (trade["stop_initial"], ROUGE, "Stop"),
        (trade["objectif"], VERT, "Objectif"),
    ]
    d = decimales(parametres)
    for valeur, couleur, etiquette in niveaux:
        figure.add_hline(
            y=float(valeur),
            line={"color": couleur, "width": 1.2, "dash": "dot"},
            annotation_text=f"{etiquette} {valeur:.{d}f}",
            annotation_position="right",
            row=1,
            col=1,
        )

    # --- Entrée et sortie --------------------------------------------------
    achat = trade["sens"] == "achat"
    figure.add_trace(
        go.Scatter(
            x=[trade["date_entree"]],
            y=[trade["entree"]],
            mode="markers",
            marker={
                "symbol": "triangle-up" if achat else "triangle-down",
                "size": 16,
                "color": BLEU,
                "line": {"width": 1, "color": "white"},
            },
            name="Entrée",
        ),
        row=1,
        col=1,
    )
    gagnant = trade["resultat_r"] > 0
    figure.add_trace(
        go.Scatter(
            x=[trade["date_sortie"]],
            y=[trade["sortie"]],
            mode="markers",
            marker={
                "symbol": "x",
                "size": 14,
                "color": VERT if gagnant else ROUGE,
                "line": {"width": 1, "color": "white"},
            },
            name=f"Sortie ({trade['motif']})",
        ),
        row=1,
        col=1,
    )

    # La bougie de signal précède l'entrée : c'est celle où les conditions
    # étaient réunies. C'est elle qu'il faut regarder pour vérifier les règles.
    avant_entree = fenetre.index[fenetre.index < trade["date_entree"]]
    if len(avant_entree):
        figure.add_vline(
            x=avant_entree[-1],
            line={"color": ORANGE, "width": 1.2, "dash": "dash"},
            annotation_text="bougie de signal",
            annotation_position="top",
        )

    # --- MACD --------------------------------------------------------------
    couleurs = [VERT if v >= 0 else ROUGE for v in fenetre["macd"] - fenetre["macd_signal"]]
    figure.add_trace(
        go.Bar(
            x=fenetre.index,
            y=fenetre["macd"] - fenetre["macd_signal"],
            marker_color=couleurs,
            name="Histogramme",
            opacity=0.45,
        ),
        row=2,
        col=1,
    )
    figure.add_trace(
        go.Scatter(x=fenetre.index, y=fenetre["macd"], name="MACD",
                   line={"color": BLEU, "width": 1.4}),
        row=2, col=1,
    )
    figure.add_trace(
        go.Scatter(x=fenetre.index, y=fenetre["macd_signal"], name="Signal",
                   line={"color": ORANGE, "width": 1.4}),
        row=2, col=1,
    )
    figure.add_hline(y=0, line={"color": GRIS, "width": 0.8}, row=2, col=1)

    # --- RSI ---------------------------------------------------------------
    figure.add_trace(
        go.Scatter(x=fenetre.index, y=fenetre["rsi"], name="RSI",
                   line={"color": "#7e3af2", "width": 1.6}),
        row=3, col=1,
    )
    plancher = float(parametres.get("strat_rsi_plancher", 50.0))
    plafond = float(parametres.get("strat_rsi_plafond", 70.0))
    for niveau, couleur in ((plancher, VERT), (plafond, ROUGE), (100 - plafond, VERT),
                            (100 - plancher, ROUGE)):
        figure.add_hline(y=niveau, line={"color": couleur, "width": 0.9, "dash": "dot"},
                         row=3, col=1)
    figure.update_yaxes(range=[0, 100], row=3, col=1)

    figure.update_layout(
        height=820,
        margin={"l": 10, "r": 90, "t": 40, "b": 10},
        xaxis_rangeslider_visible=False,
        showlegend=True,
        legend={"orientation": "h", "y": 1.06, "x": 0},
        hovermode="x unified",
    )
    return figure


#: Mois abrégés en français. On ne passe pas par la locale du système : elle
#: dépend de la machine, et un déploiement Linux ne la partagerait pas.
_MOIS = ("janv", "févr", "mars", "avr", "mai", "juin",
         "juil", "août", "sept", "oct", "nov", "déc")


def marque_positions(parametres: dict) -> str:
    """Suffixe signalant un nombre de positions simultanées inhabituel.

    Une position à la fois est le réglage par défaut : l'afficher partout
    alourdirait sans rien apprendre. En revanche, deux expériences qui ne
    diffèrent QUE par ce réglage portent le même code de stratégie, et rien ne
    les distinguerait dans la liste sans cette marque.
    """
    valeur = parametres.get("positions_simultanees", 1)
    # Le registre stocke l'absence de limite comme une absence de valeur. Selon
    # que la colonne a été lue en entier ou en flottant, elle revient en None ou
    # en NaN : les deux disent la même chose.
    if valeur is None or pd.isna(valeur):
        return " · positions sans limite"
    if str(valeur) in {"1", "1.0"}:
        return ""
    return f" · {int(float(valeur))} positions max"


def periode_lisible(parametres: dict) -> str:
    """Période réellement couverte par les données, en clair.

    On affiche `debut_reel` et `fin_reelle`, pas les dates demandées : la
    première est repoussée quand les cotations ne sont pas encore propres au
    courtier, et la seconde s'arrête à la dernière bougie disponible. Montrer
    la demande plutôt que le réel ferait croire à une couverture qui n'existe pas.
    """
    debut = pd.Timestamp(parametres.get("debut_reel"))
    fin = pd.Timestamp(parametres.get("fin_reelle"))
    if pd.isna(debut) or pd.isna(fin):
        return "Période inconnue"
    annees = (fin - debut).days / 365.25
    return (
        f"{_MOIS[debut.month - 1]} {debut.year} → "
        f"{_MOIS[fin.month - 1]} {fin.year}  ({annees:.1f} ans)"
    )


# ---------------------------------------------------------------------------
# Écran
# ---------------------------------------------------------------------------

st.title("Inspecteur de trades")

experiences = registre()

if experiences.empty:
    st.warning(
        "Aucune expérience enregistrée. Lancer d'abord :\n\n"
        "`python scripts/20_backtest.py`"
    )
    st.stop()

# --- Choix de l'expérience -------------------------------------------------
with st.sidebar:
    st.header("Expérience")

    def etiquette(i: int) -> str:
        ligne = experiences.iloc[i]
        return (
            f"{ligne['horodatage'][:16]}  ·  {ligne.get('p_instrument', '?')} "
            f"{ligne.get('p_echelle', '')}  ·  {ligne.get('p_strategie_code', '?')} "
            f"·  {ligne.get('p_courtier', '?')}"
            + marque_positions(
                {c[2:]: ligne[c] for c in experiences.columns if c.startswith("p_")}
            )
        )

    choix = st.selectbox(
        "Simulation à inspecter",
        options=range(len(experiences)),
        format_func=etiquette,
    )
    ligne = experiences.iloc[choix]
    parametres = {c[2:]: ligne[c] for c in experiences.columns if c.startswith("p_")}

    # La période des données passe avant tout le reste. Un chiffre lu sans elle
    # ne veut rien dire : les mêmes règles sur quatre ans ou sur neuf ans ne
    # racontent pas la même histoire, et deux expériences du même instrument se
    # confondent au premier coup d'œil si seule leur durée les sépare.
    st.markdown(f"### {periode_lisible(parametres)}")
    st.caption(
        f"**{parametres.get('instrument', '?')} {parametres.get('echelle', '')}** "
        f"chez **{parametres.get('courtier', '?')}** · "
        f"{int(parametres.get('bougies', 0)):,} bougies · "
        f"spread {float(parametres.get('spread_points', 0)):.1f} pts"
    )

    st.divider()
    st.caption(f"**Nature** : {ligne['nature']}")
    if ligne["note"]:
        st.caption(f"**Note** : {ligne['note']}")
    st.caption(f"**Code** : `{ligne['version_code']}`")
    if ligne["code_modifie"]:
        st.caption("modifications non validées au lancement")
    st.caption(f"**Empreinte** : `{ligne['empreinte']}`")

identifiant = ligne["identifiant"]
trades = trades_de(identifiant)

if trades.empty:
    st.warning("Cette expérience ne contient aucun trade.")
    st.stop()

# --- Résumé ----------------------------------------------------------------
# Rappel de la période sur l'écran principal : le panneau latéral se replie, et
# on inspecte souvent un trade sans l'avoir sous les yeux.
st.markdown(
    f"**{parametres.get('instrument', '?')} {parametres.get('echelle', '')}** "
    f"chez {parametres.get('courtier', '?')} · données de "
    f"**{periode_lisible(parametres)}** · "
    f"stratégie {parametres.get('strategie_code', '?')} "
    f"à {float(parametres.get('strat_ratio_objectif', 3)):.0f} R"
    + marque_positions(parametres)
)

colonnes = st.columns(6)
colonnes[0].metric("Trades", f"{len(trades):,}")
colonnes[1].metric("Réussite", f"{(trades['resultat_r'] > 0).mean() * 100:.1f} %")
colonnes[2].metric("Total", f"{trades['resultat_r'].sum():.0f} R")
colonnes[3].metric("Espérance", f"{trades['resultat_r'].mean():.3f} R")
colonnes[4].metric("Spread", f"{float(parametres.get('spread_points', 0)):.1f} pts")
colonnes[5].metric("Objectif", f"{float(parametres.get('strat_ratio_objectif', 3)):.0f} R")

# --- Ce que l'échantillon permet réellement d'affirmer -----------------------
# Sans cette lecture, on conclurait d'une centaine de trades ce qu'ils ne
# permettent pas de dire. L'intervalle est recalculé sur la sélection filtrée.
resultats_r = trades["resultat_r"]
if len(resultats_r) >= 2 and resultats_r.std(ddof=1) > 0:
    esperance = float(resultats_r.mean())
    erreur = float(resultats_r.std(ddof=1)) / float(len(resultats_r)) ** 0.5
    bas, haut = esperance - 1.96 * erreur, esperance + 1.96 * erreur
    concluant = bas > 0 or haut < 0

    if concluant:
        st.success(
            f"**Résultat concluant à 95 %.** La vraie espérance se situe entre "
            f"{bas:+.3f} et {haut:+.3f} R par trade. Zéro est en dehors de "
            f"l'intervalle : la stratégie se distingue de l'absence d'avantage."
        )
    else:
        necessaires = (
            int((1.96 * float(resultats_r.std(ddof=1)) / abs(esperance)) ** 2)
            if esperance != 0
            else 0
        )
        complement = (
            f" Il en faudrait environ **{necessaires:,}** pour trancher."
            if necessaires > len(resultats_r)
            else ""
        )
        st.warning(
            f"**Résultat non concluant.** La vraie espérance se situe entre "
            f"{bas:+.3f} et {haut:+.3f} R par trade, intervalle qui **contient zéro**. "
            f"Avec {len(resultats_r):,} trades, on ne peut affirmer ni que cette "
            f"stratégie gagne, ni qu'elle perd.{complement}"
        )

# --- Filtres ---------------------------------------------------------------
with st.sidebar:
    st.header("Filtres")
    sens = st.multiselect("Sens", sorted(trades["sens"].unique()),
                          default=sorted(trades["sens"].unique()))
    motifs = st.multiselect("Sortie", sorted(trades["motif"].unique()),
                            default=sorted(trades["motif"].unique()))
    annees = sorted(pd.to_datetime(trades["date_entree"]).dt.year.unique())
    annee = st.multiselect("Année", annees, default=annees)
    marge = st.slider("Bougies affichées autour du trade", 30, 400, 120, step=10)

filtres = (
    trades["sens"].isin(sens)
    & trades["motif"].isin(motifs)
    & pd.to_datetime(trades["date_entree"]).dt.year.isin(annee)
)
selection = trades[filtres].reset_index(drop=True)

st.caption(f"{len(selection)} trades correspondent aux filtres.")

if selection.empty:
    st.stop()

# --- Choix du trade --------------------------------------------------------
onglet_liste, onglet_graphe, onglet_capital = st.tabs(
    ["Liste des trades", "Inspection", "Évolution du capital"]
)

with onglet_liste:
    # « resultat_pips » est volontairement absent : sur un stop il vaut toujours
    # l'opposé du risque, sur un objectif trois fois celui-ci. Il n'apprend rien
    # que « motif » et « risque_pips » ne disent déjà. La colonne reste dans le
    # fichier de trades, seul l'affichage l'écarte.
    colonnes_liste = [
        "sens", "date_entree", "date_sortie", "entree", "stop_initial",
        "objectif", "sortie", "motif", "risque_pips", "lots", "risque_reel",
        "resultat_r", "bougies",
    ]

    if "risque_reel" in selection.columns:
        risques = selection["risque_reel"]
        st.caption(
            f"**Cohérence du risque** — médiane {risques.median():,.2f}, "
            f"de {risques.min():,.2f} à {risques.max():,.2f}, "
            f"écart-type {risques.std():,.2f}. "
            "Un écart marqué d'une ligne à l'autre signalerait un défaut de "
            "dimensionnement."
        )

    # Les prix s'affichent avec la précision de l'instrument : cinq décimales
    # pour une paire de devises, deux pour l'or. Un format figé rendrait l'une
    # des deux illisible.
    prix = f"%.{decimales(parametres)}f"

    st.dataframe(
        selection[[c for c in colonnes_liste if c in selection.columns]],
        use_container_width=True,
        height=520,
        column_config={
            "entree": st.column_config.NumberColumn("Entrée", format=prix),
            "stop_initial": st.column_config.NumberColumn("Stop", format=prix),
            "objectif": st.column_config.NumberColumn("Objectif", format=prix),
            "sortie": st.column_config.NumberColumn("Sortie", format=prix),
            "risque_pips": st.column_config.NumberColumn(
                "Risque (pips)", format="%.1f"
            ),
            "lots": st.column_config.NumberColumn("Lots", format="%.2f"),
            "risque_reel": st.column_config.NumberColumn(
                "Risqué", format="%.2f", help="Montant réellement risqué, après arrondi du volume"
            ),
            "resultat_r": st.column_config.NumberColumn("Résultat (R)", format="%.2f"),
        },
    )

with onglet_graphe:
    gauche, droite = st.columns([3, 1])
    with droite:
        index = st.number_input(
            "Trade n°", min_value=0, max_value=len(selection) - 1, value=0, step=1
        )
        if st.button("Trade au hasard", use_container_width=True):
            index = int(selection.sample(1).index[0])
            st.session_state["hasard"] = index
        index = int(st.session_state.get("hasard", index))
        index = min(index, len(selection) - 1)

    trade = selection.iloc[index]

    with gauche:
        resultat = float(trade["resultat_r"])
        couleur = "🟢" if resultat > 0 else ("🔴" if resultat < 0 else "⚪")
        st.subheader(
            f"{couleur} {trade['sens'].upper()} du "
            f"{pd.Timestamp(trade['date_entree']):%d/%m/%Y %H:%M} "
            f"— sortie {trade['motif']} — {resultat:+.2f} R"
        )

    with st.spinner("Reconstruction des indicateurs..."):
        preparees = bougies_preparees(parametres)

    debut = pd.Timestamp(trade["date_entree"])
    fin = pd.Timestamp(trade["date_sortie"])
    positions = preparees.index
    i_debut = max(0, positions.searchsorted(debut) - marge)
    i_fin = min(len(positions), positions.searchsorted(fin) + marge)
    fenetre = preparees.iloc[i_debut:i_fin]

    # --- Vérification des conditions ---------------------------------------
    signal = bougie_de_signal(preparees, debut)
    if signal is not None:
        tableau = pd.DataFrame(
            [
                {
                    "Condition": c.condition,
                    "Attendu": c.attendu,
                    "Constaté": c.constate,
                    "OK": "✅" if c.valide else "❌",
                }
                for c in verifier(signal, trade, parametres)
            ]
        )

        st.markdown("**Conditions d'entrée, rejouées sur la bougie de signal**")
        st.dataframe(tableau, use_container_width=True, hide_index=True)

        if "❌" in tableau["OK"].values:
            st.error(
                "Une condition n'est pas vérifiée. Soit le moteur diverge de la "
                "stratégie, soit la règle affichée ici ne correspond pas à celle "
                "qui a servi. À élucider avant d'exploiter ce backtest."
            )

    st.plotly_chart(graphique(fenetre, trade, parametres), use_container_width=True)


# ---------------------------------------------------------------------------
# Évolution du capital
# ---------------------------------------------------------------------------

with onglet_capital:
    courbe = selection.sort_values("date_sortie").reset_index(drop=True)
    capital_initial = float(parametres.get("capital_initial", 100_000.0))

    # La courbe est reconstruite à partir des résultats filtrés plutôt que reprise
    # telle quelle : sinon les filtres afficheraient un capital incohérent avec
    # les trades montrés.
    courbe["capital"] = capital_initial + courbe["resultat_montant"].cumsum()
    courbe["cumul_r"] = courbe["resultat_r"].cumsum()
    sommets = courbe["capital"].cummax()
    courbe["sous_le_sommet"] = (courbe["capital"] - sommets) / sommets * 100

    mesures = st.columns(4)
    mesures[0].metric("Capital final", f"{courbe['capital'].iloc[-1]:,.0f}")
    mesures[1].metric(
        "Rendement", f"{(courbe['capital'].iloc[-1] / capital_initial - 1) * 100:.2f} %"
    )
    mesures[2].metric("Pire creux", f"{courbe['sous_le_sommet'].min():.2f} %")
    mesures[3].metric("Cumul", f"{courbe['cumul_r'].iloc[-1]:.0f} R")

    evolution = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        row_heights=[0.62, 0.38],
        subplot_titles=("Capital", "Écart au plus haut atteint"),
    )
    evolution.add_trace(
        go.Scatter(
            x=courbe["date_sortie"],
            y=courbe["capital"],
            name="Capital",
            line={"color": BLEU, "width": 1.8},
        ),
        row=1,
        col=1,
    )
    evolution.add_hline(
        y=capital_initial,
        line={"color": GRIS, "width": 1, "dash": "dash"},
        annotation_text="capital de départ",
        row=1,
        col=1,
    )
    # Le creux sous le plus haut est ce qu'un investisseur subit réellement :
    # un compte de financement échoue sur cette courbe, pas sur le résultat final.
    evolution.add_trace(
        go.Scatter(
            x=courbe["date_sortie"],
            y=courbe["sous_le_sommet"],
            name="Écart au sommet",
            fill="tozeroy",
            line={"color": ROUGE, "width": 1.2},
        ),
        row=2,
        col=1,
    )
    evolution.update_yaxes(ticksuffix=" %", row=2, col=1)
    evolution.update_layout(
        height=560,
        margin={"l": 10, "r": 20, "t": 40, "b": 10},
        showlegend=False,
        hovermode="x unified",
    )
    st.plotly_chart(evolution, use_container_width=True)

    gauche, droite = st.columns(2)

    with gauche:
        st.markdown("**Répartition des résultats**")
        histogramme = go.Figure(
            go.Histogram(
                x=selection["resultat_r"],
                nbinsx=40,
                marker_color=BLEU,
                opacity=0.85,
            )
        )
        histogramme.update_layout(
            height=320,
            margin={"l": 10, "r": 10, "t": 10, "b": 10},
            xaxis_title="Résultat en R",
            yaxis_title="Nombre de trades",
            bargap=0.05,
        )
        st.plotly_chart(histogramme, use_container_width=True)

    with droite:
        st.markdown("**Résultat cumulé par année**")
        annuel = selection.copy()
        annuel["annee"] = pd.to_datetime(annuel["date_entree"]).dt.year
        par_an = annuel.groupby("annee").agg(
            trades=("resultat_r", "size"),
            total_r=("resultat_r", "sum"),
            gagnants=("resultat_r", lambda serie: int((serie > 0).sum())),
        )
        par_an["reussite"] = (par_an["gagnants"] / par_an["trades"] * 100).round(1)
        st.dataframe(par_an, use_container_width=True, height=320)
