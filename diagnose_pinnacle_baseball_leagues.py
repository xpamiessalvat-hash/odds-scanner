import os
import requests

URL = "https://guest.api.arcadia.pinnacle.com/0.1/sports/3/leagues"
headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Origin": "https://www.pinnacle.com",
    "Referer": "https://www.pinnacle.com/",
}
key = os.getenv("PINNACLE_X_API_KEY", "").strip()
if key:
    headers["X-API-Key"] = key

r = requests.get(URL, headers=headers, timeout=30)
print(f"HTTP_STATUS={r.status_code}")
print(f"API_KEY_CONFIGURED={bool(key)}")
try:
    data = r.json()
except Exception:
    print(r.text[:1000])
    raise SystemExit(1)

if not isinstance(data, list):
    print(data)
    raise SystemExit(1)

found = []
for league in data:
    name = str(league.get("name") or "")
    normalized = name.casefold()
    if any(term in normalized for term in (
        "mexican pacific", "liga mexicana del pacifico",
        "liga mexicana del pacífico"
    )):
        found.append((league.get("id"), name))

print("LMP_MATCHES=" + repr(found))
print("BASEBALL_LEAGUES:")
for league in data:
    print(f'{league.get("id")} - {league.get("name")}')
