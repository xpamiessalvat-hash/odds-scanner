# EARLY VALUE SCANNER — AH -1 validation stage

This branch is isolated from the existing scanner. Nothing here places bets,
sends Telegram messages, or changes the current scanner.

## Purpose
Validate whether the existing Bet365 website-reading approach can reliably
capture both selections of the exact Asian Handicap -1 market for a named match.

## Current status
- Browser navigation and page-text capture: implemented.
- SQLite audit log and raw page-text dumps: implemented.
- Fail-closed parser and unit tests: implemented.
- Live Bet365 DOM/market extraction: NOT YET VALIDATED. The parser intentionally
  rejects ambiguous layouts rather than guessing.
- Pinnacle integration, T-24/T-12 scheduler, EV alerts and performance workbook:
  deliberately not part of this validation stage.

## Run locally
Install dependencies:
`pip install -r requirements.txt`
`playwright install chromium`

Run a visible browser:
`python bet365_ah1_validator.py --home "Home Team" --away "Away Team" --headed`

The tool opens Bet365, waits for the page, stores the visible page text under
`data/bet365_page_dumps/`, and logs the parse result in
`data/bet365_validation.sqlite3`. Use a match that is actually listed on
Bet365 at the time of the test. If the market is not present in the captured
page text, the result will be a rejection, not a guessed quote.

Run parser tests:
`python -m unittest -v test_bet365_ah1_validator.py`

## Acceptance criteria before integration
1. Exact match is identified (both teams).
2. The market heading is explicitly Asian Handicap / Handicap.
3. Home -1 and away -1 selections are individually and unambiguously identified.
4. Both decimal odds are captured and manually checked against the visible page.
5. Repeat across several leagues and matches, including home and away selections.
6. No false positive in negative tests.

Only after these checks should this adapter be connected to Pinnacle and the
T-24/T-12 paper-data collector. Bet365 page layouts may vary by region/session;
manual comparison is mandatory during validation.
