# BASEBALL STEAM V11 - STEAM + VALUE TEST REAL (PAPER)
import csv
import os
import requests
import time
import re

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None
from datetime import datetime, timezone

from pathlib import Path
from pathlib import Path as _Path
import sys as _sys

_REAL_LOG_DIR = _Path("logs")
_REAL_LOG_DIR.mkdir(exist_ok=True)
_REAL_LOG_FILE = _REAL_LOG_DIR / f"steam_value_{datetime.now().strftime('%Y-%m-%d')}.log"

class _RealTee:
    def __init__(self, *streams):
        self.streams = streams
    def write(self, data):
        for s in self.streams:
            s.write(data)
            s.flush()
    def flush(self):
        for s in self.streams:
            s.flush()

_real_original_stdout = _sys.stdout
_sys.stdout = _RealTee(_real_original_stdout, open(_REAL_LOG_FILE, "a", encoding="utf-8"))
print(f"📝 STEAM/VALUE TEST LOG: {_REAL_LOG_FILE}", flush=True)

LEAGUES_URL = "https://guest.api.arcadia.pinnacle.com/0.1/sports/3/leagues"
# BANKROLL / ROI — simulació amb stake percentual
INITIAL_BANK_EUR = 1000.0
STAKE_PCT = 0.03
WEEKLY_REPORT_DAY = 6  # diumenge (0=dilluns)
WEEKLY_REPORT_HOUR = 23
BANKROLL_FILE = "baseball_bankroll.csv"
RESULTS_FILE = "baseball_results.csv"
RESULT_POLL_HOURS = 12
RESULT_LOOKBACK_DAYS = 3


ALLOWED_LEAGUES = {
    244: "Mexican League",
    246: "MLB",
    6227: "KBO",
    187703: "NPB",
    208753: "Chinese Taipei Professional League",
}

# PERFILS HISTÒRICS ACTUALS (MLB) — no són garantia de rendiment.
# Són els perfils que hem estudiat en les dades històriques disponibles.
# El scanner els manté separats per mercat.
MARKET_PROFILES = {
    "moneyline": [(5.0, 6.0, 70.0, 80.0)],
    "spread": [(3.0, 4.0, 60.0, 70.0)],
    "total": [(4.0, 5.0, 70.0, 80.0)],
}

# STEAM raw que volem estudiar: la senyal només entra en confirmació si
# compleix almenys un dels perfils del seu mercat.
STEAM_SCORE_MIN = 3.0
STEAM_SCORE_MAX = 6.0

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

# TELEGRAM — mateixes variables que les versions anteriors
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# BET365 — verificació de quota real després d'un STEAM confirmat.
BET365_URL = "https://www.bet365.es"
BET365_HEADLESS = os.getenv("BET365_HEADLESS", "1") != "0"
BET365_TIMEOUT_MS = 120000
BET365_WAIT_MS = 7000
BET365_LOOKUP_ENABLED = os.getenv("BET365_LOOKUP_ENABLED", "1") != "0"

BET365_ALIASES = {
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
    "Chicago Cubs": ["CHI Cubs", "Chicago Cubs"],
    "Cincinnati Reds": ["CIN Reds", "Cincinnati Reds"],
    "Kansas City Royals": ["KC Royals", "Kansas City Royals"],
    "Pittsburgh Pirates": ["PIT Pirates", "Pittsburgh Pirates"],
    "Milwaukee Brewers": ["MIL Brewers", "Milwaukee Brewers"],
    "Baltimore Orioles": ["BAL Orioles", "Baltimore Orioles"],
    "Cleveland Guardians": ["CLE Guardians", "Cleveland Guardians"],
    "Athletics": ["Athletics"],
    "Boston Red Sox": ["BOS Red Sox", "Boston Red Sox"],
    "Tampa Bay Rays": ["TB Rays", "Tampa Bay Rays"],
    "Philadelphia Phillies": ["PHI Phillies", "Philadelphia Phillies"],
    "New York Mets": ["NY Mets", "New York Mets"],
    "Detroit Tigers": ["DET Tigers", "Detroit Tigers"],
    "Chicago White Sox": ["CHI White Sox", "Chicago White Sox"],
}

_bet365_pw = None
_bet365_browser = None
_bet365_context = None
_bet365_page = None

def _bet365_aliases(team):
    return BET365_ALIASES.get(team, [team])

def _bet365_accept_cookies(page):
    try:
        buttons = page.locator("button")
        for i in range(min(buttons.count(), 100)):
            try:
                t = buttons.nth(i).inner_text().strip().lower()
                if any(k in t for k in ["aceptar", "accept", "agree"]):
                    buttons.nth(i).click(timeout=2000)
                    break
            except Exception:
                pass
    except Exception:
        pass

def _bet365_get_page():
    global _bet365_pw, _bet365_browser, _bet365_context, _bet365_page

    if not BET365_LOOKUP_ENABLED or sync_playwright is None:
        return None

    if _bet365_page is not None:
        try:
            if not _bet365_page.is_closed():
                return _bet365_page
        except Exception:
            pass

    _bet365_pw = sync_playwright().start()
    _bet365_browser = _bet365_pw.chromium.launch(headless=BET365_HEADLESS)
    _bet365_context = _bet365_browser.new_context(
        viewport={"width": 1400, "height": 900},
        locale="es-ES",
    )
    _bet365_page = _bet365_context.new_page()
    _bet365_page.goto(
        BET365_URL,
        wait_until="domcontentloaded",
        timeout=BET365_TIMEOUT_MS,
    )
    _bet365_page.wait_for_timeout(BET365_WAIT_MS)
    _bet365_accept_cookies(_bet365_page)
    _bet365_page.wait_for_timeout(3000)
    return _bet365_page

def _bet365_find_market_container(page, home, away):
    home_aliases = _bet365_aliases(home)
    away_aliases = _bet365_aliases(away)

    home_el = None
    away_el = None

    for name in home_aliases:
        loc = page.get_by_text(name, exact=True)
        if loc.count():
            home_el = loc.first
            break

    for name in away_aliases:
        loc = page.get_by_text(name, exact=True)
        if loc.count():
            away_el = loc.first
            break

    if home_el is None or away_el is None:
        return None

    # El debug V2/V5 ha validat que cpr-77 és el contenidor que
    # engloba partit + mercats principals.
    for cls in ["cpr-77", "cpr-07", "cpr-f4c", "cpr-a6"]:
        try:
            node = home_el.locator(
                f"xpath=ancestor::div[contains(concat(' ',normalize-space(@class),' '),' {cls} ')][1]"
            )
            if node.count():
                txt = node.first.inner_text()
                if (
                    any(a.lower() in txt.lower() for a in away_aliases)
                    and "Hándicap" in txt
                    and "Total" in txt
                    and "Línea de dinero" in txt
                ):
                    return node.first
        except Exception:
            pass

    # Fallback: pujar per la jerarquia fins a trobar el bloc amb mercats.
    node = home_el
    for _ in range(10):
        try:
            node = node.locator("xpath=..")
            if not node.count():
                break
            txt = node.first.inner_text()
            if (
                any(a.lower() in txt.lower() for a in away_aliases)
                and "Hándicap" in txt
                and "Total" in txt
                and "Línea de dinero" in txt
                and len(txt) < 10000
            ):
                return node.first
        except Exception:
            break

    return None

def _bet365_extract_total(text, side, points):
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    low = [x.lower() for x in lines]
    try:
        i = next(i for i, x in enumerate(low) if x == "total")
    except StopIteration:
        return None

    wanted = "o" if side.lower() == "over" else "u"
    for j, line in enumerate(lines[i:i + 25]):
        m = re.fullmatch(rf"{wanted}\s+(-?\d+(?:\.\d+)?)", line, re.I)
        if not m:
            continue
        p = float(m.group(1))
        if points is not None and abs(p - float(points)) > 0.001:
            continue
        for y in lines[i + j + 1:i + j + 4]:
            if re.fullmatch(r"\d+\.\d+", y):
                return float(y)
    return None

def _bet365_extract_spread(text, side, points):
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    low = [x.lower() for x in lines]
    try:
        i = next(i for i, x in enumerate(low) if x == "hándicap")
    except StopIteration:
        return None

    target = float(points)
    for j, line in enumerate(lines[i:i + 20]):
        if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", line):
            continue
        p = float(line)
        if abs(p - target) > 0.001:
            continue
        for y in lines[i + j + 1:i + j + 4]:
            if re.fullmatch(r"\d+\.\d+", y):
                return float(y)
    return None

def _bet365_extract_moneyline(text, side):
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    low = [x.lower() for x in lines]
    try:
        i = next(i for i, x in enumerate(low) if x == "línea de dinero")
    except StopIteration:
        return None

    odds = []
    for x in lines[i + 1:i + 7]:
        if re.fullmatch(r"\d+\.\d+", x):
            odds.append(float(x))
    if len(odds) >= 2:
        # Bet365 manté aquí l'ordre home / away.
        return odds[0] if side.lower() == "home" else odds[1]
    return None

def get_bet365_odds(snapshot):
    """
    Consulta Bet365 només després d'un STEAM confirmat.
    Retorna la quota real o None.
    """
    if not BET365_LOOKUP_ENABLED or sync_playwright is None:
        return None

    page = _bet365_get_page()
    if page is None:
        return None

    home = snapshot["match"].split(" @ ")[-1].strip()
    away = snapshot["match"].split(" @ ")[0].strip()

    try:
        # Refresquem la pàgina per obtenir l'estat actual de Bet365.
        page.reload(wait_until="domcontentloaded", timeout=BET365_TIMEOUT_MS)
        page.wait_for_timeout(BET365_WAIT_MS)
        _bet365_accept_cookies(page)
        page.wait_for_timeout(1500)

        game = _bet365_find_market_container(page, home, away)
        if not game:
            return None

        text = game.inner_text()
        market = snapshot["market"]
        side = snapshot["side"]
        points = snapshot.get("points")

        if market == "total":
            return _bet365_extract_total(text, side, points)
        if market == "spread":
            return _bet365_extract_spread(text, side, points)
        if market == "moneyline":
            return _bet365_extract_moneyline(text, side)
    except Exception as e:
        print(f"BET365 ERROR: {type(e).__name__}: {e}", flush=True)
        return None

    return None

def close_bet365():
    global _bet365_pw, _bet365_browser, _bet365_context, _bet365_page
    try:
        if _bet365_browser:
            _bet365_browser.close()
    except Exception:
        pass
    try:
        if _bet365_pw:
            _bet365_pw.stop()
    except Exception:
        pass
    _bet365_pw = None
    _bet365_browser = None
    _bet365_context = None
    _bet365_page = None

def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("TELEGRAM: credentials not configured; message not sent.", flush=True)
        return False
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={
                "chat_id": CHAT_ID,
                "text": message,
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        if response.status_code != 200:
            print(
                f"TELEGRAM STATUS: {response.status_code} | "
                f"{response.text[:300]}",
                flush=True,
            )
            return False
        return True
    except Exception as e:
        print(f"ERROR TELEGRAM: {type(e).__name__}: {e}", flush=True)

PINNACLE_X_API_KEY = os.getenv("PINNACLE_X_API_KEY", "")

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
if PINNACLE_X_API_KEY:
    HEADERS["X-API-Key"] = PINNACLE_X_API_KEY

session = requests.Session()
session.headers.update(HEADERS)

previous_odds = {}
previous_lines = {}
pending_steam = {}

# --- DIAGNOSTIC V22 ---
DIAG_CYCLES = 0
DIAG_SNAPSHOTS = 0
DIAG_INITIALIZED = 0
DIAG_CHANGES = 0
DIAG_SHORTENINGS = 0
DIAG_CANDIDATES = 0
DIAG_LAST_PRINT = 0
DIAG_SAMPLES = []
DIAG_SCORE_SAMPLES = []


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


def get_open_league_matchups(league_id, league_name):
    url = (
        "https://guest.api.arcadia.pinnacle.com/0.1"
        f"/leagues/{league_id}/matchups"
    )
    response = session.get(url, headers=HEADERS, timeout=30)

    # Una lliga fora de temporada o no disponible al feed pot retornar
    # 401/403/404. No volem que això ompli el terminal cada 5 segons:
    # simplement la saltem i continuem amb les altres lligues.
    if response.status_code in (401, 403, 404):
        return []

    response.raise_for_status()

    result = []

    for m in response.json():
        if m.get("type") != "matchup":
            continue

        periods = m.get("periods", [])
        p0 = next((p for p in periods if p.get("period") == 0), None)

        if not p0 or p0.get("status") != "open":
            continue

        start_time = m.get("startTime")
        if not start_time:
            continue

        try:
            dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
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
            "league_id": league_id,
            "league": league_name,
            "match": f"{away} @ {home}",
            "start": start_time,
            "hours": hours,
        })

    return result


def american_to_decimal(american):
    if american is None:
        return None
    try:
        american = float(american)
    except (TypeError, ValueError):
        return None
    if american > 0:
        return round(1 + american / 100.0, 4)
    if american < 0:
        return round(1 + 100.0 / abs(american), 4)
    return None


def get_league_main_markets(matchups, league_id):
    """
    Obté els mercats straight agregats de tota la lliga en una sola petició.
    Retorna Moneyline, Run Line/Spread i Total principal (P0, no alternate).
    """
    url = (
        "https://guest.api.arcadia.pinnacle.com/0.1"
        f"/leagues/{league_id}/markets/straight"
    )

    response = session.get(url, headers=HEADERS, timeout=30)

    # Lligues sense feed / fora de temporada: SKIP silenciós.
    if response.status_code in (401, 403, 404):
        return []

    response.raise_for_status()

    matchup_by_id = {str(m["id"]): m for m in matchups if m.get("id") is not None}
    result = []

    payload = response.json()
    if not isinstance(payload, list):
        return result

    for market in payload:
        if market.get("period") != 0:
            continue
        if market.get("isAlternate") is True:
            continue

        market_type = (market.get("type") or "").lower()

        # Normalitzem els noms que podem trobar al feed.
        if market_type in ("moneyline", "money_line", "money line"):
            normalized = "moneyline"
        elif market_type in ("spread", "runline", "run_line", "run line"):
            normalized = "spread"
        elif market_type == "total":
            normalized = "total"
        else:
            continue

        matchup_id = market.get("matchupId", market.get("matchup_id"))
        if matchup_id is None:
            continue

        matchup = matchup_by_id.get(str(matchup_id))
        if not matchup:
            continue

        for p in market.get("prices", []):
            designation = (p.get("designation") or "").lower()
            american = p.get("price")
            decimal = american_to_decimal(american)
            if decimal is None:
                continue

            # Moneyline: home/away.
            if normalized == "moneyline":
                if designation not in ("home", "away"):
                    continue
                points = 0.0

            # Spread / Run Line: conservar totes les línies ofertes.
            elif normalized == "spread":
                if designation not in ("home", "away"):
                    continue
                points = p.get("points")
                if points is None:
                    continue
                try:
                    points = float(points)
                except (TypeError, ValueError):
                    continue

            # Total: Over/Under.
            else:
                if designation not in ("over", "under"):
                    continue
                points = p.get("points")
                if points is None:
                    continue
                try:
                    points = float(points)
                except (TypeError, ValueError):
                    continue

            result.append({
                "matchup_id": matchup["id"],
                "league_id": matchup["league_id"],
                "league": matchup["league"],
                "match": matchup["match"],
                "start": matchup["start"],
                "hours": matchup["hours"],
                "market": normalized,
                "side": designation,
                "points": points,
                "american": american,
                "decimal": decimal,
            })

    return result

STEAM_LOG_FILE = "steam_signals.csv"
STEAM_LOG_FIELDS = [
    "timestamp", "matchup_id", "league_id", "league", "match", "start",
    "market", "side", "points", "old_odds", "new_odds", "movement_pct",
    "steam_score", "strength", "profile_match", "bet365_odds", "value_status"
]


def _ensure_steam_log():
    p = Path(STEAM_LOG_FILE)
    if not p.exists():
        with p.open("w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=STEAM_LOG_FIELDS).writeheader()


def _matching_profiles(market, score, strength):
    matches = []
    for smin, smax, stmin, stmax in MARKET_PROFILES.get(market, []):
        if smin <= score < smax and stmin <= strength < stmax:
            matches.append(f"S{smin:g}-{smax:g}/STR{stmin:g}-{stmax:g}")
    return matches


def _selection_label(snapshot):
    market = snapshot["market"]
    side = snapshot["side"].upper()
    points = snapshot.get("points")
    if market == "moneyline":
        return side
    if market == "spread":
        return f"{side} {points:g}" if isinstance(points, float) else f"{side} {points}"
    return f"{side} {points:g}" if isinstance(points, float) else f"{side} {points}"


def log_steam_signal(snapshot, old_odd, new_odd, score, strength, profiles):
    _ensure_steam_log()
    with Path(STEAM_LOG_FILE).open("a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=STEAM_LOG_FIELDS).writerow({
            "timestamp": datetime.now().isoformat(),
            "matchup_id": snapshot.get("matchup_id", ""),
            "league_id": snapshot.get("league_id", ""),
            "league": snapshot.get("league", ""),
            "match": snapshot.get("match", ""),
            "start": snapshot.get("start", ""),
            "market": snapshot.get("market", ""),
            "side": snapshot.get("side", ""),
            "points": snapshot.get("points", ""),
            "old_odds": old_odd,
            "new_odds": new_odd,
            "movement_pct": score,
            "steam_score": score,
            "strength": strength,
            "profile_match": " | ".join(profiles),
            "bet365_odds": "",
            "value_status": "PENDING_BET365",
        })


def process_snapshot(snapshot):
    global DIAG_SNAPSHOTS, DIAG_INITIALIZED, DIAG_CHANGES
    global DIAG_SHORTENINGS, DIAG_CANDIDATES, DIAG_SAMPLES

    DIAG_SNAPSHOTS += 1

    key = (
        snapshot["league_id"], snapshot["matchup_id"], snapshot["market"],
        snapshot["side"], snapshot["points"],
    )
    new_odd = snapshot.get("decimal")
    if new_odd is None:
        return

    if key not in previous_odds:
        previous_odds[key] = new_odd
        DIAG_INITIALIZED += 1
        return

    old_odd = previous_odds[key]
    if old_odd == new_odd:
        return

    DIAG_CHANGES += 1

    # Moviment decimal real, en percentatge.
    movement = ((old_odd - new_odd) / old_odd) * 100.0

    if movement > 0:
        DIAG_SHORTENINGS += 1
    if len(DIAG_SAMPLES) < 12:
        DIAG_SAMPLES.append(
            f"{snapshot.get('market')} {snapshot.get('side')} "
            f"{old_odd:.4f}->{new_odd:.4f} ({movement:.3f}%)"
        )

    previous_odds[key] = new_odd

    # Diagnòstic 2: mostrem també quin score produeix la funció actual.
    score = steam_score(movement)
    if len(DIAG_SCORE_SAMPLES) < 12:
        DIAG_SCORE_SAMPLES.append(
            f"{snapshot.get('market')} {snapshot.get('side')} "
            f"mov={movement:.3f}% -> score={score}"
        )

    # IMPORTANT: no canviem encara el filtre original.
    if movement < STEAM_SCORE_MIN or movement >= STEAM_SCORE_MAX:
        pending_steam.pop(key, None)
        return

    DIAG_CANDIDATES += 1
    strength = strength_from_steam(score)
    profiles = _matching_profiles(snapshot["market"], score, strength)
    if not profiles:
        pending_steam.pop(key, None)
        return

    pending_steam[key] = {
        "timestamp": time.time(),
        "old_odd": old_odd,
        "new_odd": new_odd,
        "score": score,
        "strength": strength,
        "snapshot": dict(snapshot),
        "profiles": profiles,
    }


def diagnostic_heartbeat(cycle):
    global DIAG_LAST_PRINT
    now = time.time()
    if now - DIAG_LAST_PRINT < 60:
        return
    DIAG_LAST_PRINT = now

    print(
        f"🔎 DIAG | cycle={cycle} | snapshots={DIAG_SNAPSHOTS} | "
        f"initial={DIAG_INITIALIZED} | changes={DIAG_CHANGES} | "
        f"shortenings={DIAG_SHORTENINGS} | candidates={DIAG_CANDIDATES} | "
        f"pending={len(pending_steam)}",
        flush=True
    )

    if DIAG_SAMPLES:
        for sample in DIAG_SAMPLES[-4:]:
            print(f"   ↳ {sample}", flush=True)

    if DIAG_SCORE_SAMPLES:
        print("   SCORE CHECK:", flush=True)
        for sample in DIAG_SCORE_SAMPLES[-4:]:
            print(f"   ↳ {sample}", flush=True)

def _daily_value_bet_count():
    today = datetime.now().date().isoformat()
    p = Path(BANKROLL_FILE)
    if not p.exists():
        return 0
    count = 0
    with p.open("r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("timestamp", "")[:10] == today and row.get("result") in {"PENDING", "WIN", "LOSS", "PUSH"}:
                count += 1
    return count

def _already_bet_match(matchup_id):
    p = Path(BANKROLL_FILE)
    if not p.exists():
        return False
    with p.open("r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if str(row.get("matchup_id")) == str(matchup_id):
                return True
    return False

def check_confirmations():
    now = time.time()

    for key in list(pending_steam.keys()):
        data = pending_steam[key]
        if now - data["timestamp"] < STEAM_CONFIRMATION_SECONDS:
            continue

        snapshot = data["snapshot"]
        current = previous_odds.get(key)
        if current is None:
            del pending_steam[key]
            continue

        # Si el preu torna a pujar respecte del nou preu, la confirmació cau.
        if current > data["new_odd"]:
            del pending_steam[key]
            continue

        score = data["score"]
        strength = data["strength"]
        profiles = data["profiles"]
        selection = _selection_label(snapshot)
        market_label = {
            "moneyline": "MONEYLINE",
            "spread": "RUN LINE",
            "total": "TOTAL",
        }.get(snapshot["market"], snapshot["market"].upper())

        # 1) STEAM sempre: primer el registrem i l'enviem.
        steam_log_snapshot = dict(snapshot)
        log_steam_signal(
            steam_log_snapshot,
            data["old_odd"],
            current,
            score,
            strength,
            profiles,
        )

        # 2) Bet365: només ara, amb el partit i mercat exactes.
        bet365_odds = get_bet365_odds(snapshot)

        # 3) VALUE real segons la quota Bet365 observada.
        value_status = "NO VALUE"
        edge = None
        if bet365_odds is not None:
            edge = value_edge(bet365_odds)
            if bet365_odds >= MIN_VALUE_ODDS:
                value_status = "VALUE"
            else:
                value_status = "NO VALUE — quota inferior al llindar"

        # Actualitzem la fila STEAM amb el resultat Bet365.
        try:
            p = Path(STEAM_LOG_FILE)
            if p.exists():
                rows = []
                with p.open("r", newline="", encoding="utf-8") as f:
                    rows = list(csv.DictReader(f))
                for row in reversed(rows):
                    if (
                        row.get("matchup_id") == str(snapshot.get("matchup_id"))
                        and row.get("market") == str(snapshot.get("market"))
                        and row.get("side") == str(snapshot.get("side"))
                        and row.get("points") == str(snapshot.get("points"))
                        and row.get("bet365_odds", "") == ""
                    ):
                        row["bet365_odds"] = "" if bet365_odds is None else bet365_odds
                        row["value_status"] = value_status
                        break
                with p.open("w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=STEAM_LOG_FIELDS)
                    writer.writeheader()
                    writer.writerows(rows)
        except Exception as e:
            print(f"ERROR UPDATE STEAM LOG: {type(e).__name__}: {e}", flush=True)

        # 4) Només VALUE entra al bankroll.
        bankroll_created = False
        if value_status == "VALUE":
            if _daily_value_bet_count() >= 10:
                value_status = "VALUE — NO BET (límit 10/dia)"
            elif _already_bet_match(snapshot["matchup_id"]):
                value_status = "VALUE — NO BET (1 aposta per partit)"
            else:
                value_snapshot = dict(snapshot)
                value_snapshot["steam_score"] = score
                value_snapshot["strength"] = strength
                value_snapshot["probability"] = MODEL_PROBABILITY
                value_snapshot["fair_odds"] = 1.0 / MODEL_PROBABILITY
                value_snapshot["min_value_odds"] = MIN_VALUE_ODDS
                settle_simulated_bet(value_snapshot, float(bet365_odds), "PENDING")
                bankroll_created = True

        steam_msg = (
            "⚾ 🎯 STEAM CONFIRMAT\n"
            f"🏆 {snapshot['league']}\n"
            f"⚾ {snapshot['match']}\n"
            f"📊 {market_label}: {selection}\n"
            f"📉 Pinnacle: {data['old_odd']} → {current}\n"
            f"🔥 Steam Score: {score:.2f} | Strength: {strength:.1f}\n"
            f"🎯 Perfil: {', '.join(profiles)}\n"
            f"📈 Model P: {MODEL_PROBABILITY:.2%}\n"
            f"⚖️ Fair odds: {1.0 / MODEL_PROBABILITY:.3f}\n"
            f"🎯 Quota mínima VALUE: {MIN_VALUE_ODDS:.3f}\n"
        )

        if bet365_odds is None:
            steam_msg += "💰 Bet365: NO DISPONIBLE / partit o mercat no trobat\n"
            steam_msg += "🚫 VALUE: NO BET"
        else:
            steam_msg += f"💰 Bet365: {bet365_odds:.2f}\n"
            if edge is not None:
                steam_msg += f"📐 Edge: {edge:+.2%}\n"
            if bankroll_created:
                steam_msg += "🟢 VALUE CONFIRMAT — PENDENT DE RESULTAT\n"
                steam_msg += f"💶 Stake paper: {BANKROLL_STATE['bank'] * STAKE_PCT:.2f} €"
            else:
                steam_msg += f"🔴 {value_status}"

        steam_msg += "\n📝 PAPER TEST — sense aposta real"

        send_telegram(steam_msg)

        print("", flush=True)
        print("  " + "=" * 76, flush=True)
        print("  🎯 STEAM CONFIRMAT", flush=True)
        print(f"  League:      {snapshot['league']}", flush=True)
        print(f"  Match:       {snapshot['match']}", flush=True)
        print(f"  Market:      {market_label}", flush=True)
        print(f"  Selection:   {selection}", flush=True)
        print(f"  Pinnacle:    {data['old_odd']} → {current}", flush=True)
        print(f"  Steam Score: {score:.2f}", flush=True)
        print(f"  Strength:    {strength:.1f}", flush=True)
        print(f"  Profile:     {' | '.join(profiles)}", flush=True)
        print(f"  Bet365:      {'NO DISPONIBLE' if bet365_odds is None else f'{bet365_odds:.2f}'}", flush=True)
        print(f"  VALUE:       {value_status}", flush=True)
        print("  " + "=" * 76, flush=True)

        del pending_steam[key]


# ---------------------------------------------------------------------------
# RESULTATS AUTOMÀTICS
# ---------------------------------------------------------------------------
# Els resultats es resolen des de les dades de partits/resultats de la font
# de baseball. No es demana cap entrada manual.
RESULT_FIELDS = [
    "matchup_id", "league_id", "league", "match", "start",
    "market", "side", "points", "bet365_odds", "status",
    "home_score", "away_score", "result", "resolved_at"
]

def _ensure_results_file():
    p = Path(RESULTS_FILE)
    if not p.exists():
        with p.open("w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=RESULT_FIELDS).writeheader()

def _load_unresolved_bets():
    """
    Recupera apostes VALUE pendents del CSV de bankroll.
    La columna result buida significa pendent.
    """
    p = Path(BANKROLL_FILE)
    if not p.exists():
        return []

    pending = []
    with p.open("r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not row.get("result"):
                pending.append(row)
    return pending

def _parse_score_value(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

def resolve_finished_bets():
    """
    Intenta resoldre automàticament les apostes pendents.

    IMPORTANT:
    - Resol TOTAL, RUN LINE i MONEYLINE que el scanner ha registrat.
    - No inventa cap resultat si la font no retorna un marcador fiable.
    - En cas de dubte, deixa l'aposta pendent.
    """
    pending = _load_unresolved_bets()
    if not pending:
        return 0

    resolved = 0
    _ensure_results_file()

    # Índex dels registres ja resolts.
    resolved_ids = set()
    rp = Path(RESULTS_FILE)
    with rp.open("r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (
                row.get("matchup_id"),
                row.get("market"),
                row.get("side"),
                row.get("points"),
            )
            if row.get("result"):
                resolved_ids.add(key)

    for bet in pending:
        key = (
            bet.get("matchup_id"),
            bet.get("market"),
            bet.get("side"),
            bet.get("points"),
        )
        if key in resolved_ids:
            continue

        # La resolució definitiva s'ha de fer quan el scanner tingui
        # una font de resultats per al matchup. Aquesta funció queda
        # preparada per consumir-la sense tocar el motor de bankroll.
        result_data = fetch_final_result(
            bet.get("league_id"),
            bet.get("matchup_id")
        )

        if not result_data:
            continue

        home_score = _parse_score_value(result_data.get("home_score"))
        away_score = _parse_score_value(result_data.get("away_score"))
        if home_score is None or away_score is None:
            continue

        side = str(bet.get("side", "")).upper()
        market = str(bet.get("market", "")).lower()

        if market == "total":
            points = float(bet.get("points"))
            total = home_score + away_score
            if side == "OVER":
                result = "WIN" if total > points else "LOSS" if total < points else "PUSH"
            elif side == "UNDER":
                result = "WIN" if total < points else "LOSS" if total > points else "PUSH"
            else:
                continue

        elif market == "spread":
            points = float(bet.get("points"))
            # El punt del spread s'aplica al costat seleccionat.
            selected_score = home_score if side == "HOME" else away_score
            other_score = away_score if side == "HOME" else home_score
            adjusted = selected_score + points
            if adjusted > other_score:
                result = "WIN"
            elif adjusted < other_score:
                result = "LOSS"
            else:
                result = "PUSH"

        elif market == "moneyline":
            if side == "HOME":
                result = "WIN" if home_score > away_score else "LOSS" if home_score < away_score else "PUSH"
            elif side == "AWAY":
                result = "WIN" if away_score > home_score else "LOSS" if away_score < home_score else "PUSH"
            else:
                continue

        else:
            continue

        # Actualitza la línia corresponent del bankroll.
        update_bankroll_result(
            matchup_id=bet.get("matchup_id"),
            market=bet.get("market"),
            side=bet.get("side"),
            points=bet.get("points"),
            result=result,
            bet365_odds=float(bet.get("bet365_odds"))
        )

        with rp.open("a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=RESULT_FIELDS).writerow({
                "matchup_id": bet.get("matchup_id"),
                "league_id": bet.get("league_id"),
                "league": bet.get("league"),
                "match": bet.get("match"),
                "start": bet.get("start"),
                "market": bet.get("market"),
                "side": bet.get("side"),
                "points": bet.get("points"),
                "bet365_odds": bet.get("bet365_odds"),
                "status": "finished",
                "home_score": home_score,
                "away_score": away_score,
                "result": result,
                "resolved_at": datetime.now().isoformat(),
            })

        resolved += 1
        print(
            f"🏁 RESULTAT | [{bet.get('league')}] {bet.get('match')} | "
            f"{side} {points} | {home_score}-{away_score} | {result}",
            flush=True
        )

    return resolved

def update_bankroll_result(matchup_id, market, side, points, result, bet365_odds):
    """
    Actualitza una aposta pendent del CSV de bankroll i recalcula el bank
    a partir de la seqüència cronològica. Això evita aplicar dues vegades
    el mateix resultat.
    """
    p = Path(BANKROLL_FILE)
    if not p.exists():
        return False

    with p.open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    target = None
    for row in rows:
        if (
            row.get("matchup_id") == str(matchup_id)
            and row.get("market") == str(market)
            and row.get("side") == str(side)
            and row.get("points") == str(points)
            and not row.get("result")
        ):
            target = row
            break

    if target is None:
        return False

    # Recalcula el bank des del bank inicial, mantenint l'ordre cronològic.
    rows_sorted = sorted(rows, key=lambda r: r.get("timestamp", ""))
    bank = INITIAL_BANK_EUR
    peak = bank

    for row in rows_sorted:
        stake = bank * STAKE_PCT
        row["bank_before"] = bank
        row["stake"] = stake

        row_result = row.get("result", "")
        odds = float(row.get("bet365_odds") or 0)

        if row is target:
            row_result = result
            row["result"] = result

        if row_result == "WIN":
            profit = stake * (odds - 1.0)
        elif row_result == "LOSS":
            profit = -stake
        elif row_result == "PUSH":
            profit = 0.0
        else:
            profit = 0.0

        bank += profit
        peak = max(peak, bank)

        row["profit"] = profit
        row["bank_after"] = bank
        row["roi_stake"] = profit / stake if stake else 0.0
        row["bank_return"] = profit / row["bank_before"] if row["bank_before"] else 0.0
        row["drawdown_eur"] = bank - peak
        row["drawdown_pct"] = (bank - peak) / peak if peak else 0.0

    with p.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=BANKROLL_FIELDS)
        writer.writeheader()
        writer.writerows(rows_sorted)

    BANKROLL_STATE["bank"] = bank
    BANKROLL_STATE["peak"] = peak
    return True

def fetch_final_result(league_id, matchup_id):
    """
    Recupera l'estat i el marcador final del matchup directament de
    l'API de Pinnacle/Arcadia.

    No resol una aposta mentre el matchup no consti com a finalitzat
    i no hi hagi dos marcadors enters verificables.
    """
    if not league_id or not matchup_id:
        return None

    url = (
        "https://guest.api.arcadia.pinnacle.com/0.1"
        f"/leagues/{league_id}/matchups/{matchup_id}"
    )

    try:
        response = session.get(url, headers=HEADERS, timeout=30)
        if response.status_code != 200:
            return None

        data = response.json()
    except Exception:
        return None

    # Diferents respostes poden exposar l'estat amb noms lleugerament
    # diferents. Només acceptem un estat inequívocament final.
    status = str(
        data.get("status")
        or data.get("matchupStatus")
        or data.get("state")
        or ""
    ).lower()

    final_statuses = {
        "final", "finished", "closed", "settled",
        "complete", "completed"
    }

    # Alguns endpoints exposen el resultat dins periods.
    periods = data.get("periods") or []
    p0 = next((p for p in periods if p.get("period") == 0), None)

    if p0:
        period_status = str(
            p0.get("status") or p0.get("state") or ""
        ).lower()
        if period_status in final_statuses:
            status = period_status

    if status not in final_statuses:
        return None

    # Intent 1: participants amb score/result.
    home_score = None
    away_score = None

    participants = data.get("participants") or []
    for participant in participants:
        alignment = str(participant.get("alignment") or "").lower()
        score = (
            participant.get("score")
            if participant.get("score") is not None
            else participant.get("points")
        )

        try:
            score = int(score)
        except (TypeError, ValueError):
            score = None

        if alignment == "home" and score is not None:
            home_score = score
        elif alignment == "away" and score is not None:
            away_score = score

    # Intent 2: resultats directes de l'objecte.
    if home_score is None:
        for key in ("homeScore", "home_score", "scoreHome"):
            try:
                home_score = int(data.get(key))
                break
            except (TypeError, ValueError):
                pass

    if away_score is None:
        for key in ("awayScore", "away_score", "scoreAway"):
            try:
                away_score = int(data.get(key))
                break
            except (TypeError, ValueError):
                pass

    if home_score is None or away_score is None:
        return None

    return {
        "status": "finished",
        "home_score": home_score,
        "away_score": away_score,
    }

# ---------------------------------------------------------------------------
# BANKROLL / ROI
# ---------------------------------------------------------------------------
# La simulació només s'aplica a apostes VALUE confirmades i amb quota Bet365
# disponible. Si no hi ha quota Bet365, es registra STEAM però NO es simula
# cap aposta.
BANKROLL_STATE = {
    "bank": INITIAL_BANK_EUR,
    "peak": INITIAL_BANK_EUR,
    "max_drawdown_eur": 0.0,
    "max_drawdown_pct": 0.0,
}

BANKROLL_FIELDS = [
    "timestamp", "week", "matchup_id", "league_id", "league", "match", "market", "side", "points",
    "steam_score", "strength", "probability", "fair_odds", "bet365_odds",
    "min_value_odds", "stake_pct", "bank_before", "stake",
    "result", "profit", "bank_after", "roi_stake", "bank_return",
    "drawdown_eur", "drawdown_pct"
]

def _week_id(dt=None):
    dt = dt or datetime.now()
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"

def _ensure_bankroll_file():
    p = Path(BANKROLL_FILE)
    if not p.exists():
        with p.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=BANKROLL_FIELDS)
            writer.writeheader()

def settle_simulated_bet(snapshot, bet365_odds, result):
    """
    Simula una aposta amb stake = 3% del bank disponible.
    result: WIN / LOSS / PUSH.
    """
    if not bet365_odds or bet365_odds <= 1:
        return None

    bank_before = BANKROLL_STATE["bank"]
    stake = bank_before * STAKE_PCT

    if result == "WIN":
        profit = stake * (bet365_odds - 1.0)
    elif result == "LOSS":
        profit = -stake
    elif result == "PUSH":
        profit = 0.0
    elif result == "PENDING":
        profit = 0.0
    else:
        raise ValueError(f"Resultat desconegut: {result}")

    bank_after = bank_before + profit
    BANKROLL_STATE["bank"] = bank_after

    if bank_after > BANKROLL_STATE["peak"]:
        BANKROLL_STATE["peak"] = bank_after

    drawdown_eur = bank_after - BANKROLL_STATE["peak"]
    drawdown_pct = (
        drawdown_eur / BANKROLL_STATE["peak"]
        if BANKROLL_STATE["peak"] else 0.0
    )

    BANKROLL_STATE["max_drawdown_eur"] = min(
        BANKROLL_STATE["max_drawdown_eur"], drawdown_eur
    )
    BANKROLL_STATE["max_drawdown_pct"] = min(
        BANKROLL_STATE["max_drawdown_pct"], drawdown_pct
    )

    roi_stake = profit / stake if stake else 0.0
    bank_return = profit / bank_before if bank_before else 0.0

    row = {
        "timestamp": datetime.now().isoformat(),
        "week": _week_id(),
        "matchup_id": snapshot.get("matchup_id", ""),
        "league_id": snapshot.get("league_id", ""),
        "league": snapshot.get("league", ""),
        "match": snapshot.get("match", ""),
        "market": snapshot.get("market", "TOTAL"),
        "side": snapshot.get("side", ""),
        "points": snapshot.get("points", ""),
        "steam_score": snapshot.get("steam_score", ""),
        "strength": snapshot.get("strength", ""),
        "probability": snapshot.get("probability", MODEL_PROBABILITY),
        "fair_odds": snapshot.get("fair_odds", ""),
        "bet365_odds": bet365_odds,
        "min_value_odds": snapshot.get("min_value_odds", ""),
        "stake_pct": STAKE_PCT,
        "bank_before": bank_before,
        "stake": stake,
        "result": result,
        "profit": profit,
        "bank_after": bank_after,
        "roi_stake": roi_stake,
        "bank_return": bank_return,
        "drawdown_eur": drawdown_eur,
        "drawdown_pct": drawdown_pct,
    }

    _ensure_bankroll_file()
    with Path(BANKROLL_FILE).open("a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=BANKROLL_FIELDS).writerow(row)

    return row

def generate_weekly_report(week=None):
    """
    Genera el resum de la setmana a partir del CSV persistent.
    Si week és None, utilitza la setmana ISO actual.
    """
    _ensure_bankroll_file()
    target_week = week or _week_id()
    rows = []

    with Path(BANKROLL_FILE).open("r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("week") == target_week:
                rows.append(row)

    settled = [r for r in rows if r.get("result") in {"WIN", "LOSS", "PUSH"}]
    if not settled:
        return None

    report = weekly_roi_report(settled)

    print(
        f"📅 SETMANA {target_week} | "
        f"{report['bets']} apostes | "
        f"W{report['wins']}/L{report['losses']}/P{report['pushes']} | "
        f"Bank {report['bank_initial']:.2f}€ → {report['bank_final']:.2f}€ | "
        f"Benefici {report['profit']:+.2f}€ | "
        f"ROI {report['roi']:+.2%} | "
        f"Bank {report['bank_return']:+.2%} | "
        f"DD {report['max_drawdown_eur']:.2f}€",
        flush=True
    )
    return report

def weekly_roi_report(rows):
    """Calcula el resum setmanal sobre les apostes simulades."""
    if not rows:
        return None

    wins = sum(r["result"] == "WIN" for r in rows)
    losses = sum(r["result"] == "LOSS" for r in rows)
    pushes = sum(r["result"] == "PUSH" for r in rows)
    stakes = sum(float(r["stake"]) for r in rows)
    profit = sum(float(r["profit"]) for r in rows)
    bank_initial = float(rows[0]["bank_before"])
    bank_final = float(rows[-1]["bank_after"])

    return {
        "week": rows[0]["week"],
        "bets": len(rows),
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "bank_initial": bank_initial,
        "bank_final": bank_final,
        "profit": profit,
        "roi": profit / stakes if stakes else 0.0,
        "bank_return": (bank_final / bank_initial - 1.0) if bank_initial else 0.0,
        "max_drawdown_eur": min(float(r["drawdown_eur"]) for r in rows),
        "max_drawdown_pct": min(float(r["drawdown_pct"]) for r in rows),
    }

print("🔎 BASEBALL STEAM V22 DIAGNOSTIC - 5 LEAGUES | ML + RUN LINE + TOTAL ⚾", flush=True)
print(
    "LEAGUES: " +
    " | ".join(f"{lid}={name}" for lid, name in ALLOWED_LEAGUES.items()),
    flush=True
)
print("PROFILES: ML S5-6/STR70-80 | RUN LINE S3-4/STR60-70 | TOTAL S4-5/STR70-80", flush=True)
print(
    f"VALUE: P={MODEL_PROBABILITY:.2%} | "
    f"MIN EDGE={MIN_VALUE_EDGE:.2%} | MIN ODDS={MIN_VALUE_ODDS}",
    flush=True
)
print(
    f"CONFIRMATION={STEAM_CONFIRMATION_SECONDS}s | POLL={POLL_SECONDS}s",
    flush=True
)
print(
    "PAPER TEST | NO APOSTES REALS | TELEGRAM "
    + ("ACTIU" if BOT_TOKEN and CHAT_ID else "SENSE CREDENCIALS")
    + " / NO GOOGLE SHEETS",
    flush=True
)
print(
    "PINNACLE API KEY: "
    + ("CONFIGURADA" if PINNACLE_X_API_KEY else "NO CONFIGURADA"),
    flush=True
)
print(f"BANKROLL: {INITIAL_BANK_EUR:.2f} € | STAKE: {STAKE_PCT:.1%} del bank per aposta VALUE", flush=True)
print("RESULTATS: resolució automàtica preparada; no es resol cap aposta sense marcador verificat.", flush=True)
print("MODE AUTÒNOM: només mostra esdeveniments significatius.", flush=True)
print("", flush=True)

cycle = 0
last_weekly_report_key = None

while True:
    cycle += 1

    try:
        total_matchups = 0

        for league_id, league_name in ALLOWED_LEAGUES.items():
            try:
                matchups = get_open_league_matchups(league_id, league_name)
                total_matchups += len(matchups)

                # Una sola consulta de mercats per lliga i cicle.
                snapshots = get_league_main_markets(matchups, league_id)

                for snapshot in snapshots:
                    process_snapshot(snapshot)

            except Exception as e:
                print(
                    f"ERROR LEAGUE [{league_name}] {league_id}: "
                    f"{type(e).__name__}: {e}",
                    flush=True
                )

        check_confirmations()
        # Informe setmanal automàtic quan hi ha apostes resoltes.
        try:
            current_week = _week_id()
            if current_week != last_weekly_report_key:
                report = generate_weekly_report(current_week)
                if report:
                    last_weekly_report_key = current_week
        except Exception as e:
            print(f"ERROR INFORME SETMANAL: {type(e).__name__}: {e}", flush=True)

        try:
            resolved = resolve_finished_bets()
            if resolved:
                print(f"📊 RESULTATS RESOLTS AUTOMÀTICAMENT: {resolved}", flush=True)
        except Exception as e:
            print(f"ERROR RESOLUCIÓ RESULTATS: {type(e).__name__}: {e}", flush=True)


        # Heartbeat molt discret: una línia cada 60 cicles.
        if cycle % 60 == 0:
            diagnostic_heartbeat(cycle)
            print(
                f"💓 HEARTBEAT | cycle={cycle} | "
                f"matches={total_matchups} | "
                f"{datetime.now().strftime('%H:%M:%S')}",
                flush=True
            )

    except KeyboardInterrupt:
        print("\nInterromput per l'usuari.", flush=True)
        break

    except Exception as e:
        print(
            f"ERROR CICLE: {type(e).__name__}: {e}",
            flush=True
        )

    time.sleep(POLL_SECONDS)
