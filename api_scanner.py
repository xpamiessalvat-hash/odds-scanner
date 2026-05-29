import requests
import time
import os

from datetime import (
    datetime,
    timezone
)

print(
    "API Scanner iniciat",
    flush=True
)

previous_odds = {}
last_alerts = {}
pending_steam = {}

BOT_TOKEN = os.getenv(
    "BOT_TOKEN"
)

CHAT_ID = os.getenv(
    "CHAT_ID"
)

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
    "Origin": "https://www.pinnacle.com",
    "Referer": "https://www.pinnacle.com/",
    "Connection": "keep-alive"
}

LEAGUES_URL = (
    "https://guest.api.arcadia.pinnacle.com"
    "/0.1/sports/29/leagues"
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

VALID_POINTS = [
    -1.5,
    -1.25,
    -1,
    -0.75,
    -0.5,
    -0.25,
    0,
    0.25,
    0.5,
    0.75,
    1,
    1.25,
    1.5,
    1.75,
    2,
    2.25,
    2.5,
    2.75,
    3,
    3.25,
    3.5
]

VALID_TEAM_TOTAL_POINTS = [
    1,
    1.25,
    1.5,
    1.75,
    2,
    2.25
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
    "spread": 1.2,
    "total": 1.15,
    "team_total": 0.9
}

STEAM_CONFIRMATION_SECONDS = 60


def send_telegram(message):

    try:

        url = (
            f"https://api.telegram.org/"
            f"bot{BOT_TOKEN}/sendMessage"
        )

        data = {
            "chat_id": CHAT_ID,
            "text": message
        }

        requests.post(
            url,
            data=data,
            timeout=10
        )

    except Exception as e:

        print(
            f"ERROR TELEGRAM: {e}",
            flush=True
        )


def american_to_decimal(price):

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

        time_weight = 1.4

    elif hours_until_match <= 2:

        time_weight = 1.25

    else:

        time_weight = 1

    league_weight = 1

    for top_league in TOP_LEAGUES:

        if top_league.lower() in league_name.lower():

            league_weight = 1.25
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

    # RETENTION FACTOR
    if movement >= 20:

        retention = 0.6

    elif movement >= 15:

        retention = 0.5

    else:

        retention = 0.4

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

        response = requests.get(
            LEAGUES_URL,
            headers=HEADERS,
            timeout=30
        )

        print(
            f"STATUS LEAGUES: "
            f"{response.status_code}",
            flush=True
        )

        if response.status_code != 200:

            print(
                f"Resposta incorrecta: "
                f"{response.text[:500]}",
                flush=True
            )

            time.sleep(30)

            continue

        leagues = response.json()

        matchup_map = {}

        # ITERAR LEAGUES
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

                response = requests.get(
                    matchups_url,
                    headers=HEADERS,
                    timeout=30
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

                            # NOMÉS 2H PRE-KICKOFF
                            if (
                                hours_until_match < 0
                                or hours_until_match > 2
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

                        if "(Corners)" in match_name:
                            continue

                        matchup_map[matchup_id] = {
                            "match_name": match_name,
                            "league_name": league_name,
                            "hours_until_match": hours_until_match
                        }

                    except Exception as e:

                        print(
                            f"ERROR MATCHUP MAP: "
                            f"{e}",
                            flush=True
                        )

            except Exception as e:

                print(
                    f"ERROR LEAGUE: "
                    f"{e}",
                    flush=True
                )

        print(
            f"Matchups totals: "
            f"{len(matchup_map)}",
            flush=True
        )

        # ITERAR MATCHUPS
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

                response = requests.get(
                    market_url,
                    headers=HEADERS,
                    timeout=30
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

                        allowed_markets = [
                            "spread",
                            "total",
                            "team_total"
                        ]

                        if (
                            market_type
                            not in allowed_markets
                        ):
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

                            if side is None:
                                continue

                            american_price = (
                                price_data.get(
                                    "price"
                                )
                            )

                            if (
                                american_price
                                is None
                            ):
                                continue

                            points = price_data.get(
                                "points"
                            )

                            if (
                                points
                                not in VALID_POINTS
                            ):
                                continue

                            if (
                                market_type == "team_total"
                                and points
                                not in VALID_TEAM_TOTAL_POINTS
                            ):
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

                                # NOMÉS ODDS SHORTENING
                                if (
                                    movement >= 10
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
                                            "hours_until_match": hours_until_match
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

                                                print(
                                                    f"\n🔥 "
                                                    f"STEAM "
                                                    f"CONFIRMAT "
                                                    f"🔥\n"
                                                    f"🏆 {league_name}\n"
                                                    f"{key}\n"
                                                    f"Value Limit: "
                                                    f"{value_limit}\n",
                                                    flush=True
                                                )

                                                message = (
                                                    f"🔥 STEAM CONFIRMAT 🔥\n\n"
                                                    f"🏆 {league_name}\n"
                                                    f"⚽ {match_name}\n"
                                                    f"📈 {market_type}\n"
                                                    f"🎯 {side} "
                                                    f"{points}\n\n"
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

                                                last_alert = (
                                                    last_alerts.get(
                                                        key,
                                                        0
                                                    )
                                                )

                                                if (
                                                    current_time
                                                    - last_alert
                                                    > 900
                                                ):

                                                    send_telegram(
                                                        message
                                                    )

                                                    last_alerts[key] = (
                                                        current_time
                                                    )

                                            del pending_steam[key]

                            previous_odds[key] = (
                                decimal_odd
                            )

                    except Exception as e:

                        print(
                            f"ERROR MARKET: "
                            f"{e}",
                            flush=True
                        )

            except Exception as e:

                print(
                    f"ERROR MATCHUP: "
                    f"{e}",
                    flush=True
                )

    except Exception as e:

        print(
            f"ERROR API: {e}",
            flush=True
        )

    time.sleep(30)