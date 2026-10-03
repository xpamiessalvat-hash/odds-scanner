import requests
import time
import os
import random
import csv
import math
from difflib import SequenceMatcher
from datetime import datetime, timezone

# ============================================================
# FOOTBALL MOVEMENT ENGINE V3.1
# Mode: SHARP COLLECTION + REAL-TIME STEAM TRIGGERS + POST-TRIGGER SNAPSHOTS
# Pinnacle is the sharp source. No Telegram, no Google Sheets, no betting.
# ============================================================

BASE_URL = "https://guest.api.arcadia.pinnacle.com"
LEAGUES_URL = f"{BASE_URL}/0.1/sports/29/leagues"

# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------

SCAN_HOURS = 12
POLL_SECONDS = 120

# We collect only meaningful shortening movements.
# This is an observation filter, NOT a betting threshold.
MIN_EPISODE_MOVEMENT = 1.0       # %
EPISODE_RESET_MINUTES = 10       # close episode after inactivity
MAX_EPISODE_MOVEMENT = 30.0      # safety filter

# ------------------------------------------------------------
# VALUE LAYER (Pinnacle fair probability -> manual Bet365 check)
# Pinnacle is used only as the sharp probability source.
# The user checks the Bet365 price manually after receiving the pick.
# No Bet365 API is used by this engine.
# ------------------------------------------------------------

VALUE_EDGE_TARGET_PCT = 5.0
MIN_ENTRY_ODDS = 1.80
TELEGRAM_BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID", "").strip()

VALID_SPREADS = [
    -2.5, -2.0, -1.5, -1.0, -0.5,
     0.0,  0.5,  1.0,  1.5,  2.0, 2.5
]

VALID_TOTALS = [1.5, 2.5, 3.5, 4.5]

BLOCKED_WORDS = [
    "Friendly", "Friendlies",
    "U17", "U18", "U19", "U20", "U21", "U23",
    "Youth", "Reserve", "Reserves",
    "Corners", "Esports", "Simulation",
    "Women", "3rd Division", "4. Liga",
    "Amateur", "Regional", "Kolmonen", "Kakkonen",
    "Division 1 Women", "NPL"
]

BLOCKED_MATCH_WORDS = [
    "(Corners)", "(Corner)",
    "(Bookings)", "(Booking)",
    "(Cards)", "(Card)",
    "(Throw-ins)", "(Throw In)",
    "(Offsides)", "(Offside)",
    "(Shots)", "(Shot)",
    "(Penalties)", "(Penalty)"
]

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
    "Connection": "keep-alive"
}

session = requests.Session()
session.headers.update(HEADERS)

# ------------------------------------------------------------
# STATE
# ------------------------------------------------------------

previous_odds = {}

# One active episode per market/side/line.
episodes = {}

# Number of completed episodes written to disk.
completed_episodes = 0
triggered_signals = 0
value_signals = 0

CSV_FILE = "football_episodes_ah1_ou25_v3_1.csv"
TRIGGER_CSV_FILE = "football_steam_triggers_v2.csv"
SNAPSHOT_CSV_FILE = "football_steam_snapshots_v1.csv"
VALUE_CSV_FILE = "football_value_triggers_v2.csv"
CLOSING_CSV_FILE = "football_closing_v1.csv"
RESULT_CSV_FILE = "football_results_v1.csv"
MASTER_CSV_FILE = "football_signal_master_v1.csv"

# ------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------

def american_to_decimal(price):
    if price is None:
        return None

    if price > 0:
        return round((price / 100) + 1, 3)

    return round((100 / abs(price)) + 1, 3)


def is_blocked_league(name):
    name = name or ""
    return any(word.lower() in name.lower() for word in BLOCKED_WORDS)


def is_blocked_match(match_name):
    name = match_name or ""
    return any(word.lower() in name.lower() for word in BLOCKED_MATCH_WORDS)


def ensure_csv():
    if os.path.exists(CSV_FILE):
        return

    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "episode_id", "timestamp_start", "timestamp_end",
            "league", "match", "matchup_id", "market", "line",
            "selected_side", "selected_points",
            "selected_start_odd", "selected_end_odd",
            "selected_movement_pct", "opposite_movement_pct",
            "opposite_side", "opposite_points",
            "opposite_start_odd", "opposite_end_odd",
            "steam_dominance_pct", "observations", "duration_minutes",
            "hours_until_match_start", "movement_score",
            "persistence_score", "timing_score", "fvs_score"
        ])

def ensure_trigger_csv():
    if os.path.exists(TRIGGER_CSV_FILE):
        return

    with open(TRIGGER_CSV_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "trigger_id", "timestamp_trigger",
            "league", "match", "matchup_id",
            "market", "line", "selected_side", "selected_points",
            "pinnacle_odd_at_trigger", "opposite_odd_at_trigger",
            "movement_score", "persistence_score", "timing_score",
            "steam_dominance_pct", "fvs_score",
            "hours_until_match_start", "status", "pinnacle_source"
        ])


def ensure_snapshot_csv():
    if os.path.exists(SNAPSHOT_CSV_FILE):
        return

    with open(SNAPSHOT_CSV_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "trigger_id", "snapshot_label", "timestamp_snapshot",
            "minutes_from_trigger", "league", "match", "matchup_id",
            "market", "line", "selected_side", "selected_points",
            "pinnacle_selected_odd", "pinnacle_opposite_odd",
            "pinnacle_fair_prob_pct", "min_value_odds", "edge_at_min_odds_pct",
            "movement_from_trigger_pct", "fvs_at_trigger",
            "hours_until_match_start", "snapshot_status"
        ])


# trigger snapshots are collected at T0, +5, +15 and +30 minutes.
# The trigger itself stores the selected Pinnacle side and its opposite.
snapshot_schedule = [0, 5, 15, 30]


def write_snapshot(ep, label, now_ts, status="FOLLOWUP"):
    trigger_time = ep.get("trigger_time")
    if trigger_time is None:
        return

    minutes = (now_ts - trigger_time) / 60.0
    if minutes < 0:
        return

    selected_odd = ep.get("trigger_selected_odd")
    opposite_odd = ep.get("trigger_opposite_odd")
    if selected_odd is None or opposite_odd is None:
        return

    # Avoid duplicate snapshot labels for the same trigger.
    seen = ep.setdefault("snapshots_written", set())
    if label in seen:
        return

    current_selected = ep.get("steam_last_odd")
    current_opposite = ep.get("opposite_last_odd")

    if ep.get("trigger_selected_side") != ep.get("steam_side"):
        current_selected, current_opposite = current_opposite, current_selected

    if current_selected is None or current_opposite is None:
        return

    movement_from_trigger = (
        ((selected_odd - current_selected) / selected_odd) * 100.0
        if selected_odd else 0.0
    )

    with open(SNAPSHOT_CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            ep["trigger_id"],
            label,
            datetime.fromtimestamp(now_ts, timezone.utc).isoformat(),
            round(minutes, 2),
            ep["league"],
            ep["match"],
            ep["matchup_id"],
            ep["market"],
            ep["ah_line"],
            ep["trigger_selected_side"],
            ep["trigger_selected_points"],
            round(current_selected, 3),
            round(current_opposite, 3),
            round(ep.get("pinnacle_fair_prob_pct", 0.0), 3),
            round(ep.get("min_value_odds", 0.0), 3),
            round(ep.get("edge_at_min_odds_pct", 0.0), 3),
            round(movement_from_trigger, 3),
            round(ep.get("trigger_fvs", 0.0), 2),
            round(max(0.0, ep["hours_until_match_start"] - minutes / 60.0), 2),
            status
        ])

    seen.add(label)


def maybe_write_due_snapshots(ep, now_ts):
    trigger_time = ep.get("trigger_time")
    if trigger_time is None:
        return

    elapsed_minutes = (now_ts - trigger_time) / 60.0
    for target in snapshot_schedule:
        label = f"T+{target}m"
        # Write once the scheduled point has been reached.
        if elapsed_minutes >= target:
            write_snapshot(ep, label, now_ts)


def ensure_value_csv():
    if os.path.exists(VALUE_CSV_FILE):
        return

    with open(VALUE_CSV_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "trigger_id", "timestamp_value",
            "league", "match", "matchup_id",
            "market", "line", "selected_side", "selected_points",
            "pinnacle_selected_odd", "pinnacle_opposite_odd",
            "pinnacle_fair_prob_pct", "fair_odds", "min_value_odds",
            "edge_at_min_odds_pct", "min_entry_odds",
            "value_status", "telegram_sent"
        ])

def calculate_pinnacle_value(pinnacle_selected_odd, pinnacle_opposite_odd):
    """
    Convert the two-sided Pinnacle market into a no-vig fair probability.
    The minimum price required for the configured target EV is:
        target_odds = (1 + target_edge) / fair_probability
    The user's Bet365 price is checked manually after the Telegram alert.
    """
    if not pinnacle_selected_odd or not pinnacle_opposite_odd:
        return None
    if pinnacle_selected_odd <= 1 or pinnacle_opposite_odd <= 1:
        return None

    p_sel_raw = 1.0 / pinnacle_selected_odd
    p_opp_raw = 1.0 / pinnacle_opposite_odd
    p_total = p_sel_raw + p_opp_raw
    if p_total <= 0:
        return None

    fair_prob = p_sel_raw / p_total
    fair_odds = 1.0 / fair_prob
    min_value_odds = max(MIN_ENTRY_ODDS, (1.0 + VALUE_EDGE_TARGET_PCT / 100.0) / fair_prob)
    edge_at_min_odds = (fair_prob * min_value_odds - 1.0) * 100.0

    return fair_prob * 100.0, fair_odds, min_value_odds, edge_at_min_odds

def send_telegram(text_message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text_message,
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        response.raise_for_status()
        return bool(response.json().get("ok"))
    except Exception as exc:
        print(f"⚠️ Telegram send failed: {exc}", flush=True)
        return False

def capture_value(ep, now_ts):
    """Create a Pinnacle-only VALUE candidate and send it to Telegram once.

    Bet365 is deliberately NOT queried. The Telegram message contains the
    minimum Bet365 decimal odds required for the configured 5% EV target.
    The user verifies the live Bet365 price manually.
    """
    global value_signals

    if ep.get("value_captured", False):
        return

    calc = calculate_pinnacle_value(
        ep.get("trigger_selected_odd"),
        ep.get("trigger_opposite_odd"),
    )
    if not calc:
        return

    fair_prob, fair_odds, min_value_odds, edge_at_min_odds = calc

    # Only send a VALUE candidate when the configured minimum price is valid.
    # MIN_ENTRY_ODDS is the absolute floor; the actual required price may be higher.
    ep["pinnacle_fair_prob_pct"] = fair_prob
    ep["pinnacle_fair_odds"] = fair_odds
    ep["min_value_odds"] = min_value_odds
    ep["edge_at_min_odds_pct"] = edge_at_min_odds
    ep["value_status"] = "VALUE_CANDIDATE"

    telegram_text = (
        "💰 VALUE PICK\n"
        f"{ep['league']}\n"
        f"{ep['match']}\n"
        f"{ep['market'].upper()} | {ep['trigger_selected_side']} {ep['trigger_selected_points']:+.1f}\n"
        f"Pinnacle: {ep['trigger_selected_odd']:.3f} vs {ep['trigger_opposite_odd']:.3f}\n"
        f"Fair probability: {fair_prob:.2f}%\n"
        f"Fair odds: {fair_odds:.3f}\n"
        f"VALUE ≥ {min_value_odds:.3f} (EV target {VALUE_EDGE_TARGET_PCT:.1f}%)\n"
        f"FVS: {ep['trigger_fvs']:.1f} | Movement: {ep['trigger_movement_score']:.2f}%\n"
        f"T-{ep['trigger_hours']:.2f}h\n"
        "🔎 Comprova la quota Bet365 manualment."
    )

    sent = send_telegram(telegram_text)
    ep["telegram_sent"] = sent
    value_signals += 1

    with open(VALUE_CSV_FILE, "a", newline="", encoding="utf-8") as f:
        csv.writer(f, delimiter=";").writerow([
            ep["trigger_id"],
            datetime.fromtimestamp(now_ts, timezone.utc).isoformat(),
            ep["league"], ep["match"], ep["matchup_id"],
            ep["market"], ep["ah_line"], ep["trigger_selected_side"],
            ep["trigger_selected_points"],
            round(ep["trigger_selected_odd"], 3),
            round(ep["trigger_opposite_odd"], 3),
            round(fair_prob, 3), round(fair_odds, 3),
            round(min_value_odds, 3), round(edge_at_min_odds, 3),
            MIN_ENTRY_ODDS, "VALUE_CANDIDATE", "YES" if sent else "NO"
        ])

    print(
        f"💰 VALUE | {ep['match']} | {ep['trigger_selected_side']} "
        f"| Fair={fair_prob:.2f}% | MIN_ODDS={min_value_odds:.3f} | "
        f"Telegram={'YES' if sent else 'NO'}",
        flush=True,
    )


def ensure_master_csv():
    if os.path.exists(MASTER_CSV_FILE):
        return
    with open(MASTER_CSV_FILE, "w", newline="", encoding="utf-8") as f:
        csv.writer(f, delimiter=";").writerow([
            "trigger_id", "timestamp_trigger", "league", "match", "matchup_id",
            "market", "line", "selected_side", "selected_points",
            "pinnacle_entry_odd", "pinnacle_opposite_odd",
            "movement_score", "persistence_score", "timing_score",
            "steam_dominance_pct", "fvs_score", "hours_to_kickoff",
            "bet365_entry_odd", "bet365_opposite_odd",
            "pinnacle_fair_prob_pct", "bet365_no_vig_prob_pct",
            "edge_pct", "ev_pct", "value_status",
            "bet365_closing_odd", "pinnacle_closing_odd",
            "clv_bet365_pct", "clv_pinnacle_pct",
            "result", "profit_units", "master_status"
        ])


def write_master_signal(ep):
    """
    One-row consolidated record for the complete lifecycle of a trigger.
    Written once after result capture, or when the episode is otherwise
    conclusively closed.
    """
    if ep.get("master_written", False):
        return

    value_status = (
        "VALUE"
        if ep.get("edge_pct", -999) >= 5.0
        and ep.get("bet365_selected_odd", 0) >= 1.80
        else "NO_VALUE"
    )

    result = ep.get("result", "")
    if result:
        status = "COMPLETE"
    elif ep.get("closing_captured", False):
        status = "CLOSE_ONLY"
    else:
        status = "INCOMPLETE"

    with open(MASTER_CSV_FILE, "a", newline="", encoding="utf-8") as f:
        csv.writer(f, delimiter=";").writerow([
            ep.get("trigger_id", ""),
            datetime.fromtimestamp(
                ep["trigger_time"], timezone.utc
            ).isoformat() if ep.get("trigger_time") else "",
            ep.get("league", ""),
            ep.get("match", ""),
            ep.get("matchup_id", ""),
            ep.get("market", ""),
            ep.get("ah_line", ""),
            ep.get("trigger_selected_side", ""),
            ep.get("trigger_selected_points", ""),
            round(ep.get("trigger_selected_odd", 0), 3),
            round(ep.get("trigger_opposite_odd", 0), 3),
            round(ep.get("trigger_movement_score", 0), 2),
            round(ep.get("trigger_persistence_score", 0), 2),
            round(ep.get("trigger_timing_score", 0), 2),
            round(ep.get("trigger_dominance", 0), 2),
            round(ep.get("trigger_fvs", 0), 2),
            round(ep.get("trigger_hours", 0), 2),
            round(ep.get("bet365_selected_odd", 0), 3),
            round(ep.get("bet365_opposite_odd", 0), 3),
            round(ep.get("pinnacle_fair_prob_pct", 0), 3),
            round(ep.get("bet365_no_vig_prob_pct", 0), 3),
            round(ep.get("edge_pct", 0), 3),
            round(ep.get("ev_pct", 0), 3),
            value_status,
            round(ep.get("bet365_closing_odd", 0), 3),
            round(ep.get("pinnacle_closing_odd", 0), 3),
            round(ep.get("clv_bet365_pct", 0), 3)
            if ep.get("clv_bet365_pct") is not None else "",
            round(ep.get("clv_pinnacle_pct", 0), 3)
            if ep.get("clv_pinnacle_pct") is not None else "",
            result,
            round(ep.get("profit_units", 0), 4)
            if result else "",
            status
        ])

    ep["master_written"] = True


def ensure_result_csv():
    if os.path.exists(RESULT_CSV_FILE):
        return
    with open(RESULT_CSV_FILE, "w", newline="", encoding="utf-8") as f:
        csv.writer(f, delimiter=";").writerow([
            "trigger_id", "timestamp_result",
            "league", "match", "matchup_id",
            "market", "line", "selected_side", "selected_points",
            "bet365_entry_odd", "value_status", "edge_pct",
            "result", "profit_units", "settlement_status"
        ])


def settle_result(ep, now_ts, home_score, away_score):
    """
    Pure settlement layer. It does not decide whether a trigger was good.
    It only settles the selected market side.
    """
    selected_side = ep.get("trigger_selected_side")
    market = ep["market"]
    points = float(ep["trigger_selected_points"])

    result = "UNKNOWN"

    if market == "total":
        total = home_score + away_score
        if selected_side == "over":
            if total > points:
                result = "WIN"
            elif total < points:
                result = "LOSS"
            else:
                result = "PUSH"

        elif selected_side == "under":
            if total < points:
                result = "WIN"
            elif total > points:
                result = "LOSS"
            else:
                result = "PUSH"

    elif market == "spread":
        # The selected AH side is evaluated using the match score.
        margin = home_score - away_score
        if selected_side == "home":
            adjusted = margin + points
        elif selected_side == "away":
            adjusted = -margin + points
        else:
            adjusted = None

        if adjusted is not None:
            if adjusted > 0:
                result = "WIN"
            elif adjusted < 0:
                result = "LOSS"
            else:
                result = "PUSH"

    odd = ep.get("bet365_selected_odd")
    if result == "WIN" and odd:
        profit = odd - 1.0
    elif result == "LOSS":
        profit = -1.0
    else:
        profit = 0.0

    with open(RESULT_CSV_FILE, "a", newline="", encoding="utf-8") as f:
        csv.writer(f, delimiter=";").writerow([
            ep["trigger_id"],
            datetime.fromtimestamp(now_ts, timezone.utc).isoformat(),
            ep["league"], ep["match"], ep["matchup_id"],
            ep["market"], ep["ah_line"],
            selected_side, points,
            round(odd, 3) if odd else "",
            "VALUE" if ep.get("edge_pct", -999) >= 5.0 and odd and odd >= 1.80 else "NO_VALUE",
            round(ep.get("edge_pct", 0.0), 3),
            result,
            round(profit, 4),
            "SETTLED"
        ])

    ep["result"] = result
    ep["profit_units"] = profit
    ep["result_captured"] = True
    write_master_signal(ep)

    print(
        f"🏁 RESULT | {ep['match']} | {selected_side} | "
        f"{result} | profit={profit:+.3f}u",
        flush=True
    )


def clamp_score(value, low=0, high=20):
    return max(low, min(high, int(value)))


def parse_score_from_event(event):
    """
    Defensive parser for common score payload shapes.
    Returns (home, away) or None.
    """
    candidates = [
        event.get("scores"),
        event.get("score"),
        event.get("result"),
    ]

    for data in candidates:
        if isinstance(data, dict):
            home = data.get("home")
            away = data.get("away")
            if home is not None and away is not None:
                try:
                    return int(home), int(away)
                except (TypeError, ValueError):
                    pass

    return None


def ensure_closing_csv():
    if os.path.exists(CLOSING_CSV_FILE):
        return
    with open(CLOSING_CSV_FILE, "w", newline="", encoding="utf-8") as f:
        csv.writer(f, delimiter=";").writerow([
            "trigger_id", "timestamp_closing", "league", "match", "matchup_id",
            "market", "line", "selected_side", "selected_points",
            "bet365_entry_odd", "bet365_closing_odd",
            "pinnacle_entry_odd", "pinnacle_closing_odd",
            "clv_bet365_pct", "clv_pinnacle_pct",
            "closing_status"
        ])


def calculate_clv(entry_odd, closing_odd):
    """
    Positive CLV means the closing price became less attractive to the bettor.
    For decimal odds, using implied probability:
        CLV = (1/closing - 1/entry) * 100
    Positive = closing implied probability > entry implied probability.
    """
    if not entry_odd or not closing_odd or entry_odd <= 1 or closing_odd <= 1:
        return None
    return ((1.0 / closing_odd) - (1.0 / entry_odd)) * 100.0


def capture_closing(ep, now_ts):
    """
    Capture the final Bet365/Pinnacle price once the match is about to start.
    This is deliberately separate from T+30.
    """
    if ep.get("closing_captured", False):
        return

    # Only close near kickoff; don't label an arbitrary late snapshot as close.
    hours_left = max(
        0.0,
        ep["hours_until_match_start"]
        - max(0.0, (now_ts - ep["start_time"]) / 3600.0)
    )
    if hours_left > 0.10:  # > 6 minutes from kickoff
        return

    selected_side = ep.get("trigger_selected_side")
    selected_odd = ep.get("steam_last_odd")
    opposite_odd = ep.get("opposite_last_odd")

    if selected_side != ep.get("steam_side"):
        selected_odd, opposite_odd = opposite_odd, selected_odd

    if not selected_odd:
        return

    bet365_closing = None
    if ep.get("bet365_event_id"):
        market_name = "Spread" if ep["market"] == "spread" else "Totals"
        board = get_bet365_board(ep["bet365_event_id"], market_name)
        if board:
            extracted = extract_bet365_market(
                board, market_name, selected_side,
                ep["trigger_selected_points"]
            )
            if extracted:
                bet365_closing = extracted[0]

    clv_b365 = calculate_clv(ep.get("bet365_selected_odd"), bet365_closing)
    clv_pinnacle = calculate_clv(ep.get("trigger_selected_odd"), selected_odd)

    with open(CLOSING_CSV_FILE, "a", newline="", encoding="utf-8") as f:
        csv.writer(f, delimiter=";").writerow([
            ep["trigger_id"],
            datetime.fromtimestamp(now_ts, timezone.utc).isoformat(),
            ep["league"], ep["match"], ep["matchup_id"],
            ep["market"], ep["ah_line"], selected_side,
            ep["trigger_selected_points"],
            round(ep.get("bet365_selected_odd", 0.0), 3),
            round(bet365_closing, 3) if bet365_closing else "",
            round(ep["trigger_selected_odd"], 3),
            round(selected_odd, 3),
            round(clv_b365, 3) if clv_b365 is not None else "",
            round(clv_pinnacle, 3) if clv_pinnacle is not None else "",
            "CLOSING_CAPTURED"
        ])

    ep["closing_captured"] = True
    ep["bet365_closing_odd"] = bet365_closing
    ep["pinnacle_closing_odd"] = selected_odd
    ep["clv_bet365_pct"] = clv_b365
    ep["clv_pinnacle_pct"] = clv_pinnacle

    print(
        f"🔒 CLOSE | {ep['match']} | {selected_side} | "
        f"Bet365 {ep.get('bet365_selected_odd', 0):.3f} → "
        f"{bet365_closing:.3f}" if bet365_closing else
        f"🔒 CLOSE | {ep['match']} | {selected_side} | "
        f"Pinnacle {ep['trigger_selected_odd']:.3f} → {selected_odd:.3f}",
        flush=True
    )


def fetch_bet365_result(ep, now_ts):
    """
    Retrieve final event score from the same Bet365 event provider.
    No result is inferred from the market price.
    """
    if ep.get("result_captured", False):
        return

    event_id = ep.get("bet365_event_id")
    if not ODDS_API_KEY or not event_id:
        return

    try:
        response = requests.get(
            f"{ODDS_API_BASE}/events/{event_id}",
            params={"apiKey": ODDS_API_KEY},
            timeout=20,
        )
        response.raise_for_status()
        event = response.json()

        status = str(event.get("status", "")).lower()
        if status not in ("finished", "complete", "completed", "settled"):
            return

        score = parse_score_from_event(event)
        if not score:
            return

        settle_result(ep, now_ts, score[0], score[1])

    except Exception as exc:
        print(f"⚠️ Result request failed: {exc}", flush=True)


def clamp(value, low=0.0, high=100.0):
    return max(low, min(high, value))


def timing_score(hours):
    # Neutral outside the preferred 2-8h window; peak near 5h.
    if hours is None:
        return 50.0
    h = float(hours)
    if 2.0 <= h <= 8.0:
        return 100.0
    if h < 2.0:
        return clamp(50.0 + (h / 2.0) * 50.0)
    if h <= 12.0:
        return clamp(100.0 - ((h - 8.0) / 4.0) * 50.0)
    return 50.0


def movement_score(movement_pct):
    # 12% movement is treated as the 100-point reference, capped.
    return clamp((movement_pct / 12.0) * 100.0)


def persistence_score(observations, duration_minutes):
    raw = math.log1p(max(0, observations)) * math.log1p(max(0.0, duration_minutes))
    return clamp((raw / 8.0) * 100.0)


def calculate_fvs(dominance_pct, movement_pct, observations, duration_minutes, hours):
    """
    FVS V3.1 does not use an independent probability from Pinnacle.
    Value/Edge will be calculated later from Bet365, separately.

    The original non-base weights are renormalized:
      dominance   35.71%
      movement    28.57%
      persistence 21.43%
      timing      14.29%
    """
    ps = persistence_score(observations, duration_minutes)
    ts = timing_score(hours)
    ms = movement_score(movement_pct)

    fvs = (
        (0.25 / 0.70) * dominance_pct
        + (0.20 / 0.70) * ms
        + (0.15 / 0.70) * ps
        + (0.10 / 0.70) * ts
    )
    return ps, ts, ms, clamp(fvs)



# Episode output is handled by write_market_episode().
# The previous write_episode() implementation has been removed because its
# schema contained the old base_prob field and was inconsistent with V3.1.

def get_matchups():
    response = session.get(
        LEAGUES_URL,
        timeout=30
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"LEAGUES HTTP {response.status_code}: "
            f"{response.text[:200]}"
        )

    leagues = response.json()
    matchup_map = {}

    for league in leagues:
        try:
            league_id = league.get("id")
            league_name = league.get("name", "UNKNOWN")

            if not league_id or is_blocked_league(league_name):
                continue

            url = (
                f"{BASE_URL}/0.1/leagues/"
                f"{league_id}/matchups"
            )

            response = session.get(url, timeout=30)

            time.sleep(random.uniform(0.25, 0.7))

            if response.status_code != 200:
                continue

            matchups = response.json()

            for matchup in matchups:
                try:
                    matchup_id = matchup.get("id")
                    start_time = matchup.get("startTime")

                    if not matchup_id or not start_time:
                        continue

                    match_time = datetime.fromisoformat(
                        start_time.replace("Z", "+00:00")
                    )

                    now = datetime.now(timezone.utc)

                    hours_until_match = (
                        (match_time - now).total_seconds()
                        / 3600
                    )

                    if (
                        hours_until_match < 0
                        or hours_until_match > SCAN_HOURS
                    ):
                        continue

                    participants = matchup.get(
                        "participants", []
                    )

                    home_team = None
                    away_team = None

                    for participant in participants:
                        alignment = participant.get(
                            "alignment"
                        )
                        name = participant.get(
                            "name", "UNKNOWN"
                        )

                        if alignment == "home":
                            home_team = name
                        elif alignment == "away":
                            away_team = name

                    if not home_team or not away_team:
                        continue

                    match_name = (
                        f"{home_team} vs {away_team}"
                    )

                    if is_blocked_match(match_name):
                        continue

                    matchup_map[matchup_id] = {
                        "match_name": match_name,
                        "league_name": league_name,
                        "hours_until_match": hours_until_match
                    }

                except Exception:
                    continue

        except Exception:
            continue

    return matchup_map

def process_market(
    matchup_id,
    match_info,
    market,
    now_ts
):
    """Collect ONLY full-match Asian Handicap -1/+1 as a paired market.

    One episode represents the complete AH-1 pair:
        home -1  <->  away +1
    or
        home +1  <->  away -1

    Both sides are stored in the episode so STEAM dominance is based on
    the cumulative shortening of both prices, not on the existence of a
    shortening episode on only one side.
    """
    market_type = market.get("type")
    period = market.get("period")

    if period != 0:
        return

    if market_type != "spread":
        return

    if market.get("isAlternate", False):
        return

    prices = market.get("prices", [])

    # We need the exact whole AH-1 pair in the same market:
    # home -1 / away +1 OR home +1 / away -1.
    pair = {}
    for price_data in prices:
        side = price_data.get("designation")
        american_price = price_data.get("price")
        points = price_data.get("points")

        if side not in ("home", "away") or american_price is None:
            continue

        if points not in (-1.0, 1.0):
            continue

        odd = american_to_decimal(american_price)
        if odd is None:
            continue

        pair[(side, float(points))] = odd

    # Exact AH-1 pair only.
    if (
        ("home", -1.0) not in pair
        or ("away", 1.0) not in pair
    ) and (
        ("home", 1.0) not in pair
        or ("away", -1.0) not in pair
    ):
        return

    if ("home", -1.0) in pair:
        ah_key = "home_-1"
        steam_side = "home"
        steam_points = -1.0
        opp_side = "away"
        opp_points = 1.0
    else:
        ah_key = "away_-1"
        steam_side = "away"
        steam_points = -1.0
        opp_side = "home"
        opp_points = 1.0

    steam_odd = pair[(steam_side, steam_points)]
    opp_odd = pair[(opp_side, opp_points)]

    # Group key is the AH-1 pair, NOT the individual side.
    key = (matchup_id, "ah1", ah_key)

    previous = previous_odds.get(key)
    current_pair = (steam_odd, opp_odd)
    previous_odds[key] = current_pair

    if previous is None:
        return

    prev_steam, prev_opp = previous
    move_steam = (
        ((prev_steam - steam_odd) / prev_steam) * 100.0
        if steam_odd < prev_steam else 0.0
    )
    move_opp = (
        ((prev_opp - opp_odd) / prev_opp) * 100.0
        if opp_odd < prev_opp else 0.0
    )

    total_new_move = move_steam + move_opp
    if total_new_move <= 0:
        return

    if total_new_move > MAX_EPISODE_MOVEMENT:
        return

    if key not in episodes:
        episodes[key] = {
            "episode_id": (
                f"{matchup_id}-ah1-{ah_key}-{int(now_ts)}"
            ),
            "start_time": now_ts,
            "last_update": now_ts,
            "league": match_info["league_name"],
            "match": match_info["match_name"],
            "matchup_id": matchup_id,
            "market": "spread",
            "ah_line": "AH-1",
            "steam_side": steam_side,
            "steam_points": steam_points,
            "opposite_side": opp_side,
            "opposite_points": opp_points,
            "steam_start_odd": steam_odd,
            "steam_last_odd": steam_odd,
            "opposite_start_odd": opp_odd,
            "opposite_last_odd": opp_odd,
            "cumulative_steam_move": 0.0,
            "cumulative_opposite_move": 0.0,
            "hours_until_match_start": match_info["hours_until_match"],
            "observations": 0,
            "triggered": False,
        }

    ep = episodes[key]

    # Keep the same AH-1 orientation throughout the episode.
    # Accumulate every shortening observed on each side.
    ep["cumulative_steam_move"] += move_steam
    ep["cumulative_opposite_move"] += move_opp

    ep["steam_last_odd"] = steam_odd
    ep["opposite_last_odd"] = opp_odd
    ep["last_update"] = now_ts
    ep["observations"] += 1

    # LIVE V3 trigger: select the currently dominant O/U side.
    duration_live = max(0.0, (now_ts - ep["start_time"]) / 60.0)
    total_live_move = (
        ep["cumulative_steam_move"] + ep["cumulative_opposite_move"]
    )
    if ep["cumulative_steam_move"] >= ep["cumulative_opposite_move"]:
        selected_live_side = ep["steam_side"]
        selected_live_points = ep["steam_points"]
        selected_live_odd = ep["steam_last_odd"]
        selected_live_move = ep["cumulative_steam_move"]
    else:
        selected_live_side = ep["opposite_side"]
        selected_live_points = ep["opposite_points"]
        selected_live_odd = ep["opposite_last_odd"]
        selected_live_move = ep["cumulative_opposite_move"]

    live_dominance = (
        (selected_live_move / total_live_move) * 100.0
        if total_live_move > 0 else 50.0
    )
    live_hours = max(
        0.0,
        ep["hours_until_match_start"]
        - max(0.0, (now_ts - ep["start_time"]) / 3600.0)
    )
    live_ps, live_ts, live_ms, live_fvs = calculate_fvs(
        live_dominance,
        selected_live_move,
        ep["observations"],
        duration_live,
        live_hours,
    )
    maybe_trigger(
        ep, now_ts,
        selected_live_side, selected_live_points,
        selected_live_odd, selected_live_move, live_dominance,
        live_ms, live_ps, live_ts, live_fvs
    )

    # LIVE V3 trigger: do not wait for episode finalization.
    duration_live = max(0.0, (now_ts - ep["start_time"]) / 60.0)
    live_move = ep["cumulative_steam_move"]
    total_live_move = live_move + ep["cumulative_opposite_move"]
    live_dominance = (
        (live_move / total_live_move) * 100.0
        if total_live_move > 0 else 50.0
    )
    live_hours = max(
        0.0,
        ep["hours_until_match_start"]
        - max(0.0, (now_ts - ep["start_time"]) / 3600.0)
    )
    live_ps, live_ts, live_ms, live_fvs = calculate_fvs(
        live_dominance,
        live_move,
        ep["observations"],
        duration_live,
        live_hours,
    )
    maybe_trigger(
        ep, now_ts,
        ep["steam_side"], ep["steam_points"],
        ep["steam_last_odd"], live_move, live_dominance,
        live_ms, live_ps, live_ts, live_fvs
    )

def process_ou25_market(
    matchup_id,
    match_info,
    market,
    now_ts
):
    """Collect ONLY full-match Over/Under 2.5 as a paired market."""
    market_type = market.get("type")
    period = market.get("period")

    if period != 0 or market_type != "total":
        return

    if market.get("isAlternate", False):
        return

    prices = market.get("prices", [])

    pair = {}
    for price_data in prices:
        side = price_data.get("designation")
        american_price = price_data.get("price")
        points = price_data.get("points")

        if side not in ("over", "under") or american_price is None:
            continue

        try:
            points_f = float(points)
        except (TypeError, ValueError):
            continue

        if points_f != 2.5:
            continue

        odd = american_to_decimal(american_price)
        if odd is None:
            continue

        pair[side] = odd

    if "over" not in pair or "under" not in pair:
        return

    steam_side = "over"
    opp_side = "under"
    steam_odd = pair["over"]
    opp_odd = pair["under"]

    key = (matchup_id, "ou25")

    previous = previous_odds.get(key)
    current_pair = (steam_odd, opp_odd)
    previous_odds[key] = current_pair

    if previous is None:
        return

    prev_over, prev_under = previous
    move_over = (
        ((prev_over - steam_odd) / prev_over) * 100.0
        if steam_odd < prev_over else 0.0
    )
    move_under = (
        ((prev_under - opp_odd) / prev_under) * 100.0
        if opp_odd < prev_under else 0.0
    )

    total_new_move = move_over + move_under
    if total_new_move <= 0 or total_new_move > MAX_EPISODE_MOVEMENT:
        return

    if key not in episodes:
        episodes[key] = {
            "episode_id": f"{matchup_id}-ou25-{int(now_ts)}",
            "start_time": now_ts,
            "last_update": now_ts,
            "league": match_info["league_name"],
            "match": match_info["match_name"],
            "matchup_id": matchup_id,
            "market": "total",
            "ah_line": "OU-2.5",
            "steam_side": "over",
            "steam_points": 2.5,
            "opposite_side": "under",
            "opposite_points": 2.5,
            "steam_start_odd": steam_odd,
            "steam_last_odd": steam_odd,
            "opposite_start_odd": opp_odd,
            "opposite_last_odd": opp_odd,
            "cumulative_steam_move": 0.0,
            "cumulative_opposite_move": 0.0,
            "hours_until_match_start": match_info["hours_until_match"],
            "observations": 0,
            "triggered": False,
        }

    ep = episodes[key]

    ep["cumulative_steam_move"] += move_over
    ep["cumulative_opposite_move"] += move_under
    ep["steam_last_odd"] = steam_odd
    ep["opposite_last_odd"] = opp_odd
    ep["last_update"] = now_ts
    ep["observations"] += 1

    duration_live = max(0.0, (now_ts - ep["start_time"]) / 60.0)
    total_live_move = ep["cumulative_steam_move"] + ep["cumulative_opposite_move"]

    if ep["cumulative_steam_move"] >= ep["cumulative_opposite_move"]:
        selected_live_side = ep["steam_side"]
        selected_live_points = ep["steam_points"]
        selected_live_odd = ep["steam_last_odd"]
        selected_live_move = ep["cumulative_steam_move"]
    else:
        selected_live_side = ep["opposite_side"]
        selected_live_points = ep["opposite_points"]
        selected_live_odd = ep["opposite_last_odd"]
        selected_live_move = ep["cumulative_opposite_move"]

    live_dominance = (
        (selected_live_move / total_live_move) * 100.0
        if total_live_move > 0 else 50.0
    )
    live_hours = max(
        0.0,
        ep["hours_until_match_start"]
        - max(0.0, (now_ts - ep["start_time"]) / 3600.0)
    )

    live_ps, live_ts, live_ms, live_fvs = calculate_fvs(
        live_dominance,
        selected_live_move,
        ep["observations"],
        duration_live,
        live_hours,
    )

    maybe_trigger(
        ep, now_ts,
        selected_live_side, selected_live_points,
        selected_live_odd, selected_live_move, live_dominance,
        live_ms, live_ps, live_ts, live_fvs
    )


def maybe_trigger(ep, now_ts, selected_side, selected_points,
                  selected_end, selected_move, dominance,
                  movement_score_value, persistence_score_value,
                  timing_score_value, fvs):
    """
    Real-time trigger:
      movement_score >= 30
      AND fvs >= 55

    Fires on the first live observation that reaches both thresholds.
    After firing, Pinnacle snapshots are collected at T0, +5, +15 and +30.
    """
    global triggered_signals

    # Continue collecting scheduled snapshots for an already triggered episode.
    if ep.get("triggered", False):
        capture_value(ep, now_ts)
        maybe_write_due_snapshots(ep, now_ts)
        return

    if movement_score_value < 30.0 or fvs < 55.0:
        return

    if selected_side == ep["steam_side"]:
        opposite_odd = ep["opposite_last_odd"]
    else:
        opposite_odd = ep["steam_last_odd"]

    trigger_id = f"{ep['episode_id']}-TRG"

    with open(TRIGGER_CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            trigger_id,
            datetime.fromtimestamp(now_ts, timezone.utc).isoformat(),
            ep["league"],
            ep["match"],
            ep["matchup_id"],
            ep["market"],
            ep["ah_line"],
            selected_side,
            selected_points,
            round(selected_end, 3),
            round(opposite_odd, 3),
            round(movement_score_value, 2),
            round(persistence_score_value, 2),
            round(timing_score_value, 2),
            round(dominance, 2),
            round(fvs, 2),
            round(max(0.0, ep["hours_until_match_start"]), 2),
            "TRIGGERED",
            "Pinnacle"
        ])

    ep["triggered"] = True
    ep["trigger_time"] = now_ts
    ep["trigger_id"] = trigger_id
    ep["trigger_selected_side"] = selected_side
    ep["trigger_selected_points"] = selected_points
    ep["trigger_selected_odd"] = selected_end
    ep["trigger_opposite_odd"] = opposite_odd
    ep["trigger_movement_score"] = movement_score_value
    ep["trigger_persistence_score"] = persistence_score_value
    ep["trigger_timing_score"] = timing_score_value
    ep["trigger_dominance"] = dominance
    ep["trigger_fvs"] = fvs
    ep["trigger_hours"] = max(0.0, ep["hours_until_match_start"])
    ep["snapshots_written"] = set()

    triggered_signals += 1

    # T0 is written immediately.
    write_snapshot(ep, "T+0m", now_ts, "TRIGGER")

    # VALUE is calculated from Pinnacle only; Bet365 is checked manually by the user.
    capture_value(ep, now_ts)

    print(
        f"🚨 STEAM TRIGGER #{triggered_signals} | "
        f"{ep['league']} | {ep['match']} | "
        f"{ep['market']} {selected_side} {selected_points:+.1f} | "
        f"odd={selected_end:.3f} | mov={selected_move:.2f}% | "
        f"FVS={fvs:.1f} | obs={ep['observations']} | "
        f"T-{max(0.0, ep['hours_until_match_start']):.2f}h | "
        f"VALUE>={ep.get('min_value_odds', 0):.3f}",
        flush=True
    )

def finalize_stale_episodes(now_ts):
    stale_keys = []

    for key, ep in episodes.items():
        inactive_minutes = (now_ts - ep["last_update"]) / 60

        # A triggered episode must remain active until T+30m so the
        # scheduled Pinnacle follow-up snapshots are not lost.
        if ep.get("triggered", False):
            trigger_age_minutes = (now_ts - ep.get("trigger_time", now_ts)) / 60.0
            if trigger_age_minutes < 30.0:
                continue

        if inactive_minutes >= EPISODE_RESET_MINUTES:
            total_move = (
                ep["cumulative_steam_move"]
                + ep["cumulative_opposite_move"]
            )

            if total_move >= MIN_EPISODE_MOVEMENT:
                if ep["market"] == "spread":
                    # AH-1: the target is always the -1 side.
                    steam_move = ep["cumulative_steam_move"]
                    opp_move = ep["cumulative_opposite_move"]
                    dominance = (
                        (steam_move / total_move) * 100.0
                        if total_move > 0 else 50.0
                    )

                    selected_side = ep["steam_side"]
                    selected_points = ep["steam_points"]
                    selected_start = ep["steam_start_odd"]
                    selected_end = ep["steam_last_odd"]
                    selected_move = steam_move

                else:
                    # O/U 2.5: select whichever side accumulated more steam.
                    if ep["cumulative_steam_move"] >= ep["cumulative_opposite_move"]:
                        selected_side = ep["steam_side"]
                        selected_points = ep["steam_points"]
                        selected_start = ep["steam_start_odd"]
                        selected_end = ep["steam_last_odd"]
                        selected_move = ep["cumulative_steam_move"]
                        dominance = (
                            selected_move / total_move * 100.0
                            if total_move > 0 else 50.0
                        )
                    else:
                        selected_side = ep["opposite_side"]
                        selected_points = ep["opposite_points"]
                        selected_start = ep["opposite_start_odd"]
                        selected_end = ep["opposite_last_odd"]
                        selected_move = ep["cumulative_opposite_move"]
                        dominance = (
                            selected_move / total_move * 100.0
                            if total_move > 0 else 50.0
                        )

                duration = max(
                    0,
                    (ep["last_update"] - ep["start_time"]) / 60
                )

                movement_score = clamp((selected_move / 12.0) * 100.0)
                persistence_score = clamp(
                    (math.log1p(ep["observations"])
                     * math.log1p(duration) / 8.0) * 100.0
                )
                hours = ep["hours_until_match_start"]
                timing_value = timing_score(hours)
                _, _, _, fvs = calculate_fvs(
                    dominance,
                    selected_move,
                    ep["observations"],
                    duration,
                    hours,
                )

                write_market_episode(
                    ep,
                    selected_side,
                    selected_points,
                    selected_start,
                    selected_end,
                    selected_move,
                    dominance,
                    duration,
                    movement_score,
                    persistence_score,
                    timing_value,
                    fvs,
                )

            stale_keys.append(key)

    for key in stale_keys:
        episodes.pop(key, None)



def write_market_episode(
    ep,
    selected_side,
    selected_points,
    selected_start,
    selected_end,
    selected_move,
    dominance,
    duration,
    movement_score,
    persistence_score,
    timing_score_value,
    fvs,
):
    global completed_episodes

    # The episode keeps a fixed internal orientation (over/under for O/U;
    # -1/+1 for AH-1). The CSV, however, must always describe the selected
    # steam side and its TRUE opposite side. This is especially important
    # for O/U 2.5, where the selected side may be Under even though the
    # internal episode was initialized as Over.
    if selected_side == ep["steam_side"]:
        output_opposite_side = ep["opposite_side"]
        output_opposite_points = ep["opposite_points"]
        output_opposite_move = ep["cumulative_opposite_move"]
        output_opposite_start = ep["opposite_start_odd"]
        output_opposite_end = ep["opposite_last_odd"]
    else:
        output_opposite_side = ep["steam_side"]
        output_opposite_points = ep["steam_points"]
        output_opposite_move = ep["cumulative_steam_move"]
        output_opposite_start = ep["steam_start_odd"]
        output_opposite_end = ep["steam_last_odd"]

    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            ep["episode_id"],
            datetime.fromtimestamp(ep["start_time"], timezone.utc).isoformat(),
            datetime.fromtimestamp(ep["last_update"], timezone.utc).isoformat(),
            ep["league"],
            ep["match"],
            ep["matchup_id"],
            ep["market"],
            ep["ah_line"],
            selected_side,
            selected_points,
            round(selected_start, 3),
            round(selected_end, 3),
            round(selected_move, 3),
            round(output_opposite_move, 3),
            output_opposite_side,
            output_opposite_points,
            round(output_opposite_start, 3),
            round(output_opposite_end, 3),
            round(dominance, 2),
            ep["observations"],
            round(duration, 2),
            round(ep["hours_until_match_start"], 2),
            round(movement_score, 2),
            round(persistence_score, 2),
            round(timing_score_value, 2),
            round(fvs, 2),
        ])

    completed_episodes += 1

    print(
        f"📌 {ep['ah_line']} #{ep['episode_id']} | {ep['league']} | {ep['match']} | "
        f"{selected_side} {selected_points:+.1f} | "
        f"{selected_start:.3f} → {selected_end:.3f} | "
        f"mov={selected_move:.2f}% | STEAM={dominance:.1f}% | "
        f"opp={ep['cumulative_opposite_move']:.2f}% | "
        f"FVS={fvs:.1f} | obs={ep['observations']}",
        flush=True,
    )

def run_cycle():
    now_ts = time.time()

    matchup_map = get_matchups()

    cycle_movements = 0
    cycle_markets = 0

    for matchup_id, match_info in matchup_map.items():
        try:
            market_url = (
                f"{BASE_URL}/0.1/matchups/"
                f"{matchup_id}/markets/related/straight"
            )

            response = session.get(
                market_url,
                timeout=30
            )

            time.sleep(random.uniform(0.15, 0.45))

            if response.status_code != 200:
                continue

            markets = response.json()

            for market in markets:
                before = len(episodes)

                process_market(
                    matchup_id,
                    match_info,
                    market,
                    now_ts
                )

                process_ou25_market(
                    matchup_id,
                    match_info,
                    market,
                    now_ts
                )

                after = len(episodes)

                cycle_markets += 1
                if after > before:
                    cycle_movements += 1

        except Exception:
            continue

    # Follow every triggered episode on each poll so T+5/T+15/T+30
    # snapshots are collected even when the market temporarily stops shortening.
    for ep in list(episodes.values()):
        if ep.get("triggered", False):
            capture_value(ep, now_ts)
            maybe_write_due_snapshots(ep, now_ts)
            capture_closing(ep, now_ts)

    finalize_stale_episodes(now_ts)

    return (
        len(matchup_map),
        cycle_markets,
        cycle_movements,
        len(episodes)
    )


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------

print(
    "\n⚽ FOOTBALL MOVEMENT ENGINE AH-1 + O/U 2.5\n"
    "MODE: OBSERVATION / HISTORICAL COLLECTION + T0/T+5/T+15/T+30\n"
    "NO BETS | PINNACLE VALUE | TELEGRAM | NO BET365 API | NO GOOGLE SHEETS\n"
    f"WINDOW: next {SCAN_HOURS}h | POLL: {POLL_SECONDS}s\n"
    f"MIN EPISODE MOVEMENT: {MIN_EPISODE_MOVEMENT}% "
    f"(observation filter only)\n"
    f"RESET AFTER: {EPISODE_RESET_MINUTES} min\n"
    f"MARKETS: AH-1 + O/U 2.5\n"
    f"CSV EPISODES: {CSV_FILE}\n"
    f"CSV TRIGGERS: {TRIGGER_CSV_FILE}\n"
    f"CSV SNAPSHOTS: {SNAPSHOT_CSV_FILE}\n"
    f"CSV VALUE: {VALUE_CSV_FILE}\n"
    f"CSV CLOSING: {CLOSING_CSV_FILE}\n"
    f"CSV RESULTS: {RESULT_CSV_FILE}\n"
    f"CSV MASTER: {MASTER_CSV_FILE}\n"
    f"VALUE TARGET: {VALUE_EDGE_TARGET_PCT:.1f}% EV | MIN ENTRY ODDS: {MIN_ENTRY_ODDS:.2f}\n"
    f"TELEGRAM: {'ENABLED' if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID else 'DISABLED (set BOT_TOKEN + CHAT_ID)'}\n",
    flush=True
)

ensure_csv()
ensure_trigger_csv()
ensure_snapshot_csv()
ensure_value_csv()
ensure_closing_csv()
ensure_result_csv()
ensure_master_csv()

cycle = 0

while True:
    cycle += 1
    started = time.time()

    try:
        matches, markets, new_eps, active_eps = run_cycle()

        elapsed = time.time() - started

        print(
            f"💓 CYCLE {cycle} | "
            f"matches={matches} | "
            f"markets={markets} | "
            f"new_episodes={new_eps} | "
            f"active={active_eps} | "
            f"completed={completed_episodes} | "
            f"triggers={triggered_signals} | "
            f"value={value_signals} | "
            f"{elapsed:.1f}s",
            flush=True
        )

    except KeyboardInterrupt:
        print(
            "\n🛑 Scanner aturat per l'usuari.",
            flush=True
        )
        break

    except Exception as e:
        print(
            f"ERROR CYCLE: {e}",
            flush=True
        )

    time.sleep(POLL_SECONDS)
