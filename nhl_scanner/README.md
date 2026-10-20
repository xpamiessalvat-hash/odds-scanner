# NHL independent scanner — Stage 1

This directory is isolated from the football and baseball scanner entry points.

## Current scope

- Pinnacle API, NHL league ID `1456`
- Main game markets only: moneyline, puck line `±1.5`, and game totals
- Only open full-game markets (`period == 0`), filtered to games starting within the next 24 hours
- Polls every 120 seconds by default
- Appends normalized decimal odds and original American prices to `nhl_snapshots.csv`
- Writes UTC and `Europe/Madrid` timestamps
- Paper/data-collection mode only: no bets, no alerts, no value or steam signals yet

## Railway service setup

Create a **new service** in the existing Railway project and point it at this repository. Configure the service's **Root Directory** as `/nhl_scanner` and start command as:

```bash
python nhl_scanner.py
```

Required variable:
- `PINNACLE_X_API_KEY` — set it only in Railway Variables; never commit it or paste it into chat.

Optional variables:
- `POLL_SECONDS` (default `120`; minimum effective interval is 30 seconds)
- `LOOKAHEAD_HOURS` (default `24`)
- `DATA_DIR` (default current directory; point this at a mounted Railway Volume if snapshots must survive restarts)

Install dependencies from `requirements.txt`.

## Data persistence

The output CSV is append-only. Railway's local filesystem may be ephemeral, so attach a persistent volume and set `DATA_DIR` to its mount path before relying on long-term CLV or ROI analysis.

## Next stages (not implemented yet)

1. Verify captured rows and line selection over several cycles.
2. Add a Pinnacle-vs-The-Odds-API comparison adapter only after the NHL endpoint is confirmed accessible under the available plan.
3. Define steam/value thresholds from observed data rather than inventing them.
4. Add paper-pick lifecycle, closing-line snapshots, final scores, CLV, ROI, and reporting.
5. Add notifications only after data integrity is validated.

No files or entry points for the existing football/baseball scanners are changed by this stage.
