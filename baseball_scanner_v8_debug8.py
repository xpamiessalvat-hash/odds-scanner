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

def get_all_totals(target):
    url = f"{BASE}/matchups/{target['id']}/markets/related/straight"
    r = session.get(url, timeout=30)
    r.raise_for_status()

    totals = []
    for market in r.json():
        if market.get("type") != "total":
            continue

        period = market.get("period")
        alternate = market.get("isAlternate")
        prices = {}

        for p in market.get("prices", []):
            side = (p.get("designation") or "").lower()
            if side not in ("over", "under"):
                continue
            prices[side] = {
                "points": p.get("points"),
                "american": p.get("price"),
                "decimal": american_to_decimal(p.get("price")),
            }

        if prices:
            totals.append({
                "period": period,
                "alternate": alternate,
                "prices": prices,
            })

    return totals

def snapshot(totals):
    rows = []
    for t in totals:
        for side in ("over", "under"):
            p = t["prices"].get(side)
            if p:
                rows.append((
                    t["period"],
                    t["alternate"],
                    side,
                    p["points"],
                    p["american"],
                    p["decimal"],
                ))
    return tuple(sorted(rows, key=str))

print("⚾ BASEBALL STEAM DEBUG8 - TOTS ELS TOTALS ⚾", flush=True)
print("1 partit MLB | TOTS els mercats Total | cada 5 segons", flush=True)
print("Detecta canvis de LINIA, QUOTA, PERIOD i ALTERNATE", flush=True)
print("NO TELEGRAM / NO GOOGLE SHEETS", flush=True)

try:
    target = find_target()
    if not target:
        print("No s'ha trobat cap MLB oberta amb Total.", flush=True)
        raise SystemExit(0)

    print("=" * 100, flush=True)
    print(f"🎯 PARTIT FIXAT: {target['match']}", flush=True)
    print(f"ID: {target['id']}", flush=True)
    print(f"START: {target['start']}", flush=True)
    print("=" * 100, flush=True)

    previous = None
    cycle = 0

    while True:
        cycle += 1
        now = datetime.now().strftime("%H:%M:%S")

        try:
            totals = get_all_totals(target)
            current = snapshot(totals)

            print(f"\n[{now}] CICLE {cycle} | {len(current)} PREUS", flush=True)

            # Mostrem un resum ordenat per període i línia.
            for t in sorted(
                totals,
                key=lambda x: (
                    x["period"] is None,
                    x["period"],
                    x["alternate"] is not True,
                    str(x["prices"].get("over", {}).get("points", "")),
                ),
            ):
                over = t["prices"].get("over")
                under = t["prices"].get("under")
                if not over and not under:
                    continue

                tag = "ALT" if t["alternate"] else "MAIN"
                line = over["points"] if over else under["points"]
                ov = f"O {over['american']}" if over else "O -"
                un = f"U {under['american']}" if under else "U -"

                print(
                    f"  P{t['period']} {tag:4} | LINE {line} | {ov:>8} | {un:>8}",
                    flush=True,
                )

            if previous is None:
                print("  🟢 SNAPSHOT INICIAL GUARDAT", flush=True)
            elif current == previous:
                print("  = CAP CANVI", flush=True)
            else:
                old_set = set(previous)
                new_set = set(current)

                added = sorted(new_set - old_set, key=str)
                removed = sorted(old_set - new_set, key=str)

                print("  🚨🚨 CANVI DETECTAT 🚨🚨", flush=True)

                if added:
                    print("  + APAREIX:", flush=True)
                    for x in added:
                        print(f"    {x}", flush=True)

                if removed:
                    print("  - DESAPAREIX:", flush=True)
                    for x in removed:
                        print(f"    {x}", flush=True)

            previous = current

        except Exception as e:
            print(f"  ERROR: {type(e).__name__}: {e}", flush=True)

        time.sleep(POLL_SECONDS)

except KeyboardInterrupt:
    print("\nDEBUG8 aturat per l'usuari.", flush=True)
