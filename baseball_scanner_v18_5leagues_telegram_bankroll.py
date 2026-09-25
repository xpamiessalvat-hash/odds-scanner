# BASEBALL STEAM V11 - STEAM + VALUE TEST REAL (PAPER)
import csv
import os
import requests
import time
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

# TELEGRAM — mateixes variables que les versions anteriors
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

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

        if not p0 or not p0.get("hasTotal") or p0.get("status") != "open":
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


def get_league_main_totals(matchups, league_id):
    """
    Obté els mercats straight de tota la lliga en una sola petició i els
    indexa per matchupId. Evitem /matchups/{id}/markets/related/straight,
    que en el feed guest està retornant 403.
    """
    url = (
        "https://guest.api.arcadia.pinnacle.com/0.1"
        f"/leagues/{league_id}/markets/straight"
    )

    response = session.get(url, headers=HEADERS, timeout=30)

    # Lligues sense feed/fora de temporada: SKIP silenciós.
    if response.status_code in (401, 403, 404):
        return {}

    response.raise_for_status()

    matchup_by_id = {str(m["id"]): m for m in matchups if m.get("id") is not None}
    totals_by_matchup = {}

    payload = response.json()
    if not isinstance(payload, list):
        return {}

    for market in payload:
        if market.get("type") != "total":
            continue
        if market.get("period") != 0:
            continue
        if market.get("isAlternate") is True:
            continue

        matchup_id = market.get("matchupId")
        if matchup_id is None:
            matchup_id = market.get("matchup_id")
        if matchup_id is None:
            continue

        matchup = matchup_by_id.get(str(matchup_id))
        if not matchup:
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
            if decimal is None:
                continue

            totals_by_matchup.setdefault(str(matchup_id), []).append({
                "matchup_id": matchup["id"],
                "league_id": matchup["league_id"],
                "league": matchup["league"],
                "match": matchup["match"],
                "start": matchup["start"],
                "hours": matchup["hours"],
                "market": "total",
                "side": side,
                "points": points,
                "american": american,
                "decimal": decimal,
            })

    return totals_by_matchup


def process_snapshot(snapshot):
    key = (
        snapshot["league_id"],
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
        # Inicialització silenciosa: la quota queda guardada internament.
        return

    old_odd = previous_odds[key]

    if old_odd == new_odd:
        return

    # In this scanner, shortening odds means steam:
    # OLD decimal > NEW decimal.
    movement = ((old_odd - new_odd) / old_odd) * 100.0

    print(
        f"  MOVE | [{snapshot['league']}] {snapshot['match']} | "
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
        f"  ⏳ CANDIDAT STEAM | [{snapshot['league']}] {snapshot['match']} | "
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
                f"  ❌ CANCEL·LAT | [{snapshot['league']}] {snapshot['match']} | "
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
        print(f"  League:      {snapshot['league']}", flush=True)
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
        print(
            "  RESULT:      "
            + ("VALUE CANDIDAT (Pinnacle)" if value_status else "NO BET")
            + " | Bet365 pendent",
            flush=True,
        )
        print("  " + "=" * 76, flush=True)

        # Telegram: cada STEAM confirmat s'envia.
        steam_msg = (
            "⚾ 🎯 STEAM CONFIRMAT\n"
            f"🏆 {snapshot['league']}\n"
            f"⚾ {snapshot['match']}\n"
            f"📊 TOTAL OVER {snapshot['points']}\n"
            f"📉 Quota: {data['old_odd']} → {current}\n"
            f"🔥 Steam: {data['score']:.2f}% | Strength: {data['strength']:.1f}\n"
            f"📈 Model P: {MODEL_PROBABILITY:.2%}\n"
            f"⚖️ Fair odds: {1.0 / MODEL_PROBABILITY:.3f}\n"
            f"💰 Min VALUE: {MIN_VALUE_ODDS}\n"
            f"📌 Edge observat: {edge:.2%}\n"
            "🔎 Bet365: pendent de verificació"
        )
        send_telegram(steam_msg)

        # No etiquetem com a VALUE Bet365 fins que tinguem el preu de Bet365.
        if value_status:
            send_telegram(
                "💰 VALUE CANDIDAT — ESPERANT BET365\n"
                f"{snapshot['league']} | {snapshot['match']}\n"
                f"TOTAL OVER {snapshot['points']} @ {current}\n"
                f"Fair: {1.0 / MODEL_PROBABILITY:.3f} | "
                f"Mínim: {MIN_VALUE_ODDS}\n"
                f"Edge observat: {edge:.2%}\n"
                "⚠️ NO ÉS VALUE BET365 CONFIRMAT."
            )

        # Registrem la candidata com PENDING per poder resoldre-la després.
        if value_status:
            value_snapshot = dict(snapshot)
            value_snapshot["steam_score"] = data["score"]
            value_snapshot["strength"] = data["strength"]
            value_snapshot["probability"] = MODEL_PROBABILITY
            value_snapshot["fair_odds"] = 1.0 / MODEL_PROBABILITY
            value_snapshot["min_value_odds"] = MIN_VALUE_ODDS
            settle_simulated_bet(value_snapshot, float(current), "PENDING")

        print("", flush=True)
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
    - Només resol mercats TOTAL/OVER/UNDER que el scanner ha registrat.
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
        points = float(bet.get("points"))

        total = home_score + away_score

        if side == "OVER":
            if total > points:
                result = "WIN"
            elif total < points:
                result = "LOSS"
            else:
                result = "PUSH"
        elif side == "UNDER":
            if total < points:
                result = "WIN"
            elif total > points:
                result = "LOSS"
            else:
                result = "PUSH"
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

print("⚾ BASEBALL STEAM V18 - 5 LEAGUES | STEAM + VALUE | PAPER TEST ⚾", flush=True)
print(
    "LEAGUES: " +
    " | ".join(f"{lid}={name}" for lid, name in ALLOWED_LEAGUES.items()),
    flush=True
)
print(
    f"PROFILE: TOTAL / OVER / STEAM {STEAM_SCORE_MIN}-{STEAM_SCORE_MAX} / "
    f"STRENGTH {STRENGTH_MIN}-{STRENGTH_MAX}",
    flush=True
)
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
                totals_by_matchup = get_league_main_totals(matchups, league_id)

                for snapshots in totals_by_matchup.values():
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
