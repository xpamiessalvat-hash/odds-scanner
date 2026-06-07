import requests
import time
import os
import random
import json

from datetime import (
    datetime,
    timezone
)

print(
    "⚾ BASEBALL SCANNER ⚾",
    flush=True
)
previous_odds = {}
last_alerts = {}
pending_steam = {}

BOT_TOKEN = "8826186519:AAFh2H6EUgyvENWyL5-AZ9tphGUxqNoCkpU"

CHAT_ID = "-1003576336170"

GOOGLE_SHEETS_WEBHOOK = "https://script.google.com/macros/s/AKfycbzYM5xrBqacg7Vjb53okMn5Ea84_21WPdg3rQyi1zimPgJ25YSEKAaDi5HZOHrT8Ac1/exec"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/137.0.0.0 "
        "Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.pinnacle.com",
    "Referer": "https://www.pinnacle.com/",
    "Connection": "keep-alive"
}

session = requests.Session()

session.headers.update(
    HEADERS
)

LEAGUES_URL = (
    "https://guest.api.arcadia.pinnacle.com"
    "/0.1/sports/3/leagues"
)

BLOCKED_WORDS = [
    "Friendly",
    "Friendlies",
    "U17",
    "U18",
    "U19",
    "U20",
    "U21",
    "U23",
    "Youth",
    "Reserve",
    "Reserves",
    "Corners",
    "Esports",
    "Simulation",
    "Women",
    "3rd Division",
    "4. Liga",
    "Amateur",
    "Regional",
    "Kolmonen",
    "Kakkonen",
    "Division 1 Women",
    "NPL"
]

VALID_SPREADS = [
    -2.5,
    -2.0,
    -1.5,
    -1.0,
    -0.5,
    0,
    0.5,
    1.0,
    1.5,
    2.0,
    2.5
]

VALID_TOTALS = [
    6.5,
    7.5,
    8.5,
    9.5,
    10.5,
    11.5
]

TOP_LEAGUES = [
    "Premier League",
    "Champions League",
    "Serie A",
    "La Liga",
    "Bundesliga",
    "Ligue 1",
    "Eredivisie",
    "Primeira Liga"
]

MARKET_WEIGHTS = {
    "spread": 1.25,
    "total": 1.2
}

STEAM_CONFIRMATION_SECONDS = 60

MIN_MONEYLINE_STEAM = 5
MIN_SPREAD_STEAM = 5
MIN_TOTAL_STEAM = 4

# Initialization complete

def send_telegram(message):

    try:

        url = (
            f"https://api.telegram.org/"
            f"bot{BOT_TOKEN}/sendMessage"
        )

        payload = {
            "chat_id": CHAT_ID,
            "text": message
        }

        response = requests.post(
            url,
            json=payload,
            timeout=10
        )

        print(
            f"TELEGRAM STATUS: {response.status_code}",
            flush=True
        )

        print(
            f"TELEGRAM RESPONSE: {response.text}",
            flush=True
        )

    except Exception as e:

        print(
            f"ERROR TELEGRAM: {e}",
            flush=True
        )


# TEST D'ARRANCADA (elimina'l quan acabis les proves)
send_telegram("ARRANCADA BASEBALL")

print(
    "MISSATGE ARRANCADA ENVIAT",
    flush=True
)

def save_to_sheets(data):

    try:

        response = requests.post(
            GOOGLE_SHEETS_WEBHOOK,
            json=data,
            timeout=10
        )

        print(
            f"✅ Guardat a Google Sheets: "
            f"{response.status_code}",
            flush=True
        )

        print(
            response.text,
            flush=True
        )

    except Exception as e:

        print(
            f"ERROR SHEETS: {e}",
            flush=True
        )

    return None


def american_to_decimal(price):

    if price is None:
        return None

    if price > 0:
        return round(
            (price / 100) + 1,
            3
        )

    return round(
        (100 / abs(price)) + 1,
        3
    )


def is_blocked_league(name):

    for word in BLOCKED_WORDS:

        if word.lower() in name.lower():

            return True

    return False


def calculate_steam_score(
    movement,
    market_type,
    league_name,
    hours_until_match
):

    movement_score = movement * 2

    market_weight = MARKET_WEIGHTS.get(
        market_type,
        1
    )

    if hours_until_match <= 1:

        time_weight = 1.5

    elif hours_until_match <= 2:

        time_weight = 1.3

    else:

        time_weight = 1

    league_weight = 1

    for top_league in TOP_LEAGUES:

        if top_league.lower() in league_name.lower():

            league_weight = 1.3
            break

    steam_score = (
        movement_score
        * market_weight
        * time_weight
        * league_weight
    )

    return round(
        min(100, steam_score),
        1
    )


def get_strength_label(score):

    if score >= 85:
        return "ELITE"

    if score >= 70:
        return "HIGH"

    if score >= 55:
        return "MEDIUM"

    return "LOW"


def calculate_value_limit(
    old_price,
    steam_price,
    movement
):

    if movement >= 20:

        retention = 0.65

    elif movement >= 15:

        retention = 0.55

    else:

        retention = 0.45

    value_limit = (
        steam_price
        + (
            old_price
            - steam_price
        ) * retention
    )

    return round(
        value_limit,
        3
    )


while True:

    print(
        "\nLoop iniciat...\n",
        flush=True
    )

    try:

        print(
            "Obtenint leagues...",
            flush=True
        )

        response = session.get(
            LEAGUES_URL,
            timeout=30
        )

        print(
            f"STATUS LEAGUES: "
            f"{response.status_code}",
            flush=True
        )

        if response.status_code == 403:

            print(
                "403 DETECTAT - BACKOFF 10 MIN",
                flush=True
            )

            time.sleep(600)

            continue

        if response.status_code != 200:

            print(
                f"Resposta incorrecta: "
                f"{response.text[:300]}",
                flush=True
            )

            time.sleep(120)

            continue

        leagues = response.json()

        matchup_map = {}

        for league in leagues:

            try:

                league_id = league.get(
                    "id"
                )

                league_name = league.get(
                    "name",
                    "UNKNOWN"
                )

                if not league_id:
                    continue

                ALLOWED_LEAGUES = {
                    220,      # NCAA Baseball
                    246,      # MLB
                    6227,     # KBO
                    187703,   # NPB
                    208753    # CPBL Taiwan
                }

                if league_id not in ALLOWED_LEAGUES:
                    continue

                if is_blocked_league(
                    league_name
                ):
                    continue

                matchups_url = (
                    "https://guest.api.arcadia.pinnacle.com"
                    f"/0.1/leagues/"
                    f"{league_id}"
                    "/matchups"
                )

                response = session.get(
                    matchups_url,
                    timeout=30
                )

                time.sleep(
                    random.uniform(0.4, 1.2)
                )

                if (
                    response.status_code
                    != 200
                ):
                    continue

                matchups = response.json()

                for matchup in matchups:

                    try:

                        matchup_id = matchup.get(
                            "id"
                        )

                        if not matchup_id:
                            continue

                        start_time = matchup.get(
                            "startTime"
                        )

                        if not start_time:
                            continue

                        try:

                            match_time = (
                                datetime.fromisoformat(
                                    start_time.replace(
                                        "Z",
                                        "+00:00"
                                    )
                                )
                            )

                            now = datetime.now(
                                timezone.utc
                            )

                            hours_until_match = (
                                (
                                    match_time - now
                                ).total_seconds()
                                / 3600
                            )

                            if (
                                hours_until_match < 0
                                or hours_until_match > 24
                            ):
                                continue

                        except:

                            continue

                        participants = matchup.get(
                            "participants",
                            []
                        )

                        home_team = "HOME"
                        away_team = "AWAY"

                        for participant in participants:

                            alignment = participant.get(
                                "alignment"
                            )

                            name = participant.get(
                                "name",
                                "UNKNOWN"
                            )

                            if alignment == "home":

                                home_team = name

                            elif alignment == "away":

                                away_team = name

                        match_name = (
                            f"{home_team} vs "
                            f"{away_team}"
                        )

                        matchup_map[matchup_id] = {
                            "match_name": match_name,
                            "league_name": league_name,
                            "hours_until_match": hours_until_match
                        }

                    except Exception as e:

                        print(
                            f"ERROR MATCHUP: {e}",
                            flush=True
                        )

            except Exception as e:

                print(
                    f"ERROR LEAGUE: {e}",
                    flush=True
                )

        print(
            f"Matchups totals: "
            f"{len(matchup_map)}",
            flush=True
        )

        for matchup_id in matchup_map:

            try:

                match_name = (
                    matchup_map[matchup_id]
                    ["match_name"]
                )

                league_name = (
                    matchup_map[matchup_id]
                    ["league_name"]
                )

                hours_until_match = (
                    matchup_map[matchup_id]
                    ["hours_until_match"]
                )

                market_url = (
                    "https://guest.api.arcadia.pinnacle.com"
                    f"/0.1/matchups/"
                    f"{matchup_id}"
                    "/markets/related/straight"
                )

                response = session.get(
                    market_url,
                    timeout=30
                )

                time.sleep(
                    random.uniform(0.4, 1.2)
                )

                if (
                    response.status_code
                    != 200
                ):
                    continue

                markets = response.json()

                for market in markets:

                    try:

                        market_type = market.get(
                            "type"
                        )

                        if market_type not in [
                            "moneyline",
                            "spread",
                            "total"
                        ]:
                            continue

                        is_alternate = market.get(
                            "isAlternate",
                            False
                        )

                        if is_alternate:
                            continue

                        prices = market.get(
                            "prices",
                            []
                        )

                        for price_data in prices:

                                    side = price_data.get(
                                        "designation"
                                    )

                                    american_price = (
                                        price_data.get(
                                            "price"
                                        )
                                    )

                                    points = price_data.get(
                                        "points"
                                    )

                                    if market_type == "spread":

                                        if points not in VALID_SPREADS:
                                            continue

                                    elif market_type == "total":

                                        if points not in VALID_TOTALS:
                                            continue

                                    decimal_odd = (
                                        american_to_decimal(
                                            american_price
                                        )
                                    )

                                    key = (
                                        f"{match_name}-"
                                        f"{market_type}-"
                                        f"{side}-"
                                        f"{points}"
                                    )

                                    current_time = time.time()

                                    if key in previous_odds:

                                        old_odd = (
                                            previous_odds[key]
                                        )

                                        movement = (
                                            (
                                                old_odd
                                                - decimal_odd
                                            ) / old_odd
                                        ) * 100

                                        if market_type == "moneyline":
                                            min_required = MIN_MONEYLINE_STEAM

                                        elif market_type == "spread":
                                            min_required = MIN_SPREAD_STEAM

                                        else:
                                            min_required = MIN_TOTAL_STEAM

                                        if (
                                            movement >= min_required
                                            and movement <= 25
                                        ):

                                            if key not in pending_steam:

                                                pending_steam[key] = {
                                                    "timestamp": current_time,
                                                    "old_odd": old_odd,
                                                    "new_odd": decimal_odd,
                                                    "league_name": league_name,
                                                    "match_name": match_name,
                                                    "market_type": market_type,
                                                    "side": side,
                                                    "points": points,
                                                    "movement": movement,
                                                    "hours_until_match": hours_until_match,
                                                    "matchup_id": matchup_id
                                                }

                                            else:

                                                steam_data = (
                                                    pending_steam[key]
                                                )

                                                elapsed = (
                                                    current_time
                                                    - steam_data["timestamp"]
                                                )

                                                if (
                                                    elapsed >=
                                                    STEAM_CONFIRMATION_SECONDS
                                                ):

                                                    if (
                                                        decimal_odd
                                                        <= steam_data["new_odd"]
                                                    ):

                                                        steam_score = (
                                                            calculate_steam_score(
                                                                steam_data["movement"],
                                                                market_type,
                                                                league_name,
                                                                hours_until_match
                                                            )
                                                        )

                                                        strength = (
                                                            get_strength_label(
                                                                steam_score
                                                            )
                                                        )

                                                        value_limit = (
                                                            calculate_value_limit(
                                                                steam_data["old_odd"],
                                                                decimal_odd,
                                                                steam_data["movement"]
                                                            )
                                                        )

                                                        if market_type == "moneyline":
                                                            market_text = side if side else "moneyline"
                                                        else:
                                                            market_text = f"{side} {points}"

                                                        print(
                                                            f"🏆 {league_name}\n"
                                                            f"{match_name}\n"
                                                            f"{market_type}\n"
                                                            f"{market_text}\n"
                                                            f"{steam_data['old_odd']} "
                                                            f"-> "
                                                            f"{decimal_odd}\n",
                                                            flush=True
                                                        )

                                                        message = (
                                                            f"⚾🔥 BASEBALL STEAM 🔥⚾\n\n"
                                                            f"🏆 {league_name}\n"
                                                            f"⚽ {match_name}\n"
                                                            f"📈 {market_type}\n"
                                                            f"🎯 {market_text}\n\n"
                                                            f"💰 Steam:\n"
                                                            f"{steam_data['old_odd']} "
                                                            f"-> "
                                                            f"{decimal_odd}\n\n"
                                                            f"✅ VALUE FINS:\n"
                                                            f"{value_limit}\n\n"
                                                            f"📊 "
                                                            f"{steam_data['movement']:.2f}%\n"
                                                            f"⭐ Score: "
                                                            f"{steam_score}/100\n"
                                                            f"🔥 Strength: "
                                                            f"{strength}\n"
                                                            f"🕒 Kickoff: "
                                                            f"{hours_until_match:.1f}h"
                                                        )

                                                        save_to_sheets({
                                                            "league": league_name,
                                                            "match": match_name,
                                                            "market": market_type,
                                                            "selection": market_text,
                                                            "entry_odds": decimal_odd,
                                                            "value_limit": value_limit,
                                                            "steam_percent": round(
                                                                steam_data['movement'],
                                                                2
                                                            ),
                                                            "steam_score": steam_score,
                                                            "strength": strength,
                                                            "kickoff_hours": round(
                                                                hours_until_match,
                                                                1
                                                            ),
                                                            "matchup_id": matchup_id,
                                                            "market_type": market_type,
                                                            "points": points,
                                                            "side": side
                                                        })

                                                        print(
                                                            "MISSATGE A ENVIAR:",
                                                            flush=True
                                                        )

                                                        print(
                                                            message,
                                                            flush=True
                                                        )

                                                        send_telegram(
                                                            message
                                                        )

                                                        # cleanup
                                                        del pending_steam[key]

                                                        previous_odds[key] = decimal_odd

                    except Exception as e:

                        print(
                            f"ERROR MARKET: {e}",
                            flush=True
                        )

            except Exception as e:

                print(
                    f"ERROR MATCHUP: {e}",
                    flush=True
                )

    except Exception as e:

        print(
            f"ERROR: {e}",
            flush=True
        )

        time.sleep(120)

    time.sleep(5)
