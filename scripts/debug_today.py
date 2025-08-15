# scripts/debug_today.py
"""
Script de debug pour tester l'API Football et diagnostiquer les problèmes
"""
import os
import requests
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

# Configuration
API_HOST = "api-football-v1.p.rapidapi.com"
BASE_URL = f"https://{API_HOST}/v3"
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "").strip()

def test_api_connection() -> bool:
    """Test basic API connectivity"""
    print("🔍 Testing API Connection...")
    
    if not RAPIDAPI_KEY:
        print("❌ RAPIDAPI_KEY not found in environment")
        return False
    
    print(f"🔑 API Key: {RAPIDAPI_KEY[:10]}...{RAPIDAPI_KEY[-4:]} (length: {len(RAPIDAPI_KEY)})")
    
    headers = {
        "x-rapidapi-host": API_HOST,
        "x-rapidapi-key": RAPIDAPI_KEY,
    }
    
    # Test endpoint timezone (simple endpoint)
    try:
        print("📡 Testing /timezone endpoint...")
        response = requests.get(f"{BASE_URL}/timezone", headers=headers, timeout=30)
        
        print(f"📊 Response: HTTP {response.status_code}")
        print(f"📦 Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ API Connection OK")
            print(f"📋 Sample data: {data.get('response', [])[:2]}")
            return True
        else:
            print(f"❌ API Error: {response.text}")
            return False
            
    except Exception as e:
        print(f"💥 Connection failed: {e}")
        return False

def test_fixtures_endpoint() -> Dict[str, Any]:
    """Test fixtures endpoint with different parameters"""
    print("\n🧪 Testing Fixtures Endpoints...")
    
    headers = {
        "x-rapidapi-host": API_HOST,
        "x-rapidapi-key": RAPIDAPI_KEY,
    }
    
    results = {}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    
    test_cases = [
        {"name": "Yesterday", "params": {"date": yesterday}},
        {"name": "Today", "params": {"date": today}},
        {"name": "Tomorrow", "params": {"date": tomorrow
