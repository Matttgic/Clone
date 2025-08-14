import os
import sys
import argparse
import datetime as dt
import pandas as pd
from src.models.database import db

def export_day(conn, date_iso: str) -> int:
    """Exporte les prédictions d'une date (YYYY-MM-DD) en CSV+JSON. Retourne le nb de lignes."""
    q = "SELECT * FROM predictions WHERE substr(created_at,1,10)=?"
    df = pd.read_sql_query(q, conn, params=[date_iso])

    os.makedirs("predictions", exist_ok=True)

    if df.empty:
        print(f"[info] No predictions for {date_iso}")
        return 0

    csv_path = f"predictions/{date_iso}.csv"
    json_path = f"predictions/{date_iso}.json"
    df.to_csv(csv_path, index=False)
    df.to_json(json_path, orient="records", force_ascii=False, indent=2)
    print(f"[ok] Wrote {csv_path} and {json_path} ({len(df)} rows)")
    return len(df)

def main():
    parser = argparse.ArgumentParser(description="Export predictions to files")
    parser.add_argument("--days", type=int, default=1, help="Nombre de jours à exporter (depuis aujourd'hui, inclus).")
    args = parser.parse_args()

    today = dt.datetime.utcnow().date()
    total_files = 0
    total_rows = 0

    with db.get_connection() as conn:
        for i in range(args.days):
            d = (today - dt.timedelta(days=i)).isoformat()
            n = export_day(conn, d)
            if n > 0:
                total_files += 2  # csv + json
                total_rows += n

        # fallback: s'il n'y a absolument rien, on exporte la dernière série disponible
        if total_rows == 0:
            df = pd.read_sql_query("""
                SELECT * FROM predictions
                WHERE created_at = (SELECT MAX(created_at) FROM predictions)
            """, conn)
            if df.empty:
                # déposer un placeholder pour que le dossier existe
                os.makedirs("predictions", exist_ok=True)
                open("predictions/.gitkeep", "w").close()
                print("[warn] No predictions in DB. Wrote predictions/.gitkeep")
                return
            # utilise la date de la première ligne
            last_date = df["created_at"].iloc[0][:10]
            csv_path = f"predictions/{last_date}.csv"
            json_path = f"predictions/{last_date}.json"
            df.to_csv(csv_path, index=False)
            df.to_json(json_path, orient="records", force_ascii=False, indent=2)
            print(f"[ok] Fallback wrote {csv_path} and {json_path} ({len(df)} rows)")

if __name__ == "__main__":
    main()
