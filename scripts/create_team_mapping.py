# scripts/create_team_mapping.py
import requests
import pandas as pd
import json
from difflib import SequenceMatcher
from config.settings import Settings
from config.league_mapping import LEAGUE_CODE_TO_API_ID

class TeamMapper:
    def __init__(self):
        self.settings = Settings()
        self.team_mapping = {}
    
    def get_api_teams(self, league_id, season=2024):
        """Récupère les équipes via l'API Football"""
        url = f"{self.settings.API.BASE_URL}/standings"
        params = {
            "league": league_id,
            "season": season
        }
        
        response = requests.get(url, headers=self.settings.API.headers, params=params)
        
        if response.status_code == 200:
            data = response.json()
            teams = []
            if data.get("response"):
                for standing in data["response"][0]["league"]["standings"][0]:
                    teams.append({
                        "name": standing["team"]["name"],
                        "id": standing["team"]["id"]
                    })
            return teams
        return []
    
    def get_fd_teams(self, csv_url):
        """Récupère les équipes depuis Football Data UK"""
        try:
            df = pd.read_csv(csv_url)
            teams = set()
            if 'HomeTeam' in df.columns and 'AwayTeam' in df.columns:
                teams.update(df['HomeTeam'].unique())
                teams.update(df['AwayTeam'].unique())
            return list(teams)
        except Exception as e:
            print(f"Erreur lors du téléchargement de {csv_url}: {e}")
            return []
    
    def similarity(self, a, b):
        """Calcule la similarité entre deux chaînes"""
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()
    
    def normalize_name(self, name):
        """Normalise le nom d'une équipe pour améliorer le matching"""
        # Remplacements pour normaliser les noms
        replacements = {
            # Préfixes/suffixes courants
            "FC ": "", " FC": "", "CF ": "", " CF": "",
            "AC ": "", " AC": "", "SC ": "", " SC": "",
            "AS ": "", " AS": "", "CD ": "", " CD": "",
            "SK ": "", " SK": "", "FK ": "", " FK": "",
            "1. ": "", "2. ": "",
            
            # Cas spéciaux
            "Real ": "", "Club ": "",
            "Atletico ": "Atletico ",
            "Saint ": "St ", "Saint-": "St-",
        }
        
        normalized = name
        for old, new in replacements.items():
            normalized = normalized.replace(old, new)
        
        return normalized.strip()
    
    def match_teams(self, fd_teams, api_teams):
        """Fait correspondre les équipes FD avec l'API"""
        mapping = {}
        
        for fd_team in fd_teams:
            best_match = None
            best_score = 0
            
            fd_normalized = self.normalize_name(fd_team)
            
            for api_team in api_teams:
                api_normalized = self.normalize_name(api_team["name"])
                
                # Match exact
                if fd_normalized.lower() == api_normalized.lower():
                    mapping[fd_team] = api_team["name"]
                    break
                
                # Match par similarité
                score = self.similarity(fd_normalized, api_normalized)
                if score > best_score and score > 0.75:  # Seuil de 75%
                    best_score = score
                    best_match = api_team["name"]
            
            # Si pas de match exact, utiliser le meilleur match
            if fd_team not in mapping and best_match:
                mapping[fd_team] = best_match
        
        return mapping
    
    def create_full_mapping(self):
        """Crée le dictionnaire complet de correspondance"""
        with open('config/fd_sources.json', 'r') as f:
            sources = json.load(f)["sources"]
        
        total_processed = 0
        total_mapped = 0
        
        for source in sources:
            league_code = source["league_code"]
            
            # Ignorer les ligues non mappées
            if league_code not in LEAGUE_CODE_TO_API_ID:
                print(f"⏭️  Ignoré {league_code} (ID non défini)")
                continue
            
            league_id = LEAGUE_CODE_TO_API_ID[league_code]
            if league_id is None:
                print(f"⏭️  Ignoré {league_code} (ID = None)")
                continue
            
            print(f"🔄 Traitement de {league_code} (ID: {league_id})...")
            
            # Récupérer les équipes
            api_teams = self.get_api_teams(league_id)
            fd_teams = self.get_fd_teams(source["url"])
            
            if not api_teams:
                print(f"  ❌ Pas de données API pour {league_code}")
                continue
                
            if not fd_teams:
                print(f"  ❌ Pas de données FD pour {league_code}")
                continue
            
            # Créer le mapping
            mapping = self.match_teams(fd_teams, api_teams)
            
            if mapping:
                self.team_mapping[str(league_id)] = mapping
                total_processed += 1
                total_mapped += len(mapping)
                
                print(f"  ✅ {len(mapping)}/{len(fd_teams)} équipes mappées")
                
                # Afficher les équipes non mappées
                unmapped = [team for team in fd_teams if team not in mapping]
                if unmapped:
                    print(f"  ⚠️  Non mappées: {unmapped}")
            else:
                print(f"  ❌ Aucune correspondance trouvée")
        
        # Sauvegarder le résultat
        output_file = 'config/team_mapping.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.team_mapping, f, indent=2, ensure_ascii=False)
        
        print(f"\n🎉 Mapping terminé:")
        print(f"   📊 {total_processed} ligues traitées")
        print(f"   🏟️  {total_mapped} équipes mappées au total")
        print(f"   💾 Sauvegardé dans {output_file}")
        
        return self.team_mapping

if __name__ == "__main__":
    mapper = TeamMapper()
    mapping = mapper.create_full_mapping()
    
    # Afficher un aperçu du résultat
    print(f"\n📋 Aperçu du mapping:")
    for league_id, teams in list(mapping.items())[:3]:  # Premiers 3 pour l'aperçu
        print(f"Ligue {league_id}: {len(teams)} équipes")
        for fd, api in list(teams.items())[:3]:  # Premiers 3 teams
            print(f"  '{fd}' → '{api}'")
