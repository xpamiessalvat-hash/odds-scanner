"""Fail-closed Bet365 AH -1 validation harness.

This is a validation tool, not a betting bot. It never places bets or sends alerts.
It deliberately returns no quote unless the page text explicitly ties a decimal
price to the requested team and exact -1 handicap selection.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright


ODD_RE = re.compile(r"(?<!\d)([1-9]\d?\.\d{2})(?!\d)")
HANDICAP_RE = re.compile(
    r"(?:asian\s*)?(?:handicap|hándicap|spread|\bah\b)", re.IGNORECASE
)


def norm(value: str) -> str:
    value = value.casefold().replace("’", "'")
    value = re.sub(r"\b(fc|cf|sc|afc)\b", " ", value)
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def team_matches(line: str, team: str) -> bool:
    wanted = norm(team)
    actual = norm(line)
    return bool(wanted and (wanted in actual or actual in wanted))


def parse_explicit_selection(lines: list[str], team: str, handicap: int) -> Optional[float]:
    """Accept only a line explicitly naming the team and its exact handicap."""
    candidates: list[float] = []
    for i, line in enumerate(lines):
        if not team_matches(line, team):
            continue
        # The handicap and team must be on the same line; price may be
        # immediately after it on this line or within the next two lines.
        target = r"(?<![\d.])-1(?:\.0)?(?!\d)" if handicap < 0 else r"(?<![\d.])\+?1(?:\.0)?(?!\d)"
        if not re.search(target, line):
            continue
        for nearby in lines[i : min(i + 3, len(lines))]:
            candidates.extend(float(x) for x in ODD_RE.findall(nearby))
        if candidates:
            break
    # Ambiguous multiple prices => fail closed.
    unique = sorted(set(candidates))
    return unique[0] if len(unique) == 1 else None


def extract_ah1_quotes(
    page_text: str, home_team: str, away_team: str
) -> dict:
    lines = [x.strip() for x in page_text.splitlines() if x.strip()]
    home_idx = [i for i, x in enumerate(lines) if team_matches(x, home_team)]
    away_idx = [i for i, x in enumerate(lines) if team_matches(x, away_team)]
    if not home_idx or not away_idx:
        return {"ok": False, "reason": "match_not_found"}

    # Use the first team occurrence as an anchor and require both teams and
    # an explicit handicap heading in the same bounded text region.
    anchors = sorted(set(home_idx + away_idx))
    region = lines[max(0, anchors[0] - 3) : min(len(lines), anchors[-1] + 100)]
    if not any(HANDICAP_RE.search(x) for x in region):
        return {"ok": False, "reason": "handicap_market_heading_not_found"}

    home_odd = parse_explicit_selection(region, home_team, -1)
    away_odd = parse_explicit_selection(region, away_team, +1)
    if home_odd is None or away_odd is None:
        return {
            "ok": False,
            "reason": "exact_home_and_away_minus_one_quotes_not_unambiguously_parsed",
            "home_odd": home_odd,
            "away_odd": away_odd,
        }
    if home_odd <= 1.0 or away_odd <= 1.0:
        return {"ok": False, "reason": "invalid_decimal_odds"}
    return {
        "ok": True,
        "market": "AH",
        "line": -1.0,
        "home_team": home_team,
        "home_odd": home_odd,
        "away_team": away_team,
        "away_odd": away_odd,
    }


def save_run(db_path: str, record: dict) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS bet365_validation_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                captured_at_utc TEXT NOT NULL,
                home_team TEXT NOT NULL,
                away_team TEXT NOT NULL,
                result_json TEXT NOT NULL,
                page_text_file TEXT
            )"""
        )
        conn.execute(
            """INSERT INTO bet365_validation_runs
               (captured_at_utc, home_team, away_team, result_json, page_text_file)
               VALUES (?, ?, ?, ?, ?)""",
            (
                record["captured_at_utc"],
                record["home_team"],
                record["away_team"],
                json.dumps(record["result"], ensure_ascii=False),
                record.get("page_text_file"),
            ),
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", required=True)
    parser.add_argument("--away", required=True)
    parser.add_argument("--url", default="https://www.bet365.es")
    parser.add_argument("--db", default="data/bet365_validation.sqlite3")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    page_text = ""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        context = browser.new_context(locale="es-ES")
        page = context.new_page()
        try:
            page.goto(args.url, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(12000)
            page_text = page.locator("body").inner_text(timeout=30000)
        finally:
            context.close()
            browser.close()

    timestamp = datetime.now(timezone.utc).isoformat()
    dump_dir = Path("data/bet365_page_dumps")
    dump_dir.mkdir(parents=True, exist_ok=True)
    dump_path = dump_dir / (timestamp.replace(":", "-") + ".txt")
    dump_path.write_text(page_text, encoding="utf-8")

    result = extract_ah1_quotes(page_text, args.home, args.away)
    record = {
        "captured_at_utc": timestamp,
        "home_team": args.home,
        "away_team": args.away,
        "result": result,
        "page_text_file": str(dump_path),
    }
    save_run(args.db, record)
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
