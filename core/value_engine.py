from datetime import datetime, timezone

from core.odds import calculate_edge


def build_candidate(
    league,
    match,
    market,
    designation,
    points,
    steam_level,
    movement_pct,
    pinnacle_old,
    pinnacle_new,
    game_time
):

    return {

        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),

        "league": league,

        "match": match,

        "market": market,

        "designation": designation,

        "points": points,

        "steam_level": steam_level,

        "movement_pct": movement_pct,

        "pinnacle_old": pinnacle_old,

        "pinnacle_new": pinnacle_new,

        "game_time": game_time,

        "bet365_odd": None,

        "edge": None,

        "status": "NEW"

    }


def evaluate_edge(
    candidate,
    bet365_odd
):

    candidate["bet365_odd"] = bet365_odd

    candidate["edge"] = calculate_edge(
        candidate["pinnacle_new"],
        bet365_odd
    )

    return candidate


def is_value(
    candidate,
    minimum_edge
):

    return candidate["edge"] >= minimum_edge