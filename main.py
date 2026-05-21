import time
import requests
from datetime import datetime, timezone
import os
        
# ===== CONFIGURACIÓ =====

API_KEY = os.getenv("API_KEY")


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


SPORT = "soccer"

REGIONS = "eu"

MARKETS = "totals"
ALLOWED_BOOKMAKERS = []

previous_odds = {}
previous_times = {}

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    try:
        requests.post(url, json=payload)
    except Exception:
        pass

def fetch_odds():
    url = f"https://api.the-odds-api.com/v4/sports/{SPORT}/odds/"
    params = {
        "apiKey": API_KEY,
        "regions": REGIONS,
        "markets": MARKETS,
        "oddsFormat": "decimal"
    }
    response = requests.get(url, params=params)

    return response.json()

def analyze():
    global previous_odds
    data = fetch_odds()
    print(data)

    for match in data:
        commence_time = match.get("commence_time")

        # Parse match time and skip live matches
        if not commence_time:
            continue

        match_time = datetime.fromisoformat(commence_time.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)

        if match_time <= now:
            continue

        hours_until_kickoff = (
            match_time - now
        ).total_seconds() / 3600

        # Ignorar partits massa llunyans
        if hours_until_kickoff > 6:
            continue

        home = match.get("home_team")
        away = match.get("away_team")
        match_name = f"{home} vs {away}"
        for bookmaker in match.get("bookmakers", []):
            if ALLOWED_BOOKMAKERS and bookmaker.get("title") not in ALLOWED_BOOKMAKERS:
                continue

            bookie = bookmaker.get("title")

            allowed_markets = ["h2h", "spreads", "totals"]

            for market in bookmaker.get("markets", []):
                if market.get("key") not in allowed_markets:
                    continue

                for outcome in market.get("outcomes", []):
                    name = outcome.get("name")
                    price = outcome.get("price")

                    key = f"{match_name}-{bookie}-{name}"

                    if key in previous_odds:
                        old_price = previous_odds[key]
                        movement = ((old_price - price) / old_price) * 100

                        if abs(movement) >= 8:
                            message = (
                                f"🔥 STEAM MOVE\n\n"
                                f"⚽ {match_name}\n"
                                f"🏦 {bookie}\n"
                                f"📈 {name}\n"
                                f"💰 {old_price} → {price}\n"
                                f"📊 {movement:.2f}%"
                            )

                            print(message)
                            send_telegram(message)

                    previous_odds[key] = price
                    previous_times[key] = time.time()

while True:
    try:
        analyze()
        print("Escanejant quotes...")
        time.sleep(300)
    except Exception as e:
        print("Error:", e)
        time.sleep(60)
        