import csv
import requests
import time
from datetime import datetime, timezone

print("⚾ BASEBALL SCANNER V2 ⚾", flush=True)

previous_odds = {}
last_steam = {}

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


def get_steam_level(movement_pct):
    """Return a simple steam level label for a given movement percentage."""
    try:
        pct = float(movement_pct)
    except Exception:
        return "unknown"

    if pct >= 10:
        return "high"
    if pct >= 5:
        return "medium"
    return "low"


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

                    if key in previous_odds:
                        old_odd = previous_odds[key]

                        if old_odd != american_odd:
                            old_decimal = american_to_decimal(
                                old_odd
                            )

                            new_decimal = american_to_decimal(
                                american_odd
                            )

                            movement_pct = round(
                                (
                                    abs(
                                        new_decimal - old_decimal
                                    )
                                    / old_decimal
                                ) * 100,
                                2
                            )

                            print(
                                f"MOVIMENT: "
                                f"{data['match_name']} | "
                                f"{market['type']} | "
                                f"{designation} | "
                                f"{points} | "
                                f"{old_odd} -> {american_odd} | "
                                f"{movement_pct}%",
                                flush=True
                            )

                            with open(
                                CSV_FILE,
                                "a",
                                newline="",
                                encoding="utf-8"
                            ) as file:

                                writer = csv.writer(
                                    file,
                                    delimiter=";"
                                )

                                writer.writerow([
                                    datetime.now(timezone.utc).isoformat(),
                                    data["match_name"],
                                    market["type"],
                                    designation,
                                    points,
                                    old_odd,
                                    american_odd,
                                    movement_pct
                                ])

                            if movement_pct >= 3:
                                steam_key = (
                                    matchup_id,
                                    market["type"],
                                    designation,
                                    points
                                )

                                current_time = time.time()

                                should_write_steam = True

                                if steam_key in last_steam:
                                    seconds_since = (
                                        current_time
                                        - last_steam[steam_key]
                                    )

                                    if seconds_since < 1800:
                                        should_write_steam = False

                                if should_write_steam:
                                    steam_level = get_steam_level(
                                        movement_pct
                                    )

                                    with open(
                                        STEAM_FILE,
                                        "a",
                                        newline="",
                                        encoding="utf-8"
                                    ) as file:

                                        writer = csv.writer(
                                            file,
                                            delimiter=";"
                                        )

                                        writer.writerow([
                                            datetime.now(timezone.utc).isoformat(),
                                            data["match_name"],
                                            market["type"],
                                            designation,
                                            points,
                                            old_odd,
                                            american_odd,
                                            movement_pct,
                                            steam_level
                                        ])

                                    last_steam[steam_key] = current_time

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