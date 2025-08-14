import sqlite3
from typing import Optional

DB_PATH = "data/football.db"

class Database:
    def __init__(self, path: str):
        self.path = path
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.path)

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS team_stats (
                    team_id TEXT PRIMARY KEY,
                    elo REAL DEFAULT 1500,
                    updated_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS matches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT,
                    home_team TEXT,
                    away_team TEXT,
                    home_score INTEGER,
                    away_score INTEGER,
                    status TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_matches_teams ON matches(home_team, away_team)")
            conn.commit()

    def _ensure_team_seed(self, team_id: Optional[str], seed_elo: float = 1500.0):
        """Ajoute l'équipe avec un ELO initial si absente."""
        if team_id is None:
            return
        team_id = str(team_id).strip()  # 🔹 conversion forcée en string
        if not team_id:
            return
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO team_stats (team_id, elo, updated_at) VALUES (?, ?, datetime('now'))",
                (team_id, seed_elo),
            )
            conn.commit()

    def insert_match(self, date, home_team, away_team, home_score=None, away_score=None, status=None):
        """Insère un match en s'assurant que les équipes existent."""
        self._ensure_team_seed(home_team)
        self._ensure_team_seed(away_team)
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO matches (date, home_team, away_team, home_score, away_score, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (date, str(home_team), str(away_team), home_score, away_score, status))
            conn.commit()

# Instance globale
db = Database(DB_PATH) 
