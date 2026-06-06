import requests

MATCHUP_ID = 0

leagues = requests.get(
    "https://guest.api.arcadia.pinnacle.com/0.1/sports/3/leagues"
).json()

league_id = 246

matchups = requests.get(
    f"https://guest.api.arcadia.pinnacle.com/0.1/leagues/{league_id}/matchups"
).json()

for m in matchups:
    MATCHUP_ID = m["id"]
    break

print("MATCHUP:", MATCHUP_ID)

markets = requests.get(
    f"https://guest.api.arcadia.pinnacle.com/0.1/matchups/{MATCHUP_ID}/markets/related/straight"
).json()

for market in markets:
    print(
        market.get("type")
    )