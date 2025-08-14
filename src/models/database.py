# src/models/database.py
from __future__ import annotations
import os
import sqlite3
from contextlib import contextmanager
from typing import Optional, Dict, List, Tuple

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

    # ---------- utils ----------
    @staticmethod
    def _columns(conn: sqlite3.Connection, table: str) -> List[str]:
        return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]

    # ---------- init ----------
    def _init_db(self):
        with self._get_connection() as conn:
            # 1) Assurer l'existence de la table matches (minimale, pas de migration)
            conn.execute("CREATE TABLE IF NOT EXISTS matches (id INTEGER PRIMARY KEY AUTOINCREMENT)")
            cols = self._columns(conn, "matches")

            # 2) Créer les index SANS supposer les colonnes : choisir celles qui existent
            # Index par date si la colonne existe déjà
            if "date" in cols:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(date)")

            # Index sur équipes : home_team/away_team OU home_team_id/away_team_id
            team_cols_pair: Optional[Tuple[str, str]] = None
            if "home_team" in cols and "away_team" in cols:
                team_cols_pair = ("home_team", "away_team")
            elif "home_team_id" in cols and "away_team_id" in cols:
                team_cols_pair = ("home_team_id", "away_team_id")

            if team_cols_pair:
                conn.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_matches_teams ON matches({team_cols_pair[0]}, {team_cols_pair[1]})"
                )

            # 3) Autres tables nécessaires (créées si absentes, sans toucher à matches)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS team_stats (
              team_id    TEXT PRIMARY KEY,
              elo        REAL NOT NULL,
              updated_at TEXT DEFAULT (datetime('now'))
            )
            """)

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

            conn.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
              id           INTEGER PRIMARY KEY AUTOINCREMENT,
              date         TEXT,
              league       TEXT,
              home_team    TEXT,
              away_team    TEXT,
              method       TEXT,
              market       TEXT,
              selection    TEXT,
              prob         REAL,
              odd          REAL,
              value        REAL,
              created_at   TEXT DEFAULT (datetime('now'))
            )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_predictions_date   ON predictions(date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_predictions_method ON predictions(method)")

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

    # ---------- helpers ----------
    def _ensure_team_seed(self, team_id: Optional[str], seed_elo: float = 1500.0):
        """Crée l'équipe avec un ELO de base si inconnue (team_id stocké en TEXTE)."""
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

    # ---------- upserts ----------
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
        result: Optional[str] = None,
    ):
        """
        Insert/Update un match *en s'adaptant au schéma actuel* de la table `matches`.
        On n'ajoute aucune colonne; on n'utilise que celles déjà présentes.
        Priorité d'upsert : fixture_id si présent et colonne dispo ; sinon (date+home+away) si colonnes dispo.
        """
        # Seed ELO (utilise les noms passés par fetch_today.py)
        self._ensure_team_seed(home_team)
        self._ensure_team_seed(away_team)

        with self._get_connection() as conn:
            cols = set(self._columns(conn, "matches"))

            # Construire un dictionnaire des valeurs compatibles avec les colonnes existantes
            values: Dict[str, Optional[object]] = {}

            # mapping flexible pour les équipes
            if "home_team" in cols:
                values["home_team"] = str(home_team)
            elif "home_team_id" in cols:
                values["home_team_id"] = str(home_team)

            if "away_team" in cols:
                values["away_team"] = str(away_team)
            elif "away_team_id" in cols:
                values["away_team_id"] = str(away_team)

            # autres champs si dispo
            if "date" in cols:       values["date"] = date
            if "league" in cols:     values["league"] = league
            if "season" in cols:     values["season"] = season
            if "home_score" in cols: values["home_score"] = home_score
            if "away_score" in cols: values["away_score"] = away_score
            if "status" in cols:     values["status"] = status
            if "result" in cols:
                values["result"] = result if result is not None else self._derive_result(home_score, away_score)
            if "fixture_id" in cols and fixture_id is not None:
                values["fixture_id"] = str(fixture_id).strip()

            # Déterminer la clé d'upsert
            use_fixture_key = ("fixture_id" in cols) and ("fixture_id" in values) and bool(values["fixture_id"])

            # fallback clé naturelle : nécessite date + équipes dans les colonnes présentes
            have_home = ("home_team" in values) or ("home_team_id" in values)
            have_away = ("away_team" in values) or ("away_team_id" in values)
            use_natural_key = ("date" in values) and have_home and have_away

            if use_fixture_key:
                row = conn.execute("SELECT id FROM matches WHERE fixture_id = ?", (values["fixture_id"],)).fetchone()
                if row:
                    # UPDATE
                    set_clause = ", ".join([f"{k} = COALESCE(?, {k})" for k in values.keys() if k != "fixture_id"])
                    params = [values[k] for k in values.keys() if k != "fixture_id"]
                    sql = f"UPDATE matches SET {set_clause} WHERE fixture_id = ?"
                    params.append(values["fixture_id"])
                    conn.execute(sql, params)
                else:
                    # INSERT
                    cols_sql = ", ".join(list(values.keys()))
                    qmarks = ", ".join(["?"] * len(values))
                    sql = f"INSERT INTO matches ({cols_sql}) VALUES ({qmarks})"
                    conn.execute(sql, list(values.values()))
            elif use_natural_key:
                # Construire WHERE selon colonnes présentes
                where_parts = ["date = ?"]
                where_vals: List[object] = [values["date"]]
                if "home_team" in values:
                    where_parts.append("home_team = ?")
                    where_vals.append(values["home_team"])
                else:
                    where_parts.append("home_team_id = ?")
                    where_vals.append(values["home_team_id"])
                if "away_team" in values:
                    where_parts.append("away_team = ?")
                    where_vals.append(values["away_team"])
                else:
                    where_parts.append("away_team_id = ?")
                    where_vals.append(values["away_team_id"])

                row = conn.execute(f"SELECT id FROM matches WHERE {' AND '.join(where_parts)}", where_vals).fetchone()
                if row:
                    # UPDATE partiel (pas de WHERE sur id, on réutilise la clé naturelle)
                    set_cols = [k for k in values.keys() if k not in ("date", "home_team", "home_team_id", "away_team", "away_team_id")]
                    if set_cols:
                        set_clause = ", ".join([f"{k} = COALESCE(?, {k})" for k in set_cols])
                        params = [values[k] for k in set_cols] + where_vals
                        conn.execute(f"UPDATE matches SET {set_clause} WHERE {' AND '.join(where_parts)}", params)
                else:
                    # INSERT
                    cols_sql = ", ".join(list(values.keys()))
                    qmarks = ", ".join(["?"] * len(values))
                    sql = f"INSERT INTO matches ({cols_sql}) VALUES ({qmarks})"
                    conn.execute(sql, list(values.values()))
            else:
                # Si ni fixture_id utilisable ni clé naturelle complète, on insère ce qu'on peut
                cols_sql = ", ".join(list(values.keys()))
                if not cols_sql:
                    # Rien d'insérable -> on ignore proprement
                    return
                qmarks = ", ".join(["?"] * len(values))
                sql = f"INSERT INTO matches ({cols_sql}) VALUES ({qmarks})"
                conn.execute(sql, list(values.values()))

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
