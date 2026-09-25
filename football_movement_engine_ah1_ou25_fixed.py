import requests
import time
import os
import random
import csv
import math
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

CSV_FILE = "football_episodes_ah1.csv"

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
            "episode_id", "timestamp_start", "timestamp_end",
            "league", "match", "matchup_id", "market", "ah_line",
            "steam_side", "steam_points", "steam_start_odd", "steam_end_odd",
            "steam_movement_pct", "opposite_movement_pct", "opposite_side",
            "opposite_points", "opposite_start_odd", "opposite_end_odd",
            "steam_dominance_pct", "base_prob_pct", "observations",
            "duration_minutes", "hours_until_match_start", "movement_score",
            "persistence_score", "timing_score", "fvs_score"
        ])

def clamp(value, low=0.0, high=100.0):
    return max(low, min(high, value))


def timing_score(hours):
    # Neutral outside the preferred 2-8h window; peak near 5h.
    if hours is None:
        return 50.0
    h = float(hours)
    if 2.0 <= h <= 8.0:
        return 100.0
    if h < 2.0:
        return clamp(50.0 + (h / 2.0) * 50.0)
    if h <= 12.0:
        return clamp(100.0 - ((h - 8.0) / 4.0) * 50.0)
    return 50.0


def movement_score(movement_pct):
    # 12% movement is treated as the 100-point reference, capped.
    return clamp((movement_pct / 12.0) * 100.0)


def persistence_score(observations, duration_minutes):
    raw = math.log1p(max(0, observations)) * math.log1p(max(0.0, duration_minutes))
    return clamp((raw / 8.0) * 100.0)


def calculate_fvs(base_prob_pct, dominance_pct, movement_pct, observations, duration_minutes, hours):
    ps = persistence_score(observations, duration_minutes)
    ts = timing_score(hours)
    ms = movement_score(movement_pct)
    fvs = (
        0.30 * base_prob_pct
        + 0.25 * dominance_pct
        + 0.20 * ms
        + 0.15 * ps
        + 0.10 * ts
    )
    return ps, ts, ms, clamp(fvs)


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

    ps, ts, ms, fvs = calculate_fvs(
        ep.get("base_prob_pct", 50.0),
        ep.get("steam_dominance_pct", 50.0),
        movement_pct,
        ep.get("observations", 1),
        duration_minutes,
        hours_start,
    )

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
            ep["observations"],
            round(ep.get("base_prob_pct", 50.0), 2),
            round(ep.get("steam_dominance_pct", 50.0), 2),
            round(ms, 2),
            round(ps, 2),
            round(ts, 2),
            round(fvs, 2),
        ])

    completed_episodes += 1

    print(
        f"📌 EPISODI #{ep['episode_id']} | "
        f"{ep['league']} | {ep['match']} | "
        f"{ep['market']} {ep['side']} {ep['points']} | "
        f"{ep['start_odd']:.3f} → {ep['last_odd']:.3f} | "
        f"mov={movement_pct:.2f}% | FVS={fvs:.1f} | "
        f"Pbase={ep.get('base_prob_pct',50.0):.1f}% | "
        f"Dom={ep.get('steam_dominance_pct',50.0):.1f}% | "
        f"dur={duration_minutes:.1f}m | obs={ep['observations']}",
        flush=True
    )



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
    """Collect ONLY full-match Asian Handicap -1/+1 as a paired market.

    One episode represents the complete AH-1 pair:
        home -1  <->  away +1
    or
        home +1  <->  away -1

    Both sides are stored in the episode so STEAM dominance is based on
    the cumulative shortening of both prices, not on the existence of a
    shortening episode on only one side.
    """
    market_type = market.get("type")
    period = market.get("period")

    if period != 0:
        return

    if market_type != "spread":
        return

    if market.get("isAlternate", False):
        return

    prices = market.get("prices", [])

    # We need the exact whole AH-1 pair in the same market:
    # home -1 / away +1 OR home +1 / away -1.
    pair = {}
    for price_data in prices:
        side = price_data.get("designation")
        american_price = price_data.get("price")
        points = price_data.get("points")

        if side not in ("home", "away") or american_price is None:
            continue

        if points not in (-1.0, 1.0):
            continue

        odd = american_to_decimal(american_price)
        if odd is None:
            continue

        pair[(side, float(points))] = odd

    # Exact AH-1 pair only.
    if (
        ("home", -1.0) not in pair
        or ("away", 1.0) not in pair
    ) and (
        ("home", 1.0) not in pair
        or ("away", -1.0) not in pair
    ):
        return

    if ("home", -1.0) in pair:
        ah_key = "home_-1"
        steam_side = "home"
        steam_points = -1.0
        opp_side = "away"
        opp_points = 1.0
    else:
        ah_key = "away_-1"
        steam_side = "away"
        steam_points = -1.0
        opp_side = "home"
        opp_points = 1.0

    steam_odd = pair[(steam_side, steam_points)]
    opp_odd = pair[(opp_side, opp_points)]

    # Group key is the AH-1 pair, NOT the individual side.
    key = (matchup_id, "ah1", ah_key)

    previous = previous_odds.get(key)
    current_pair = (steam_odd, opp_odd)
    previous_odds[key] = current_pair

    if previous is None:
        return

    prev_steam, prev_opp = previous
    move_steam = (
        ((prev_steam - steam_odd) / prev_steam) * 100.0
        if steam_odd < prev_steam else 0.0
    )
    move_opp = (
        ((prev_opp - opp_odd) / prev_opp) * 100.0
        if opp_odd < prev_opp else 0.0
    )

    total_new_move = move_steam + move_opp
    if total_new_move <= 0:
        return

    if total_new_move > MAX_EPISODE_MOVEMENT:
        return

    if key not in episodes:
        # Normalized market probability at episode start.
        inv_steam = 1.0 / steam_odd
        inv_opp = 1.0 / opp_odd
        inv_total = inv_steam + inv_opp
        base_prob = (inv_steam / inv_total) * 100.0

        episodes[key] = {
            "episode_id": (
                f"{matchup_id}-ah1-{ah_key}-{int(now_ts)}"
            ),
            "start_time": now_ts,
            "last_update": now_ts,
            "league": match_info["league_name"],
            "match": match_info["match_name"],
            "matchup_id": matchup_id,
            "market": "spread",
            "ah_line": "AH-1",
            "steam_side": steam_side,
            "steam_points": steam_points,
            "opposite_side": opp_side,
            "opposite_points": opp_points,
            "steam_start_odd": steam_odd,
            "steam_last_odd": steam_odd,
            "opposite_start_odd": opp_odd,
            "opposite_last_odd": opp_odd,
            "cumulative_steam_move": 0.0,
            "cumulative_opposite_move": 0.0,
            "base_prob_pct": base_prob,
            "hours_until_match_start": match_info["hours_until_match"],
            "observations": 0,
        }

    ep = episodes[key]

    # Keep the same AH-1 orientation throughout the episode.
    # Accumulate every shortening observed on each side.
    ep["cumulative_steam_move"] += move_steam
    ep["cumulative_opposite_move"] += move_opp

    ep["steam_last_odd"] = steam_odd
    ep["opposite_last_odd"] = opp_odd
    ep["last_update"] = now_ts
    ep["observations"] += 1

def process_ou25_market(
    matchup_id,
    match_info,
    market,
    now_ts
):
    """Collect ONLY full-match Over/Under 2.5 as a paired market."""
    market_type = market.get("type")
    period = market.get("period")

    if period != 0 or market_type != "total":
        return

    if market.get("isAlternate", False):
        return

    prices = market.get("prices", [])

    pair = {}
    for price_data in prices:
        side = price_data.get("designation")
        american_price = price_data.get("price")
        points = price_data.get("points")

        if side not in ("over", "under") or american_price is None:
            continue

        try:
            points_f = float(points)
        except (TypeError, ValueError):
            continue

        if points_f != 2.5:
            continue

        odd = american_to_decimal(american_price)
        if odd is None:
            continue

        pair[side] = odd

    if "over" not in pair or "under" not in pair:
        return

    steam_side = "over"
    opp_side = "under"
    steam_odd = pair["over"]
    opp_odd = pair["under"]

    key = (matchup_id, "ou25")

    previous = previous_odds.get(key)
    current_pair = (steam_odd, opp_odd)
    previous_odds[key] = current_pair

    if previous is None:
        return

    prev_over, prev_under = previous
    move_over = (
        ((prev_over - steam_odd) / prev_over) * 100.0
        if steam_odd < prev_over else 0.0
    )
    move_under = (
        ((prev_under - opp_odd) / prev_under) * 100.0
        if opp_odd < prev_under else 0.0
    )

    total_new_move = move_over + move_under
    if total_new_move <= 0 or total_new_move > MAX_EPISODE_MOVEMENT:
        return

    if key not in episodes:
        inv_over = 1.0 / steam_odd
        inv_under = 1.0 / opp_odd
        inv_total = inv_over + inv_under

        episodes[key] = {
            "episode_id": f"{matchup_id}-ou25-{int(now_ts)}",
            "start_time": now_ts,
            "last_update": now_ts,
            "league": match_info["league_name"],
            "match": match_info["match_name"],
            "matchup_id": matchup_id,
            "market": "total",
            "ah_line": "OU-2.5",
            "steam_side": "over",
            "steam_points": 2.5,
            "opposite_side": "under",
            "opposite_points": 2.5,
            "steam_start_odd": steam_odd,
            "steam_last_odd": steam_odd,
            "opposite_start_odd": opp_odd,
            "opposite_last_odd": opp_odd,
            "cumulative_steam_move": 0.0,
            "cumulative_opposite_move": 0.0,
            "base_prob_pct": (inv_over / inv_total) * 100.0,
            "hours_until_match_start": match_info["hours_until_match"],
            "observations": 0,
        }

    ep = episodes[key]

    ep["cumulative_steam_move"] += move_over
    ep["cumulative_opposite_move"] += move_under
    ep["steam_last_odd"] = steam_odd
    ep["opposite_last_odd"] = opp_odd
    ep["last_update"] = now_ts
    ep["observations"] += 1


def finalize_stale_episodes(now_ts):
    stale_keys = []

    for key, ep in episodes.items():
        inactive_minutes = (now_ts - ep["last_update"]) / 60

        if inactive_minutes >= EPISODE_RESET_MINUTES:
            total_move = (
                ep["cumulative_steam_move"]
                + ep["cumulative_opposite_move"]
            )

            if total_move >= MIN_EPISODE_MOVEMENT:
                if ep["market"] == "spread":
                    # AH-1: the target is always the -1 side.
                    steam_move = ep["cumulative_steam_move"]
                    opp_move = ep["cumulative_opposite_move"]
                    dominance = (
                        (steam_move / total_move) * 100.0
                        if total_move > 0 else 50.0
                    )

                    selected_side = ep["steam_side"]
                    selected_points = ep["steam_points"]
                    selected_start = ep["steam_start_odd"]
                    selected_end = ep["steam_last_odd"]
                    selected_move = steam_move
                    selected_base = ep["base_prob_pct"]

                else:
                    # O/U 2.5: select whichever side accumulated more steam.
                    if ep["cumulative_steam_move"] >= ep["cumulative_opposite_move"]:
                        selected_side = ep["steam_side"]
                        selected_points = ep["steam_points"]
                        selected_start = ep["steam_start_odd"]
                        selected_end = ep["steam_last_odd"]
                        selected_move = ep["cumulative_steam_move"]
                        selected_base = ep["base_prob_pct"]
                        dominance = (
                            selected_move / total_move * 100.0
                            if total_move > 0 else 50.0
                        )
                    else:
                        selected_side = ep["opposite_side"]
                        selected_points = ep["opposite_points"]
                        selected_start = ep["opposite_start_odd"]
                        selected_end = ep["opposite_last_odd"]
                        selected_move = ep["cumulative_opposite_move"]
                        selected_base = 100.0 - ep["base_prob_pct"]
                        dominance = (
                            selected_move / total_move * 100.0
                            if total_move > 0 else 50.0
                        )

                duration = max(
                    0,
                    (ep["last_update"] - ep["start_time"]) / 60
                )

                movement_score = clamp((selected_move / 12.0) * 100.0)
                persistence_score = clamp(
                    (math.log1p(ep["observations"])
                     * math.log1p(duration) / 8.0) * 100.0
                )
                hours = ep["hours_until_match_start"]
                timing_value = timing_score_fn(hours)
                fvs = clamp(
                    0.30 * selected_base
                    + 0.25 * dominance
                    + 0.20 * movement_score
                    + 0.15 * persistence_score
                    + 0.10 * timing_value
                )

                write_market_episode(
                    ep,
                    selected_side,
                    selected_points,
                    selected_start,
                    selected_end,
                    selected_move,
                    dominance,
                    selected_base,
                    duration,
                    movement_score,
                    persistence_score,
                    timing_value,
                    fvs,
                )

            stale_keys.append(key)

    for key in stale_keys:
        episodes.pop(key, None)


def timing_score_fn(hours):
    if hours is None:
        return 50.0
    h = float(hours)
    if 2.0 <= h <= 8.0:
        return 100.0
    if h < 2.0:
        return clamp(50.0 + (h / 2.0) * 50.0)
    if h <= 12.0:
        return clamp(100.0 - ((h - 8.0) / 4.0) * 50.0)
    return 50.0


def write_market_episode(
    ep,
    selected_side,
    selected_points,
    selected_start,
    selected_end,
    selected_move,
    dominance,
    selected_base,
    duration,
    movement_score,
    persistence_score,
    timing_score_value,
    fvs,
):
    global completed_episodes

    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            ep["episode_id"],
            datetime.fromtimestamp(ep["start_time"], timezone.utc).isoformat(),
            datetime.fromtimestamp(ep["last_update"], timezone.utc).isoformat(),
            ep["league"],
            ep["match"],
            ep["matchup_id"],
            ep["market"],
            ep["ah_line"],
            selected_side,
            selected_points,
            round(selected_start, 3),
            round(selected_end, 3),
            round(selected_move, 3),
            round(ep["cumulative_opposite_move"], 3),
            ep["opposite_side"],
            ep["opposite_points"],
            round(ep["opposite_start_odd"], 3),
            round(ep["opposite_last_odd"], 3),
            round(dominance, 2),
            round(selected_base, 2),
            ep["observations"],
            round(duration, 2),
            round(ep["hours_until_match_start"], 2),
            round(movement_score, 2),
            round(persistence_score, 2),
            round(timing_score_value, 2),
            round(fvs, 2),
        ])

    completed_episodes += 1

    print(
        f"📌 {ep['ah_line']} #{ep['episode_id']} | {ep['league']} | {ep['match']} | "
        f"{selected_side} {selected_points:+.1f} | "
        f"{selected_start:.3f} → {selected_end:.3f} | "
        f"mov={selected_move:.2f}% | STEAM={dominance:.1f}% | "
        f"opp={ep['cumulative_opposite_move']:.2f}% | "
        f"FVS={fvs:.1f} | obs={ep['observations']}",
        flush=True,
    )

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

                process_ou25_market(
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
    "\n⚽ FOOTBALL MOVEMENT ENGINE AH-1 + O/U 2.5\n"
    "MODE: OBSERVATION / HISTORICAL COLLECTION\n"
    "NO BETS | NO VALUE | NO TELEGRAM | NO GOOGLE SHEETS\n"
    f"WINDOW: next {SCAN_HOURS}h | POLL: {POLL_SECONDS}s\n"
    f"MIN EPISODE MOVEMENT: {MIN_EPISODE_MOVEMENT}% "
    f"(observation filter only)\n"
    f"RESET AFTER: {EPISODE_RESET_MINUTES} min\n"
    f"MARKETS: AH-1 + O/U 2.5\n"
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
