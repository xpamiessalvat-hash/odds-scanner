import argparse, re
from playwright.sync_api import sync_playwright

URL = "https://www.bet365.es"

ALIASES = {
    "Seattle Mariners": ["SEA Mariners"],
    "Colorado Rockies": ["COL Rockies"],
    "San Diego Padres": ["SD Padres"],
    "Miami Marlins": ["MIA Marlins"],
    "Los Angeles Dodgers": ["LA Dodgers"],
    "San Francisco Giants": ["SF Giants"],
    "Texas Rangers": ["TEX Rangers"],
    "Toronto Blue Jays": ["TOR Blue Jays"],
}

def names(team):
    return ALIASES.get(team, [team])

def find_game_market_container(page, home, away):
    h = page.get_by_text(names(home)[0], exact=True)
    a = page.get_by_text(names(away)[0], exact=True)
    if not h.count() or not a.count():
        return None

    # The previous debug showed:
    # team span -> cpr-a6 -> cpr-f4c -> cpr-07 -> cpr-a
    # The market headers are siblings/descendants at a larger level.
    # Try progressively larger ancestors and choose the smallest one
    # that contains both teams AND the three main market headers.
    for cls in ["cpr-77", "cpr-07", "cpr-f4c", "cpr-a6"]:
        node = h.first.locator(
            f"xpath=ancestor::div[contains(concat(' ',normalize-space(@class),' '),' {cls} ')][1]"
        )
        if not node.count():
            continue
        try:
            txt = node.first.inner_text()
            if (names(away)[0].lower() in txt.lower()
                and "Hándicap" in txt
                and "Total" in txt
                and "Línea de dinero" in txt):
                return node.first
        except Exception:
            pass

    # Generic nearest ancestor containing both teams and markets.
    node = h.first
    for _ in range(10):
        try:
            node = node.locator("xpath=..")
            if not node.count():
                break
            txt = node.first.inner_text()
            if (names(away)[0].lower() in txt.lower()
                and "Hándicap" in txt
                and "Total" in txt
                and "Línea de dinero" in txt
                and len(txt) < 10000):
                return node.first
        except Exception:
            break
    return None

def extract(text, market, side, points):
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    low = [x.lower() for x in lines]

    if market == "total":
        try: i = next(i for i,x in enumerate(low) if x == "total")
        except StopIteration: return None
        block = lines[i:i+25]
        wanted = "o" if side == "over" else "u"
        for j,x in enumerate(block):
            m = re.fullmatch(rf"{wanted}\s+(-?\d+(?:\.\d+)?)", x, re.I)
            if m:
                p = float(m.group(1))
                if points is not None and abs(p-points) > .001: continue
                for y in block[j+1:j+4]:
                    if re.fullmatch(r"\d+\.\d+", y):
                        return p, float(y)
        return None

    if market == "spread":
        try: i = next(i for i,x in enumerate(low) if x == "hándicap")
        except StopIteration: return None
        block = lines[i:i+20]
        for j,x in enumerate(block):
            if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", x):
                p=float(x)
                if points is not None and abs(p-points)>.001: continue
                for y in block[j+1:j+4]:
                    if re.fullmatch(r"\d+\.\d+", y):
                        return p,float(y)
        return None

    if market == "moneyline":
        try: i = next(i for i,x in enumerate(low) if x == "línea de dinero")
        except StopIteration: return None
        odds=[]
        for x in lines[i+1:i+6]:
            if re.fullmatch(r"\d+\.\d+",x):
                odds.append(float(x))
        if len(odds)>=2:
            return odds[0] if side=="home" else odds[1]
        return None

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--home",required=True)
    ap.add_argument("--away",required=True)
    ap.add_argument("--market",choices=["moneyline","spread","total"],required=True)
    ap.add_argument("--side",required=True)
    ap.add_argument("--points",type=float,default=None)
    args=ap.parse_args()

    print("⚾ BET365 BASEBALL TESTER V5 — DOM MARKET CONTAINER")
    print("="*72)
    print(f"Match: {args.away} @ {args.home}")
    print(f"Market: {args.market} | Side: {args.side} | Points: {args.points}")
    print("🌐 Obrint Bet365...")

    with sync_playwright() as p:
        browser=p.chromium.launch(headless=False)
        context=browser.new_context(viewport={"width":1400,"height":900},locale="es-ES")
        page=context.new_page()
        try:
            page.goto(URL,wait_until="domcontentloaded",timeout=120000)
            page.wait_for_timeout(10000)
            try:
                bs=page.locator("button")
                for i in range(min(bs.count(),100)):
                    try:
                        t=bs.nth(i).inner_text().strip().lower()
                        if any(k in t for k in ["aceptar","accept","agree"]):
                            bs.nth(i).click(timeout=2000); print("✅ Cookies gestionades"); break
                    except: pass
            except: pass
            page.wait_for_timeout(5000)

            game=find_game_market_container(page,args.home,args.away)
            if not game:
                print("❌ No s'ha trobat el contenidor de mercats del partit.")
                return

            text=game.inner_text()
            print("\n✅ CONTENIDOR DE MERCATS TROBAT")
            print("-"*72)
            print(text[:7000])
            print("-"*72)

            result=extract(text,args.market,args.side,args.points)
            if result is None:
                print("❌ Mercat/quota no trobats.")
                return

            if args.market=="moneyline":
                odds=result; out_points=None
            else:
                out_points,odds=result

            print(f"💰 Bet365 quota: {odds}")
            print("\nRESULTAT:")
            print({"home":args.home,"away":args.away,"market":args.market,
                   "side":args.side,"points":out_points,"bet365_odds":odds})
            page.wait_for_timeout(5000)
        finally:
            browser.close()

if __name__=="__main__":
    main()
