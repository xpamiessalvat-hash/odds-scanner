"""
NHL Pinnacle snapshot collector — paper mode only.

Polls NHL main markets and appends normalized prices to CSV.
No bet placement, no value picks, no external API calls unless ODDS_API_KEY
is configured (comparison adapter intentionally not enabled in this first stage).
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
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "120"))
LOOKAHEAD_HOURS = int(os.getenv("LOOKAHEAD_HOURS", "24"))
OUTPUT_DIR = Path(os.getenv("DATA_DIR", "."))
OUTPUT_FILE = OUTPUT_DIR / "nhl_snapshots.csv"
REUS_TZ = ZoneInfo("Europe/Madrid")
SESSION = requests.Session()
SESSION.headers.update({"Accept": "application/json"})

KEY = os.getenv("PINNACLE_X_API_KEY", "").strip()
if KEY:
    SESSION.headers["X-API-Key"] = KEY

FIELDS = [
    "timestamp_utc", "timestamp_reus", "source", "league_id",
    "matchup_id", "start_utc", "start_reus", "away", "home",
    "market", "period", "side", "line", "american_price",
    "decimal_odds",
]


def american_to_decimal(price):
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


def get_json(path):
    response = SESSION.get(f"{BASE_URL}{path}", timeout=25)
    response.raise_for_status()
    return response.json()


def iso_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def open_matchups():
    payload = get_json(f"/leagues/{NHL_LEAGUE_ID}/matchups")
    now = datetime.now(timezone.utc)
    end = now + timedelta(hours=LOOKAHEAD_HOURS)
    result = {}
    for item in payload:
        if item.get("type") != "matchup" or item.get("id") is None:
            continue
        periods = item.get("periods") or []
        main_period = next((p for p in periods if p.get("period") == 0), None)
        if not main_period or main_period.get("status") != "open":
            continue
        start = iso_dt(item.get("startTime"))
        if not start or not (now <= start <= end):
            continue
        participants = item.get("participants") or []
        away = next((p.get("name") for p in participants if p.get("alignment") == "away"), "AWAY")
        home = next((p.get("name") for p in participants if p.get("alignment") == "home"), "HOME")
        result[str(item["id"])] = {
            "matchup_id": str(item["id"]),
            "start_utc": start.astimezone(timezone.utc).isoformat(),
            "start_reus": start.astimezone(REUS_TZ).isoformat(),
            "away": away,
            "home": home,
        }
    return result


def market_rows(matchups):
    payload = get_json(f"/leagues/{NHL_LEAGUE_ID}/markets/straight")
    now = datetime.now(timezone.utc)
    timestamp_utc = now.isoformat()
    timestamp_reus = now.astimezone(REUS_TZ).isoformat()
    rows = []

    for market in payload:
        if market.get("period") != 0 or market.get("isAlternate") is True:
            continue
        matchup_id = str(market.get("matchupId", market.get("matchup_id", "")))
        matchup = matchups.get(matchup_id)
        if not matchup:
            continue

        market_type = (market.get("type") or "").lower()
        if market_type not in {"moneyline", "money_line", "money line", "spread", "total"}:
            continue

        prices = market.get("prices") or []
        if not prices:
            continue

        # Only the NHL puck line +/-1.5 is in scope for spread markets.
        if market_type == "spread":
            prices = [p for p in prices if p.get("points") in (-1.5, 1.5)]
            if not prices:
                continue

        # Main game total: keep a matched over/under pair at the same points.
        if market_type == "total":
            pairs = {}
            for price in prices:
                points = price.get("points")
                designation = (price.get("designation") or "").lower()
                if points is None or designation not in {"over", "under"}:
                    continue
                pairs.setdefault(float(points), {})[designation] = price
            complete = [(line, sides) for line, sides in pairs.items()
                        if "over" in sides and "under" in sides]
            if not complete:
                continue
            # Exclude alternate totals; Pinnacle's main total is represented by the first complete pair.
            line, sides = complete[0]
            prices = [dict(sides["over"], designation="over", points=line),
                      dict(sides["under"], designation="under", points=line)]

        normalized_market = (
            "moneyline" if market_type in {"moneyline", "money_line", "money line"}
            else "puckline" if market_type == "spread"
            else "total"
        )
        for price in prices:
            designation = (price.get("designation") or "").lower()
            points = price.get("points")
            if normalized_market == "moneyline":
                side = designation
                line = ""
            elif normalized_market == "puckline":
                side = designation
                line = points if points is not None else ""
            else:
                side = designation
                line = points if points is not None else ""

            american = price.get("price")
            decimal = american_to_decimal(american)
            if decimal is None or not side:
                continue
            rows.append({
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
            })
    return rows


def append_rows(rows):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    new_file = not OUTPUT_FILE.exists() or OUTPUT_FILE.stat().st_size == 0
    with OUTPUT_FILE.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerows(rows)


def main():
    if not KEY:
        raise SystemExit("ERROR: PINNACLE_X_API_KEY no configurada")
    print("NHL PINNACLE SNAPSHOT COLLECTOR | PAPER MODE | NO BETS", flush=True)
    print(f"Lliga={NHL_LEAGUE_ID} | interval={POLL_SECONDS}s | dades={OUTPUT_FILE}", flush=True)

    while True:
        try:
            matchups = open_matchups()
            rows = market_rows(matchups)
            append_rows(rows)
            print(
                f"{datetime.now(REUS_TZ).isoformat(timespec='seconds')} "
                f"| partits={len(matchups)} | snapshots={len(rows)}",
                flush=True,
            )
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            print(f"ERROR HTTP Pinnacle: {status}", flush=True)
        except (requests.RequestException, ValueError, KeyError) as exc:
            print(f"ERROR de captura: {type(exc).__name__}: {exc}", flush=True)
        except Exception as exc:
            print(f"ERROR inesperat: {type(exc).__name__}: {exc}", flush=True)
        time.sleep(max(30, POLL_SECONDS))


if __name__ == "__main__":
    main()
