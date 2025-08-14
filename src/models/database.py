import sqlite3
import os

DB_PATH = os.path.join("data", "football.db")


class Database:
    def __init__(self, path):
        self.path = path
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.path)

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS matches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fixture_id TEXT UNIQUE,
                    date TEXT,
                    league_id TEXT,
                    season TEXT,
                    home_team TEXT,
                    away_team TEXT,
                    home_score INTEGER,
                    away_score INTEGER,
                    status TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS team_stats (
                    team_id TEXT PRIMARY KEY,
                    elo REAL DEFAULT 1500,
                    updated_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS odds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fixture_id TEXT,
                    bookmaker_id TEXT,
                    bookmaker_name TEXT,
                    home_odd REAL,
                    draw_odd REAL,
                    away_odd REAL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_matches_teams ON matches(home_team, away_team)")

    def _ensure_team_seed(self, team_id):
        team_id = str(team_id).strip()  # ✅ Forcer en texte pour éviter les erreurs datatype mismatch
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO team_stats (team_id, elo, updated_at)
                VALUES (?, 1500.0, datetime('now'))
                """,
                (team_id,)
            )

    def insert_match(self, fixture_id, date, league_id, season, home, away, home_score=None, away_score=None, status=None):
        self._ensure_team_seed(home)
        self._ensure_team_seed(away)

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO matches (fixture_id, date, league_id, season, home_team, away_team, home_score, away_score, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (fixture_id, date, league_id, season, home, away, home_score, away_score, status)
            )

    def insert_odds(self, fixture_id, bookmaker_id, bookmaker_name, home_odd, draw_odd, away_odd):
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO odds (fixture_id, bookmaker_id, bookmaker_name, home_odd, draw_odd, away_odd)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (fixture_id, bookmaker_id, bookmaker_name, home_odd, draw_odd, away_odd)
            )


db = Database(DB_PATH) 
