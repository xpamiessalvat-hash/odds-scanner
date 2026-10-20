"""
NHL Pinnacle snapshot collector — paper mode only.

Collects NHL full-game main markets from Pinnacle and appends normalized
prices to CSV. No bet placement, no value picks, no external API calls.

Markets:
- Moneyline
- Puck line +/-1.5
- Full-game totals (over/under pair at the selected main line)

Environment:
- PINNACLE_X_API_KEY (required)
- POLL_SECONDS (default 120)
- LOOKAHEAD_HOURS (default 24)
- DATA_DIR (default current directory)
"""

import csv
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

BASE_URL = "https://guest.api.arcadia.pinnacle.com/0.1"
NHL_LEAGUE_ID = 1456
POLL_SECONDS = max(30, int(os.getenv("POLL_SECONDS", "120")))
LOOKAHEAD_HOURS = max(1, int(os.getenv("LOOKAHEAD_HOURS", "24")))
OUTPUT_DIR = Path(os.getenv("DATA_DIR", "."))
OUTPUT_FILE = OUTPUT_DIR / "nhl_snapshots.csv"
REUS_TZ = ZoneInfo("Europe/Madrid")

SESSION = requests.Session()
SESSION.headers.update({"Accept": "application/json"})

KEY = os.getenv("PINNACLE_X_API_KEY", "").strip()
if KEY:
    SESSION.headers["X-API-Key"] = KEY

# Current NHL franchises. Names must match the participant names returned by
# Pinnacle; unknown names are deliberately excluded rather than treated as games.
NHL_TEAMS = {
    "Anaheim Ducks",
    "Boston Bruins",
    "Buffalo Sabres",
    "Calgary Flames",
    "Carolina Hurricanes",
    "Chicago Blackhawks",
    "Colorado Avalanche",
    "Columbus Blue Jackets",
    "Dallas Stars",
    "Detroit Red Wings",
    "Edmonton Oilers",
    "Florida Panthers",
    "Los Angeles Kings",
    "Minnesota Wild",
    "Montreal Canadiens",
    "Nashville Predators",
    "New Jersey Devils",
    "New York Islanders",
    "New York Rangers",
    "Ottawa Senators",
    "Philadelphia Flyers",
    "Pittsburgh Penguins",
    "San Jose Sharks",
    "Seattle Kraken",
    "St. Louis Blues",
    "Tampa Bay Lightning",
    "Toronto Maple Leafs",
    "Utah Mammoth",
    "Vancouver Canucks",
    "Vegas Golden Knights",
    "Washington Capitals",
    "Winnipeg Jets",
}

FIELDS = [
    "timestamp_utc",
    "timestamp_reus",
    "source",
    "league_id",
    "matchup_id",
    "start_utc",
    "start_reus",
    "away",
    "home",
    "market",
    "period",
    "side",
    "line",
    "american_price",
    "decimal_odds",
]


def american_to_decimal(price):
    """Convert American odds to decimal odds."""
    if price is None:
        return None
    try:
        price = float(price)
    except (TypeError, ValueError):
        return None

    if price > 0:
        return round(1 + price / 100, 4)
    if price < 0:
        return round(1 + 100 / abs(price), 4)
    return None


def implied_probability_from_american(price):
    """Return raw implied probability, including margin, from American odds."""
    try:
        price = float(price)
    except (TypeError, ValueError):
        return None
    if price > 0:
        return 100.0 / (price + 100.0)
    if price < 0:
        return abs(price) / (abs(price) + 100.0)
    return None


def get_json(path):
    response = SESSION.get(f"{BASE_URL}{path}", timeout=25)
    response.raise_for_status()
    return response.json()


def iso_dt(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (TypeError, ValueError, AttributeError):
        return None


def participant_name(participants, alignment):
    for participant in participants:
        if participant.get("alignment") == alignment:
            return participant.get("name")
    return None


def open_matchups():
    """Return upcoming open NHL matchups with recognized teams only."""
    payload = get_json(f"/leagues/{NHL_LEAGUE_ID}/matchups")
    now = datetime.now(timezone.utc)
    end = now + timedelta(hours=LOOKAHEAD_HOURS)
    result = {}

    if not isinstance(payload, list):
        raise ValueError("Pinnacle matchups response is not a list")

    for item in payload:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "matchup" or item.get("id") is None:
            continue

        periods = item.get("periods") or []
        main_period = next(
            (period for period in periods if period.get("period") == 0),
            None,
        )
        if not main_period or main_period.get("status") != "open":
            continue

        start = iso_dt(item.get("startTime"))
        if not start or not (now <= start <= end):
            continue

        participants = item.get("participants") or []
        away = participant_name(participants, "away")
        home = participant_name(participants, "home")

        # Reject aggregate/event markets and unknown participant labels.
        if away not in NHL_TEAMS or home not in NHL_TEAMS or away == home:
            continue

        result[str(item["id"])] = {
            "matchup_id": str(item["id"]),
            "start_utc": start.astimezone(timezone.utc).isoformat(),
            "start_reus": start.astimezone(REUS_TZ).isoformat(),
            "away": away,
            "home": home,
        }

    return result


def get_market_type(market):
    return (market.get("type") or "").strip().lower().replace("-", "_")


def is_main_market(market):
    """Accept full-game, non-alternate markets only."""
    if market.get("period") != 0:
        return False
    if market.get("isAlternate") is True:
        return False
    return True


def price_side(price):
    return (price.get("designation") or "").strip().lower()


def numeric_points(price):
    try:
        value = price.get("points")
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def select_main_total_pair(prices):
    """
    Select a complete over/under total pair.

    Pinnacle's payload can contain multiple points values. Alternate markets
    are filtered by isAlternate at market level above. If multiple complete
    lines remain, select the pair whose raw implied probabilities are closest
    to 50/50 after normalizing the two sides. This is a defensive fallback,
    not a guarantee of Pinnacle's official main-line designation.
    """
    pairs = {}
    for price in prices:
        points = numeric_points(price)
        side = price_side(price)
        if points is None or side not in {"over", "under"}:
            continue
        pairs.setdefault(points, {})[side] = price

    complete = []
    for line, sides in pairs.items():
        if "over" not in sides or "under" not in sides:
            continue

        over_prob = implied_probability_from_american(sides["over"].get("price"))
        under_prob = implied_probability_from_american(sides["under"].get("price"))
        if over_prob is None or under_prob is None or over_prob + under_prob <= 0:
            continue

        normalized_over = over_prob / (over_prob + under_prob)
        # A main total line is often near a balanced normalized price.
        balance_distance = abs(normalized_over - 0.5)
        complete.append((balance_distance, line, sides))

    if not complete:
        return None

    complete.sort(key=lambda item: (item[0], item[1]))
    _, line, sides = complete[0]
    return line, sides


def market_rows(matchups):
    """Build normalized snapshot rows for the selected main markets."""
    payload = get_json(f"/leagues/{NHL_LEAGUE_ID}/markets/straight")
    now = datetime.now(timezone.utc)
    timestamp_utc = now.isoformat()
    timestamp_reus = now.astimezone(REUS_TZ).isoformat()
    rows = []

    if not isinstance(payload, list):
        raise ValueError("Pinnacle markets response is not a list")

    for market in payload:
        if not isinstance(market, dict) or not is_main_market(market):
            continue

        matchup_id = str(market.get("matchupId", market.get("matchup_id", "")))
        matchup = matchups.get(matchup_id)
        if not matchup:
            continue

        market_type = get_market_type(market)
        if market_type in {"moneyline", "money_line", "money line"}:
            normalized_market = "moneyline"
        elif market_type in {"spread", "puckline", "puck_line"}:
            normalized_market = "puckline"
        elif market_type == "total":
            normalized_market = "total"
        else:
            continue

        prices = market.get("prices") or []
        if not prices:
            continue

        if normalized_market == "puckline":
            filtered = []
            for price in prices:
                points = numeric_points(price)
                if points is not None and abs(points) == 1.5:
                    filtered.append(price)
            prices = filtered
            if not prices:
                continue

        if normalized_market == "total":
            selected = select_main_total_pair(prices)
            if not selected:
                continue
            line, sides = selected
            prices = [
                dict(sides["over"], designation="over", points=line),
                dict(sides["under"], designation="under", points=line),
            ]

        for price in prices:
            side = price_side(price)
            american = price.get("price")
            decimal = american_to_decimal(american)
            if decimal is None:
                continue

            if normalized_market == "moneyline":
                if side not in {"home", "away"}:
                    continue
                line = ""
            elif normalized_market == "puckline":
                if side not in {"home", "away"}:
                    continue
                line = numeric_points(price)
                if line is None or abs(line) != 1.5:
                    continue
            else:
                if side not in {"over", "under"}:
                    continue
                line = numeric_points(price)
                if line is None:
                    continue

            rows.append(
                {
                    "timestamp_utc": timestamp_utc,
                    "timestamp_reus": timestamp_reus,
                    "source": "pinnacle",
                    "league_id": NHL_LEAGUE_ID,
                    **matchup,
                    "market": normalized_market,
                    "period": 0,
                    "side": side,
                    "line": line,
                    "american_price": american,
                    "decimal_odds": decimal,
                }
            )

    return rows


def append_rows(rows):
    """Append snapshots to the existing CSV without deleting historical rows."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    new_file = not OUTPUT_FILE.exists() or OUTPUT_FILE.stat().st_size == 0

    with OUTPUT_FILE.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerows(rows)


def existing_data_rows():
    """Count existing CSV data rows, excluding the header."""
    if not OUTPUT_FILE.exists() or OUTPUT_FILE.stat().st_size == 0:
        return 0
    with OUTPUT_FILE.open("r", newline="", encoding="utf-8") as handle:
        return max(0, sum(1 for _ in handle) - 1)


def main():
    if not KEY:
        raise SystemExit("ERROR: PINNACLE_X_API_KEY no configurada")

    print("NHL PINNACLE SNAPSHOT COLLECTOR | PAPER MODE | NO BETS", flush=True)
    print(
        f"Lliga={NHL_LEAGUE_ID} | interval={POLL_SECONDS}s "
        f"| horitzó={LOOKAHEAD_HOURS}h | dades={OUTPUT_FILE}",
        flush=True,
    )

    while True:
        try:
            matchups = open_matchups()
            rows = market_rows(matchups)
            append_rows(rows)
            total_rows = existing_data_rows()
            print(
                f"{datetime.now(REUS_TZ).isoformat(timespec='seconds')} "
                f"| partits_validats={len(matchups)} "
                f"| registres_cicle={len(rows)} "
                f"| registres_acumulats={total_rows}",
                flush=True,
            )
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            print(f"ERROR HTTP Pinnacle: {status}", flush=True)
        except (requests.RequestException, ValueError, KeyError) as exc:
            print(f"ERROR de captura: {type(exc).__name__}: {exc}", flush=True)
        except Exception as exc:
            print(f"ERROR inesperat: {type(exc).__name__}: {exc}", flush=True)

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()

