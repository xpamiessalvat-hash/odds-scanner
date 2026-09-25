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

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

CHAT_ID = os.getenv("CHAT_ID", "")

GOOGLE_SHEETS_WEBHOOK = os.getenv("GOOGLE_SHEETS_WEBHOOK", "")

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

MIN_MONEYLINE_STEAM = 7
MIN_SPREAD_STEAM = 6
MIN_TOTAL_STEAM = 5

# VALUE ENGINE V5 CORRECTED
VALUE_ENGINE_ENABLED = True
VALUE_MIN_EV = 0.05
VALUE_MIN_ODDS = 1.90
VALUE_MIN_HISTORY = 20
VALUE_ONE_BET_PER_MATCH = True
VALUE_PROFILES = {
    ("MLB", "total", "4-5", "70-80"): {"enabled": True, "wins": 25, "losses": 19, "pushes": 2, "min_steam_score": 4.0, "max_steam_score": 5.0, "min_strength": 70.0, "max_strength": 80.0},
    ("MLB", "spread", "3-4", "60-70"): {"enabled": False, "wins": 45, "losses": 46, "pushes": 0, "min_steam_score": 3.0, "max_steam_score": 4.0, "min_strength": 60.0, "max_strength": 70.0},
}

def value_check(league, market_type, steam_score, strength, decimal_odds):
    if not VALUE_ENGINE_ENABLED or decimal_odds is None: return None
    for (pl, pm, _, _), prof in VALUE_PROFILES.items():
        if not prof["enabled"] or league != pl or market_type != pm: continue
        if not (prof["min_steam_score"] <= steam_score < prof["max_steam_score"]): continue
        if not (prof["min_strength"] <= strength < prof["max_strength"]): continue
        n = prof["wins"] + prof["losses"] + prof["pushes"]
        if n < VALUE_MIN_HISTORY: return None
        p_model = (prof["wins"] + 1.0) / (prof["wins"] + prof["losses"] + 2.0)
        fair = 1.0 / p_model
        min_odds = max(fair * 1.05, VALUE_MIN_ODDS)
        ev = p_model * decimal_odds - 1.0
        return {"p_model": p_model, "fair_odds": fair, "min_odds": min_odds, "expected_value": ev, "is_value": decimal_odds >= min_odds and ev >= VALUE_MIN_EV, "profile_n": n}
    return None

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



def save_to_sheets(data):

    try:
        print(
            "ENTRANT A SAVE_TO_SHEETS",
            flush=True
        )

        print(
            data,
            flush=True
        )

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


def calculate_steam_score(movement, market_type, league_name, hours_until_match):
    return round(max(0.0, movement), 2)


def get_strength_label(score):
    return round(50.0 + (5.0 * score), 1)


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

                                                        if steam_score < 70:

                                                            del pending_steam[key]

                                                            continue

                                                        strength = (
                                                            get_strength_label(
                                                                steam_score
                                                            )
                                                        )

                                                        if strength < 60:

                                                            del pending_steam[key]

                                                            continue

                                                        value_limit = (
                                                            calculate_value_limit(
                                                                steam_data["old_odd"],
                                                                decimal_odd,
                                                                steam_data["movement"]
                                                            )
                                                        )

                                                        if market_type == "moneyline":

                                                            market_text = (
                                                                side
                                                                if side
                                                                else "moneyline"
                                                            )

                                                        else:

                                                            if side is None:

                                                                market_text = str(points)

                                                            else:

                                                                market_text = (
                                                                    f"{side} {points}"
                                                                )

                                                        value = value_check(league_name, market_type, steam_score, strength, decimal_odd)

                                                        if value is None:
                                                            print(f"NO BET | {league_name} | {market_type} | Score={steam_score:.2f} | Strength={strength:.1f}", flush=True)
                                                            del pending_steam[key]
                                                            previous_odds[key] = decimal_odd
                                                            continue

                                                        if not value["is_value"]:
                                                            print(f"NO BET VALUE | odds={decimal_odd:.3f} | fair={value['fair_odds']:.3f} | min={value['min_odds']:.3f} | EV={value['expected_value']:.2%}", flush=True)
                                                            del pending_steam[key]
                                                            previous_odds[key] = decimal_odd
                                                            continue

                                                        alert_key = (matchup_id, market_type, side, points)
                                                        if VALUE_ONE_BET_PER_MATCH and alert_key in last_alerts:
                                                            print(f"SKIP DUPLICATE | {match_name} | {market_type}", flush=True)
                                                            del pending_steam[key]
                                                            previous_odds[key] = decimal_odd
                                                            continue

                                                        message = (
                                                            f"⚾🔥 BASEBALL STEAM VALUE 🔥⚾\n\n"
                                                            f"🏆 {league_name}\n"
                                                            f"⚽ {match_name}\n"
                                                            f"📈 {market_type}\n"
                                                            f"🎯 {market_text}\n\n"
                                                            f"💰 Odds: {decimal_odd:.3f}\n"
                                                            f"📊 Steam Score: {steam_score:.2f}\n"
                                                            f"🔥 Strength: {strength:.1f}\n"
                                                            f"🎯 P_model: {value['p_model']:.2%}\n"
                                                            f"📐 Fair odds: {value['fair_odds']:.3f}\n"
                                                            f"🚦 Min odds: {value['min_odds']:.3f}\n"
                                                            f"💎 EV: {value['expected_value']:.2%}\n"
                                                            f"🕒 Kickoff: {hours_until_match:.1f}h"
                                                        )

                                                        save_to_sheets({
                                                            "league": league_name, "match": match_name, "market": market_type, "selection": market_text,
                                                            "entry_odds": decimal_odd, "value_limit": value["min_odds"],
                                                            "steam_percent": round(steam_data["movement"], 2), "steam_score": steam_score, "strength": strength,
                                                            "kickoff_hours": round(hours_until_match, 1), "matchup_id": matchup_id, "market_type": market_type,
                                                            "points": points, "side": side, "p_model": value["p_model"], "fair_odds": value["fair_odds"],
                                                            "min_odds_5pct": value["min_odds"], "expected_value": value["expected_value"], "value_5pct": True,
                                                            "value_profile_n": value["profile_n"]
                                                        })

                                                        send_telegram(message)
                                                        last_alerts[alert_key] = current_time
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
