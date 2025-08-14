# src/models/database.py
from __future__ import annotations
import os
import sqlite3
from contextlib import contextmanager
from typing import Optional, Tuple

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

    # alias public (certains scripts l’utilisent)
    def get_connection(self):
        return self._get_connection()

    def _init_db(self):
        with self._get_connection() as conn:
            # Table principale des matches (historique + live)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS matches (
              id           INTEGER PRIMARY KEY AUTOINCREMENT,
              fixture_id   INTEGER UNIQUE,              -- id API-Football si connu
              date         TEXT,                        -- YYYY-MM-DD
              season       TEXT,                        -- ex: 2024-2025 (ou entier string)
              league_code  TEXT,                        -- 'E0','F1' ou nom de ligue API
              home_team    TEXT NOT NULL,
              away_team    TEXT NOT NULL,
              fthg         INTEGER,                     -- full-time home goals
              ftag         INTEGER,                     -- full-time away goals
              result       TEXT,                        -- 'H','D','A'
              btts_yes     REAL,
              btts_no      REAL,
              odds_home    REAL,
              odds_draw    REAL,
              odds_away    REAL,
              created_at   TEXT DEFAULT (datetime('now')),
              updated_at   TEXT DEFAULT (datetime('now'))
            )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_matches_teams ON matches(home_team, away_team)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_matches_league ON matches(league_code)")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uidx_matches_fixture ON matches(fixture_id)")

            # ELO par équipe
            conn.execute("""
            CREATE TABLE IF NOT EXISTS team_stats (
              team_id    TEXT PRIMARY KEY,              -- on stocke le nom normalisé comme id
              elo        REAL NOT NULL,
              updated_at TEXT DEFAULT (datetime('now'))
            )
            """)

            # Historique ELO par match (utilisé par build_elo_history.py)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS match_elo (
              id              INTEGER PRIMARY KEY AUTOINCREMENT,
              match_id        INTEGER,                  -- id sur 'matches' si utile
              home_team       TEXT,
              away_team       TEXT,
              date            TEXT,
              league_code     TEXT,
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

            # Table des prédictions (générées par generate_predictions.py)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
              id           INTEGER PRIMARY KEY AUTOINCREMENT,
              date         TEXT,                        -- date du match
              league_code  TEXT,
              home_team    TEXT,
              away_team    TEXT,
              method       TEXT,                        -- 'ELO' | 'B365' | 'PINNACLE' | 'COMBINED'
              market       TEXT,                        -- '1X2' | 'BTTS' | 'OU2.5' ...
              selection    TEXT,                        -- 'H','D','A' | 'Yes','No' | 'Over','Under'
              prob         REAL,                        -- probabilité modèle
              odd          REAL,                        -- cote retenue
              value        REAL,                        -- (prob*odd - 1)
              created_at   TEXT DEFAULT (datetime('now'))
            )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_predictions_date ON predictions(date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_predictions_method ON predictions(method)")

            # La table odds peut être créée via migration séparée ; on la crée ici aussi si besoin (idempotent).
            conn.execute("""
            CREATE TABLE IF NOT EXISTS odds (
              fixture_id     INTEGER NOT NULL,
              bookmaker_id   INTEGER,
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

    # ---------- Helpers ----------
    def _ensure_team_seed(self, team_name: Optional[str], seed_elo: float = 1500.0):
        """Crée l'équipe avec un ELO de base si inconnue."""
        if not team_name:
            return
        with self._get_connection() as conn:
            row = conn.execute("SELECT 1 FROM team_stats WHERE team_id = ?", (team_name,)).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO team_stats (team_id, elo, updated_at) VALUES (?, ?, datetime('now'))",
                    (team_name, seed_elo),
                )
                conn.commit()

    # ---------- Upserts ----------
    def insert_match(
        self,
        season: Optional[str],
        league_code: Optional[str],
        home: str,
        away: str,
        fthg: Optional[int] = None,
        ftag: Optional[int] = None,
        result: Optional[str] = None,
        btts_yes: Optional[float] = None,
        btts_no: Optional[float] = None,
        odds_home: Optional[float] = None,
        odds_draw: Optional[float] = None,
        odds_away: Optional[float] = None,
        date: Optional[str] = None,
        fixture_id: Optional[int] = None,
    ):
        """
        Upsert d'un match.
        - Si fixture_id est fourni → upsert par fixture_id (UNIQUE).
        - Sinon → upsert par (date, league_code, home_team, away_team).
        """
        # Seed ELO des équipes (si nouvelles)
        self._ensure_team_seed(home)
        self._ensure_team_seed(away)

        with self._get_connection() as conn:
            if fixture_id is not None:
                # Existe déjà ?
                row = conn.execute(
                    "SELECT id FROM matches WHERE fixture_id = ?",
                    (fixture_id,)
                ).fetchone()

                if row:
                    # UPDATE
                    conn.execute("""
                        UPDATE matches
                           SET date = COALESCE(?, date),
                               season = COALESCE(?, season),
                               league_code = COALESCE(?, league_code),
                               home_team = COALESCE(?, home_team),
                               away_team = COALESCE(?, away_team),
                               fthg = COALESCE(?, fthg),
                               ftag = COALESCE(?, ftag),
                               result = COALESCE(?, result),
                               btts_yes = COALESCE(?, btts_yes),
                               btts_no = COALESCE(?, btts_no),
                               odds_home = COALESCE(?, odds_home),
                               odds_draw = COALESCE(?, odds_draw),
                               odds_away = COALESCE(?, odds_away),
                               updated_at = datetime('now')
                         WHERE fixture_id = ?
                    """, (
                        date, season, league_code, home, away,
                        fthg, ftag, result,
                        btts_yes, btts_no,
                        odds_home, odds_draw, odds_away,
                        fixture_id
                    ))
                else:
                    # INSERT
                    conn.execute("""
                        INSERT INTO matches (
                            fixture_id, date, season, league_code,
                            home_team, away_team,
                            fthg, ftag, result,
                            btts_yes, btts_no,
                            odds_home, odds_draw, odds_away,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                    """, (
                        fixture_id, date, season, league_code,
                        home, away,
                        fthg, ftag, result,
                        btts_yes, btts_no,
                        odds_home, odds_draw, odds_away
                    ))
            else:
                # Fallback: upsert par clé naturelle
                row = conn.execute("""
                    SELECT id FROM matches
                     WHERE date = ? AND league_code = ? AND home_team = ? AND away_team = ?
                """, (date, league_code, home, away)).fetchone()

                if row:
                    conn.execute("""
                        UPDATE matches
                           SET fthg = COALESCE(?, fthg),
                               ftag = COALESCE(?, ftag),
                               result = COALESCE(?, result),
                               btts_yes = COALESCE(?, btts_yes),
                               btts_no = COALESCE(?, btts_no),
                               odds_home = COALESCE(?, odds_home),
                               odds_draw = COALESCE(?, odds_draw),
                               odds_away = COALESCE(?, odds_away),
                               updated_at = datetime('now')
                         WHERE id = ?
                    """, (
                        fthg, ftag, result,
                        btts_yes, btts_no,
                        odds_home, odds_draw, odds_away,
                        row["id"]
                    ))
                else:
                    conn.execute("""
                        INSERT INTO matches (
                            fixture_id, date, season, league_code,
                            home_team, away_team,
                            fthg, ftag, result,
                            btts_yes, btts_no,
                            odds_home, odds_draw, odds_away,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                    """, (
                        None, date, season, league_code,
                        home, away,
                        fthg, ftag, result,
                        btts_yes, btts_no,
                        odds_home, odds_draw, odds_away
                    ))
            conn.commit()

    def upsert_odds(
        self,
        fixture_id: int,
        bookmaker_id: Optional[int] = None,
        bookmaker_name: Optional[str] = None,
        home_odd: Optional[float] = None,
        draw_odd: Optional[float] = None,
        away_odd: Optional[float] = None,
        btts_yes: Optional[float] = None,
        btts_no: Optional[float] = None,
        ou_over25: Optional[float] = None,
        ou_under25: Optional[float] = None,
    ):
        """
        Upsert des cotes pour un fixture/bookmaker dans la table odds.
        Compatible avec la migration 'migrate_add_odds.py' (idempotent).
        """
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
                fixture_id, bookmaker_id, bookmaker_name,
                home_odd, draw_odd, away_odd,
                btts_yes, btts_no, ou_over25, ou_under25
            ))
            conn.commit()


# Instance globale
db = Database(DB_PATH) 
