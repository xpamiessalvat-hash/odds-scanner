import requests
import time
from datetime import datetime, timezone

print("⚾ BASEBALL SCANNER V2 ⚾", flush=True)

previous_odds = {}
pending_steam = {}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/137.0.0.0 "
        "Safari/537.36"
    ),
    "Origin": "https://www.pinnacle.com",
    "Referer": "https://www.pinnacle.com/",
    "Accept": "application/json"
}

session = requests.Session()
session.headers.update(HEADERS)

ALLOWED_LEAGUES = {
    246
}

LEAGUES_URL = (
    "https://guest.api.arcadia.pinnacle.com"
    "/0.1/sports/3/leagues"
)

MARKETS_URL = (
    "https://guest.api.arcadia.pinnacle.com"
    "/0.1/matchups/{}/markets/related/straight"
)


def get_markets(matchup_id):

    url = MARKETS_URL.format(matchup_id)

    try:

        r = session.get(
            url,
            timeout=30
        )

        if r.status_code != 200:
            return []

        return r.json()

    except Exception as e:

        print(
            f"ERROR MARKETS: {e}",
            flush=True
        )

        return []


def get_matchups():

    matchup_map = {}

    response = session.get(
        LEAGUES_URL,
        timeout=30
    )

    print(
        f"STATUS LEAGUES: {response.status_code}",
        flush=True
    )

    if response.status_code != 200:
        return matchup_map

    leagues = response.json()
    print(
        f"LEAGUES TROBADES: {len(leagues)}",
        flush=True
    )

    for league in leagues:
        print(
            f"LEAGUE ID: {league.get('id')} - {league.get('name')}",
            flush=True
        )

        league_id = league.get("id")

        if league_id not in ALLOWED_LEAGUES:
            continue

        matchups_url = (
            "https://guest.api.arcadia.pinnacle.com"
            f"/0.1/leagues/{league_id}/matchups"
        )

        try:
            r = session.get(
                matchups_url,
                timeout=30
            )

            if r.status_code != 200:
                continue

            matchups = r.json()

            for matchup in matchups:
                if matchup.get("parentId"):
                    continue

                participants = matchup.get(
                    "participants",
                    []
                )

                home = None
                away = None

                for p in participants:
                    if p.get("alignment") == "home":
                        home = p.get("name")
                    elif p.get("alignment") == "away":
                        away = p.get("name")

                if not home or not away:
                    continue

                if "(" in home or "(" in away:
                    continue

                if "Games" in home or "Games" in away:
                    continue

                matchup_id = matchup.get("id")

                matchup_map[matchup_id] = {
                    "match_name": f"{home} vs {away}",
                    "league": league.get("name")
                }

        except Exception as e:
            print(
                f"ERROR MATCHUPS: {e}",
                flush=True
            )

    return matchup_map


while True:

    try:

        matchups = get_matchups()

        print(
            f"MATCHUPS: {len(matchups)}",
            flush=True
        )

        for matchup_id, data in matchups.items():

            markets = get_markets(matchup_id)

            valids = 0

            for market in markets:

                prices = market.get("prices", [])

                if len(prices) != 2:
                    continue

                if "designation" not in prices[0]:
                    continue

                if market.get("type") not in [
                    "moneyline",
                    "spread",
                    "total"
                ]:
                    continue

                if market.get("period") != 0:
                    continue

                if market.get("isAlternate", False):
                    continue

                valids += 1

                for price in prices:

                    designation = price.get(
                        "designation"
                    )

                    points = price.get(
                        "points"
                    )

                    american_odd = price.get(
                        "price"
                    )

                    key = (
                        matchup_id,
                        market["type"],
                        designation,
                        points
                    )

                    print(
                        f"KEY={key} EXISTEIX={key in previous_odds}",
                        flush=True
                    )

                    if key in previous_odds:
                        print(
                            f"COMPARANT: {key}",
                            flush=True
                        )
                        old_odd = previous_odds[key]

                        if old_odd != american_odd:
                            print(
                                f"MOVIMENT: "
                                f"{key} | "
                                f"{old_odd} -> "
                                f"{american_odd}",
                                flush=True
                            )

                    previous_odds[key] = american_odd

            print(
                f"{data['match_name']} -> {valids}",
                flush=True
            )

    except Exception as e:

        print(
            f"ERROR: {e}",
            flush=True
        )

    time.sleep(60)