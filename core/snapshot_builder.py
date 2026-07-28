from core.models import (
    MarketSnapshot,
    MarketSide
)

from core.utils import (
    american_to_decimal
)


def build_snapshot(
    matchup_id,
    data,
    market,
    prices,
    previous_odds
):

    sides = []

    for price in prices:

        designation = price.get(
            "designation"
        )

        points = price.get(
            "points",
            ""
        )

        new_american = price.get(
            "price"
        )

        key = (
            matchup_id,
            market["type"],
            designation,
            points
        )

        print(
            f"BUSCANT: {repr(key)}",
            flush=True
        )

        if key not in previous_odds:

            print(
                "NO TROBADA",
                flush=True
            )

            if previous_odds:

                coincidencies = [
                    k
                    for k in previous_odds.keys()
                    if k[0] == matchup_id
                ]

                print(
                    f"CLAUS PER MATCHUP {matchup_id}: {len(coincidencies)}",
                    flush=True
                )

                if coincidencies:

                    print(
                        "CLAUS DEL MATCHUP:",
                        flush=True
                    )

                    for k in coincidencies:
                        print(
                            f"   {repr(k)}",
                            flush=True
                        )

            continue

        old_american = previous_odds[key]

        side = MarketSide(

            designation=designation,

            points=points,

            old_american=old_american,

            new_american=new_american,

            old_decimal=american_to_decimal(
                old_american
            ),

            new_decimal=american_to_decimal(
                new_american
            )

        )

        sides.append(side)

    if len(sides) != 2:

        print(
            f"SNAPSHOT DESCARTAT | "
            f"{data['match_name']} | "
            f"{market['type']} | "
            f"sides={len(sides)}",
            flush=True
        )

        for price in prices:

            designation = price.get(
                "designation"
            )

            points = price.get(
                "points",
                ""
            )

            key = (
                matchup_id,
                market["type"],
                designation,
                points
            )

            print(
                f"  {designation} {points} -> "
                f"{'OK' if key in previous_odds else 'NO'}",
                flush=True
            )

        return None

    designations = {
        side.designation.lower()
        for side in sides
    }

    if len(designations) != 2:
        return None

    sides.sort(
        key=lambda side: side.designation
    )

    return MarketSnapshot(

        matchup_id=matchup_id,

        match=data["match_name"],

        league=data["league"],

        market=market["type"],

        period=market["period"],

        points=prices[0].get(
            "points",
            ""
        ),

        sides=sides

    )