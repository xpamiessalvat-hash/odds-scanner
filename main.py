import time
import requests
from datetime import datetime, timezone
import os
        
# ===== CONFIGURACIÓ =====

API_KEY = os.getenv("API_KEY")
print(API_KEY)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


SPORT = "soccer"

REGIONS = "eu"

MARKETS = "totals"

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
            allowed_bookmakers = ["Pinnacle", "Bet365"]
            if bookmaker.get("title") not in allowed_bookmakers:
                continue
            bookie = bookmaker.get("title")
            print(bookie)
            for market in bookmaker.get("markets", []):
                for outcome in market.get("outcomes", []):
                    name = outcome.get("name")
                    price = outcome.get("price")

                    key = f"{match_name}-{bookie}-{name}"

                    if key in previous_odds:
                        old_price = previous_odds[key]
                        old_time = previous_times.get(key, time.time())

                        movement = ((old_price - price) / old_price) * 100
                        minutes_passed = (time.time() - old_time) / 60

                        # Detect steam move
                        if abs(movement) >= 5 and minutes_passed <= 15:
                            message = (
                                f"🔥 STEAM MOVE DETECTAT\n\n"
                                f"Partit: {match_name}\n"
                                f"Casa: {bookie}\n"
                                f"Mercat: {name}\n"
                                f"Quota antiga: {old_price}\n"
                                f"Quota actual: {price}\n"
                                f"Moviment: {movement:.2f}%\n"
                                f"Temps: {minutes_passed:.1f} minuts"
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
        