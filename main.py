from playwright.sync_api import sync_playwright
import time
from datetime import datetime
import requests
import os
import json

previous_odds = {}
last_alerts = {}
last_move_times = {}

HISTORY_FILE = "steam_history.json"

if not os.path.exists(HISTORY_FILE):

    with open(HISTORY_FILE, "w") as f:

        json.dump([], f)

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


def update_clv(
    current_match,
    current_market,
    current_side,
    current_odd
):

    with open(HISTORY_FILE, "r") as f:

        history = json.load(f)

    updated = False

    for entry in history:

        if (
            entry["match"] == current_match
            and entry["market"] == current_market
            and entry["side"] == current_side
            and entry["closing_odd"] is None
        ):

            entry["closing_odd"] = current_odd

            clv = (
                (
                    entry["new_odd"]
                    - current_odd
                ) / entry["new_odd"]
            ) * 100

            entry["clv_percent"] = round(clv, 2)

            updated = True

    if updated:

        with open(HISTORY_FILE, "w") as f:

            json.dump(history, f, indent=4)


def update_results():

    with open(HISTORY_FILE, "r") as f:

        history = json.load(f)

    updated = False

    for entry in history:

        if entry["result"] is not None:
            continue

        if entry["closing_odd"] is None:
            continue

        if entry["clv_percent"] > 0:

            entry["result"] = "WIN"

            entry["profit"] = round(
                entry["new_odd"] - 1,
                2
            )

        else:

            entry["result"] = "LOSS"

            entry["profit"] = -1

        updated = True

    if updated:

        with open(HISTORY_FILE, "w") as f:

            json.dump(history, f, indent=4)


print("Script iniciat", flush=True)

with sync_playwright() as p:

    print("Playwright iniciat", flush=True)

    browser = p.chromium.launch(
        headless=True,
        args=["--no-sandbox"]
    )

    while True:

        print("Loop iniciat", flush=True)

        update_results()

        page = browser.new_page()

        # EVITAR CACHE
        page.set_extra_http_headers({
            "Cache-Control": "no-cache"
        })

        try:

            page.goto(
                "https://www.pinnacle.com/en/soccer",
                timeout=60000,
                wait_until="networkidle"
            )

            # REFRESH REAL
            page.reload(wait_until="networkidle")

            page.wait_for_timeout(5000)

            page.wait_for_selector("body")

            # SCROLL COMPLET
            for i in range(15):

                page.mouse.wheel(0, 10000)

                page.wait_for_timeout(1500)

            text = page.inner_text("body")

            lines = text.splitlines()

            current_match = "UNKNOWN"
            current_time = "UNKNOWN"
            current_market = "UNKNOWN"
            current_side = "UNKNOWN"
            current_line = "UNKNOWN"

            hours_until_kickoff = 999

            blocked_section = False
            moneyline_counter = 0

            for line in lines:

                line = line.strip()

                if not line:
                    continue

                # BLOQUEJAR FUTURES
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

                # MONEY LINE
                if "Money Line" in line:

                    blocked_section = False

                    current_market = "Money Line"
                    current_line = "ML"

                    moneyline_counter = 0

                    continue

                # HANDICAP
                if (
                    "Spread" in line
                    or "Handicap" in line
                ):

                    blocked_section = False

                    current_market = "Handicap"
                    current_line = "UNKNOWN"

                    moneyline_counter = 0

                    continue

                # TOTALS
                if (
                    "Total" in line
                    or "Over/Under" in line
                ):

                    blocked_section = False

                    current_market = "Total"
                    current_line = "UNKNOWN"

                    moneyline_counter = 0

                    continue

                if blocked_section:
                    continue

                # FILTRE JUVENILS
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

                # DETECTAR PARTIT
                if (
                    " - " in line
                    and len(line) < 60
                    and "Soccer" not in line
                    and "Odds" not in line
                    and "Winner" not in line
                    and "LEAGUE" not in line
                    and "SOCCER" not in line
                    and "FIFA" not in line
                    and "UEFA" not in line
                ):

                    current_match = line
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

                        # IGNORAR PARTITS LLUNYANS
                        if (
                            hours_until_kickoff > 3
                            or hours_until_kickoff < 0
                        ):

                            current_match = "UNKNOWN"

                            continue

                    except:

                        hours_until_kickoff = 999

                    continue

                # DRAW
                if line == "Draw":

                    current_side = "DRAW"

                # EQUIPS
                elif current_match != "UNKNOWN":

                    teams = current_match.split(" - ")

                    if line in teams:

                        current_side = line

                # OVER
                if "Over" in line:

                    current_side = "OVER"
                    continue

                # UNDER
                if "Under" in line:

                    current_side = "UNDER"
                    continue

                # DETECTAR LÍNIES
                if current_market in ["Total", "Handicap"]:

                    try:

                        test_line = float(
                            line.replace("+", "")
                        )

                        current_line = line

                        allowed_suffixes = [
                            ".0",
                            ".25",
                            ".5",
                            ".75"
                        ]

                        if not any(
                            suffix in current_line
                            for suffix in allowed_suffixes
                        ):
                            continue

                        continue

                    except:

                        pass

                # DETECTAR QUOTES
                try:

                    odd = float(line)

                    # FILTRE LIQUIDITAT
                    if odd < 1.20 or odd > 10:
                        continue

                except:

                    continue

                # VALIDACIÓ
                if (
                    current_match == "UNKNOWN"
                    or current_market == "UNKNOWN"
                    or current_side == "UNKNOWN"
                ):
                    continue

                if (
                    current_market in ["Handicap", "Total"]
                    and current_line == "UNKNOWN"
                ):
                    continue

                # KEY
                key = (
                    f"{current_match}-"
                    f"{current_market}-"
                    f"{current_side}-"
                    f"{current_line}"
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

                    print(
                        f"{key} | "
                        f"{old_odd} -> {odd} | "
                        f"{movement:.2f}%",
                        flush=True
                    )

                    velocity_score = 0

                    if key in last_move_times:

                        seconds_since_move = (
                            time.time()
                            - last_move_times[key]
                        )

                        if seconds_since_move <= 60:

                            velocity_score = 30

                        elif seconds_since_move <= 300:

                            velocity_score = 15

                    steam_score = 0

                    steam_score += min(
                        abs(movement) * 40,
                        50
                    )

                    if hours_until_kickoff <= 1:

                        steam_score += 40

                    elif hours_until_kickoff <= 3:

                        steam_score += 30

                    steam_score += velocity_score

                    steam_score = round(
                        min(steam_score, 100),
                        2
                    )

                    steam_tier = "Weak"

                    if steam_score >= 90:

                        steam_tier = "Nuclear"

                    elif steam_score >= 75:

                        steam_tier = "Gold"

                    elif steam_score >= 60:

                        steam_tier = "Silver"

                    elif steam_score >= 40:

                        steam_tier = "Bronze"

                    # ALERTA STEAM
                    if (
                        steam_score >= 5
                        and hours_until_kickoff <= 3
                        and hours_until_kickoff >= 0
                        and abs(movement) >= 0.5
                    ):

                        if key in last_alerts:

                            cooldown = (
                                time.time()
                                - last_alerts[key]
                            )

                            if cooldown < 1800:
                                continue

                        print(
                            f"\n🔥 STEAM MOVE DETECTAT 🔥\n"
                            f"⚽ {current_match}\n"
                            f"📈 {current_side} "
                            f"{current_market}\n"
                            f"📏 {current_line}\n"
                            f"💰 {old_odd} → {odd}\n"
                            f"📊 {movement:.2f}%\n"
                            f"🔥 Score: {steam_score}/100\n"
                            f"🏆 Tier: {steam_tier}\n",
                            flush=True
                        )

                        message = (
                            f"🔥 STEAM MOVE DETECTAT 🔥\n\n"
                            f"⚽ {current_match}\n"
                            f"📈 {current_side} "
                            f"{current_market}\n"
                            f"📏 {current_line}\n"
                            f"💰 {old_odd} → {odd}\n"
                            f"📊 {movement:.2f}%\n"
                            f"🔥 Score: {steam_score}/100\n"
                            f"🏆 Tier: {steam_tier}"
                        )

                        send_telegram(message)

                        last_alerts[key] = time.time()

                previous_odds[key] = odd
                last_move_times[key] = time.time()

                # RESET DESPRÉS QUOTA
                if current_market == "Money Line":

                    current_side = "UNKNOWN"

                elif current_market in ["Total", "Handicap"]:

                    current_line = "UNKNOWN"

                # LIMITAR MONEYLINE
                if current_market == "Money Line":

                    moneyline_counter += 1

                    if moneyline_counter >= 10:

                        current_market = "UNKNOWN"

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

        time.sleep(30)