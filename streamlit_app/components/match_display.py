import streamlit as st
from typing import Dict
from src.services.elo_system import elo_system
from src.services.odds_analyzer import odds_analyzer
from src.services.stats_analyzer import stats_analyzer

class MatchDisplayComponent:
    def __init__(self):
        pass
    
    def show_match_analysis(self, match: Dict):
        """Affiche l'analyse complète d'un match"""
        
        # Informations de base
        col1, col2, col3 = st.columns([2, 1, 2])
        
        with col1:
            st.write(f"**🏠 {match['home_team']}**")
            st.write(f"ELO: {match.get('home_elo', 1500):.0f}")
        
        with col2:
            st.write("**VS**")
            match_time = match.get('match_date', 'N/A')
            st.write(f"⏰ {match_time}")
        
        with col3:
            st.write(f"**✈️ {match['away_team']}**")
            st.write(f"ELO: {match.get('away_elo', 1500):.0f}")
        
        st.markdown("---")
        
        # Tabs pour différentes analyses
        tab1, tab2, tab3, tab4 = st.tabs([
            "🎯 Prédiction ELO", 
            "💰 Analyse Côtes", 
            "📊 Statistiques", 
            "⚡ Recommandation"
        ])
        
        with tab1:
            self.show_elo_prediction(match)
        
        with tab2:
            self.show_odds_analysis(match)
        
        with tab3:
            self.show_team_stats(match)
        
        with tab4:
            self.show_betting_recommendation(match)
    
    def show_elo_prediction(self, match: Dict):
        """Affiche la prédiction basée sur ELO"""
        home_team_id = match.get('home_team_id')
        away_team_id = match.get('away_team_id')
        
        if home_team_id and away_team_id:
            prediction = elo_system.predict_match(home_team_id, away_team_id)
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("🏠 Victoire Domicile", f"{prediction['home_win_prob']:.1%}")
                st.progress(prediction['home_win_prob'])
            
            with col2:
                st.metric("🤝 Match Nul", f"{prediction['draw_prob']:.1%}")
                st.progress(prediction['draw_prob'])
            
            with col3:
                st.metric("✈️ Victoire Extérieur", f"{prediction['away_win_prob']:.1%}")
                st.progress(prediction['away_win_prob'])
            
            # Différence ELO et interprétation
            elo_diff = prediction['elo_difference']
            st.write(f"**Différence ELO:** {elo_diff:+.0f}")
            
            if abs(elo_diff) > 200:
                st.warning("⚠️ Écart ELO important - Favori très clair")
            elif abs(elo_diff) > 100:
                st.info("ℹ️ Léger favori")
            else:
                st.success("✅ Match équilibré")
    
    def show_odds_analysis(self, match: Dict):
        """Affiche l'analyse des côtes"""
        fixture_id = match.get('fixture_id')
        
        if not fixture_id:
            st.warning("Pas d'ID de match disponible")
            return
        
        # Récupérer la prédiction ELO pour le calcul des value bets
        home_team_id = match.get('home_team_id')
        away_team_id = match.get('away_team_id')
        
        if home_team_id and away_team_id:
            elo_prediction = elo_system.predict_match(home_team_id, away_team_id)
            odds_analysis = odds_analyzer.analyze_match_odds(fixture_id, elo_prediction)
            
            if 'error' in odds_analysis:
                st.warning(f"⚠️ {odds_analysis['error']}")
                return
            
            # Afficher les côtes par bookmaker
            for bookmaker, data in odds_analysis.get('bookmakers', {}).items():
                st.subheader(f"💼 {bookmaker}")
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("1", f"{data['home_odd']:.2f}")
                    if data['home_value'] > 0:
                        st.success(f"Value: {data['home_value']:.2f}")
                
                with col2:
                    st.metric("X", f"{data['draw_odd']:.2f}")
                    if data['draw_value'] > 0:
                        st.success(f"Value: {data['draw_value']:.2f}")
                
                with col3:
                    st.metric("2", f"{data['away_odd']:.2f}")
                    if data['away_value'] > 0:
                        st.success(f"Value: {data['away_value']:.2f}")
                
                with col4:
                    st.metric("Marge", f"{data['margin']:.1f}%")
            
            # Value bets recommandés
            value_bets = odds_analysis.get('best_value_bets', [])
            if value_bets:
                st.subheader("💎 Value Bets Détectés")
                for bet in value_bets:
                    st.success(
                        f"🎯 **{bet['bookmaker']}** - {bet['outcome'].upper()} "
                        f"@ {bet['odd']:.2f} (Value: {bet['value']:.2f}) "
                        f"- Mise recommandée: {bet['recommended_stake']:.1%}"
                    )
            else:
                st.info("Aucun value bet détecté")
    
    def show_team_stats(self, match: Dict):
        """Affiche les statistiques des équipes"""
        home_team_id = match.get('home_team_id')
        away_team_id = match.get('away_team_id')
        league_id = match.get('league_id')
        
        if all([home_team_id, away_team_id, league_id]):
            prediction_data = stats_analyzer.get_match_prediction_data(
                home_team_id, away_team_id, league_id
            )
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("🏠 Équipe Domicile")
                home_analysis = prediction_data.get('home_team_analysis', {})
                self.display_team_metrics(home_analysis)
            
            with col2:
                st.subheader("✈️ Équipe Extérieur")
                away_analysis = prediction_data.get('away_team_analysis', {})
                self.display_team_metrics(away_analysis)
            
            # Confrontations directes
            h2h = prediction_data.get('head_to_head', {})
            if h2h.get('total_matches', 0) > 0:
                st.subheader("⚔️ Confrontations Directes")
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Total matchs", h2h['total_matches'])
                
                with col2:
                    st.metric("Victoires domicile", h2h['home_wins'])
                
                with col3:
                    st.metric("Matchs nuls", h2h['draws'])
                
                with col4:
                    st.metric("Victoires extérieur", h2h['away_wins'])
                
                st.write(f"**Tendance récente:** {h2h.get('recent_trend', 'N/A')}")
                st.write(f"**Moyenne buts:** {h2h.get('avg_goals', 0):.1f}")
        else:
            st.warning("Données insuffisantes pour l'analyse statistique")
    
    def display_team_metrics(self, team_analysis: Dict):
        """Affiche les métriques d'une équipe"""
        if not team_analysis:
            st.warning("Pas de données disponibles")
            return
        
        basic_stats = team_analysis.get('basic_stats', {})
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("Win Rate", f"{team_analysis.get('win_rate', 0):.1%}")
            st.metric("Buts pour/match", f"{basic_stats.get('avg_goals_for', 0):.1f}")
            st.metric("Clean Sheets", f"{team_analysis.get('clean_sheet_rate', 0):.1%}")
        
        with col2:
            st.metric("Points/match", f"{team_analysis.get('points_per_game', 0):.1f}")
            st.metric("Buts contre/match", f"{basic_stats.get('avg_goals_against', 0):.1f}")
            st.metric("Forme", f"{basic_stats.get('form_points', 0):.0f} pts")
        
        # Classification et forme
        classification = team_analysis.get('team_classification', 'Moyenne')
        form_rating = basic_stats.get('form_points', 0)
        
        if classification == 'Elite':
            st.success(f"🏆 Équipe {classification}")
        elif classification == 'Forte':
            st.info(f"💪 Équipe {classification}")
        elif classification == 'Moyenne':
            st.warning(f"📊 Équipe {classification}")
        else:
            st.error(f"📉 Équipe {classification}")
    
    def show_betting_recommendation(self, match: Dict):
        """Affiche la recommandation de pari"""
        fixture_id = match.get('fixture_id')
        home_team_id = match.get('home_team_id')
        away_team_id = match.get('away_team_id')
        
        if not all([fixture_id, home_team_id, away_team_id]):
            st.warning("Données insuffisantes pour la recommandation")
            return
        
        # Combiner toutes les analyses
        elo_prediction = elo_system.predict_match(home_team_id, away_team_id)
        odds_analysis = odds_analyzer.analyze_match_odds(fixture_id, elo_prediction)
        
        # Générer la recommandation finale
        recommendation = self.generate_betting_recommendation(
            elo_prediction, odds_analysis, match
        )
        
        # Afficher la recommandation
        if recommendation['recommended']:
            st.success("✅ PARI RECOMMANDÉ")
            
            st.write(f"**Type de pari:** {recommendation['bet_type']}")
            st.write(f"**Côte:** {recommendation['odds']:.2f}")
            st.write(f"**Mise recommandée:** {recommendation['stake']:.1%} de la bankroll")
            st.write(f"**Confiance:** {recommendation['confidence']:.1%}")
            
            st.info(f"💡 {recommendation['reasoning']}")
            
            # Stocker la prédiction en base
            self.store_prediction(fixture_id, recommendation)
        
        else:
            st.warning("⚠️ AUCUN PARI RECOMMANDÉ")
            st.write(f"**Raison:** {recommendation.get('reasoning', 'Pas de value détectée')}")
    
    def generate_betting_recommendation(self, elo_pred: Dict, odds_analysis: Dict, match: Dict) -> Dict:
        """Génère une recommandation de pari basée sur toutes les analyses"""
        
        best_value_bets = odds_analysis.get('best_value_bets', [])
        
        if not best_value_bets:
            return {
                'recommended': False,
                'reasoning': 'Aucun value bet détecté'
            }
        
        # Prendre le meilleur value bet
        best_bet = max(best_value_bets, key=lambda x: x['value'])
        
        # Calculer la confiance basée sur différents facteurs
        confidence_factors = []
        base_confidence = min(best_bet['value'] * 0.5, 0.8)  # Max 80%
        
        # Ajuster selon la différence ELO
        elo_diff = abs(elo_pred['elo_difference'])
        if elo_diff > 150:
            confidence_factors.append(0.1)  # +10% si grosse différence ELO
        
        final_confidence = min(base_confidence + sum(confidence_factors), 0.9)
        
        return {
            'recommended': True,
            'bet_type': best_bet['outcome'],
            'odds': best_bet['odd'],
            'stake': min(best_bet['recommended_stake'], 0.05),  # Max 5%
            'confidence': final_confidence,
            'value': best_bet['value'],
            'reasoning': f"Value bet détecté avec une valeur de {best_bet['value']:.2f}"
        }
    
    def store_prediction(self, fixture_id: int, recommendation: Dict):
        """Stocke la prédiction en base de données"""
        from src.models.database import db
        
        with db.get_connection() as conn:
            conn.execute(
                """INSERT INTO predictions 
                   (fixture_id, prediction_type, predicted_outcome, confidence, 
                    recommended_bet, stake, potential_return)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    fixture_id,
                    recommendation['bet_type'],
                    recommendation['bet_type'],
                    recommendation['confidence'],
                    f"{recommendation['bet_type']} @ {recommendation['odds']:.2f}",
                    recommendation['stake'],
                    recommendation['stake'] * recommendation['odds']
                )
            )
            conn.commit()
