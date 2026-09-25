import argparse
import re
from playwright.sync_api import sync_playwright

URL = "https://www.bet365.es"

TEAM_ALIASES = {
    "Seattle Mariners": ["SEA Mariners", "Seattle Mariners"],
    "Colorado Rockies": ["COL Rockies", "Colorado Rockies"],
    "San Diego Padres": ["SD Padres", "San Diego Padres"],
    "Miami Marlins": ["MIA Marlins", "Miami Marlins"],
    "Los Angeles Dodgers": ["LA Dodgers", "Los Angeles Dodgers"],
    "San Francisco Giants": ["SF Giants", "San Francisco Giants"],
    "Texas Rangers": ["TEX Rangers", "Texas Rangers"],
    "Toronto Blue Jays": ["TOR Blue Jays", "Toronto Blue Jays"],
    "Atlanta Braves": ["ATL Braves", "Atlanta Braves"],
    "Houston Astros": ["HOU Astros", "Houston Astros"],
    "Washington Nationals": ["WAS Nationals", "Washington Nationals"],
    "St. Louis Cardinals": ["STL Cardinals", "St. Louis Cardinals"],
    "Minnesota Twins": ["MIN Twins", "Minnesota Twins"],
    "Los Angeles Angels": ["LA Angels", "Los Angeles Angels"],
    "New York Yankees": ["NY Yankees", "New York Yankees"],
    "Arizona Diamondbacks": ["ARI Diamondbacks", "Arizona Diamondbacks"],
}

def aliases(team):
    return TEAM_ALIASES.get(team, [team])

def american_to_decimal(x):
    x = int(x)
    return round(1 + (x / 100 if x > 0 else 100 / abs(x)), 4)

def find_game_container(page, home, away):
    # Bet365 DOM debug confirmed the team span is inside:
    # SPAN.cpr-092 -> DIV.cpr-c0 -> DIV.cpr-48 -> DIV.cpr-77
    # -> DIV.cpr-a6 -> DIV.cpr-f4c -> DIV.cpr-07 -> DIV.cpr-a
    #
    # We deliberately use the cpr-a game container rather than body text.
    wanted = []
    for team in aliases(home) + aliases(away):
        loc = page.get_by_text(team, exact=True)
        if loc.count():
            wanted.append(loc.first)

    if len(wanted) < 2:
        return None

    home_el, away_el = wanted[0], wanted[1]

    # Find the nearest ancestor common to both team elements.
    common = page.locator("div.cpr-a").filter(
        has=page.get_by_text(aliases(home)[0], exact=True)
    ).filter(
        has=page.get_by_text(aliases(away)[0], exact=True)
    )

    if common.count():
        return common.first

    # Fallback: climb from home and test ancestors for away.
    for cls in ["cpr-a", "cpr-07", "cpr-f4c", "cpr-a6"]:
        node = home_el.locator(
            f"xpath=ancestor::div[contains(@class, '{cls}')][1]"
        )
        if node.count():
            try:
                txt = node.first.inner_text()
                if any(a.lower() in txt.lower() for a in aliases(away)):
                    return node.first
            except Exception:
                pass

    return None

def extract_market(game_text, market, side, points):
    lines = [x.strip() for x in game_text.splitlines() if x.strip()]
    low = [x.lower() for x in lines]

    # Locate market header.
    if market == "total":
        headers = ["total"]
    elif market == "spread":
        headers = ["hándicap"]
    elif market == "moneyline":
        headers = ["línea de dinero"]
    else:
        return None

    try:
        idx = next(i for i, x in enumerate(low) if x in headers)
    except StopIteration:
        return None

    block = lines[idx:idx + 18]

    if market == "total":
        target = "o" if side == "over" else "u"
        for i, line in enumerate(block):
            if re.fullmatch(rf"{target}\s*-?\d+(?:\.\d+)?", line, re.I):
                p = float(re.search(r"-?\d+(?:\.\d+)?", line).group())
                if points is not None and abs(p - points) > 0.001:
                    continue
                for nxt in block[i+1:i+4]:
                    if re.fullmatch(r"\d+(?:\.\d+)?", nxt):
                        return p, float(nxt)
        return None

    if market == "spread":
        target = points
        # Bet365 text has point on one line and decimal odds on next line.
        for i, line in enumerate(block):
            if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", line):
                p = float(line)
                if target is not None and abs(p - target) > 0.001:
                    continue
                for nxt in block[i+1:i+4]:
                    if re.fullmatch(r"\d+(?:\.\d+)?", nxt):
                        return p, float(nxt)
        return None

    if market == "moneyline":
        odds = []
        for line in block[1:]:
            if re.fullmatch(r"\d+(?:\.\d+)?", line):
                odds.append(float(line))
                if len(odds) == 2:
                    break
        if len(odds) == 2:
            # In the verified page structure, the two ML prices follow
            # the market header in home/away order.
            return odds[0] if side == "home" else odds[1]
        return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", required=True)
    ap.add_argument("--away", required=True)
    ap.add_argument("--market", choices=["moneyline", "spread", "total"], required=True)
    ap.add_argument("--side", required=True)
    ap.add_argument("--points", type=float, default=None)
    args = ap.parse_args()

    print("⚾ BET365 BASEBALL TESTER V4 — DOM")
    print("=" * 72)
    print(f"Match: {args.away} @ {args.home}")
    print(f"Market: {args.market} | Side: {args.side} | Points: {args.points}")
    print("🌐 Obrint Bet365...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1400, "height": 900},
            locale="es-ES"
        )
        page = context.new_page()

        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=120000)
            page.wait_for_timeout(10000)

            # Cookies
            try:
                buttons = page.locator("button")
                for i in range(min(buttons.count(), 100)):
                    try:
                        t = buttons.nth(i).inner_text().strip().lower()
                        if any(k in t for k in ["aceptar", "accept", "agree"]):
                            buttons.nth(i).click(timeout=2000)
                            print("✅ Cookies gestionades")
                            break
                    except Exception:
                        pass
            except Exception:
                pass

            page.wait_for_timeout(5000)

            game = find_game_container(page, args.home, args.away)

            if not game:
                print("❌ Partit no trobat al DOM.")
                print("   Això vol dir que aquest partit no està visible a Bet365")
                print("   o que els noms utilitzats no coincideixen.")
                return

            text = game.inner_text()
            print("\n✅ PARTIT TROBAT AL CONTENIDOR DOM")
            print("-" * 72)
            print(text[:6000])
            print("-" * 72)

            result = extract_market(
                text, args.market, args.side, args.points
            )

            if result is None:
                print("❌ Mercat/quota no trobats dins del mateix contenidor.")
                return

            if args.market == "moneyline":
                print(f"💰 Bet365 quota: {result}")
                odds = result
                out_points = None
            else:
                out_points, odds = result
                print(f"📈 Línia: {out_points}")
                print(f"💰 Bet365 quota: {odds}")

            print("\nRESULTAT:")
            print({
                "home": args.home,
                "away": args.away,
                "market": args.market,
                "side": args.side,
                "points": out_points,
                "bet365_odds": odds,
            })

            page.wait_for_timeout(5000)

        finally:
            browser.close()

if __name__ == "__main__":
    main()
