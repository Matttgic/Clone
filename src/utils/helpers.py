"""
Utilitaires et fonctions helper pour le Football Clone Detector
"""

import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union
import sqlite3

class DateHelper:
    @staticmethod
    def parse_api_date(date_str: str) -> datetime:
        """Parse une date depuis l'API Football"""
        try:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except:
            return datetime.now()
    
    @staticmethod
    def format_match_time(date_str: str) -> str:
        """Formate l'heure d'un match"""
        try:
            dt = DateHelper.parse_api_date(date_str)
            return dt.strftime("%H:%M")
        except:
            return "N/A"
    
    @staticmethod
    def is_today(date_str: str) -> bool:
        """Vérifie si une date est aujourd'hui"""
        try:
            match_date = DateHelper.parse_api_date(date_str).date()
            return match_date == datetime.now().date()
        except:
            return False

class MatchHelper:
    @staticmethod
    def get_match_status_emoji(status: str) -> str:
        """Retourne l'emoji correspondant au statut du match"""
        status_emojis = {
            'NS': '⏰',  # Not Started
            '1H': '🟢',  # First Half
            'HT': '⏸️',   # Half Time
            '2H': '🟢',  # Second Half
            'ET': '⏰',  # Extra Time
            'P': '🥅',   # Penalty
            'FT': '✅',  # Full Time
            'AET': '✅', # After Extra Time
            'PEN': '✅', # Penalty
            'SUSP': '⏸️', # Suspended
            'INT': '⏸️',  # Interrupted
            'PST': '❌', # Postponed
            'CANC': '❌', # Cancelled
            'ABD': '❌', # Abandoned
            'AWD': '⚖️',  # Awarded
            'WO': '⚖️'   # Walkover
        }
        return status_emojis.get(status, '❓')
    
    @staticmethod
    def calculate_total_goals(home_score: int, away_score: int) -> int:
        """Calcule le total de buts d'un match"""
        return (home_score or 0) + (away_score or 0)
    
    @staticmethod
    def get_result_emoji(home_score: int, away_score: int) -> str:
        """Retourne l'emoji du résultat"""
        if home_score > away_score:
            return '🏠'  # Victoire domicile
        elif away_score > home_score:
            return '✈️'   # Victoire extérieur
        else:
            return '🤝'  # Match nul

class OddsHelper:
    @staticmethod
    def calculate_implied_probability(odd: float) -> float:
        """Convertit une côte en probabilité implicite"""
        return (1 / odd) * 100 if odd > 0 else 0
    
    @staticmethod
    def format_odd(odd: float) -> str:
        """Formate une côte pour l'affichage"""
        return f"{odd:.2f}" if odd > 0 else "N/A"
    
    @staticmethod
    def get_value_color(value: float) -> str:
        """Retourne la couleur selon la valeur du bet"""
        if value >= 0.15:
            return "🟢"  # Très bon
        elif value >= 0.10:
            return "🟡"  # Bon
        elif value >= 0.05:
            return "🟠"  # Moyen
        else:
            return "🔴"  # Faible

class ValidationHelper:
    @staticmethod
    def validate_team_id(team_id: Union[int, str]) -> bool:
        """Valide un ID d'équipe"""
        try:
            return int(team_id) > 0
        except:
            return False
    
    @staticmethod
    def validate_odds(home: float, draw: float, away: float) -> bool:
        """Valide un set de côtes"""
        return all(odd > 1.0 for odd in [home, draw, away] if odd)
    
    @staticmethod
    def sanitize_team_name(name: str) -> str:
        """Nettoie le nom d'une équipe"""
        # Supprimer les caractères spéciaux problématiques
        cleaned = re.sub(r'[^\w\s\-\.]', '', name)
        return cleaned.strip()

class StatsHelper:
    @staticmethod
    def calculate_win_rate(wins: int, total: int) -> float:
        """Calcule le taux de victoire"""
        return (wins / total) * 100 if total > 0 else 0
    
    @staticmethod
    def calculate_average(values: List[float]) -> float:
        """Calcule la moyenne d'une liste de valeurs"""
        return sum(values) / len(values) if values else 0
    
    @staticmethod
    def get_form_rating_emoji(points: int) -> str:
        """Retourne l'emoji de forme selon les points"""
        if points >= 12:
            return "🔥"  # Excellente
        elif points >= 9:
            return "👍"  # Bonne
        elif points >= 6:
            return "😐"  # Moyenne
        elif points >= 3:
            return "👎"  # Mauvaise
        else:
            return "💀"  # Très mauvaise
    
    @staticmethod
    def calculate_confidence_level(value: float, elo_diff: float, form_diff: float) -> str:
        """Calcule le niveau de confiance global"""
        score = 0
        
        # Value bet
        if value > 0.15:
            score += 3
        elif value > 0.10:
            score += 2
        elif value > 0.05:
            score += 1
        
        # Différence ELO
        if abs(elo_diff) > 200:
            score += 2
        elif abs(elo_diff) > 100:
            score += 1
        
        # Différence de forme
        if abs(form_diff) > 6:
            score += 1
        
        if score >= 5:
            return "🔥 TRÈS HAUTE"
        elif score >= 3:
            return "⚡ HAUTE"
        elif score >= 2:
            return "📊 MOYENNE"
        else:
            return "⚠️ FAIBLE"

class DatabaseHelper:
    @staticmethod
    def dict_factory(cursor, row):
        """Factory pour convertir les résultats SQLite en dictionnaires"""
        d = {}
        for idx, col in enumerate(cursor.description):
            d[col[0]] = row[idx]
        return d
    
    @staticmethod
    def execute_query(query: str, params: tuple = None) -> List[Dict]:
        """Exécute une requête et retourne les résultats"""
        from src.models.database import db
        
        with db.get_connection() as conn:
            conn.row_factory = DatabaseHelper.dict_factory
            cursor = conn.execute(query, params or ())
            return cursor.fetchall()
    
    @staticmethod
    def get_table_count(table_name: str) -> int:
        """Retourne le nombre d'enregistrements dans une table"""
        try:
            result = DatabaseHelper.execute_query(f"SELECT COUNT(*) as count FROM {table_name}")
            return result[0]['count'] if result else 0
        except:
            return 0

class NotificationHelper:
    @staticmethod
    def format_clone_alert(clone_data: Dict) -> str:
        """Formate une alerte de clone détecté"""
        similarity = clone_data['similarity_score']
        match1 = clone_data['match1']
        match2 = clone_data['match2']
        
        alert = f"🚨 CLONE DÉTECTÉ ({similarity:.1%})\n"
        alert += f"📍 {match1['home_team']} vs {match1['away_team']}\n"
        alert += f"📍 {match2['home_team']} vs {match2['away_team']}\n"
        alert += f"💡 {clone_data['recommendation']}"
        
        return alert
    
    @staticmethod
    def format_value_bet_alert(bet_data: Dict) -> str:
        """Formate une alerte de value bet"""
        alert = f"💎 VALUE BET DÉTECTÉ\n"
        alert += f"🏟️ {bet_data.get('match_name', 'Match')}\n"
        alert += f"📊 {bet_data['outcome'].upper()} @ {bet_data['odd']:.2f}\n"
        alert += f"⚡ Value: {bet_data['value']:.2f}\n"
        alert += f"💰 Mise: {bet_data['stake']:.1%} bankroll"
        
        return alert

# Export des helpers
__all__ = [
    'DateHelper',
    'MatchHelper', 
    'OddsHelper',
    'ValidationHelper',
    'StatsHelper',
    'DatabaseHelper',
    'NotificationHelper'
]
