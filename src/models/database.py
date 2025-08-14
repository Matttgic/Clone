# src/models/database.py
from __future__ import annotations
import os
import sqlite3
from contextlib import contextmanager
from typing import Optional, List, Tuple

DB_PATH = os.getenv("DB_PATH", "data/football.db")

class Database:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def get_connection(self):
        return self._get_connection()

    @staticmethod
    def _columns(conn: sqlite3.Connection, table: str) -> List[str]:
        return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]

    def _init_db(self):
        with self._get_connection() as conn:
            # 1) Crée la table matches minimale si absente (sans forcer de colonnes)
            conn.execute("CREATE TABLE IF NOT EXISTS matches (id INTEGER PRIMARY KEY AUTOINCREMENT)")
            cols = self._columns(conn, "matches")

            # 2) Créer les index **seulement si** les colonnes existent déjà
            if "date" in cols:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(date)")

            team_cols_pair: Optional[Tuple[str, str]] = None
            if "home_team" in cols and "away_team" in cols:
                team_cols_pair = ("home_team", "away_team")
            elif "home_team_id" in cols and "away_team_id" in cols:
                team_cols_pair = ("home_team_id", "away_team_id")

            if team_cols_pair:
                conn.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_matches_teams ON matches({team_cols_pair[0]}, {team_cols_pair[1]})"
                )

            # 3) Tables annexes (créées si absentes, on ne touche pas aux existantes)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS team_stats (
              team_id    TEXT PRIMARY KEY,
              elo        REAL,
              updated_at TEXT
            )
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS odds (
              fixture_id     TEXT,
              bookmaker_id   TEXT,
              bookmaker_name TEXT,
              home_odd       REAL,
              draw_odd       REAL,
              away_odd       REAL,
              btts_yes       REAL,
              btts_no        REAL,
              ou_over25      REAL,
              ou_under25     REAL,
              updated_at     TEXT,
              PRIMARY KEY (fixture_id, bookmaker_id)
            )
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
              id         INTEGER PRIMARY KEY AUTOINCREMENT,
              fixture_id TEXT,
              date       TEXT,
              league     TEXT,
              home_team  TEXT,
              away_team  TEXT,
              method     TEXT,
              market     TEXT,
              selection  TEXT,
              prob       REAL,
              odd        REAL,
              value      REAL,
              created_at TEXT
            )
            """)

            conn.commit()

    # ---------- helpers ----------
    def _ensure_team_seed(self, team_id: Optional[str], seed_elo: float = 1500.0):
        """Stocke toujours le team_id en TEXTE pour éviter datatype mismatch."""
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

    # ---------- upsert match sans changer ton schéma existant ----------
    def insert_match(
        self,
        date: Optional[str],
        home_team: str,
        away_team: str,
        home_score: Optional[int] = None,
        away_score: Optional[int] = None,
        status: Optional[str] = None,
        league: Optional[str] = None,
        season: Optional[str] = None,
        fixture_id: Optional[str] = None,
    ):
        """S'adapte au schéma réel de `matches` (utilise seulement les colonnes présentes)."""
        # Seed ELO avec les noms d'équipes
        self._ensure_team_seed(home_team)
        self._ensure_team_seed(away_team)

        with self._get_connection() as conn:
            cols = set(self._columns(conn, "matches"))

            # Prépare dict valeurs en respectant les colonnes existantes
            values = {}
            if "date" in cols:        values["date"] = date
            if "home_team" in cols:   values["home_team"] = str(home_team)
            if "home_team_id" in cols and "home_team" not in values:
                values["home_team_id"] = str(home_team)
            if "away_team" in cols:   values["away_team"] = str(away_team)
            if "away_team_id" in cols and "away_team" not in values:
                values["away_team_id"] = str(away_team)
            if "home_score" in cols:  values["home_score"] = home_score
            if "away_score" in cols:  values["away_score"] = away_score
            if "status" in cols:      values["status"] = status
            if "league" in cols:      values["league"] = league
            if "league_id" in cols and "league" not in values:
                values["league_id"] = league
            if "season" in cols:      values["season"] = season
            if "fixture_id" in cols and fixture_id:
                values["fixture_id"] = str(fixture_id).strip()

            # Upsert par fixture_id si possible, sinon insert simple
            if "fixture_id" in values:
                row = conn.execute("SELECT id FROM matches WHERE fixture_id=?", (values["fixture_id"],)).fetchone()
                if row:
                    set_clause = ", ".join([f"{k}=COALESCE(?, {k})" for k in values if k != "fixture_id"])
                    params = [values[k] for k in values if k != "fixture_id"] + [values["fixture_id"]]
                    conn.execute(f"UPDATE matches SET {set_clause} WHERE fixture_id = ?", params)
                else:
                    cols_sql = ", ".join(values.keys())
                    qmarks  = ", ".join(["?"] * len(values))
                    conn.execute(f"INSERT INTO matches ({cols_sql}) VALUES ({qmarks})", list(values.values()))
            else:
                # Pas de fixture_id disponible dans le schéma → insert best-effort
                if not values:
                    return
                cols_sql = ", ".join(values.keys())
                qmarks  = ", ".join(["?"] * len(values))
                conn.execute(f"INSERT INTO matches ({cols_sql}) VALUES ({qmarks})", list(values.values()))

            conn.commit()


# instance globale
db = Database(DB_PATH)
