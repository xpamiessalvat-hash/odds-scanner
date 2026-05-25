from playwright.sync_api import sync_playwright
import re
import time
from datetime import datetime
import requests
import os

previous_odds = {}
markets = {}
last_alerts = {}

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")


def send_telegram(message):

    if not BOT_TOKEN or not CHAT_ID:
        return

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

    while True:

        print("Loop iniciat")

        page = browser.new_page()

        try:

            page.goto(
                "https://www.pinnacle.com/en/soccer",
                timeout=60000
            )

            page.wait_for_timeout(3000)

            page.wait_for_load_state(
                "domcontentloaded"
            )

            text = page.content()

            lines = text.splitlines()

            current_match = "UNKNOWN"
            current_time = "UNKNOWN"
            current_market = "UNKNOWN"
            current_side = "UNKNOWN"
            hours_until_kickoff = 999

            for line in lines:

                line = line.strip()

                if not line:
                    continue

                # MATCH
                if " (Match)" in line:
                    current_match = line
                    continue

                # DATE / TIME
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

                # TOTALS MARKET
                if line in [
                    "2",
                    "2.25",
                    "2.5",
                    "2.75",
                    "3",
                    "3.5"
                ]:

                    current_market = (
                        f"Over/Under {line}"
                    )

                    continue

                # SIDE
                if "Over" in line:
                    current_side = "OVER"

                elif "Under" in line:
                    current_side = "UNDER"

                # ODDS
                if re.match(
                    r"^\d+(\.\d+)?$",
                    line
                ):

                    if (
                        current_market == "UNKNOWN"
                        or current_side == "UNKNOWN"
                    ):
                        continue

                    odd = float(line)

                    market_key = (
                        f"{current_match}-"
                        f"{current_market}"
                    )

                    if market_key not in markets:
                        markets[market_key] = {}

                    markets[market_key][current_side] = odd

                    key = (
                        f"{current_match}-"
                        f"{current_market}-"
                        f"{current_side}"
                    )

                    # STEAM DETECTION
                    if (
                        key in previous_odds
                        and previous_odds[key] != 0
                    ):

                        old_odd = previous_odds[key]

                        movement = (
                            (
                                old_odd - odd
                            ) / old_odd
                        ) * 100

                        if (
                            movement >= 8
                            and hours_until_kickoff <= 4
                            and "Over/Under"
                            in current_market
                        ):

                            # COOLDOWN
                            if key in last_alerts:

                                cooldown = (
                                    time.time()
                                    - last_alerts[key]
                                )

                                if cooldown < 1800:
                                    continue

                            print(
                                f"\n🔥 STEAM MOVE DETECTAT 🔥\n"
                                f"⚽ Partit: "
                                f"{current_match}\n"
                                f"📈 Mercat: "
                                f"{current_side} "
                                f"{current_market}\n"
                                f"💰 Quota: "
                                f"{old_odd} → {odd}\n"
                                f"📊 Moviment: "
                                f"{movement:.2f}%\n"
                            )

                            message = (
                                f"🔥 STEAM MOVE DETECTAT 🔥\n\n"
                                f"⚽ {current_match}\n"
                                f"📈 {current_side} "
                                f"{current_market}\n"
                                f"💰 {old_odd} → {odd}\n"
                                f"📊 {movement:.2f}%"
                            )

                            send_telegram(message)

                            last_alerts[key] = time.time()

                    previous_odds[key] = odd

            print("Escaneig completat...")

        except Exception as e:

            print(f"ERROR: {e}")

        finally:

            try:
                page.close()
            except:
                pass

        time.sleep(600)