import requests

data = requests.get(
    "https://guest.api.arcadia.pinnacle.com/0.1/sports"
).json()

for sport in data:
    print(
        sport.get("id"),
        "-",
        sport.get("name")
    )