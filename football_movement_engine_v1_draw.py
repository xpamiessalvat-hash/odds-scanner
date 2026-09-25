import requests
import time
import os
import random
import csv
from datetime import datetime, timezone

# ============================================================
# FOOTBALL MOVEMENT ENGINE V1
# Mode: OBSERVATION / HISTORICAL COLLECTION
# No Telegram, no Google Sheets, no betting, no VALUE decisions.
# ============================================================

BASE_URL = "https://guest.api.arcadia.pinnacle.com"
LEAGUES_URL = f"{BASE_URL}/0.1/sports/29/leagues"

# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------

SCAN_HOURS = 12
POLL_SECONDS = 120

# We collect only meaningful shortening movements.
# This is an observation filter, NOT a betting threshold.
MIN_EPISODE_MOVEMENT = 1.0       # %
EPISODE_RESET_MINUTES = 10       # close episode after inactivity
MAX_EPISODE_MOVEMENT = 30.0      # safety filter

VALID_SPREADS = [
    -2.5, -2.0, -1.5, -1.0, -0.5,
     0.0,  0.5,  1.0,  1.5,  2.0, 2.5
]

VALID_TOTALS = [1.5, 2.5, 3.5, 4.5]

BLOCKED_WORDS = [
    "Friendly", "Friendlies",
    "U17", "U18", "U19", "U20", "U21", "U23",
    "Youth", "Reserve", "Reserves",
    "Corners", "Esports", "Simulation",
    "Women", "3rd Division", "4. Liga",
    "Amateur", "Regional", "Kolmonen", "Kakkonen",
    "Division 1 Women", "NPL"
]

BLOCKED_MATCH_WORDS = [
    "(Corners)", "(Corner)",
    "(Bookings)", "(Booking)",
    "(Cards)", "(Card)",
    "(Throw-ins)", "(Throw In)",
    "(Offsides)", "(Offside)",
    "(Shots)", "(Shot)",
    "(Penalties)", "(Penalty)"
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/137.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.pinnacle.com",
    "Referer": "https://www.pinnacle.com/",
    "Connection": "keep-alive"
}

session = requests.Session()
session.headers.update(HEADERS)

# ------------------------------------------------------------
# STATE
# ------------------------------------------------------------

previous_odds = {}

# One active episode per market/side/line.
episodes = {}

# Number of completed episodes written to disk.
completed_episodes = 0

CSV_FILE = "football_episodes_draw.csv"

# ------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------

def american_to_decimal(price):
    if price is None:
        return None

    if price > 0:
        return round((price / 100) + 1, 3)

    return round((100 / abs(price)) + 1, 3)


def is_blocked_league(name):
    name = name or ""
    return any(word.lower() in name.lower() for word in BLOCKED_WORDS)


def is_blocked_match(match_name):
    name = match_name or ""
    return any(word.lower() in name.lower() for word in BLOCKED_MATCH_WORDS)


def ensure_csv():
    if os.path.exists(CSV_FILE):
        return

    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "episode_id",
            "timestamp_start",
            "timestamp_end",
            "league",
            "match",
            "matchup_id",
            "market",
            "side",
            "points",
            "start_odd",
            "end_odd",
            "movement_pct",
            "duration_minutes",
            "hours_until_match_start",
            "hours_until_match_end",
            "observations"
        ])


def write_episode(ep):
    global completed_episodes

    end_time = ep["last_update"]
    start_time = ep["start_time"]

    duration_minutes = max(
        0,
        (end_time - start_time) / 60
    )

    now = datetime.now(timezone.utc)

    hours_start = (
        ep["hours_until_match_start"]
    )

    # Recalculate approximate remaining time at episode end.
    elapsed_since_scan = max(0, (now.timestamp() - end_time) / 3600)
    hours_end = max(0, hours_start - elapsed_since_scan)

    movement_pct = (
        (ep["start_odd"] - ep["last_odd"])
        / ep["start_odd"]
    ) * 100

    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            ep["episode_id"],
            datetime.fromtimestamp(
                start_time, timezone.utc
            ).isoformat(),
            datetime.fromtimestamp(
                end_time, timezone.utc
            ).isoformat(),
            ep["league"],
            ep["match"],
            ep["matchup_id"],
            ep["market"],
            ep["side"],
            ep["points"],
            round(ep["start_odd"], 3),
            round(ep["last_odd"], 3),
            round(movement_pct, 3),
            round(duration_minutes, 2),
            round(hours_start, 2),
            round(hours_end, 2),
            ep["observations"]
        ])

    completed_episodes += 1

    print(
        f"📌 EPISODI #{ep['episode_id']} | "
        f"{ep['league']} | {ep['match']} | "
        f"{ep['market']} {ep['side']} {ep['points']} | "
        f"{ep['start_odd']:.3f} → {ep['last_odd']:.3f} | "
        f"{movement_pct:.2f}% | "
        f"{duration_minutes:.1f} min | "
        f"obs={ep['observations']}",
        flush=True
    )


def finalize_stale_episodes(now_ts):
    stale_keys = []

    for key, ep in episodes.items():
        inactive_minutes = (
            now_ts - ep["last_update"]
        ) / 60

        if inactive_minutes >= EPISODE_RESET_MINUTES:
            movement_pct = (
                (ep["start_odd"] - ep["last_odd"])
                / ep["start_odd"]
            ) * 100

            if movement_pct >= MIN_EPISODE_MOVEMENT:
                write_episode(ep)

            stale_keys.append(key)

    for key in stale_keys:
        episodes.pop(key, None)


def get_matchups():
    response = session.get(
        LEAGUES_URL,
        timeout=30
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"LEAGUES HTTP {response.status_code}: "
            f"{response.text[:200]}"
        )

    leagues = response.json()
    matchup_map = {}

    for league in leagues:
        try:
            league_id = league.get("id")
            league_name = league.get("name", "UNKNOWN")

            if not league_id or is_blocked_league(league_name):
                continue

            url = (
                f"{BASE_URL}/0.1/leagues/"
                f"{league_id}/matchups"
            )

            response = session.get(url, timeout=30)

            time.sleep(random.uniform(0.25, 0.7))

            if response.status_code != 200:
                continue

            matchups = response.json()

            for matchup in matchups:
                try:
                    matchup_id = matchup.get("id")
                    start_time = matchup.get("startTime")

                    if not matchup_id or not start_time:
                        continue

                    match_time = datetime.fromisoformat(
                        start_time.replace("Z", "+00:00")
                    )

                    now = datetime.now(timezone.utc)

                    hours_until_match = (
                        (match_time - now).total_seconds()
                        / 3600
                    )

                    if (
                        hours_until_match < 0
                        or hours_until_match > SCAN_HOURS
                    ):
                        continue

                    participants = matchup.get(
                        "participants", []
                    )

                    home_team = None
                    away_team = None

                    for participant in participants:
                        alignment = participant.get(
                            "alignment"
                        )
                        name = participant.get(
                            "name", "UNKNOWN"
                        )

                        if alignment == "home":
                            home_team = name
                        elif alignment == "away":
                            away_team = name

                    if not home_team or not away_team:
                        continue

                    match_name = (
                        f"{home_team} vs {away_team}"
                    )

                    if is_blocked_match(match_name):
                        continue

                    matchup_map[matchup_id] = {
                        "match_name": match_name,
                        "league_name": league_name,
                        "hours_until_match": hours_until_match
                    }

                except Exception:
                    continue

        except Exception:
            continue

    return matchup_map


def process_market(
    matchup_id,
    match_info,
    market,
    now_ts
):
    market_type = market.get("type")
    period = market.get("period")

    # IMPORTANT: only full-match markets. The related/straight endpoint
    # can return multiple periods (match, 1H, 2H, etc.). Without this
    # filter, a period-specific price can be incorrectly labelled as the
    # full-match market (e.g. Total Under 4.5).
    if period != 0:
        return

    if market_type not in ("moneyline", "spread", "total"):
        return

    if market.get("isAlternate", False):
        return

    prices = market.get("prices", [])

    for price_data in prices:
        try:
            side = price_data.get("designation")
            american_price = price_data.get("price")
            points = price_data.get("points")

            if american_price is None:
                continue

            if market_type == "moneyline":
                # 1X2 full-match market: home / draw / away.
                # No points field is used.
                if side not in ("home", "draw", "away"):
                    continue
                points = ""
            elif market_type == "spread":
                if points not in VALID_SPREADS:
                    continue
            else:
                if points not in VALID_TOTALS:
                    continue

            decimal_odd = american_to_decimal(
                american_price
            )

            if decimal_odd is None:
                continue

            key = (
                matchup_id,
                market_type,
                side,
                points
            )

            old_odd = previous_odds.get(key)
            previous_odds[key] = decimal_odd

            if old_odd is None:
                continue

            if decimal_odd >= old_odd:
                # No shortening. The active episode will be
                # closed by the inactivity mechanism.
                continue

            movement_pct = (
                (old_odd - decimal_odd)
                / old_odd
            ) * 100

            if movement_pct <= 0:
                continue

            if movement_pct > MAX_EPISODE_MOVEMENT:
                continue

            # Start a new episode if none is active.
            if key not in episodes:
                episodes[key] = {
                    "episode_id": (
                        f"{matchup_id}-"
                        f"{market_type}-"
                        f"{side}-{points}-"
                        f"{int(now_ts)}"
                    ),
                    "start_time": now_ts,
                    "last_update": now_ts,
                    "league": match_info["league_name"],
                    "match": match_info["match_name"],
                    "matchup_id": matchup_id,
                    "market": market_type,
                    "side": side,
                    "points": points,
                    "start_odd": old_odd,
                    "last_odd": decimal_odd,
                    "hours_until_match_start":
                        match_info["hours_until_match"],
                    "observations": 1
                }
                continue

            ep = episodes[key]

            # If a new movement starts from a lower current
            # price, extend the same episode.
            if decimal_odd < ep["last_odd"]:
                ep["last_odd"] = decimal_odd
                ep["last_update"] = now_ts
                ep["observations"] += 1

        except Exception:
            continue



def run_cycle():
    now_ts = time.time()

    matchup_map = get_matchups()

    cycle_movements = 0
    cycle_markets = 0

    for matchup_id, match_info in matchup_map.items():
        try:
            market_url = (
                f"{BASE_URL}/0.1/matchups/"
                f"{matchup_id}/markets/related/straight"
            )

            response = session.get(
                market_url,
                timeout=30
            )

            time.sleep(random.uniform(0.15, 0.45))

            if response.status_code != 200:
                continue

            markets = response.json()

            for market in markets:
                before = len(episodes)

                process_market(
                    matchup_id,
                    match_info,
                    market,
                    now_ts
                )

                after = len(episodes)

                cycle_markets += 1
                if after > before:
                    cycle_movements += 1

        except Exception:
            continue

    finalize_stale_episodes(now_ts)

    return (
        len(matchup_map),
        cycle_markets,
        cycle_movements,
        len(episodes)
    )


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------

print(
    "\n⚽ FOOTBALL MOVEMENT ENGINE V1 + MONEYLINE DRAW COLLECTION\n"
    "MODE: OBSERVATION / HISTORICAL COLLECTION\n"
    "NO BETS | NO VALUE | NO TELEGRAM | NO GOOGLE SHEETS\n"
    f"WINDOW: next {SCAN_HOURS}h | POLL: {POLL_SECONDS}s\n"
    f"MIN EPISODE MOVEMENT: {MIN_EPISODE_MOVEMENT}% "
    f"(observation filter only)\n"
    f"RESET AFTER: {EPISODE_RESET_MINUTES} min\n"
    f"CSV: {CSV_FILE}\n",
    flush=True
)

ensure_csv()

cycle = 0

while True:
    cycle += 1
    started = time.time()

    try:
        matches, markets, new_eps, active_eps = run_cycle()

        elapsed = time.time() - started

        print(
            f"💓 CYCLE {cycle} | "
            f"matches={matches} | "
            f"markets={markets} | "
            f"new_episodes={new_eps} | "
            f"active={active_eps} | "
            f"completed={completed_episodes} | "
            f"{elapsed:.1f}s",
            flush=True
        )

    except KeyboardInterrupt:
        print(
            "\n🛑 Scanner aturat per l'usuari.",
            flush=True
        )
        break

    except Exception as e:
        print(
            f"ERROR CYCLE: {e}",
            flush=True
        )

    time.sleep(POLL_SECONDS)
