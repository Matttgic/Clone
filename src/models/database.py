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
            # Matches
            conn.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                fixture_id INTEGER PRIMARY KEY,
                league_id INTEGER,
                date TEXT,                     -- ISO 8601
                home_team_id INTEGER,
                away_team_id INTEGER
            );""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(date);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_matches_league ON matches(league_id);")
            # Odds
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
            # Team stats (ELO)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS team_stats (
                team_id INTEGER PRIMARY KEY,
                elo REAL
            );""")
            # Predictions / value bets
            conn.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fixture_id INTEGER NOT NULL,
                selection TEXT CHECK(selection IN ('HOME','DRAW','AWAY')),
                prob REAL,
                odd REAL,
                ev REAL,             -- expected value: prob * odd
                kelly REAL,          -- fraction Kelly
                confidence REAL,
                created_at TEXT DEFAULT (datetime('now'))
            );""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pred_fixture ON predictions(fixture_id);")
            # Clone matches
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
