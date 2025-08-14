# src/models/database.py
from __future__ import annotations
import os
import sqlite3
from contextlib import contextmanager
from typing import Optional, Dict

DB_PATH = os.getenv("DB_PATH", "data/football.db")


class Database:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._init_db()

    # ---------- Connections ----------
    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # alias public (utilisé par d’autres scripts)
    def get_connection(self):
        return self._get_connection()

    # ---------- Init & migrations légères ----------
    def _init_db(self):
        with self._get_connection() as conn:
            # Étape 1 : garantir l’existence de la table (même vide)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS matches (
              id INTEGER PRIMARY KEY AUTOINCREMENT
            )
            """)

            # Étape 2 : ajouter les colonnes manquantes AVANT de créer les index
            self._ensure_columns(conn, "matches", {
                "fixture_id": "TEXT",   # ID API-Football (unique si présent)
                "date": "TEXT",         # ex: 2025-08-14T19:00:00Z
                "league": "TEXT",       # nom/code de ligue
                "season": "TEXT",       # ex: 2024 ou 2024-2025 (string)
                "home_team": "TEXT",
                "away_team": "TEXT",
                "home_score": "INTEGER",
                "away_score": "INTEGER",
                "result": "TEXT",       # 'H','D','A'
                "status": "TEXT",       # 'NS','FT', ...
                "created_at": "TEXT",
                "updated_at": "TEXT"
            })

            # Étape 3 : index (maintenant que les colonnes existent)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_matches_date   ON matches(date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_matches_teams  ON matches(home_team, away_team)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_matches_league ON matches(league)")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_matches_fixture ON matches(fixture_id)")

            # Table ELO par équipe
            conn.execute("""
            CREATE TABLE IF NOT EXISTS team_stats (
              team_id    TEXT PRIMARY KEY,
              elo        REAL NOT NULL,
              updated_at TEXT DEFAULT (datetime('now'))
            )
            """)

            # Historique ELO par match (si utilisé)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS match_elo (
              id              INTEGER PRIMARY KEY AUTOINCREMENT,
              match_id        INTEGER,
              home_team       TEXT,
              away_team       TEXT,
              date            TEXT,
              league          TEXT,
              home_pre_elo    REAL,
              away_pre_elo    REAL,
              home_post_elo   REAL,
              away_post_elo   REAL,
              home_win_prob   REAL,
              draw_prob       REAL,
              away_win_prob   REAL
            )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_match_elo_date ON match_elo(date)")

            # Table prédictions
            conn.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
              id           INTEGER PRIMARY KEY AUTOINCREMENT,
              date         TEXT,
              league       TEXT,
              home_team    TEXT,
              away_team    TEXT,
              method       TEXT,   -- 'ELO' | 'B365' | 'PINNACLE' | 'COMBINED'
              market       TEXT,   -- '1X2' | 'BTTS' | 'OU2.5' ...
              selection    TEXT,   -- 'H','D','A' | 'Yes','No' | 'Over','Under'
              prob         REAL,
              odd          REAL,
              value        REAL,
              created_at   TEXT DEFAULT (datetime('now'))
            )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_predictions_date   ON predictions(date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_predictions_method ON predictions(method)")

            # Table des cotes (upsert par fixture+bookmaker)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS odds (
              fixture_id     TEXT NOT NULL,
              bookmaker_id   TEXT,
              bookmaker_name TEXT,
              home_odd       REAL,
              draw_odd       REAL,
              away_odd       REAL,
              btts_yes       REAL,
              btts_no        REAL,
              ou_over25      REAL,
              ou_under25     REAL,
              updated_at     TEXT DEFAULT (datetime('now')),
              PRIMARY KEY (fixture_id, bookmaker_id)
            )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_odds_fixture ON odds(fixture_id)")

            conn.commit()

    def _ensure_columns(self, conn: sqlite3.Connection, table: str, wanted: Dict[str, str]):
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        added = False
        for col, typ in wanted.items():
            if col not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
                added = True
        if added:
            conn.commit()

    # ---------- Helpers ----------
    def _ensure_team_seed(self, team_id: Optional[str], seed_elo: float = 1500.0):
        """Crée l'équipe avec un ELO de base si inconnue."""
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

    @staticmethod
    def _derive_result(home_score: Optional[int], away_score: Optional[int]) -> Optional[str]:
        if home_score is None or away_score is None:
            return None
        if home_score > away_score:
            return "H"
        if home_score < away_score:
            return "A"
        return "D"

    # ---------- Upserts ----------
    def insert_match(
        self,
        fixture_id: Optional[str],
        date: Optional[str],
        league: Optional[str],
        season: Optional[str],
        home_team: str,
        away_team: str,
        home_score: Optional[int] = None,
        away_score: Optional[int] = None,
        status: Optional[str] = None,
        result: Optional[str] = None,
    ):
        """Upsert par fixture_id (unique) si fourni, sinon par clé naturelle (date+league+teams)."""
        # Seed ELO des équipes
        self._ensure_team_seed(home_team)
        self._ensure_team_seed(away_team)

        # Déduire résultat si non fourni
        if result is None:
            result = self._derive_result(home_score, away_score)

        # Normalisation légère
        f_id = None if fixture_id is None else str(fixture_id).strip()

        with self._get_connection() as conn:
            if f_id:
                row = conn.execute(
                    "SELECT id FROM matches WHERE fixture_id = ?",
                    (f_id,),
                ).fetchone()

                if row:
                    conn.execute("""
                        UPDATE matches
                           SET date = COALESCE(?, date),
                               league = COALESCE(?, league),
                               season = COALESCE(?, season),
                               home_team = COALESCE(?, home_team),
                               away_team = COALESCE(?, away_team),
                               home_score = COALESCE(?, home_score),
                               away_score = COALESCE(?, away_score),
                               result = COALESCE(?, result),
                               status = COALESCE(?, status),
                               updated_at = datetime('now')
                         WHERE fixture_id = ?
                    """, (
                        date, league, season,
                        home_team, away_team,
                        home_score, away_score,
                        result, status,
                        f_id
                    ))
                else:
                    conn.execute("""
                        INSERT INTO matches (
                          fixture_id, date, league, season,
                          home_team, away_team,
                          home_score, away_score, result, status,
                          created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                    """, (
                        f_id, date, league, season,
                        home_team, away_team,
                        home_score, away_score, result, status
                    ))
            else:
                # Fallback si pas de fixture_id : clé naturelle
                row = conn.execute("""
                    SELECT id FROM matches
                     WHERE date = ? AND league = ? AND home_team = ? AND away_team = ?
                """, (date, league, home_team, away_team)).fetchone()

                if row:
                    conn.execute("""
                        UPDATE matches
                           SET home_score = COALESCE(?, home_score),
                               away_score = COALESCE(?, away_score),
                               result = COALESCE(?, result),
                               status = COALESCE(?, status),
                               updated_at = datetime('now')
                         WHERE id = ?
                    """, (
                        home_score, away_score, result, status, row["id"]
                    ))
                else:
                    conn.execute("""
                        INSERT INTO matches (
                          fixture_id, date, league, season,
                          home_team, away_team,
                          home_score, away_score, result, status,
                          created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                    """, (
                        None, date, league, season,
                        home_team, away_team,
                        home_score, away_score, result, status
                    ))

            conn.commit()

    def upsert_odds(
        self,
        fixture_id: str,
        bookmaker_id: Optional[str] = None,
        bookmaker_name: Optional[str] = None,
        home_odd: Optional[float] = None,
        draw_odd: Optional[float] = None,
        away_odd: Optional[float] = None,
        btts_yes: Optional[float] = None,
        btts_no: Optional[float] = None,
        ou_over25: Optional[float] = None,
        ou_under25: Optional[float] = None,
    ):
        """Upsert des cotes pour un fixture/bookmaker."""
        with self._get_connection() as conn:
            conn.execute("""
            INSERT INTO odds (
                fixture_id, bookmaker_id, bookmaker_name,
                home_odd, draw_odd, away_odd,
                btts_yes, btts_no, ou_over25, ou_under25, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(fixture_id, bookmaker_id) DO UPDATE SET
                bookmaker_name=excluded.bookmaker_name,
                home_odd=excluded.home_odd,
                draw_odd=excluded.draw_odd,
                away_odd=excluded.away_odd,
                btts_yes=excluded.btts_yes,
                btts_no=excluded.btts_no,
                ou_over25=excluded.ou_over25,
                ou_under25=excluded.ou_under25,
                updated_at=excluded.updated_at
            """, (
                str(fixture_id).strip(),
                None if bookmaker_id is None else str(bookmaker_id).strip(),
                bookmaker_name,
                home_odd, draw_odd, away_odd,
                btts_yes, btts_no, ou_over25, ou_under25
            ))
            conn.commit()


# Instance globale
db = Database(DB_PATH)
