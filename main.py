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
market_prices = {}

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
    global previous_odds, market_prices, previous_times
    data = fetch_odds()
    print(data)

    for match in data:
        commence_time = match.get("commence_time")

        if not commence_time:
            continue

        match_time = datetime.fromisoformat(commence_time.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)

        if match_time <= now:
            continue

        hours_until_kickoff = (match_time - now).total_seconds() / 3600

        if hours_until_kickoff > 4:
            continue

        home = match.get("home_team")
        away = match.get("away_team")
        match_name = f"{home} vs {away}"

        allowed_bookmakers = ["Pinnacle", "Bet365"]
        allowed_markets = ["totals"]

        for bookmaker in match.get("bookmakers", []):
            if bookmaker.get("title") not in allowed_bookmakers:
                continue

            bookie = bookmaker.get("title")

            for market in bookmaker.get("markets", []):
                if market.get("key") not in allowed_markets:
                    continue

                for outcome in market.get("outcomes", []):
                    name = outcome.get("name")
                    price = outcome.get("price")
                    key = f"{match_name}-{bookie}-{name}"
                    market_prices[key] = {"bookie": bookie, "price": price}

                    if key in previous_odds:
                        old_price = previous_odds[key]
                        movement = ((old_price - price) / old_price) * 100

                        # compute minutes passed since last seen for this key
                        if key in previous_times:
                            minutes_passed = (time.time() - previous_times[key]) / 60
                        else:
                            minutes_passed = float('inf')

                        if (
                            movement >= 8
                            and minutes_passed <= 15
                            and bookie == "Pinnacle"
                            and old_price >= 1.70
                            and price <= 1.60
                        ):
                            message = (
                                f"📉 STEAM MOVE\n"
                                f"Partit: {match_name}\n"
                                f"Mercat: {market.get('key')}\n"
                                f"Selecció: {name}\n"
                                f"Bookie: {bookie}\n"
                                f"{old_price} → {price}\n"
                                f"Move: {movement:.2f}%"
                            )
                            print(message)
                            send_telegram(message)

                    if bookie == "Pinnacle":
                        for other_key, other_data in market_prices.items():
                            if (
                                name in other_key
                                and match_name in other_key
                                and other_data["bookie"] != "Pinnacle"
                            ):
                                soft_price = other_data["price"]
                                if soft_price > price * 1.05:
                                    value_message = (
                                        f"💰 VALUE BET DETECTED\n"
                                        f"Partit: {match_name}\n"
                                        f"Selecció: {name}\n"
                                        f"Pinnacle: {price}\n"
                                        f"{other_data['bookie']}: {soft_price}\n"
                                        f"Edge: {((soft_price / price) - 1) * 100:.2f}%"
                                    )
                                    print(value_message)
                                    send_telegram(value_message)

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
        