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

        # SI JA TÉ RESULTAT
        if entry["result"] is not None:
            continue

        # SI ENCARA NO TÉ CLOSING LINE
        if entry["closing_odd"] is None:
            continue

        # PLACEHOLDER RESULTAT
        # després connectarem SofaScore

        # EXEMPLE TEMPORAL
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

        try:

            page.goto(
                "https://www.pinnacle.com/en/soccer",
                timeout=60000
            )

            page.wait_for_timeout(10000)

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

                # MONEY LINE
                if "Money Line" in line:

                    blocked_section = False

                    current_market = "Money Line"

                    moneyline_counter = 0

                    continue

                # ASIAN HANDICAP
                if (
                    "Spread" in line
                    or "Handicap" in line
                ):

                    blocked_section = False

                    current_market = "Handicap"

                    moneyline_counter = 0

                    continue

                # TOTALS
                if (
                    "Total" in line
                    or "Over/Under" in line
          ):

                    blocked_section = False

                    current_market = "Total"

                    moneyline_counter = 0

                    continue


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

                # DRAW
                if line == "Draw":

                    current_side = "DRAW"

                # EQUIPS
                elif current_match != "UNKNOWN":

                    teams = current_match.split(" - ")

                    if line in teams:

                        current_side = line
                # DETECTAR LÍNIES TOTALS/HANDICAP
                if (
                    current_market in ["Total", "Handicap"]
):

                    try:

                        test_line = float(
                            line.replace("+", "")
        )

                        current_line = line

                        continue

                    except:

                        pass

                 # FILTRAR LÍNIES EXÒTIQUES
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
                # DETECTAR QUOTES
                try:

                    odd = float(line)

                    # FILTRAR QUOTES REALS
                    if odd < 1.01 or odd > 20:
                        continue

                except:

                    continue

                if (
                    current_match == "UNKNOWN"
                    or current_market == "UNKNOWN"
                    or current_side == "UNKNOWN"
                    or current_line == "UNKNOWN"
            ):
                    continue

                key = (
                    f"{current_match}-"
                    f"{current_market}-"
                    f"{current_side}"
                )

                # ACTUALITZAR CLV
                if hours_until_kickoff <= 0:

                    update_clv(
                        current_match,
                        current_market,
                        current_side,
                        odd
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
                    velocity_score = 0

                    if key in last_move_times:

                        seconds_since_move = (
                           time.time()
                           - last_move_times[key]
    )

                    # MOVIMENT MOLT RÀPID
                    if seconds_since_move <= 60:

                        velocity_score = 30

                    # MOVIMENT RÀPID
                    elif seconds_since_move <= 300:

                        velocity_score = 15
                    steam_score = 0

                    # SCORE MOVIMENT
                    steam_score += min(
                        abs(movement) * 20,
                        50
                    )

                    # SCORE KICKOFF
                    if hours_until_kickoff <= 6:

                        steam_score += 30

                    elif hours_until_kickoff <= 12:

                        steam_score += 15
                    steam_score += velocity_score

                    # LIMIT FINAL
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

                    # FILTRE STEAM
                    if (
                        steam_score >= 20
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
                            f"{movement:.2f}%\n"
                            f"🔥 Score: "
                            f"{steam_score}/100\n"
                            f"🏆 Tier: "
                            f"{steam_tier}\n",
                            flush=True
                        )

                        message = (
                            f"🔥 STEAM MOVE DETECTAT 🔥\n\n"
                            f"⚽ {current_match}\n"
                            f"📈 {current_side} "
                            f"{current_market}\n"
                            f"💰 {old_odd} → {odd}\n"
                            f"📊 {movement:.2f}%\n"
                            f"🔥 Score: "
                            f"{steam_score}/100\n"
                            f"🏆 Tier: "
                            f"{steam_tier}\n"
                        )

                        send_telegram(message)

                        steam_entry = {
                            "timestamp": str(datetime.now()),
                            "match": current_match,

                            "home_team": current_match.split(" - ")[0],
                            "away_team": current_match.split(" - ")[1],

                            "market": current_market,
                            "side": current_side,
                            "old_odd": old_odd,
                            "new_odd": odd,
                            "movement": round(movement, 2),
                            "steam_score": steam_score,
                            "hours_until_kickoff": round(
                                hours_until_kickoff,
                                2
                            ),
                            "closing_odd": None,
                            "clv_percent": None,
                            "result": None,
                            "profit": None
                        }

                        with open(HISTORY_FILE, "r") as f:

                            history = json.load(f)

                        history.append(steam_entry)

                        with open(HISTORY_FILE, "w") as f:

                            json.dump(history, f, indent=4)

                        last_alerts[key] = time.time()

                previous_odds[key] = odd
                last_move_times[key] = time.time()

                # LIMITAR A 3 QUOTES MONEYLINE
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