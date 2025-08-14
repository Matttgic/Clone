# streamlit_app/pages/02_Comparateur_du_jour.py
import streamlit as st
import pandas as pd
from datetime import datetime, timezone
from src.models.database import db
from config.settings import Settings

st.set_page_config(page_title="Comparateur (ELO / B365 / PIN / Combined)", page_icon="🧮", layout="wide")
st.title("🧮 Comparateur — ELO vs Codes (Bet365 / Pinnacle) vs Combiné")

MIN_VALUE = Settings.BETTING.MIN_VALUE

@st.cache_data(ttl=60)
def load_today_data():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with db.get_connection() as conn:
        matches = pd.read_sql_query("""
            SELECT m.fixture_id, m.league_id, m.date, m.home_team_id, m.away_team_id, 
                   th.name as home_team, ta.name as away_team
            FROM matches m
            LEFT JOIN teams th ON th.team_id=m.home_team_id
            LEFT JOIN teams ta ON ta.team_id=m.away_team_id
            WHERE substr(m.date,1,10)=?
            ORDER BY m.date ASC
        """, conn, params=(today,))

        preds = pd.read_sql_query("""
            SELECT fixture_id, market, selection, source_method, prob, odd, ev, kelly, confidence, created_at
            FROM predictions
            WHERE substr(created_at,1,10) >= date('now','-1 day')  -- sécurité
        """, conn)

        method_stats = pd.read_sql_query("""
            SELECT fixture_id, method, sample_size, home_win_pct, draw_pct, away_win_pct, over25_pct, btts_yes_pct
            FROM method_stats
        """, conn)

    return matches, preds, method_stats

def fancy_pct(x):
    return f"{x*100:.1f}%" if pd.notnull(x) else "—"

def value_tag(ev):
    if pd.isna(ev): return ""
    return "✅ Value" if ev >= MIN_VALUE else ""

def build_market_table(preds_df: pd.DataFrame, market: str, samples_row_b365, samples_row_pin):
    """
    Construit un tableau comparatif pour un marché donné:
    Colonnes: Selection, Odd, ELO Prob/EV, B365 Prob/EV, PIN Prob/EV, COMBINED Prob/EV, Value? (sur EV COMBINED).
    """
    df = preds_df[preds_df["market"] == market].copy()
    if df.empty:
        return pd.DataFrame()

    # Pivot des probs & EV par méthode
    def pick(selection, method, field):
        rows = df[(df.selection == selection) & (df.source_method == method)]
        return rows[field].iloc[0] if not rows.empty else None

    selections = []
    if market == "1X2":
        selections = ["HOME", "DRAW", "AWAY"]
    elif market == "OU25":
        selections = ["OVER25", "UNDER25"]
    elif market == "BTTS":
        selections = ["BTTS_YES", "BTTS_NO"]

    rows = []
    for sel in selections:
        odd = pick(sel, "COMBINED", "odd") or pick(sel, "B365", "odd") or pick(sel, "PINNACLE", "odd") or pick(sel, "ELO", "odd")
        elo_prob = pick(sel, "ELO", "prob")
        elo_ev   = pick(sel, "ELO", "ev")
        b_prob   = pick(sel, "B365", "prob")
        b_ev     = pick(sel, "B365", "ev")
        p_prob   = pick(sel, "PINNACLE", "prob")
        p_ev     = pick(sel, "PINNACLE", "ev")
        c_prob   = pick(sel, "COMBINED", "prob")
        c_ev     = pick(sel, "COMBINED", "ev")

        rows.append({
            "Sélection": sel,
            "Cote": odd,
            "ELO Prob": elo_prob, "ELO EV": elo_ev,
            "B365 Prob": b_prob,  "B365 EV": b_ev,
            "PIN Prob": p_prob,   "PIN EV": p_ev,
            "COMB Prob": c_prob,  "COMB EV": c_ev,
            "Value?": value_tag(c_ev)
        })

    out = pd.DataFrame(rows)
    # mise en forme lisible
    for col in ["ELO Prob","B365 Prob","PIN Prob","COMB Prob"]:
        out[col] = out[col].apply(lambda x: fancy_pct(x) if pd.notnull(x) else "—")
    for col in ["Cote","ELO EV","B365 EV","PIN EV","COMB EV"]:
        out[col] = out[col].apply(lambda x: f"{x:.3f}" if pd.notnull(x) else "—")

    # Ajouter info sample sizes pour B365 / PIN si disponible
    foot = ""
    if samples_row_b365 is not None:
        foot += f"📊 B365 échantillon: {int(samples_row_b365['sample_size'])} matchs — "
        if market == "1X2":
            foot += f"HW={fancy_pct(samples_row_b365['home_win_pct'])}, D={fancy_pct(samples_row_b365['draw_pct'])}, AW={fancy_pct(samples_row_b365['away_win_pct'])}"
        elif market == "OU25":
            foot += f"Over2.5={fancy_pct(samples_row_b365['over25_pct'])}"
        elif market == "BTTS":
            foot += f"BTTS Yes={fancy_pct(samples_row_b365['btts_yes_pct'])}"
    if samples_row_pin is not None:
        foot += " | " if foot else ""
        foot += f"📊 Pinnacle échantillon: {int(samples_row_pin['sample_size'])} matchs — "
        if market == "1X2":
            foot += f"HW={fancy_pct(samples_row_pin['home_win_pct'])}, D={fancy_pct(samples_row_pin['draw_pct'])}, AW={fancy_pct(samples_row_pin['away_win_pct'])}"
        elif market == "OU25":
            foot += f"Over2.5={fancy_pct(samples_row_pin['over25_pct'])}"
        elif market == "BTTS":
            foot += f"BTTS Yes={fancy_pct(samples_row_pin['btts_yes_pct'])}"

    return out, foot

matches, preds, method_stats = load_today_data()

if matches.empty:
    st.info("Aucun match aujourd'hui dans la base. Assure-toi que le workflow a tourné (`update_data.py` + `generate_predictions.py`).")
    st.stop()

for _, m in matches.iterrows():
    fid = int(m["fixture_id"])
    st.subheader(f"Fixture {fid} — {m['home_team']} vs {m['away_team']} — {m['date']}")

    pv = preds[preds.fixture_id == fid].copy()
    if pv.empty:
        st.warning("Pas de prédictions pour ce match (vérifie que `odds_method_stats` et `generate_predictions` ont tourné).")
        st.divider()
        continue

    # Méthode stats (samples) par bookmaker
    b365 = method_stats[(method_stats.fixture_id == fid) & (method_stats.method == "B365")]
    b365 = b365.iloc[0] if not b365.empty else None
    pin  = method_stats[(method_stats.fixture_id == fid) & (method_stats.method == "PINNACLE")]
    pin  = pin.iloc[0] if not pin.empty else None

    # 1X2
    t1x2, foot1 = build_market_table(pv, "1X2", b365, pin)
    st.markdown("### 1X2")
    if isinstance(t1x2, pd.DataFrame) and not t1x2.empty:
        st.dataframe(t1x2, use_container_width=True)
        if foot1: st.caption(foot1)
    else:
        st.info("Pas de données 1X2 pour ce match.")

    # OU 2.5
    tou, foot2 = build_market_table(pv, "OU25", b365, pin)
    st.markdown("### Over/Under 2.5")
    if isinstance(tou, pd.DataFrame) and not tou.empty:
        st.dataframe(tou, use_container_width=True)
        if foot2: st.caption(foot2)
    else:
        st.info("Pas de données Over/Under 2.5 pour ce match.")

    # BTTS
    tbt, foot3 = build_market_table(pv, "BTTS", b365, pin)
    st.markdown("### BTTS (Both Teams To Score)")
    if isinstance(tbt, pd.DataFrame) and not tbt.empty:
        st.dataframe(tbt, use_container_width=True)
        if foot3: st.caption(foot3)
    else:
        st.info("Pas de données BTTS pour ce match.")

    # Synthèse recommandations: on liste les selections COMBINED avec EV >= MIN_VALUE
    recs = pv[(pv.source_method == "COMBINED") & (pv.ev >= MIN_VALUE)][["market","selection","prob","odd","ev","kelly"]].copy()
    if not recs.empty:
        st.success("Recommandations (méthode COMBINED) — EV ≥ seuil :")
        recs["Prob (%)"] = (recs["prob"]*100).round(1)
        recs["Odd"] = recs["odd"].round(3)
        recs["EV"] = recs["ev"].round(3)
        recs["Kelly (%)"] = (recs["kelly"]*100).round(1)
        st.dataframe(recs[["market","selection","Prob (%)","Odd","EV","Kelly (%)"]], use_container_width=True)
    else:
        st.info("Aucune recommandation COMBINED (EV insuffisant).")

    st.divider()
