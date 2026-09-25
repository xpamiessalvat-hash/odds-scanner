from playwright.sync_api import sync_playwright
import re
import time
import argparse

BET365_URL = "https://www.bet365.es"

def norm(s):
    s=s.lower()
    reps={"new york yankees":"yankees","new york mets":"mets",
          "los angeles dodgers":"dodgers","los angeles angels":"angels",
          "san francisco giants":"giants","san diego padres":"padres",
          "tampa bay rays":"rays","st louis cardinals":"cardinals",
          "st. louis cardinals":"cardinals","colorado rockies":"rockies",
          "chicago white sox":"white sox","chicago cubs":"cubs",
          "detroit tigers":"tigers","boston red sox":"red sox",
          "texas rangers":"rangers","houston astros":"astros",
          "atlanta braves":"braves","philadelphia phillies":"phillies",
          "baltimore orioles":"orioles","washington nationals":"nationals",
          "arizona diamondbacks":"diamondbacks","minnesota twins":"twins",
          "cleveland guardians":"guardians","milwaukee brewers":"brewers",
          "cincinnati reds":"reds","pittsburgh pirates":"pirates",
          "miami marlins":"marlins","seattle mariners":"mariners",
          "toronto blue jays":"blue jays","oakland athletics":"athletics",
          "athletics":"athletics"}
    for a,b in reps.items(): s=s.replace(a,b)
    return re.sub(r"\s+"," ",re.sub(r"[^a-z0-9 ]","",s)).strip()

def odd(text):
    m=re.search(r"\b([1-9]\d?\.\d{2})\b",text.replace(",","."))
    return float(m.group(1)) if m else None

def extract_games(body):
    """
    Construeix blocs de partits a partir del text visible de Bet365.

    No considerem vàlid un partit perquè aparegui un sol equip:
    el bloc ha de contenir dos equips MLB diferents i, posteriorment,
    la cerca demanarà exactament la parella home/away.
    """
    lines=[x.strip() for x in body.splitlines() if x.strip()]

    # Patró flexible per als noms que Bet365 mostra en aquesta prova:
    # "COL Rockies", "SD Padres", "SEA Mariners", etc.
    team_pat=re.compile(
        r"^(?:[A-Z]{2,4}\s+)?"
        r"(?:[A-Z][A-Za-z.'-]+(?:\s+[A-Za-z.'-]+){0,3})$"
    )

    time_pat=re.compile(r"^\d{2}:\d{2}$")
    date_pat=re.compile(r"^(?:Lun|Mar|Mié|Jue|Vie|Sáb|Dom)\s+\d{1,2}\s+\w+$")

    games=[]
    i=0

    while i < len(lines)-1:
        # Busquem una línia d'equip seguida d'una línia de pitcher,
        # hora i mercats. No intentem endevinar un partit a partir d'un
        # únic nom dins de tota la pàgina.
        if not time_pat.match(lines[i]):
            i+=1
            continue

        # La informació dels equips acostuma a estar abans de l'hora.
        window=lines[max(0,i-8):i]
        team_lines=[]

        for x in window:
            low=x.lower()
            if any(k in low for k in [
                "hándicap","total","línea de dinero","selección rápida",
                "últimos","resultado final","combinadas"
            ]):
                continue
            if re.match(r"^[A-Z]{2,4}\s+",x) or (
                len(x.split())>=2 and x[0].isupper()
            ):
                team_lines.append(x)

        # De la finestra, conservem candidats que semblen equips.
        # En aquesta pàgina els dos equips apareixen just abans dels pitchers.
        if len(team_lines)>=2:
            # Preferim els dos últims candidats diferents.
            home=team_lines[-1]
            away=team_lines[-2]

            # El bloc de mercats va des de la línia d'hora fins abans
            # del següent marcador de data/equip.
            end=min(len(lines),i+18)
            j=i+1
            while j<end and not date_pat.match(lines[j]):
                j+=1

            block="\n".join(lines[max(0,i-2):j])
            games.append({
                "home":home,
                "away":away,
                "text":block,
                "time":lines[i]
            })
        i+=1

    return games


def section(body,home,away):
    """
    Retorna exclusivament el bloc del partit exacte.
    """
    h=norm(home)
    a=norm(away)

    for game in extract_games(body):
        gh=norm(game["home"])
        ga=norm(game["away"])

        # Acceptem també abreviacions de Bet365 si contenen el nom
        # normalitzat de l'equip sol·licitat.
        direct = (
            (h in gh or gh in h) and
            (a in ga or ga in a)
        )

        reverse = (
            (h in ga or ga in h) and
            (a in gh or gh in a)
        )

        if direct or reverse:
            return game["text"]

    return None

def nearby(lines,i,w=8):
    for j in range(i,min(i+w,len(lines))):
        x=odd(lines[j])
        if x is not None:return x
    return None

def total(sec,side,points):
    lines=sec.splitlines(); p=str(points)
    targets=([f"Más de {p}",f"Over {p}",f"O {p}"] if side=="over"
             else [f"Menos de {p}",f"Under {p}",f"U {p}"])
    for i,x in enumerate(lines):
        if any(t.lower() in x.lower() for t in targets): return nearby(lines,i)
    return None

def spread(sec,side,points):
    lines=sec.splitlines(); p=str(points)
    for i,x in enumerate(lines):
        if p in x:
            q=nearby(lines,i)
            if q is not None:return q
    return None

def moneyline(sec,team):
    lines=sec.splitlines(); t=norm(team)
    for i,x in enumerate(lines):
        if t in norm(x):
            q=nearby(lines,i,6)
            if q is not None:return q
    return None

def scan(home,away,market,side,points=None):
    print("="*65)
    print("⚾ BET365 BASEBALL TESTER")
    print("="*65)
    print(f"Match: {away} @ {home}")
    print(f"Market: {market} | Side: {side} | Points: {points}")
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=False,slow_mo=100)
        ctx=browser.new_context(viewport={"width":1400,"height":900},
            locale="es-ES",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/137.0.0.0 Safari/537.36")
        page=ctx.new_page()
        try:
            print("🌐 Obrint Bet365...")
            page.goto(BET365_URL,wait_until="domcontentloaded",timeout=120000)
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
            body=page.locator("body").inner_text()
            print(f"📄 Text capturat: {len(body):,} caràcters")
            sec=section(body,home,away)
            if not sec:
                print("❌ Partit no trobat: no s\'han identificat ELS DOS equips a la mateixa secció."); time.sleep(15); return
            print("✅ Partit trobat.")
            if market=="total": q=total(sec,side,points)
            elif market=="spread": q=spread(sec,side,points)
            else: q=moneyline(sec,home if side=="home" else away)
            if q is None:
                print("❌ Quota no trobada.")
                print(sec[:5000]); time.sleep(15); return
            print(f"💰 QUOTA BET365: {q:.2f}")
            print("✅ Extracció correcta.")
            return {"home":home,"away":away,"market":market,"side":side,"points":points,"bet365_odds":q}
        except Exception as e:
            print(f"❌ ERROR: {type(e).__name__}: {e}"); time.sleep(10)
        finally: browser.close()

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--home",required=True); ap.add_argument("--away",required=True)
    ap.add_argument("--market",required=True,choices=["moneyline","spread","total"])
    ap.add_argument("--side",required=True,choices=["home","away","over","under"])
    ap.add_argument("--points",type=float)
    a=ap.parse_args()
    if a.market in ("total","spread") and a.points is None: ap.error("--points és obligatori")
    print(scan(a.home,a.away,a.market,a.side,a.points))
