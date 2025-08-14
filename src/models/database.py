# src/models/database.py
import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator
from config.settings import Settings

DB_PATH = Settings.DB.DB_PATH

class Database:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._init_db()

    @contextmanager
    def get_connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self.get_connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA foreign_keys=ON;")

            # Teams
            conn.execute("""
            CREATE TABLE IF NOT EXISTS teams (
                team_id INTEGER PRIMARY KEY,
                name TEXT,
                league_id INTEGER
            );""")

            # Matches (+ scores + status)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                fixture_id INTEGER PRIMARY KEY,
                league_id INTEGER,
                date TEXT,
                status_short TEXT,
                home_team_id INTEGER,
                away_team_id INTEGER,
                goals_home INTEGER,
                goals_away INTEGER
            );""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(date);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_matches_league ON matches(league_id);")

            # 1X2 odds (comme avant)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS odds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fixture_id INTEGER NOT NULL,
                bookmaker_id INTEGER NOT NULL,
                bookmaker_name TEXT,
                home_odd REAL,
                draw_odd REAL,
                away_odd REAL,
                UNIQUE(fixture_id, bookmaker_id) ON CONFLICT REPLACE
            );""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_odds_fixture ON odds(fixture_id);")

            # Nouveaux marchés : Over/Under 2.5
            conn.execute("""
            CREATE TABLE IF NOT EXISTS ou25_odds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fixture_id INTEGER NOT NULL,
                bookmaker_id INTEGER NOT NULL,
                bookmaker_name TEXT,
                over25_odd REAL,
                under25_odd REAL,
                UNIQUE(fixture_id, bookmaker_id) ON CONFLICT REPLACE
            );""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ou25_fixture ON ou25_odds(fixture_id);")

            # Nouveaux marchés : BTTS
            conn.execute("""
            CREATE TABLE IF NOT EXISTS btts_odds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fixture_id INTEGER NOT NULL,
                bookmaker_id INTEGER NOT NULL,
                bookmaker_name TEXT,
                yes_odd REAL,
                no_odd REAL,
                UNIQUE(fixture_id, bookmaker_id) ON CONFLICT REPLACE
            );""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_btts_fixture ON btts_odds(fixture_id);")

            # Team ELO courant
            conn.execute("""
            CREATE TABLE IF NOT EXISTS team_stats (
                team_id INTEGER PRIMARY KEY,
                elo REAL
            );""")

            # Historique ELO par match
            conn.execute("""
            CREATE TABLE IF NOT EXISTS match_elo (
                fixture_id INTEGER PRIMARY KEY,
                home_pre_elo REAL,
                away_pre_elo REAL,
                home_post_elo REAL,
                away_post_elo REAL,
                home_win_prob REAL,
                draw_prob REAL,
                away_win_prob REAL
            );""")

            # Stats méthode “codes” par bookmaker (Bet365/Pinnacle) calculées depuis l'historique
            conn.execute("""
            CREATE TABLE IF NOT EXISTS method_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fixture_id INTEGER NOT NULL,
                method TEXT CHECK(method IN ('B365','PINNACLE')),
                sample_size INTEGER,
                home_win_pct REAL,
                draw_pct REAL,
                away_win_pct REAL,
                over25_pct REAL,
                btts_yes_pct REAL,
                UNIQUE(fixture_id, method) ON CONFLICT REPLACE
            );""")

            # Predictions (étendue à 1X2 + O/U + BTTS) + méthode + marché
            conn.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fixture_id INTEGER NOT NULL,
                market TEXT CHECK(market IN ('1X2','OU25','BTTS')),
                selection TEXT CHECK(selection IN ('HOME','DRAW','AWAY','OVER25','UNDER25','BTTS_YES','BTTS_NO')),
                source_method TEXT,          -- 'ELO','B365','PINNACLE','COMBINED'
                prob REAL,
                odd REAL,
                ev REAL,
                kelly REAL,
                confidence REAL,
                created_at TEXT DEFAULT (datetime('now'))
            );""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pred_fixture ON predictions(fixture_id);")

            # Clones
            conn.execute("""
            CREATE TABLE IF NOT EXISTS clone_matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fixture1_id INTEGER NOT NULL,
                fixture2_id INTEGER NOT NULL,
                similarity_score REAL,
                clone_factors TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_clone_f1 ON clone_matches(fixture1_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_clone_f2 ON clone_matches(fixture2_id);")

db = Database(DB_PATH)
