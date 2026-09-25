import requests
import json
from datetime import datetime, timezone

LEAGUES_URL = "https://guest.api.arcadia.pinnacle.com/0.1/sports/3/leagues"
MLB_ID = 246
VALID_TOTALS = [6.5, 7.0, 7.5, 8.0, 8.5, 9.0, 9.5, 10.0, 10.5, 11.0, 11.5, 12.0]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/137.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.pinnacle.com",
    "Referer": "https://www.pinnacle.com/",
    "Connection": "keep-alive",
}

session = requests.Session()
session.headers.update(HEADERS)

def american_to_decimal(price):
    if price is None:
        return None
    price = float(price)
    return round((price / 100.0) + 1.0, 4) if price > 0 else round((100.0 / abs(price)) + 1.0, 4)

print("⚾ BASEBALL STEAM DEBUG6 - INSPECCIÓ REAL DE MERCATS ⚾", flush=True)

try:
    print("1) Obtenint leagues...", flush=True)
    r = session.get(LEAGUES_URL, timeout=30)
    print(f"STATUS LEAGUES: {r.status_code}", flush=True)
    r.raise_for_status()

    leagues = r.json()
    mlb = next((x for x in leagues if x.get("id") == MLB_ID), None)
    if not mlb:
        print("No s'ha trobat MLB (246).", flush=True)
        raise SystemExit(1)

    print(f"MLB: {mlb.get('name')}", flush=True)

    matchups_url = f"https://guest.api.arcadia.pinnacle.com/0.1/leagues/{MLB_ID}/matchups"
    print("2) Obtenint matchups MLB...", flush=True)
    r = session.get(matchups_url, timeout=30)
    print(f"STATUS MATCHUPS: {r.status_code}", flush=True)
    r.raise_for_status()
    matchups = r.json()
    print(f"Matchups rebuts: {len(matchups)}", flush=True)

    target = None
    for m in matchups:
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
        target = m
        break

    if not target:
        print("NO S'HA TROBAT CAP MATCHUP MLB OBERT AMB TOTAL.", flush=True)
        raise SystemExit(0)

    away = next((p.get("name") for p in target.get("participants", []) if p.get("alignment") == "away"), "AWAY")
    home = next((p.get("name") for p in target.get("participants", []) if p.get("alignment") == "home"), "HOME")
    matchup_id = target.get("id")

    print("=" * 90, flush=True)
    print(f"🎯 MATCHUP: {away} @ {home}", flush=True)
    print(f"ID: {matchup_id}", flush=True)
    print(f"START: {target.get('startTime')}", flush=True)
    print("=" * 90, flush=True)

    market_url = f"https://guest.api.arcadia.pinnacle.com/0.1/matchups/{matchup_id}/markets/related/straight"
    print("3) Consultant mercats...", flush=True)
    print(f"GET: {market_url}", flush=True)
    r = session.get(market_url, timeout=30)
    print(f"STATUS MARKETS: {r.status_code}", flush=True)
    r.raise_for_status()

    markets = r.json()
    print(f"Markets rebuts: {len(markets) if isinstance(markets, list) else 'NO-LIST'}", flush=True)

    total_count = 0
    print("\n4) TOTALS / OVER / UNDER", flush=True)
    print("-" * 90, flush=True)

    if not isinstance(markets, list):
        print(json.dumps(markets, indent=2, ensure_ascii=False)[:16000], flush=True)
    else:
        for market in markets:
            if market.get("type") != "total":
                continue

            total_count += 1
            print(f"TOTAL MARKET #{total_count}", flush=True)
            print(f"  period      = {market.get('period')}", flush=True)
            print(f"  isAlternate = {market.get('isAlternate')}", flush=True)

            prices = market.get("prices", [])
            for p in prices:
                side = p.get("designation")
                points = p.get("points")
                american = p.get("price")
                decimal = american_to_decimal(american)
                valid = points in VALID_TOTALS
                print(
                    f"  SIDE={side} | POINTS={points} | AMERICAN={american} | "
                    f"DECIMAL={decimal} | VALID_TOTAL={valid}",
                    flush=True
                )
            print("", flush=True)

    print("-" * 90, flush=True)
    print(f"TOTAL MARKETS TROBATS: {total_count}", flush=True)
    print("✅ DEBUG6 FINALITZAT. No envia res a Telegram ni Google Sheets.", flush=True)

except KeyboardInterrupt:
    print("Interromput per l'usuari.", flush=True)
except Exception as e:
    print(f"ERROR DEBUG6: {type(e).__name__}: {e}", flush=True)
