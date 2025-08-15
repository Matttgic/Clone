#!/usr/bin/env python3
"""
Vérification système pour Football Predictions
"""
import os
import sys
import sqlite3
from datetime import datetime
from pathlib import Path

def check_environment():
    """Vérification de l'environnement"""
    print("🔍 Vérification de l'environnement...")
    
    # Python version
    python_version = sys.version_info
    print(f"   Python: {python_version.major}.{python_version.minor}.{python_version.micro}")
    
    if python_version < (3, 8):
        print("   ❌ Python 3.8+ requis")
        return False
    
    # RAPIDAPI_KEY
    api_key = os.getenv("RAPIDAPI_KEY")
    if not api_key:
        print("   ⚠️  RAPIDAPI_KEY non définie (optionnelle pour tests)")
    else:
        print(f"   ✅ RAPIDAPI_KEY définie ({api_key[:8]}...)")
    
    return True

def check_database():
    """Vérification de la base de données"""
    print("\n💾 Vérification de la base de données...")
    
    db_path = Path("data/football.db")
    
    if not db_path.exists():
        print("   ⚠️  Base de données absente, sera créée au premier usage")
        return True
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Vérifier les tables principales
        tables_required = ['matches', 'teams', 'odds', 'predictions', 'team_stats', 'match_elo']
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = {row[0] for row in cursor.fetchall()}
        
        for table in tables_required:
            if table in existing_tables:
                count = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                print(f"   ✅ Table '{table}': {count:,} lignes")
            else:
                print(f"   ⚠️  Table '{table}' absente")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"   ❌ Erreur base de données: {e}")
        return False

def check_config():
    """Vérification de la configuration"""
    print("\n⚙️  Vérification de la configuration...")
    
    config_files = [
        "config/settings.py",
        "config/leagues.py"
    ]
    
    for config_file in config_files:
        if Path(config_file).exists():
            print(f"   ✅ {config_file}")
        else:
            print(f"   ❌ {config_file} manquant")
    
    return True

def check_scripts():
    """Vérification des scripts"""
    print("\n📜 Vérification des scripts...")
    
    required_scripts = [
        "scripts/backfill_history.py",
        "scripts/build_elo_history.py", 
        "scripts/fetch_today.py",
        "scripts/generate_predictions.py",
        "scripts/export_predictions.py"
    ]
    
    all_good = True
    for script in required_scripts:
        if Path(script).exists():
            print(f"   ✅ {script}")
        else:
            print(f"   ❌ {script} manquant")
            all_good = False
    
    return all_good

def test_imports():
    """Test des imports principaux"""
    print("\n📦 Test des imports...")
    
    try:
        from src.models.database import db
        print("   ✅ src.models.database")
        
        from src.services.elo_system import elo_system  
        print("   ✅ src.services.elo_system")
        
        from config.settings import Settings
        print("   ✅ config.settings")
        
        return True
        
    except ImportError as e:
        print(f"   ❌ Erreur import: {e}")
        return False

def main():
    """Fonction principale"""
    print("🎯 Football Predictions - Vérification Système")
    print("=" * 50)
    
    checks = [
        check_environment,
        check_database,
        check_config,
        check_scripts,
        test_imports
    ]
    
    all_passed = True
    for check in checks:
        if not check():
            all_passed = False
    
    print("\n" + "=" * 50)
    if all_passed:
        print("🎉 Système prêt ! Vous pouvez lancer les scripts.")
        print("\n💡 Commandes utiles:")
        print("   python scripts/fetch_today.py")
        print("   python scripts/generate_predictions.py")
        print("   python scripts/export_predictions.py --days 1")
    else:
        print("⚠️  Quelques problèmes détectés, mais le système peut fonctionner.")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    exit(main())
