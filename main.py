from playwright.sync_api import sync_playwright
import re
import time
from datetime import datetime
import requests

previous_odds = {}
markets = {}
last_alerts = {}
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
def send_telegram(message):

    url = (
        f"https://api.telegram.org/bot"
        f"{BOT_TOKEN}/sendMessage"
    )

    data = {
        "chat_id": CHAT_ID,
        "text": message
    }

    requests.post(url, data=data)
with sync_playwright() as p:

    browser = p.chromium.launch(
        headless=True,
        args=["--no-sandbox"]
    )

    page = browser.new_page()

    while True:

        page.goto("https://www.pinnacle.com/en/soccer")

        page.wait_for_timeout(8000)

        text = page.locator("body").inner_text()

        lines = text.split("\n")

        current_match = "UNKNOWN"
        current_time = "UNKNOWN"
        current_market = "UNKNOWN"
        current_side = "UNKNOWN"
        hours_until_kickoff = 999

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if " (Match)" in line:
                current_match = line
                continue

            if "/" in line and ":" in line:
                current_time = line
                try:
                    match_time = datetime.strptime(
                        current_time,
                        "%m/%d/%Y %H:%M"
                    )
                    now = datetime.now()
                    hours_until_kickoff = (
                        match_time - now
                    ).total_seconds() / 3600
                except ValueError:
                    hours_until_kickoff = 999
                continue

            # detect market names like Over/Under values
            if line in ["2", "2.25", "2.5", "2.75", "3", "3.5"]:
                current_market = f"Over/Under {line}"
                continue

            if "Over" in line:
                current_side = "OVER"
            elif "Under" in line:
                current_side = "UNDER"

            if re.match(r"^\d+(\.\d+)?$", line):
                if current_market == "UNKNOWN" or current_side == "UNKNOWN":
                    continue

                odd = float(line)
                market_key = f"{current_match}-{current_market}"

                if market_key not in markets:
                    markets[market_key] = {}

                markets[market_key][current_side] = odd
                key = f"{current_match}-{current_market}-{current_side}-{line}"

                if key in previous_odds and previous_odds[key] != 0:
                    old_odd = previous_odds[key]
                    movement = ((old_odd - odd) / old_odd) * 100

                    if (
                        abs(movement) >= 8
                        and hours_until_kickoff <= 4
                        and "Over/Under" in current_market
                    ):
                        if key in last_alerts:
                            cooldown = time.time() - last_alerts[key]
                            if cooldown < 1800:
                                continue

                        print(
                            f"\n🔥 STEAM MOVE DETECTAT 🔥\n"
                            f"⚽ Partit: {current_match}\n"
                            f"📈 Mercat: {current_side} {current_market}\n"
                            f"💰 Quota: {old_odd} → {odd}\n"
                            f"📊 Moviment: {movement:.2f}%\n"
                        )
                        message = (
                            f"🔥 STEAM MOVE DETECTAT 🔥\n\n"
                            f"⚽ {current_match}\n"
                            f"📈 {current_side} {current_market}\n"
                            f"💰 {old_odd} → {odd}\n"
                            f"📊 {movement:.2f}%"
                        )

                        send_telegram(message)
                        last_alerts[key] = time.time()

                previous_odds[key] = odd

    print("Escaneig completat...\n")

    time.sleep(300)