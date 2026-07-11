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

        if key not in previous_odds:
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