import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path("data/football.db")


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._get_connection() as conn:
            # matches table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS matches (
                    match_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fixture_id TEXT UNIQUE,
                    date TEXT,
                    home_team TEXT,
                    away_team TEXT,
                    home_score INTEGER,
                    away_score INTEGER,
                    league_id TEXT,
                    status TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_matches_teams ON matches(home_team, away_team)")

            # team_stats table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS team_stats (
                    team_id TEXT PRIMARY KEY,
                    elo REAL,
                    updated_at TEXT
                )
            """)

            # odds table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS odds (
                    fixture_id TEXT,
                    bookmaker_id TEXT,
                    bookmaker_name TEXT,
                    home_odd REAL,
                    draw_odd REAL,
                    away_odd REAL,
                    PRIMARY KEY (fixture_id, bookmaker_id)
                )
            """)

            # predictions table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS predictions (
                    fixture_id TEXT PRIMARY KEY,
                    home_prob REAL,
                    draw_prob REAL,
                    away_prob REAL,
                    method TEXT,
                    created_at TEXT
                )
            """)

            conn.commit()

    def _ensure_team_seed(self, team_id: Optional[str], seed_elo: float = 1500.0):
        """Ajoute l'équipe avec un ELO de base si absente, stockée comme texte."""
        if team_id is None:
            return
        team_id = str(team_id).strip()
        if not team_id:
            return
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO team_stats (team_id, elo, updated_at) VALUES (?, ?, datetime('now'))",
                (team_id, seed_elo),
            )
            conn.commit()

    def insert_match(
        self,
        fixture_id: str,
        date: str,
        home_team: str,
        away_team: str,
        home_score: Optional[int] = None,
        away_score: Optional[int] = None,
        league_id: Optional[str] = None,
        status: Optional[str] = None
    ):
        """Insère un match et seed les équipes si nécessaire."""
        self._ensure_team_seed(home_team)
        self._ensure_team_seed(away_team)
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO matches (
                    fixture_id, date, home_team, away_team,
                    home_score, away_score, league_id, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(fixture_id), date, str(home_team), str(away_team),
                home_score, away_score, str(league_id) if league_id else None, status
            ))
            conn.commit()


# Instance globale
db = Database(DB_PATH) 
