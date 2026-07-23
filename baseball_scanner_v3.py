from core.snapshot_builder import (
    build_snapshot
)

from core.market_engine import (
    MarketEngine
)

import time
import json
import csv
import os
import urllib.request
import urllib.error
import traceback

class MarketAnalyzer:

    def __init__(self):

        self.min_movement = 3.0
        self.min_dominance = 70.0

    def analyze(self, snapshot):
        self._debug(
    f"ANALYZE -> {snapshot.match} | {snapshot.market} | {snapshot.period}"
)

        if len(snapshot["sides"]) != 2:
            return None

        side1 = snapshot["sides"][0]
        side2 = snapshot["sides"][1]

        if side1["movement"] >= side2["movement"]:
            winner = side1
            loser = side2
        else:
            winner = side2
            loser = side1

        total = (
            winner["movement"]
            + loser["movement"]
        )

        if total == 0:
            return None

        dominance = round(
            winner["movement"] / total * 100,
            1
        )

        if winner["movement"] < self.min_movement:
            return None

        if dominance < self.min_dominance:
            return None

        return {
            "winner": winner,
            "loser": loser,
            "dominance": dominance
        }
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

market_history = {}

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


def update_market_history(history, key, new_decimal):
    if key not in history:
        history[key] = []

    history[key].append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "value": new_decimal
    })

    return history[key]


def build_market_snapshot(
    matchup_id,
    data,
    market,
    prices,
    previous_odds
):

    snapshot = {
        "matchup_id": matchup_id,
        "match": data["match_name"],
        "league": data["league"],
        "market": market["type"],
        "period": market["period"],
        "points": prices[0].get("points", ""),
        "sides": []
    }

    for price in prices:

        designation = price.get("designation")
        american = price.get("price")
        points = price.get("points", "")

        key = (
            matchup_id,
            market["type"],
            designation,
            points
        )

        if key not in previous_odds:
            continue

        old_american = previous_odds[key]

        old_decimal = american_to_decimal(old_american)
        new_decimal = american_to_decimal(american)

        movement = round(
            abs(new_decimal - old_decimal)
            / old_decimal
            * 100,
            2
        )

        snapshot["sides"].append({
            "designation": designation,
            "points": points,
            "old_american": old_american,
            "new_american": american,
            "old_decimal": old_decimal,
            "new_decimal": new_decimal,
            "movement": movement,
            "key": key
        })

    return snapshot

def analyze_market(snapshot):

    sides = snapshot["sides"]

    if len(sides) != 2:
        return None

    side1 = sides[0]
    side2 = sides[1]

    diff = abs(
        side1["movement"] - side2["movement"]
    )

    # Si els dos costats es mouen gairebé igual,
    # no hi ha direcció clara.
    if diff < 2:
        return None

    if side1["movement"] > side2["movement"]:
        winner = side1
        loser = side2
    else:
        winner = side2
        loser = side1

    dominance = round(
        winner["movement"] / (
            winner["movement"] + loser["movement"]
        ) * 100,
        1
    )

    return {
        "winner": winner,
        "loser": loser,
        "dominance": dominance,
        "difference": diff,
        "snapshot": snapshot
    }

def generate_steam(analyzed_market):

    if analyzed_market is None:
        return None

    winner = analyzed_market["winner"]
    snapshot = analyzed_market["snapshot"]

    movement = winner["movement"]
    dominance = analyzed_market["dominance"]

    # Filtres mínims
    if movement < 3:
        return None

    if dominance < 70:
        return None

    steam_score = round(
        movement * 8 +
        (dominance - 50),
        1
    )

    steam_score = min(100, steam_score)

    if steam_score >= 90:
        strength = "ELITE"
    elif steam_score >= 75:
        strength = "HIGH"
    elif steam_score >= 60:
        strength = "MEDIUM"
    else:
        strength = "LOW"

    return {
        "matchup_id": snapshot["matchup_id"],
        "match": snapshot["match"],
        "league": snapshot["league"],
        "market": snapshot["market"],
        "points": snapshot["points"],
        "designation": winner["designation"],
        "old_decimal": winner["old_decimal"],
        "new_decimal": winner["new_decimal"],
        "movement": movement,
        "dominance": dominance,
        "steam_score": steam_score,
        "strength": strength
    }

def is_continuous_steam(history):

    if len(history) < 3:
        return True

    odds = [x["value"] for x in history]

    # Comprovem que la quota continua baixant
    decreasing = all(
        odds[i] >= odds[i + 1]
        for i in range(len(odds) - 1)
    )

    return decreasing
market_engine = MarketEngine()
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
            print(f"{data['match_name']} -> markets={len(markets)}", flush=True)
            valids = 0

            for market in markets:
                print(
                    f"Market: {market.get('type')} period={market.get('period')} prices={len(market.get('prices', []))}",
                    flush=True
                )
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

                print("ARRIBA A BUILD_SNAPSHOT", flush=True)
                snapshot = build_snapshot(
                    matchup_id,
                    data,
                    market,
                    prices,
                    previous_odds
                )

                if snapshot is None:
                    print("SNAPSHOT = NONE", flush=True)
                    continue

                signal = market_engine.analyze(
                    snapshot
                )

                if signal is None:
                    print(
                        f"SIGNAL NONE -> {data['match_name']} | {market['type']}",
                        flush=True
                    )
                    continue

                print(
                    f"SIGNAL -> "
                    f"{signal.selection} | "
                    f"Move={signal.movement:.2f}% | "
                    f"Dom={signal.dominance:.1f}% | "
                    f"Conf={signal.confidence:.1f}",
                    flush=True
                )


                for price in prices:
                    designation = price.get("designation")

                    if designation != signal.selection:
                        continue

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


                    if key in previous_odds:
                        old_odd = previous_odds[key]

                        if old_odd != american_odd:

                            new_decimal = american_to_decimal(american_odd)

                            history = update_market_history(
                                market_history,                              key,
                                new_decimal
                            )

                            if not is_continuous_steam(history):
                                continue

                            movement_pct = signal.movement
                            steam_score = signal.steam_score
                            strength = signal.strength

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
                                            strength
                                        ])

                                    last_steam[steam_key] = current_time

                                    open_steams[steam_key] = {
                                        "timestamp": datetime.now(timezone.utc).isoformat(),
                                        "match": data["match_name"],
                                        "market": market["type"],
                                        "designation": designation,
                                        "points": points,
                                        "steam_level": signal.strength,
                                        "steam_odd": american_odd
                                    }

                                    value_limit = calculate_value_limit(
                                        american_to_decimal(old_odd),
                                        american_to_decimal(american_odd),
                                        movement_pct
                                    )
                                    
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
                                        "steam_score": steam_score,
                                        "strength": strength
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

    finally:
        time.sleep(60)
