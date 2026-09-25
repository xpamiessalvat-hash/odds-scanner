import os
import sys
import time

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

try:
    from core.snapshot_builder import build_snapshot
except ImportError:
    from snapshot_builder import build_snapshot

try:
    from core.api import PinnacleAPI  # type: ignore[import]
    from core.cache import OddsCache  # type: ignore[import]
    from core.market_engine import MarketEngine  # type: ignore[import]
except ImportError:
    from api import PinnacleAPI
    from cache import OddsCache
    from market_engine import MarketEngine

try:
    from core.notifier import SteamNotifier
except ImportError:
    from notifier import SteamNotifier


class BaseballScanner:

    def __init__(self):

        self.api = PinnacleAPI()
        self.cache = OddsCache()
        self.engine = MarketEngine()
        self.notifier = SteamNotifier()

        self.running = True

    def run(self):

        print(
            "\n⚾ BASEBALL SCANNER V4 ⚾",
            flush=True
        )

        while self.running:

            try:

                self.process_matchups()

            except KeyboardInterrupt:

                print(
                    "\nScanner aturat per l'usuari.",
                    flush=True
                )

                break

            except Exception as e:

                print(
                    f"ERROR: {e}",
                    flush=True
                )

            finally:
                time.sleep(60)

    def process_matchups(self):

        leagues = self.api.get_leagues()

        print(
            f"LEAGUES TROBADES: {len(leagues)}",
            flush=True
        )

        for league in leagues:

            league_id = league.get("id")

            if league_id != 246:
                continue

            print(
                f"PROCESSANT LLIGA: {league.get('name')}",
                flush=True
            )

            matchups = self.api.get_matchups(
                league_id
            )

            print(
                f"MATCHUPS: {len(matchups)}",
                flush=True
            )

            for matchup in matchups:

                self.process_matchup(
                    matchup,
                    league
                )

    def process_matchup(
        self,
        matchup,
        league
    ):

        if matchup.get("parentId"):
            return

        participants = matchup.get(
            "participants",
            []
        )

        home = None
        away = None

        for participant in participants:

            alignment = participant.get(
                "alignment"
            )

            if alignment == "home":
                home = participant.get("name")

            elif alignment == "away":
                away = participant.get("name")

        if not home or not away:
            return

        if "(" in home or "(" in away:
            return

        if "Games" in home or "Games" in away:
            return

        matchup_id = matchup.get("id")

        data = {

            "match_name": f"{home} vs {away}",

            "league": league.get("name"),

            "start_time": matchup.get("startTime")

        }

        markets = self.api.get_markets(
            matchup_id
        )

        print(
            f"{data['match_name']} -> markets={len(markets)}",
            flush=True
        )

        for market in markets:

            self.process_market(
                matchup_id,
                data,
                market
            )

    def process_market(
        self,
        matchup_id,
        data,
        market
    ):

        prices = market.get(
            "prices",
            []
        )

        if len(prices) != 2:
            return

        if "designation" not in prices[0]:
            return

        if market.get("type") not in (
            "moneyline",
            "spread",
            "total"
        ):
            return

        if market.get("period") != 0:
            return

        if market.get(
            "isAlternate",
            False
        ):
            return

        snapshot = build_snapshot(

            matchup_id,

            data,

            market,

            prices,

            self.cache.previous_odds

        )

        if snapshot is None:

            for price in prices:

                key = (

                    matchup_id,

                    market["type"],

                    price.get("designation"),

                    price.get("points", "")

                )

                self.cache.update(
                    key,
                    price.get("price")
                )

            return

        print(
            f"SNAPSHOT OK | "
            f"{snapshot.match} | "
            f"{snapshot.market}",
            flush=True
        )

        signal = self.engine.analyze(
            snapshot
        )

        for side in snapshot.sides:

            key = (

                matchup_id,

                market["type"],

                side.designation,

                side.points

            )

            self.cache.update(
                key,
                side.new_american
            )

        if signal is None:
            return

        print(
            f"STEAM DETECTAT | "
            f"{signal.match} | "
            f"{signal.market} | "
            f"{signal.selection}",
            flush=True
        )


if __name__ == "__main__":

    scanner = BaseballScanner()

    scanner.run()