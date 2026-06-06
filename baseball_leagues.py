import requests

data = requests.get(
    "https://guest.api.arcadia.pinnacle.com/0.1/sports/3/leagues"
).json()

for league in data:
    print(
        league.get("id"),
        "-",
        league.get("name")
    )