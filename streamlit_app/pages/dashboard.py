import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import pandas as pd

from src.utils.helpers import DatabaseHelper, StatsHelper

def show_dashboard():
    """Affiche le dashboard principal"""
    st.header("📊 Dashboard Principal")
    
    # Métriques principales
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_teams = DatabaseHelper.get_table_count("teams")
        st.metric("👥 Équipes", total_teams)
    
    with col2:
        total_matches = DatabaseHelper.get_table_count("matches WHERE status = 'FT'")
        st.metric("⚽ Matchs terminés", total_matches)
    
    with col3:
        today_matches = DatabaseHelper.get_table_count(
            "matches WHERE DATE(match_date) = DATE('now')"
        )
        st.metric("🗓️ Matchs aujourd'hui", today_matches)
    
    with col4:
        total_predictions = DatabaseHelper.get_table_count("predictions")
        st.metric("🎯 Prédictions", total_predictions)
    
    st.markdown("---")
    
    # Graphiques
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📈 Évolution ELO Top 10")
        show_elo_evolution_chart()
    
    with col2:
        st.subheader("💰 Performance des Paris")
        show_betting_performance_chart()
    
    # Tableau des derniers clones
    st.subheader("🔍 Derniers Clones Détectés")
    show_recent_clones_table()

def show_elo_evolution_chart():
    """Graphique d'évolution des ELO"""
    # Simuler des données d'évolution ELO
    top_teams = DatabaseHelper.execute_query("""
        SELECT name, elo_rating 
        FROM teams 
        WHERE elo_rating > 1600
        ORDER BY elo_rating DESC 
        LIMIT 10
    """)
    
    if top_teams:
        df = pd.DataFrame(top_teams)
        fig = px.bar(df, x='name', y='elo_rating', 
                     title="Top 10 Équipes par ELO")
        fig.update_xaxes(tickangle=45)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Pas assez de données ELO")

def show_betting_performance_chart():
    """Graphique des performances de paris"""
    betting_data = DatabaseHelper.execute_query("""
        SELECT 
            DATE(created_at) as date,
            SUM(profit_loss) as daily_profit
        FROM predictions 
        WHERE actual_outcome IS NOT NULL
        AND created_at > datetime('now', '-30 days')
        GROUP BY DATE(created_at)
        ORDER BY date
    """)
    
    if betting_data:
        df = pd.DataFrame(betting_data)
        df['cumulative_profit'] = df['daily_profit'].cumsum()
        
        fig = px.line(df, x='date', y='cumulative_profit',
                      title="Évolution des Profits")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Pas de données de paris disponibles")

def show_recent_clones_table():
    """Tableau des clones récents"""
    recent_clones = DatabaseHelper.execute_query("""
        SELECT 
            c.similarity_score,
            c.clone_factors,
            c.detected_at,
            h1.name || ' vs ' || a1.name as match1,
            h2.name || ' vs ' || a2.name as match2
        FROM clone_matches c
        JOIN matches m1 ON c.fixture1_id = m1.fixture_id
        JOIN matches m2 ON c.fixture2_id = m2.fixture_id
        JOIN teams h1 ON m1.home_team_id = h1.id
        JOIN teams a1 ON m1.away_team_id = a1.id
        JOIN teams h2 ON m2.home_team_id = h2.id
        JOIN teams a2 ON m2.away_team_id = a2.id
        ORDER BY c.detected_at DESC
        LIMIT 10
    """)
    
    if recent_clones:
        df = pd.DataFrame(recent_clones)
        df['similarity_score'] = df['similarity_score'].apply(lambda x: f"{x:.1%}")
        df['detected_at'] = pd.to_datetime(df['detected_at']).dt.strftime('%d/%m %H:%M')
        
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Aucun clone détecté récemment")
