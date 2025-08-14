# streamlit_app/pages/03_Dashboard_performance.py
import streamlit as st
import pandas as pd
from datetime import datetime, timezone
from config.settings import Settings
from src.models.database import db

st.set_page_config(page_title="Dashboard Performance", page_icon="📊", layout="wide")
st.title("📊 Dashboard — Performance par méthode & marché")

MIN_VALUE = Settings.BETTING.MIN_VALUE

@st.cache_data(ttl=120)
def load_history():
    with db.get_connection() as conn:
        matches = pd.read_sql_query("""
            SELECT fixture_id, date, goals_home, goals_away
            FROM matches
            WHERE goals_home IS NOT NULL AND goals_away IS NOT NULL
            ORDER BY date DESC
        """, conn)
        preds = pd.read_sql_query("""
            SELECT fixture_id, market, selection, source_method, prob, odd, ev, kelly, created_at
            FROM predictions
        """, conn)
    return matches, preds

def settle_bet(row, gh, ga):
    """Renvoie 1 si gagné, 0 si perdu. Marchés: 1X2, OU25, BTTS."""
    if row["market"] == "1X2":
        if row["selection"] == "HOME": return 1 if gh > ga else 0
        if row["selection"] == "DRAW": return 1 if gh == ga else 0
        if row["selection"] == "AWAY": return 1 if gh < ga else 0
        return 0
    if row["market"] == "OU25":
        total = gh + ga
        if row["selection"] == "OVER25": return 1 if total > 2.5 else 0
        if row["selection"] == "UNDER25": return 1 if total < 2.5 else 0
        return 0
    if row["market"] == "BTTS":
        both = (gh > 0 and ga > 0)
        if row["selection"] == "BTTS_YES": return 1 if both else 0
        if row["selection"] == "BTTS_NO":  return 1 if (not both) else 0
        return 0
    return 0

def evaluate_performance(matches, preds, ev_threshold: float, pick_policy: str):
    """
    pick_policy:
      - 'MAX_EV': sélectionne la ligne de prédiction (par fixture/méthode/marché) à EV max
      - 'EV_THRESHOLD_ALL': prend toutes les lignes EV >= seuil (multiple bets possible)
    """
    # Restreindre aux fixtures déjà joués
    past_ids = set(matches["fixture_id"].tolist())
    p = preds[preds.fixture_id.isin(past_ids)].copy()
    if p.empty:
        return pd.DataFrame(columns=["source_method","market","bets","wins","winrate","roi","units"])

    # On évalue séparément par méthode & marché
    out_rows = []
    for (method, market), g in p.groupby(["source_method","market"]):
        # join goals
        g = g.merge(matches[["fixture_id","goals_home","goals_away"]], on="fixture_id", how="left")
        g = g.dropna(subset=["goals_home","goals_away"])
        # politique de sélection
        if pick_policy == "MAX_EV":
            # garder la meilleure EV par fixture
            g = g.sort_values(["fixture_id","ev"], ascending=[True, False])
            g = g.groupby("fixture_id", as_index=False).first()
        else:  # EV_THRESHOLD_ALL
            g = g[g["ev"] >= ev_threshold]

        if g.empty:
            continue

        g["win"] = g.apply(lambda r: settle_bet(r, int(r["goals_home"]), int(r["goals_away"])), axis=1)

        # Flat stake 1u
        g["pl"] = g.apply(lambda r: (r["odd"] - 1.0) if r["win"] == 1 else -1.0, axis=1)

        bets = len(g)
        wins = int(g["win"].sum())
        winrate = wins / bets if bets else 0.0
        units = g["pl"].sum()
        roi = units / bets if bets else 0.0

        out_rows.append({
            "source_method": method,
            "market": market,
            "bets": bets,
            "wins": wins,
            "winrate": winrate,
            "roi": roi,
            "units": units
        })

    out = pd.DataFrame(out_rows)
    if not out.empty:
        out["winrate"] = (out["winrate"]*100).round(1)
        out["roi"] = (out["roi"]*100).round(1)
        out["units"] = out["units"].round(2)
    return out.sort_values(["market","source_method"])

matches, preds = load_history()

if matches.empty or preds.empty:
    st.info("Pas encore assez d'historique pour calculer les performances.")
    st.stop()

colA, colB, colC = st.columns(3)
with colA:
    pick_policy = st.selectbox(
        "Politique de sélection",
        options=[("MAX_EV","Max EV par match"), ("EV_THRESHOLD_ALL","Toutes les bets EV ≥ seuil")],
        format_func=lambda x: x[1],
        index=0
    )[0]
with colB:
    ev_threshold = st.slider("Seuil EV (value) pour compter une bet", min_value=1.00, max_value=1.20, value=float(MIN_VALUE), step=0.01)
with colC:
    st.write("")

perf = evaluate_performance(matches, preds, ev_threshold, pick_policy)

if perf.empty:
    st.info("Aucune bet à évaluer avec ces critères.")
else:
    st.subheader("Performance par méthode et marché")
    st.dataframe(
        perf.rename(columns={"source_method":"Méthode","market":"Marché","bets":"Bets","wins":"Wins","winrate":"Winrate (%)","roi":"ROI (%)","units":"Unités"}),
        use_container_width=True
    )

    # KPIs rapides par méthode (tous marchés confondus)
    kpis = perf.groupby("source_method").agg(
        Bets=("bets","sum"),
        Unités=("units","sum")
    ).reset_index()
    st.subheader("Synthèse par méthode (tous marchés)")
    st.dataframe(kpis, use_container_width=True)
