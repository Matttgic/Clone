# scripts/migrate_team_stats_text.py
"""
Migration pour s'assurer que team_stats.team_id est en format TEXT
pour éviter les erreurs "datatype mismatch"
"""
import os
import sqlite3
from src.models.database import DB_PATH

def migrate_team_stats():
    """Migre team_stats pour s'assurer que team_id est TEXT"""
    print("🔧 Migration: team_stats.team_id -> TEXT")
    
    if not os.path.exists(DB_PATH):
        print(f"⚠️ Database not found at {DB_PATH}, skipping migration")
        return
    
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            
            # Vérifier la structure actuelle
            cursor = conn.execute("PRAGMA table_info(team_stats)")
            columns = {row['name']: row['type'] for row in cursor.fetchall()}
            
            if 'team_id' not in columns:
                print("⚠️ team_stats.team_id column not found, skipping")
                return
            
            current_type = columns['team_id'].upper()
            print(f"📊 Current team_id type: {current_type}")
            
            if current_type == 'TEXT':
                print("✅ team_id is already TEXT, no migration needed")
                return
            
            print("🔄 Migrating team_id to TEXT...")
            
            # Sauvegarder les données existantes
            backup_data = conn.execute("SELECT * FROM team_stats").fetchall()
            print(f"💾 Backing up {len(backup_data)} records")
            
            # Recréer la table avec le bon type
            conn.execute("DROP TABLE IF EXISTS team_stats_backup")
            conn.execute("""
                CREATE TABLE team_stats_backup AS SELECT * FROM team_stats
            """)
            
            conn.execute("DROP TABLE team_stats")
            
            conn.execute("""
                CREATE TABLE team_stats (
                    team_id TEXT PRIMARY KEY,
                    elo REAL,
                    updated_at TEXT DEFAULT (datetime('now'))
                )
            """)
            
            # Restaurer les données en convertissant team_id en TEXT
            for row in backup_data:
                conn.execute("""
                    INSERT OR REPLACE INTO team_stats (team_id, elo, updated_at)
                    VALUES (?, ?, ?)
                """, (str(row['team_id']), row['elo'], row['updated_at']))
            
            conn.execute("DROP TABLE team_stats_backup")
            conn.commit()
            
            print(f"✅ Migration completed: {len(backup_data)} records restored")
            
            # Vérification finale
            cursor = conn.execute("PRAGMA table_info(team_stats)")
            new_columns = {row['name']: row['type'] for row in cursor.fetchall()}
            print(f"🎯 Final team_id type: {new_columns.get('team_id', 'UNKNOWN')}")
            
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    migrate_team_stats()
