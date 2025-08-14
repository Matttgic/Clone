# streamlit_app/pages/01_Matchs_du_jour.py
import streamlit as st
import pandas as pd
from src.models.database import db
from src.services.elo_system import elo_system
from src.services.odds_analyzer import odds_analyzer
from src.services.clone_detector import clone_detector

st.set_page_config(page_title="Matchs du jour", page_icon="🏆", layout="wide")
st.title("🏆 Matchs & Value Bets")

@st.cache_data(ttl=60)
def load_data():
    with db.get_connection() as conn:
        matches = pd.read_sql_query("""
            SELECT m.fixture_id, m.league_id, m.date, 
                   m.home_team_id, th.name as home_team,
                   m.away_team_id, ta.name as away_team
            FROM matches m
            LEFT JOIN teams th ON th.team_id = m.home_team_id
            LEFT JOIN teams ta ON ta.team_id = m.away_team_id
            ORDER BY date ASC
        """, conn)

        odds = pd.read_sql_query("""
            SELECT fixture_id, bookmaker_name, home_odd, draw_odd, away_odd
            FROM odds
            ORDER BY fixture_id, bookmaker_name
        """, conn)

        preds = pd.read_sql_query("""
            SELECT fixture_id, selection, prob, odd, ev, kelly, confidence, created_at
            FROM predictions ORDER BY created_at DESC
        """, conn)

        clones = pd.read_sql_query("""
            SELECT fixture1_id, fixture2_id, similarity_score, clone_factors, created_at
            FROM clone_matches ORDER BY created_at DESC
        """, conn)

    return matches, odds, preds, clones

matches, odds, preds, clones = load_data()

if matches.empty:
    st.info("Aucun match en base. Lance d'abord le seed et la génération de prédictions.")
else:
    for _, row in matches.iterrows():
        fid = int(row["fixture_id"])
        st.subheader(f"Fixture {fid}: {row['home_team']} vs {row['away_team']} — {row['date']}")

        # Odds table
        o = odds[odds.fixture_id == fid]
        st.caption("Cotes disponibles")
        st.dataframe(o, use_container_width=True)

        # ELO & Probas
        p = elo_system.predict_match(int(row["home_team_id"]), int(row["away_team_id"]))
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("ELO Home", f"{p['home_elo']:.0f}")
        col2.metric("ELO Away", f"{p['away_elo']:.0f}")
        col3.metric("P(Home)", f"{p['home_win_prob']*100:.1f}%")
        col4.metric("P(Nul)", f"{p['draw_prob']*100:.1f}%")
        col5.metric("P(Away)", f"{p['away_win_prob']*100:.1f}%")

        # Predictions/value bets
        pv = preds[preds.fixture_id == fid]
        if pv.empty:
            st.warning("Pas de value bet retenu pour ce match.")
        else:
            st.success("Value bets détectés :")
            st.dataframe(
                pv[["selection","prob","odd","ev","kelly","confidence"]]
                  .assign(prob=lambda d: (d.prob*100).round(1),
                          ev=lambda d: d.ev.round(3),
                          kelly=lambda d: (d.kelly*100).round(1),
                          confidence=lambda d: (d.confidence*100).round(0))
                  .rename(columns={"prob":"Prob (%)","ev":"EV","kelly":"Kelly (%)","confidence":"Confiance (%)"}),
                use_container_width=True
            )

        # Clones où ce match apparaît
        cc = clones[(clones.fixture1_id == fid) | (clones.fixture2_id == fid)]
        if not cc.empty:
            st.info("Clones détectés sur ce match :")
            st.dataframe(
                cc.assign(similarity_score=lambda d: (d.similarity_score*100).round(1))
                  .rename(columns={"similarity_score":"Similarity (%)", "clone_factors":"Facteurs"}),
                use_container_width=True
            )
        st.divider()
