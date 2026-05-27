from playwright.sync_api import sync_playwright
import time
from datetime import datetime
import requests
import os

previous_odds = {}
last_alerts = {}

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

print(BOT_TOKEN, flush=True)
print(CHAT_ID, flush=True)


def send_telegram(message):

    if not BOT_TOKEN or not CHAT_ID:

        print(
            "TELEGRAM VARIABLES NO TROBADES",
            flush=True
        )

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

    print(
        "MISSATGE TELEGRAM ENVIAT",
        flush=True
    )


print("Script iniciat", flush=True)

send_telegram("TEST TELEGRAM")

with sync_playwright() as p:

    print("Playwright iniciat", flush=True)

    browser = p.chromium.launch(
        headless=True,
        args=["--no-sandbox"]
    )

    while True:

        print("Loop iniciat", flush=True)
        print("VERSIO NOVA CLEAN", flush=True)

        page = browser.new_page()

        try:

            page.goto(
                "https://www.pinnacle.com/en/soccer",
                timeout=60000
            )

            page.wait_for_timeout(10000)

            page.wait_for_selector("body")

            text = page.inner_text("body")

            lines = text.splitlines()

            current_match = "UNKNOWN"
            current_time = "UNKNOWN"
            current_market = "UNKNOWN"
            current_side = "UNKNOWN"

            hours_until_kickoff = 999

            blocked_section = False

            for line in lines:

                line = line.strip()

                if not line:
                    continue

                # BLOQUEJAR FUTURES / OUTRIGHTS
                blocked_words = [
                    "Winner",
                    "Outright",
                    "Futures",
                    "Specials",
                    "To Qualify",
                    "Relegation",
                    "Top Goalscorer"
                ]

                if any(
                    word in line
                    for word in blocked_words
                ):
                    blocked_section = True
                    continue

                # RESETEJAR BLOCKED SECTION
                if "Money Line" in line:
                    blocked_section = False

                if blocked_section:
                    continue

                # FILTRE JUVENILS / RESERVES
                youth_words = [
                    "U17",
                    "U18",
                    "U19",
                    "U20",
                    "U21",
                    "U23",
                    "Youth",
                    "Reserve",
                    "Reserves",
                    "B Team"
                ]

                if any(
                    word in line
                    for word in youth_words
                ):
                    continue

                # FILTRE AMISTOSOS
                friendly_words = [
                    "Friendly",
                    "Club Friendly",
                    "Exhibition"
                ]

                if any(
                    word in line
                    for word in friendly_words
                ):
                    continue

                # DETECTAR PARTITS REALS
                if (
                    " - " in line
                    and len(line) < 60
                    and "Soccer" not in line
                    and "Odds" not in line
                    and "Winner" not in line
                    and "LEAGUE" not in line
                    and "WORLD CUP" not in line
                    and "CHAMPIONS LEAGUE" not in line
                    and "CONFERENCE LEAGUE" not in line
                ):

                    current_match = line

                    print(
                        f"MATCH ACTUAL: {current_match}",
                        flush=True
                    )

                    continue

                # DETECTAR HORA
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

                    except:

                        hours_until_kickoff = 999

                    continue

                # MONEY LINE
                if "Money Line" in line:

                    current_market = "Money Line"

                    continue

                # DRAW
                if line == "Draw":

                    current_side = "DRAW"

                # EQUIPS
                elif current_match != "UNKNOWN":

                    teams = current_match.split(" - ")

                    if line in teams:

                        current_side = line

                # DETECTAR QUOTES
                try:

                    odd = float(line)

                except:

                    continue

                print(
                    f"{current_match} | "
                    f"{current_side} | "
                    f"{odd}",
                    flush=True
                )

                if (
                    current_market == "UNKNOWN"
                    or current_side == "UNKNOWN"
                ):
                    continue

                key = (
                    f"{current_match}-"
                    f"{current_market}-"
                    f"{current_side}"
                )

                # DETECTAR MOVIMENT
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

                    # FILTRE STEAM
                    if (
                        abs(movement) >= 1
                        and hours_until_kickoff <= 12
                    ):

                        # COOLDOWN ALERTES
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
                            f"{movement:.2f}%\n",
                            flush=True
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

            print(
                "Escaneig completat...",
                flush=True
            )

        except Exception as e:

            print(
                f"ERROR: {e}",
                flush=True
            )

        finally:

            try:
                page.close()
            except:
                pass

        time.sleep(600)