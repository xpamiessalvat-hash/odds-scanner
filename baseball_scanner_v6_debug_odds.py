import requests
import time
from datetime import datetime, timezone

LEAGUES_URL = "https://guest.api.arcadia.pinnacle.com/0.1/sports/3/leagues"
MLB_ID = 246

ACTIVE_MARKET = "total"
ACTIVE_SELECTION = "over"

STEAM_SCORE_MIN = 4.0
STEAM_SCORE_MAX = 5.0
STRENGTH_MIN = 70.0
STRENGTH_MAX = 80.0

MODEL_PROBABILITY = 0.55
MIN_VALUE_EDGE = 0.05
MIN_VALUE_ODDS = round((1.0 + MIN_VALUE_EDGE) / MODEL_PROBABILITY, 3)

STEAM_CONFIRMATION_SECONDS = 60
POLL_SECONDS = 5
DEBUG_MIN_MOVEMENT = 0.05

VALID_TOTALS = [
    6.5, 7.0, 7.5, 8.0, 8.5, 9.0, 9.5, 10.0,
    10.5, 11.0, 11.5, 12.0
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
    "Connection": "keep-alive",
}

session = requests.Session()
session.headers.update(HEADERS)

previous_odds = {}
pending_steam = {}


def american_to_decimal(price):
    if price is None:
        return None
    price = float(price)
    if price > 0:
        return round((price / 100.0) + 1.0, 4)
    return round((100.0 / abs(price)) + 1.0, 4)


def steam_score(movement):
    return round(float(movement), 2)


def strength_from_steam(score):
    return round(50.0 + 5.0 * float(score), 1)


def value_edge(decimal_odds):
    if decimal_odds is None:
        return None
    return round(MODEL_PROBABILITY * decimal_odds - 1.0, 4)


def get_open_mlb_matchups():
    url = f"https://guest.api.arcadia.pinnacle.com/0.1/leagues/{MLB_ID}/matchups"
    response = session.get(url, timeout=30)
    response.raise_for_status()

    result = []

    for m in response.json():
        if m.get("type") != "matchup":
            continue

        periods = m.get("periods", [])
        p0 = next((p for p in periods if p.get("period") == 0), None)

        if not p0 or not p0.get("hasTotal") or p0.get("status") != "open":
            continue

        start = m.get("startTime")
        if not start:
            continue

        try:
            dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            hours = (dt - datetime.now(timezone.utc)).total_seconds() / 3600
            if hours < 0 or hours > 24:
                continue
        except Exception:
            continue

        away = next(
            (p.get("name") for p in m.get("participants", [])
             if p.get("alignment") == "away"),
            "AWAY"
        )
        home = next(
            (p.get("name") for p in m.get("participants", [])
             if p.get("alignment") == "home"),
            "HOME"
        )

        result.append({
            "id": m.get("id"),
            "match": f"{away} @ {home}",
            "start": start,
            "hours": hours,
        })

    return result


def get_main_total(matchup):
    matchup_id = matchup["id"]
    url = (
        "https://guest.api.arcadia.pinnacle.com"
        f"/0.1/matchups/{matchup_id}/markets/related/straight"
    )

    response = session.get(url, timeout=30)
    response.raise_for_status()

    # Only the primary Total: period 0, non-alternate.
    for market in response.json():
        if market.get("type") != "total":
            continue
        if market.get("period") != 0:
            continue
        if market.get("isAlternate") is True:
            continue

        prices = market.get("prices", [])
        for p in prices:
            side = (p.get("designation") or "").lower()
            if side not in ("over", "under"):
                continue

            points = p.get("points")
            if points not in VALID_TOTALS:
                continue

            american = p.get("price")
            decimal = american_to_decimal(american)

            yield {
                "matchup_id": matchup_id,
                "match": matchup["match"],
                "start": matchup["start"],
                "hours": matchup["hours"],
                "market": "total",
                "side": side,
                "points": points,
                "american": american,
                "decimal": decimal,
            }


def process_snapshot(snapshot):
    key = (
        snapshot["matchup_id"],
        snapshot["market"],
        snapshot["side"],
        snapshot["points"],
    )

    new_odd = snapshot["decimal"]
    if new_odd is None:
        return

    now = time.time()

    if key not in previous_odds:
        previous_odds[key] = new_odd
        print(
            f"  INIT | {snapshot['match']} | "
            f"{snapshot['side'].upper()} {snapshot['points']} | "
            f"{new_odd}",
            flush=True
        )
        return

    old_odd = previous_odds[key]

    if old_odd == new_odd:
        return

    # In this scanner, shortening odds means steam:
    # OLD decimal > NEW decimal.
    movement = ((old_odd - new_odd) / old_odd) * 100.0

    print(
        f"  MOVE | {snapshot['match']} | "
        f"{snapshot['side'].upper()} {snapshot['points']} | "
        f"{old_odd} -> {new_odd} | "
        f"movement={movement:.2f}%",
        flush=True
    )

    # Always update the current market snapshot.
    previous_odds[key] = new_odd

    if movement < STEAM_SCORE_MIN or movement > 25:
        pending_steam.pop(key, None)
        return

    if snapshot["side"] != ACTIVE_SELECTION:
        return

    score = steam_score(movement)
    strength = strength_from_steam(score)

    if not (STEAM_SCORE_MIN <= score < STEAM_SCORE_MAX):
        return

    if not (STRENGTH_MIN <= strength < STRENGTH_MAX):
        return

    pending_steam[key] = {
        "timestamp": now,
        "old_odd": old_odd,
        "new_odd": new_odd,
        "score": score,
        "strength": strength,
        "snapshot": snapshot,
    }

    print(
        f"  ⏳ CANDIDAT STEAM | {snapshot['match']} | "
        f"OVER {snapshot['points']} | "
        f"Steam={score:.2f}% | Strength={strength:.1f} | "
        f"confirmació={STEAM_CONFIRMATION_SECONDS}s",
        flush=True
    )


def check_confirmations():
    now = time.time()

    for key in list(pending_steam.keys()):
        data = pending_steam[key]
        elapsed = now - data["timestamp"]
        snapshot = data["snapshot"]

        if elapsed < STEAM_CONFIRMATION_SECONDS:
            continue

        current = previous_odds.get(key)
        if current is None:
            del pending_steam[key]
            continue

        # Confirmation requires the current price not to have drifted
        # back above the post-move price.
        if current > data["new_odd"]:
            print(
                f"  ❌ CANCEL·LAT | {snapshot['match']} | "
                f"OVER {snapshot['points']} | quota ha rebotat",
                flush=True
            )
            del pending_steam[key]
            continue

        edge = value_edge(current)
        value_status = edge >= MIN_VALUE_EDGE

        print("", flush=True)
        print("  " + "=" * 76, flush=True)
        print("  🎯 STEAM CONFIRMAT", flush=True)
        print(f"  Match:       {snapshot['match']}", flush=True)
        print(f"  Market:      TOTAL", flush=True)
        print(f"  Selection:   OVER {snapshot['points']}", flush=True)
        print(f"  Old odds:    {data['old_odd']}", flush=True)
        print(f"  New odds:    {current}", flush=True)
        print(f"  Steam %:     {data['score']:.2f}%", flush=True)
        print(f"  Steam Score: {data['score']:.2f}", flush=True)
        print(f"  Strength:    {data['strength']:.1f}", flush=True)
        print(f"  Model P:     {MODEL_PROBABILITY:.2%}", flush=True)
        print(f"  Fair odds:   {1.0 / MODEL_PROBABILITY:.3f}", flush=True)
        print(f"  Min VALUE:   {MIN_VALUE_ODDS}", flush=True)
        print(f"  Current:     {current}", flush=True)
        print(f"  VALUE edge:  {edge:.2%}", flush=True)
        print(f"  RESULT:      {'VALUE' if value_status else 'NO BET'}", flush=True)
        print("  " + "=" * 76, flush=True)
        print("", flush=True)

        del pending_steam[key]


print("⚾ BASEBALL STEAM V6 - LIVE STEAM TEST ⚾", flush=True)
print("PROFILE: MLB / TOTAL / OVER / STEAM 4-5 / STRENGTH 70-80", flush=True)
print(
    f"VALUE: P={MODEL_PROBABILITY:.2%} | "
    f"MIN EDGE={MIN_VALUE_EDGE:.2%} | MIN ODDS={MIN_VALUE_ODDS}",
    flush=True
)
print(
    f"CONFIRMATION={STEAM_CONFIRMATION_SECONDS}s | POLL={POLL_SECONDS}s",
    flush=True
)
print("NO TELEGRAM / NO GOOGLE SHEETS", flush=True)
print("", flush=True)

cycle = 0

while True:
    cycle += 1
    print(
        f"\n{'=' * 90}\n"
        f"🔄 CICLE {cycle} | {datetime.now().strftime('%H:%M:%S')}\n"
        f"{'=' * 90}",
        flush=True
    )

    try:
        matchups = get_open_mlb_matchups()
        print(f"MLB matchups oberts amb Total: {len(matchups)}", flush=True)

        for matchup in matchups:
            try:
                snapshots = list(get_main_total(matchup))

                # Print the primary market once per cycle.
                if snapshots:
                    over = next((x for x in snapshots if x["side"] == "over"), None)
                    under = next((x for x in snapshots if x["side"] == "under"), None)

                    if over:
                        print(
                            f"  {matchup['match']} | "
                            f"TOTAL {over['points']} | "
                            f"OVER {over['american']} ({over['decimal']}) | "
                            f"UNDER "
                            f"{under['american']} ({under['decimal']})"
                            if under else
                            f"  {matchup['match']} | "
                            f"TOTAL {over['points']} | "
                            f"OVER {over['american']} ({over['decimal']})",
                            flush=True
                        )

                for snapshot in snapshots:
                    process_snapshot(snapshot)

            except Exception as e:
                print(
                    f"ERROR MARKET {matchup.get('id')}: "
                    f"{type(e).__name__}: {e}",
                    flush=True
                )

        check_confirmations()

    except KeyboardInterrupt:
        print("\nInterromput per l'usuari.", flush=True)
        break

    except Exception as e:
        print(
            f"ERROR CICLE: {type(e).__name__}: {e}",
            flush=True
        )

    time.sleep(POLL_SECONDS)
