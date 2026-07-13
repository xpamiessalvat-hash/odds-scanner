import time
import json
import csv
import os
import urllib.request
import urllib.error
import traceback

from datetime import datetime, timezone

from core.utils import (
    american_to_decimal,
    calculate_value_limit,
    calculate_baseball_steam_score,
    get_steam_level
)

from core.config import (
    CSV_FILE,
    STEAM_FILE,
    CLV_FILE,
    BOT_TOKEN,
    CHAT_ID,
    BASE_URL
)
from core.telegram import send_telegram
from core.sheets import save_to_sheets
import requests

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

previous_odds = {}
open_steams = {}
last_steam = {}

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

    if response.status_code == 401:
        print(
            "PINNACLE BLOCK TEMPORAL - ESPERANT 5 MINUTS",
            flush=True
        )

        time.sleep(300)

        return matchup_map

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

                start_time = matchup.get("startTime")

                matchup_map[matchup_id] = {
                    "match_name": f"{home} vs {away}",
                    "league": league.get("name"),
                    "start_time": start_time
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

        market_leaders = {}

        for matchup_id, data in matchups.items():
            start_time = datetime.fromisoformat(
                data["start_time"].replace("Z", "+00:00")
            )

            hours_until_match = (
                start_time - datetime.now(timezone.utc)
            ).total_seconds() / 3600
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
                        "points",
                        ""
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

                    key_data = {
                        "match": data["match_name"],
                        "market": market["type"],
                        "designation": designation,
                        "points": points
                    }

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

                            market_key = (
                                matchup_id,
                                market["type"],
                                points
                            )

                            if (
                                market_key not in market_leaders
                                or movement_pct > market_leaders[market_key]["movement"]
                            ):

                                market_leaders[market_key] = {
                                    "designation": designation,
                                    "movement": movement_pct
                                }

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

                                    market_key = (
                                        matchup_id,
                                        market["type"],
                                        points
                                    )

                                    leader = market_leaders.get(market_key)

                                    if leader is not None:

                                        if leader["designation"] != designation:

                                            continue

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

                                    open_steams[steam_key] = {
                                        "timestamp": datetime.now(timezone.utc).isoformat(),
                                        "match": data["match_name"],
                                        "market": market["type"],
                                        "designation": designation,
                                        "points": points,
                                        "steam_level": steam_level,
                                        "steam_odd": american_odd
                                    }

                                    value_limit = calculate_value_limit(
                                        american_to_decimal(old_odd),
                                        american_to_decimal(american_odd),
                                        movement_pct
                                    )

                                    steam_score = steam_level

                                    strength = steam_level

                                    message = (
    f"⚾ STEAM DETECTAT ⚾\n\n"
    f"🏟️ {data['match_name']}\n"
    f"📈 {market['type']}\n"
    f"🎯 {designation} {points}\n\n"
    f"💰 {american_to_decimal(old_odd):.3f} → {american_to_decimal(american_odd):.3f}\n\n"
    f"✅ VALUE FINS:\n"
    f"{value_limit:.3f}\n\n"
    f"📊 Moviment: {movement_pct:.2f}%\n"
    f"⭐ Score: {steam_score:.1f}/100\n"
    f"🔥 Strength: {strength}\n"
    f"🕒 Kickoff: {hours_until_match:.1f}h"
)

                                    save_to_sheets({
                                        "league": data["league"],
                                        "match": data["match_name"],
                                        "market": market["type"],
                                        "selection": f"{designation} {points}",
                                        "entry_odds": american_odd,
                                        "steam_percent": movement_pct,
                                        "steam_score": steam_level,
                                        "strength": steam_level
                                    })
                                    send_telegram(message)

                                    print("SHEETS ENVIAT", flush=True)

                                    print("TELEGRAM ENVIAT", flush=True)

                                    print(
                                        f"STEAM DETECTAT | Actius: {len(open_steams)}",
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
