import requests
import time
from datetime import datetime, timezone

MLB_ID = 246
POLL_SECONDS = 5
BASE = "https://guest.api.arcadia.pinnacle.com/0.1"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/137.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.pinnacle.com",
    "Referer": "https://www.pinnacle.com/",
}

session = requests.Session()
session.headers.update(HEADERS)

def american_to_decimal(price):
    if price is None:
        return None
    price = float(price)
    return round((price / 100) + 1, 4) if price > 0 else round((100 / abs(price)) + 1, 4)

def find_target():
    r = session.get(f"{BASE}/leagues/{MLB_ID}/matchups", timeout=30)
    r.raise_for_status()
    for m in r.json():
        if m.get("type") != "matchup":
            continue
        p0 = next((p for p in m.get("periods", []) if p.get("period") == 0), None)
        if not p0 or not p0.get("hasTotal") or p0.get("status") != "open":
            continue
        start = m.get("startTime")
        if not start:
            continue
        try:
            dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            if dt < datetime.now(timezone.utc):
                continue
        except Exception:
            continue
        away = next((p.get("name") for p in m.get("participants", []) if p.get("alignment") == "away"), "AWAY")
        home = next((p.get("name") for p in m.get("participants", []) if p.get("alignment") == "home"), "HOME")
        return {"id": m["id"], "match": f"{away} @ {home}", "start": start}
    return None

def get_total(target):
    url = f"{BASE}/matchups/{target['id']}/markets/related/straight"
    r = session.get(url, timeout=30)
    r.raise_for_status()
    for market in r.json():
        if market.get("type") == "total" and market.get("period") == 0 and market.get("isAlternate") is not True:
            result = {}
            for p in market.get("prices", []):
                side = (p.get("designation") or "").lower()
                if side in ("over", "under"):
                    result[side] = {
                        "points": p.get("points"),
                        "american": p.get("price"),
                        "decimal": american_to_decimal(p.get("price")),
                    }
            if result:
                return result
    return {}

print("⚾ BASEBALL STEAM DEBUG7 - MONITOR DIRECTE ⚾", flush=True)
print("1 partit MLB | Total principal | consulta cada 5 segons", flush=True)
print("NO TELEGRAM / NO GOOGLE SHEETS", flush=True)

try:
    target = find_target()
    if not target:
        print("No s'ha trobat cap MLB oberta amb Total.", flush=True)
        raise SystemExit(0)

    print("=" * 90, flush=True)
    print(f"🎯 PARTIT FIXAT: {target['match']}", flush=True)
    print(f"ID: {target['id']}", flush=True)
    print(f"START: {target['start']}", flush=True)
    print("=" * 90, flush=True)

    previous = None
    cycle = 0

    while True:
        cycle += 1
        now = datetime.now().strftime("%H:%M:%S")
        try:
            current = get_total(target)
            print(f"\n[{now}] CICLE {cycle}", flush=True)

            if not current:
                print("  ⚠️ Total principal no disponible.", flush=True)
            else:
                for side in ("over", "under"):
                    x = current.get(side)
                    if x:
                        print(
                            f"  {side.upper():5} {x['points']} | "
                            f"American={x['american']} | Decimal={x['decimal']}",
                            flush=True
                        )

                if previous is not None:
                    changed = False
                    for side in ("over", "under"):
                        old = previous.get(side)
                        new = current.get(side)
                        if old and new and (
                            old["points"] != new["points"]
                            or old["american"] != new["american"]
                            or old["decimal"] != new["decimal"]
                        ):
                            changed = True
                            movement = ((old["decimal"] - new["decimal"]) / old["decimal"]) * 100
                            print(
                                f"  🚨 CANVI {side.upper()}: "
                                f"{old['points']} {old['american']} ({old['decimal']}) -> "
                                f"{new['points']} {new['american']} ({new['decimal']}) | "
                                f"movement={movement:.2f}%",
                                flush=True
                            )
                    if not changed:
                        print("  = Sense canvi", flush=True)

                previous = current

        except Exception as e:
            print(f"  ERROR MERCAT: {type(e).__name__}: {e}", flush=True)

        time.sleep(POLL_SECONDS)

except KeyboardInterrupt:
    print("\nDEBUG7 aturat per l'usuari.", flush=True)
