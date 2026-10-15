import os
import requests

URL = "https://guest.api.arcadia.pinnacle.com/0.1/sports/3/leagues?all=false"
headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Origin": "https://www.pinnacle.com",
    "Referer": "https://www.pinnacle.com/",
}
key = os.getenv("PINNACLE_X_API_KEY", "").strip()
if key:
    headers["x-api-key"] = key

print("PINNACLE_X_API_KEY configured:", bool(key))
try:
    response = requests.get(URL, headers=headers, timeout=25)
    print("HTTP status:", response.status_code)
    response.raise_for_status()
    leagues = response.json()
except Exception as exc:
    print("REQUEST ERROR:", type(exc).__name__, str(exc))
    raise SystemExit(1)

if not isinstance(leagues, list):
    print("Unexpected response:", str(leagues)[:1000])
    raise SystemExit(1)

terms = ("mexican pacific", "liga mexicana del pacifico", "liga mexicana del pacífico")
matches = [
    league for league in leagues
    if any(term in str(league.get("name", "")).casefold() for term in terms)
]
print("LMP matches:", [(x.get("id"), x.get("name")) for x in matches])
print("League count:", len(leagues))
for league in leagues:
    print(f'{league.get("id")} - {league.get("name")}')
