import sqlite3
from contextlib import contextmanager
from config.settings import Settings
import os

class Database:
    def __init__(self):
        self.db_path = Settings.DB.DB_PATH
        self._ensure_db_directory()
        self._init_database()
    
    def _ensure_db_directory(self):
        """Crée le répertoire data s'il n'existe pas"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
    
    @contextmanager
    def get_connection(self):
        """Context manager pour les connexions à la base"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def _init_database(self):
        """Initialise les tables de la base de données"""
        with self.get_connection() as conn:
            # Table des équipes avec Elo
            conn.execute('''
                CREATE TABLE IF NOT EXISTS teams (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    logo TEXT,
                    league_id INTEGER,
                    elo_rating REAL DEFAULT 1500,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Table des matchs
            conn.execute('''
                CREATE TABLE IF NOT EXISTS matches (
                    id INTEGER PRIMARY KEY,
                    fixture_id INTEGER UNIQUE,
                    home_team_id INTEGER,
                    away_team_id INTEGER,
                    league_id INTEGER,
                    match_date TIMESTAMP,
                    status TEXT,
                    home_score INTEGER,
                    away_score INTEGER,
                    home_elo_before REAL,
                    away_elo_before REAL,
                    home_elo_after REAL,
                    away_elo_after REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (home_team_id) REFERENCES teams (id),
                    FOREIGN KEY (away_team_id) REFERENCES teams (id)
                )
            ''')
            
            # Table des côtes
            conn.execute('''
                CREATE TABLE IF NOT EXISTS odds (
                    id INTEGER PRIMARY KEY,
                    fixture_id INTEGER,
                    bookmaker_id INTEGER,
                    bookmaker_name TEXT,
                    home_odd REAL,
                    draw_odd REAL,
                    away_odd REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (fixture_id) REFERENCES matches (fixture_id)
                )
            ''')
            
            # Table des statistiques des équipes
            conn.execute('''
                CREATE TABLE IF NOT EXISTS team_stats (
                    id INTEGER PRIMARY KEY,
                    team_id INTEGER,
                    league_id INTEGER,
                    season INTEGER,
                    matches_played INTEGER,
                    wins INTEGER,
                    draws INTEGER,
                    losses INTEGER,
                    goals_for INTEGER,
                    goals_against INTEGER,
                    clean_sheets INTEGER,
                    failed_to_score INTEGER,
                    avg_goals_for REAL,
                    avg_goals_against REAL,
                    form_points REAL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (team_id) REFERENCES teams (id)
                )
            ''')
            
            # Table des prédictions et paris
            conn.execute('''
                CREATE TABLE IF NOT EXISTS predictions (
                    id INTEGER PRIMARY KEY,
                    fixture_id INTEGER,
                    prediction_type TEXT,
                    predicted_outcome TEXT,
                    confidence REAL,
                    recommended_bet TEXT,
                    stake REAL,
                    potential_return REAL,
                    actual_outcome TEXT,
                    profit_loss REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (fixture_id) REFERENCES matches (fixture_id)
                )
            ''')
            
            # Table des clones détectés
            conn.execute('''
                CREATE TABLE IF NOT EXISTS clone_matches (
                    id INTEGER PRIMARY KEY,
                    fixture1_id INTEGER,
                    fixture2_id INTEGER,
                    similarity_score REAL,
                    clone_factors TEXT,
                    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()

# Instance globale
db = Database()
