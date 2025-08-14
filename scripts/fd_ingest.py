import os
import re
import json
import pandas as pd
from urllib.request import urlopen
from io import StringIO
from src.models.database import db

# -----------------------------------------------------------------
# Fonctions utilitaires
# -----------------------------------------------------------------
def find_col(df, patterns):
    """
    Recherche la première colonne du DataFrame correspondant à un des patterns.
    patterns peut contenir des strings ou des regex compilées.
    Retourne le nom de colonne ou None si rien trouvé.
    """
    for patt in patterns:
        for c in df.columns:
            if isinstance(patt, re.Pattern):
                if patt.search(c):
                    print(f"[DEBUG] Colonne trouvée: {c} pour pattern {patt.pattern}")
                    return c
            else:
                if re.search(patt, c, flags=re.I):
                    print(f"[DEBUG] Colonne trouvée: {c} pour pattern {patt}")
                    return c
    print(f"[WARN] Aucune colonne trouvée pour patterns: {patterns}")
    return None


def download_csv(url):
    """Télécharge un CSV et retourne un DataFrame pandas"""
    print(f"▶ Téléchargement: {url}")
    resp = urlopen(url)
    csv_data = resp.read().decode("utf-8", errors="replace")
    return pd.read_csv(StringIO(csv_data))


# -----------------------------------------------------------------
# Parsing format Europe
# -----------------------------------------------------------------
def parse_format_europe(df, code, season):
    """
    Parse les CSVs Europe (format mmz4281) et insère en base.
    """
    c_home = find_col(df, ["HomeTeam", "Home", "Team1"])
    c_away = find_col(df, ["AwayTeam", "Away", "Team2"])
    c_fthg = find_col(df, ["FTHG", "HG", "HomeGoals"])
    c_ftag = find_col(df, ["FTAG", "AG", "AwayGoals"])
    c_res = find_col(df, ["FTR", "Res", "Result"])

    c_b365_by = find_col(df, ["B365>BTTS Yes", "B365BTTSY", re.compile(r"B365.*BTTS.*Yes", re.I)])
    c_b365_bn = find_col(df, ["B365>BTTS No", "B365BTTSN", re.compile(r"B365.*BTTS.*No", re.I)])

    count = 0
    for _, row in df.iterrows():
        db.insert_match(
            season=season,
            league_code=code,
            home=row[c_home] if c_home else None,
            away=row[c_away] if c_away else None,
            fthg=row[c_fthg] if c_fthg else None,
            ftag=row[c_ftag] if c_ftag else None,
            result=row[c_res] if c_res else None,
            btts_yes=row[c_b365_by] if c_b365_by else None,
            btts_no=row[c_b365_bn] if c_b365_bn else None
        )
        count += 1

    print(f"✓ {count} matchs insérés pour {code} {season}")
    return count


# -----------------------------------------------------------------
# Parsing format Worldwide
# -----------------------------------------------------------------
def parse_format_worldwide(df, code, season):
    """
    Parse les CSV type Country,League,Season,Date,Time,Home,Away,HG,AG,Res,...
    """
    c_home = find_col(df, ["Home", "HomeTeam", "Team1"])
    c_away = find_col(df, ["Away", "AwayTeam", "Team2"])
    c_fthg = find_col(df, ["HG", "HomeGoals", "FTHG"])
    c_ftag = find_col(df, ["AG", "AwayGoals", "FTAG"])
    c_res = find_col(df, ["Res", "Result", "FTR"])

    # Bookmaker columns
    c_psch = find_col(df, ["PSCH", re.compile(r"^PSCH$", re.I)])
    c_pscd = find_col(df, ["PSCD", re.compile(r"^PSCD$", re.I)])
    c_psca = find_col(df, ["PSCA", re.compile(r"^PSCA$", re.I)])

    count = 0
    for _, row in df.iterrows():
        db.insert_match(
            season=season,
            league_code=code,
            home=row[c_home] if c_home else None,
            away=row[c_away] if c_away else None,
            fthg=row[c_fthg] if c_fthg else None,
            ftag=row[c_ftag] if c_ftag else None,
            result=row[c_res] if c_res else None,
            odds_home=row[c_psch] if c_psch else None,
            odds_draw=row[c_pscd] if c_pscd else None,
            odds_away=row[c_psca] if c_psca else None
        )
        count += 1

    print(f"✓ {count} matchs insérés pour {code} {season} (Worldwide)")
    return count


# -----------------------------------------------------------------
# Main
# -----------------------------------------------------------------
def main():
    cfg_path = os.path.join("config", "fd_sources.json")
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f) or {}

    total = 0
    for src in cfg.get("sources", []):
        code = src["league_code"]
        season = src["season"]
        url = src["url"]

        try:
            df = download_csv(url)

            # Détection du format
            if "Div" in df.columns and "FTHG" in df.columns:
                fmt = "EU"
            elif "Country" in df.columns and "HG" in df.columns:
                fmt = "WW"
            else:
                fmt = "UNKNOWN"

            print(f"  ↳ Format détecté: {fmt}")

            if fmt == "EU":
                n = parse_format_europe(df, code, season)
                total += n
            elif fmt == "WW":
                n = parse_format_worldwide(df, code, season)
                total += n
            else:
                print(f"[WARN] Format inconnu pour {code}, ignoré.")

        except Exception as e:
            print(f"[ERROR] Échec ingestion {code} {season}: {e}")

    print(f"=== Ingestion terminée: {total} matchs insérés ===")


if __name__ == "__main__":
    main() 
